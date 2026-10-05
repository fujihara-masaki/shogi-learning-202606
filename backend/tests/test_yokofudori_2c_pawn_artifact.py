import json
from collections import defaultdict
from pathlib import Path

import shogi

import app.seed as seed_module
from app.database import get_connection, init_db
from app.seed import apply_bundled_wikipedia_opening_artifacts, seed_opening_catalog_if_empty, seed_openings_if_empty
from app.wikipedia_opening_importer import apply_wikipedia_opening_artifact, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact


PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/yokofudori-2c-pawn.json"
MOVES = "7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d P*2c 2d3d 2b8h+ 7i8h B*2e".split()
DESCRIPTION = "横歩取りで後手が2三歩と打ち、角交換後に2五角と打つ基本戦法です。"


def artifact():
    return json.loads(PATH.read_text(encoding="utf-8"))


# Exact artifact exported with git show from the merged PR-E2f baseline, not a
# truncation of the new production artifact.
BASE_SHA = "3601e15d57d2bd4fa73de1a3d4c93f809d2764da"
OLD_PATH = Path(__file__).parent / "fixtures/yokofudori-2c-pawn-e2f.json"
TAIL = "B*4e 3d3e 4e2g+ B*1e 5a5b 3g3f 1c1d 1e4h".split()
SECTION = "戦法の概要／導入～△2三歩からの展開（図1-Bへ至る基本16手と△4五角の明示変化23手目まで）"


def test_contract_legality_sfens_and_branch_signature():
    data = artifact()
    old = json.loads(OLD_PATH.read_text(encoding="utf-8"))
    assert validate_wikipedia_opening_artifact(old) == ()
    assert validate_wikipedia_opening_artifact(data) == ()
    record = data["records"][0]
    assert (record["record_key"], record["line_key"], record["line_name"]) == (
        "wikipedia.yokofudori.pawn-2c", "wikipedia.yokofudori.pawn-2c", "横歩取り△2三歩")
    assert (record["provenance"], record["coverage_status"]) == ("A", "complete_for_cited_sequence")
    assert record["revision"] == 92929426
    assert record["retrieved_date"] == "2026-10-06"
    assert record["license"] == "CC BY-SA 4.0"
    assert "oldid=92929426" in record["source"]["url"]
    assert record["source"]["section"] == SECTION
    assert record["coverage"] == {"covered_through_ply": 16, "covered_through_move": "B*2e", "omitted_after": None}
    nodes = {node["key"]: node for node in record["nodes"]}
    # Retain every prior node, including its audit metadata, byte-for-value.
    assert len(old["records"][0]["nodes"]) == 16
    for node in old["records"][0]["nodes"]:
        assert nodes[node["key"]] == node
    assert [nodes[f"main-{ply}"]["usi"] for ply in range(1, 17)] == MOVES
    children = defaultdict(list)
    for node in record["nodes"]:
        board = shogi.Board(node["from_sfen"])
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        before_turn = board.turn
        board.push(move)
        assert board.turn != before_turn
        assert board.sfen() == node["to_sfen"]
        assert node["provenance"] == "A"
        if node["parent_key"]:
            assert nodes[node["parent_key"]]["to_sfen"] == node["from_sfen"]
        children[node["parent_key"]].append(node)
    for siblings in children.values():
        assert len({n["usi"] for n in siblings}) == len(siblings)
        assert len({n["sort_order"] for n in siblings}) == len(siblings)
        assert sum(n["is_main"] for n in siblings) == 1
    assert [(n["key"], n["usi"], n["sort_order"], n["is_main"]) for n in children["main-15"]] == [
        ("main-16", "B*2e", 0, True), ("bishop-4e-16", "B*4e", 1, False)]
    for ply, usi in enumerate(TAIL, 16):
        node = nodes[f"bishop-4e-{ply}"]
        assert node["usi"] == usi
        assert node["parent_key"] == ("main-15" if ply == 16 else f"bishop-4e-{ply - 1}")
        assert (node["sort_order"], node["is_main"]) == ((1, False) if ply == 16 else (0, True))
        assert node["variation_group"] == "△4五角の変化"

    def path(node):
        result = []
        while node:
            result.append(node["usi"])
            node = nodes.get(node["parent_key"])
        return result[::-1]

    leaves = [n for n in record["nodes"] if not children[n["key"]]]
    assert {n["key"] for n in leaves} == {"main-16", "bishop-4e-23"}
    assert [path(n) for n in leaves] == [MOVES, MOVES[:15] + TAIL]
    main = []
    parent = None
    while children[parent]:
        node = next(n for n in children[parent] if n["is_main"])
        main.append(node["usi"]); parent = node["key"]
    assert main == MOVES
    assert (len(nodes), len(main), max(map(lambda n: len(path(n)), leaves)),
            sum(len(c) > 1 for c in children.values()), len(leaves)) == (24, 16, 23, 1, 2)
    # Independent physical checks: 18 is promotion onto an EMPTY square, not capture.
    square = lambda name: shogi.SQUARE_NAMES.index(name)
    before18 = shogi.Board(nodes["bishop-4e-18"]["from_sfen"])
    after18 = shogi.Board(nodes["bishop-4e-18"]["to_sfen"])
    assert before18.piece_at(square("2g")) is None
    assert after18.piece_at(square("2g")).symbol() == "+b"
    assert after18.sfen().split()[1:3] == ["b", "B2P"]
    for ply in (21, 23):
        assert nodes[f"bishop-4e-{ply}"]["to_sfen"].split()[1:3] == ["w", "2P"]
    assert shogi.Board(nodes["bishop-4e-19"]["to_sfen"]).piece_at(square("1e")).symbol() == "B"
    assert shogi.Board(nodes["bishop-4e-21"]["to_sfen"]).piece_at(square("3f")).symbol() == "P"
    assert shogi.Board(nodes["bishop-4e-23"]["to_sfen"]).piece_at(square("4h")).symbol() == "B"


