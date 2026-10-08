import asyncio
import logging
import os
import platform
import random
import secrets
import time
from datetime import timedelta

import psutil
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import aiogram
import config
import database
import keyboards
import security
import states
import utils


cmd_router = Router()
callback_router = Router()
message_router = Router()


async def get_admin_level_for_message(message: Message) -> int:
    if not message.from_user:
        return 0

    return await database.get_admin_level(message.from_user.id)


async def get_admin_level_for_callback(cb: CallbackQuery) -> int:
    if not cb.from_user:
        return 0

    return await database.get_admin_level(cb.from_user.id)


async def send_captcha(bot, chat_id: int, state: FSMContext, user_id: int, fails: int = 0):
    row = await database.get_fresh_user(user_id)

    if row and row["captcha_locked_until"] and row["captcha_locked_until"] > utils.now_utc():
        remaining = row["captcha_locked_until"] - utils.now_utc()
        await utils.safe_send(
            bot,
            chat_id,
            f"❌ Слишком много попыток капчи. Попробуйте через {utils.format_timedelta(remaining)}.",
        )
        return

    correct = random.choice(config.ANIMALS)
    wrong = random.sample(
        [a for a in config.ANIMALS if a["slug"] != correct["slug"]],
        7,
    )

    options = [correct] + wrong
    random.shuffle(options)

    await state.set_state(states.CaptchaStates.captcha)
    await state.update_data(correct=correct["slug"], fails=fails)

    await utils.safe_send(
        bot,
        chat_id,
        f"Прежде чем начать пользоваться ботом решите капчу. "
        f"Какое животное изображено на эмодзи {correct['emoji']}?",
        reply_markup=keyboards.captcha_kb(options),
    )


async def after_captcha(bot, chat_id: int, tg_user, state: FSMContext):
    await database.upsert_user(tg_user)

    row = await database.get_fresh_user(tg_user.id)
    level = await database.get_admin_level(tg_user.id)

    if level > 0:
        admin_row = await database.get_admin(tg_user.id)

        if admin_row and admin_row["nickname"]:
            await send_admin_panel(bot, chat_id, admin_row["nickname"], level)
        else:
            await start_first_admin(bot, chat_id, tg_user.id, state)
    else:
        if row and row["greeted"]:
            await start_returning_user(bot, chat_id, tg_user, state)
        else:
            await start_first_user(bot, chat_id, tg_user.id, state)


async def intro_sequence(bot, chat_id: int):
    message_ids = []

    for text in ("Привет!", "Это", "Ami Connect"):
        msg = await utils.safe_send(bot, chat_id, text)

        if msg:
            message_ids.append(msg.message_id)

        await asyncio.sleep(0.7)

    await asyncio.sleep(2.0)

    for message_id in message_ids:
        await utils.safe_delete(bot, chat_id, message_id)

    await asyncio.sleep(1.0)


async def start_first_user(bot, chat_id: int, user_id: int, state: FSMContext):
    await state.set_state(states.UserStates.greeting)
    security.set_silent(user_id, 8.0)

    await intro_sequence(bot, chat_id)

    await utils.safe_send(
        bot,
        chat_id,
        "Пиши что тебе нужно и тебе ответят в ближайшее время!",
    )

    await database.mark_greeted(user_id)
    await state.clear()


async def start_returning_user(bot, chat_id: int, tg_user, state: FSMContext):
    await state.set_state(states.UserStates.greeting)
    security.set_silent(tg_user.id, 5.0)

    name = utils.esc(utils.nickname_for_mention(tg_user))

    msg = await utils.safe_send(
        bot,
        chat_id,
        f"С возвращением, {name}!",
    )

    await asyncio.sleep(2.0)

    if msg:
        await utils.safe_delete(bot, chat_id, msg.message_id)

    await utils.safe_send(
        bot,
        chat_id,
        "Пиши что тебе нужно и тебе ответят в ближайшее время!",
    )

    await state.clear()


async def start_first_admin(bot, chat_id: int, user_id: int, state: FSMContext):
    await state.set_state(states.UserStates.greeting)
    security.set_silent(user_id, 7.0)

    await intro_sequence(bot, chat_id)

    await utils.safe_send(bot, chat_id, "Как вас зовут?")
    await state.set_state(states.AdminStates.name)


