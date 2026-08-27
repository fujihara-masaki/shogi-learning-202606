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
MAIN = ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e"]


def artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_artifact_contract_legality_and_tree_signature():
    data = artifact()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["revision"], record["source"]["section"], record["license"], record["retrieved_date"]) == (107928861, "早石田", "CC BY-SA 4.0", "2026-08-27")
    assert "oldid=107928861" in record["source"]["url"]
    assert (record["provenance"], record["coverage_status"]) == ("A", "complete_for_cited_sequence")
    assert record["coverage"] == {"covered_through_ply": 6, "covered_through_move": "8d8e", "omitted_after": None}
    nodes = {node["key"]: node for node in record["nodes"]}
    assert len(nodes) == 14
    assert "main-7" not in nodes
    children = defaultdict(list)
    for node in nodes.values():
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
    assert len(children["main-3"]) == 1
    branch = sorted(children["main-5"], key=lambda n: n["sort_order"])
    assert [(n["key"], n["usi"], n["is_main"], n["variation_group"]) for n in branch] == [
        ("silver-defense-6", "7a6b", False, "△6二銀の変化"),
        ("castle-defense-6", "5a4b", False, "△4二玉の変化"),
        ("main-6", "8d8e", True, "図2-Dへの△8五歩"),
        ("bishop-exchange-6", "2b8h+", False, "図2-Cの角交換変化"),
    ]
    assert nodes["silver-defense-7"]["usi"] == nodes["castle-defense-7"]["usi"] == "6g6f"
    assert nodes["silver-defense-7"] is not nodes["castle-defense-7"]
    assert {key for key in nodes if key not in children} == {"main-6", "silver-defense-7", "castle-defense-7", "bishop-exchange-9"}
    assert [nodes[f"bishop-exchange-{ply}"]["usi"] for ply in range(6, 10)] == ["2b8h+", "7i8h", "B*4e", "B*7f"]

def test_legacy_comparison_is_a_read_only_audit():
    path = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
    before = path.read_bytes()
    result = compare_canonical_to_legacy(artifact()["records"][0], json.loads(before))
    statuses = {node["key"]: node["status"] for node in result["nodes"]}
    assert result["status"] == "changed"
    assert statuses["main-7"] == "removed"
    assert statuses["main-6"] == "changed"
    assert all(statuses[key] == "added" for key in ("silver-defense-6", "castle-defense-6", "bishop-exchange-9"))
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
        removed_id = old_nodes[-1]["id"]
        apply_bundled_wikipedia_opening_artifacts(conn)
        seed_openings_if_empty(conn)
        other_after_static = dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone())
        first = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (old["id"],))]
        apply_bundled_wikipedia_opening_artifacts(conn)
        second = [dict(r) for r in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (old["id"],))]
        line = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchone()
        assert (line["id"], line["seed_key"], line["line_key"]) == (old["id"], "sample:早石田", "wikipedia.ishida.haya-ishida")
        assert (line["opening_type_id"], line["tags"]) == (old["opening_type_id"], old["tags"])
        main_rows = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? AND move_key LIKE 'main-%' ORDER BY ply", (line["id"],)).fetchall()
        assert [r["id"] for r in main_rows] == [r["id"] for r in old_nodes[:6]]
        assert [r["comment"] for r in main_rows] == [r["comment"] for r in old_nodes[:6]]
        assert all(row["id"] != removed_id for row in second)
        assert all(row["usi"] != "7h7f" for row in second)
        assert first == second
        assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
        assert dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone()) == other_after_static
    finally:
        conn.close()


def test_api_projects_complete_canonical_tree(client):
    summary = next(row for row in client.get("/api/openings").json() if row["name"] == LINE_NAME)
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert summary["move_count"] == 6
    assert len(detail["moves"]) == 14
    by_key = {n["move_key"]: n for n in detail["moves"]}
    assert [by_key[f"main-{i}"]["usi"] for i in range(1, 7)] == MAIN
    assert all({"id", "parent_move_id", "move_key", "is_main", "sort_order"} <= n.keys() for n in detail["moves"])
    assert Counter(n["parent_move_id"] for n in detail["moves"])[by_key["main-5"]["id"]] == 4
    assert detail["source"]["source_section"] == "早石田"
    assert detail["source"]["source_url"].endswith("oldid=107928861")
    assert [tag["tag"] for tag in detail["tags"]] == ["haya_ishida"]
    assert detail["opening_type"] == "振り飛車"
