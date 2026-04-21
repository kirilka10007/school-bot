import asyncio
import logging

from aiogram import Bot, Dispatcher
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import BOT_TOKEN
from config import SUPERADMINS
from handlers import router
from shared.database import init_db, run_startup_maintenance_from_env
from shared.logging_setup import get_log_settings, setup_logging


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def main():
    log_level, log_dir = get_log_settings()
    log_file = setup_logging("school_admin_bot", log_level=log_level, log_dir=log_dir)
    logging.getLogger(__name__).info("Starting admin bot, log file: %s", log_file)
    init_db()
    maintenance_executed = run_startup_maintenance_from_env(preserve_superadmin_ids=SUPERADMINS)
    if maintenance_executed:
        logging.getLogger(__name__).info("Startup maintenance completed: student data reset for testing.")
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
