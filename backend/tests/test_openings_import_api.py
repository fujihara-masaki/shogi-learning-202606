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