async def send_admin_panel(bot, chat_id: int, nickname: str | None, level: int):
    text = "Админ-панель"

    if nickname:
        text = f"Админ-панель, {utils.esc(nickname)}"

    await bot.send_message(
        chat_id,
        text,
        reply_markup=keyboards.admin_panel_kb(level),
    )


async def process_admin_name(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Пожалуйста, отправьте ваш ник текстом.",
        )
        return

    nickname = message.text.strip()[:32]
    user_id = message.from_user.id

    await database.set_admin_nickname(user_id, nickname)
    await state.set_state(states.AdminStates.loading)

    msg = await utils.safe_send(
        message.bot,
        message.chat.id,
        f"Для вас уже все подготовлено {utils.esc(nickname)}!",
    )

    await asyncio.sleep(2.0)

    if msg:
        await utils.safe_edit(
            message.bot,
            message.chat.id,
            msg.message_id,
            "⏳ Загрузка... 0%",
        )

        for i in range(1, 6):
            await asyncio.sleep(1.0)

            filled = i * 2
            bar = "█" * filled + "░" * (10 - filled)

            await utils.safe_edit(
                message.bot,
                message.chat.id,
                msg.message_id,
                f"⏳ Загрузка... {i * 20}%\n{bar}",
            )

        await utils.safe_edit(
            message.bot,
            message.chat.id,
            msg.message_id,
            "✅ Готово",
        )

    await state.clear()

    level = await database.get_admin_level(user_id)
    await send_admin_panel(message.bot, message.chat.id, nickname, level)


async def process_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("reply_target")

    await state.clear()

    if not target:
        return

    try:
        await message.copy_to(chat_id=target)
        await utils.safe_send(message.bot, message.chat.id, "✅ Отправлено пользователю")
    except Exception:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "❌ Не удалось отправить. Пользователь мог заблокировать бота.",
        )


async def process_unblock_input(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().lstrip("-").isdigit():
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Отправьте числовой ID пользователя.",
        )
        return

    target = int(message.text.strip())
    await state.clear()

    ok = await database.unblock_user(target)

    if ok:
        await utils.safe_send(message.bot, target, "✅ Вы были разблокированы")
        await utils.safe_send(message.bot, message.chat.id, "✅ Пользователь разблокирован")
    else:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Пользователь не найден или не заблокирован.",
        )


async def process_unmute_input(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().lstrip("-").isdigit():
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Отправьте числовой ID пользователя.",
        )
        return

    target = int(message.text.strip())
    await state.clear()

    ok = await database.unmute_user(target)

    if ok:
        await utils.safe_send(message.bot, target, "✅ Мут снят")
        await utils.safe_send(message.bot, message.chat.id, "✅ Мут снят")
    else:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Пользователь не найден или не замучен.",
        )


async def apply_mute(bot, target: int, hours: float):
    until = utils.now_utc() + timedelta(hours=hours)

    await database.mute_user(target, until)

    await utils.safe_send(
        bot,
        target,
        f"🔇 Вам выдан мут на {utils.fmt_hours(hours)} ч.",
    )


async def process_mute_custom(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("mute_target")

    if not target:
        await state.clear()
        return

    try:
        hours = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Введите количество часов числом.",
        )
        return

    if hours <= 0 or hours > 720:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Допустимый диапазон: от 0 до 720 часов.",
        )
        return

    await state.clear()
    await apply_mute(message.bot, target, hours)

    await utils.safe_send(
        message.bot,
        message.chat.id,
        f"✅ Пользователь замучен на {utils.fmt_hours(hours)} ч.",
    )


async def deliver_to_admins(bot, message: Message, tg_user):
    admin_ids = await database.get_admin_ids()

    if not admin_ids:
        return

    header = (
        "📩 Новое сообщение\n"
        f"От: {utils.esc(utils.header_from(tg_user))}\n"
        f"ID: {tg_user.id}"
    )

    kb = keyboards.message_admin_kb(tg_user.id)
    ct = utils.content_type_str(message)

    for admin_id in admin_ids:
        try:
            if ct == "text" and message.text:
                text = message.text

                if len(text) <= 3500:
                    full = f"{header}\n\n{utils.esc(text)}"

                    if len(full) > 4096:
                        full = full[:4090] + "..."

                    await bot.send_message(admin_id, full, reply_markup=kb)
                else:
                    await bot.send_message(
                        admin_id,
                        f"{header}\n\n[длинное сообщение, оригинал ниже]",
                        reply_markup=kb,
                    )
                    await message.copy_to(chat_id=admin_id)
            else:
                preview = utils.media_preview(message)

                await bot.send_message(
                    admin_id,
                    f"{header}\n\n{preview}",
                    reply_markup=kb,
                )

                await message.copy_to(chat_id=admin_id)

        except Exception:
            logging.exception("deliver_to_admins error")


