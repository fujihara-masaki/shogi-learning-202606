import os
import sqlite3

from app.database import init_db


OLD_TSUME_SCHEMA = """
CREATE TABLE tsume_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    initial_sfen TEXT NOT NULL,
    mate_length INTEGER NOT NULL,
    solution_moves TEXT NOT NULL,
    opponent_moves TEXT NOT NULL,
    difficulty INTEGER NOT NULL DEFAULT 1,
    tags TEXT NOT NULL DEFAULT '[]',
    explanation TEXT NOT NULL DEFAULT '',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def test_init_db_migrates_existing_tsume_table_before_source_indexes(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(OLD_TSUME_SCHEMA)
        conn.execute(
            """
            INSERT INTO tsume_problems
              (title, initial_sfen, mate_length, solution_moves, opponent_moves)
            VALUES ('legacy', '4k4/9/9/9/9/9/9/9/9 b G 1', 1, '[]', '[]')
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("SHOGI_DB_PATH", str(db))
    init_db()

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tsume_problems)")}
        assert {
            "source_name",
            "source_url",
            "source_license",
            "source_copyright",
            "external_id",
            "source_hash",
            "source_metadata",
        }.issubset(columns)

        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(tsume_problems)")}
        assert "idx_tsume_source_external" in indexes
        assert "idx_tsume_source_hash" in indexes

        row = conn.execute("SELECT source_name, source_metadata FROM tsume_problems WHERE title = 'legacy'").fetchone()
        assert row["source_name"] == ""
        assert row["source_metadata"] == "{}"
    finally:
        conn.close()
        os.environ.pop("SHOGI_DB_PATH", None)
