"""SQLite データベース接続・初期化。

個人利用前提のため接続はリクエストごとに開閉するシンプルな構成。
DB ファイルパスは環境変数 SHOGI_DB_PATH で上書きできる(テスト用)。
"""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shogi.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tsume_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    initial_sfen TEXT NOT NULL,
    mate_length INTEGER NOT NULL,
    solution_moves TEXT NOT NULL,   -- USI 形式の攻め方手順 (JSON 配列)
    opponent_moves TEXT NOT NULL,   -- USI 形式の玉方応手 (JSON 配列)
    difficulty INTEGER NOT NULL DEFAULT 1,
    tags TEXT NOT NULL DEFAULT '[]',  -- JSON 配列
    explanation TEXT NOT NULL DEFAULT '',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS problem_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES tsume_problems(id) ON DELETE CASCADE,
    is_correct INTEGER NOT NULL,
    elapsed_ms INTEGER NOT NULL DEFAULT 0,
    mistake_count INTEGER NOT NULL DEFAULT 0,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS time_attack_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL DEFAULT 'normal',
    mate_length INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_count INTEGER NOT NULL,
    mistake_count INTEGER NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    played_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opening_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ja TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS opening_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES opening_categories(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES opening_types(id) ON DELETE SET NULL,
    name_ja TEXT NOT NULL,
    name_kana TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '[]',
    description_short TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(category_id, name_ja)
);

CREATE TABLE IF NOT EXISTS opening_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    license_name TEXT NOT NULL DEFAULT '',
    license_url TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 第2段階(戦型別定跡学習)用。局面は SFEN、手順は USI の JSON 配列で保存する。
CREATE TABLE IF NOT EXISTS opening_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES opening_sources(id) ON DELETE SET NULL,
    opening_type_id INTEGER REFERENCES opening_types(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    opening_type TEXT NOT NULL,     -- 矢倉 / 角換わり / 四間飛車 など
    initial_sfen TEXT NOT NULL,
    moves TEXT NOT NULL DEFAULT '[]',     -- USI 配列 (JSON)
    comments TEXT NOT NULL DEFAULT '[]',  -- 指し手ごとのコメント (JSON 配列)
    tags TEXT NOT NULL DEFAULT '[]',
    source_url TEXT NOT NULL DEFAULT '',
    source_title TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    source_note TEXT NOT NULL DEFAULT '',
    coverage_status TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opening_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL REFERENCES opening_lines(id) ON DELETE CASCADE,
    ply INTEGER NOT NULL,
    sfen TEXT NOT NULL,
    UNIQUE(line_id, ply)
);

CREATE TABLE IF NOT EXISTS opening_line_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL REFERENCES opening_lines(id) ON DELETE CASCADE,
    ply INTEGER NOT NULL,
    usi TEXT NOT NULL,
    from_sfen TEXT NOT NULL,
    to_sfen TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    variation_group TEXT NOT NULL DEFAULT 'main',
    parent_move_id INTEGER REFERENCES opening_line_moves(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(line_id, ply, variation_group, sort_order)
);

CREATE VIEW IF NOT EXISTS opening_moves AS
    SELECT id, line_id, ply, usi, from_sfen, to_sfen, comment
    FROM opening_line_moves
    WHERE variation_group = 'main';

CREATE TABLE IF NOT EXISTS opening_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL REFERENCES opening_lines(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 1.0,
    reason TEXT NOT NULL DEFAULT '',
    UNIQUE(line_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_problem_results_problem
    ON problem_results(problem_id);
CREATE INDEX IF NOT EXISTS idx_tsume_problems_mate_length
    ON tsume_problems(mate_length);
CREATE INDEX IF NOT EXISTS idx_opening_tags_tag
    ON opening_tags(tag);
CREATE INDEX IF NOT EXISTS idx_opening_types_category
    ON opening_types(category_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_opening_types_parent
    ON opening_types(parent_id);
CREATE INDEX IF NOT EXISTS idx_opening_positions_line
    ON opening_positions(line_id, ply);
CREATE INDEX IF NOT EXISTS idx_opening_line_moves_line
    ON opening_line_moves(line_id, ply);

CREATE TABLE IF NOT EXISTS book_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license_name TEXT NOT NULL DEFAULT '',
    license_text TEXT NOT NULL DEFAULT '',
    copyright_notice TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    file_sha256 TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    position_count INTEGER NOT NULL DEFAULT 0,
    move_count INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(name, version, file_sha256)
);

CREATE TABLE IF NOT EXISTS book_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES book_sources(id) ON DELETE CASCADE,
    sfen TEXT NOT NULL,
    line_no INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_id, sfen)
);

CREATE TABLE IF NOT EXISTS book_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES book_positions(id) ON DELETE CASCADE,
    usi TEXT NOT NULL,
    score INTEGER,
    depth INTEGER,
    pv TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(position_id, usi, sort_order)
);