async def build_debug_text(bot) -> str:
    tg_ok = False
    tg_ping = None

    try:
        started = time.perf_counter()
        await bot.get_my_commands()
        tg_ping = int((time.perf_counter() - started) * 1000)
        tg_ok = True
    except Exception:
        pass

    db_ping = await database.ping()
    db_ok = db_ping is not None

    try:
        memory_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        memory_mb = 0.0

    try:
        cpu = await asyncio.to_thread(psutil.cpu_percent, interval=0.2)
    except Exception:
        cpu = 0.0

    try:
        load_avg = " ".join(f"{x:.2f}" for x in os.getloadavg())
    except Exception:
        load_avg = "n/a"

    uptime = str(timedelta(seconds=int(time.time() - config.BOT_START_TIME)))

    return "\n".join(
        [
            "⚙️ Отладка",
            "",
            f"Telegram API: {'✅ OK' if tg_ok else '❌ FAIL'} | пинг: {tg_ping if tg_ping is not None else '—'} ms",
            f"База данных: {'✅ OK' if db_ok else '❌ FAIL'} | пинг: {db_ping if db_ping is not None else '—'} ms",
            f"Аптайм бота: {uptime}",
            f"Серверное время: {utils.format_dt(utils.now_utc())}",
            f"Python: {platform.python_version()}",
            f"aiogram: {aiogram.__version__}",
            f"RAM процесса: {memory_mb:.1f} MB",
            f"CPU: {cpu:.1f}%",
            f"Load average: {load_avg}",
        ]
    )


async def send_admins_list(message: Message):
    rows = await database.list_admins()

    if not rows:
        await utils.safe_send(message.bot, message.chat.id, "Админы не найдены.")
        return

    lines = ["👑 Администраторы:"]

    for i, row in enumerate(rows, 1):
        role = "OWNER" if row["level"] >= 100 else "SUPPORT"
        nick = row["nickname"] or "—"

        lines.append(
            f"{i}. ID {row['user_id']} | {utils.esc(nick)} | {role} | добавлен {utils.format_dt(row['created_at'])}"
        )

    lines.append("")
    lines.append("Команды владельца:")
    lines.append("/create_admin_invite — создать одноразовый инвайт-код")
    lines.append("/add_admin ID — добавить админа по ID")
    lines.append("/remove_admin ID — удалить админа по ID")

    await utils.send_long_message(message.bot, message.chat.id, "\n".join(lines))


@cmd_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not message.from_user or message.chat.type != "private":
        return

    tg_user = message.from_user
    user_id = tg_user.id

    await database.upsert_user(tg_user)
    row = await database.get_fresh_user(user_id)

    if not row:
        return

    current_state = await state.get_state()

    if current_state == states.AdminStates.name.state:
        await utils.safe_send(message.bot, message.chat.id, "Как вас зовут?")
        return

    if current_state in (
        states.UserStates.greeting.state,
        states.AdminStates.loading.state,
    ):
        return

    if not row["captcha_solved"]:
        await send_captcha(message.bot, message.chat.id, state, user_id)
        return

    if row["blocked_until"] and row["blocked_until"] > utils.now_utc():
        return

    await state.clear()

    level = await database.get_admin_level(user_id)

    if level > 0:
        admin_row = await database.get_admin(user_id)

        if admin_row and admin_row["nickname"]:
            await send_admin_panel(message.bot, message.chat.id, admin_row["nickname"], level)
        else:
            await start_first_admin(message.bot, message.chat.id, user_id, state)
    else:
        if row["greeted"]:
            await start_returning_user(message.bot, message.chat.id, tg_user, state)
        else:
            await start_first_user(message.bot, message.chat.id, user_id, state)


