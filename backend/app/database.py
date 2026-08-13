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
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    source_license TEXT NOT NULL DEFAULT '',
    source_copyright TEXT NOT NULL DEFAULT '',
    external_id TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL DEFAULT '',
    source_metadata TEXT NOT NULL DEFAULT '{}'
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
    source_type TEXT NOT NULL DEFAULT '',
    source_section TEXT NOT NULL DEFAULT '',
    source_license TEXT NOT NULL DEFAULT '',
    source_retrieved_at TEXT NOT NULL DEFAULT '',
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
    move_key TEXT NOT NULL,
    is_main INTEGER NOT NULL DEFAULT 1 CHECK(is_main IN (0, 1)),
    UNIQUE(line_id, move_key),
    UNIQUE(line_id, parent_move_id, sort_order)
);

CREATE VIEW IF NOT EXISTS opening_moves AS
    WITH RECURSIVE main_path(id) AS (
        SELECT id FROM opening_line_moves WHERE parent_move_id IS NULL AND is_main = 1
        UNION ALL
        SELECT child.id FROM opening_line_moves child JOIN main_path parent ON child.parent_move_id = parent.id
        WHERE child.is_main = 1
    )
    SELECT m.id, m.line_id, m.ply, m.usi, m.from_sfen, m.to_sfen, m.comment
    FROM opening_line_moves m JOIN main_path ON main_path.id = m.id;

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

