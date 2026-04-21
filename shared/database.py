import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = (BASE_DIR / "school_system.db").resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        telegram_id INTEGER,
        phone TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        full_name TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        teacher_id INTEGER NOT NULL,
        subject_name TEXT NOT NULL,
        lesson_balance INTEGER NOT NULL DEFAULT 0,
        tariff_type TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(teacher_id) REFERENCES teachers(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_lesson_id INTEGER NOT NULL,
        lesson_date TEXT NOT NULL,
        status TEXT NOT NULL,
        written_off INTEGER NOT NULL DEFAULT 0,
        marked_by INTEGER,
        FOREIGN KEY(student_lesson_id) REFERENCES student_lessons(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS balance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_lesson_id INTEGER NOT NULL,
        operation_type TEXT NOT NULL,
        lessons_delta INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        FOREIGN KEY(student_lesson_id) REFERENCES student_lessons(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_user_id INTEGER,
        telegram_username TEXT,
        telegram_full_name TEXT,
        caption_text TEXT,
        file_id TEXT,
        file_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        approved_by INTEGER,
        rejected_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT
    )
    """)

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_telegram_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            details TEXT,
            status TEXT NOT NULL DEFAULT 'success',
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_runs (
            task_name TEXT PRIMARY KEY,
            executed_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def reset_student_data_for_testing(preserve_superadmin_ids: list[int] | tuple[int, ...] | None = None):
    preserve_superadmin_ids = tuple(preserve_superadmin_ids or [])
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("BEGIN")

    cur.execute(
        """
        DELETE FROM attendance
        WHERE student_lesson_id IN (SELECT id FROM student_lessons)
        """
    )
    cur.execute(
        """
        DELETE FROM balance_history
        WHERE student_lesson_id IN (SELECT id FROM student_lessons)
        """
    )
    cur.execute("DELETE FROM student_lessons")
    cur.execute("DELETE FROM payment_requests")
    cur.execute("DELETE FROM admin_actions")
    cur.execute("DELETE FROM students")
    cur.execute("DELETE FROM users WHERE role = 'student'")
    cur.execute("DELETE FROM users WHERE role = 'admin'")

    if preserve_superadmin_ids:
        placeholders = ",".join("?" for _ in preserve_superadmin_ids)
        cur.execute(
            f"""
            DELETE FROM users
            WHERE role = 'superadmin'
              AND telegram_id NOT IN ({placeholders})
            """,
            preserve_superadmin_ids,
        )
    else:
        cur.execute("DELETE FROM users WHERE role = 'superadmin'")

    conn.commit()
    conn.close()


def run_startup_maintenance_from_env(preserve_superadmin_ids: list[int] | tuple[int, ...] | None = None) -> bool:
    if not _is_truthy_env(os.getenv("SCHOOL_RESET_STUDENT_DATA")):
        return False

    task_name = "reset_student_data_for_testing_v1"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM maintenance_runs
        WHERE task_name = ?
        """,
        (task_name,),
    )
    already_executed = cur.fetchone() is not None
    conn.close()

    if already_executed:
        return False

    reset_student_data_for_testing(preserve_superadmin_ids=preserve_superadmin_ids)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO maintenance_runs (task_name, executed_at)
        VALUES (?, ?)
        """,
        (task_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()
    return True


def add_student(full_name: str, telegram_id: int | None, phone: str | None):
    conn = get_connection()
    cur = conn.cursor()

    if telegram_id is not None:
        cur.execute(
            """
            SELECT id
            FROM students
            WHERE telegram_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,)
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE students
                SET full_name = ?, phone = ?
                WHERE id = ?
                """,
                (full_name, phone, existing[0])
            )
            conn.commit()
            conn.close()
            return existing[0]

    cur.execute(
        """
        INSERT INTO students (full_name, telegram_id, phone)
        VALUES (?, ?, ?)
        """,
        (full_name, telegram_id, phone)
    )

    student_id = cur.lastrowid
    conn.commit()
    conn.close()
    return student_id


def get_all_students():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, full_name, telegram_id, phone FROM students ORDER BY id")
    rows = cur.fetchall()

    conn.close()
    return rows


def add_teacher_if_not_exists(full_name: str, telegram_id: int | None = None):
    conn = get_connection()
    cur = conn.cursor()

    if telegram_id is not None:
        cur.execute(
            "SELECT id FROM teachers WHERE telegram_id = ?",
            (telegram_id,)
        )
        row = cur.fetchone()

        if row:
            cur.execute(
                """
                UPDATE teachers
                SET full_name = ?
                WHERE telegram_id = ?
                """,
                (full_name, telegram_id)
            )
            conn.commit()
            conn.close()
            return row[0]

    cur.execute(
        "SELECT id FROM teachers WHERE full_name = ?",
        (full_name,)
    )
    row = cur.fetchone()

    if row:
        conn.close()
        return row[0]

    cur.execute(
        """
        INSERT INTO teachers (telegram_id, full_name)
        VALUES (?, ?)
        """,
        (telegram_id, full_name)
    )

    teacher_id = cur.lastrowid
    conn.commit()
    conn.close()
    return teacher_id


def bind_teacher_telegram_id(full_name: str, telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, full_name
        FROM teachers
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )
    existing_by_telegram = cur.fetchone()

    if existing_by_telegram and existing_by_telegram[1] != full_name:
        conn.close()
        return {
            "ok": False,
            "error": f"Этот Telegram ID уже привязан к преподавателю: {existing_by_telegram[1]}",
        }

    cur.execute(
        """
        SELECT id
        FROM teachers
        WHERE full_name = ?
        """,
        (full_name,)
    )
    existing_by_name = cur.fetchone()

    if existing_by_name:
        cur.execute(
            """
            UPDATE teachers
            SET telegram_id = ?
            WHERE id = ?
            """,
            (telegram_id, existing_by_name[0])
        )
        teacher_id = existing_by_name[0]
        action = "updated"
    else:
        cur.execute(
            """
            INSERT INTO teachers (telegram_id, full_name)
            VALUES (?, ?)
            """,
            (telegram_id, full_name)
        )
        teacher_id = cur.lastrowid
        action = "created"

    conn.commit()
    conn.close()
    return {"ok": True, "teacher_id": teacher_id, "action": action}


def get_teacher_by_telegram_id(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, telegram_id, full_name
        FROM teachers
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )
    row = cur.fetchone()

    conn.close()
    return row


def add_student_lesson(student_id: int, teacher_id: int, subject_name: str, lesson_balance: int, tariff_type: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO student_lessons (student_id, teacher_id, subject_name, lesson_balance, tariff_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (student_id, teacher_id, subject_name, lesson_balance, tariff_type)
    )

    conn.commit()
    conn.close()


def find_students_by_name(search_text: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, full_name, telegram_id, phone
        FROM students
        WHERE full_name LIKE ?
        ORDER BY full_name
        """,
        (f"%{search_text}%",)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def find_teacher_students_by_name(teacher_telegram_id: int, search_text: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT DISTINCT
            s.id,
            s.full_name,
            s.telegram_id,
            s.phone
        FROM student_lessons sl
        JOIN students s ON sl.student_id = s.id
        JOIN teachers t ON sl.teacher_id = t.id
        WHERE t.telegram_id = ?
          AND s.full_name LIKE ?
        ORDER BY s.full_name
        """,
        (teacher_telegram_id, f"%{search_text}%")
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def get_students_by_teacher_telegram_id(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT DISTINCT
            s.id,
            s.full_name,
            s.telegram_id,
            s.phone
        FROM student_lessons sl
        JOIN students s ON sl.student_id = s.id
        JOIN teachers t ON sl.teacher_id = t.id
        WHERE t.telegram_id = ?
        ORDER BY s.full_name
        """,
        (telegram_id,)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def get_student_directions(student_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT sl.id, t.full_name, sl.subject_name, sl.lesson_balance, sl.tariff_type
        FROM student_lessons sl
        JOIN teachers t ON sl.teacher_id = t.id
        WHERE sl.student_id = ?
        ORDER BY sl.id
        """,
        (student_id,)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def get_student_lesson_by_id(direction_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT sl.id, sl.student_id, sl.teacher_id, sl.subject_name, sl.lesson_balance, sl.tariff_type,
               s.full_name, t.full_name
        FROM student_lessons sl
        JOIN students s ON sl.student_id = s.id
        JOIN teachers t ON sl.teacher_id = t.id
        WHERE sl.id = ?
        """,
        (direction_id,)
    )
    row = cur.fetchone()

    conn.close()
    return row


def add_balance_history(student_lesson_id: int, operation_type: str, lessons_delta: int, comment: str | None, created_by: int | None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO balance_history (student_lesson_id, operation_type, lessons_delta, comment, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            student_lesson_id,
            operation_type,
            lessons_delta,
            comment,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            created_by
        )
    )

    conn.commit()
    conn.close()


def get_balance_history_by_student(student_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            bh.id,
            s.full_name,
            t.full_name,
            sl.subject_name,
            bh.operation_type,
            bh.lessons_delta,
            bh.comment,
            bh.created_at,
            bh.created_by
        FROM balance_history bh
        JOIN student_lessons sl ON bh.student_lesson_id = sl.id
        JOIN students s ON sl.student_id = s.id
        JOIN teachers t ON sl.teacher_id = t.id
        WHERE sl.student_id = ?
        ORDER BY bh.id DESC
        """,
        (student_id,)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def mark_attendance(direction_id: int, status: str, marked_by: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO attendance (student_lesson_id, lesson_date, status, written_off, marked_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            direction_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status,
            1 if status == "present" else 0,
            marked_by
        )
    )

    if status == "present":
        cur.execute(
            """
            UPDATE student_lessons
            SET lesson_balance = CASE
                WHEN lesson_balance > 0 THEN lesson_balance - 1
                ELSE 0
            END
            WHERE id = ?
            """,
            (direction_id,)
        )

        cur.execute(
            """
            INSERT INTO balance_history (student_lesson_id, operation_type, lessons_delta, comment, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                direction_id,
                "attendance_writeoff",
                -1,
                "Списание за посещение",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                marked_by
            )
        )

    conn.commit()
    conn.close()


def add_lessons_to_balance(direction_id: int, lessons_count: int, created_by: int | None = None, comment: str | None = None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE student_lessons
        SET lesson_balance = lesson_balance + ?
        WHERE id = ?
        """,
        (lessons_count, direction_id)
    )

    cur.execute(
        """
        INSERT INTO balance_history (student_lesson_id, operation_type, lessons_delta, comment, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            direction_id,
            "manual_topup",
            lessons_count,
            comment or "Начисление занятий",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            created_by
        )
    )

    conn.commit()
    conn.close()


def create_payment_request(
    telegram_user_id: int | None,
    telegram_username: str | None,
    telegram_full_name: str | None,
    caption_text: str | None,
    file_id: str,
    file_type: str
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO payment_requests (
            telegram_user_id,
            telegram_username,
            telegram_full_name,
            caption_text,
            file_id,
            file_type,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (
            telegram_user_id,
            telegram_username,
            telegram_full_name,
            caption_text,
            file_id,
            file_type,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    payment_request_id = cur.lastrowid
    conn.commit()
    conn.close()
    return payment_request_id


def get_payment_request_by_id(payment_request_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, telegram_user_id, telegram_username, telegram_full_name,
               caption_text, file_id, file_type, status, approved_by,
               rejected_by, created_at, updated_at
        FROM payment_requests
        WHERE id = ?
        """,
        (payment_request_id,)
    )
    row = cur.fetchone()

    conn.close()
    return row


def get_recent_payment_history_by_telegram_user(telegram_user_id: int, limit: int = 4):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            pr.id,
            pr.status,
            pr.caption_text,
            pr.created_at,
            pr.updated_at,
            COALESCE(
                (
                    SELECT SUM(bh.lessons_delta)
                    FROM balance_history bh
                    WHERE bh.operation_type = 'manual_topup'
                      AND bh.comment LIKE '%' || '#' || pr.id || '%'
                ),
                0
            ) AS lessons_added
        FROM payment_requests pr
        WHERE pr.telegram_user_id = ?
        ORDER BY pr.id DESC
        LIMIT ?
        """,
        (telegram_user_id, limit),
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def update_payment_request_status(payment_request_id: int, status: str, admin_id: int | None = None):
    conn = get_connection()
    cur = conn.cursor()

    approved_by = admin_id if status == "approved" else None
    rejected_by = admin_id if status == "rejected" else None

    cur.execute(
        """
        UPDATE payment_requests
        SET status = ?,
            approved_by = COALESCE(?, approved_by),
            rejected_by = COALESCE(?, rejected_by),
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            approved_by,
            rejected_by,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            payment_request_id
        )
    )

    conn.commit()
    conn.close()


def try_transition_payment_request_status(
    payment_request_id: int,
    allowed_from_statuses: list[str],
    new_status: str,
    admin_id: int | None = None
) -> bool:
    if not allowed_from_statuses:
        return False

    conn = get_connection()
    cur = conn.cursor()

    approved_by = admin_id if new_status == "approved" else None
    rejected_by = admin_id if new_status == "rejected" else None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    placeholders = ", ".join("?" for _ in allowed_from_statuses)
    params = [
        new_status,
        approved_by,
        rejected_by,
        now,
        payment_request_id,
        *allowed_from_statuses,
    ]

    cur.execute(
        f"""
        UPDATE payment_requests
        SET status = ?,
            approved_by = COALESCE(?, approved_by),
            rejected_by = COALESCE(?, rejected_by),
            updated_at = ?
        WHERE id = ?
          AND status IN ({placeholders})
        """,
        params
    )

    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def finalize_payment_with_topup(
    payment_request_id: int,
    direction_id: int,
    lessons_count: int,
    admin_id: int,
    comment: str | None = None
) -> bool:
    if lessons_count <= 0:
        return False

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("BEGIN IMMEDIATE")

        cur.execute(
            """
            SELECT status
            FROM payment_requests
            WHERE id = ?
            """,
            (payment_request_id,)
        )
        payment_row = cur.fetchone()
        if not payment_row:
            conn.rollback()
            return False

        current_status = payment_row[0]
        if current_status != "processing":
            conn.rollback()
            return False

        cur.execute(
            """
            UPDATE student_lessons
            SET lesson_balance = lesson_balance + ?
            WHERE id = ?
            """,
            (lessons_count, direction_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO balance_history (student_lesson_id, operation_type, lessons_delta, comment, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                direction_id,
                "manual_topup",
                lessons_count,
                comment or f"Начисление после подтверждения оплаты #{payment_request_id}",
                now,
                admin_id
            )
        )

        cur.execute(
            """
            UPDATE payment_requests
            SET status = 'approved',
                approved_by = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'processing'
            """,
            (admin_id, now, payment_request_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def find_students_by_telegram_id(telegram_user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, full_name, telegram_id, phone
        FROM students
        WHERE telegram_id = ?
        ORDER BY id DESC
        """,
        (telegram_user_id,)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def add_user(telegram_id: int, full_name: str, role: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (telegram_id, full_name, role, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            full_name = excluded.full_name,
            role = excluded.role,
            is_active = 1
        """,
        (
            telegram_id,
            full_name,
            role,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()
    conn.close()


def log_admin_action(
    admin_telegram_id: int,
    action_type: str,
    target_type: str | None = None,
    target_id: int | None = None,
    details: str | dict | None = None,
    status: str = "success",
):
    conn = get_connection()
    cur = conn.cursor()

    details_value: str | None
    if isinstance(details, dict):
        details_value = json.dumps(details, ensure_ascii=False)
    elif details is None:
        details_value = None
    else:
        details_value = str(details)

    cur.execute(
        """
        INSERT INTO admin_actions (
            admin_telegram_id, action_type, target_type, target_id, details, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_telegram_id,
            action_type,
            target_type,
            target_id,
            details_value,
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    conn.commit()
    conn.close()


def get_recent_admin_actions(limit: int = 50):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, admin_telegram_id, action_type, target_type, target_id, details, status, created_at
        FROM admin_actions
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def get_user_by_telegram_id(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, telegram_id, full_name, role, is_active
        FROM users
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )
    row = cur.fetchone()

    conn.close()
    return row


def get_users_by_role(role: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, telegram_id, full_name, role, is_active
        FROM users
        WHERE role = ?
        ORDER BY full_name
        """,
        (role,)
    )
    rows = cur.fetchall()

    conn.close()
    return rows


def get_student_by_telegram_id(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, full_name, telegram_id, phone
        FROM students
        WHERE telegram_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (telegram_id,)
    )
    row = cur.fetchone()

    conn.close()
    return row
