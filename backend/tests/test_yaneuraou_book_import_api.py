import os
from pathlib import Path

from app.next_move_database import get_next_move_write_connection as get_connection, init_next_move_db as init_db
from app.importers.yaneuraou_book import import_book
from app.learning_samples import build_learning_sample_plan

FIXTURE = Path(__file__).parent / "fixtures" / "yaneuraou_book_sample.db"
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy."


def count_rows(table: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_does_not_write_db(tmp_path):
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "dry.db")
    init_db()
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT, dry_run=True)
    assert result.dry_run is True
    assert result.positions_read == 4
    assert result.moves_read == 6
    assert result.duplicate_positions == 1
    assert count_rows("book_sources") == 0


def test_limit_imports_small_subset_and_registers_source(tmp_path):
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "limit.db")
    result = import_book(FIXTURE, name="sample", version="test", license_name="MIT License", license_text=MIT, limit=2)
    assert result.imported_positions == 2
    assert result.imported_moves == 4
    assert count_rows("book_sources") == 1
    assert count_rows("book_positions") == 2
    assert count_rows("book_moves") == 4


def test_duplicate_sfen_is_counted_without_breaking_import(tmp_path):
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "dup.db")
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT)
    assert result.duplicate_positions == 1
    assert result.invalid_lines == 1
    assert result.imported_positions == 4


def test_book_source_and_license_api(client):
    result = import_book(FIXTURE, name="Sample YaneuraOu Book", version="fixture", source_url="https://example.test/book", license_name="MIT License", license_text=MIT, limit=1)
    build_learning_sample_plan(result.source_id, limit=1, per_opening_limit=1, seed=1, dry_run=False)
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
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "lowercase.db")
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT)
    assert result.imported_positions == 4
    conn = get_connection()
    try:
        row = conn.execute("SELECT sfen FROM book_positions WHERE sfen LIKE ?", ("% rb2p 4",)).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_book_candidates_api_returns_moves_with_source_info(client):
    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    result = import_book(
        FIXTURE,
        name="Sample YaneuraOu Book",
        version="fixture",
        source_url="https://example.test/book",
        license_name="MIT License",
        license_text=MIT,
        limit=1,
    )
    build_learning_sample_plan(result.source_id, limit=1, per_opening_limit=1, seed=1, dry_run=False)

    response = client.get("/api/book/candidates", params={"sfen": sfen})

    assert response.status_code == 200
    body = response.json()
    assert body["sfen"] == sfen
    assert body["found"] is True
    assert [candidate["move_usi"] for candidate in body["candidates"]] == ["7g7f", "2g2f"]
    assert body["candidates"][0]["rank"] == 1
    assert body["candidates"][0]["score"] == 30
    assert body["candidates"][0]["depth"] == 1
    assert body["candidates"][0]["source_name"] == "Sample YaneuraOu Book"
    assert body["candidates"][0]["license"] == "MIT License"
    assert body["candidates"][0]["license_name"] == "MIT License"
    assert body["candidates"][0]["source_url"] == "https://example.test/book"


def test_book_candidates_api_returns_not_found_for_unknown_sfen(client):
    result = import_book(FIXTURE, name="sample", license_name="MIT License", license_text=MIT, limit=1)
    build_learning_sample_plan(result.source_id, limit=1, per_opening_limit=1, seed=1, dry_run=False)
    sfen = "9/9/9/9/9/9/9/9/9 b - 1"

    response = client.get("/api/book/candidates", params={"sfen": sfen})

    assert response.status_code == 200
    assert response.json() == {"sfen": sfen, "found": False, "candidates": []}


def test_book_candidates_api_rejects_blank_sfen(client):
    response = client.get("/api/book/candidates", params={"sfen": "   "})

    assert response.status_code == 422


def test_book_candidates_api_allows_null_sort_order(client):
    init_db()
    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    conn = get_connection()
    try:
        conn.execute("DROP TABLE book_moves")
        conn.execute(
            """
            CREATE TABLE book_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL REFERENCES book_positions(id) ON DELETE CASCADE,
                usi TEXT NOT NULL,
                score INTEGER,
                depth INTEGER,
                pv TEXT NOT NULL DEFAULT '',
                raw TEXT NOT NULL DEFAULT '',
                sort_order INTEGER,
                UNIQUE(position_id, usi, sort_order)
            )
            """
        )
        source_id = conn.execute(
            """
            INSERT INTO book_sources(name, source_url, license_name)
            VALUES (?, ?, ?)
            """,
            ("Legacy Nullable Sort Book", "https://example.test/legacy", "CC0"),
        ).lastrowid
        position_id = conn.execute(
            "INSERT INTO book_positions(source_id, sfen) VALUES (?, ?)",
            (source_id, sfen),
        ).lastrowid
        conn.execute(
            "INSERT INTO book_moves(position_id, usi, score, depth, sort_order) VALUES (?, ?, ?, ?, ?)",
            (position_id, "7g7f", 30, 1, 0),
        )
        conn.execute(
            "INSERT INTO book_moves(position_id, usi, score, depth, sort_order) VALUES (?, ?, ?, ?, ?)",
            (position_id, "2g2f", 10, 1, None),
        )
        conn.execute("INSERT INTO learning_samples(book_source_id, book_position_id, sfen, sample_rank) VALUES (?, ?, ?, 1)", (source_id, position_id, sfen))
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/book/candidates", params={"sfen": sfen})

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert [candidate["move_usi"] for candidate in body["candidates"]] == ["7g7f", "2g2f"]
    assert [candidate["rank"] for candidate in body["candidates"]] == [1, None]
