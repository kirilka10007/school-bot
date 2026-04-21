from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import PAYMENTS_CHAT_ID
from keyboards import (
    get_payment_check_keyboard,
    get_payment_direction_keyboard,
    get_payment_topup_keyboard,
)
from shared.database import (
    create_payment_request,
    finalize_payment_with_topup,
    find_students_by_telegram_id,
    get_payment_request_by_id,
    get_student_directions,
    get_student_lesson_by_id,
    log_admin_action,
    try_transition_payment_request_status,
)
from states import ApplicationForm

from .common import build_payment_caption, show_main_menu

router = Router()


@router.callback_query(ApplicationForm.menu, lambda c: c.data == "menu_paid")
async def menu_paid(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Отправь, пожалуйста, скрин или фото чека об оплате.\n\n"
        "Если нужно вернуться в меню, нажми /start"
    )
    await state.set_state(ApplicationForm.payment_proof)
    await callback.answer()


@router.message(ApplicationForm.payment_proof)
async def get_payment_proof(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправь именно фото или скрин чека.")
        return

    username = f"@{message.from_user.username}" if message.from_user.username else None
    caption_text = message.caption.strip() if message.caption else None

    largest_photo = message.photo[-1]
    file_id = largest_photo.file_id

    payment_request_id = create_payment_request(
        telegram_user_id=message.from_user.id,
        telegram_username=username,
        telegram_full_name=message.from_user.full_name,
        caption_text=caption_text,
        file_id=file_id,
        file_type="photo",
    )

    payment_text = build_payment_caption(
        payment_request_id=payment_request_id,
        full_name=message.from_user.full_name,
        username=username,
        telegram_user_id=message.from_user.id,
        caption_text=caption_text,
        status_text="⏳ Ожидает проверки",
    )

    await message.bot.send_photo(
        PAYMENTS_CHAT_ID,
        photo=file_id,
        caption=payment_text,
        parse_mode="HTML",
        reply_markup=get_payment_check_keyboard(payment_request_id),
    )

    await message.answer("Спасибо, чек отправлен. Мы проверим оплату и сообщим результат.")
    await show_main_menu(message, state)


@router.callback_query(lambda c: c.data.startswith("payment_reject_"))
async def reject_payment_request(callback: CallbackQuery):
    parts = callback.data.split("_")
    payment_request_id = int(parts[2])

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await callback.answer("Запрос оплаты не найден", show_alert=True)
        return

    (
        _,
        telegram_user_id,
        telegram_username,
        telegram_full_name,
        caption_text,
        _file_id,
        _file_type,
        status,
        _approved_by,
        _rejected_by,
        _created_at,
        _updated_at,
    ) = payment

    if status == "approved":
        await callback.answer("Эта оплата уже подтверждена", show_alert=True)
        return

    if status == "rejected":
        await callback.answer("Эта оплата уже отклонена", show_alert=True)
        return

    transitioned = try_transition_payment_request_status(
        payment_request_id=payment_request_id,
        allowed_from_statuses=["pending", "processing"],
        new_status="rejected",
        admin_id=callback.from_user.id,
    )
    if not transitioned:
        payment_latest = get_payment_request_by_id(payment_request_id)
        latest_status = payment_latest[7] if payment_latest else "unknown"
        await callback.answer(
            f"Эту оплату уже обработали (статус: {latest_status})",
            show_alert=True,
        )
        return

    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="payment_rejected",
        target_type="payment_request",
        target_id=payment_request_id,
        details=f"telegram_user_id={telegram_user_id}",
        status="success",
    )

    rejected_caption = build_payment_caption(
        payment_request_id=payment_request_id,
        full_name=telegram_full_name,
        username=telegram_username,
        telegram_user_id=telegram_user_id,
        caption_text=caption_text,
        status_text="❌ Отклонено",
    )

    try:
        await callback.message.edit_caption(caption=rejected_caption, parse_mode="HTML")
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if telegram_user_id:
        try:
            await callback.bot.send_message(
                telegram_user_id,
                "❌ Ваша оплата пока не подтверждена.\n"
                "Проверьте чек или свяжитесь с администратором.",
            )
        except Exception:
            pass

    await callback.answer("Оплата отклонена")


