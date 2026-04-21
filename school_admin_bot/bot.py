import asyncio
import logging

from aiogram import Bot, Dispatcher
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import BOT_TOKEN
from handlers import router
from shared.database import init_db
from shared.logging_setup import get_log_settings, setup_logging


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def main():
    log_level, log_dir = get_log_settings()
    log_file = setup_logging("school_admin_bot", log_level=log_level, log_dir=log_dir)
    logging.getLogger(__name__).info("Starting admin bot, log file: %s", log_file)
    init_db()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
