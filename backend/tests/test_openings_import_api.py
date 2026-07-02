import os
from pathlib import Path

from app.database import init_db
from scripts.import_openings import import_directory, import_file, parse_usi_line, classify_opening, board_snapshots, infer_opening_type


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
    major_openings = {
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
    assert major_openings.issubset(names)
    assert all(next(line for line in lines.json() if line["name"] == name)["move_count"] > 0 for name in major_openings)

    bougin = next(line for line in lines.json() if line["name"] == "棒銀")
    detail = client.get(f"/opening-lines/{bougin['id']}")
    assert detail.status_code == 200
    assert detail.json()["moves"][0]["usi"] == "7g7f"

    moves = client.get(f"/opening-lines/{bougin['id']}/moves")
    assert moves.status_code == 200
    assert len(moves.json()) == bougin["move_count"]


def test_major_opening_types_have_playable_seed_lines(client):
    required_names = {
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

    types = client.get("/api/opening-types")
    assert types.status_code == 200
    types_by_name = {opening_type["name_ja"]: opening_type for opening_type in types.json()}

    for name in required_names:
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
        assert len(body["moves"]) == playable_lines[0]["move_count"]
        assert body["moves"][0]["usi"]
        assert body["moves"][0]["from_sfen"]
        assert body["moves"][0]["to_sfen"]
        assert len(body["positions"]) == len(body["moves"]) + 1


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