def assert_runtime_tree(conn, line_id):
    rows = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (line_id,)).fetchall()
    by = {row["move_key"]: row for row in rows}
    expected = {node["key"]: node for node in artifact()["records"][0]["nodes"]}
    assert len(rows) == len(by) == 24
    assert set(by) == set(expected)
    for key, node in expected.items():
        row = by[key]
        parent_id = by[node["parent_key"]]["id"] if node["parent_key"] else None
        assert (row["parent_move_id"], row["usi"], row["from_sfen"], row["to_sfen"],
                bool(row["is_main"]), row["sort_order"], row["variation_group"]) == (
                    parent_id, node["usi"], node["from_sfen"], node["to_sfen"],
                    node["is_main"], node["sort_order"], node["variation_group"])
    # opening_positions is a derived semantic-main index; row IDs may change.
    positions = conn.execute("SELECT ply,sfen FROM opening_positions WHERE line_id=? ORDER BY ply", (line_id,)).fetchall()
    assert [tuple(row) for row in positions] == [(0, artifact()["records"][0]["initial_sfen"])] + [
        (ply, expected[f"main-{ply}"]["to_sfen"]) for ply in range(1, 17)]
    return by


def test_fresh_and_existing_seed_are_idempotent_and_preserve_other_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        protected = {}
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂", "横歩取り△3三角"):
            line = dict(conn.execute("SELECT * FROM opening_lines WHERE name=?", (name,)).fetchone())
            protected[name] = (line, [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))])
        line = dict(conn.execute("SELECT * FROM opening_lines WHERE line_key='wikipedia.yokofudori.pawn-2c'").fetchone())
        rows = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert (line["name"], line["seed_key"], len(rows)) == ("横歩取り△2三歩", "sample:横歩取り△2三歩", 24)
        conn.execute("UPDATE opening_line_moves SET comment='runtime memo' WHERE line_id=? AND move_key='main-16'", (line["id"],))
        first_ids = [(row["id"], row["move_key"], row["parent_move_id"]) for row in rows]
        for _ in range(2):
            seed_openings_if_empty(conn)
            apply_bundled_wikipedia_opening_artifacts(conn)
        after = [dict(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY id", (line["id"],))]
        assert [(row["id"], row["move_key"], row["parent_move_id"]) for row in after] == first_ids
        assert next(row for row in after if row["move_key"] == "main-16")["comment"] == "runtime memo"
        assert_runtime_tree(conn, line["id"])
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
        assert len(protected["横歩取り△3三角"][1]) == 16
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
        monkeypatch.setattr(seed_module, "SAMPLE_OPENING_LINES", [item for item in original_lines if item["name"] != "横歩取り△2三歩"])
        monkeypatch.setattr(seed_module, "OPENING_TYPE_SEEDS", [item for item in original_types if item[2] != "横歩取り△2三歩"])
        monkeypatch.setattr(seed_module, "BUNDLED_WIKIPEDIA_OPENING_ARTIFACTS", tuple(name for name in original_artifacts if name != "yokofudori-2c-pawn.json"))
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        assert conn.execute("SELECT COUNT(*) FROM opening_types WHERE name_ja='横歩取り△2三歩'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM opening_lines WHERE name='横歩取り△2三歩'").fetchone()[0] == 0

        protected = {}
        line_columns = "id,line_key,seed_key,name,opening_type_id,opening_type,initial_sfen,moves,comments,tags,source_url,source_title,license,source_note,coverage_status,source_type,source_section,source_license,source_retrieved_at"
        node_columns = "id,line_id,ply,usi,from_sfen,to_sfen,comment,variation_group,parent_move_id,sort_order,move_key,is_main"
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂", "横歩取り△3三角"):
            line = conn.execute(f"SELECT {line_columns} FROM opening_lines WHERE name=?", (name,)).fetchone()
            conn.execute("UPDATE opening_line_moves SET comment=? WHERE line_id=? AND move_key='main-1'", (f"pre-E2f runtime memo: {name}", line["id"]))
        # Canonical import projects runtime-owned node comments back to the
        # legacy main-line comments array. Snapshot only after that projection.
        apply_bundled_wikipedia_opening_artifacts(conn)
        for name in ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂", "横歩取り△3三角"):
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
            own = conn.execute("SELECT * FROM opening_types WHERE name_ja='横歩取り△2三歩'").fetchall()
            line_rows = conn.execute("SELECT * FROM opening_lines WHERE line_key='wikipedia.yokofudori.pawn-2c'").fetchall()
            assert len(own) == len(line_rows) == 1
            parent = conn.execute("SELECT * FROM opening_types WHERE id=?", (own[0]["parent_id"],)).fetchone()
            category = conn.execute("SELECT * FROM opening_categories WHERE id=?", (own[0]["category_id"],)).fetchone()
            assert (parent["name_ja"], category["name_ja"], own[0]["description_short"]) == ("横歩取り", "相居飛車", DESCRIPTION)
            line = line_rows[0]
            nodes = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply", (line["id"],)).fetchall()
            assert (line["seed_key"], line["opening_type_id"], json.loads(line["moves"])) == ("sample:横歩取り△2三歩", own[0]["id"], MOVES)
            assert_runtime_tree(conn, line["id"])
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
            "UPDATE opening_line_moves SET comment='PR-E2f runtime memo' WHERE line_id=? AND move_key='main-16'",
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
        assert next(row for row in repeated_nodes if row["move_key"] == "main-16")["comment"] == "PR-E2f runtime memo"
    finally:
        conn.close()


def test_api_catalog_projection_and_type_routes(client):
    summary = next(item for item in client.get("/api/openings").json() if item["name"] == "横歩取り△2三歩")
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert (summary["move_count"], len(detail["moves"]), detail["opening_type"]) == (16, 24, "相居飛車")
    assert [tag["tag"] for tag in detail["tags"]] == ["yokofudori"]
    assert detail["source"]["source_section"] == SECTION
    types = client.get("/api/opening-types").json()
    own = next(item for item in types if item["name_ja"] == "横歩取り△2三歩")
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
        row = conn.execute("SELECT id FROM opening_types WHERE name_ja='横歩取り△2三歩'").fetchone()
        conn.execute("UPDATE opening_types SET description_short='後手が3三桂と跳ねて角道を保つ横歩取りの戦法です。' WHERE id=?", (row["id"],))
        seed_opening_catalog_if_empty(conn)
        updated = conn.execute("SELECT id,description_short FROM opening_types WHERE name_ja='横歩取り△2三歩'").fetchone()
        assert (updated["id"], updated["description_short"]) == (row["id"], DESCRIPTION)
    finally:
        conn.close()


def test_upgrade_from_exact_e2f_snapshot_preserves_ids_comments_and_other_lines(tmp_path, monkeypatch):
    """Fixture exported from BASE_SHA; compare the FIRST E2g import, then repeats."""
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "e2f-upgrade.db"))
    init_db()
    conn = get_connection()
    old_artifact = json.loads(OLD_PATH.read_text(encoding="utf-8"))
    own_key = "wikipedia.yokofudori.pawn-2c"
    protected_names = ("横歩取り", "相横歩取り", "横歩取り△4五角", "横歩取り△3三桂", "横歩取り△3三角")

    def old_bundle():
        for filename in seed_module.BUNDLED_WIKIPEDIA_OPENING_ARTIFACTS:
            data = old_artifact if filename == PATH.name else json.loads((PATH.parent / filename).read_text())
            apply_wikipedia_opening_artifact(conn, data)

    def clean(row):
        return {key: value for key, value in dict(row).items() if key != "updated_at"}

    def line_and_nodes(key):
        line = conn.execute("SELECT * FROM opening_lines WHERE line_key=?", (key,)).fetchone()
        nodes = {row["move_key"]: clean(row) for row in conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=?", (line["id"],))}
        return clean(line), nodes

    def catalog():
        return {table: [clean(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                for table in ("opening_types", "opening_categories", "opening_tags")}

    def protected():
        keys = [conn.execute("SELECT line_key FROM opening_lines WHERE name=?", (name,)).fetchone()[0]
                for name in protected_names]
        return {key: line_and_nodes(key) for key in keys}

    try:
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        old_bundle()
        old_line, old_nodes = line_and_nodes(own_key)
        assert len(old_nodes) == 16
        assert json.loads(old_line["moves"]) == MOVES
        for key in ("main-1", "main-15", "main-16"):
            conn.execute("UPDATE opening_line_moves SET comment=? WHERE id=?", (f"E2f memo {key}", old_nodes[key]["id"]))
        for name in protected_names:
            line_id = conn.execute("SELECT id FROM opening_lines WHERE name=?", (name,)).fetchone()[0]
            conn.execute("UPDATE opening_line_moves SET comment=? WHERE line_id=? AND move_key='main-1'",
                         (f"protected memo {name}", line_id))
        # Project legacy comments using the OLD baseline before taking snapshots.
        old_bundle()
        old_line, old_nodes = line_and_nodes(own_key)
        old_protected, old_catalog = protected(), catalog()
        line_count = conn.execute("SELECT COUNT(*) FROM opening_lines").fetchone()[0]
        preserved_line_fields = (
            "id", "line_key", "seed_key", "name", "source_id", "opening_type_id", "opening_type",
            "initial_sfen", "moves", "comments", "tags", "source_url", "source_title", "license",
            "coverage_status", "source_type", "source_license", "created_at")

        def assert_preserved():
            current_line, current_nodes = line_and_nodes(own_key)
            assert {k: current_line[k] for k in preserved_line_fields} == {k: old_line[k] for k in preserved_line_fields}
            assert len(current_nodes) == 24
            assert set(current_nodes) - set(old_nodes) == {f"bishop-4e-{ply}" for ply in range(16, 24)}
            for key, node in old_nodes.items():
                assert current_nodes[key] == node  # includes ID, direct parent and nonempty comments
            assert protected() == old_protected
            assert catalog() == old_catalog
            assert conn.execute("SELECT COUNT(*) FROM opening_lines").fetchone()[0] == line_count
            assert_runtime_tree(conn, current_line["id"])
            assert compare_canonical_to_runtime(conn, artifact()["records"][0])["status"] == "unchanged"
            return current_line, current_nodes

        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        # No repair-like second import before these upgrade assertions.
        first_line, first_nodes = assert_preserved()
        for key in ("bishop-4e-16", "bishop-4e-21", "bishop-4e-23"):
            conn.execute("UPDATE opening_line_moves SET comment=? WHERE id=?", (f"E2g memo {key}", first_nodes[key]["id"]))
        expected = line_and_nodes(own_key)[1]
        for _ in range(2):
            seed_opening_catalog_if_empty(conn)
            seed_openings_if_empty(conn)
            apply_bundled_wikipedia_opening_artifacts(conn)
            _, current_nodes = assert_preserved()
            assert current_nodes == expected  # all 24 IDs/comments/direct parents, not just projection diff
            assert json.loads(line_and_nodes(own_key)[0]["comments"])[-1] == "E2f memo main-16"
        assert first_line["id"] == old_line["id"]
    finally:
        conn.close()
