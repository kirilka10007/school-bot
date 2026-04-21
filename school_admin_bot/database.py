import sqlite3
from datetime import datetime

def get_connection():
    return sqlite3.connect("school_admin_bot.db")

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
    conn.commit()
    conn.close()

def add_student(full_name: str, telegram_id: int | None, phone: str | None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO students (full_name, telegram_id, phone)
        VALUES (?, ?, ?)
        """,
        (full_name, telegram_id, phone)
    )

    conn.commit()
    conn.close()

def add_teacher_if_not_exists(full_name: str, telegram_id: int | None = None):
    conn = get_connection()
    cur = conn.cursor()

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

def get_all_students():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, full_name, telegram_id, phone FROM students ORDER BY id")
    rows = cur.fetchall()

    conn.close()
    return rows
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