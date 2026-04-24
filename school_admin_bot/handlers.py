from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from config import SCHOOL_BOT_TOKEN, SCHOOL_BOT_USERNAME, SUPERADMINS
from keyboards import (
    get_superadmin_menu,
    get_superadmin_users_menu,
    get_superadmin_school_menu,
    get_superadmin_reports_menu,
    get_admin_menu,
    get_teacher_menu,
    get_student_menu,
    get_tariff_keyboard,
    get_attendance_direction_keyboard,
    get_attendance_mark_keyboard,
    get_teacher_attendance_students_keyboard,
    get_balance_direction_keyboard,
    get_balance_add_keyboard,
    get_teacher_bind_keyboard,
    get_role_change_keyboard,
    get_main_menu_shortcut_keyboard,
    get_user_selection_keyboard,
    get_teacher_selection_keyboard,
    get_teacher_subject_picker_keyboard,
    get_publication_audience_keyboard,
    get_publication_schedule_keyboard,
)
from states import AdminStates
from shared.database import (
    add_student,
    get_all_students,
    add_teacher_if_not_exists,
    add_student_lesson,
    find_students_by_name,
    get_student_directions,
    get_student_lesson_by_id,
    mark_attendance,
    add_lessons_to_balance,
    get_balance_history_by_student,
    add_user,
    get_user_by_telegram_id,
    get_users_by_role,
    search_users_by_name_or_username,
    get_user_by_id,
    get_student_by_id,
    get_student_by_telegram_id,
    bind_teacher_telegram_id,
    log_admin_action,
    get_recent_admin_actions,
    get_recent_payment_history_by_telegram_user,
    build_daily_debt_report,
    get_students_by_teacher_telegram_id,
    get_teacher_by_telegram_id,
    get_teacher_by_id,
    search_teacher_profiles,
    list_teacher_profiles,
    get_teacher_profile_by_id,
    get_teacher_catalog_subjects,
    update_teacher_profile_fields,
    set_teacher_telegram_id,
    update_user_role,
    set_user_active,
    delete_admin_by_telegram_id,
    delete_teacher_by_telegram_id,
    delete_student_by_telegram_id,
    add_or_update_teacher_profile,
    get_active_admin_contacts,
    get_known_telegram_user_id_by_username,
    create_onboarding_invite,
    normalize_telegram_username,
    get_latest_pending_invite_by_role_and_username,
    mark_onboarding_invite_used,
    upsert_known_telegram_user,
    create_publication_post,
)

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEACHER_UPLOADS_DIR = PROJECT_ROOT / "school-bot" / "assets" / "teachers_uploaded"


async def update_flow_message(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def save_teacher_photo(message: Message) -> str:
    """Save uploaded teacher photo locally so it can be shown by the school bot."""
    file_info = await message.bot.get_file(message.photo[-1].file_id)
    file_ext = Path(file_info.file_path or "").suffix or ".jpg"
    unique_id = message.photo[-1].file_unique_id or uuid4().hex
    filename = f"teacher_{unique_id}{file_ext}"

    TEACHER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destination = TEACHER_UPLOADS_DIR / filename
    await message.bot.download_file(file_info.file_path, destination=destination)

    return f"assets/teachers_uploaded/{filename}".replace("\\", "/")


async def send_student_notification(
    callback: CallbackQuery,
    student_telegram_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not student_telegram_id:
        return

    if SCHOOL_BOT_TOKEN:
        try:
            async with Bot(token=SCHOOL_BOT_TOKEN) as school_bot:
                await school_bot.send_message(
                    student_telegram_id,
                    text,
                    reply_markup=reply_markup,
                )
            return
        except Exception as exc:
            logger.warning(
                "Failed to send via school bot token to user %s: %s",
                student_telegram_id,
                exc,
            )

    try:
        await callback.bot.send_message(
            student_telegram_id,
            text,
            reply_markup=reply_markup,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send via admin bot token to user %s: %s",
            student_telegram_id,
            exc,
        )


def build_payment_prompt_keyboard() -> InlineKeyboardMarkup | None:
    if not SCHOOL_BOT_USERNAME:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перейти к оплате",
                    url=f"https://t.me/{SCHOOL_BOT_USERNAME}?start=pay",
                )
            ]
        ]
    )


async def notify_student_about_attendance(
    callback: CallbackQuery,
    *,
    student_telegram_id: int | None,
    student_name: str,
    subject_name: str,
    teacher_name: str,
    tariff_type: str,
    status: str,
    lesson_balance_before: int,
    lesson_balance_after: int,
) -> None:
    if not student_telegram_id:
        return

    if status != "present":
        text = (
            "Здравствуйте!\n\n"
            "По Вашему направлению обновлена отметка посещаемости.\n\n"
            f"Ученик: {student_name}\n"
            f"Предмет: {subject_name}\n"
            f"Преподаватель: {teacher_name}\n"
            "Статус занятия: не был"
        )
        await send_student_notification(callback, student_telegram_id, text)
        return

    lines = [
        "Здравствуйте!",
        "",
        "Занятие отмечено как проведённое.",
        "",
        f"Ученик: {student_name}",
        f"Предмет: {subject_name}",
        f"Преподаватель: {teacher_name}",
        "Списано занятий: 1",
        f"Баланс был: {lesson_balance_before}",
        f"Баланс стал: {lesson_balance_after}",
    ]

    need_payment_prompt = tariff_type == "single" or lesson_balance_after < 0
    reply_markup = None

    if lesson_balance_after < 0:
        lines.extend(
            [
                "",
                f"Внимание: по данному направлению образовалась задолженность {abs(lesson_balance_after)} занят.",
            ]
        )
        reply_markup = build_payment_prompt_keyboard()
    elif lesson_balance_after == 0:
        lines.extend(
            [
                "",
                "На балансе больше не осталось оплаченных занятий.",
            ]
        )

    if tariff_type == "single":
        lines.extend(
            [
                "",
                "У Вас разовый тариф. Пожалуйста, направьте чек об оплате следующего занятия.",
            ]
        )
        if reply_markup is None:
            reply_markup = build_payment_prompt_keyboard()

    if reply_markup is None and need_payment_prompt:
        reply_markup = build_payment_prompt_keyboard()

    await send_student_notification(
        callback,
        student_telegram_id,
        "\n".join(lines),
        reply_markup=reply_markup,
    )


def build_payment_prompt_keyboard_clean() -> InlineKeyboardMarkup | None:
    if not SCHOOL_BOT_USERNAME:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перейти к оплате",
                    url=f"https://t.me/{SCHOOL_BOT_USERNAME}?start=pay",
                )
            ]
        ]
    )


async def notify_student_about_attendance_clean(
    callback: CallbackQuery,
    *,
    student_telegram_id: int | None,
    student_name: str,
    subject_name: str,
    teacher_name: str,
    tariff_type: str,
    status: str,
    lesson_balance_before: int,
    lesson_balance_after: int,
) -> None:
    if not student_telegram_id:
        return

    if status != "present":
        text = (
            "Здравствуйте!\n\n"
            "По Вашему направлению обновлена отметка посещаемости.\n\n"
            f"Ученик: {student_name}\n"
            f"Предмет: {subject_name}\n"
            f"Преподаватель: {teacher_name}\n"
            "Статус занятия: не был."
        )
        await send_student_notification(callback, student_telegram_id, text)
        return

    lines = [
        "Здравствуйте!",
        "",
        "Занятие отмечено как проведённое.",
        "",
        f"Ученик: {student_name}",
        f"Предмет: {subject_name}",
        f"Преподаватель: {teacher_name}",
        "Списано занятий: 1",
        f"Баланс был: {lesson_balance_before}",
        f"Баланс стал: {lesson_balance_after}",
    ]

    reply_markup = None
    if lesson_balance_after < 0:
        lines.extend(
            [
                "",
                "ВНИМАНИЕ! У ВАС ЗАДОЛЖЕННОСТЬ!",
                f"Размер задолженности: {abs(lesson_balance_after)} занят.",
            ]
        )
        reply_markup = build_payment_prompt_keyboard_clean()
    elif lesson_balance_after == 0:
        lines.extend(["", "На балансе больше не осталось оплаченных занятий."])

    if tariff_type == "single":
        lines.extend(
            [
                "",
                "У Вас разовый тариф. Пожалуйста, направьте чек об оплате следующего занятия.",
            ]
        )
        if reply_markup is None:
            reply_markup = build_payment_prompt_keyboard_clean()

    await send_student_notification(
        callback,
        student_telegram_id,
        "\n".join(lines),
        reply_markup=reply_markup,
    )


async def notify_teacher_about_attendance(
    callback: CallbackQuery,
    *,
    teacher_telegram_id: int | None,
    student_name: str,
    subject_name: str,
    status: str,
    lesson_balance_after: int,
) -> None:
    if not teacher_telegram_id:
        return

    status_text = "был" if status == "present" else "не был"
    text = (
        "Здравствуйте!\n\n"
        "По Вашему ученику обновлена посещаемость.\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Статус занятия: {status_text}\n"
        f"Текущий баланс ученика: {lesson_balance_after}"
    )
    try:
        await callback.bot.send_message(teacher_telegram_id, text)
    except Exception:
        pass


def get_role_by_user_id(user_id: int):
    user = get_user_by_telegram_id(user_id)
    if not user:
        return None

    _, telegram_id, full_name, role, is_active = user

    if not is_active:
        return None

    return role


def is_admin_role(user_id: int) -> bool:
    role = get_role_by_user_id(user_id)
    return role in ["superadmin", "admin"]


def is_teacher_role(user_id: int) -> bool:
    role = get_role_by_user_id(user_id)
    return role == "teacher"


def get_admin_reply_menu(user_id: int):
    return get_superadmin_menu() if user_id in SUPERADMINS else get_admin_menu()


def get_home_menu_by_user_id(user_id: int):
    role = get_role_by_user_id(user_id)
    if user_id in SUPERADMINS:
        return get_superadmin_menu()
    if role == "admin":
        return get_admin_menu()
    if role == "teacher":
        return get_teacher_menu()
    if role == "student":
        return get_student_menu()
    return None


