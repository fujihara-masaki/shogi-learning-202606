import os
from pathlib import Path

from app.database import init_db
from scripts.import_openings import import_file, parse_usi_line, classify_opening, board_snapshots


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
    assert {"棒銀", "中飛車", "向かい飛車"}.issubset(names)

    bougin = next(line for line in lines.json() if line["name"] == "棒銀")
    detail = client.get(f"/opening-lines/{bougin['id']}")
    assert detail.status_code == 200
    assert detail.json()["moves"][0]["usi"] == "7g7f"

    moves = client.get(f"/opening-lines/{bougin['id']}/moves")
    assert moves.status_code == 200
    assert len(moves.json()) == bougin["move_count"]


def test_parse_sfen_line_and_classify_nakabisha():
    parsed = parse_usi_line("startpos moves 7g7f 3c3d 2h5h")
    positions, _ = board_snapshots(parsed)
    tags = classify_opening(positions, parsed.moves)
    assert any(tag.tag == "nakabisha" for tag in tags)


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
