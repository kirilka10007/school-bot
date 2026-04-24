import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def _load_env() -> None:
    env_path = ROOT_DIR / ".env"
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

from shared.database import cleanup_orphan_teacher_subjects, get_connection


def _connect():
    return get_connection()


def list_teachers() -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, full_name, telegram_id
        FROM teachers
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No teachers found.")
        return 0

    print("Teachers:")
    for teacher_id, full_name, telegram_id in rows:
        print(f"- id={teacher_id}; name={full_name}; telegram_id={telegram_id}")
    return 0


def _resolve_teacher_ids(cur, teacher_id: int | None, teacher_name: str | None) -> list[int]:
    if teacher_id is not None:
        cur.execute("SELECT id FROM teachers WHERE id = ?", (teacher_id,))
        row = cur.fetchone()
        return [row[0]] if row else []

    if teacher_name:
        cur.execute("SELECT id FROM teachers WHERE full_name = ?", (teacher_name,))
        rows = cur.fetchall()
        return [r[0] for r in rows]

    return []


def delete_teacher(teacher_id: int | None, teacher_name: str | None) -> int:
    conn = _connect()
    cur = conn.cursor()

    teacher_ids = _resolve_teacher_ids(cur, teacher_id, teacher_name)
    if not teacher_ids:
        conn.close()
        print("Teacher not found.")
        return 1

    cur.execute("BEGIN")
    deleted_teachers = 0
    deleted_lessons = 0
    deleted_attendance = 0
    deleted_balance_history = 0
    deleted_teacher_users = 0

    for t_id in teacher_ids:
        cur.execute("SELECT telegram_id FROM teachers WHERE id = ?", (t_id,))
        teacher_row = cur.fetchone()
        teacher_telegram_id = teacher_row[0] if teacher_row else None

        cur.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (t_id,))

        cur.execute("SELECT id FROM student_lessons WHERE teacher_id = ?", (t_id,))
        lesson_ids = [r[0] for r in cur.fetchall()]

        for lesson_id in lesson_ids:
            cur.execute("DELETE FROM attendance WHERE student_lesson_id = ?", (lesson_id,))
            deleted_attendance += cur.rowcount

            cur.execute("DELETE FROM balance_history WHERE student_lesson_id = ?", (lesson_id,))
            deleted_balance_history += cur.rowcount

        cur.execute("DELETE FROM student_lessons WHERE teacher_id = ?", (t_id,))
        deleted_lessons += cur.rowcount

        if teacher_telegram_id is not None:
            cur.execute(
                "DELETE FROM users WHERE telegram_id = ? AND role = 'teacher'",
                (teacher_telegram_id,),
            )
            deleted_teacher_users += cur.rowcount

        cur.execute("DELETE FROM teachers WHERE id = ?", (t_id,))
        deleted_teachers += cur.rowcount

    conn.commit()
    conn.close()

    print("Delete completed:")
    print(f"- teachers: {deleted_teachers}")
    print(f"- teacher users: {deleted_teacher_users}")
    print(f"- lessons: {deleted_lessons}")
    print(f"- attendance records: {deleted_attendance}")
    print(f"- balance_history records: {deleted_balance_history}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DB admin helper")
    subparsers = parser.add_subparsers(dest="entity", required=True)

    teachers_parser = subparsers.add_parser("teachers", help="Teacher operations")
    teachers_sub = teachers_parser.add_subparsers(dest="action", required=True)

    teachers_sub.add_parser("list", help="List teachers")

    delete_parser = teachers_sub.add_parser("delete", help="Delete teacher by id or exact name")
    delete_parser.add_argument("--id", type=int, default=None)
    delete_parser.add_argument("--name", type=str, default=None)

    subjects_parser = subparsers.add_parser("subjects", help="Subject operations")
    subjects_sub = subjects_parser.add_subparsers(dest="action", required=True)
    subjects_sub.add_parser("cleanup-orphans", help="Delete subjects not linked to current teacher subject")

    publication_parser = subparsers.add_parser("publications", help="Publication operations")
    publication_sub = publication_parser.add_subparsers(dest="action", required=True)

    publication_sub.add_parser("list", help="List latest publications")

    publication_requeue = publication_sub.add_parser("requeue", help="Requeue failed publications")
    publication_requeue.add_argument("--id", type=int, default=None)
    publication_requeue.add_argument("--all-failed", action="store_true")

    args = parser.parse_args()

    if args.entity == "teachers" and args.action == "list":
        return list_teachers()

    if args.entity == "teachers" and args.action == "delete":
        if args.id is None and not args.name:
            print("Provide --id or --name")
            return 1
        return delete_teacher(args.id, args.name)

    if args.entity == "subjects" and args.action == "cleanup-orphans":
        result = cleanup_orphan_teacher_subjects()
        print("Subjects cleanup completed:")
        print(f"- before_total: {result['before_total']}")
        print(f"- deleted_invalid: {result['deleted_invalid']}")
        print(f"- deleted_not_linked: {result['deleted_not_linked']}")
        print(f"- after_total: {result['after_total']}")
        return 0

    if args.entity == "publications" and args.action == "list":
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status, scheduled_for, sent_at, last_error
            FROM publication_posts
            ORDER BY id DESC
            LIMIT 50
            """
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            print("No publications found.")
            return 0
        for row in rows:
            print(row)
        return 0

    if args.entity == "publications" and args.action == "requeue":
        conn = _connect()
        cur = conn.cursor()
        if args.all_failed:
            cur.execute(
                """
                UPDATE publication_posts
                SET status = 'scheduled',
                    last_error = NULL
                WHERE status = 'failed'
                """
            )
            changed = cur.rowcount
        elif args.id is not None:
            cur.execute(
                """
                UPDATE publication_posts
                SET status = 'scheduled',
                    last_error = NULL
                WHERE id = ?
                """,
                (args.id,),
            )
            changed = cur.rowcount
        else:
            conn.close()
            print("Provide --id <post_id> or --all-failed")
            return 1
        conn.commit()
        conn.close()
        print(f"Requeued posts: {changed}")
        return 0

    print("Unknown command.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
