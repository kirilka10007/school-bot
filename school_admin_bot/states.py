from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    waiting_student_name = State()
    waiting_student_telegram_id = State()
    waiting_student_phone = State()

    choosing_student_for_lesson = State()
    waiting_teacher_name = State()
    waiting_subject_name = State()
    waiting_tariff_type = State()
    waiting_lesson_balance = State()

    waiting_student_search = State()
    waiting_attendance_student_search = State()
    waiting_balance_student_search = State()
    waiting_history_student_search = State()

    waiting_new_admin_id = State()
    waiting_new_teacher_id = State()
    waiting_bind_teacher_telegram_id = State()
