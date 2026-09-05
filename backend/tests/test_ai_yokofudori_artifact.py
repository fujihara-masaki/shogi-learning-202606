import json
from collections import defaultdict
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import compare_canonical_to_legacy, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact

ARTIFACT_PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/ai-yokofudori.json"
AUDIT_PATH = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
MAIN = ["7g7f", "3c3d", "2g2f", "8c8d", "2f2e", "8d8e", "6i7h", "4a3b", "2e2d", "2c2d", "2h2d", "8e8f", "8g8f", "8b8f", "2d3d", "2b8h+", "7i8h", "8f7f", "8h7g", "7f7d", "3d7d"]


def artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_contract_legality_and_tree_signature():
    data = artifact(); assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["revision"], record["source"]["section"], record["license"], record["retrieved_date"]) == (92929410, "戦法の詳細と近年の傾向", "CC BY-SA 4.0", "2026-09-05")
    assert "oldid=92929410" in record["source"]["url"]
    assert (record["provenance"], record["coverage_status"], record["coverage"]) == ("A", "complete_for_cited_sequence", {"covered_through_ply": 21, "covered_through_move": "3d7d", "omitted_after": None})
    assert len(record["nodes"]) == 24
    nodes = {node["key"]: node for node in record["nodes"]}; children = defaultdict(list)
    for node in record["nodes"]:
        board = shogi.Board(node["from_sfen"]); move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves; board.push(move); assert board.sfen() == node["to_sfen"]
        if node["parent_key"]: assert nodes[node["parent_key"]]["to_sfen"] == node["from_sfen"]
        children[node["parent_key"]].append(node)
    for siblings in children.values():
        assert len({n["usi"] for n in siblings}) == len(siblings)
        assert len({n["sort_order"] for n in siblings}) == len(siblings)
        assert sum(n["is_main"] for n in siblings) == 1
    assert [(n["usi"], n["sort_order"], n["is_main"]) for n in children["main-18"]] == [("P*7g", 0, False), ("8i7g", 1, False), ("8h7g", 2, True)]
    assert [n["usi"] for n in children["main-19"]] == ["7f7d"]
    assert [(n["usi"], n["is_main"]) for n in children["main-20"]] == [("3d7d", True), ("3d3f", False)]
    def depth(node):
        result = 1
        while node["parent_key"] is not None:
            node = nodes[node["parent_key"]]
            result += 1
        return result

    leaves = [n for n in record["nodes"] if n["key"] not in children]
    assert {n["usi"] for n in leaves} == {"P*7g", "8i7g", "3d7d", "3d3f"}
    assert len(leaves) == 4  # Each leaf represents one root-to-leaf path in this tree.
    assert [nodes[f"main-{i}"]["usi"] for i in range(1, 22)] == MAIN
    assert max(depth(node) for node in record["nodes"]) == 21


def test_static_claim_identity_classification_and_e2a_non_regression(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db")); init_db(); conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn); seed_openings_if_empty(conn)
        old = dict(conn.execute("SELECT * FROM opening_lines WHERE name='相横歩取り'").fetchone())
        old_nodes = {r["move_key"]: dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (old["id"],))}
        apply_bundled_wikipedia_opening_artifacts(conn)
        e2a = dict(conn.execute("SELECT * FROM opening_lines WHERE name='横歩取り'").fetchone())
        e2a_nodes = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (e2a["id"],))]
        line = dict(conn.execute("SELECT * FROM opening_lines WHERE name='相横歩取り'").fetchone())
        rows = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        by_key = {r["move_key"]: r for r in rows}
        assert (line["id"], line["seed_key"], line["line_key"], line["tags"]) == (old["id"], "sample:相横歩取り", "wikipedia.yokofudori.ai-yokofudori", old["tags"])
        assert line["opening_type_id"] == old["opening_type_id"]
        for i in range(1, 22): assert (by_key[f"main-{i}"]["id"], by_key[f"main-{i}"]["comment"]) == (old_nodes[f"main-{i}"]["id"], old_nodes[f"main-{i}"]["comment"])
        assert len(rows) == 24 and set(by_key) - set(old_nodes) == {"pawn-defense-19", "knight-defense-19", "rook-decline-21"}
        type_row = conn.execute("SELECT * FROM opening_types WHERE name_ja='相横歩取り'").fetchone()
        parent = conn.execute("SELECT * FROM opening_types WHERE id=?", (type_row["parent_id"],)).fetchone()
        assert parent["name_ja"] == "横歩取り" and type_row["sort_order"] == 41
        first = rows; seed_openings_if_empty(conn); apply_bundled_wikipedia_opening_artifacts(conn)
        assert first == [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
        assert {k: v for k, v in dict(conn.execute("SELECT * FROM opening_lines WHERE id=?", (e2a["id"],)).fetchone()).items() if k != "updated_at"} == {k: v for k, v in e2a.items() if k != "updated_at"}
        assert [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (e2a["id"],))] == e2a_nodes
    finally: conn.close()


def test_legacy_audit_is_unchanged_and_new_line_is_added():
    before = AUDIT_PATH.read_bytes()
    assert compare_canonical_to_legacy(artifact()["records"][0], json.loads(before))["status"] == "added"
    assert AUDIT_PATH.read_bytes() == before


def test_api_projection_and_catalog_routes(client):
    summary = next(x for x in client.get("/api/openings").json() if x["name"] == "相横歩取り")
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert summary["move_count"] == 21 and len(detail["moves"]) == 24
    assert detail["opening_type"] == "相居飛車" and [t["tag"] for t in detail["tags"]] == ["yokofudori"]
    assert detail["source"]["source_section"] == "戦法の詳細と近年の傾向" and detail["source"]["source_url"].endswith("oldid=92929410")
    types = client.get("/api/opening-types").json(); own = next(t for t in types if t["name_ja"] == "相横歩取り"); parent = next(t for t in types if t["name_ja"] == "横歩取り")
    assert own["parent_id"] == parent["id"] and summary["opening_type_id"] == own["id"]
    assert any(x["id"] == summary["id"] for x in client.get(f"/api/opening-types/{own['id']}/lines").json())
