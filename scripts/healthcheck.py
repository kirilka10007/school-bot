import argparse
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shared.database import DB_PATH


REQUIRED_TABLES = {
    "students",
    "users",
    "teachers",
    "student_lessons",
    "attendance",
    "balance_history",
    "payment_requests",
    "admin_actions",
}


def run_healthcheck() -> tuple[bool, str]:
    if not DB_PATH.exists():
        return False, f"DB not found: {DB_PATH}"

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        conn.close()
    except Exception as exc:
        return False, f"DB connection failed: {exc}"

    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        return False, f"Missing tables: {', '.join(missing)}"

    return True, "OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="School system healthcheck")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only final status line",
    )
    args = parser.parse_args()

    ok, msg = run_healthcheck()
    status = "HEALTHCHECK_OK" if ok else "HEALTHCHECK_FAIL"
    if args.quiet:
        print(status)
    else:
        print(f"{status}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
