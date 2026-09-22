import json
from collections import defaultdict
from pathlib import Path

import shogi

import app.seed as seed_module
from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact


PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/yokofudori-3c-bishop.json"
MOVES = "7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d 8e8f 8g8f 8b8f 2d3d 2b3c".split()
DESCRIPTION = "横歩取りの基本局面から後手が2二の角を3三へ上がる戦法です。"


def artifact():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_contract_legality_sfens_and_linear_signature():
    data = artifact()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["record_key"], record["line_key"]) == ("wikipedia.yokofudori.bishop-3c",) * 2
    assert (record["provenance"], record["coverage_status"]) == ("A", "complete_for_cited_sequence")
    assert record["coverage"] == {"covered_through_ply": 16, "covered_through_move": "2b3c", "omitted_after": None}
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
    assert len(leaves) == 1 and leaves[0]["usi"] == "2b3c"
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
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂"):
            line = dict(conn.execute("SELECT * FROM opening_lines WHERE name=?", (name,)).fetchone())
            protected[name] = (line, [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))])
        line = dict(conn.execute("SELECT * FROM opening_lines WHERE line_key='wikipedia.yokofudori.bishop-3c'").fetchone())
        rows = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert (line["name"], line["seed_key"], len(rows)) == ("横歩取り△3三角", "sample:横歩取り△3三角", 16)
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
        assert len(protected["横歩取り△3三桂"][1]) == 16
    finally:
        conn.close()


