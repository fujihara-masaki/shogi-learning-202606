import json
from collections import defaultdict
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact


PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/yokofudori-3c-knight.json"
MOVES = "7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d 8e8f 8g8f 8b8f 2d3d 2a3c".split()


def artifact():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_contract_legality_sfens_and_linear_signature():
    data = artifact()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["record_key"], record["line_key"]) == ("wikipedia.yokofudori.knight-3c",) * 2
    assert (record["provenance"], record["coverage_status"]) == ("A", "complete_for_cited_sequence")
    assert record["coverage"] == {"covered_through_ply": 16, "covered_through_move": "2a3c", "omitted_after": None}
    assert len(record["nodes"]) == 16
    assert [node["usi"] for node in record["nodes"]] == MOVES
    nodes = {node["key"]: node for node in record["nodes"]}
    children = defaultdict(list)
    for ply, node in enumerate(record["nodes"], 1):
        board = shogi.Board(node["from_sfen"])
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        board.push(move)
        assert board.sfen() == node["to_sfen"]
        assert node["parent_key"] == (None if ply == 1 else f"main-{ply - 1}")
        if node["parent_key"]:
            assert nodes[node["parent_key"]]["to_sfen"] == node["from_sfen"]
        children[node["parent_key"]].append(node)
    assert all(len(siblings) == 1 and siblings[0]["is_main"] and siblings[0]["sort_order"] == 0 for siblings in children.values())
    leaves = [node for node in record["nodes"] if node["key"] not in children]
    assert len(leaves) == 1 and leaves[0]["usi"] == "2a3c"
    assert max(int(node["key"].split("-")[1]) for node in record["nodes"]) == 16


def test_fresh_and_existing_seed_are_idempotent_and_preserve_other_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        protected = {}
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角"):
            line = dict(conn.execute("SELECT * FROM opening_lines WHERE name=?", (name,)).fetchone())
            protected[name] = (line, [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))])
        line = dict(conn.execute("SELECT * FROM opening_lines WHERE line_key='wikipedia.yokofudori.knight-3c'").fetchone())
        rows = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert (line["name"], line["seed_key"], len(rows)) == ("横歩取り△3三桂", "sample:横歩取り△3三桂", 16)
        conn.execute("UPDATE opening_line_moves SET comment='runtime memo' WHERE line_id=? AND move_key='main-16'", (line["id"],))
        first_ids = [(row["id"], row["move_key"], row["parent_move_id"]) for row in rows]
        for _ in range(2):
            seed_openings_if_empty(conn)
            apply_bundled_wikipedia_opening_artifacts(conn)
        after = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert [(row["id"], row["move_key"], row["parent_move_id"]) for row in after] == first_ids
        assert after[-1]["comment"] == "runtime memo"
        assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
        for name, (old_line, old_nodes) in protected.items():
            current = dict(conn.execute("SELECT * FROM opening_lines WHERE id=?", (old_line["id"],)).fetchone())
            current_nodes = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (old_line["id"],))]
            current.pop("updated_at"); old_line.pop("updated_at")
            for row in current_nodes + old_nodes:
                row.pop("updated_at", None)
            assert current == old_line
            assert current_nodes == old_nodes
        assert len(protected["横歩取り"][1]) == 15
        assert len(protected["相横歩取り"][1]) == 24
        assert len(protected["横歩取り△4五角"][1]) == 35
    finally:
        conn.close()


def test_api_catalog_projection_and_type_routes(client):
    summary = next(item for item in client.get("/api/openings").json() if item["name"] == "横歩取り△3三桂")
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert (summary["move_count"], len(detail["moves"]), detail["opening_type"]) == (16, 16, "相居飛車")
    assert [tag["tag"] for tag in detail["tags"]] == ["yokofudori"]
    assert detail["source"]["source_section"] == "導入部（「解説」節より前）"
    types = client.get("/api/opening-types").json()
    own = next(item for item in types if item["name_ja"] == "横歩取り△3三桂")
    parent = next(item for item in types if item["name_ja"] == "横歩取り")
    assert own["parent_id"] == parent["id"]
    assert any(item["id"] == summary["id"] for item in client.get(f"/api/opening-types/{own['id']}/lines").json())
