import os
from pathlib import Path

from shared.database import init_db, reset_system_data_keep_current_teachers


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


def _parse_superadmins(raw: str) -> list[int]:
    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


def main() -> None:
    _load_env()
    init_db()
    superadmins = _parse_superadmins(os.getenv("SCHOOL_ADMIN_SUPERADMINS", ""))
    result = reset_system_data_keep_current_teachers(preserve_superadmin_ids=superadmins)

    print("RESET_KEEP_TEACHERS_OK")
    print(f"Superadmins preserved: {result['superadmins_preserved']}")
    print(f"Teachers kept: {result['teachers_kept']}")


if __name__ == "__main__":
    main()