def test_upgrade_from_pre_e2e_database_adds_line_without_changing_existing_trees(tmp_path, monkeypatch):
    """Model an existing PR-E2d DB, excluding timestamps that imports refresh."""
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "upgrade.db"))
    init_db()
    conn = get_connection()
    original_lines = seed_module.SAMPLE_OPENING_LINES
    original_types = seed_module.OPENING_TYPE_SEEDS
    original_artifacts = seed_module.BUNDLED_WIKIPEDIA_OPENING_ARTIFACTS
    try:
        monkeypatch.setattr(seed_module, "SAMPLE_OPENING_LINES", [item for item in original_lines if item["name"] != "横歩取り△3三角"])
        monkeypatch.setattr(seed_module, "OPENING_TYPE_SEEDS", [item for item in original_types if item[2] != "横歩取り△3三角"])
        monkeypatch.setattr(seed_module, "BUNDLED_WIKIPEDIA_OPENING_ARTIFACTS", tuple(name for name in original_artifacts if name != "yokofudori-3c-bishop.json"))
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        assert conn.execute("SELECT COUNT(*) FROM opening_types WHERE name_ja='横歩取り△3三角'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM opening_lines WHERE name='横歩取り△3三角'").fetchone()[0] == 0

        protected = {}
        line_columns = "id,line_key,seed_key,name,opening_type_id,opening_type,initial_sfen,moves,comments,tags,source_url,source_title,license,source_note,coverage_status,source_type,source_section,source_license,source_retrieved_at"
        node_columns = "id,line_id,ply,usi,from_sfen,to_sfen,comment,variation_group,parent_move_id,sort_order,move_key,is_main"
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂"):
            line = conn.execute(f"SELECT {line_columns} FROM opening_lines WHERE name=?", (name,)).fetchone()
            conn.execute("UPDATE opening_line_moves SET comment=? WHERE line_id=? AND move_key='main-1'", (f"pre-E2e runtime memo: {name}", line["id"]))
        # Canonical import projects runtime-owned node comments back to the
        # legacy main-line comments array. Snapshot only after that projection.
        apply_bundled_wikipedia_opening_artifacts(conn)
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂"):
            line = conn.execute(f"SELECT {line_columns} FROM opening_lines WHERE name=?", (name,)).fetchone()
            protected[name] = (
                dict(line),
                [dict(row) for row in conn.execute(f"SELECT {node_columns} FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))],
            )

        def assert_protected_lines_unchanged():
            for name, expected in protected.items():
                line = conn.execute(f"SELECT {line_columns} FROM opening_lines WHERE name=?", (name,)).fetchone()
                nodes = conn.execute(f"SELECT {node_columns} FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],)).fetchall()
                assert dict(line) == expected[0]
                assert [dict(row) for row in nodes] == expected[1]

        def assert_added_line():
            own = conn.execute("SELECT * FROM opening_types WHERE name_ja='横歩取り△3三角'").fetchall()
            line_rows = conn.execute("SELECT * FROM opening_lines WHERE line_key='wikipedia.yokofudori.bishop-3c'").fetchall()
            assert len(own) == len(line_rows) == 1
            parent = conn.execute("SELECT * FROM opening_types WHERE id=?", (own[0]["parent_id"],)).fetchone()
            category = conn.execute("SELECT * FROM opening_categories WHERE id=?", (own[0]["category_id"],)).fetchone()
            assert (parent["name_ja"], category["name_ja"], own[0]["description_short"]) == ("横歩取り", "相居飛車", DESCRIPTION)
            line = line_rows[0]
            nodes = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply", (line["id"],)).fetchall()
            assert (line["seed_key"], line["opening_type_id"], json.loads(line["moves"])) == ("sample:横歩取り△3三角", own[0]["id"], MOVES)
            assert [row["usi"] for row in nodes] == MOVES
            assert [row["move_key"] for row in nodes] == [f"main-{ply}" for ply in range(1, 17)]
            assert all(row["is_main"] and row["sort_order"] == 0 for row in nodes)
            assert [row["parent_move_id"] for row in nodes] == [None] + [row["id"] for row in nodes[:-1]]
            assert [row["tag"] for row in conn.execute("SELECT tag FROM opening_tags WHERE line_id=?", (line["id"],))] == ["yokofudori"]
            assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
            return own[0], line, nodes

        monkeypatch.setattr(seed_module, "SAMPLE_OPENING_LINES", original_lines)
        monkeypatch.setattr(seed_module, "OPENING_TYPE_SEEDS", original_types)
        monkeypatch.setattr(seed_module, "BUNDLED_WIKIPEDIA_OPENING_ARTIFACTS", original_artifacts)
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)

        # Assert the first-add result before any runtime edit or repair-like
        # second import, then retain every new identity used by the tree.
        assert_protected_lines_unchanged()
        first_type, first_line, first_nodes = assert_added_line()
        first_identity = (
            first_type["id"],
            first_line["id"],
            [(row["id"], row["move_key"], row["parent_move_id"]) for row in first_nodes],
        )
        conn.execute(
            "UPDATE opening_line_moves SET comment='PR-E2e runtime memo' WHERE line_id=? AND move_key='main-16'",
            (first_line["id"],),
        )
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)

        assert_protected_lines_unchanged()
        repeated_type, repeated_line, repeated_nodes = assert_added_line()
        repeated_identity = (
            repeated_type["id"],
            repeated_line["id"],
            [(row["id"], row["move_key"], row["parent_move_id"]) for row in repeated_nodes],
        )
        assert repeated_identity == first_identity
        assert repeated_nodes[-1]["comment"] == "PR-E2e runtime memo"
    finally:
        conn.close()


def test_api_catalog_projection_and_type_routes(client):
    summary = next(item for item in client.get("/api/openings").json() if item["name"] == "横歩取り△3三角")
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert (summary["move_count"], len(detail["moves"]), detail["opening_type"]) == (16, 16, "相居飛車")
    assert [tag["tag"] for tag in detail["tags"]] == ["yokofudori"]
    assert detail["source"]["source_section"] == "概要（冒頭の基本16手）"
    types = client.get("/api/opening-types").json()
    own = next(item for item in types if item["name_ja"] == "横歩取り△3三角")
    parent = next(item for item in types if item["name_ja"] == "横歩取り")
    assert own["parent_id"] == parent["id"]
    assert own["description_short"] == DESCRIPTION
    assert any(item["id"] == summary["id"] for item in client.get(f"/api/opening-types/{own['id']}/lines").json())


def test_catalog_reseed_updates_old_description_without_changing_type_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "catalog.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        row = conn.execute("SELECT id FROM opening_types WHERE name_ja='横歩取り△3三角'").fetchone()
        conn.execute("UPDATE opening_types SET description_short='後手が3三桂と跳ねて角道を保つ横歩取りの戦法です。' WHERE id=?", (row["id"],))
        seed_opening_catalog_if_empty(conn)
        updated = conn.execute("SELECT id,description_short FROM opening_types WHERE name_ja='横歩取り△3三角'").fetchone()
        assert (updated["id"], updated["description_short"]) == (row["id"], DESCRIPTION)
    finally:
        conn.close()