@cmd_router.message(Command("panel"))
async def cmd_panel(message: Message, state: FSMContext):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level <= 0:
        return

    await state.clear()

    admin_row = await database.get_admin(message.from_user.id)

    if admin_row and admin_row["nickname"]:
        await send_admin_panel(message.bot, message.chat.id, admin_row["nickname"], level)
    else:
        await start_first_admin(message.bot, message.chat.id, message.from_user.id, state)


@cmd_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level <= 0:
        return

    await state.clear()
    await utils.safe_send(message.bot, message.chat.id, "Отменено.")


@cmd_router.message(Command("create_admin_invite"))
async def cmd_create_admin_invite(message: Message):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level < 100:
        await utils.safe_send(message.bot, message.chat.id, "Недостаточно прав.")
        return

    code = secrets.token_urlsafe(8)

    await database.create_invite(code, message.from_user.id, 50)

    await utils.safe_send(
        message.bot,
        message.chat.id,
        "✅ Одноразовый инвайт-код создан.\n"
        f"Код: {code}\n\n"
        f"Новый админ должен отправить:\n/activate_admin {code}",
    )


@cmd_router.message(Command("activate_admin"))
async def cmd_activate_admin(message: Message):
    if not message.from_user or message.chat.type != "private":
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Использование: /activate_admin код",
        )
        return

    code = parts[1].strip()
    user_id = message.from_user.id

    await database.upsert_user(message.from_user)
    row = await database.get_fresh_user(user_id)

    if not row or not row["captcha_solved"]:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Сначала пройдите /start и решите капчу.",
        )
        return

    if await database.get_admin_level(user_id) > 0:
        await utils.safe_send(message.bot, message.chat.id, "Вы уже администратор.")
        return

    ok = await database.activate_invite(code, user_id)

    if ok:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "✅ Вы добавлены администратором поддержки.\nНажмите /start",
        )

        if config.OWNER_ID:
            await utils.safe_send(
                message.bot,
                config.OWNER_ID,
                f"Администратор {user_id} активировал приглашение.",
            )
    else:
        await utils.safe_send(message.bot, message.chat.id, "Код недействителен.")


@cmd_router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level < 100:
        await utils.safe_send(message.bot, message.chat.id, "Недостаточно прав.")
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await utils.safe_send(message.bot, message.chat.id, "Использование: /add_admin ID")
        return

    try:
        target = int(parts[1].strip())
    except ValueError:
        await utils.safe_send(message.bot, message.chat.id, "ID должен быть числом.")
        return

    if config.OWNER_ID and target == config.OWNER_ID:
        await utils.safe_send(
            message.bot,
            message.chat.id,
            "Этот пользователь уже главный админ.",
        )
        return

    if await database.get_admin_level(target) > 0:
        await utils.safe_send(message.bot, message.chat.id, "Пользователь уже администратор.")
        return

    await database.add_admin(target, message.from_user.id)

    await utils.safe_send(message.bot, message.chat.id, f"Администратор {target} добавлен.")
    await utils.safe_send(
        message.bot,
        target,
        "Вы добавлены администратором поддержки.\nНажмите /start",
    )


@cmd_router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level < 100:
        await utils.safe_send(message.bot, message.chat.id, "Недостаточно прав.")
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await utils.safe_send(message.bot, message.chat.id, "Использование: /remove_admin ID")
        return

    try:
        target = int(parts[1].strip())
    except ValueError:
        await utils.safe_send(message.bot, message.chat.id, "ID должен быть числом.")
        return

    if config.OWNER_ID and target == config.OWNER_ID:
        await utils.safe_send(message.bot, message.chat.id, "Нельзя удалить главного админа.")
        return

    if await database.get_admin_level(target) == 0:
        await utils.safe_send(message.bot, message.chat.id, "Пользователь не администратор.")
        return

    ok = await database.remove_admin(target)

    if ok:
        await utils.safe_send(message.bot, message.chat.id, f"Администратор {target} удалён.")
        await utils.safe_send(message.bot, target, "Ваш доступ администратора отозван.")
    else:
        await utils.safe_send(message.bot, message.chat.id, "Не удалось удалить администратора.")


@cmd_router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not message.from_user or message.chat.type != "private":
        return

    level = await database.get_admin_level(message.from_user.id)

    if level < 100:
        await utils.safe_send(message.bot, message.chat.id, "Недостаточно прав.")
        return

    await send_admins_list(message)


