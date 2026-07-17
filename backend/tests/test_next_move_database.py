import os
import sqlite3
from pathlib import Path

from app.database import get_connection
from app.importers.yaneuraou_book import import_book
from app.learning_samples import build_learning_sample_plan

FIXTURE = Path(__file__).parent / "fixtures" / "yaneuraou_book_sample.db"

def seed_next_move():
    source = import_book(FIXTURE, name="Test fixture", license_name="MIT", source_url="https://example.test", limit=1)
    build_learning_sample_plan(source.source_id, limit=1, per_opening_limit=1, seed=1, dry_run=False)

def test_main_and_next_move_databases_are_separate(client, tmp_path):
    seed_next_move()
    main = Path(os.environ["SHOGI_DB_PATH"])
    next_move = Path(os.environ["NEXT_MOVE_DB_PATH"])
    assert main != next_move
    conn = get_connection()
    try: assert conn.execute("SELECT COUNT(*) FROM learning_samples").fetchone()[0] == 0
    finally: conn.close()
    assert client.get("/api/learning-samples").json()
    assert client.get("/api/tsume-problems").status_code == 200

def test_missing_next_move_database_returns_503_without_creating_file(client, tmp_path):
    missing = tmp_path / "missing.db"
    os.environ["NEXT_MOVE_DB_PATH"] = str(missing)
    response = client.get("/api/learning-samples")
    assert response.status_code == 503
    assert "存在しません" in response.json()["detail"]
    assert not missing.exists()
    assert client.get("/api/tsume-problems").status_code == 200

def test_missing_required_table_returns_503(client, tmp_path):
    invalid = tmp_path / "invalid.db"
    sqlite3.connect(invalid).execute("CREATE TABLE learning_samples(id INTEGER)").connection.close()
    os.environ["NEXT_MOVE_DB_PATH"] = str(invalid)
    response = client.get("/api/book/sources")
    assert response.status_code == 503
    assert "必須テーブル" in response.json()["detail"]

def test_licenses_combine_main_and_next_move_databases(client):
    seed_next_move()
    response = client.get("/api/licenses")
    assert response.status_code == 200
    assert response.json()["book_sources"][0]["name"] == "Test fixture"
