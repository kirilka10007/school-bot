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