CREATE TABLE IF NOT EXISTS next_move_problem_refs (
    problem_key TEXT PRIMARY KEY, stable_source_key TEXT NOT NULL, normalized_sfen TEXT NOT NULL,
    candidate_definition_fingerprint TEXT NOT NULL, problem_definition_version INTEGER NOT NULL DEFAULT 1,
    last_extraction_run_key TEXT NOT NULL DEFAULT '', last_source_file_sha256 TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')), last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS next_move_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, problem_key TEXT NOT NULL REFERENCES next_move_problem_refs(problem_key),
    opening_key_at_answer TEXT NOT NULL DEFAULT '', opening_name_at_answer TEXT NOT NULL DEFAULT '',
    move_usi TEXT NOT NULL, verdict TEXT NOT NULL, candidate_rank INTEGER,
    judgment_position INTEGER, hint_count INTEGER NOT NULL, elapsed_ms INTEGER NOT NULL,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_next_move_results_latest
    ON next_move_results(problem_key, answered_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_next_move_results_answered
    ON next_move_results(answered_at);
"""

LATEST_NEXT_MOVE_RESULT_ORDER = "answered_at DESC, id DESC"

def latest_next_move_result(conn: sqlite3.Connection, problem_key: str):
    return conn.execute(
        f"SELECT * FROM next_move_results WHERE problem_key = ? ORDER BY {LATEST_NEXT_MOVE_RESULT_ORDER} LIMIT 1",
        (problem_key,),
    ).fetchone()


def latest_next_move_results(conn: sqlite3.Connection, problem_keys: list[str]):
    """Return the same deterministic latest row for many current problems."""
    unique_keys = list(dict.fromkeys(problem_keys))
    if not unique_keys:
        return {}
    latest = {}
    for start in range(0, len(unique_keys), 500):
        chunk = unique_keys[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(f"""SELECT * FROM (
            SELECT r.*, ROW_NUMBER() OVER (PARTITION BY problem_key
              ORDER BY answered_at DESC, id DESC) AS latest_rank
            FROM next_move_results r WHERE problem_key IN ({marks})
          ) WHERE latest_rank=1""", chunk).fetchall()
        latest.update((row["problem_key"], row) for row in rows)
    return latest


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
    for column in ("source_url", "source_title", "license", "source_note", "coverage_status", "source_type", "source_section", "source_license", "source_retrieved_at"):
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
                WITH RECURSIVE main_path(id) AS (
                    SELECT id FROM opening_line_moves WHERE parent_move_id IS NULL AND is_main = 1
                    UNION ALL SELECT child.id FROM opening_line_moves child JOIN main_path parent ON child.parent_move_id=parent.id WHERE child.is_main=1
                )
                SELECT m.id, m.line_id, m.ply, m.usi, m.from_sfen, m.to_sfen, m.comment
                FROM opening_line_moves m JOIN main_path ON main_path.id=m.id
            """
        )


def _ensure_opening_line_moves_schema(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'opening_line_moves'"
    ).fetchone()
    if not table or not table["sql"]:
        return

    table_sql = " ".join(str(table["sql"]).lower().split())
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_line_moves)").fetchall()}
    if {"move_key", "is_main"}.issubset(columns):
        conn.execute("DROP VIEW IF EXISTS opening_moves")
        conn.execute(
            """CREATE VIEW opening_moves AS
               WITH RECURSIVE main_path(id) AS (
                 SELECT id FROM opening_line_moves WHERE parent_move_id IS NULL AND is_main=1
                 UNION ALL SELECT child.id FROM opening_line_moves child JOIN main_path parent ON child.parent_move_id=parent.id WHERE child.is_main=1
               )
               SELECT m.id, m.line_id, m.ply, m.usi, m.from_sfen, m.to_sfen, m.comment
               FROM opening_line_moves m JOIN main_path ON main_path.id=m.id"""
        )
        return
    variation_expr = "variation_group" if "variation_group" in columns else "'main'"
    parent_expr = "parent_move_id" if "parent_move_id" in columns else "NULL"
    sort_expr = "sort_order" if "sort_order" in columns else "0"

    # The constrained copy below must temporarily renumber siblings.  Preserve
    # the structural fields from the old table first: variation_group is only
    # a display label and is not, by itself, a legacy branch identity.
    legacy_identity = {
        row["id"]: (row["original_parent_move_id"], row["original_sort_order"])
        for row in conn.execute(
            f"""SELECT id, {parent_expr} AS original_parent_move_id,
                       {sort_expr} AS original_sort_order
                FROM opening_line_moves"""
        ).fetchall()
    }

    conn.execute("DROP VIEW IF EXISTS opening_moves")
    conn.execute("ALTER TABLE opening_line_moves RENAME TO opening_line_moves_old")
    conn.execute(
        """
        CREATE TABLE opening_line_moves (
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
            move_key TEXT NOT NULL,
            is_main INTEGER NOT NULL DEFAULT 1 CHECK(is_main IN (0, 1)),
            UNIQUE(line_id, move_key),
            UNIQUE(line_id, parent_move_id, sort_order)
        )
        """
    )
    conn.execute(
        f"""
        INSERT INTO opening_line_moves(
            id, line_id, ply, usi, from_sfen, to_sfen, comment,
            variation_group, parent_move_id, sort_order, move_key, is_main
        )
        SELECT
            id, line_id, ply, usi, from_sfen, to_sfen, comment,
            {variation_expr}, {parent_expr},
            ROW_NUMBER() OVER (
                PARTITION BY line_id, {parent_expr}
                ORDER BY {sort_expr}, id
            ) - 1,
            'legacy-' || id, CASE WHEN {variation_expr} = 'main' THEN 1 ELSE 0 END
        FROM opening_line_moves_old
        """
    )
    conn.execute("DROP TABLE opening_line_moves_old")
    # Keep the copied legacy rank before evacuation.  Temporary values only
    # exist to make reparenting collision-free and must not become display
    # ordering (for example, by reversing two variations through negative IDs).
    legacy_sort_orders = {
        row_id: identity[1] for row_id, identity in legacy_identity.items()
    }
    # Reparenting can move a root-level main move into a sibling set that still
    # contains legacy branch rows with the same order.  Evacuate every copied
    # order before changing any parent so the active UNIQUE constraint cannot
    # be hit halfway through the conversion.
    conn.execute("UPDATE opening_line_moves SET sort_order = -id - 1")
    # Old branch rows pointed every move at the branch point.  Convert them to
    # direct-parent chains without using SFEN as node identity.
    for line in conn.execute("SELECT id, initial_sfen FROM opening_lines").fetchall():
        rows = conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply, id", (line["id"],)
        ).fetchall()
        by_group = {}
        for row in rows:
            original_parent, original_sort = legacy_identity[row["id"]]
            branch_identity = (row["variation_group"], original_parent, original_sort)
            by_group.setdefault(branch_identity, []).append(row)
        main = sorted(
            (row for row in rows if row["variation_group"] == "main"),
            key=lambda row: (row["ply"], row["id"]),
        )
        previous = None
        for row in main:
            conn.execute("UPDATE opening_line_moves SET parent_move_id=? WHERE id=?", (previous, row["id"]))
            previous = row["id"]
        for group, group_rows in by_group.items():
            if group[0] == "main":
                continue
            previous = group[1]
            for row in sorted(group_rows, key=lambda item: (item["ply"], item["id"])):
                conn.execute("UPDATE opening_line_moves SET parent_move_id=? WHERE id=?", (previous, row["id"]))
                previous = row["id"]
        sibling_parents = conn.execute(
            "SELECT DISTINCT parent_move_id FROM opening_line_moves WHERE line_id=?", (line["id"],)
        ).fetchall()
        for sibling_parent in sibling_parents:
            parent_id = sibling_parent["parent_move_id"]
            predicate = "parent_move_id IS NULL" if parent_id is None else "parent_move_id=?"
            values = (line["id"],) if parent_id is None else (line["id"], parent_id)
            group_rows = conn.execute(
                f"SELECT id, variation_group, sort_order FROM opening_line_moves WHERE line_id=? AND {predicate}",
                values,
            ).fetchall()
            group_rows = sorted(
                group_rows,
                key=lambda row: (
                    0 if row["variation_group"] == "main" else 1,
                    legacy_sort_orders[row["id"]],
                    row["id"],
                ),
            )
            # Move the legacy values out of the non-negative target range first.
            # Updating directly to 0..n can otherwise collide with a sibling that
            # has not yet been updated while the UNIQUE constraint is active.
            for row in group_rows:
                conn.execute(
                    "UPDATE opening_line_moves SET sort_order=? WHERE id=?",
                    (-row["id"] - 1, row["id"]),
                )
            for sort_order, row in enumerate(group_rows):
                conn.execute(
                    "UPDATE opening_line_moves SET sort_order=? WHERE id=?",
                    (sort_order, row["id"]),
                )
            conn.execute(f"UPDATE opening_line_moves SET is_main=0 WHERE line_id=? AND {predicate}", values)
            if group_rows:
                conn.execute("UPDATE opening_line_moves SET is_main=1 WHERE id=?", (group_rows[0]["id"],))
    conn.execute(
        """
        CREATE VIEW opening_moves AS
            WITH RECURSIVE main_path(id) AS (
                SELECT id FROM opening_line_moves WHERE parent_move_id IS NULL AND is_main=1
                UNION ALL SELECT child.id FROM opening_line_moves child JOIN main_path parent ON child.parent_move_id=parent.id WHERE child.is_main=1
            )
            SELECT m.id, m.line_id, m.ply, m.usi, m.from_sfen, m.to_sfen, m.comment
            FROM opening_line_moves m JOIN main_path ON main_path.id=m.id
        """
    )


