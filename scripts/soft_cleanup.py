import os
from datetime import datetime, timedelta
from pathlib import Path

from shared.database import (
    get_connection,
    init_db,
    normalize_telegram_username,
    resolve_student_teacher_telegram_conflicts,
)


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def run_soft_cleanup() -> dict:
    init_db()
    role_conflicts_result = resolve_student_teacher_telegram_conflicts()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("BEGIN")

    now = datetime.now()
    unused_invite_ttl_days = int(os.getenv("SOFT_CLEANUP_UNUSED_INVITE_DAYS", "14"))
    used_invite_ttl_days = int(os.getenv("SOFT_CLEANUP_USED_INVITE_DAYS", "7"))
    unknown_user_ttl_days = int(os.getenv("SOFT_CLEANUP_UNKNOWN_USER_DAYS", "30"))

    deleted_unused_invites = 0
    deleted_used_invites = 0
    deleted_duplicate_pending_invites = 0
    deleted_unknown_known_users = 0
    normalized_usernames_users = 0
    normalized_usernames_students = 0
    normalized_usernames_known = 0
    backfilled_known_users = 0

    cur.execute("SELECT id, created_at, used_at FROM onboarding_invites")
    invite_rows = cur.fetchall()
    for invite_id, created_at, used_at in invite_rows:
        created_dt = _parse_dt(created_at)
        used_dt = _parse_dt(used_at)
        if used_dt and now - used_dt > timedelta(days=used_invite_ttl_days):
            cur.execute("DELETE FROM onboarding_invites WHERE id = ?", (invite_id,))
            deleted_used_invites += cur.rowcount
            continue
        if not used_dt and created_dt and now - created_dt > timedelta(days=unused_invite_ttl_days):
            cur.execute("DELETE FROM onboarding_invites WHERE id = ?", (invite_id,))
            deleted_unused_invites += cur.rowcount

    # Keep only the latest pending invite per target to prevent onboarding duplicates.
    cur.execute(
        """
        SELECT
            id,
            role,
            telegram_username,
            COALESCE(entity_type, ''),
            COALESCE(entity_id, -1)
        FROM onboarding_invites
        WHERE used_by_telegram_id IS NULL
        ORDER BY id DESC
        """
    )
    seen_pending_keys: set[tuple[str, str, str, int]] = set()
    for invite_id, role, telegram_username, entity_type_key, entity_id_key in cur.fetchall():
        key = (
            str(role or ""),
            str(telegram_username or ""),
            str(entity_type_key or ""),
            int(entity_id_key if entity_id_key is not None else -1),
        )
        if key in seen_pending_keys:
            cur.execute("DELETE FROM onboarding_invites WHERE id = ?", (invite_id,))
            deleted_duplicate_pending_invites += cur.rowcount
            continue
        seen_pending_keys.add(key)

    cur.execute("SELECT telegram_id, telegram_username, full_name, last_seen_at FROM known_telegram_users")
    known_rows = cur.fetchall()
    for telegram_id, telegram_username, full_name, last_seen_at in known_rows:
        normalized = normalize_telegram_username(telegram_username)
        last_seen_dt = _parse_dt(last_seen_at)
        if normalized != telegram_username:
            cur.execute(
                """
                UPDATE known_telegram_users
                SET telegram_username = ?
                WHERE telegram_id = ?
                """,
                (normalized, telegram_id),
            )
            normalized_usernames_known += cur.rowcount

        if not normalized and last_seen_dt and now - last_seen_dt > timedelta(days=unknown_user_ttl_days):
            cur.execute("DELETE FROM known_telegram_users WHERE telegram_id = ?", (telegram_id,))
            deleted_unknown_known_users += cur.rowcount

    cur.execute("SELECT id, telegram_username FROM users")
    for user_id, telegram_username in cur.fetchall():
        normalized = normalize_telegram_username(telegram_username)
        if normalized != telegram_username:
            cur.execute(
                "UPDATE users SET telegram_username = ? WHERE id = ?",
                (normalized, user_id),
            )
            normalized_usernames_users += cur.rowcount

    cur.execute("SELECT id, telegram_username FROM students")
    for student_id, telegram_username in cur.fetchall():
        normalized = normalize_telegram_username(telegram_username)
        if normalized != telegram_username:
            cur.execute(
                "UPDATE students SET telegram_username = ? WHERE id = ?",
                (normalized, student_id),
            )
            normalized_usernames_students += cur.rowcount

    cur.execute(
        """
        SELECT telegram_id, telegram_username, full_name
        FROM users
        WHERE telegram_id IS NOT NULL
        """
    )
    for telegram_id, telegram_username, full_name in cur.fetchall():
        normalized = normalize_telegram_username(telegram_username)
        cur.execute(
            """
            INSERT INTO known_telegram_users (telegram_id, telegram_username, full_name, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_username = COALESCE(excluded.telegram_username, known_telegram_users.telegram_username),
                full_name = COALESCE(excluded.full_name, known_telegram_users.full_name)
            """,
            (telegram_id, normalized, full_name, now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        backfilled_known_users += 1

    conn.commit()
    conn.close()

    return {
        "deleted_unused_invites": deleted_unused_invites,
        "deleted_used_invites": deleted_used_invites,
        "deleted_duplicate_pending_invites": deleted_duplicate_pending_invites,
        "deleted_unknown_known_users": deleted_unknown_known_users,
        "normalized_usernames_users": normalized_usernames_users,
        "normalized_usernames_students": normalized_usernames_students,
        "normalized_usernames_known": normalized_usernames_known,
        "backfilled_known_users": backfilled_known_users,
        "conflicted_telegram_ids": role_conflicts_result["conflicted_telegram_ids"],
        "detached_from_students": role_conflicts_result["detached_from_students"],
        "detached_from_teachers": role_conflicts_result["detached_from_teachers"],
    }


def main() -> None:
    _load_env()
    result = run_soft_cleanup()
    print("SOFT_CLEANUP_OK")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