@cmd_router.message(F.text == "📋 Заблокированные")
async def panel_blocked(message: Message):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    rows = await database.get_blocked_list(100)

    if not rows:
        await utils.safe_send(message.bot, message.chat.id, "Заблокированных пользователей нет.")
        return

    lines = ["📋 Заблокированные (до 100):"]

    for i, row in enumerate(rows, 1):
        reason = row["blocked_reason"] or "-"
        lines.append(
            f"{i}. ID {row['user_id']} | {reason} | до {utils.format_dt(row['blocked_until'])}"
        )

    if len(rows) == 100:
        lines.append("... и другие")

    await utils.send_long_message(message.bot, message.chat.id, "\n".join(lines))


@cmd_router.message(F.text == "🔇 Замученные")
async def panel_muted(message: Message):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    rows = await database.get_muted_list(100)

    if not rows:
        await utils.safe_send(message.bot, message.chat.id, "Замученных пользователей нет.")
        return

    lines = ["🔇 Замученные (до 100):"]
    now = utils.now_utc()

    for i, row in enumerate(rows, 1):
        remaining = row["muted_until"] - now if row["muted_until"] else timedelta(0)
        lines.append(
            f"{i}. ID {row['user_id']} | осталось {utils.format_timedelta(remaining)}"
        )

    if len(rows) == 100:
        lines.append("... и другие")

    await utils.send_long_message(message.bot, message.chat.id, "\n".join(lines))


@cmd_router.message(F.text == "✅ Разблокировать по ID")
async def panel_unblock_ask(message: Message, state: FSMContext):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    await state.set_state(states.AdminStates.wait_unblock)

    await utils.safe_send(
        message.bot,
        message.chat.id,
        "Отправьте ID пользователя для разблокировки.\n/cancel — отмена.",
    )


@cmd_router.message(F.text == "🔊 Размутить по ID")
async def panel_unmute_ask(message: Message, state: FSMContext):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    await state.set_state(states.AdminStates.wait_unmute)

    await utils.safe_send(
        message.bot,
        message.chat.id,
        "Отправьте ID пользователя для снятия мута.\n/cancel — отмена.",
    )


@cmd_router.message(F.text == "📊 Статистика")
async def panel_stats(message: Message):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    row = await database.get_common_stats()

    text = "\n".join(
        [
            "📊 Статистика",
            "",
            f"Всего пользователей: {row['total_users']}",
            f"Пользователей без флудер-статуса: {row['clean_users']}",
            f"Сообщений от не-флудеров: {row['clean_messages']}",
            f"Заблокировано сейчас: {row['blocked_count']}",
            f"Замучено сейчас: {row['muted_count']}",
            f"Админов: {row['admins_count']}",
        ]
    )

    await utils.safe_send(message.bot, message.chat.id, text)


@cmd_router.message(F.text == "⚙️ Отладка")
async def panel_debug(message: Message):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    text = await build_debug_text(message.bot)
    await utils.safe_send(message.bot, message.chat.id, text)


@cmd_router.message(F.text == "☣️ Статистика флуда")
async def panel_flood_stats(message: Message):
    level = await get_admin_level_for_message(message)

    if level <= 0:
        return

    row = await database.get_flood_stats()
    top_rows = await database.get_top_flooders(5)

    lines = [
        "☣️ Статистика флуда",
        "",
        f"Пользователей с флуд-активностью: {row['flood_users']}",
        f"Флуд-сообщений зафиксировано: {row['flood_messages']}",
        f"Всего сообщений от этих пользователей: {row['total_all']}",
    ]

    if top_rows:
        lines.append("")
        lines.append("Топ по флуду:")

        for i, top in enumerate(top_rows, 1):
            total = top["total_messages"] + top["flood_messages"]
            lines.append(
                f"{i}. ID {top['user_id']} | флуд: {top['flood_messages']} | всего: {total}"
            )

    await utils.send_long_message(message.bot, message.chat.id, "\n".join(lines))


@cmd_router.message(F.text == "👑 Админы")
async def panel_admins(message: Message):
    level = await get_admin_level_for_message(message)

    if level < 100:
        return

    await send_admins_list(message)


