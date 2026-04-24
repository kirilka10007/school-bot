import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
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

from shared.database import get_db_backend_name, get_existing_tables, init_db


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
    try:
        init_db()
        tables = get_existing_tables()
    except Exception as exc:
        return False, f"DB connection failed: {exc}"

    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        return False, f"Missing tables: {', '.join(missing)}"

    return True, f"OK ({get_db_backend_name()})"


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
