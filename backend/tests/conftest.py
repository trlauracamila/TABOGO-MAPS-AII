import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    import main
    database.init_db()
    return TestClient(main.app)
