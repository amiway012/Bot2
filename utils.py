import html
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramAPIError

import config


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_timedelta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total < 0:
        total = 0

    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60

    if days:
        return f"{days}д {hours}ч {minutes}м"
    if hours:
        return f"{hours}ч {minutes}м"
    if minutes:
        return f"{minutes}м {seconds}с"
    return f"{seconds}с"


def format_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def fmt_hours(hours: float):
    if float(hours).is_integer():
        return int(hours)
    return round(hours, 2)


def full_name(tg_user) -> str:
    return " ".join(filter(None, [tg_user.first_name, tg_user.last_name])).strip()


def header_from(tg_user) -> str:
    name = full_name(tg_user)

    if tg_user.username:
        if name:
            return f"{name} (@{tg_user.username})"
        return f"@{tg_user.username}"

    return name or str(tg_user.id)


def nickname_for_mention(tg_user) -> str:
    if tg_user.username:
        return f"@{tg_user.username}"

    return tg_user.first_name or tg_user.last_name or "пользователь"


async def safe_send(message_bot, chat_id: int, text: str, **kwargs):
    try:
        return await message_bot.send_message(chat_id, text, **kwargs)
    except TelegramAPIError as e:
        print(f"safe_send failed for {chat_id}: {e}")
    except Exception:
        print("safe_send error")


async def safe_delete(message_bot, chat_id: int, message_id: int):
    try:
        await message_bot.delete_message(chat_id, message_id)
    except TelegramAPIError:
        pass
    except Exception:
        print("safe_delete error")


async def safe_edit(message_bot, chat_id: int, message_id: int, text: str):
    try:
        await message_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
        )
    except TelegramAPIError:
        pass
    except Exception:
        print("safe_edit error")


async def send_long_message(message_bot, chat_id: int, text: str):
    if len(text) <= 4000:
        await safe_send(message_bot, chat_id, text)
        return

    parts = []

    while len(text) > 4000:
        cut = text.rfind("\n", 0, 4000)
        if cut < 3500:
            cut = 4000

        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")

    if text:
        parts.append(text)

    for part in parts:
        await safe_send(message_bot, chat_id, part)


def content_type_str(message) -> str:
    ct = message.content_type

    if hasattr(ct, "value"):
        ct = ct.value

    return str(ct)


def extract_text(message) -> str:
    if message.text:
        return message.text

    if message.caption:
        return message.caption

    if message.sticker and message.sticker.emoji:
        return message.sticker.emoji

    return ""


def media_preview(message) -> str:
    ct = content_type_str(message)
    title = config.CONTENT_TITLES.get(ct, ct)
    extra = ""

    if ct == "sticker" and message.sticker and message.sticker.emoji:
        extra = f" {message.sticker.emoji}"

    if message.caption:
        extra += f"\nПодпись: {esc(message.caption[:200])}"

    return f"[{title}{extra}]"