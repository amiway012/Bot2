import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database
from handlers import callback_router, cmd_router, message_router


async def health(request):
    return web.Response(text="ok")


async def main():
    if not config.BOT_TOKEN:
        logging.critical("BOT_TOKEN не задан. Добавьте переменную окружения.")
        return

    if not config.DATABASE_URL:
        logging.critical("DATABASE_URL не задан. Добавьте PostgreSQL в Railway.")
        return

    if not config.OWNER_ID:
        logging.critical("OWNER_ID не задан или некорректен. Добавьте ID главного админа.")
        return

    await database.init_db()
    await database.ensure_owner()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_routers(cmd_router, callback_router, message_router)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()

    logging.info("Health server started on port %s", config.PORT)

    me = await bot.get_me()
    logging.info("Bot @%s started", me.username)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped")