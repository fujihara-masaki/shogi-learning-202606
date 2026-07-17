import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "next-move.db")
    from app.main import app

    with TestClient(app) as c:
        yield c
    os.environ.pop("SHOGI_DB_PATH", None)
    os.environ.pop("NEXT_MOVE_DB_PATH", None)
