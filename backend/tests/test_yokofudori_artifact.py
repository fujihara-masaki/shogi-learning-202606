import json
from collections import defaultdict
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import compare_canonical_to_legacy, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact

ARTIFACT_PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/yokofudori.json"
AUDIT_PATH = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
MAIN = ["7g7f", "3c3d", "2g2f", "8c8d", "2f2e", "8d8e", "6i7h", "4a3b", "2e2d", "2c2d", "2h2d", "8e8f", "8g8f", "8b8f", "2d3d"]
LEGACY_KEYS = [f"main-{i}" for i in range(1, 14)]


def artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_artifact_contract_legality_and_linear_tree():
    data = artifact()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["revision"], record["source"]["section"], record["license"], record["retrieved_date"]) == (109255965, "最初の共通手順（初手から15手まで）", "CC BY-SA 4.0", "2026-08-28")
    assert "oldid=109255965" in record["source"]["url"]
    assert (record["provenance"], record["coverage_status"]) == ("A", "complete_for_cited_sequence")
    assert record["coverage"] == {"covered_through_ply": 15, "covered_through_move": "2d3d", "omitted_after": None}
    assert [node["usi"] for node in record["nodes"]] == MAIN
    assert len(record["nodes"]) == 15
    nodes = {node["key"]: node for node in record["nodes"]}
    children = defaultdict(list)
    for node in record["nodes"]:
        board = shogi.Board(node["from_sfen"])
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        board.push(move)
        assert board.sfen() == node["to_sfen"]
        if node["parent_key"]:
            assert nodes[node["parent_key"]]["to_sfen"] == node["from_sfen"]
        children[node["parent_key"]].append(node)
    assert len(children[None]) == 1
    for siblings in children.values():
        assert len({node["usi"] for node in siblings}) == len(siblings)
        assert len({node["sort_order"] for node in siblings}) == len(siblings)
        assert sum(node["is_main"] for node in siblings) == 1
    assert all(node["sort_order"] == 0 and node["is_main"] for node in record["nodes"])


def test_legacy_comparison_records_insertions_without_mutating_audit():
    before = AUDIT_PATH.read_bytes()
    result = compare_canonical_to_legacy(artifact()["records"][0], json.loads(before))
    statuses = {node["key"]: node["status"] for node in result["nodes"]}
    assert result["status"] == "changed"
    assert statuses["common-gold-7"] == statuses["common-gold-8"] == "added"
    assert not any(node["status"] == "removed" for node in result["nodes"])
    assert AUDIT_PATH.read_bytes() == before


def test_static_seed_claim_reparents_and_preserves_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn); seed_openings_if_empty(conn)
        old_line = dict(conn.execute("SELECT * FROM opening_lines WHERE name='横歩取り'").fetchone())
        old_nodes = {row["move_key"]: dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (old_line["id"],))}
        other = dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone())
        other_moves = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (other["id"],))]
        apply_bundled_wikipedia_opening_artifacts(conn)
        line = dict(conn.execute("SELECT * FROM opening_lines WHERE name='横歩取り'").fetchone())
        rows = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply", (line["id"],))]
        by_key = {row["move_key"]: row for row in rows}
        assert conn.execute("SELECT count(*) c FROM opening_lines WHERE name='横歩取り'").fetchone()["c"] == 1
        assert (line["id"], line["seed_key"], line["line_key"]) == (old_line["id"], "sample:横歩取り", "wikipedia.yokofudori.basic")
        assert (line["opening_type_id"], line["tags"]) == (old_line["opening_type_id"], old_line["tags"])
        for key in LEGACY_KEYS:
            assert (by_key[key]["id"], by_key[key]["usi"], by_key[key]["comment"]) == (old_nodes[key]["id"], old_nodes[key]["usi"], old_nodes[key]["comment"])
        assert by_key["main-7"]["parent_move_id"] == by_key["common-gold-8"]["id"]
        assert {by_key[key]["id"] for key in ("common-gold-7", "common-gold-8")}.isdisjoint({node["id"] for node in old_nodes.values()})
        record = artifact()["records"][0]
        assert [(row["move_key"], row["parent_move_id"], row["ply"], row["from_sfen"], row["to_sfen"]) for row in rows] == [(node["key"], by_key[node["parent_key"]]["id"] if node["parent_key"] else None, ply, node["from_sfen"], node["to_sfen"]) for ply, node in enumerate(record["nodes"], 1)]
        assert [row["ply"] for row in conn.execute("SELECT ply FROM opening_positions WHERE line_id=? ORDER BY ply", (line["id"],))] == list(range(16))
        assert json.loads(line["moves"]) == MAIN
        first = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        apply_bundled_wikipedia_opening_artifacts(conn); seed_openings_if_empty(conn)
        second = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert first == second
        assert compare_canonical_to_runtime(conn, record)["status"] == "unchanged"
        assert dict(conn.execute("SELECT * FROM opening_lines WHERE name='棒銀'").fetchone()) == other
        assert [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (other["id"],))] == other_moves
    finally:
        conn.close()


def test_api_projects_complete_yokofudori_chain(client):
    summary = next(row for row in client.get("/api/openings").json() if row["name"] == "横歩取り")
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert summary["move_count"] == 15
    assert len(detail["moves"]) == 15
    by_id = {node["id"]: node for node in detail["moves"]}
    roots = [node for node in detail["moves"] if node["parent_move_id"] is None]
    chain = []
    node = roots[0]
    while node:
        chain.append(node["usi"])
        node = next((candidate for candidate in detail["moves"] if candidate["parent_move_id"] == node["id"]), None)
    assert chain == MAIN
    assert detail["source"]["source_section"] == "最初の共通手順（初手から15手まで）"
    assert detail["source"]["source_url"].endswith("oldid=109255965")
    assert detail["opening_type"] == "相居飛車"
    assert [tag["tag"] for tag in detail["tags"]] == ["yokofudori"]
