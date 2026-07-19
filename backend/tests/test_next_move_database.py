import os
import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.database import get_connection
from app.importers.yaneuraou_book import import_book
from app.learning_samples import build_learning_sample_plan
from app.next_move_identity import get_dataset_version

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

@pytest.mark.parametrize("column", ["imported_at", "file_name"])
def test_missing_book_source_api_column_returns_503(client, column):
    seed_next_move()
    conn = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
    try:
        conn.execute(f"ALTER TABLE book_sources DROP COLUMN {column}")
        conn.commit()
    finally:
        conn.close()
    response = client.get("/api/book/sources")
    assert response.status_code == 503
    assert "book_sources" in response.json()["detail"]
    assert column in response.json()["detail"]

def test_licenses_combine_main_and_next_move_databases(client):
    seed_next_move()
    response = client.get("/api/licenses")
    assert response.status_code == 200
    assert response.json()["book_sources"][0]["name"] == "Test fixture"

def test_validator_checks_expected_learning_sample_count(client):
    seed_next_move()
    script = Path(__file__).parents[1] / "scripts" / "validate_next_move_db.py"
    path = os.environ["NEXT_MOVE_DB_PATH"]
    before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    success = subprocess.run(
        [sys.executable, str(script), path, "--expected-learning-samples", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    mismatch = subprocess.run(
        [sys.executable, str(script), path, "--expected-learning-samples", "10000"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert success.returncode == 0
    assert mismatch.returncode == 1
    assert "expected 10000, actual 1" in mismatch.stdout
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == before


def _make_legacy(source: Path, target: Path):
    shutil.copy2(source, target)
    conn = sqlite3.connect(target)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("ALTER TABLE learning_samples RENAME TO learning_samples_new")
    conn.execute("""CREATE TABLE learning_samples (
      id INTEGER PRIMARY KEY AUTOINCREMENT, book_source_id INTEGER NOT NULL, book_position_id INTEGER NOT NULL,
      opening_key TEXT NOT NULL, opening_name TEXT NOT NULL, sfen TEXT NOT NULL, sample_rank INTEGER NOT NULL,
      sample_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(book_source_id,book_position_id))""")
    conn.execute("""INSERT INTO learning_samples(id,book_source_id,book_position_id,opening_key,opening_name,sfen,sample_rank,sample_reason,created_at)
      SELECT id,book_source_id,book_position_id,opening_key,opening_name,sfen,sample_rank,sample_reason,created_at FROM learning_samples_new""")
    conn.execute("DROP TABLE learning_samples_new")
    conn.execute("DROP TABLE extraction_runs")
    conn.execute("DROP TABLE database_metadata")
    conn.commit(); conn.close()


def test_validator_distinguishes_legacy_new_and_incomplete_without_writes(client, tmp_path):
    seed_next_move()
    script = Path(__file__).parents[1] / "scripts" / "validate_next_move_db.py"
    new_path = Path(os.environ["NEXT_MOVE_DB_PATH"])
    legacy = tmp_path / "legacy.db"
    _make_legacy(new_path, legacy)
    partial = tmp_path / "partial.db"
    shutil.copy2(new_path, partial)
    conn = sqlite3.connect(partial); conn.execute("DROP TABLE database_metadata"); conn.commit(); conn.close()
    for path, expected_code, marker in [(new_path, 0, "schema=new"), (legacy, 0, "legacy schema"),
                                        (partial, 1, "incomplete extraction metadata schema")]:
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
        assert result.returncode == expected_code
        assert marker in result.stdout
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_legacy_dataset_version_falls_back_to_file_sha256(client, tmp_path):
    seed_next_move()
    legacy = tmp_path / "legacy-version.db"
    _make_legacy(Path(os.environ["NEXT_MOVE_DB_PATH"]), legacy)
    conn = sqlite3.connect(f"file:{legacy.resolve().as_posix()}?mode=ro", uri=True)
    try:
        expected = "v1:sha256-file:" + hashlib.sha256(legacy.read_bytes()).hexdigest()
        assert get_dataset_version(conn, legacy) == expected
    finally: conn.close()
