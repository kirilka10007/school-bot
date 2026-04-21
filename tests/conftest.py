import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from shared import database


@pytest.fixture()
def db(tmp_path, monkeypatch):
    test_db_path = tmp_path / "school_system_test.db"
    monkeypatch.setattr(database, "DB_PATH", test_db_path)
    database.init_db()
    return database
