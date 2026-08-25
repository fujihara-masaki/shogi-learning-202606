import json
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import (
    apply_bundled_wikipedia_opening_artifacts,
    seed_if_empty,
    seed_opening_catalog_if_empty,
    seed_openings_if_empty,
)
from app.wikipedia_opening_importer import compare_canonical_to_legacy, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact

ARTIFACT_PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/masuda-ishida.json"
LINE_NAME = "升田式石田流（Wikipedia明示手順）"
MOVES = ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "5i4h"]


def _artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_canonical_artifact_legality_and_coverage_boundary():
    artifact = _artifact()
    assert validate_wikipedia_opening_artifact(artifact) == ()
    record = artifact["records"][0]
    assert record["revision"] == 107928861
    assert "oldid=107928861" in record["source"]["url"]
    assert record["provenance"] == "A"
    assert record["coverage_status"] == "complete_for_cited_sequence"
    assert record["coverage"] == {
        "covered_through_ply": 7,
        "covered_through_move": "5i4h",
        "omitted_after": None,
    }
    assert len(record["nodes"]) == 7
    assert record["nodes"][-1]["usi"] == "5i4h"
    assert "7h7f" not in [node["usi"] for node in record["nodes"]]

    board = shogi.Board(record["initial_sfen"])
    for node in record["nodes"]:
        assert node["from_sfen"] == board.sfen()
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        board.push(move)
        assert node["to_sfen"] == board.sfen()
    assert board.turn == shogi.WHITE
    assert shogi.Move.from_usi("7h7f") not in board.legal_moves


def test_legacy_audit_comparison_does_not_mutate_snapshot():
    audit_path = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
    before = audit_path.read_bytes()
    legacy = json.loads(before)
    comparison = compare_canonical_to_legacy(_artifact()["records"][0], legacy)
    assert comparison["status"] in {"changed", "unverifiable"}
    assert comparison["status"] != "ambiguous"
    assert comparison["metadata_changed"] or comparison["unverifiable"]
    assert audit_path.read_bytes() == before


def test_normal_seed_claims_existing_line_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        old = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchone()
        old_nodes = conn.execute(
            "SELECT id, move_key, comment FROM opening_line_moves WHERE line_id=? ORDER BY ply", (old["id"],)
        ).fetchall()
        old_other = dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone())
        conn.commit()
    finally:
        conn.close()

    seed_if_empty()
    seed_if_empty()
    conn = get_connection()
    try:
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        rows = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchall()
        assert len(rows) == 1
        line = rows[0]
        assert line["id"] == old["id"]
        assert line["line_key"] == "wikipedia.ishida.masuda-ishida"
        assert line["seed_key"] == f"sample:{LINE_NAME}"
        assert line["opening_type_id"] == old["opening_type_id"]
        assert line["tags"] == old["tags"]
        assert line["coverage_status"] == old["coverage_status"]
        assert line["source_url"].endswith("oldid=107928861")
        assert (line["source_section"], line["source_license"], line["source_retrieved_at"]) == (
            "升田式石田流", "CC BY-SA 4.0", "2026-08-24"
        )
        nodes = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply", (line["id"],)).fetchall()
        assert len(nodes) == 7
        assert [row["usi"] for row in nodes] == MOVES
        assert [row["id"] for row in nodes] == [row["id"] for row in old_nodes]
        assert [row["comment"] for row in nodes] == [row["comment"] for row in old_nodes]
        assert [row["parent_move_id"] for row in nodes] == [None, *[row["id"] for row in nodes[:-1]]]
        positions = conn.execute("SELECT ply FROM opening_positions WHERE line_id=? ORDER BY ply", (line["id"],)).fetchall()
        assert [row["ply"] for row in positions] == list(range(8))
        assert compare_canonical_to_runtime(conn, _artifact()["records"][0])["status"] == "unchanged"
        other = conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone()
        assert other["id"] == old_other["id"]
        assert other["seed_key"] == old_other["seed_key"]
    finally:
        conn.close()


def test_api_returns_canonical_main_tree_and_attribution(client):
    summary = next(row for row in client.get("/api/openings").json() if row["name"] == LINE_NAME)
    line_id = summary["id"]
    detail = client.get(f"/api/openings/{line_id}").json()
    assert summary["move_count"] == 7
    assert len(detail["moves"]) == 7
    assert [node["usi"] for node in detail["moves"]] == MOVES
    assert "7h7f" not in [node["usi"] for node in detail["moves"]]
    assert all(node["is_main"] and node["variation_group"] == "main" for node in detail["moves"])
    assert detail["source"]["source_url"].endswith("oldid=107928861")
    assert detail["source"]["source_section"] == "升田式石田流"
    assert [tag["tag"] for tag in detail["tags"]] == ["ishida"]
    assert detail["opening_type"] == "振り飛車"
    assert client.get(f"/api/openings/{line_id}").status_code == 200