@callback_router.callback_query(F.data.startswith("cap:"))
async def cb_captcha(cb: CallbackQuery, state: FSMContext):
    logging.info(
        "CAPTCHA CALLBACK: data=%s user=%s",
        cb.data,
        cb.from_user.id if cb.from_user else None,
    )

    if not cb.from_user:
        return

    try:
        await cb.answer()
    except Exception:
        pass

    user_id = cb.from_user.id

    await database.upsert_user(cb.from_user)

    data = await state.get_data()
    correct = data.get("correct")

    chat_id = cb.message.chat.id if cb.message else user_id

    if not correct or not cb.data:
        await utils.safe_send(
            cb.bot,
            chat_id,
            "Капча устарела. Нажмите /start, чтобы получить новую.",
        )
        return

    slug = cb.data.split(":", 1)[1]

    if slug == correct:
        await database.solve_captcha(user_id)
        await state.clear()

        if cb.message:
            try:
                await cb.message.edit_text("✅ Капча решена!")
            except Exception:
                pass

        await after_captcha(cb.bot, chat_id, cb.from_user, state)
        return

    fails = int(data.get("fails", 0)) + 1

    if fails >= 3:
        lock_until = utils.now_utc() + timedelta(minutes=10)
        await database.lock_captcha(user_id, lock_until)
        await state.clear()

        if cb.message:
            try:
                await cb.message.edit_text(
                    "❌ Неверно. Слишком много попыток. Попробуйте через 10 минут."
                )
            except Exception:
                pass

        return

    await state.update_data(fails=fails)

    if cb.message:
        try:
            await cb.message.edit_text("❌ Неверно. Новая капча ниже.")
        except Exception:
            pass

    await send_captcha(cb.bot, chat_id, state, user_id, fails=fails)


@callback_router.callback_query(F.data.startswith("blk:"))
async def cb_block(cb: CallbackQuery):
    level = await get_admin_level_for_callback(cb)

    if level <= 0:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        target = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных", show_alert=True)
        return

    until = utils.now_utc() + timedelta(days=3650)

    await database.block_user(target, until, "manual", False)
    await utils.safe_send(cb.bot, target, "⛔ Вы заблокированы")

    chat_id = cb.message.chat.id if cb.message else cb.from_user.id

    if cb.message:
        try:
            await cb.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
            )
        except Exception:
            pass

        await utils.safe_send(cb.bot, chat_id, "✅ Пользователь заблокирован")

    await cb.answer("Пользователь заблокирован")


@callback_router.callback_query(F.data.startswith("mut:"))
async def cb_mute(cb: CallbackQuery):
    level = await get_admin_level_for_callback(cb)

    if level <= 0:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        target = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных", show_alert=True)
        return

    chat_id = cb.message.chat.id if cb.message else cb.from_user.id

    await utils.safe_send(
        cb.bot,
        chat_id,
        f"Выберите длительность мута для пользователя {target}:",
        reply_markup=keyboards.mute_options_kb(target),
    )

    await cb.answer()


@callback_router.callback_query(F.data.startswith("mset:"))
async def cb_mute_set(cb: CallbackQuery, state: FSMContext):
    level = await get_admin_level_for_callback(cb)

    if level <= 0:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        _, target_raw, hours_raw = cb.data.split(":", 2)
        target = int(target_raw)
    except Exception:
        await cb.answer("Ошибка данных", show_alert=True)
        return

    chat_id = cb.message.chat.id if cb.message else cb.from_user.id

    if hours_raw == "custom":
        await state.set_state(states.AdminStates.wait_mute_custom)
        await state.update_data(mute_target=target)

        await utils.safe_send(
            cb.bot,
            chat_id,
            "Введите количество часов для мута числом.\nПример: 12",
        )

        await cb.answer()
        return

    try:
        hours = float(hours_raw)
    except ValueError:
        await cb.answer("Некорректное число часов", show_alert=True)
        return

    if hours <= 0 or hours > 720:
        await cb.answer("Допустимый диапазон: от 0 до 720 часов", show_alert=True)
        return

    await apply_mute(cb.bot, target, hours)

    await utils.safe_send(
        cb.bot,
        chat_id,
        f"✅ Пользователь замучен на {utils.fmt_hours(hours)} ч.",
    )

    await cb.answer("Мут выдан")


