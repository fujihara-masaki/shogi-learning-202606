import os
from pathlib import Path

from app.database import init_db
from scripts.import_openings import import_directory, import_file, parse_usi_line, classify_opening, board_snapshots, infer_opening_type

MAJOR_PLAYABLE_OPENINGS = {
    "棒銀",
    "中飛車",
    "向かい飛車",
    "四間飛車",
    "矢倉",
    "角換わり",
    "相掛かり",
    "横歩取り",
    "石田流",
    "ゴキゲン中飛車",
    "角交換四間飛車",
    "右四間飛車",
    "居飛車穴熊",
    "対振り飛車急戦",
}

ADDITIONAL_PLAYABLE_OPENINGS = {
    "三間飛車",
    "角交換振り飛車",
    "相振り飛車",
    "嬉野流",
    "鬼殺し",
    "早石田",
    "筋違い角",
    "雁木",
    "矢倉棒銀",
    "角換わり棒銀",
    "角換わり早繰り銀",
    "角換わり腰掛け銀",
    "原始棒銀",
    "美濃囲い",
    "穴熊",
    "舟囲い",
    "左美濃",
}

ALL_PLAYABLE_OPENINGS = MAJOR_PLAYABLE_OPENINGS | ADDITIONAL_PLAYABLE_OPENINGS


