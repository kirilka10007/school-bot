from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from data import TEACHERS_DATA, load_reviews_from_folder
from keyboards import (
    get_main_menu_keyboard,
    get_teacher_subject_keyboard,
    get_user_type_keyboard,
)
from shared.database import (
    find_students_by_telegram_id,
    get_recent_payment_history_by_telegram_user,
    get_student_directions,
)
from states import ApplicationForm

from .common import (
    build_cabinet_text,
    build_multi_students_warning,
    build_recent_payments_text,
    edit_review_card,
    edit_teacher_card,
    send_review_card,
    send_teacher_card,
    show_main_menu,
)

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! Пожалуйста, укажите, кто будет оставлять заявку.",
        reply_markup=get_user_type_keyboard(),
    )
    await state.set_state(ApplicationForm.user_type)


@router.callback_query(
    ApplicationForm.user_type, lambda c: c.data in ["user_student", "user_parent"]
)
async def choose_user_type(callback: CallbackQuery, state: FSMContext):
    user_type_map = {"user_student": "Ученик", "user_parent": "Родитель"}

    await state.update_data(user_type=user_type_map[callback.data])

    await callback.message.answer(
        "Благодарим. Теперь, пожалуйста, выберите раздел:",
        reply_markup=get_main_menu_keyboard(),
    )
    await state.set_state(ApplicationForm.menu)
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, state)
    await callback.answer()


@router.callback_query(ApplicationForm.menu, lambda c: c.data == "menu_teachers")
async def menu_teachers(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Пожалуйста, выберите предмет:",
        reply_markup=get_teacher_subject_keyboard(),
    )
    await state.set_state(ApplicationForm.teacher_subject)
    await callback.answer()


@router.callback_query(ApplicationForm.menu, lambda c: c.data == "menu_reviews")
async def menu_reviews(callback: CallbackQuery, state: FSMContext):
    reviews = load_reviews_from_folder()

    if not reviews:
        await callback.message.answer("Отзывы пока не добавлены.")
        await callback.answer()
        return

    await send_review_card(callback.message, 0, state)
    await state.set_state(ApplicationForm.review_card)
    await callback.answer()


@router.callback_query(ApplicationForm.menu, lambda c: c.data == "menu_cabinet")
async def menu_cabinet(callback: CallbackQuery, state: FSMContext):
    students = find_students_by_telegram_id(callback.from_user.id)

    if not students:
        await callback.message.answer(
            "Мы пока не нашли Вас в базе учеников.\n"
            "Пожалуйста, обратитесь к администратору, чтобы привязать Telegram ID к Вашей карточке."
        )
        await callback.answer()
        return

    student_id, student_name, _, _ = students[0]
    directions = get_student_directions(student_id)
    recent_payments = get_recent_payment_history_by_telegram_user(
        callback.from_user.id,
        limit=4,
    )

    if not directions:
        warning = build_multi_students_warning(len(students))
        await callback.message.answer(
            f"👤 <b>Личный кабинет</b>\n\n"
            f"<b>Ученик:</b> {student_name}\n"
            f"Активные направления пока отсутствуют.\n\n"
            f"{build_recent_payments_text(recent_payments)}{warning}",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    text = build_cabinet_text(student_name, directions, recent_payments)
    text += build_multi_students_warning(len(students))
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(
    ApplicationForm.review_card, lambda c: c.data in ["review_prev", "review_next"]
)
async def navigate_reviews(callback: CallbackQuery, state: FSMContext):
    reviews = load_reviews_from_folder()
    data = await state.get_data()
    index = data["selected_review_index"]

    if callback.data == "review_prev" and index > 0:
        index -= 1
    elif callback.data == "review_next" and index < len(reviews) - 1:
        index += 1

    await edit_review_card(callback, index, state)
    await callback.answer()


@router.callback_query(
    ApplicationForm.teacher_subject, lambda c: c.data.startswith("teacher_subject_")
)
async def choose_teacher_subject(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.split("teacher_subject_", 1)[1]
    teachers = TEACHERS_DATA.get(subject, [])
    if not teachers:
        await callback.answer(
            "По этому предмету преподаватели пока не добавлены.",
            show_alert=True,
        )
        return

    await send_teacher_card(callback.message, subject, 0, state)
    await state.set_state(ApplicationForm.teacher_card)
    await callback.answer()


@router.callback_query(
    ApplicationForm.teacher_card, lambda c: c.data in ["teacher_prev", "teacher_next"]
)
async def navigate_teacher_cards(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    subject = data["selected_teacher_subject"]
    index = data["selected_teacher_index"]

    if callback.data == "teacher_prev" and index > 0:
        index -= 1
    elif callback.data == "teacher_next" and index < len(TEACHERS_DATA[subject]) - 1:
        index += 1

    await edit_teacher_card(callback, subject, index, state)
    await callback.answer()


@router.callback_query(ApplicationForm.teacher_card, lambda c: c.data == "teacher_signup")
async def signup_from_teacher_card(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    subject = data["selected_teacher_subject"]
    index = data["selected_teacher_index"]
    teacher = TEACHERS_DATA[subject][index]
    user_type = data.get("user_type")

    await state.clear()

    if user_type:
        await state.update_data(user_type=user_type)

    await state.update_data(
        from_teacher_card=True,
        subjects=[subject],
        teacher_choice="Выбрать конкретного",
        teacher_name=teacher["name"],
    )

    await callback.message.answer("Пожалуйста, напишите, как к Вам обращаться.")
    await state.set_state(ApplicationForm.name)
    await callback.answer()
