def test_payment_finalize_is_idempotent(db):
    student_id = db.add_student(
        full_name="Petr Petrov",
        telegram_id=10002,
        phone="+79990002233",
    )
    teacher_id = db.add_teacher_if_not_exists("Ekaterina Smirnova", telegram_id=20002)
    db.add_student_lesson(
        student_id=student_id,
        teacher_id=teacher_id,
        subject_name="Social Studies",
        lesson_balance=2,
        tariff_type="single",
    )
    direction_id = db.get_student_directions(student_id)[0][0]

    payment_request_id = db.create_payment_request(
        telegram_user_id=10002,
        telegram_username="@petrov",
        telegram_full_name="Petr Petrov",
        caption_text="payment for lessons",
        file_id="fake-file-id",
        file_type="photo",
    )

    transitioned = db.try_transition_payment_request_status(
        payment_request_id=payment_request_id,
        allowed_from_statuses=["pending"],
        new_status="processing",
        admin_id=90001,
    )
    assert transitioned is True

    finalized_first = db.finalize_payment_with_topup(
        payment_request_id=payment_request_id,
        direction_id=direction_id,
        lessons_count=4,
        admin_id=90001,
        comment="Test approval",
    )
    assert finalized_first is True

    finalized_second = db.finalize_payment_with_topup(
        payment_request_id=payment_request_id,
        direction_id=direction_id,
        lessons_count=4,
        admin_id=90001,
        comment="Retry",
    )
    assert finalized_second is False

    updated_direction = db.get_student_lesson_by_id(direction_id)
    assert updated_direction is not None
    assert updated_direction[4] == 6

    payment = db.get_payment_request_by_id(payment_request_id)
    assert payment is not None
    assert payment[7] == "approved"