@router.callback_query(lambda c: c.data.startswith("payment_approve_"))
async def approve_payment_request(callback: CallbackQuery):
    parts = callback.data.split("_")
    payment_request_id = int(parts[2])

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await callback.answer("Запрос оплаты не найден", show_alert=True)
        return

    (
        _,
        telegram_user_id,
        telegram_username,
        telegram_full_name,
        caption_text,
        _file_id,
        _file_type,
        status,
        _approved_by,
        _rejected_by,
        _created_at,
        _updated_at,
    ) = payment

    if status == "approved":
        await callback.answer("Эта оплата уже подтверждена", show_alert=True)
        return

    if status == "rejected":
        await callback.answer("Эта оплата уже отклонена", show_alert=True)
        return

    if not telegram_user_id:
        await callback.message.answer(
            f"⚠️ У оплаты #{payment_request_id} нет Telegram ID.\n"
            "Автоматически найти ученика нельзя."
        )
        await callback.answer()
        return

    students = find_students_by_telegram_id(telegram_user_id)

    if not students:
        await callback.message.answer(
            f"⚠️ Ученик по Telegram ID <code>{telegram_user_id}</code> не найден в базе.\n"
            "Нужно сначала добавить ученика во внутреннем боте.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if len(students) > 1:
        await callback.message.answer(
            f"⚠️ По Telegram ID <code>{telegram_user_id}</code> найдено несколько учеников.\n"
            "Нужно проверить вручную во внутреннем боте.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    student_id, student_name, _, _ = students[0]
    directions = get_student_directions(student_id)

    if not directions:
        await callback.message.answer(
            f"⚠️ У ученика {student_name} пока нет направлений.\n"
            "Сначала добавьте направление и преподавателя для этого ученика во внутреннем боте."
        )
        await callback.answer()
        return

    transitioned = try_transition_payment_request_status(
        payment_request_id=payment_request_id,
        allowed_from_statuses=["pending"],
        new_status="processing",
        admin_id=callback.from_user.id,
    )
    if not transitioned:
        payment_latest = get_payment_request_by_id(payment_request_id)
        latest_status = payment_latest[7] if payment_latest else "unknown"
        await callback.answer(
            f"Эту оплату уже обрабатывают или обработали (статус: {latest_status})",
            show_alert=True,
        )
        return

    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="payment_processing_started",
        target_type="payment_request",
        target_id=payment_request_id,
        details=f"student={student_name}",
        status="success",
    )

    processing_caption = build_payment_caption(
        payment_request_id=payment_request_id,
        full_name=telegram_full_name,
        username=telegram_username,
        telegram_user_id=telegram_user_id,
        caption_text=caption_text,
        status_text="🔄 В обработке",
    )

    try:
        await callback.message.edit_caption(caption=processing_caption, parse_mode="HTML")
    except Exception:
        pass

    if len(directions) == 1:
        direction_id, teacher_name, subject_name, lesson_balance, _ = directions[0]

        await callback.message.answer(
            f"✅ Оплата #{payment_request_id} принята в обработку.\n\n"
            f"Ученик: {student_name}\n"
            f"Направление определено автоматически:\n"
            f"{subject_name} — {teacher_name}\n"
            f"Текущий остаток: {lesson_balance}\n\n"
            "Выберите, сколько занятий начислить:",
            reply_markup=get_payment_topup_keyboard(payment_request_id, direction_id),
        )
        await callback.answer("Направление выбрано автоматически")
        return

    await callback.message.answer(
        f"✅ Оплата #{payment_request_id} принята в обработку.\n\n"
        f"Ученик: {student_name}\n"
        "Выбери направление для начисления:",
        reply_markup=get_payment_direction_keyboard(payment_request_id, directions),
    )

    await callback.answer("Выбери направление")


@router.callback_query(lambda c: c.data.startswith("paydir_"))
async def choose_payment_direction(callback: CallbackQuery):
    parts = callback.data.split("_")
    payment_request_id = int(parts[1])
    direction_id = int(parts[2])

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await callback.answer("Запрос оплаты не найден", show_alert=True)
        return

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance, _, student_name, teacher_name = lesson

    await callback.message.answer(
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Текущий баланс: {lesson_balance}\n\n"
        "Выберите, сколько занятий начислить:",
        reply_markup=get_payment_topup_keyboard(payment_request_id, direction_id),
    )

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("paymanual_"))
async def manual_payment_topup_start(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    payment_request_id = int(parts[1])
    direction_id = int(parts[2])

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await callback.answer("Запрос оплаты не найден", show_alert=True)
        return

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance, _, student_name, teacher_name = lesson

    await state.update_data(
        manual_payment_request_id=payment_request_id, manual_direction_id=direction_id
    )

    await callback.message.answer(
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Текущий баланс: {lesson_balance}\n\n"
        "Введи вручную, сколько занятий начислить:"
    )
    await state.set_state(ApplicationForm.payment_manual_amount)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("payadd_"))