@callback_router.callback_query(F.data.startswith("ans:"))
async def cb_answer(cb: CallbackQuery, state: FSMContext):
    level = await get_admin_level_for_callback(cb)

    if level <= 0:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        target = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных", show_alert=True)
        return

    await state.set_state(states.AdminStates.wait_reply)
    await state.update_data(reply_target=target)

    chat_id = cb.message.chat.id if cb.message else cb.from_user.id

    await utils.safe_send(
        cb.bot,
        chat_id,
        "Отправьте сообщение, фото, видео, голосовое, кружок или стикер "
        "для пользователя. /cancel — отмена.",
    )

    await cb.answer()


@callback_router.callback_query(F.data.startswith("his:"))
async def cb_history(cb: CallbackQuery):
    level = await get_admin_level_for_callback(cb)

    if level <= 0:
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        target = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных", show_alert=True)
        return

    rows = await database.get_last_messages(target, 15)

    chat_id = cb.message.chat.id if cb.message else cb.from_user.id

    if not rows:
        await utils.safe_send(cb.bot, chat_id, "История сообщений пуста.")
        await cb.answer()
        return

    lines = [f"📜 Последние 15 сообщений пользователя {target}:"]

    for i, row in enumerate(rows, 1):
        ct = config.CONTENT_TITLES.get(row["content_type"], row["content_type"])
        text = row["text"] or ""

        lines.append(
            f"{i}. {utils.format_dt(row['created_at'])} | {ct} | {utils.esc(text[:120])}"
        )

    await utils.send_long_message(cb.bot, chat_id, "\n".join(lines))
    await cb.answer()


@callback_router.callback_query()
async def cb_debug_unknown_callback(cb: CallbackQuery):
    logging.info(
        "UNHANDLED CALLBACK: data=%s user=%s",
        cb.data,
        cb.from_user.id if cb.from_user else None,
    )

    try:
        await cb.answer("Кнопка устарела. Нажмите /start", show_alert=True)
    except Exception:
        pass


@message_router.message(F.chat.type == "private")
async def handle_messages(message: Message, state: FSMContext):
    if not message.from_user:
        return

    if message.text and message.text.startswith("/"):
        return

    tg_user = message.from_user
    user_id = tg_user.id

    await database.upsert_user(tg_user)
    row = await database.get_fresh_user(user_id)

    if not row:
        return

    now = utils.now_utc()

    if row["blocked_until"] and row["blocked_until"] > now:
        if row["blocked_reason"] == "antiflood":
            await database.increment_flood_message(user_id)
        return

    level = await database.get_admin_level(user_id)

    if not row["captcha_solved"]:
        if row["captcha_locked_until"] and row["captcha_locked_until"] > now:
            return

        if level <= 0 and security.antiflood_check(user_id):
            await security.handle_antiflood_trigger(message.bot, message.chat.id, user_id)
            return

        current_state = await state.get_state()

        if current_state != states.CaptchaStates.captcha.state:
            await send_captcha(message.bot, message.chat.id, state, user_id)

        return

    if level > 0:
        current_state = await state.get_state()

        if current_state == states.AdminStates.name.state:
            await process_admin_name(message, state)
            return

        if current_state == states.AdminStates.wait_unblock.state:
            await process_unblock_input(message, state)
            return

        if current_state == states.AdminStates.wait_unmute.state:
            await process_unmute_input(message, state)
            return

        if current_state == states.AdminStates.wait_mute_custom.state:
            await process_mute_custom(message, state)
            return

        if current_state == states.AdminStates.wait_reply.state:
            await process_admin_reply(message, state)
            return

        if current_state in (
            states.UserStates.greeting.state,
            states.AdminStates.loading.state,
        ):
            return

        if security.is_silent(user_id):
            return

        return

    current_state = await state.get_state()

    if current_state == states.UserStates.greeting.state:
        return

    if security.is_silent(user_id):
        return

    if row["captcha_locked_until"] and row["captcha_locked_until"] > now:
        return

    if row["muted_until"] and row["muted_until"] > now:
        return

    if security.antiflood_check(user_id):
        await security.handle_antiflood_trigger(message.bot, message.chat.id, user_id)
        return

    ct = utils.content_type_str(message)
    text = utils.extract_text(message)

    await database.increment_total_message(user_id)
    await database.add_message(user_id, ct, text[:4000])

    await deliver_to_admins(message.bot, message, tg_user)