def role_title(role: str) -> str:
    return {
        "superadmin": "Суперадмин",
        "admin": "Администратор",
        "teacher": "Преподаватель",
        "student": "Ученик",
    }.get(role, role)


def format_debt_report_text(report_data: dict, overdue_days: int) -> str:
    report_date = report_data.get("report_date", "-")
    total_current_debts = report_data.get("total_current_debts", 0)
    new_debts = report_data.get("new_debts", [])
    closed_debts = report_data.get("closed_debts", [])
    overdue_debts = report_data.get("overdue_debts", [])

    lines = [
        f"📊 <b>Отчёт по долгам за {report_date}</b>",
        "",
        f"Текущих долгов по направлениям: <b>{total_current_debts}</b>",
        f"Новые долги за день: <b>{len(new_debts)}</b>",
        f"Закрытые долги за день: <b>{len(closed_debts)}</b>",
        f"Долги старше {overdue_days} дн.: <b>{len(overdue_debts)}</b>",
    ]

    if new_debts:
        lines.append("")
        lines.append("<b>Новые долги:</b>")
        for item in new_debts[:20]:
            lines.append(
                f"- {item.get('student_name', '—')} | {item.get('subject_name', '—')} — "
                f"{item.get('teacher_name', '—')} | долг: {abs(item.get('lesson_balance', 0))}"
            )

    if closed_debts:
        lines.append("")
        lines.append("<b>Закрытые долги:</b>")
        for item in closed_debts[:20]:
            lines.append(
                f"- {item.get('student_name', '—')} | {item.get('subject_name', '—')} — "
                f"{item.get('teacher_name', '—')}"
            )

    if overdue_debts:
        lines.append("")
        lines.append(f"<b>Не оплатили более {overdue_days} дней:</b>")
        for item in overdue_debts[:30]:
            lines.append(
                f"- {item.get('student_name', '—')} | {item.get('subject_name', '—')} — "
                f"{item.get('teacher_name', '—')} | дней: {item.get('age_days', 0)} | "
                f"долг: {abs(item.get('lesson_balance', 0))}"
            )

    return "\n".join(lines)


def can_delete_role(actor_id: int, target_role: str) -> bool:
    if actor_id in SUPERADMINS:
        return target_role in {"admin", "teacher", "student"}
    return target_role in {"teacher", "student"}


def delete_user_with_related_data(target_role: str, target_telegram_id: int) -> dict:
    if target_role == "admin":
        return delete_admin_by_telegram_id(target_telegram_id)
    if target_role == "teacher":
        return delete_teacher_by_telegram_id(target_telegram_id)
    if target_role == "student":
        return delete_student_by_telegram_id(target_telegram_id)
    return {"ok": False}


def get_teacher_owned_directions(teacher_telegram_id: int, student_id: int):
    teacher = get_teacher_by_telegram_id(teacher_telegram_id)
    if not teacher:
        return []

    teacher_id = teacher[0]
    directions = get_student_directions(student_id)
    result = []

    for direction in directions:
        direction_id = direction[0]
        lesson = get_student_lesson_by_id(direction_id)
        if lesson and lesson[2] == teacher_id:
            result.append(direction)

    return result


def can_manage_attendance(user_id: int, direction_id: int) -> bool:
    role = get_role_by_user_id(user_id)
    if role in ["superadmin", "admin"]:
        return True

    if role != "teacher":
        return False

    teacher = get_teacher_by_telegram_id(user_id)
    lesson = get_student_lesson_by_id(direction_id)
    if not teacher or not lesson:
        return False

    return lesson[2] == teacher[0]


def load_teacher_names_for_binding() -> list[str]:
    names: list[str] = []
    for _teacher_id, full_name, _subject_name, _username in list_teacher_profiles(limit=2000):
        if full_name and full_name not in names:
            names.append(full_name)

    return names


def is_valid_username(value: str) -> bool:
    return bool(re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value.strip()))


def build_onboarding_link(token: str) -> str | None:
    if not SCHOOL_BOT_USERNAME:
        return None
    return f"https://t.me/{SCHOOL_BOT_USERNAME}?start=invite_{token}"


def parse_publication_links(raw_text: str) -> list[str]:
    value = (raw_text or "").strip()
    if not value or value == "-":
        return []

    links: list[str] = []
    for token in re.split(r"[\s,;]+", value):
        token = token.strip()
        if not token:
            continue
        if token.startswith("@"):
            token = f"https://t.me/{token.lstrip('@')}"
        if token.startswith("http://") or token.startswith("https://"):
            if token not in links:
                links.append(token)
    return links[:8]


def parse_publication_schedule(value: str) -> datetime | None:
    text = value.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = normalize_telegram_username(message.from_user.username)

    upsert_known_telegram_user(
        telegram_id=user_id,
        telegram_username=username,
        full_name=message.from_user.full_name,
    )

    if user_id in SUPERADMINS:
        existing_user = get_user_by_telegram_id(user_id)
        if not existing_user:
            add_user(
                telegram_id=user_id,
                full_name=message.from_user.full_name,
                role="superadmin"
            )

        await message.answer(
            "Внутренний бот школы.\n\nТы вошел как главный админ.",
            reply_markup=get_superadmin_menu()
        )
        return

    user = get_user_by_telegram_id(user_id)

    if not user:
        pending_admin_invite = get_latest_pending_invite_by_role_and_username("admin", username)
        if pending_admin_invite:
            invite_id, _token, _role, invite_full_name, _invite_username, _entity_type, _entity_id = pending_admin_invite
            add_user(
                telegram_id=user_id,
                full_name=invite_full_name or message.from_user.full_name,
                role="admin",
                telegram_username=username,
            )
            mark_onboarding_invite_used(invite_id=int(invite_id), telegram_id=user_id)
            await message.answer(
                "Доступ администратора активирован.\n\n"
                "Добро пожаловать во внутренний бот школы.",
                reply_markup=get_admin_menu(),
            )
            return

        await message.answer("У тебя нет доступа к этому боту.")
        return

    _, telegram_id, full_name, role, is_active = user

    if not is_active:
        await message.answer("Твой доступ отключен.")
        return

    if role == "admin":
        await message.answer(
            "Внутренний бот школы.\n\nТы вошел как админ.",
            reply_markup=get_admin_menu()
        )
        return

    if role == "teacher":
        await message.answer(
            "Внутренний бот школы.\n\nТы вошел как преподаватель.",
            reply_markup=get_teacher_menu()
        )
        return

    if role == "student":
        await message.answer(
            "Личный кабинет ученика.",
            reply_markup=get_student_menu()
        )
        return

    await message.answer("У тебя нет доступа к этому боту.")


@router.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext):
    await start_handler(message, state)


