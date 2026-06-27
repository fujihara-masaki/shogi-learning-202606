import os
from pathlib import Path

from app.database import get_connection, init_db
from app.importers.yaneuraou_book import import_book

FIXTURE = Path(__file__).parent / "fixtures" / "yaneuraou_book_sample.db"
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy."


def count_rows(table: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_does_not_write_db(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "dry.db")
    init_db()
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT, dry_run=True)
    assert result.dry_run is True
    assert result.positions_read == 4
    assert result.moves_read == 6
    assert result.duplicate_positions == 1
    assert count_rows("book_sources") == 0


def test_limit_imports_small_subset_and_registers_source(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "limit.db")
    result = import_book(FIXTURE, name="sample", version="test", license_name="MIT License", license_text=MIT, limit=2)
    assert result.imported_positions == 2
    assert result.imported_moves == 4
    assert count_rows("book_sources") == 1
    assert count_rows("book_positions") == 2
    assert count_rows("book_moves") == 4


def test_duplicate_sfen_is_counted_without_breaking_import(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "dup.db")
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT)
    assert result.duplicate_positions == 1
    assert result.invalid_lines == 1
    assert result.imported_positions == 4


def test_book_source_and_license_api(client):
    import_book(FIXTURE, name="Sample YaneuraOu Book", version="fixture", source_url="https://example.test/book", license_name="MIT License", license_text=MIT, limit=1)
    sources = client.get("/api/book/sources")
    assert sources.status_code == 200
    source = sources.json()[0]
    assert source["name"] == "Sample YaneuraOu Book"
    detail = client.get(f"/api/book/sources/{source['id']}")
    assert detail.status_code == 200
    assert "MIT License" in detail.json()["license_text"]
    licenses = client.get("/api/licenses")
    assert licenses.status_code == 200
    assert licenses.json()["book_sources"][0]["license_name"] == "MIT License"


def test_lowercase_white_hand_sfen_imports(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "lowercase.db")
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT)
    assert result.imported_positions == 4
    conn = get_connection()
    try:
        row = conn.execute("SELECT sfen FROM book_positions WHERE sfen LIKE ?", ("% rb2p 4",)).fetchone()
    finally:
        conn.close()
    assert row is not None
