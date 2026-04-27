import asyncio
import contextlib
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config import ADMIN_ID, BOT_TOKEN
from handlers import routers
from shared.database import (
    get_debt_rows_for_reminder,
    init_db,
    mark_debt_reminder_sent,
    run_startup_maintenance_from_env,
)
from shared.logging_setup import get_log_settings, setup_logging


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
try:
    MSK_TZ = ZoneInfo("Europe/Moscow")
except Exception:
    MSK_TZ = timezone(timedelta(hours=3))

for router in routers:
    dp.include_router(router)


async def debt_reminder_worker(bot: Bot):
    logger = logging.getLogger(__name__)
    reminder_weekday_raw = os.getenv("SCHOOL_DEBT_REMINDER_WEEKDAY", "0").strip()
    reminder_hour_raw = os.getenv("SCHOOL_DEBT_REMINDER_HOUR", "10").strip()
    try:
        reminder_weekday = min(6, max(0, int(reminder_weekday_raw)))
    except ValueError:
        reminder_weekday = 0
    try:
        reminder_hour = min(23, max(0, int(reminder_hour_raw)))
    except ValueError:
        reminder_hour = 10

    while True:
        try:
            now = datetime.now(MSK_TZ)
            iso_year, iso_week, _ = now.isocalendar()
            reminder_key = f"{iso_year}-W{iso_week:02d}"
            schedule_reached = (
                now.weekday() > reminder_weekday
                or (now.weekday() == reminder_weekday and now.hour >= reminder_hour)
            )
            if not schedule_reached:
                await asyncio.sleep(3600)
                continue

            rows = get_debt_rows_for_reminder(reminder_key)
            grouped = defaultdict(list)

            for row in rows:
                student_lesson_id, telegram_id, student_name, teacher_name, subject_name, lesson_balance = row
                grouped[telegram_id].append(
                    (
                        student_lesson_id,
                        student_name,
                        teacher_name,
                        subject_name,
                        lesson_balance,
                    )
                )

            for telegram_id, debts in grouped.items():
                student_name = debts[0][1]
                lines = [
                    "❗❗❗🔴 ВНИМАНИЕ! У ВАС ЗАДОЛЖЕННОСТЬ! 🔴❗❗❗",
                    "",
                    f"Ученик: {student_name}",
                    "",
                    "Направления с задолженностью:",
                ]
                for _, _, teacher_name, subject_name, lesson_balance in debts:
                    lines.append(
                        f"- {subject_name} — {teacher_name}: задолженность {abs(lesson_balance)} занят."
                    )
                lines.append("")
                lines.append("❗❗❗ Пожалуйста, внесите оплату или свяжитесь с администратором школы. ❗❗❗")

                try:
                    await bot.send_message(telegram_id, "\n".join(lines))
                except Exception as exc:
                    logger.warning("Debt reminder send failed for %s: %s", telegram_id, exc)
                    continue

                for student_lesson_id, *_ in debts:
                    mark_debt_reminder_sent(student_lesson_id, reminder_key)
        except Exception as exc:
            logger.exception("Debt reminder worker error: %s", exc)

        await asyncio.sleep(3600)


async def main():
    log_level, log_dir = get_log_settings()
    log_file = setup_logging("school_bot", log_level=log_level, log_dir=log_dir)
    logging.getLogger(__name__).info("Starting school bot, log file: %s", log_file)
    init_db()
    maintenance_executed = run_startup_maintenance_from_env(preserve_superadmin_ids=[ADMIN_ID])
    if maintenance_executed:
        logging.getLogger(__name__).info("Startup maintenance completed: student data reset for testing.")
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Запустить бота"),
                BotCommand(command="menu", description="Открыть главное меню"),
            ]
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to set bot commands on startup (will continue): %s",
            exc,
        )
    reminder_task = asyncio.create_task(debt_reminder_worker(bot))
    try:
        while True:
            try:
                await dp.start_polling(bot)
                break
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "School polling crashed, retry in 5s: %s",
                    exc,
                )
                await asyncio.sleep(5)
    finally:
        reminder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminder_task


if __name__ == "__main__":
    asyncio.run(main())
