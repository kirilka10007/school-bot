def test_application_flow_creates_student_and_direction(db):
    student_id = db.add_student(
        full_name="Ivan Ivanov",
        telegram_id=10001,
        phone="+79990001122",
    )
    teacher_id = db.add_teacher_if_not_exists(
        full_name="Darya Petrova",
        telegram_id=20001,
    )
    db.add_student_lesson(
        student_id=student_id,
        teacher_id=teacher_id,
        subject_name="Mathematics",
        lesson_balance=8,
        tariff_type="package",
    )

    student = db.get_student_by_telegram_id(10001)
    assert student is not None
    assert student[1] == "Ivan Ivanov"

    directions = db.get_student_directions(student_id)
    assert len(directions) == 1

    direction = directions[0]
    assert direction[2] == "Mathematics"
    assert direction[3] == 8
    assert direction[4] == "package"