async def add_lessons_after_payment(callback: CallbackQuery):
    parts = callback.data.split("_")
    payment_request_id = int(parts[1])
    direction_id = int(parts[2])
    lessons_to_add = int(parts[3])

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await callback.answer("Запрос оплаты не найден", show_alert=True)
        return

    (
        _,
        telegram_user_id,
        telegram_username,
        telegram_full_name,
        caption_text,
        _file_id,
        _file_type,
        _status,
        _approved_by,
        _rejected_by,
        _created_at,
        _updated_at,
    ) = payment

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance_before, _, student_name, teacher_name = lesson

    finalized = finalize_payment_with_topup(
        payment_request_id=payment_request_id,
        direction_id=direction_id,
        lessons_count=lessons_to_add,
        admin_id=callback.from_user.id,
        comment=f"Начисление после подтверждения оплаты #{payment_request_id}",
    )
    if not finalized:
        payment_latest = get_payment_request_by_id(payment_request_id)
        latest_status = payment_latest[7] if payment_latest else "unknown"
        log_admin_action(
            admin_telegram_id=callback.from_user.id,
            action_type="payment_topup_failed",
            target_type="payment_request",
            target_id=payment_request_id,
            details=f"status={latest_status}",
            status="error",
        )
        await callback.answer(
            f"Начисление не выполнено: оплата уже обработана (статус: {latest_status})",
            show_alert=True,
        )
        return

    log_admin_action(
        admin_telegram_id=callback.from_user.id,
        action_type="payment_topup_success",
        target_type="payment_request",
        target_id=payment_request_id,
        details=f"direction={direction_id};lessons={lessons_to_add}",
        status="success",
    )

    approved_caption = build_payment_caption(
        payment_request_id=payment_request_id,
        full_name=telegram_full_name,
        username=telegram_username,
        telegram_user_id=telegram_user_id,
        caption_text=caption_text,
        status_text=f"✅ Подтверждено, начислено {lessons_to_add} занятий",
    )

    try:
        await callback.message.edit_caption(caption=approved_caption, parse_mode="HTML")
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    updated_lesson = get_student_lesson_by_id(direction_id)
    _, _, _, _, lesson_balance_after, _, _, _ = updated_lesson

    await callback.message.answer(
        f"✅ Оплата #{payment_request_id} подтверждена и обработана\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Баланс был: {lesson_balance_before}\n"
        f"Начислено: {lessons_to_add}\n"
        f"Баланс стал: {lesson_balance_after}"
    )

    if telegram_user_id:
        try:
            await callback.bot.send_message(
                telegram_user_id,
                f"✅ Ваша оплата подтверждена.\n"
                f"На баланс начислено {lessons_to_add} занятий.\n\n"
                f"Предмет: {subject_name}\n"
                f"Преподаватель: {teacher_name}",
            )
        except Exception:
            pass

    await callback.answer("Занятия начислены")


@router.message(ApplicationForm.payment_manual_amount)
async def process_manual_payment_amount(message: Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введи количество занятий числом.")
        return

    lessons_to_add = int(text)
    if lessons_to_add <= 0:
        await message.answer("Количество занятий должно быть больше нуля.")
        return

    data = await state.get_data()
    payment_request_id = data.get("manual_payment_request_id")
    direction_id = data.get("manual_direction_id")

    if not payment_request_id or not direction_id:
        await message.answer("Не удалось получить данные для начисления.")
        await state.clear()
        return

    payment = get_payment_request_by_id(payment_request_id)
    if not payment:
        await message.answer("Запрос оплаты не найден.")
        await state.clear()
        return

    (
        _,
        telegram_user_id,
        telegram_username,
        telegram_full_name,
        caption_text,
        _file_id,
        _file_type,
        _status,
        _approved_by,
        _rejected_by,
        _created_at,
        _updated_at,
    ) = payment

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await message.answer("Направление не найдено.")
        await state.clear()
        return

    _, _, _, subject_name, lesson_balance_before, _, student_name, teacher_name = lesson

    finalized = finalize_payment_with_topup(
        payment_request_id=payment_request_id,
        direction_id=direction_id,
        lessons_count=lessons_to_add,
        admin_id=message.from_user.id,
        comment=f"Начисление после подтверждения оплаты #{payment_request_id} (вручную)",
    )
    if not finalized:
        payment_latest = get_payment_request_by_id(payment_request_id)
        latest_status = payment_latest[7] if payment_latest else "unknown"
        log_admin_action(
            admin_telegram_id=message.from_user.id,
            action_type="payment_manual_topup_failed",
            target_type="payment_request",
            target_id=payment_request_id,
            details=f"status={latest_status}",
            status="error",
        )
        await message.answer(
            f"Не удалось завершить начисление: оплата уже обработана (статус: {latest_status})."
        )
        await state.clear()
        return

    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="payment_manual_topup_success",
        target_type="payment_request",
        target_id=payment_request_id,
        details=f"direction={direction_id};lessons={lessons_to_add}",
        status="success",
    )

    updated_lesson = get_student_lesson_by_id(direction_id)
    _, _, _, _, lesson_balance_after, _, _, _ = updated_lesson

    await message.answer(
        f"✅ Оплата #{payment_request_id} подтверждена и обработана\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Баланс был: {lesson_balance_before}\n"
        f"Начислено: {lessons_to_add}\n"
        f"Баланс стал: {lesson_balance_after}"
    )

    if telegram_user_id:
        try:
            await message.bot.send_message(
                telegram_user_id,
                f"✅ Ваша оплата подтверждена.\n"
                f"На баланс начислено {lessons_to_add} занятий.\n\n"
                f"Предмет: {subject_name}\n"
                f"Преподаватель: {teacher_name}",
            )
        except Exception:
            pass

    await state.clear()