def _ensure_opening_root_sort_order_index(conn: sqlite3.Connection) -> None:
    """Enforce sibling ordering for roots, which NULL-aware UNIQUE cannot cover."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opening_line_moves'"
    ).fetchone()
    if table:
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_opening_line_moves_root_sort_order
               ON opening_line_moves(line_id, sort_order)
               WHERE parent_move_id IS NULL"""
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



def _ensure_tsume_source_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tsume_problems)").fetchall()}
    for column in ("source_name", "source_url", "source_license", "source_copyright", "external_id", "source_hash"):
        if column not in columns:
            conn.execute(f"ALTER TABLE tsume_problems ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "source_metadata" not in columns:
        conn.execute("ALTER TABLE tsume_problems ADD COLUMN source_metadata TEXT NOT NULL DEFAULT '{}'")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tsume_source_external
        ON tsume_problems(source_name, mate_length, external_id)
        WHERE source_name <> '' AND external_id <> ''
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tsume_source_hash
        ON tsume_problems(source_name, source_hash)
        WHERE source_name <> '' AND source_hash <> ''
    """)

def init_db() -> None:
    conn = get_connection()
    try:
        _migrate_opening_moves(conn)
        conn.executescript(SCHEMA)
        _ensure_tsume_source_columns(conn)
        _ensure_opening_line_moves_schema(conn)
        _ensure_opening_line_columns(conn)
        _ensure_opening_line_indexes(conn)
        _backfill_opening_line_type_ids(conn)
        _migrate_opening_moves(conn)
        _ensure_opening_line_moves_schema(conn)
        _ensure_opening_root_sort_order_index(conn)
        conn.commit()
    finally:
        conn.close()
