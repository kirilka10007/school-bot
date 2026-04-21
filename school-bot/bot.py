import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import BOT_TOKEN
from handlers import routers
from shared.database import init_db
from shared.logging_setup import get_log_settings, setup_logging


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

for router in routers:
    dp.include_router(router)


async def main():
    log_level, log_dir = get_log_settings()
    log_file = setup_logging("school_bot", log_level=log_level, log_dir=log_dir)
    logging.getLogger(__name__).info("Starting school bot, log file: %s", log_file)
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