@router.callback_query(lambda c: c.data == "menu_home")
async def menu_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    menu = get_home_menu_by_user_id(callback.from_user.id)
    if menu is None:
        await callback.message.answer("Доступ не найден. Используйте /start для повторного входа.")
        await callback.answer()
        return
    await callback.message.answer("Главное меню.", reply_markup=menu)
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_section_users")
async def superadmin_section_users(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer("Раздел: управление пользователями.", reply_markup=get_superadmin_users_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_section_school")
async def superadmin_section_school(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer("Раздел: учебный процесс.", reply_markup=get_superadmin_school_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_section_reports")
async def superadmin_section_reports(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer("Раздел: отчеты и журнал.", reply_markup=get_superadmin_reports_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_back_main")
async def superadmin_back_main(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer("Главное меню супер-администратора.", reply_markup=get_superadmin_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_publication_new")
async def admin_publication_new(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.answer(
        "Введите текст публикации для учеников.\n"
        "Описание обязательно.",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_publication_description)
    await callback.answer()


@router.message(AdminStates.waiting_publication_description)
async def admin_publication_description(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Описание слишком короткое. Введите полноценный текст публикации.")
        return

    await state.update_data(publication_description=text)
    await message.answer(
        "Теперь отправьте фото для публикации.\n"
        "Если фото не нужно, отправьте символ: -"
    )
    await state.set_state(AdminStates.waiting_publication_photo)


@router.message(AdminStates.waiting_publication_photo)
async def admin_publication_photo(message: Message, state: FSMContext):
    photo_file_id = None
    text_value = (message.text or "").strip()

    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif text_value != "-":
        await message.answer("Отправьте фото или символ - чтобы пропустить.")
        return

    await state.update_data(publication_photo_file_id=photo_file_id)
    await message.answer(
        "Добавьте ссылки (через пробел или с новой строки).\n"
        "Можно вставлять URL или @username.\n"
        "Если ссылки не нужны, отправьте: -"
    )
    await state.set_state(AdminStates.waiting_publication_links)


@router.message(AdminStates.waiting_publication_links)
async def admin_publication_links(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    links = parse_publication_links(raw)
    if raw and raw != "-" and not links:
        await message.answer(
            "Не удалось распознать ссылки.\n"
            "Используйте формат https://... или @username, либо отправьте -."
        )
        return

    await state.update_data(publication_links=links)
    await message.answer(
        "Выберите аудиторию публикации:",
        reply_markup=get_publication_audience_keyboard(),
    )
    await state.set_state(AdminStates.waiting_publication_audience)


@router.callback_query(
    AdminStates.waiting_publication_audience,
    lambda c: c.data in {
        "publication_audience_students",
        "publication_audience_students_plus_me",
        "publication_audience_me_only",
    },
)
async def admin_publication_audience(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    audience_map = {
        "publication_audience_students": "students",
        "publication_audience_students_plus_me": "students_plus_creator",
        "publication_audience_me_only": "creator_only",
    }
    audience = audience_map.get(callback.data, "students")
    await state.update_data(publication_audience=audience)
    await callback.message.answer(
        "Выберите, когда отправить публикацию:",
        reply_markup=get_publication_schedule_keyboard(),
    )
    await state.set_state(AdminStates.waiting_publication_schedule_mode)
    await callback.answer()


@router.callback_query(
    AdminStates.waiting_publication_schedule_mode,
    lambda c: c.data in {"publication_send_now", "publication_schedule_pick_time"},
)
async def admin_publication_schedule_mode(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    description = (data.get("publication_description") or "").strip()
    photo_file_id = data.get("publication_photo_file_id")
    links = data.get("publication_links") or []
    audience = data.get("publication_audience") or "students"

    if not description:
        await state.clear()
        await callback.message.answer("Сценарий публикации сброшен. Начните заново.")
        await callback.answer()
        return

    if callback.data == "publication_send_now":
        scheduled_for = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        post_id = create_publication_post(
            created_by=callback.from_user.id,
            audience=audience,
            description=description,
            photo_file_id=photo_file_id,
            links=links,
            scheduled_for=scheduled_for,
        )
        log_admin_action(
            admin_telegram_id=callback.from_user.id,
            action_type="publication_created",
            target_type="publication_post",
            target_id=post_id,
            details={
                "mode": "now",
                "audience": audience,
                "has_photo": bool(photo_file_id),
                "links_count": len(links),
            },
            status="success",
        )
        await state.clear()
        await callback.message.answer(
            f"Публикация создана и поставлена в очередь отправки (ID: {post_id}).",
            reply_markup=get_admin_reply_menu(callback.from_user.id),
        )
        await callback.answer("Готово")
        return

    await callback.message.answer(
        "Введите дату и время публикации.\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 25.04.2026 10:30"
    )
    await state.set_state(AdminStates.waiting_publication_schedule_datetime)
    await callback.answer()


@router.message(AdminStates.waiting_publication_schedule_datetime)
async def admin_publication_schedule_datetime(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    schedule_dt = parse_publication_schedule(message.text or "")
    if schedule_dt is None:
        await message.answer("Неверный формат даты. Пример: 25.04.2026 10:30")
        return
    if schedule_dt <= datetime.now():
        await message.answer("Дата должна быть в будущем. Укажите более позднее время.")
        return

    data = await state.get_data()
    description = (data.get("publication_description") or "").strip()
    if not description:
        await state.clear()
        await message.answer("Сценарий публикации сброшен. Начните заново.")
        return

    photo_file_id = data.get("publication_photo_file_id")
    links = data.get("publication_links") or []
    audience = data.get("publication_audience") or "students"
    scheduled_for = schedule_dt.strftime("%Y-%m-%d %H:%M:%S")

    post_id = create_publication_post(
        created_by=message.from_user.id,
        audience=audience,
        description=description,
        photo_file_id=photo_file_id,
        links=links,
        scheduled_for=scheduled_for,
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="publication_created",
        target_type="publication_post",
        target_id=post_id,
        details={
            "mode": "scheduled",
            "audience": audience,
            "scheduled_for": scheduled_for,
            "has_photo": bool(photo_file_id),
            "links_count": len(links),
        },
        status="success",
    )

    await state.clear()
    await message.answer(
        f"Публикация запланирована на {schedule_dt.strftime('%d.%m.%Y %H:%M')} (ID: {post_id}).",
        reply_markup=get_admin_reply_menu(message.from_user.id),
    )


@router.callback_query(lambda c: c.data == "admin_add_student")
async def admin_add_student(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer(
        "Введите ФИО ученика.\nПодсказка: в любой момент можно нажать «Главное меню».",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_student_name)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_bind_teacher_telegram")
async def admin_bind_teacher_telegram(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    teacher_names = load_teacher_names_for_binding()
    if not teacher_names:
        await callback.message.answer("Не удалось получить список преподавателей.")
        await callback.answer()
        return

    await state.update_data(bind_teacher_names=teacher_names)
    await callback.message.answer(
        "Выбери преподавателя для привязки Telegram ID:",
        reply_markup=get_teacher_bind_keyboard(teacher_names)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_bind_teacher_cancel")
async def admin_bind_teacher_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.answer("Привязка отменена.", reply_markup=get_admin_reply_menu(callback.from_user.id))
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("bind_teacher_choose_"))
async def choose_teacher_for_binding(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    teacher_names = data.get("bind_teacher_names") or load_teacher_names_for_binding()

    try:
        idx = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    if idx < 0 or idx >= len(teacher_names):
        await callback.answer("Преподаватель не найден", show_alert=True)
        return

    teacher_name = teacher_names[idx]
    await state.update_data(bind_teacher_name=teacher_name, bind_teacher_names=teacher_names)

    await callback.message.answer(
        f"Выбран преподаватель: {teacher_name}\n\n"
        "Отправь Telegram ID преподавателя числом.\n"
        "Для отмены напиши: отмена"
    )
    await state.set_state(AdminStates.waiting_bind_teacher_telegram_id)
    await callback.answer()


@router.message(AdminStates.waiting_bind_teacher_telegram_id)
async def process_bind_teacher_telegram_id(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text.lower() in {"отмена", "-"}:
        await state.clear()
        await message.answer("Привязка отменена.", reply_markup=get_admin_reply_menu(message.from_user.id))
        return

    if not text.isdigit():
        await message.answer("Telegram ID должен быть числом. Для отмены напиши: отмена")
        return

    data = await state.get_data()
    teacher_name = data.get("bind_teacher_name")
    if not teacher_name:
        await state.clear()
        await message.answer(
            "Не удалось определить преподавателя. Начни заново через меню.",
            reply_markup=get_admin_reply_menu(message.from_user.id)
        )
        return

    telegram_id = int(text)
    result = bind_teacher_telegram_id(teacher_name, telegram_id)

    if not result["ok"]:
        log_admin_action(
            admin_telegram_id=message.from_user.id,
            action_type="bind_teacher_telegram_failed",
            target_type="teacher",
            target_id=None,
            details={"teacher_name": teacher_name, "error": result["error"]},
            status="error",
        )
        await message.answer(f"❌ {result['error']}\nПопробуй другой Telegram ID.")
        return

    add_user(
        telegram_id=telegram_id,
        full_name=teacher_name,
        role="teacher"
    )

    await message.answer(
        "✅ Преподаватель привязан.\n\n"
        f"Преподаватель: {teacher_name}\n"
        f"Telegram ID: {telegram_id}",
        reply_markup=get_admin_reply_menu(message.from_user.id)
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="bind_teacher_telegram_success",
        target_type="teacher",
        target_id=result.get("teacher_id"),
        details={
            "before": None,
            "after": {"teacher_name": teacher_name, "telegram_id": telegram_id},
        },
        status="success",
    )
    await state.clear()


@router.message(AdminStates.waiting_student_name)
async def get_student_name(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    await state.update_data(full_name=message.text.strip())
    await message.answer(
        "Укажите @username ученика (обязательно), например: @ivan_ivanov"
    )
    await state.set_state(AdminStates.waiting_student_username)


@router.message(AdminStates.waiting_student_username)
async def get_student_username(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not is_valid_username(text):
        await message.answer("Введите корректный @username в формате @example_user")
        return

    normalized_username = normalize_telegram_username(text)
    telegram_id = get_known_telegram_user_id_by_username(normalized_username)
    await state.update_data(
        telegram_id=telegram_id,
        telegram_username=normalized_username,
    )
    await message.answer("Введи номер телефона ученика или напиши '-' если его нет:")
    await state.set_state(AdminStates.waiting_student_phone)


@router.message(AdminStates.waiting_student_phone)
async def get_student_phone(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    phone = None if text == "-" else text

    data = await state.get_data()

    student_id = add_student(
        full_name=data["full_name"],
        telegram_id=data["telegram_id"],
        phone=phone,
        telegram_username=data.get("telegram_username"),
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_student",
        target_type="student",
        target_id=None,
        details={
            "before": None,
            "after": {
                "full_name": data["full_name"],
                "telegram_id": data["telegram_id"],
                "telegram_username": data.get("telegram_username"),
                "phone": phone,
            },
        },
        status="success",
    )

    if data["telegram_id"]:
        add_user(
            telegram_id=data["telegram_id"],
            full_name=data["full_name"],
            role="student",
            telegram_username=data.get("telegram_username"),
        )

    onboarding_text = ""
    if not data["telegram_id"]:
        token = create_onboarding_invite(
            role="student",
            full_name=data["full_name"],
            telegram_username=data.get("telegram_username") or "",
            entity_type="student",
            entity_id=student_id,
            created_by=message.from_user.id,
        )
        link = build_onboarding_link(token)
        if link:
            onboarding_text = (
                "\n\nПользователь еще не писал боту, поэтому ID пока не найден.\n"
                "Отправьте ему эту ссылку для автоматической привязки:\n"
                f"{link}"
            )
        else:
            onboarding_text = (
                "\n\nПользователь еще не писал боту, но ссылка не сформирована "
                "(проверьте переменную SCHOOL_BOT_USERNAME в .env)."
            )

    await message.answer(
        "✅ Ученик добавлен.\n\n"
        f"ФИО: {data['full_name']}\n"
        f"Telegram ID: {data['telegram_id'] if data['telegram_id'] else '-'}\n"
        f"Username: @{data.get('telegram_username') if data.get('telegram_username') else '-'}\n"
        f"Телефон: {phone if phone else '-'}\n"
        f"ID в базе: {student_id}\n"
        f"Роль student: {'создана' if data['telegram_id'] else 'будет создана после входа по ссылке'}"
        f"{onboarding_text}",
        reply_markup=get_admin_menu()
    )

    await state.clear()


@router.callback_query(lambda c: c.data == "admin_assign_lesson")
async def admin_assign_lesson(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    students = get_all_students()
    if not students:
        await callback.message.answer("Сначала добавь хотя бы одного ученика.")
        await callback.answer()
        return

    text_lines = ["Выбери ученика из списка ниже и отправь его ID (в скобках):\n"]
    for index, student in enumerate(students, start=1):
        student_id, full_name, telegram_id, phone = student
        text_lines.append(f"{index}. {full_name} (ID: {student_id})")

    await callback.message.answer("\n".join(text_lines))
    await state.set_state(AdminStates.choosing_student_for_lesson)
    await callback.answer()


@router.message(AdminStates.choosing_student_for_lesson)
async def choose_student_for_lesson(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введи ID ученика числом.")
        return

    student_id = int(text)
    students = get_all_students()
    valid_ids = [student[0] for student in students]

    if student_id not in valid_ids:
        await message.answer("Ученика с таким ID нет. Введи корректный ID.")
        return

    teachers = list_teacher_profiles(limit=1000)
    if not teachers:
        await message.answer("Преподаватели пока не добавлены.")
        await state.clear()
        return

    await state.update_data(
        student_id=student_id,
        assign_teacher_candidates=[int(item[0]) for item in teachers],
    )
    await message.answer(
        "Выберите преподавателя из списка кнопками ниже.\n"
        "Или введите часть ФИО для поиска (например: Ма).",
        reply_markup=get_teacher_selection_keyboard(teachers, action_prefix="assign_teacher_pick"),
    )
    await state.set_state(AdminStates.waiting_teacher_name)
    return


@router.message(AdminStates.waiting_teacher_selection)
async def get_teacher_name(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите ID преподавателя числом из списка выше.")
        return

    teacher_id = int(text)
    data = await state.get_data()
    allowed_ids = data.get("assign_teacher_candidates") or []
    if teacher_id not in allowed_ids:
        await message.answer("Такого ID нет в текущем списке. Введите ID из списка выше.")
        return

    teacher = get_teacher_profile_by_id(teacher_id)
    if not teacher:
        await message.answer("Преподаватель не найден. Повторите поиск.")
        await state.set_state(AdminStates.waiting_teacher_name)
        return

    _, _teacher_telegram_id, teacher_name, _teacher_subject, _description, _photo, _username = teacher
    await state.update_data(teacher_id=teacher_id, teacher_name=teacher_name)
    await message.answer(f"Выбран преподаватель: {teacher_name}\n\nВведите предмет:")
    await state.set_state(AdminStates.waiting_subject_name)
    return


@router.message(AdminStates.waiting_teacher_name)
async def search_teacher_for_lesson_by_fio(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    query = (message.text or "").strip().lower()
    if len(query) < 2:
        await message.answer("Введите минимум 2 символа ФИО преподавателя для поиска.")
        return

    teachers = search_teacher_profiles(query, limit=50)
    teachers = [item for item in teachers if query in (item[1] or "").lower()]
    if not teachers:
        await message.answer("По ФИО преподаватели не найдены. Попробуйте другой запрос.")
        return

    await state.update_data(assign_teacher_candidates=[int(item[0]) for item in teachers])
    await message.answer(
        "Найдены преподаватели. Выберите нужного кнопкой:",
        reply_markup=get_teacher_selection_keyboard(teachers, action_prefix="assign_teacher_pick"),
    )
    await state.set_state(AdminStates.waiting_teacher_name)


@router.callback_query(lambda c: c.data.startswith("assign_teacher_pick_"))
async def choose_teacher_for_lesson(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        await state.clear()
        return

    try:
        teacher_id = int(callback.data.split("_")[-1])
    except (TypeError, ValueError):
        await callback.answer("Не удалось определить преподавателя", show_alert=True)
        return

    data = await state.get_data()
    allowed_ids = data.get("assign_teacher_candidates") or []
    if allowed_ids and teacher_id not in allowed_ids:
        await callback.answer("Преподаватель не из текущего списка", show_alert=True)
        return

    teacher = get_teacher_profile_by_id(teacher_id)
    if not teacher:
        await callback.answer("Преподаватель не найден", show_alert=True)
        return

    _, _teacher_telegram_id, teacher_name, _teacher_subject, _description, _photo, _username = teacher
    await state.update_data(teacher_id=teacher_id, teacher_name=teacher_name)
    await callback.message.answer(
        f"Выбран преподаватель: {teacher_name}\n\nВведите часть названия предмета (или новое название):"
    )
    await state.set_state(AdminStates.waiting_subject_name)
    await callback.answer()


@router.message(AdminStates.waiting_subject_name)
async def get_subject_name(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    raw_subject_query = (message.text or "").strip()
    if len(raw_subject_query) < 2:
        await message.answer("Введите корректное название предмета (минимум 2 символа).")
        return

    subject_query = raw_subject_query.lower()
    subjects = [item for item in get_teacher_catalog_subjects() if item]
    matched_subjects = [item for item in subjects if subject_query in item.lower()]

    if len(matched_subjects) == 1:
        subject_name = matched_subjects[0]
    elif len(matched_subjects) > 1:
        variants = ", ".join(matched_subjects[:6])
        await message.answer(
            "Найдено несколько предметов по запросу. Уточните название:\n"
            f"{variants}"
        )
        return
    else:
        subject_name = raw_subject_query

    await state.update_data(subject_name=subject_name, expect_custom_subject=False)
    await message.answer("Выбери тип тарифа:", reply_markup=get_tariff_keyboard())
    await state.set_state(AdminStates.waiting_tariff_type)


@router.callback_query(AdminStates.waiting_tariff_type, lambda c: c.data in ["tariff_single", "tariff_package"])
async def choose_tariff_type(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        await state.clear()
        return

    tariff_map = {
        "tariff_single": "single",
        "tariff_package": "package"
    }

    tariff_type = tariff_map[callback.data]
    await state.update_data(tariff_type=tariff_type)

    await callback.message.answer("Сколько занятий начислить на баланс?")
    await state.set_state(AdminStates.waiting_lesson_balance)
    await callback.answer()


@router.message(AdminStates.waiting_lesson_balance)
async def get_lesson_balance(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введи количество занятий числом.")
        return

    lesson_balance = int(text)
    if lesson_balance < 0:
        await message.answer("Количество занятий не может быть отрицательным.")
        return

    data = await state.get_data()

    teacher_id = data.get("teacher_id")
    if not teacher_id:
        teacher_id = add_teacher_if_not_exists(data["teacher_name"])

    add_student_lesson(
        student_id=data["student_id"],
        teacher_id=teacher_id,
        subject_name=data["subject_name"],
        lesson_balance=lesson_balance,
        tariff_type=data["tariff_type"]
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="assign_lesson",
        target_type="student_lesson",
        target_id=None,
        details={
            "student_id": data["student_id"],
            "teacher_id": teacher_id,
            "subject_name": data["subject_name"],
            "lesson_balance": lesson_balance,
            "tariff_type": data["tariff_type"],
        },
        status="success",
    )

    await message.answer(
        "✅ Направление добавлено.\n\n"
        f"ID ученика: {data['student_id']}\n"
        f"Преподаватель: {data['teacher_name']}\n"
        f"Предмет: {data['subject_name']}\n"
        f"Тариф: {data['tariff_type']}\n"
        f"Баланс: {lesson_balance}",
        reply_markup=get_admin_menu()
    )

    await state.clear()


@router.callback_query(lambda c: c.data == "admin_find_student")
async def admin_find_student(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Введи имя или часть имени ученика:")
    await state.set_state(AdminStates.waiting_student_search)
    await callback.answer()


@router.message(AdminStates.waiting_student_search)
async def search_student(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    search_text = message.text.strip()
    students = find_students_by_name(search_text)

    if not students:
        await message.answer("Ничего не найдено.", reply_markup=get_admin_menu())
        await state.clear()
        return

    result_messages = []

    for student in students:
        student_id, full_name, telegram_id, phone = student
        directions = get_student_directions(student_id)

        text = (
            f"👤 <b>{full_name}</b>\n"
            f"🆔 ID: <code>{student_id}</code>\n"
            f"📱 Телефон: {phone if phone else '-'}\n"
            f"🔗 Telegram ID: {telegram_id if telegram_id else '-'}\n\n"
        )

        if directions:
            text += "<b>Направления:</b>\n"
            for direction in directions:
                _, teacher_name, subject_name, lesson_balance, tariff_type = direction
                tariff_text = "Разовое" if tariff_type == "single" else "Пакет"
                text += (
                    f"• {subject_name} — {teacher_name}\n"
                    f"  Тариф: {tariff_text}\n"
                    f"  Остаток: {lesson_balance}\n"
                )
        else:
            text += "Направлений пока нет."

        result_messages.append(text)

    for text in result_messages:
        await message.answer(text, parse_mode="HTML")

    await message.answer("Поиск завершен.", reply_markup=get_admin_menu())
    await state.clear()


@router.callback_query(lambda c: c.data == "admin_attendance")
async def admin_attendance(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await update_flow_message(
        callback,
        "Введите имя или часть имени ученика для отметки посещения.\n\n"
        "Финальный результат будет отправлен отдельным сообщением.",
    )
    await state.set_state(AdminStates.waiting_attendance_student_search)
    await callback.answer()


@router.callback_query(lambda c: c.data == "teacher_students")
async def teacher_students(callback: CallbackQuery):
    if not is_teacher_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    teacher = get_teacher_by_telegram_id(callback.from_user.id)
    if not teacher:
        await callback.message.answer(
            "Профиль преподавателя не найден. Пожалуйста, обратитесь к администратору."
        )
        await callback.answer()
        return

    students = get_students_by_teacher_telegram_id(callback.from_user.id)
    if not students:
        await callback.message.answer("За вами пока не закреплены ученики.")
        await callback.answer()
        return

    lines = ["<b>Ваши ученики:</b>\n"]
    for student_id, full_name, telegram_id, phone in students:
        directions = get_teacher_owned_directions(callback.from_user.id, student_id)
        direction_text = "; ".join(
            f"{subject_name} (остаток: {lesson_balance})"
            for _, _, subject_name, lesson_balance, _ in directions
        ) or "Направления пока не найдены"

        lines.append(
            f"• <b>{full_name}</b>\n"
            f"ID: <code>{telegram_id if telegram_id else '-'}</code>\n"
            f"Телефон: {phone if phone else '-'}\n"
            f"Направления: {direction_text}\n"
        )

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_teacher_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "teacher_attendance")
async def teacher_attendance_v2(callback: CallbackQuery):
    if not is_teacher_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    students = get_students_by_teacher_telegram_id(callback.from_user.id)
    if not students:
        await update_flow_message(callback, "За Вами пока не закреплены ученики.")
        await callback.answer()
        return

    await update_flow_message(
        callback,
        "Выберите ученика для отметки посещаемости:",
        reply_markup=get_teacher_attendance_students_keyboard(students),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("teacher_attendance_student_"))
async def teacher_attendance_choose_student(callback: CallbackQuery):
    if not is_teacher_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        student_id = int(callback.data.split("_")[-1])
    except (TypeError, ValueError):
        await callback.answer("Не удалось определить ученика", show_alert=True)
        return

    directions = get_teacher_owned_directions(callback.from_user.id, student_id)
    if not directions:
        await update_flow_message(callback, "Для этого ученика у Вас пока нет направлений.")
        await callback.answer()
        return

    await update_flow_message(
        callback,
        "Выберите направление ученика для отметки посещаемости:",
        reply_markup=get_attendance_direction_keyboard(directions),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "teacher_attendance_legacy")
async def teacher_attendance(callback: CallbackQuery):
    if not is_teacher_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    students = get_students_by_teacher_telegram_id(callback.from_user.id)
    if not students:
        await callback.message.answer("За вами пока не закреплены ученики.")
        await callback.answer()
        return

    directions = []
    for student_id, _, _, _ in students:
        directions.extend(get_teacher_owned_directions(callback.from_user.id, student_id))

    if not directions:
        await callback.message.answer("Для вас пока нет направлений для отметки посещения.")
        await callback.answer()
        return

    await callback.message.answer(
        "Выберите направление для отметки посещения:",
        reply_markup=get_attendance_direction_keyboard(directions)
    )
    await callback.answer()


@router.message(AdminStates.waiting_attendance_student_search)
async def attendance_student_search(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    search_text = message.text.strip()
    students = find_students_by_name(search_text)

    if not students:
        await message.answer("Ученик не найден.", reply_markup=get_admin_menu())
        await state.clear()
        return

    if len(students) > 1:
        lines = ["Найдено несколько учеников:\n"]
        for index, student in enumerate(students, start=1):
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{index}. {full_name} (ID: {student_id})")
        lines.append("\nУточни запрос точнее.")
        await message.answer("\n".join(lines), reply_markup=get_admin_menu())
        await state.clear()
        return

    student_id, full_name, telegram_id, phone = students[0]
    directions = get_student_directions(student_id)

    if not directions:
        await message.answer("У этого ученика пока нет направлений.", reply_markup=get_admin_menu())
        await state.clear()
        return

    await message.answer(
        f"Выбери направление для ученика {full_name}:",
        reply_markup=get_attendance_direction_keyboard(directions)
    )
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("attendance_direction_"))
async def choose_attendance_direction(callback: CallbackQuery):
    direction_id = int(callback.data.split("_")[-1])

    if not can_manage_attendance(callback.from_user.id, direction_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance, tariff_type, student_name, teacher_name = lesson

    await update_flow_message(
        callback,
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Остаток: {lesson_balance}\n\n"
        f"Отметьте посещение:",
        reply_markup=get_attendance_mark_keyboard(direction_id)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("attendance_present_") or c.data.startswith("attendance_absent_"))
async def mark_student_attendance(callback: CallbackQuery):
    if callback.data.startswith("attendance_present_"):
        direction_id = int(callback.data.split("_")[-1])
        status = "present"
    else:
        direction_id = int(callback.data.split("_")[-1])
        status = "absent"

    if not can_manage_attendance(callback.from_user.id, direction_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, student_id, _, subject_name, lesson_balance_before, tariff_type, student_name, teacher_name = lesson

    mark_attendance(direction_id, status, callback.from_user.id)
    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="mark_attendance",
        target_type="student_lesson",
        target_id=direction_id,
        details={"status": status},
        status="success",
    )

    updated_lesson = get_student_lesson_by_id(direction_id)
    _, _, _, _, lesson_balance_after, _, _, _ = updated_lesson

    student = get_student_by_id(student_id)
    student_telegram_id = student[2] if student else None

    await notify_student_about_attendance_clean(
        callback,
        student_telegram_id=student_telegram_id,
        student_name=student_name,
        subject_name=subject_name,
        teacher_name=teacher_name,
        tariff_type=tariff_type,
        status=status,
        lesson_balance_before=lesson_balance_before,
        lesson_balance_after=lesson_balance_after,
    )

    teacher_telegram_id = None
    teacher = get_teacher_by_id(lesson[2])
    if teacher:
        teacher_telegram_id = teacher[1]
    if teacher_telegram_id and teacher_telegram_id != callback.from_user.id:
        await notify_teacher_about_attendance(
            callback,
            teacher_telegram_id=teacher_telegram_id,
            student_name=student_name,
            subject_name=subject_name,
            status=status,
            lesson_balance_after=lesson_balance_after,
        )

    status_text = "Был" if status == "present" else "Не был"

    await callback.message.answer(
        f"✅ Посещаемость отмечена\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Статус: {status_text}\n"
        f"Баланс был: {lesson_balance_before}\n"
        f"Баланс стал: {lesson_balance_after}",
        reply_markup=get_admin_reply_menu(callback.from_user.id) if is_admin_role(callback.from_user.id) else get_teacher_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Введи имя или часть имени ученика для начисления занятий:")
    await state.set_state(AdminStates.waiting_balance_student_search)
    await callback.answer()


@router.message(AdminStates.waiting_balance_student_search)
async def balance_student_search(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    search_text = message.text.strip()
    students = find_students_by_name(search_text)

    if not students:
        await message.answer("Ученик не найден.", reply_markup=get_admin_menu())
        await state.clear()
        return

    if len(students) > 1:
        lines = ["Найдено несколько учеников:\n"]
        for index, student in enumerate(students, start=1):
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{index}. {full_name} (ID: {student_id})")
        lines.append("\nУточни запрос точнее.")
        await message.answer("\n".join(lines), reply_markup=get_admin_menu())
        await state.clear()
        return

    student_id, full_name, telegram_id, phone = students[0]
    directions = get_student_directions(student_id)

    if not directions:
        await message.answer("У этого ученика пока нет направлений.", reply_markup=get_admin_menu())
        await state.clear()
        return

    await message.answer(
        f"Выбери направление для начисления ученику {full_name}:",
        reply_markup=get_balance_direction_keyboard(directions)
    )
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("balance_direction_"))
async def choose_balance_direction(callback: CallbackQuery):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    direction_id = int(callback.data.split("_")[-1])

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance, tariff_type, student_name, teacher_name = lesson

    await callback.message.answer(
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Текущий баланс: {lesson_balance}\n\n"
        f"Сколько занятий начислить?",
        reply_markup=get_balance_add_keyboard(direction_id)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("balance_add_"))
async def add_balance_to_direction(callback: CallbackQuery):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    direction_id = int(parts[2])
    lessons_to_add = int(parts[3])

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance_before, tariff_type, student_name, teacher_name = lesson

    add_lessons_to_balance(
        direction_id,
        lessons_to_add,
        created_by=callback.from_user.id,
        comment="Ручное начисление админом"
    )
    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="manual_balance_topup",
        target_type="student_lesson",
        target_id=direction_id,
        details={"lessons_to_add": lessons_to_add},
        status="success",
    )

    updated_lesson = get_student_lesson_by_id(direction_id)
    _, _, _, _, lesson_balance_after, _, _, _ = updated_lesson

    await callback.message.answer(
        f"✅ Баланс пополнен\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Баланс был: {lesson_balance_before}\n"
        f"Начислено: {lessons_to_add}\n"
        f"Баланс стал: {lesson_balance_after}",
        reply_markup=get_admin_reply_menu(callback.from_user.id) if is_admin_role(callback.from_user.id) else get_teacher_menu()
    )

    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_balance_history")
async def admin_balance_history(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Введи имя или часть имени ученика для просмотра истории:")
    await state.set_state(AdminStates.waiting_history_student_search)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_actions_recent")
async def admin_actions_recent(callback: CallbackQuery):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    rows = get_recent_admin_actions(30)
    if not rows:
        await callback.message.answer("Журнал действий пока пуст.")
        await callback.answer()
        return

    lines = ["<b>Последние действия админов:</b>\n"]
    for row in rows:
        action_id, admin_id, action_type, target_type, target_id, details, status, created_at = row
        lines.append(
            f"#{action_id} | {created_at}\n"
            f"admin: <code>{admin_id}</code>\n"
            f"action: <b>{action_type}</b> ({status})\n"
            f"target: {target_type if target_type else '-'}:{target_id if target_id else '-'}\n"
            f"details: {details if details else '-'}\n"
        )

    chunks = []
    current = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > 3500 and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))

    for chunk in chunks:
        await callback.message.answer(chunk, parse_mode="HTML")

    await callback.answer()


@router.message(AdminStates.waiting_history_student_search)
async def show_balance_history(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    search_text = message.text.strip()
    students = find_students_by_name(search_text)

    if not students:
        await message.answer("Ученик не найден.", reply_markup=get_admin_menu())
        await state.clear()
        return

    if len(students) > 1:
        lines = ["Найдено несколько учеников:\n"]
        for index, student in enumerate(students, start=1):
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{index}. {full_name} (ID: {student_id})")
        lines.append("\nУточни запрос точнее.")
        await message.answer("\n".join(lines), reply_markup=get_admin_menu())
        await state.clear()
        return

    student_id, full_name, telegram_id, phone = students[0]
    history_rows = get_balance_history_by_student(student_id)

    if not history_rows:
        await message.answer("История операций пока пустая.", reply_markup=get_admin_menu())
        await state.clear()
        return

    chunks = []
    current_chunk = [f"📘 <b>История баланса</b>\n\n👤 <b>{full_name}</b>\n"]

    for row in history_rows:
        _, student_name, teacher_name, subject_name, operation_type, lessons_delta, comment, created_at, created_by = row

        if operation_type == "manual_topup":
            op_text = "Начисление"
        elif operation_type == "attendance_writeoff":
            op_text = "Списание за посещение"
        else:
            op_text = operation_type

        sign = "+" if lessons_delta > 0 else ""

        entry = (
            f"\n📅 <b>{created_at}</b>\n"
            f"📚 {subject_name} — {teacher_name}\n"
            f"🧾 {op_text}\n"
            f"🔢 {sign}{lessons_delta}\n"
            f"💬 {comment if comment else '-'}\n"
            f"👨‍💼 ID кто сделал: {created_by if created_by else '-'}\n"
        )

        current_chunk.append(entry)

        if sum(len(x) for x in current_chunk) > 3000:
            chunks.append("".join(current_chunk))
            current_chunk = []

    if current_chunk:
        chunks.append("".join(current_chunk))

    for chunk in chunks:
        await message.answer(chunk, parse_mode="HTML")

    await message.answer("История показана.", reply_markup=get_admin_menu())
    await state.clear()


@router.callback_query(lambda c: c.data == "admin_delete_user")
async def admin_delete_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    if callback.from_user.id in SUPERADMINS:
        role_hint = "Доступно удаление ролей: администратор, преподаватель, ученик."
    else:
        role_hint = "Доступно удаление ролей: преподаватель, ученик."

    await callback.message.answer(
        "Введите ФИО или @username пользователя для удаления.\n"
        f"{role_hint}",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_delete_user_query)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_debt_report")
async def admin_debt_report(callback: CallbackQuery):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    overdue_days_raw = os.getenv("SCHOOL_DEBT_OVERDUE_DAYS", "7").strip()
    try:
        overdue_days = max(1, int(overdue_days_raw))
    except ValueError:
        overdue_days = 7
    report_data = build_daily_debt_report(
        report_date=date.today().isoformat(),
        overdue_days=overdue_days,
    )
    text = format_debt_report_text(report_data, overdue_days)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer("Отчёт сформирован")


@router.message(AdminStates.waiting_delete_user_query)
async def process_delete_user_query(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text.lower() in {"отмена", "cancel", "/menu"}:
        await state.clear()
        await message.answer("Удаление отменено.", reply_markup=get_admin_reply_menu(message.from_user.id))
        return

    allowed_roles = ("admin", "teacher", "student") if message.from_user.id in SUPERADMINS else ("teacher", "student")
    candidates = search_users_by_name_or_username(text, roles=allowed_roles, limit=20)
    if not candidates:
        await message.answer(
            "Ничего не найдено. Попробуйте другой запрос (ФИО или @username).",
            reply_markup=get_main_menu_shortcut_keyboard(),
        )
        return

    prepared = []
    for user_id, telegram_id, full_name, role, _is_active, telegram_username in candidates:
        if telegram_id in SUPERADMINS:
            continue
        prepared.append((user_id, full_name, role, telegram_username, str(telegram_id)))

    if not prepared:
        await message.answer("Подходящих пользователей для удаления не найдено.")
        return

    await state.set_state(AdminStates.waiting_delete_user_selection)
    await message.answer(
        "Выберите пользователя для удаления:",
        reply_markup=get_user_selection_keyboard(prepared, "delete_user_pick"),
    )


@router.callback_query(
    AdminStates.waiting_delete_user_selection,
    lambda c: c.data.startswith("delete_user_pick_"),
)
async def process_delete_user_selection(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        user_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    target_user = get_user_by_id(user_id)
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    _, target_telegram_id, target_full_name, target_role, _is_active, target_username = target_user
    if target_telegram_id in SUPERADMINS:
        await callback.answer("Удалять супер-админа запрещено", show_alert=True)
        return
    if target_role not in {"admin", "teacher", "student"}:
        await callback.answer("Эта роль не поддерживается для удаления", show_alert=True)
        return
    if not can_delete_role(callback.from_user.id, target_role):
        await callback.answer("Недостаточно прав для удаления", show_alert=True)
        return

    before_snapshot = {
        "full_name": target_full_name,
        "role": target_role,
        "telegram_id": target_telegram_id,
        "telegram_username": target_username,
    }
    result = delete_user_with_related_data(target_role, target_telegram_id)
    if not result.get("ok"):
        await callback.answer("Не удалось удалить пользователя", show_alert=True)
        return

    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="delete_user",
        target_type=target_role,
        target_id=target_telegram_id,
        details={
            "before": before_snapshot,
            "after": None,
            "result": result,
        },
        status="success",
    )

    await state.clear()
    await callback.message.answer(
        f"Пользователь удален.\n"
        f"Имя: {target_full_name}\n"
        f"Роль: {role_title(target_role)}\n"
        f"Username: @{target_username if target_username else '-'}",
        reply_markup=get_admin_reply_menu(callback.from_user.id),
    )
    await callback.answer("Готово")


@router.callback_query(lambda c: c.data == "superadmin_add_admin")
async def superadmin_add_admin(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer(
        "Отправьте @username нового администратора (обязательно).\n"
        "Подсказка: нажмите «Главное меню», если хотите выйти из сценария.",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_new_admin_username)
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_change_role")
async def superadmin_change_role(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.answer(
        "Введите ФИО или @username пользователя, у которого нужно изменить роль:",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_role_change_query)
    await callback.answer()


@router.message(AdminStates.waiting_role_change_query)
async def process_role_change_query(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text.lower() in {"отмена", "cancel", "/menu"}:
        await state.clear()
        await message.answer("Изменение роли отменено.", reply_markup=get_superadmin_menu())
        return

    candidates = search_users_by_name_or_username(text, roles=("admin", "teacher", "student"), limit=20)
    if not candidates:
        await message.answer(
            "Пользователи не найдены. Попробуйте другой запрос.",
            reply_markup=get_main_menu_shortcut_keyboard(),
        )
        return

    prepared = []
    for user_id, telegram_id, full_name, role, _is_active, username in candidates:
        if telegram_id in SUPERADMINS:
            continue
        prepared.append((user_id, full_name, role, username, str(telegram_id)))

    if not prepared:
        await message.answer("Подходящие пользователи для смены роли не найдены.")
        return

    await message.answer(
        "Выберите пользователя:",
        reply_markup=get_user_selection_keyboard(prepared, "role_user_pick"),
    )
    await state.set_state(AdminStates.waiting_role_change_selection)


@router.callback_query(
    AdminStates.waiting_role_change_selection,
    lambda c: c.data.startswith("role_user_pick_"),
)
async def process_role_change_user_pick(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        user_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    target_user = get_user_by_id(user_id)
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    _, target_telegram_id, _target_full_name, _current_role, _is_active, _username = target_user
    await state.update_data(role_change_target_id=target_telegram_id)
    await callback.message.answer(
        "Выберите новую роль:",
        reply_markup=get_role_change_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    AdminStates.waiting_role_change_selection,
    lambda c: c.data.startswith("role_set_"),
)
async def process_role_change_selection(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    action = callback.data.replace("role_set_", "", 1)
    if action == "cancel":
        await state.clear()
        await callback.message.answer("Изменение роли отменено.", reply_markup=get_superadmin_menu())
        await callback.answer()
        return

    data = await state.get_data()
    target_telegram_id = data.get("role_change_target_id")
    if not target_telegram_id:
        await state.clear()
        await callback.answer("Целевой пользователь не найден", show_alert=True)
        return

    target_user = get_user_by_telegram_id(target_telegram_id)
    if not target_user:
        await state.clear()
        await callback.message.answer("Пользователь не найден.", reply_markup=get_superadmin_menu())
        await callback.answer()
        return

    _, _, target_full_name, current_role, _is_active = target_user

    if action == "disabled":
        changed = set_user_active(target_telegram_id, False)
        if not changed:
            await callback.answer("Не удалось отключить доступ", show_alert=True)
            return

        log_admin_action(
            admin_telegram_id=callback.from_user.id,
            action_type="change_role",
            target_type="user",
            target_id=target_telegram_id,
            details={
                "before": {"role": current_role, "is_active": True},
                "after": {"role": current_role, "is_active": False},
            },
            status="success",
        )
        await state.clear()
        await callback.message.answer(
            f"Доступ пользователя отключён.\nTelegram ID: {target_telegram_id}",
            reply_markup=get_superadmin_menu(),
        )
        await callback.answer("Готово")
        return

    if action not in {"admin", "teacher", "student"}:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    changed = update_user_role(target_telegram_id, action)
    if not changed:
        await callback.answer("Не удалось изменить роль", show_alert=True)
        return

    if action == "teacher":
        add_teacher_if_not_exists(full_name=target_full_name, telegram_id=target_telegram_id)

    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="change_role",
        target_type="user",
        target_id=target_telegram_id,
        details={
            "before": {"role": current_role, "is_active": True},
            "after": {"role": action, "is_active": True},
        },
        status="success",
    )

    await state.clear()
    await callback.message.answer(
        f"Роль пользователя обновлена.\nTelegram ID: {target_telegram_id}\nНовая роль: {action}",
        reply_markup=get_superadmin_menu(),
    )
    await callback.answer("Готово")


@router.message(AdminStates.waiting_new_admin_username)
async def process_new_admin_username(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if not is_valid_username(text):
        await message.answer("Введите корректный @username в формате @example_user")
        return

    normalized_username = normalize_telegram_username(text)
    telegram_id = get_known_telegram_user_id_by_username(normalized_username)

    onboarding_text = ""
    target_id_for_log = None
    if telegram_id is not None:
        add_user(
            telegram_id=telegram_id,
            full_name=f"Admin @{normalized_username}",
            role="admin",
            telegram_username=normalized_username,
        )
        target_id_for_log = telegram_id
    else:
        token = create_onboarding_invite(
            role="admin",
            full_name=f"Admin @{normalized_username}",
            telegram_username=normalized_username,
            entity_type="user",
            entity_id=None,
            created_by=message.from_user.id,
        )
        link = build_onboarding_link(token)
        if link:
            onboarding_text = (
                "\n\nПользователь еще не писал школьному боту.\n"
                "Отправьте ему ссылку для автоматической выдачи роли admin:\n"
                f"{link}"
            )
        else:
            onboarding_text = (
                "\n\nПользователь еще не писал школьному боту, но ссылка не сформирована "
                "(проверьте SCHOOL_BOT_USERNAME в .env)."
            )

    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_admin",
        target_type="user",
        target_id=target_id_for_log,
        details={
            "before": None,
            "after": {
                "role": "admin",
                "telegram_username": normalized_username,
                "telegram_id": telegram_id,
            },
        },
        status="success",
    )

    await message.answer(
        "✅ Администратор добавлен.\n"
        f"Username: @{normalized_username}\n"
        f"Telegram ID: {telegram_id if telegram_id else 'будет определен автоматически'}"
        f"{onboarding_text}",
        reply_markup=get_superadmin_menu()
    )
    await state.clear()


@router.callback_query(lambda c: c.data == "superadmin_edit_teacher")
async def superadmin_edit_teacher(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.answer(
        "Введите ФИО, предмет или @username преподавателя для редактирования карточки:",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_edit_teacher_query)
    await callback.answer()


@router.message(AdminStates.waiting_edit_teacher_query)
async def process_edit_teacher_query(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    query = message.text.strip()
    if query.lower() in {"отмена", "cancel", "/menu"}:
        await state.clear()
        await message.answer("Редактирование преподавателя отменено.", reply_markup=get_superadmin_menu())
        return

    teachers = search_teacher_profiles(query, limit=20)
    if not teachers:
        await message.answer(
            "Преподаватели не найдены. Попробуйте другой запрос.",
            reply_markup=get_main_menu_shortcut_keyboard(),
        )
        return

    await message.answer(
        "Выберите преподавателя:",
        reply_markup=get_teacher_selection_keyboard(teachers),
    )
    await state.set_state(AdminStates.waiting_edit_teacher_selection)


@router.callback_query(
    AdminStates.waiting_edit_teacher_selection,
    lambda c: c.data.startswith("edit_teacher_pick_"),
)
async def process_edit_teacher_pick(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        teacher_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    teacher = get_teacher_profile_by_id(teacher_id)
    if not teacher:
        await callback.answer("Преподаватель не найден", show_alert=True)
        return

    (
        _teacher_id,
        telegram_id,
        full_name,
        subject_name,
        description,
        photo_path,
        telegram_username,
    ) = teacher

    await state.update_data(
        edit_teacher_id=teacher_id,
        edit_teacher_old={
            "full_name": full_name,
            "subject_name": subject_name,
            "description": description,
            "photo_path": photo_path,
            "telegram_id": telegram_id,
            "telegram_username": telegram_username,
        },
        edit_teacher_full_name=full_name,
        edit_teacher_subject=subject_name,
        edit_teacher_description=description,
        edit_teacher_photo=photo_path,
        edit_teacher_username=telegram_username,
        edit_teacher_telegram_id=telegram_id,
    )

    await callback.message.answer(
        "Текущая карточка преподавателя:\n"
        f"ФИО: {full_name}\n"
        f"Предмет: {subject_name if subject_name else '-'}\n"
        f"Описание: {'есть' if description else 'нет'}\n"
        f"Фото: {'есть' if photo_path else 'нет'}\n"
        f"Username: @{telegram_username if telegram_username else '-'}\n\n"
        "Введите новое ФИО или '-' чтобы оставить текущее.",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_edit_teacher_full_name)
    await callback.answer()


@router.message(AdminStates.waiting_edit_teacher_full_name)
async def process_edit_teacher_full_name(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text != "-":
        if len(text) < 3:
            await message.answer("Введите корректное ФИО или '-'.")
            return
        await state.update_data(edit_teacher_full_name=text)

    await message.answer("Введите новый предмет или '-' чтобы оставить текущий.")
    await state.set_state(AdminStates.waiting_edit_teacher_subject)


@router.message(AdminStates.waiting_edit_teacher_subject)
async def process_edit_teacher_subject(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text != "-":
        if len(text) < 2:
            await message.answer("Введите корректный предмет или '-'.")
            return
        await state.update_data(edit_teacher_subject=text)

    await message.answer(
        "Введите новое описание, '-' чтобы оставить текущее, или 'очистить' чтобы убрать описание."
    )
    await state.set_state(AdminStates.waiting_edit_teacher_description)


@router.message(AdminStates.waiting_edit_teacher_description)
async def process_edit_teacher_description(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if text.lower() == "очистить":
        await state.update_data(edit_teacher_description=None)
    elif text != "-":
        await state.update_data(edit_teacher_description=text)

    await message.answer(
        "Отправьте новое фото карточки.\n"
        "Отправьте '-' чтобы оставить текущее фото, или 'очистить' чтобы убрать фото."
    )
    await state.set_state(AdminStates.waiting_edit_teacher_photo)


@router.message(AdminStates.waiting_edit_teacher_photo)
async def process_edit_teacher_photo(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    if message.photo:
        try:
            photo_path = await save_teacher_photo(message)
        except Exception as exc:
            logger.exception("Failed to save edited teacher photo locally: %s", exc)
            await message.answer("Не удалось сохранить фото. Попробуйте отправить изображение еще раз.")
            return
        await state.update_data(edit_teacher_photo=photo_path)
    else:
        text = message.text.strip()
        if text.lower() == "очистить":
            await state.update_data(edit_teacher_photo=None)
        elif text != "-":
            await message.answer("Отправьте фото, '-' или 'очистить'.")
            return

    await message.answer(
        "Введите новый @username преподавателя, '-' чтобы оставить текущий, или 'очистить' чтобы убрать."
    )
    await state.set_state(AdminStates.waiting_edit_teacher_username)


@router.message(AdminStates.waiting_edit_teacher_username)
async def process_edit_teacher_username(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    data = await state.get_data()
    username_text = message.text.strip()

    current_username = data.get("edit_teacher_username")
    if username_text.lower() == "очистить":
        final_username = None
    elif username_text == "-":
        final_username = current_username
    else:
        if not is_valid_username(username_text):
            await message.answer("Введите корректный @username, '-' или 'очистить'.")
            return
        final_username = normalize_telegram_username(username_text)

    old = data.get("edit_teacher_old", {})
    teacher_id = data.get("edit_teacher_id")
    full_name = data.get("edit_teacher_full_name")
    subject_name = data.get("edit_teacher_subject")
    description = data.get("edit_teacher_description")
    photo_path = data.get("edit_teacher_photo")
    old_telegram_id = old.get("telegram_id")

    telegram_id = get_known_telegram_user_id_by_username(final_username)
    if telegram_id is None and final_username == old.get("telegram_username"):
        telegram_id = old_telegram_id

    updated = update_teacher_profile_fields(
        teacher_id,
        full_name=full_name,
        subject_name=subject_name,
        description=description,
        photo_path=photo_path,
    )
    if updated:
        set_teacher_telegram_id(teacher_id, telegram_id)

    onboarding_text = ""
    if final_username and telegram_id is None:
        token = create_onboarding_invite(
            role="teacher",
            full_name=full_name,
            telegram_username=final_username,
            entity_type="teacher",
            entity_id=teacher_id,
            created_by=message.from_user.id,
        )
        link = build_onboarding_link(token)
        if link:
            onboarding_text = (
                "\n\nПреподаватель еще не писал школьному боту.\n"
                "Отправьте ему ссылку для автоматической привязки:\n"
                f"{link}"
            )

    if telegram_id:
        add_user(
            telegram_id=telegram_id,
            full_name=full_name,
            role="teacher",
            telegram_username=final_username,
        )

    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="edit_teacher_profile",
        target_type="teacher",
        target_id=telegram_id,
        details={
            "before": old,
            "after": {
                "full_name": full_name,
                "subject_name": subject_name,
                "description": description,
                "photo_path": photo_path,
                "telegram_id": telegram_id,
                "telegram_username": final_username,
            },
        },
        status="success",
    )

    await state.clear()
    await message.answer(
        "Карточка преподавателя обновлена.\n"
        f"ФИО: {full_name}\n"
        f"Предмет: {subject_name}\n"
        f"Описание: {'есть' if description else 'нет'}\n"
        f"Фото: {'есть' if photo_path else 'нет'}\n"
        f"Username: @{final_username if final_username else '-'}\n"
        f"Telegram ID: {telegram_id if telegram_id else '-'}"
        f"{onboarding_text}",
        reply_markup=get_superadmin_menu(),
    )


@router.callback_query(lambda c: c.data == "superadmin_add_teacher")
async def superadmin_add_teacher(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.answer(
        "Введите ФИО преподавателя.\n"
        "Подсказка: можно нажать «Главное меню» для выхода.",
        reply_markup=get_main_menu_shortcut_keyboard(),
    )
    await state.set_state(AdminStates.waiting_new_teacher_full_name)
    await callback.answer()


@router.message(AdminStates.waiting_new_teacher_full_name)
async def process_new_teacher_full_name(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    full_name = (message.text or "").strip()
    if len(full_name) < 3:
        await message.answer("Введите корректное ФИО преподавателя.")
        return

    await state.update_data(new_teacher_full_name=full_name)
    subjects = [item for item in get_teacher_catalog_subjects() if item]
    if subjects:
        await state.update_data(new_teacher_subject_options=subjects, new_teacher_subject_custom=False)
        await message.answer(
            "Выберите предмет из списка или нажмите «Добавить новый предмет»:",
            reply_markup=get_teacher_subject_picker_keyboard(subjects),
        )
    else:
        await state.update_data(new_teacher_subject_options=[], new_teacher_subject_custom=True)
        await message.answer("Введите новый предмет для преподавателя:")
    await state.set_state(AdminStates.waiting_new_teacher_subject)


@router.callback_query(
    AdminStates.waiting_new_teacher_subject,
    lambda c: c.data.startswith("new_teacher_subject_pick_") or c.data == "new_teacher_subject_add_new",
)
async def process_new_teacher_subject_pick(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    subjects = data.get("new_teacher_subject_options") or []

    if callback.data == "new_teacher_subject_add_new":
        await state.update_data(new_teacher_subject_custom=True)
        await callback.message.answer("Введите новый предмет текстом:")
        await callback.answer()
        return

    try:
        subject_index = int(callback.data.split("_")[-1])
    except (TypeError, ValueError):
        await callback.answer("Не удалось определить предмет", show_alert=True)
        return

    if subject_index < 0 or subject_index >= len(subjects):
        await callback.answer("Предмет не найден", show_alert=True)
        return

    subject_name = subjects[subject_index]
    await state.update_data(new_teacher_subject=subject_name, new_teacher_subject_custom=False)
    await callback.message.answer("Введите описание преподавателя или отправьте '-' чтобы пропустить:")
    await state.set_state(AdminStates.waiting_new_teacher_description)
    await callback.answer()


@router.message(AdminStates.waiting_new_teacher_subject)
async def process_new_teacher_subject(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    subject_name = (message.text or "").strip()
    if len(subject_name) < 2:
        await message.answer("Введите корректное название предмета.")
        return

    data = await state.get_data()
    subject_options = data.get("new_teacher_subject_options") or []
    normalized_lookup = {
        option.strip().lower(): option
        for option in subject_options
        if option and option.strip()
    }
    subject_name = normalized_lookup.get(subject_name.lower(), subject_name)

    await state.update_data(new_teacher_subject=subject_name)
    await message.answer("Введите описание преподавателя или отправьте '-' чтобы пропустить:")
    await state.set_state(AdminStates.waiting_new_teacher_description)


@router.message(AdminStates.waiting_new_teacher_description)
async def process_new_teacher_description(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = (message.text or "").strip()
    description = None if text in {"-", "пропустить", "skip"} else text
    await state.update_data(new_teacher_description=description)
    await message.answer(
        "Отправьте фото карточки преподавателя или отправьте '-' чтобы пропустить.\n"
        "Можно использовать и новое фото, и текущую локальную картинку позже."
    )
    await state.set_state(AdminStates.waiting_new_teacher_photo)


@router.message(AdminStates.waiting_new_teacher_photo)
async def process_new_teacher_photo(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    photo_path = None
    if message.photo:
        try:
            photo_path = await save_teacher_photo(message)
        except Exception as exc:
            logger.exception("Failed to save new teacher photo locally: %s", exc)
            await message.answer("Не удалось сохранить фото. Попробуйте отправить изображение еще раз.")
            return
    else:
        text = (message.text or "").strip()
        if text not in {"-", "пропустить", "skip"}:
            await message.answer("Отправьте фото или '-' для пропуска.")
            return

    await state.update_data(new_teacher_photo=photo_path)
    await message.answer("Теперь укажите @username преподавателя (обязательно):")
    await state.set_state(AdminStates.waiting_new_teacher_username)


@router.message(AdminStates.waiting_new_teacher_username)
async def process_new_teacher_username(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not is_valid_username(text):
        await message.answer("Введите корректный @username в формате @example_user")
        return
    normalized_username = normalize_telegram_username(text)
    telegram_id = get_known_telegram_user_id_by_username(normalized_username)

    data = await state.get_data()
    teacher_name = data.get("new_teacher_full_name")
    subject_name = data.get("new_teacher_subject")
    description = data.get("new_teacher_description")
    photo_path = data.get("new_teacher_photo")

    if not teacher_name or not subject_name:
        await message.answer("Не удалось завершить создание преподавателя. Повторите снова.")
        await state.clear()
        return

    teacher_id = add_or_update_teacher_profile(
        full_name=teacher_name,
        subject_name=subject_name,
        telegram_id=telegram_id,
        description=description,
        photo_path=photo_path,
    )
    onboarding_text = ""
    if telegram_id:
        add_user(
            telegram_id=telegram_id,
            full_name=teacher_name,
            role="teacher",
            telegram_username=normalized_username,
        )
    else:
        token = create_onboarding_invite(
            role="teacher",
            full_name=teacher_name,
            telegram_username=normalized_username or "",
            entity_type="teacher",
            entity_id=teacher_id,
            created_by=message.from_user.id,
        )
        link = build_onboarding_link(token)
        if link:
            onboarding_text = (
                "\n\nПреподаватель еще не писал школьному боту.\n"
                "Отправьте ему ссылку для автоматической привязки роли teacher:\n"
                f"{link}"
            )
        else:
            onboarding_text = (
                "\n\nПреподаватель еще не писал школьному боту, но ссылка не сформирована "
                "(проверьте SCHOOL_BOT_USERNAME в .env)."
            )

    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_teacher",
        target_type="teacher",
        target_id=telegram_id,
        details={
            "before": None,
            "after": {
                "teacher_name": teacher_name,
                "subject_name": subject_name,
                "has_description": bool(description),
                "has_photo": bool(photo_path),
                "telegram_id": telegram_id,
                "telegram_username": normalized_username,
            },
        },
        status="success",
    )

    await message.answer(
        "✅ Преподаватель добавлен.\n\n"
        f"ФИО: {teacher_name}\n"
        f"Предмет: {subject_name}\n"
        f"Описание: {'добавлено' if description else 'пока нет'}\n"
        f"Фото карточки: {'добавлено' if photo_path else 'пока нет'}\n"
        f"Username: @{normalized_username}\n"
        f"Telegram ID: {telegram_id if telegram_id else 'будет определен автоматически'}"
        f"{onboarding_text}",
        reply_markup=get_superadmin_menu()
    )
    await state.clear()


@router.callback_query(lambda c: c.data == "superadmin_list_admins")
async def superadmin_list_admins(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    admins = get_users_by_role("admin")

    if not admins:
        await callback.message.answer("Админов пока нет.")
        await callback.answer()
        return

    lines = ["<b>Список админов:</b>\n"]
    for user in admins:
        _, telegram_id, full_name, role, is_active = user
        lines.append(f"• {full_name} — <code>{telegram_id}</code>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "superadmin_list_teachers")
async def superadmin_list_teachers(callback: CallbackQuery):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    teachers = get_users_by_role("teacher")

    if not teachers:
        await callback.message.answer("Учителей пока нет.")
        await callback.answer()
        return

    lines = ["<b>Список учителей:</b>\n"]
    for user in teachers:
        _, telegram_id, full_name, role, is_active = user
        lines.append(f"• {full_name} — <code>{telegram_id}</code>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "student_profile")
async def student_profile(callback: CallbackQuery):
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, telegram_id, full_name, role, is_active = user

    if role != "student" or not is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    student = get_student_by_telegram_id(callback.from_user.id)
    if not student:
        await callback.message.answer(
            "Профиль ученика пока не найден в базе.\n"
            "Обратись к администратору."
        )
        await callback.answer()
        return

    student_id, student_name, student_telegram_id, phone = student
    admin_contacts = get_active_admin_contacts()
    admin_links_text = ""
    if admin_contacts:
        admin_links = [
            (
                f"• <a href=\"https://t.me/{username}\">{full_name}</a>"
                if username
                else f"• <a href=\"tg://user?id={telegram_id}\">{full_name}</a>"
            )
            for telegram_id, full_name, username in admin_contacts
        ]
        admin_links_text = "\n\n<b>Напишите администратору:</b>\n" + "\n".join(admin_links)

    await callback.message.answer(
        f"👤 <b>Мой профиль</b>\n\n"
        f"📝 <b>Имя:</b> {student_name}\n"
        f"📱 <b>Телефон:</b> {phone if phone else '-'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{student_telegram_id if student_telegram_id else '-'}</code>"
        f"{admin_links_text}",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "student_payment_history")
async def student_payment_history(callback: CallbackQuery):
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, _, _, role, is_active = user

    if role != "student" or not is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    student = get_student_by_telegram_id(callback.from_user.id)
    if not student:
        await callback.message.answer(
            "Профиль ученика пока не найден в базе.\n"
            "Пожалуйста, обратитесь к администратору."
        )
        await callback.answer()
        return

    _, student_name, _, _ = student
    payments = get_recent_payment_history_by_telegram_user(callback.from_user.id, limit=4)

    lines = [f"💳 <b>История оплат</b>\n\n👤 <b>{student_name}</b>\n"]

    if not payments:
        lines.append("\nИстория оплат пока отсутствует.")
    else:
        status_map = {
            "pending": "Ожидает проверки",
            "processing": "На проверке",
            "approved": "Подтверждена",
            "rejected": "Отклонена",
        }
        for index, payment in enumerate(payments, start=1):
            payment_id, status, caption_text, created_at, _updated_at, lessons_added = payment
            lines.append(
                f"\n{index}. Оплата #{payment_id}\n"
                f"Статус: <b>{status_map.get(status, status)}</b>\n"
                f"Дата: {created_at}\n"
                f"Начислено занятий: <b>{lessons_added}</b>\n"
                f"Комментарий: {caption_text if caption_text else '-'}"
            )

    await callback.message.answer("".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "student_directions")
async def student_directions(callback: CallbackQuery):
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, telegram_id, full_name, role, is_active = user

    if role != "student" or not is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    student = get_student_by_telegram_id(callback.from_user.id)
    if not student:
        await callback.message.answer(
            "Профиль ученика пока не найден в базе.\n"
            "Обратись к администратору."
        )
        await callback.answer()
        return

    student_id, student_name, student_telegram_id, phone = student
    directions = get_student_directions(student_id)

    if not directions:
        await callback.message.answer("У тебя пока нет активных направлений.")
        await callback.answer()
        return

    lines = [f"📚 <b>Мои направления</b>\n\n👤 <b>{student_name}</b>\n"]

    total_lessons = sum(direction[3] for direction in directions)
    lines.append(f"\n<b>Всего занятий на балансе:</b> {total_lessons}\n")

    for direction in directions:
        direction_id, teacher_name, subject_name, lesson_balance, tariff_type = direction
        tariff_text = "Разовое" if tariff_type == "single" else "Пакет"

        lines.append(
            f"\n<b>{subject_name}</b>\n"
            f"👨‍🏫 Преподаватель: {teacher_name}\n"
            f"🧾 Тариф: {tariff_text}\n"
            f"🔢 Остаток занятий: {lesson_balance}"
        )

    await callback.message.answer("".join(lines), parse_mode="HTML")
    await callback.answer()
    return

    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Введите минимум 2 символа для поиска преподавателя.")
        return

    teachers = search_teacher_profiles(query, limit=20)
    if not teachers:
        await message.answer(
            "Преподаватели не найдены. Попробуйте другой запрос (часть ФИО или @username)."
        )
        return

    await message.answer(
        "Выберите преподавателя из найденных:",
        reply_markup=get_teacher_selection_keyboard(teachers, action_prefix="assign_teacher_pick"),
    )
    await state.set_state(AdminStates.waiting_teacher_selection)
    return
