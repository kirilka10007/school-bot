from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_superadmin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить админа", callback_data="superadmin_add_admin")],
            [InlineKeyboardButton(text="Добавить учителя", callback_data="superadmin_add_teacher")],
            [InlineKeyboardButton(text="Привязать Telegram преподавателя", callback_data="admin_bind_teacher_telegram")],
            [InlineKeyboardButton(text="Список админов", callback_data="superadmin_list_admins")],
            [InlineKeyboardButton(text="Список учителей", callback_data="superadmin_list_teachers")],
            [InlineKeyboardButton(text="Добавить ученика", callback_data="admin_add_student")],
            [InlineKeyboardButton(text="Назначить предмет/препода", callback_data="admin_assign_lesson")],
            [InlineKeyboardButton(text="Найти ученика", callback_data="admin_find_student")],
            [InlineKeyboardButton(text="Начислить занятия", callback_data="admin_add_balance")],
            [InlineKeyboardButton(text="Посещаемость", callback_data="admin_attendance")],
            [InlineKeyboardButton(text="История баланса", callback_data="admin_balance_history")],
            [InlineKeyboardButton(text="Журнал действий", callback_data="admin_actions_recent")],
        ]
    )


def get_admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить ученика", callback_data="admin_add_student")],
            [InlineKeyboardButton(text="Назначить предмет/препода", callback_data="admin_assign_lesson")],
            [InlineKeyboardButton(text="Привязать Telegram преподавателя", callback_data="admin_bind_teacher_telegram")],
            [InlineKeyboardButton(text="Найти ученика", callback_data="admin_find_student")],
            [InlineKeyboardButton(text="Начислить занятия", callback_data="admin_add_balance")],
            [InlineKeyboardButton(text="Посещаемость", callback_data="admin_attendance")],
            [InlineKeyboardButton(text="История баланса", callback_data="admin_balance_history")],
            [InlineKeyboardButton(text="Журнал действий", callback_data="admin_actions_recent")],
        ]
    )


def get_teacher_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мои ученики", callback_data="teacher_students")],
            [InlineKeyboardButton(text="Отметить посещение", callback_data="teacher_attendance")],
        ]
    )


def get_student_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мой профиль", callback_data="student_profile")],
            [InlineKeyboardButton(text="Мои направления", callback_data="student_directions")],
        ]
    )


def get_tariff_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Разовое", callback_data="tariff_single")],
            [InlineKeyboardButton(text="Пакет", callback_data="tariff_package")]
        ]
    )


def get_attendance_direction_keyboard(directions):
    buttons = []

    for direction in directions:
        direction_id, teacher_name, subject_name, lesson_balance, tariff_type = direction
        buttons.append([
            InlineKeyboardButton(
                text=f"{subject_name} — {teacher_name} (остаток: {lesson_balance})",
                callback_data=f"attendance_direction_{direction_id}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_attendance_mark_keyboard(direction_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Был", callback_data=f"attendance_present_{direction_id}")],
            [InlineKeyboardButton(text="Не был", callback_data=f"attendance_absent_{direction_id}")]
        ]
    )


def get_balance_direction_keyboard(directions):
    buttons = []

    for direction in directions:
        direction_id, teacher_name, subject_name, lesson_balance, tariff_type = direction
        buttons.append([
            InlineKeyboardButton(
                text=f"{subject_name} — {teacher_name} (остаток: {lesson_balance})",
                callback_data=f"balance_direction_{direction_id}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_balance_add_keyboard(direction_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="+1", callback_data=f"balance_add_{direction_id}_1")],
            [InlineKeyboardButton(text="+4", callback_data=f"balance_add_{direction_id}_4")],
            [InlineKeyboardButton(text="+8", callback_data=f"balance_add_{direction_id}_8")],
            [InlineKeyboardButton(text="+12", callback_data=f"balance_add_{direction_id}_12")]
        ]
    )


def get_teacher_bind_keyboard(teacher_names: list[str]):
    buttons = []

    for idx, teacher_name in enumerate(teacher_names):
        buttons.append(
            [InlineKeyboardButton(text=teacher_name, callback_data=f"bind_teacher_choose_{idx}")]
        )

    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="admin_bind_teacher_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
