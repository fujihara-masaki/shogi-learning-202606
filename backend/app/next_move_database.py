"""Read-only runtime access and explicit creation for the next-move database."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_NEXT_MOVE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "next_move.db"

NEXT_MOVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS book_sources (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, version TEXT NOT NULL DEFAULT '',
 source_url TEXT NOT NULL DEFAULT '', license_name TEXT NOT NULL DEFAULT '', license_text TEXT NOT NULL DEFAULT '',
 copyright_notice TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL DEFAULT '', file_sha256 TEXT NOT NULL DEFAULT '',
 imported_at TEXT NOT NULL DEFAULT (datetime('now')), position_count INTEGER NOT NULL DEFAULT 0,
 move_count INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', UNIQUE(name, version, file_sha256)
);
CREATE TABLE IF NOT EXISTS book_positions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL REFERENCES book_sources(id) ON DELETE CASCADE,
 sfen TEXT NOT NULL, line_no INTEGER NOT NULL DEFAULT 0, UNIQUE(source_id, sfen)
);
CREATE TABLE IF NOT EXISTS book_moves (
 id INTEGER PRIMARY KEY AUTOINCREMENT, position_id INTEGER NOT NULL REFERENCES book_positions(id) ON DELETE CASCADE,
 usi TEXT NOT NULL, score INTEGER, depth INTEGER, pv TEXT NOT NULL DEFAULT '', raw TEXT NOT NULL DEFAULT '',
 sort_order INTEGER NOT NULL DEFAULT 0, UNIQUE(position_id, usi, sort_order)
);
CREATE TABLE IF NOT EXISTS extraction_runs (
 extraction_run_key TEXT PRIMARY KEY, extractor_version TEXT NOT NULL, "limit" INTEGER NOT NULL,
 per_opening_limit INTEGER NOT NULL, seed INTEGER NOT NULL, source_file_sha256 TEXT NOT NULL,
 extracted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_samples (
 id INTEGER PRIMARY KEY AUTOINCREMENT, book_source_id INTEGER NOT NULL REFERENCES book_sources(id) ON DELETE CASCADE,
 book_position_id INTEGER NOT NULL REFERENCES book_positions(id) ON DELETE CASCADE, opening_key TEXT NOT NULL DEFAULT 'unclassified',
 opening_name TEXT NOT NULL DEFAULT '未分類', sfen TEXT NOT NULL, sample_rank INTEGER NOT NULL,
 sample_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
 extraction_run_key TEXT REFERENCES extraction_runs(extraction_run_key),
 UNIQUE(book_source_id, book_position_id)
);
CREATE TABLE IF NOT EXISTS database_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_book_positions_source ON book_positions(source_id);
CREATE INDEX IF NOT EXISTS idx_book_positions_sfen ON book_positions(sfen);
CREATE INDEX IF NOT EXISTS idx_book_moves_position ON book_moves(position_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_learning_samples_source_opening ON learning_samples(book_source_id, opening_key, sample_rank);
CREATE INDEX IF NOT EXISTS idx_learning_samples_position ON learning_samples(book_position_id);
"""

REQUIRED_COLUMNS = {
    "book_sources": {
        "id", "name", "version", "source_url", "license_name", "license_text",
        "copyright_notice", "file_name", "file_sha256", "imported_at",
        "position_count", "move_count", "note",
    },
    "book_positions": {"id", "source_id", "sfen", "line_no"},
    "book_moves": {"id", "position_id", "usi", "score", "depth", "pv", "raw", "sort_order"},
    "learning_samples": {"id", "book_source_id", "book_position_id", "opening_key", "opening_name", "sfen", "sample_rank", "sample_reason", "created_at"},
}


class NextMoveDatabaseUnavailable(RuntimeError):
    pass


def next_move_db_path() -> Path:
    return Path(os.environ.get("NEXT_MOVE_DB_PATH", str(DEFAULT_NEXT_MOVE_DB_PATH)))


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    target = f"file:{path.resolve().as_posix()}?mode=ro" if read_only else str(path)
    conn = sqlite3.connect(target, uri=read_only)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_next_move_connection() -> sqlite3.Connection:
    path = next_move_db_path()
    if not path.is_file():
        raise NextMoveDatabaseUnavailable(f"次の一手専用DBが存在しません: {path}")
    try:
        conn = _connect(path, read_only=True)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(REQUIRED_COLUMNS) - tables
        if missing:
            raise NextMoveDatabaseUnavailable("次の一手専用DBに必須テーブルがありません: " + ", ".join(sorted(missing)))
        for table, required in REQUIRED_COLUMNS.items():
            actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if absent := required - actual:
                raise NextMoveDatabaseUnavailable(f"次の一手専用DBの {table} に必須カラムがありません: {', '.join(sorted(absent))}")
        if conn.execute("SELECT COUNT(*) FROM learning_samples").fetchone()[0] < 1:
            raise NextMoveDatabaseUnavailable("次の一手専用DBに学習サンプルがありません")
        return conn
    except NextMoveDatabaseUnavailable:
        if 'conn' in locals(): conn.close()
        raise
    except sqlite3.Error as exc:
        if 'conn' in locals(): conn.close()
        raise NextMoveDatabaseUnavailable(f"次の一手専用DBをSQLiteとして開けません: {exc}") from exc


def init_next_move_db() -> None:
    """Create a database explicitly for import/test tooling; never called at app startup."""
    path = next_move_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(path, read_only=False)
    try:
        conn.executescript(NEXT_MOVE_SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(learning_samples)")}
        if "extraction_run_key" not in columns:
            # SQLite cannot add a REFERENCES clause while foreign keys are enabled.
            # Legacy writer-upgraded DBs therefore rely on the extractor transaction
            # and read-only validator for the same referential guarantee.
            conn.execute("ALTER TABLE learning_samples ADD COLUMN extraction_run_key TEXT")
        conn.commit()
    finally:
        conn.close()


def get_next_move_write_connection() -> sqlite3.Connection:
    return _connect(next_move_db_path(), read_only=False)
