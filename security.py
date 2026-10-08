import time
from collections import deque
from datetime import timedelta

import database
import utils


user_flood_windows = {}
silent_until = {}
flood_triggers = deque()
last_flood_alert = 0.0


def set_silent(user_id: int, seconds: float):
    silent_until[user_id] = time.monotonic() + seconds


def is_silent(user_id: int) -> bool:
    return silent_until.get(user_id, 0) > time.monotonic()


def antiflood_check(user_id: int) -> bool:
    now = time.monotonic()
    window = user_flood_windows.setdefault(user_id, deque())

    while window and now - window[0] > 5.0:
        window.popleft()

    window.append(now)

    if len(window) >= 10:
        window.clear()
        return True

    return False


async def handle_antiflood_trigger(bot, chat_id: int, user_id: int):
    until = utils.now_utc() + timedelta(days=1)

    await database.apply_antiflood_block(user_id, until)
    await utils.safe_send(
        bot,
        chat_id,
        "⚠️ Подозрительная активность, блокирую на 1 день",
    )

    await register_flood_trigger(bot)


async def register_flood_trigger(bot):
    global last_flood_alert

    now = time.time()
    flood_triggers.append(now)

    while flood_triggers and now - flood_triggers[0] > 60:
        flood_triggers.popleft()

    if len(flood_triggers) >= 3 and now - last_flood_alert > 60:
        last_flood_alert = now

        admin_ids = await database.get_admin_ids()

        for admin_id in admin_ids:
            await utils.safe_send(
                bot,
                admin_id,
                "⚠️ Повышенная нагрузка флудом",
            )