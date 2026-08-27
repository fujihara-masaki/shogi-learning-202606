import json
from collections import Counter, defaultdict
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import compare_canonical_to_legacy, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact

ARTIFACT_PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/haya-ishida.json"
LINE_NAME = "早石田"
MAIN = ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "7h7f"]


def artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_artifact_contract_legality_and_tree_signature():
    data = artifact()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["revision"], record["source"]["section"], record["license"], record["retrieved_date"]) == (107928861, "早石田", "CC BY-SA 4.0", "2026-08-27")
    assert "oldid=107928861" in record["source"]["url"]
    assert (record["provenance"], record["coverage_status"]) == ("B", "diagram_reconstruction")
    assert record["coverage"] == {"covered_through_ply": 7, "covered_through_move": "7h7f", "omitted_after": None}
    nodes = {node["key"]: node for node in record["nodes"]}
    assert len(nodes) == 11
    assert set(nodes) == {"main-1", "main-2", "main-3", "main-4", "main-5", "main-6", "main-7", "castle-defense-4", "castle-defense-5", "silver-defense-4", "silver-defense-5"}
    children = defaultdict(list)
    for node in nodes.values():
        assert node["parent_key"] is None or node["parent_key"] in nodes
        board = shogi.Board(node["from_sfen"])
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        board.push(move)
        assert board.sfen() == node["to_sfen"]
        if node["parent_key"]:
            assert nodes[node["parent_key"]]["to_sfen"] == node["from_sfen"]
        children[node["parent_key"]].append(node)
    for siblings in children.values():
        assert len({n["usi"] for n in siblings}) == len(siblings)
        assert len({n["sort_order"] for n in siblings}) == len(siblings)
        assert sum(n["is_main"] for n in siblings) == 1
    branch = sorted(children["main-3"], key=lambda n: n["sort_order"])
    assert [(n["key"], n["usi"], n["is_main"], n["variation_group"]) for n in branch] == [
        ("castle-defense-4", "5a4b", False, "4手目△4二玉の変化"),
        ("main-4", "8c8d", True, "4手目△8四歩の本線"),
        ("silver-defense-4", "7a6b", False, "4手目△6二銀の変化"),
    ]
    leaves = {key for key in nodes if key not in children}
    assert leaves == {"main-7", "castle-defense-5", "silver-defense-5"}
    assert "図の先の応手は未収録" in record["evidence_note"]


def test_legacy_comparison_is_a_read_only_audit():
    path = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
    before = path.read_bytes()
    result = compare_canonical_to_legacy(artifact()["records"][0], json.loads(before))
    assert result["status"] in {"changed", "unverifiable"}
    assert result["status"] != "ambiguous"
    assert path.read_bytes() == before


def test_seed_claim_preserves_line_main_ids_comments_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn); seed_openings_if_empty(conn)
        old = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchone()
        old_nodes = conn.execute("SELECT id, comment FROM opening_line_moves WHERE line_id=? ORDER BY ply", (old["id"],)).fetchall()
        other = dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone())
        apply_bundled_wikipedia_opening_artifacts(conn)
        first = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (old["id"],))]
        apply_bundled_wikipedia_opening_artifacts(conn)
        second = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (old["id"],))]
        line = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchone()
        assert (line["id"], line["seed_key"], line["line_key"]) == (old["id"], "sample:早石田", "wikipedia.ishida.haya-ishida")
        assert (line["opening_type_id"], line["tags"]) == (old["opening_type_id"], old["tags"])
        main_rows = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? AND move_key LIKE 'main-%' ORDER BY ply", (line["id"],)).fetchall()
        assert [r["id"] for r in main_rows] == [r["id"] for r in old_nodes]
        assert [r["comment"] for r in main_rows] == [r["comment"] for r in old_nodes]
        assert first == second
        assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
        assert dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone()) == other
    finally:
        conn.close()


def test_api_projects_complete_canonical_tree(client):
    summary = next(row for row in client.get("/api/openings").json() if row["name"] == LINE_NAME)
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert summary["move_count"] == 7
    assert len(detail["moves"]) == 11
    by_key = {n["move_key"]: n for n in detail["moves"]}
    assert [by_key[f"main-{i}"]["usi"] for i in range(1, 8)] == MAIN
    assert all({"id", "parent_move_id", "move_key", "is_main", "sort_order"} <= n.keys() for n in detail["moves"])
    assert Counter(n["parent_move_id"] for n in detail["moves"])[by_key["main-3"]["id"]] == 3
    assert detail["source"]["source_section"] == "早石田"
    assert detail["source"]["source_url"].endswith("oldid=107928861")
    assert [tag["tag"] for tag in detail["tags"]] == ["haya_ishida"]
    assert detail["opening_type"] == "振り飛車"
