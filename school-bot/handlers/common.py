import re
from pathlib import Path

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from data import TEACHERS_DATA, load_reviews_from_folder
from keyboards import (
    get_main_menu_keyboard,
    get_review_card_keyboard,
    get_teacher_card_keyboard,
)
from states import ApplicationForm

BOT_DIR = Path(__file__).resolve().parent.parent


def is_valid_telegram_username(text: str) -> bool:
    return bool(re.fullmatch(r"@[A-Za-z0-9_]{5,32}", text.strip()))


def is_valid_phone(text: str) -> bool:
    cleaned = re.sub(r"[^\d+]", "", text.strip())

    if cleaned.startswith("+"):
        digits = cleaned[1:]
        return digits.isdigit() and 10 <= len(digits) <= 15

    return cleaned.isdigit() and 10 <= len(cleaned) <= 15


def resolve_local_path(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((BOT_DIR / path).resolve())


def format_tariff_type(tariff_type: str) -> str:
    return "Разовое занятие" if tariff_type == "single" else "Пакет занятий"


def format_payment_status(status: str) -> str:
    return {
        "pending": "Ожидает проверки",
        "processing": "На проверке",
        "approved": "Подтверждена",
        "rejected": "Отклонена",
    }.get(status, status)


def build_application_text(data: dict) -> str:
    teacher_text = data.get("teacher_choice", "Не указано")
    if data.get("teacher_choice") == "Выбрать конкретного":
        teacher_text = f"{data['teacher_name']}"

    subjects = data.get("subjects", [])
    subjects_text = ", ".join(subjects) if subjects else "-"

    return (
        "📌 <b>Новая заявка</b>\n\n"
        f"👤 <b>Кто оставил заявку:</b> {data.get('user_type', '-')}\n"
        f"📝 <b>Имя:</b> {data.get('name', '-')}\n"
        f"🏫 <b>Класс:</b> {data.get('school_class', '-')}\n"
        f"🎯 <b>Цель:</b> {data.get('goal', '-')}\n"
        f"📚 <b>Формат занятий:</b> {data.get('lesson_type', '-')}\n"
        f"📖 <b>Предметы:</b> {subjects_text}\n"
        f"👨‍🏫 <b>Преподаватель:</b> {teacher_text}\n"
        f"📞 <b>Способ связи:</b> {data.get('contact_method', '-')}\n"
        f"🔗 <b>Контакт:</b> {data.get('contact_value', '-')}\n"
        f"💬 <b>Комментарий:</b> {data.get('comment', '-')}"
    )


def build_recent_payments_text(recent_payments: list[tuple]) -> str:
    if not recent_payments:
        return "История оплат пока отсутствует."

    lines = ["<b>Последние оплаты:</b>"]

    for index, payment in enumerate(recent_payments, start=1):
        payment_id, status, caption_text, created_at, _updated_at, lessons_added = payment
        lines.append(
            f"{index}. Оплата #{payment_id}\n"
            f"   Статус: <b>{format_payment_status(status)}</b>\n"
            f"   Дата: {created_at}\n"
            f"   Начислено занятий: <b>{lessons_added}</b>\n"
            f"   Комментарий: {caption_text if caption_text else '-'}"
        )

    return "\n".join(lines)


def build_cabinet_text(
    student_name: str,
    directions: list[tuple],
    recent_payments: list[tuple],
) -> str:
    total_balance = sum(direction[3] for direction in directions)

    lines = [
        "👤 <b>Личный кабинет</b>",
        "",
        f"<b>Ученик:</b> {student_name}",
        f"<b>Всего занятий на балансе:</b> {total_balance}",
        "",
        "📚 <b>Ваши направления:</b>",
    ]

    for index, direction in enumerate(directions, start=1):
        _, teacher_name, subject_name, lesson_balance, tariff_type = direction
        lines.append(
            f"{index}. {subject_name} — {teacher_name}\n"
            f"   Остаток: <b>{lesson_balance}</b> | Тариф: {format_tariff_type(tariff_type)}"
        )

    lines.extend(["", build_recent_payments_text(recent_payments)])
    lines.extend(["", "Если информация отображается некорректно, пожалуйста, обратитесь к администратору."])
    return "\n".join(lines)


def build_multi_students_warning(students_count: int) -> str:
    if students_count <= 1:
        return ""
    return (
        "\n\n⚠️ В базе найдено несколько карточек с этим Telegram ID. "
        "Сейчас отображается самая актуальная запись."
    )


def build_payment_caption(
    payment_request_id: int,
    full_name: str | None,
    username: str | None,
    telegram_user_id: int | None,
    caption_text: str | None,
    status_text: str,
) -> str:
    text = (
        f"💳 <b>Оплата #{payment_request_id}</b>\n\n"
        f"📌 <b>Статус:</b> {status_text}\n"
        f"👤 <b>Имя в Telegram:</b> {full_name if full_name else '-'}\n"
        f"🔗 <b>Username:</b> {username if username else 'не указан'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{telegram_user_id if telegram_user_id else '-'}</code>"
    )

    if caption_text:
        text += f"\n💬 <b>Комментарий:</b> {caption_text}"

    return text


async def show_main_menu(message_obj: Message, state: FSMContext):
    data = await state.get_data()
    user_type = data.get("user_type")

    await state.clear()
    if user_type:
        await state.update_data(user_type=user_type)

    await message_obj.answer(
        "Пожалуйста, выберите нужный раздел:",
        reply_markup=get_main_menu_keyboard(),
    )
    await state.set_state(ApplicationForm.menu)


async def send_teacher_card(
    message_obj: Message, subject: str, index: int, state: FSMContext
):
    teachers = TEACHERS_DATA[subject]
    teacher = teachers[index]

    text = (
        f"Преподаватель: {teacher['name']}\n"
        f"Предмет: {subject}\n\n"
        f"{teacher['description']}"
    )

    await state.update_data(
        selected_teacher_subject=subject,
        selected_teacher_index=index,
    )

    photo_path = resolve_local_path(teacher.get("photo"))
    photo = FSInputFile(photo_path)

    await message_obj.answer_photo(
        photo=photo,
        caption=text,
        reply_markup=get_teacher_card_keyboard(index, len(teachers)),
    )


async def edit_teacher_card(
    callback: CallbackQuery, subject: str, index: int, state: FSMContext
):
    teachers = TEACHERS_DATA[subject]
    teacher = teachers[index]

    text = (
        f"Преподаватель: {teacher['name']}\n"
        f"Предмет: {subject}\n\n"
        f"{teacher['description']}"
    )

    await state.update_data(
        selected_teacher_subject=subject,
        selected_teacher_index=index,
    )

    photo_path = resolve_local_path(teacher.get("photo"))
    photo = FSInputFile(photo_path)

    await callback.message.edit_media(
        media=InputMediaPhoto(media=photo, caption=text),
        reply_markup=get_teacher_card_keyboard(index, len(teachers)),
    )


async def send_review_card(message_obj: Message, index: int, state: FSMContext):
    reviews = load_reviews_from_folder()

    if not reviews:
        await message_obj.answer("Отзывы пока не добавлены.")
        return

    review = reviews[index]
    total = len(reviews)

    caption = f"Отзыв {index + 1} из {total}"
    photo = FSInputFile(resolve_local_path(review["image"]))

    await state.update_data(selected_review_index=index)

    await message_obj.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=get_review_card_keyboard(index, total),
    )


async def edit_review_card(callback: CallbackQuery, index: int, state: FSMContext):
    reviews = load_reviews_from_folder()

    if not reviews:
        await callback.message.answer("Отзывы пока не добавлены.")
        return

    review = reviews[index]
    total = len(reviews)

    caption = f"Отзыв {index + 1} из {total}"
    photo = FSInputFile(resolve_local_path(review["image"]))

    await state.update_data(selected_review_index=index)

    await callback.message.edit_media(
        media={"type": "photo", "media": photo, "caption": caption},
        reply_markup=get_review_card_keyboard(index, total),
    )
