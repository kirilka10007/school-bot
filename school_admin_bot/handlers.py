from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram import Router
from aiogram.fsm.context import FSMContext
import importlib.util
from pathlib import Path

from config import SUPERADMINS
from keyboards import (
    get_superadmin_menu,
    get_admin_menu,
    get_teacher_menu,
    get_student_menu,
    get_tariff_keyboard,
    get_attendance_direction_keyboard,
    get_attendance_mark_keyboard,
    get_balance_direction_keyboard,
    get_balance_add_keyboard,
    get_teacher_bind_keyboard
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
    get_student_by_telegram_id,
    bind_teacher_telegram_id,
    log_admin_action,
    get_recent_admin_actions,
)

router = Router()


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


def get_admin_reply_menu(user_id: int):
    return get_superadmin_menu() if user_id in SUPERADMINS else get_admin_menu()


def load_teacher_names_for_binding() -> list[str]:
    data_path = Path(__file__).resolve().parent.parent / "school-bot" / "data.py"
    if not data_path.exists():
        return []

    try:
        spec = importlib.util.spec_from_file_location("school_bot_data", data_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        teachers_data = getattr(module, "TEACHERS_DATA", {})
    except Exception:
        return []

    names: list[str] = []
    for subject_teachers in teachers_data.values():
        for teacher in subject_teachers:
            name = teacher.get("name")
            if name and name not in names:
                names.append(name)

    return names


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

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


@router.callback_query(lambda c: c.data == "admin_add_student")
async def admin_add_student(callback: CallbackQuery, state: FSMContext):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Введи ФИО ученика:")
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
        details={"teacher_name": teacher_name, "telegram_id": telegram_id},
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
    await message.answer("Введи Telegram ID ученика или напиши '-' если его нет:")
    await state.set_state(AdminStates.waiting_student_telegram_id)


@router.message(AdminStates.waiting_student_telegram_id)
async def get_student_telegram_id(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()

    if text == "-":
        telegram_id = None
    else:
        if not text.isdigit():
            await message.answer("Telegram ID должен быть числом или напиши '-'")
            return
        telegram_id = int(text)

    await state.update_data(telegram_id=telegram_id)
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

    add_student(
        full_name=data["full_name"],
        telegram_id=data["telegram_id"],
        phone=phone
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_student",
        target_type="student",
        target_id=None,
        details={
            "full_name": data["full_name"],
            "telegram_id": data["telegram_id"],
            "phone": phone,
        },
        status="success",
    )

    if data["telegram_id"]:
        add_user(
            telegram_id=data["telegram_id"],
            full_name=data["full_name"],
            role="student"
        )

    await message.answer(
        "✅ Ученик добавлен.\n\n"
        f"ФИО: {data['full_name']}\n"
        f"Telegram ID: {data['telegram_id'] if data['telegram_id'] else '-'}\n"
        f"Телефон: {phone if phone else '-'}\n"
        f"Роль student: {'создана' if data['telegram_id'] else 'не создана, потому что нет Telegram ID'}",
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

    text_lines = ["Выбери ученика по ID и отправь номер сообщением:\n"]
    for student in students:
        student_id, full_name, telegram_id, phone = student
        text_lines.append(f"{student_id}. {full_name}")

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

    await state.update_data(student_id=student_id)
    await message.answer("Введи имя преподавателя:")
    await state.set_state(AdminStates.waiting_teacher_name)


@router.message(AdminStates.waiting_teacher_name)
async def get_teacher_name(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    await state.update_data(teacher_name=message.text.strip())
    await message.answer("Введи название предмета:")
    await state.set_state(AdminStates.waiting_subject_name)


@router.message(AdminStates.waiting_subject_name)
async def get_subject_name(message: Message, state: FSMContext):
    if not is_admin_role(message.from_user.id):
        await message.answer("Нет доступа.")
        await state.clear()
        return

    await state.update_data(subject_name=message.text.strip())
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

    await callback.message.answer("Введи имя или часть имени ученика для отметки посещения:")
    await state.set_state(AdminStates.waiting_attendance_student_search)
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
        for student in students:
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{student_id}. {full_name}")
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
        f"Остаток: {lesson_balance}\n\n"
        f"Отметь посещение:",
        reply_markup=get_attendance_mark_keyboard(direction_id)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("attendance_present_") or c.data.startswith("attendance_absent_"))
async def mark_student_attendance(callback: CallbackQuery):
    if not is_admin_role(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    if callback.data.startswith("attendance_present_"):
        direction_id = int(callback.data.split("_")[-1])
        status = "present"
    else:
        direction_id = int(callback.data.split("_")[-1])
        status = "absent"

    lesson = get_student_lesson_by_id(direction_id)
    if not lesson:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    _, _, _, subject_name, lesson_balance_before, tariff_type, student_name, teacher_name = lesson

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

    status_text = "Был" if status == "present" else "Не был"

    await callback.message.answer(
        f"✅ Посещаемость отмечена\n\n"
        f"Ученик: {student_name}\n"
        f"Предмет: {subject_name}\n"
        f"Преподаватель: {teacher_name}\n"
        f"Статус: {status_text}\n"
        f"Баланс был: {lesson_balance_before}\n"
        f"Баланс стал: {lesson_balance_after}",
        reply_markup=get_admin_menu()
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
        for student in students:
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{student_id}. {full_name}")
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
        reply_markup=get_admin_menu()
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
        for student in students:
            student_id, full_name, telegram_id, phone = student
            lines.append(f"{student_id}. {full_name}")
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


@router.callback_query(lambda c: c.data == "superadmin_add_admin")
async def superadmin_add_admin(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Отправь Telegram ID нового админа:")
    await state.set_state(AdminStates.waiting_new_admin_id)
    await callback.answer()


@router.message(AdminStates.waiting_new_admin_id)
async def process_new_admin_id(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Telegram ID должен быть числом.")
        return

    telegram_id = int(text)

    add_user(
        telegram_id=telegram_id,
        full_name=f"Admin {telegram_id}",
        role="admin"
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_admin",
        target_type="user",
        target_id=telegram_id,
        details={"role": "admin"},
        status="success",
    )

    await message.answer(
        f"✅ Админ добавлен.\nTelegram ID: {telegram_id}",
        reply_markup=get_superadmin_menu()
    )
    await state.clear()


@router.callback_query(lambda c: c.data == "superadmin_add_teacher")
async def superadmin_add_teacher(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in SUPERADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.answer("Отправь Telegram ID нового учителя:")
    await state.set_state(AdminStates.waiting_new_teacher_id)
    await callback.answer()


@router.message(AdminStates.waiting_new_teacher_id)
async def process_new_teacher_id(message: Message, state: FSMContext):
    if message.from_user.id not in SUPERADMINS:
        await message.answer("Нет доступа.")
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Telegram ID должен быть числом.")
        return

    telegram_id = int(text)
    teacher_name = f"Teacher {telegram_id}"

    add_user(
        telegram_id=telegram_id,
        full_name=teacher_name,
        role="teacher"
    )

    add_teacher_if_not_exists(
        full_name=teacher_name,
        telegram_id=telegram_id
    )
    log_admin_action(
        admin_telegram_id=message.from_user.id,
        action_type="add_teacher",
        target_type="teacher",
        target_id=telegram_id,
        details={"teacher_name": teacher_name},
        status="success",
    )

    await message.answer(
        f"✅ Учитель добавлен.\nTelegram ID: {telegram_id}",
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

    await callback.message.answer(
        f"👤 <b>Мой профиль</b>\n\n"
        f"📝 <b>Имя:</b> {student_name}\n"
        f"📱 <b>Телефон:</b> {phone if phone else '-'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{student_telegram_id if student_telegram_id else '-'}</code>",
        parse_mode="HTML"
    )
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
    lines.append(f"\n<b>Total lessons on balance:</b> {total_lessons}\n")

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
