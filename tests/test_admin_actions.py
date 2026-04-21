import json


def test_admin_action_written_to_journal(db):
    db.log_admin_action(
        admin_telegram_id=777001,
        action_type="assign_lesson",
        target_type="student_lesson",
        target_id=123,
        details={"student_id": 1, "subject": "Physics"},
        status="success",
    )

    rows = db.get_recent_admin_actions(limit=10)
    assert len(rows) == 1

    action = rows[0]
    assert action[1] == 777001
    assert action[2] == "assign_lesson"
    assert action[3] == "student_lesson"
    assert action[4] == 123
    assert action[6] == "success"

    details = json.loads(action[5])
    assert details["student_id"] == 1
    assert details["subject"] == "Physics"


def test_reset_student_data_for_testing_preserves_teachers_and_selected_superadmin(db):
    teacher_id = db.add_teacher_if_not_exists("Elena Smirnova", telegram_id=50001)
    student_id = db.add_student(
        full_name="Ivan Ivanov",
        telegram_id=60001,
        phone="+79990000001",
    )
    db.add_student_lesson(
        student_id=student_id,
        teacher_id=teacher_id,
        subject_name="Mathematics",
        lesson_balance=5,
        tariff_type="package",
    )
    direction_id = db.get_student_directions(student_id)[0][0]
    db.add_balance_history(
        student_lesson_id=direction_id,
        operation_type="topup",
        lessons_delta=5,
        comment="Test topup",
        created_by=70001,
    )
    db.create_payment_request(
        telegram_user_id=60001,
        telegram_username="@ivan",
        telegram_full_name="Ivan Ivanov",
        caption_text="Test payment",
        file_id="file-1",
        file_type="photo",
    )
    db.add_user(telegram_id=90001, full_name="Main Superadmin", role="superadmin")
    db.add_user(telegram_id=90002, full_name="Old Superadmin", role="superadmin")
    db.add_user(telegram_id=91001, full_name="Admin User", role="admin")
    db.add_user(telegram_id=92001, full_name="Student User", role="student")
    db.add_user(telegram_id=93001, full_name="Teacher User", role="teacher")
    db.log_admin_action(
        admin_telegram_id=90001,
        action_type="create_student",
        target_type="student",
        target_id=student_id,
        details={"student_id": student_id},
    )

    db.reset_student_data_for_testing(preserve_superadmin_ids=[90001])

    assert db.get_all_students() == []
    assert db.get_student_directions(student_id) == []
    assert db.get_recent_admin_actions(limit=10) == []
    assert db.get_users_by_role("admin") == []
    assert db.get_users_by_role("student") == []

    teacher = db.get_teacher_by_telegram_id(50001)
    assert teacher is not None
    assert teacher[0] == teacher_id
    assert teacher[2] == "Elena Smirnova"

    teacher_users = db.get_users_by_role("teacher")
    assert len(teacher_users) == 1
    assert teacher_users[0][1] == 93001

    superadmins = db.get_users_by_role("superadmin")
    assert len(superadmins) == 1
    assert superadmins[0][1] == 90001