def test_import_opening_file_and_query_api(client, tmp_path):
    path = tmp_path / "licensed.sfen"
    path.write_text("startpos moves 7g7f 3c3d 2h5h\n", encoding="utf-8")
    imported = import_file(path, license_name="CC0", license_url="https://example.test/license")
    assert imported == 1

    tags = client.get("/api/openings/tags")
    assert tags.status_code == 200
    assert any(tag["tag"] == "nakabisha" for tag in tags.json())

    lines = client.get("/api/openings?tag=nakabisha")
    assert lines.status_code == 200
    body = lines.json()
    imported_line = next(line for line in body if line["source"]["license_name"] == "CC0")
    assert imported_line["opening_type_id"] is not None

    detail = client.get(f"/api/openings/{imported_line['id']}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["moves"][2]["usi"] == "2h5h"
    assert len(data["positions"]) == 4
    assert data["source"]["license_url"] == "https://example.test/license"

    moves = client.get(f"/api/opening-lines/{imported_line['id']}/moves")
    assert moves.status_code == 200
    assert moves.json()[2]["usi"] == "2h5h"


def test_seed_opening_mvp_apis(client):
    lines = client.get("/openings")
    assert lines.status_code == 200
    names = {line["name"] for line in lines.json()}
    assert ALL_PLAYABLE_OPENINGS.issubset(names)
    assert all(next(line for line in lines.json() if line["name"] == name)["move_count"] > 0 for name in ALL_PLAYABLE_OPENINGS)

    bougin = next(line for line in lines.json() if line["name"] == "棒銀")
    detail = client.get(f"/opening-lines/{bougin['id']}")
    assert detail.status_code == 200
    assert detail.json()["moves"][0]["usi"] == "7g7f"

    moves = client.get(f"/opening-lines/{bougin['id']}/moves")
    assert moves.status_code == 200
    assert len(moves.json()) == bougin["move_count"]


def test_major_opening_types_have_playable_seed_lines(client):
    types = client.get("/api/opening-types")
    assert types.status_code == 200
    types_by_name = {opening_type["name_ja"]: opening_type for opening_type in types.json()}

    for name in ALL_PLAYABLE_OPENINGS:
        opening_type = types_by_name[name]
        assert opening_type["opening_line_count"] >= 1

        lines = client.get(f"/api/opening-types/{opening_type['id']}/lines")
        assert lines.status_code == 200
        playable_lines = [line for line in lines.json() if line["move_count"] > 0]
        assert playable_lines

        detail = client.get(f"/api/openings/{playable_lines[0]['id']}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["opening_type_id"] == opening_type["id"]
        assert body["initial_sfen"]
        main_body_moves = [move for move in body["moves"] if move["variation_group"] == "main"]
        assert len(main_body_moves) == playable_lines[0]["move_count"]
        assert body["moves"][0]["usi"]
        assert body["moves"][0]["from_sfen"]
        assert body["moves"][0]["to_sfen"]
        assert len(body["positions"]) == len(main_body_moves) + 1


def test_seed_openings_backfills_missing_lines_in_existing_database(tmp_path):
    db_path = tmp_path / "existing-openings.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        init_db()

        from app.database import get_connection
        from app.seed import seed_opening_catalog_if_empty, seed_openings_if_empty

        conn = get_connection()
        try:
            seed_opening_catalog_if_empty(conn)
            type_ids = {
                row["name_ja"]: row["id"]
                for row in conn.execute("SELECT id, name_ja FROM opening_types").fetchall()
            }
            legacy_names = {"棒銀", "中飛車", "向かい飛車"}
            legacy_opening_types = {"棒銀": "居飛車", "中飛車": "振り飛車", "向かい飛車": "振り飛車"}
            for name in legacy_names:
                conn.execute(
                    """
                    INSERT INTO opening_lines(name, opening_type, initial_sfen)
                    VALUES (?, ?, 'startpos')
                    """,
                    (name, legacy_opening_types[name]),
                )
            imported_source_id = conn.execute(
                """
                INSERT INTO opening_sources(name, file_path, license_name)
                VALUES ('user import', '/tmp/user.sfen', 'CC0')
                """
            ).lastrowid
            imported_line_id = conn.execute(
                """
                INSERT INTO opening_lines(source_id, opening_type_id, name, opening_type, initial_sfen, moves)
                VALUES (?, ?, 'ユーザー中飛車', '中飛車', 'startpos', '["7g7f"]')
                """,
                (imported_source_id, type_ids["中飛車"]),
            ).lastrowid
            conn.commit()

            seed_openings_if_empty(conn)
            conn.commit()

            rows = conn.execute(
                """
                SELECT ol.id, ol.name, COUNT(olm.id) AS move_count
                FROM opening_lines ol
                LEFT JOIN opening_line_moves olm ON olm.line_id = ol.id
                WHERE ol.source_id IS NULL AND ol.name IN ({})
                GROUP BY ol.id, ol.name
                """.format(",".join("?" for _ in ALL_PLAYABLE_OPENINGS)),
                tuple(ALL_PLAYABLE_OPENINGS),
            ).fetchall()
            counts_by_name = {row["name"]: row["move_count"] for row in rows}
            assert ALL_PLAYABLE_OPENINGS.issubset(counts_by_name)
            assert all(counts_by_name[name] > 0 for name in ALL_PLAYABLE_OPENINGS)

            for name in legacy_names:
                assert sum(1 for row in rows if row["name"] == name) == 1

            linked_rows = conn.execute(
                """
                SELECT ol.name, ot.name_ja AS linked_type_name
                FROM opening_lines ol
                JOIN opening_types ot ON ot.id = ol.opening_type_id
                WHERE ol.source_id IS NULL AND ol.name IN ({})
                """.format(",".join("?" for _ in ALL_PLAYABLE_OPENINGS)),
                tuple(ALL_PLAYABLE_OPENINGS),
            ).fetchall()
            assert {row["name"]: row["linked_type_name"] for row in linked_rows} == {
                name: name for name in ALL_PLAYABLE_OPENINGS
            }

            imported_line = conn.execute(
                "SELECT source_id, name FROM opening_lines WHERE id = ?",
                (imported_line_id,),
            ).fetchone()
            assert imported_line["source_id"] == imported_source_id
            assert imported_line["name"] == "ユーザー中飛車"
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_seed_openings_supports_legacy_related_tables_without_unique_constraints(tmp_path):
    db_path = tmp_path / "legacy-no-unique.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE opening_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name_ja TEXT NOT NULL UNIQUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE opening_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    parent_id INTEGER,
                    name_ja TEXT NOT NULL,
                    name_kana TEXT NOT NULL DEFAULT '',
                    name_en TEXT NOT NULL DEFAULT '',
                    aliases TEXT NOT NULL DEFAULT '[]',
                    description_short TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE opening_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    opening_type_id INTEGER,
                    name TEXT NOT NULL,
                    opening_type TEXT NOT NULL,
                    initial_sfen TEXT NOT NULL,
                    moves TEXT NOT NULL DEFAULT '[]',
                    comments TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE opening_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id INTEGER NOT NULL,
                    ply INTEGER NOT NULL,
                    sfen TEXT NOT NULL
                );
                CREATE TABLE opening_line_moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id INTEGER NOT NULL,
                    ply INTEGER NOT NULL,
                    usi TEXT NOT NULL,
                    from_sfen TEXT NOT NULL,
                    to_sfen TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    variation_group TEXT NOT NULL DEFAULT 'main',
                    parent_move_id INTEGER,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE opening_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 1.0,
                    reason TEXT NOT NULL DEFAULT ''
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        init_db()

        from app.database import get_connection
        from app.seed import seed_opening_catalog_if_empty, seed_openings_if_empty

        conn = get_connection()
        try:
            seed_opening_catalog_if_empty(conn)
            seed_openings_if_empty(conn)
            seed_openings_if_empty(conn)
            conn.commit()

            bougin = conn.execute(
                """
                SELECT ol.id, ot.name_ja AS linked_type_name, COUNT(olm.id) AS move_count
                FROM opening_lines ol
                JOIN opening_types ot ON ot.id = ol.opening_type_id
                LEFT JOIN opening_line_moves olm ON olm.line_id = ol.id
                WHERE ol.name = '棒銀' AND ol.source_id IS NULL
                GROUP BY ol.id, ot.name_ja
                """
            ).fetchone()
            assert bougin["linked_type_name"] == "棒銀"
            assert bougin["move_count"] > 0

            duplicate_moves = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM opening_line_moves
                WHERE line_id = ? AND ply = 1 AND variation_group = 'main' AND sort_order = 0
                """,
                (bougin["id"],),
            ).fetchone()["c"]
            assert duplicate_moves == 1
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_seed_openings_repairs_existing_seed_line_details(tmp_path):
    db_path = tmp_path / "broken-seed-lines.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        init_db()

        from app.database import get_connection
        from app.seed import seed_opening_catalog_if_empty, seed_openings_if_empty

        conn = get_connection()
        try:
            seed_opening_catalog_if_empty(conn)
            bougin_type = conn.execute("SELECT id FROM opening_types WHERE name_ja = '棒銀'").fetchone()
            line_id = conn.execute(
                """
                INSERT INTO opening_lines(opening_type_id, name, opening_type, initial_sfen, moves, comments, tags)
                VALUES (?, '棒銀', 'legacy seed', 'startpos', '[]', '[]', '[]')
                """,
                (bougin_type["id"],),
            ).lastrowid
            conn.commit()

            seed_openings_if_empty(conn)
            conn.commit()

            repaired = conn.execute(
                """
                SELECT ol.initial_sfen, ol.moves, COUNT(olm.id) AS move_count
                FROM opening_lines ol
                LEFT JOIN opening_line_moves olm ON olm.line_id = ol.id
                WHERE ol.id = ?
                GROUP BY ol.id
                """,
                (line_id,),
            ).fetchone()
            position_count = conn.execute(
                "SELECT COUNT(*) AS c FROM opening_positions WHERE line_id = ?",
                (line_id,),
            ).fetchone()["c"]
            tag_count = conn.execute(
                "SELECT COUNT(*) AS c FROM opening_tags WHERE line_id = ? AND tag = 'bougin'",
                (line_id,),
            ).fetchone()["c"]

            assert repaired["initial_sfen"] != "startpos"
            assert repaired["moves"] != "[]"
            assert repaired["move_count"] > 0
            assert position_count == repaired["move_count"] + 1
            assert tag_count == 1
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_parse_sfen_line_and_classify_nakabisha():
    parsed = parse_usi_line("startpos moves 7g7f 3c3d 2h5h")
    positions, _ = board_snapshots(parsed)
    tags = classify_opening(positions, parsed.moves)
    assert any(tag.tag == "nakabisha" for tag in tags)



def test_infer_opening_type_from_import_metadata(client):
    from app.database import get_connection

    conn = get_connection()
    try:
        cases = [
            ("棒銀戦法", "棒銀"),
            ("右四間", "右四間飛車"),
            ("角換わり腰掛け銀", "角換わり腰掛け銀"),
            ("ゴキ中", "ゴキゲン中飛車"),
            ("分類できない謎の序盤", "未分類"),
        ]
        for text, expected in cases:
            _, name, _ = infer_opening_type(conn, [text])
            assert name == expected
    finally:
        conn.close()


def test_import_opening_file_uses_filename_opening_classification(client, tmp_path):
    path = tmp_path / "右四間.sfen"
    path.write_text("startpos moves 7g7f 3c3d\n", encoding="utf-8")

    imported = import_file(path, license_name="CC0", license_url="https://example.test/license")
    assert imported == 1

    lines = client.get("/api/openings")
    assert lines.status_code == 200
    imported_line = next(line for line in lines.json() if line["name"].startswith("右四間 #"))
    assert imported_line["opening_type"] == "右四間飛車"
    assert imported_line["opening_type_id"] is not None


def test_import_directory_seeds_opening_catalog_for_fresh_database(tmp_path):
    db_path = tmp_path / "fresh-import.db"
    import_dir = tmp_path / "openings"
    import_dir.mkdir()
    path = import_dir / "ゴキ中.sfen"
    path.write_text("startpos moves 7g7f 3c3d 2h5h\n", encoding="utf-8")
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        imported = import_directory(import_dir, license_name="CC0", license_url="https://example.test/license")
        assert imported == 1

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            line = conn.execute(
                """
                SELECT opening_lines.opening_type_id, opening_lines.opening_type, opening_types.name_ja
                FROM opening_lines
                LEFT JOIN opening_types ON opening_types.id = opening_lines.opening_type_id
                WHERE opening_lines.name = 'ゴキ中 #1'
                """
            ).fetchone()
            assert line is not None
            assert line["opening_type_id"] is not None
            assert line["opening_type"] == "ゴキゲン中飛車"
            assert line["name_ja"] == "ゴキゲン中飛車"
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_seed_opening_catalog_updates_same_name_types_without_duplicates(tmp_path):
    db_path = tmp_path / "legacy-catalog.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        init_db()

        from app.database import get_connection
        from app.seed import seed_opening_catalog_if_empty

        conn = get_connection()
        try:
            conn.execute("INSERT INTO opening_categories(name_ja, sort_order) VALUES ('奇襲・B級戦法', 40)")
            conn.execute("INSERT INTO opening_categories(name_ja, sort_order) VALUES ('囲い・構想', 50)")
            conn.execute("INSERT INTO opening_categories(name_ja, sort_order) VALUES ('対抗型', 20)")
            conn.execute("INSERT INTO opening_categories(name_ja, sort_order) VALUES ('相居飛車', 10)")
            old_right = conn.execute(
                "INSERT INTO opening_types(category_id, name_ja, aliases) VALUES (1, '右四間飛車', '[]')"
            ).lastrowid
            old_gangi = conn.execute(
                "INSERT INTO opening_types(category_id, name_ja, aliases) VALUES (2, '雁木', '[]')"
            ).lastrowid
            conn.execute(
                "INSERT INTO opening_lines(opening_type_id, name, opening_type, initial_sfen) VALUES (?, '右四間飛車', '右四間飛車', 'startpos')",
                (old_right,),
            )

            seed_opening_catalog_if_empty(conn)
            conn.commit()

            rows = conn.execute(
                "SELECT name_ja, COUNT(*) AS c FROM opening_types WHERE name_ja IN ('右四間飛車', '雁木') GROUP BY name_ja"
            ).fetchall()
            assert {row["name_ja"]: row["c"] for row in rows} == {"右四間飛車": 1, "雁木": 1}

            right = conn.execute("SELECT id, category_id FROM opening_types WHERE name_ja = '右四間飛車'").fetchone()
            gangi = conn.execute("SELECT id, category_id FROM opening_types WHERE name_ja = '雁木'").fetchone()
            taikou = conn.execute("SELECT id FROM opening_categories WHERE name_ja = '対抗型'").fetchone()
            aiibisha = conn.execute("SELECT id FROM opening_categories WHERE name_ja = '相居飛車'").fetchone()
            assert right["id"] == old_right
            assert right["category_id"] == taikou["id"]
            assert gangi["id"] == old_gangi
            assert gangi["category_id"] == aiibisha["id"]

            line = conn.execute("SELECT opening_type_id FROM opening_lines WHERE name = '右四間飛車'").fetchone()
            assert line["opening_type_id"] == old_right
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)

def test_opening_catalog_seed_apis(client):
    categories = client.get("/opening-categories")
    assert categories.status_code == 200
    category_body = categories.json()
    category_names = {category["name_ja"] for category in category_body}
    assert {"相居飛車", "対抗型", "相振り飛車", "奇襲・B級戦法", "囲い・構想"}.issubset(category_names)
    assert all(category["license"] == "CC BY-SA" for category in category_body)
    assert any(category["source_url"] == "https://ja.wikibooks.org/wiki/将棋の戦法一覧" for category in category_body)
    assert not any("/wiki/将棋/将棋の戦法一覧" in category["source_url"] for category in category_body)

    types = client.get("/opening-types")
    assert types.status_code == 200
    type_body = types.json()
    type_names = {opening_type["name_ja"] for opening_type in type_body}
    assert {"矢倉", "角換わり", "四間飛車", "嬉野流", "美濃囲い", "雁木"}.issubset(type_names)
    assert all(opening_type["license"] == "CC BY-SA" for opening_type in type_body)
    assert any(opening_type["source_url"] == "https://ja.wikibooks.org/wiki/将棋の戦法一覧" for opening_type in type_body)
    assert not any("/wiki/将棋/将棋の戦法一覧" in opening_type["source_url"] for opening_type in type_body)

    taikou = next(category for category in category_body if category["name_ja"] == "対抗型")
    filtered = client.get(f"/opening-types?category_id={taikou['id']}")
    assert filtered.status_code == 200
    assert {opening_type["category_id"] for opening_type in filtered.json()} == {taikou["id"]}
    assert any(opening_type["name_ja"] == "中飛車" for opening_type in filtered.json())

    detail_id = next(opening_type["id"] for opening_type in type_body if opening_type["name_ja"] == "矢倉")
    detail = client.get(f"/opening-types/{detail_id}")
    assert detail.status_code == 200
    assert detail.json()["name_ja"] == "矢倉"

    nakabisha_id = next(opening_type["id"] for opening_type in type_body if opening_type["name_ja"] == "中飛車")
    nakabisha_lines = client.get(f"/opening-types/{nakabisha_id}/lines")
    assert nakabisha_lines.status_code == 200
    assert any(line["name"] == "中飛車" and line["opening_type_id"] == nakabisha_id for line in nakabisha_lines.json())
    assert next(opening_type for opening_type in type_body if opening_type["name_ja"] == "中飛車")["opening_line_count"] == len(nakabisha_lines.json())


def test_init_db_migrates_existing_opening_lines_type_id_column_and_index(tmp_path):
    db_path = tmp_path / "legacy.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE opening_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name_ja TEXT NOT NULL UNIQUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE opening_types (
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
                CREATE TABLE opening_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER REFERENCES opening_sources(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    opening_type TEXT NOT NULL,
                    initial_sfen TEXT NOT NULL,
                    moves TEXT NOT NULL DEFAULT '[]',
                    comments TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                INSERT INTO opening_categories(name_ja) VALUES ('対抗型');
                INSERT INTO opening_types(category_id, name_ja) VALUES (1, '中飛車');
                INSERT INTO opening_lines(name, opening_type, initial_sfen) VALUES ('中飛車', '振り飛車', 'startpos');
                """
            )
            conn.commit()
        finally:
            conn.close()

        init_db()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(opening_lines)").fetchall()}
            assert "opening_type_id" in columns
            index = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_opening_lines_type'").fetchone()
            assert index is not None
            row = conn.execute("SELECT opening_type_id FROM opening_lines WHERE name = '中飛車'").fetchone()
            assert row["opening_type_id"] == 1
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_startup_migrates_legacy_opening_line_moves_unique_constraint_for_branch_seeds(tmp_path):
    import sqlite3
    import shogi

    db_path = tmp_path / "legacy_branch_seed.db"
    os.environ["SHOGI_DB_PATH"] = str(db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE opening_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    opening_type TEXT NOT NULL,
                    initial_sfen TEXT NOT NULL,
                    moves TEXT NOT NULL DEFAULT '[]',
                    comments TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
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
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX idx_opening_line_moves_line
                    ON opening_line_moves(line_id, ply);
                """
            )
            conn.execute(
                "INSERT INTO opening_lines(name, opening_type, initial_sfen) VALUES (?, ?, ?)",
                ("原始鬼殺し（旧seed）", "奇襲戦法", "startpos"),
            )
            main_moves = (
                "7g7f", "3c3d", "8i7g", "8c8d", "7g6e", "7a6b", "7f7e",
                "6c6d", "8h2b+", "3a2b", "B*5e", "2b3c", "5e6d", "6a5b",
                "7e7d", "6b6c", "2h7h", "6c6d", "7d7c+",
            )
            board = shogi.Board()
            main_ids = {}
            for ply, usi in enumerate(main_moves, start=1):
                from_sfen = board.sfen()
                board.push_usi(usi)
                cursor = conn.execute(
                    """INSERT INTO opening_line_moves
                       (line_id, ply, usi, from_sfen, to_sfen, variation_group,
                        parent_move_id, sort_order)
                       VALUES (1, ?, ?, ?, ?, 'main', NULL, 0)""",
                    (ply, usi, from_sfen, board.sfen()),
                )
                main_ids[ply] = cursor.lastrowid

            # Exact pre-PR-B seed shape: main rows are all roots (order 0), and
            # every move in a variation shares move 3 as parent and its branch
            # index as sort_order.
            branch_parent_id = main_ids[3]
            for branch_order, branch_name, branch_moves in (
                (1, "△6二銀の対応", ("7a6b",)),
                (2, "△6二金の有効な受け", ("6a6b", "7g6e", "6c6d")),
                # Two independent legacy branches intentionally reuse one
                # human-readable label. Their original sort orders are their
                # structural identities and must not be chained together.
                (3, "同じ表示名", ("4a4b", "6g6f")),
                (4, "同じ表示名", ("5c5d", "6g6f")),
            ):
                branch_board = shogi.Board()
                for usi in main_moves[:3]:
                    branch_board.push_usi(usi)
                for ply, usi in enumerate(branch_moves, start=4):
                    from_sfen = branch_board.sfen()
                    branch_board.push_usi(usi)
                    conn.execute(
                        """INSERT INTO opening_line_moves
                           (line_id, ply, usi, from_sfen, to_sfen, variation_group,
                            parent_move_id, sort_order)
                           VALUES (1, ?, ?, ?, ?, ?, ?, ?)""",
                        (ply, usi, from_sfen, branch_board.sfen(), branch_name,
                         branch_parent_id, branch_order),
                    )
            # Reuse the same label and sort rank at a different branch point;
            # original parent identity must keep this branch separate too.
            branch_board = shogi.Board()
            for usi in main_moves[:5]:
                branch_board.push_usi(usi)
            from_sfen = branch_board.sfen()
            branch_board.push_usi("4a4b")
            conn.execute(
                """INSERT INTO opening_line_moves
                   (line_id, ply, usi, from_sfen, to_sfen, variation_group,
                    parent_move_id, sort_order)
                   VALUES (1, 6, '4a4b', ?, ?, '同じ表示名', ?, 3)""",
                (from_sfen, branch_board.sfen(), main_ids[5]),
            )
            conn.commit()
        finally:
            conn.close()

        from app.database import init_db

        init_db()

        # The legacy index follows opening_line_moves_old during the rebuild and
        # is dropped with it. Verify the replacement table is indexed during the
        # migration startup itself, before a second SCHEMA execution can mask it.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            first_startup_indexes = {
                index["name"]: index
                for index in conn.execute("PRAGMA index_list(opening_line_moves)").fetchall()
            }
            assert "idx_opening_line_moves_line" in first_startup_indexes
            assert tuple(
                row["name"] for row in conn.execute(
                    "PRAGMA index_info(idx_opening_line_moves_line)"
                ).fetchall()
            ) == ("line_id", "ply")
            assert "idx_opening_line_moves_root_sort_order" in first_startup_indexes
            assert first_startup_indexes["idx_opening_line_moves_root_sort_order"]["partial"] == 1
            assert conn.execute(
                """SELECT tbl_name FROM sqlite_master
                   WHERE type='index' AND name='idx_opening_line_moves_line'"""
            ).fetchone()["tbl_name"] == "opening_line_moves"
        finally:
            conn.close()

        init_db()  # startup migration is idempotent

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            indexes = conn.execute("PRAGMA index_list(opening_line_moves)").fetchall()
            unique_indexes = [index for index in indexes if index["unique"]]
            assert unique_indexes
            unique_columns = {
                tuple(
                    row["name"]
                    for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
                )
                for index in unique_indexes
            }
            assert ("line_id", "move_key") in unique_columns
            assert ("line_id", "parent_move_id", "sort_order") in unique_columns
            root_index = next(
                index for index in unique_indexes
                if index["name"] == "idx_opening_line_moves_root_sort_order"
            )
            assert root_index["partial"] == 1
            assert tuple(
                row["name"] for row in conn.execute(
                    "PRAGMA index_info(idx_opening_line_moves_root_sort_order)"
                ).fetchall()
            ) == ("line_id", "sort_order")
            assert ("line_id", "ply") not in unique_columns

            rows = conn.execute(
                "SELECT * FROM opening_line_moves WHERE line_id=1 ORDER BY ply"
            ).fetchall()
            assert len(rows) == 28
            by_id = {row["id"]: row for row in rows}
            roots = [row for row in rows if row["parent_move_id"] is None]
            assert len(roots) == 1
            for row in rows:
                if row["parent_move_id"] is None:
                    continue
                parent = by_id[row["parent_move_id"]]
                assert parent["ply"] == row["ply"] - 1
                assert by_id[row["parent_move_id"]]["to_sfen"] == row["from_sfen"]

            sibling_groups = conn.execute(
                """SELECT parent_move_id, COUNT(*) AS total,
                          COUNT(DISTINCT sort_order) AS sort_orders,
                          SUM(is_main) AS main_count
                   FROM opening_line_moves WHERE line_id=1
                   GROUP BY parent_move_id"""
            ).fetchall()
            assert all(row["sort_orders"] == row["total"] for row in sibling_groups)
            assert all(row["main_count"] == 1 for row in sibling_groups)
            groups = {
                row["variation_group"]: [item["usi"] for item in rows
                                          if item["variation_group"] == row["variation_group"]]
                for row in rows
            }
            assert groups["main"] == list(main_moves)
            assert groups["△6二銀の対応"] == ["7a6b"]
            assert groups["△6二金の有効な受け"] == ["6a6b", "7g6e", "6c6d"]
            branch_point = next(row for row in rows if row["variation_group"] == "main" and row["ply"] == 3)
            variations = conn.execute(
                """SELECT variation_group FROM opening_line_moves
                   WHERE line_id=1 AND parent_move_id=? AND variation_group != 'main'
                   ORDER BY sort_order""",
                (branch_point["id"],),
            ).fetchall()
            assert [row["variation_group"] for row in variations] == [
                "△6二銀の対応", "△6二金の有効な受け", "同じ表示名", "同じ表示名",
            ]
            same_label_roots = conn.execute(
                """SELECT * FROM opening_line_moves
                   WHERE line_id=1 AND parent_move_id=? AND variation_group='同じ表示名'
                   ORDER BY sort_order""",
                (branch_point["id"],),
            ).fetchall()
            assert [row["usi"] for row in same_label_roots] == ["4a4b", "5c5d"]
            assert len({row["id"] for row in same_label_roots}) == 2
            for root in same_label_roots:
                child = conn.execute(
                    "SELECT * FROM opening_line_moves WHERE parent_move_id=?", (root["id"],)
                ).fetchone()
                assert child is not None
                assert root["to_sfen"] == child["from_sfen"]
            reused_at_other_parent = conn.execute(
                """SELECT * FROM opening_line_moves
                   WHERE parent_move_id=? AND variation_group='同じ表示名'""",
                (main_ids[5],),
            ).fetchone()
            assert reused_at_other_parent is not None
            assert reused_at_other_parent["usi"] == "4a4b"

            from app.seed import validate_opening_move_tree
            validate_opening_move_tree(conn, [1])
        finally:
            conn.close()
    finally:
        os.environ.pop("SHOGI_DB_PATH", None)


def test_seed_openings_expose_wikipedia_source_metadata_and_legal_moves(client):
    import shogi

    types = client.get("/api/opening-types")
    assert types.status_code == 200
    target_names = {
        "棒銀", "原始棒銀", "矢倉棒銀", "角換わり棒銀", "角換わり早繰り銀", "角換わり腰掛け銀",
        "矢倉", "角換わり", "相掛かり", "横歩取り", "雁木", "右四間飛車", "対振り飛車急戦",
        "四間飛車", "三間飛車", "中飛車", "向かい飛車", "石田流", "ゴキゲン中飛車",
        "角交換四間飛車", "居飛車穴熊",
    }
    type_ids = {row["name_ja"]: row["id"] for row in types.json() if row["name_ja"] in target_names}
    assert set(type_ids) == target_names

    for name, type_id in type_ids.items():
        lines_response = client.get(f"/api/opening-types/{type_id}/lines")
        assert lines_response.status_code == 200
        lines = lines_response.json()
        assert lines, name
        detail_response = client.get(f"/api/openings/{lines[0]['id']}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        source = detail["source"]
        assert source["source_url"].startswith("https://ja.wikipedia.org/wiki/")
        assert source["license"] in {"CC BY-SA", "CC BY-SA 4.0"}
        assert source["source_note"]
        assert source["coverage_status"]

        board = shogi.Board(detail["initial_sfen"])
        main_moves = [move for move in detail["moves"] if move["variation_group"] == "main"]
        for move_row in sorted(main_moves, key=lambda row: row["ply"]):
            move = shogi.Move.from_usi(move_row["usi"])
            assert move in board.legal_moves, (name, move_row["usi"], board.sfen())
            board.push(move)


def test_wikipedia_long_seed_branches_are_idempotent_and_replayable(client):
    import shogi

    names = {
        "原始鬼殺し（Wikipedia明示手順）": ("原始鬼殺し", 19),
        "新・早石田（鈴木流急戦・Wikipedia明示手順）": ("新・早石田", 7),
        "升田式石田流（Wikipedia明示手順）": ("升田式石田流", 7),
    }
    lines = client.get("/api/openings").json()
    ids = {line["name"]: line["id"] for line in lines if line["name"] in names}
    assert set(ids) == set(names)

    from app.database import get_connection
    from app.seed import find_duplicate_opening_sibling_moves, seed_openings_if_empty

    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) AS c FROM opening_lines").fetchone()["c"]
        seed_openings_if_empty(conn)
        seed_openings_if_empty(conn)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) AS c FROM opening_lines").fetchone()["c"]
        assert after == before
        assert find_duplicate_opening_sibling_moves(conn) == []
    finally:
        conn.close()

    for name, (section, min_main_moves) in names.items():
        detail = client.get(f"/api/openings/{ids[name]}").json()
        assert detail["source"]["source_type"] == "wikipedia"
        assert detail["source"]["source_section"] == section
        assert detail["source"]["source_license"] == "CC BY-SA 4.0"
        assert detail["source"]["source_retrieved_at"] == "2026-07-03"

        main_moves = sorted([m for m in detail["moves"] if m["variation_group"] == "main"], key=lambda m: m["ply"])
        assert len(main_moves) >= min_main_moves
        board = shogi.Board(detail["initial_sfen"])
        for expected_ply, move_row in enumerate(main_moves, start=1):
            assert move_row["ply"] == expected_ply
            assert move_row["from_sfen"] == board.sfen()
            move = shogi.Move.from_usi(move_row["usi"])
            assert move in board.legal_moves, (name, move_row)
            board.push(move)
            assert move_row["to_sfen"] == board.sfen()

    onigoroshi = client.get(f"/api/openings/{ids['原始鬼殺し（Wikipedia明示手順）']}").json()
    branches = [m for m in onigoroshi["moves"] if m["variation_group"] != "main"]
    assert {m["variation_group"] for m in branches} == {"△6二銀の対応", "△6二金の有効な受け"}
    main_sfen = {pos["ply"]: pos["sfen"] for pos in onigoroshi["positions"]}
    for group in {m["variation_group"] for m in branches}:
        branch_moves = sorted([m for m in branches if m["variation_group"] == group], key=lambda m: m["ply"])
        start_ply = branch_moves[0]["ply"] - 1
        board = shogi.Board(main_sfen[start_ply])
        for move_row in branch_moves:
            assert move_row["from_sfen"] == board.sfen()
            move = shogi.Move.from_usi(move_row["usi"])
            assert move in board.legal_moves, (group, move_row)
            board.push(move)
            assert move_row["to_sfen"] == board.sfen()


def test_all_seed_opening_siblings_have_unique_usi(client):
    from app.database import get_connection
    from app.seed import find_duplicate_opening_sibling_moves

    conn = get_connection()
    try:
        seed_line_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM opening_lines WHERE source_id IS NULL"
            ).fetchall()
        ]
        assert seed_line_ids
        assert find_duplicate_opening_sibling_moves(conn, seed_line_ids) == []
    finally:
        conn.close()


def test_primitive_onigoroshi_silver_moves_are_distinct_nodes(client):
    from app.database import get_connection

    conn = get_connection()
    try:
        line = conn.execute(
            "SELECT id FROM opening_lines WHERE name = ? AND source_id IS NULL",
            ("原始鬼殺し（Wikipedia明示手順）",),
        ).fetchone()
        assert line is not None
        moves = conn.execute(
            """
            SELECT id, ply, usi, from_sfen, parent_move_id, variation_group
            FROM opening_line_moves
            WHERE line_id = ? AND usi = '7a6b'
            ORDER BY ply, variation_group
            """,
            (line["id"],),
        ).fetchall()
        assert len(moves) == 2

        branch_move, main_move = moves
        third_main_move = conn.execute(
            """
            SELECT id, to_sfen FROM opening_line_moves
            WHERE line_id = ? AND ply = 3 AND variation_group = 'main'
            """,
            (line["id"],),
        ).fetchone()

        assert dict(branch_move) == {
            "id": branch_move["id"],
            "ply": 4,
            "usi": "7a6b",
            "from_sfen": third_main_move["to_sfen"],
            "parent_move_id": third_main_move["id"],
            "variation_group": "△6二銀の対応",
        }
        assert main_move["ply"] == 6
        assert main_move["usi"] == "7a6b"
        previous_main = conn.execute(
            "SELECT id FROM opening_line_moves WHERE line_id=? AND ply=5 AND variation_group='main'",
            (line["id"],),
        ).fetchone()
        assert main_move["parent_move_id"] == previous_main["id"]
        assert main_move["variation_group"] == "main"
        assert main_move["from_sfen"] != branch_move["from_sfen"]

        sibling_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM opening_line_moves
            WHERE line_id = ? AND from_sfen = ? AND usi = '7a6b'
            """,
            (line["id"], third_main_move["to_sfen"]),
        ).fetchone()["count"]
        assert sibling_count == 1
    finally:
        conn.close()
