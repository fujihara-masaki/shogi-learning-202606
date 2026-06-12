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

-- 第2段階(戦型別定跡学習)用。局面は SFEN、手順は USI の JSON 配列で保存する。
CREATE TABLE IF NOT EXISTS opening_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    opening_type TEXT NOT NULL,     -- 矢倉 / 角換わり / 四間飛車 など
    initial_sfen TEXT NOT NULL,
    moves TEXT NOT NULL DEFAULT '[]',     -- USI 配列 (JSON)
    comments TEXT NOT NULL DEFAULT '[]',  -- 指し手ごとのコメント (JSON 配列)
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_problem_results_problem
    ON problem_results(problem_id);
CREATE INDEX IF NOT EXISTS idx_tsume_problems_mate_length
    ON tsume_problems(mate_length);
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


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
