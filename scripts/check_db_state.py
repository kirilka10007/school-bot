import os
from pathlib import Path

def _load_env() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    env_path = root_dir / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()

from shared.database import get_connection, get_db_backend_name


def q(conn, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def main() -> None:
    backend = get_db_backend_name()
    print(f"DB backend: {backend}")
    conn = get_connection()
    if backend == "postgresql":
        info_row = q(
            conn,
            """
            SELECT
                current_database(),
                current_user
            """,
        )
        if info_row:
            db_name, db_user = info_row[0]
            print(f"DB target: database={db_name}; user={db_user}")
    print("")

    tables = [
        "users",
        "students",
        "teachers",
        "student_lessons",
        "attendance",
        "balance_history",
        "payment_requests",
        "admin_actions",
        "onboarding_invites",
        "known_telegram_users",
        "publication_posts",
    ]

    print("\nCOUNTS:")
    for table in tables:
        count = q(conn, f"SELECT COUNT(1) FROM {table}")[0][0]
        print(f"- {table}: {count}")

    print("\nUSERS:")
    for row in q(
        conn,
        """
        SELECT id, telegram_id, full_name, role, is_active, telegram_username
        FROM users
        ORDER BY id
        """,
    ):
        print(row)

    print("\nPENDING ADMIN INVITES:")
    for row in q(
        conn,
        """
        SELECT id, token, role, full_name, telegram_username, created_at, used_by_telegram_id
        FROM onboarding_invites
        WHERE role = 'admin'
        ORDER BY id DESC
        LIMIT 20
        """,
    ):
        print(row)

    print("\nKNOWN USERS WITHOUT USERNAME (top 30):")
    for row in q(
        conn,
        """
        SELECT telegram_id, full_name, last_seen_at
        FROM known_telegram_users
        WHERE telegram_username IS NULL OR TRIM(telegram_username) = ''
        ORDER BY last_seen_at DESC
        LIMIT 30
        """,
    ):
        print(row)

    print("\nSTUDENT/TEACHER TELEGRAM CONFLICTS:")
    for row in q(
        conn,
        """
        SELECT
            s.telegram_id,
            s.full_name AS student_name,
            t.full_name AS teacher_name
        FROM students s
        JOIN teachers t ON t.telegram_id = s.telegram_id
        WHERE s.telegram_id IS NOT NULL
        ORDER BY s.telegram_id
        """,
    ):
        print(row)

    print("\nPUBLICATIONS (latest 20):")
    for row in q(
        conn,
        """
        SELECT id, status, scheduled_for, sent_at, last_error
        FROM publication_posts
        ORDER BY id DESC
        LIMIT 20
        """,
    ):
        print(row)

    conn.close()


if __name__ == "__main__":
    main()