CREATE INDEX IF NOT EXISTS idx_book_sources_imported_at ON book_sources(imported_at);
CREATE INDEX IF NOT EXISTS idx_book_positions_source ON book_positions(source_id);
CREATE INDEX IF NOT EXISTS idx_book_positions_sfen ON book_positions(sfen);
CREATE INDEX IF NOT EXISTS idx_book_moves_position ON book_moves(position_id, sort_order);

CREATE TABLE IF NOT EXISTS learning_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_source_id INTEGER NOT NULL REFERENCES book_sources(id) ON DELETE CASCADE,
    book_position_id INTEGER NOT NULL REFERENCES book_positions(id) ON DELETE CASCADE,
    opening_key TEXT NOT NULL DEFAULT 'unclassified',
    opening_name TEXT NOT NULL DEFAULT '未分類',
    sfen TEXT NOT NULL,
    sample_rank INTEGER NOT NULL,
    sample_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_source_id, book_position_id)
);

CREATE INDEX IF NOT EXISTS idx_learning_samples_source_opening
    ON learning_samples(book_source_id, opening_key, sample_rank);
CREATE INDEX IF NOT EXISTS idx_learning_samples_position
    ON learning_samples(book_position_id);
"""


def db_path() -> Path:
    return Path(os.environ.get("SHOGI_DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_opening_line_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_lines)").fetchall()}
    if "source_id" not in columns:
        conn.execute("ALTER TABLE opening_lines ADD COLUMN source_id INTEGER REFERENCES opening_sources(id) ON DELETE SET NULL")
    if "opening_type_id" not in columns:
        conn.execute("ALTER TABLE opening_lines ADD COLUMN opening_type_id INTEGER REFERENCES opening_types(id) ON DELETE SET NULL")
    for column in ("source_url", "source_title", "license", "source_note", "coverage_status"):
        if column not in columns:
            conn.execute(f"ALTER TABLE opening_lines ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def _ensure_opening_line_indexes(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_lines)").fetchall()}
    if "opening_type_id" in columns:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_opening_lines_type ON opening_lines(opening_type_id)")


def _migrate_opening_moves(conn: sqlite3.Connection) -> None:
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()}
    if "opening_moves" in tables:
        info = conn.execute("SELECT type FROM sqlite_master WHERE name = 'opening_moves'").fetchone()
        if info and info["type"] == "table":
            conn.execute("ALTER TABLE opening_moves RENAME TO opening_line_moves")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_line_moves)").fetchall()}
            if "variation_group" not in columns:
                conn.execute("ALTER TABLE opening_line_moves ADD COLUMN variation_group TEXT NOT NULL DEFAULT 'main'")
            if "parent_move_id" not in columns:
                conn.execute("ALTER TABLE opening_line_moves ADD COLUMN parent_move_id INTEGER REFERENCES opening_line_moves(id) ON DELETE CASCADE")
            if "sort_order" not in columns:
                conn.execute("ALTER TABLE opening_line_moves ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    objects = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    }
    if "opening_line_moves" in objects:
        conn.execute(
            """
            CREATE VIEW IF NOT EXISTS opening_moves AS
                SELECT id, line_id, ply, usi, from_sfen, to_sfen, comment
                FROM opening_line_moves
                WHERE variation_group = 'main'
            """
        )


def _backfill_opening_line_type_ids(conn: sqlite3.Connection) -> None:
    objects = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if not {"opening_lines", "opening_types"}.issubset(objects):
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_lines)").fetchall()}
    if "opening_type_id" not in columns:
        return
    conn.execute(
        """
        UPDATE opening_lines
        SET opening_type_id = (
            SELECT ot.id
            FROM opening_types ot
            WHERE ot.name_ja = opening_lines.name
            ORDER BY ot.id
            LIMIT 1
        )
        WHERE opening_type_id IS NULL
          AND EXISTS (SELECT 1 FROM opening_types ot WHERE ot.name_ja = opening_lines.name)
        """
    )
    conn.execute(
        """
        UPDATE opening_lines
        SET opening_type_id = (
            SELECT ot.id
            FROM opening_types ot
            WHERE ot.name_ja = opening_lines.opening_type
            ORDER BY ot.id
            LIMIT 1
        )
        WHERE opening_type_id IS NULL
          AND EXISTS (SELECT 1 FROM opening_types ot WHERE ot.name_ja = opening_lines.opening_type)
        """
    )


def init_db() -> None:
    conn = get_connection()
    try:
        _migrate_opening_moves(conn)
        conn.executescript(SCHEMA)
        _ensure_opening_line_columns(conn)
        _ensure_opening_line_indexes(conn)
        _backfill_opening_line_type_ids(conn)
        _migrate_opening_moves(conn)
        conn.commit()
    finally:
        conn.close()
