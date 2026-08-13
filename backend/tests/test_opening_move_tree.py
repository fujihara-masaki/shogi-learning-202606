import sqlite3

import pytest
import shogi

from app.database import get_connection
from app import seed
from app.seed import _prepare_opening_move_nodes, seed_openings_if_empty, validate_opening_move_tree


TREE_SEED = {
    "name": "stable-key multi-level fixture",
    "opening_type": "test",
    "description": "stable key tree fixture",
    "tag": "stable-key-tree",
    "move_nodes": [
        {"key": "m1", "parent_key": None, "usi": "7g7f", "sort_order": 0, "is_main": True},
        {"key": "m2", "parent_key": "m1", "usi": "3c3d", "sort_order": 0, "is_main": True},
        # Display B first, but follow A as the semantic main choice.
        {"key": "b", "parent_key": "m2", "usi": "2g2f", "sort_order": 0, "is_main": False,
         "branch_key": "b", "branch_label": "B", "comment": "explicit B comment"},
        {"key": "a", "parent_key": "m2", "usi": "6g6f", "sort_order": 1, "is_main": True,
         "branch_key": "a", "branch_label": "A"},
        {"key": "a1", "parent_key": "a", "usi": "8c8d", "sort_order": 0, "is_main": False},
        {"key": "a2", "parent_key": "a", "usi": "4c4d", "sort_order": 1, "is_main": True},
    ],
}


def _line_and_rows(conn):
    line = conn.execute(
        "SELECT ol.id FROM opening_lines ol WHERE ol.source_id IS NULL ORDER BY (SELECT COUNT(*) FROM opening_line_moves m WHERE m.line_id=ol.id) DESC, ol.id LIMIT 1"
    ).fetchone()
    rows = conn.execute(
        "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply, id", (line["id"],)
    ).fetchall()
    return line["id"], rows


def test_seed_tree_is_direct_valid_and_reseed_is_idempotent(client):
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) AS count FROM opening_line_moves").fetchone()["count"]
        seed_openings_if_empty(conn)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) AS count FROM opening_line_moves").fetchone()["count"]
        assert after == before
        validate_opening_move_tree(conn)
        line_id, rows = _line_and_rows(conn)
        assert all(row["parent_move_id"] is not None for row in rows if row["ply"] > 1)
        detail = client.get(f"/api/openings/{line_id}").json()
        assert {"id", "parent_move_id", "move_key", "is_main", "sort_order"} <= detail["moves"][0].keys()
    finally:
        conn.close()


def test_stable_key_seed_persists_branch_of_branch_and_reseeds_by_natural_key(client, monkeypatch):
    monkeypatch.setattr(seed, "SAMPLE_OPENING_LINES", [TREE_SEED])
    conn = get_connection()
    try:
        seed_openings_if_empty(conn)
        conn.commit()
        line = conn.execute("SELECT id FROM opening_lines WHERE name=?", (TREE_SEED["name"],)).fetchone()
        rows = conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply, sort_order", (line["id"],)
        ).fetchall()
        first_ids = {row["move_key"]: row["id"] for row in rows}

        seed_openings_if_empty(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply, sort_order", (line["id"],)
        ).fetchall()
        assert {row["move_key"]: row["id"] for row in rows} == first_ids
        assert len(rows) == len(TREE_SEED["move_nodes"])

        by_key = {row["move_key"]: row for row in rows}
        assert by_key["a1"]["parent_move_id"] == by_key["a"]["id"]
        assert by_key["a2"]["parent_move_id"] == by_key["a"]["id"]
        assert by_key["a"]["sort_order"] == 1 and by_key["a"]["is_main"] == 1
        assert by_key["b"]["sort_order"] == 0 and by_key["b"]["is_main"] == 0
        assert by_key["a"]["variation_group"] == "A"
        assert by_key["b"]["variation_group"] == "B"
        assert by_key["a"]["comment"] == ""
        assert by_key["b"]["comment"] == "explicit B comment"
        for row in rows:
            if row["parent_move_id"] is not None:
                parent = next(candidate for candidate in rows if candidate["id"] == row["parent_move_id"])
                assert row["ply"] == parent["ply"] + 1
                assert row["from_sfen"] == parent["to_sfen"]
        validate_opening_move_tree(conn, [line["id"]])

        detail = client.get(f"/api/openings/{line['id']}")
        assert detail.status_code == 200
        api_by_key = {row["move_key"]: row for row in detail.json()["moves"]}
        assert api_by_key["a1"]["parent_move_id"] == api_by_key["a"]["id"]
        assert api_by_key["a2"]["parent_move_id"] == api_by_key["a"]["id"]
        assert api_by_key["a"]["variation_group"] == "A"
        assert api_by_key["b"]["variation_group"] == "B"
    finally:
        conn.close()


def test_stable_key_reseed_prunes_obsolete_nodes_and_positions(client, monkeypatch):
    monkeypatch.setattr(seed, "SAMPLE_OPENING_LINES", [TREE_SEED])
    conn = get_connection()
    try:
        seed_openings_if_empty(conn)
        line = conn.execute("SELECT id FROM opening_lines WHERE name=?", (TREE_SEED["name"],)).fetchone()
        original = {
            row["move_key"]: row["id"]
            for row in conn.execute(
                "SELECT id, move_key FROM opening_line_moves WHERE line_id=?", (line["id"],)
            )
        }

        revised = {**TREE_SEED, "move_nodes": [
            *TREE_SEED["move_nodes"][:2],
            # Reuse removed B's USI under a new stable key.
            {"key": "c", "parent_key": "m2", "usi": "2g2f", "sort_order": 0,
             "is_main": False, "branch_key": "c", "branch_label": "C"},
            TREE_SEED["move_nodes"][3],
        ]}
        monkeypatch.setattr(seed, "SAMPLE_OPENING_LINES", [revised])
        seed_openings_if_empty(conn)
        seed_openings_if_empty(conn)
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply, sort_order", (line["id"],)
        ).fetchall()
        by_key = {row["move_key"]: row for row in rows}
        assert set(by_key) == {"m1", "m2", "a", "c"}
        assert by_key["m1"]["id"] == original["m1"]
        assert by_key["m2"]["id"] == original["m2"]
        assert by_key["a"]["id"] == original["a"]
        assert by_key["a"]["parent_move_id"] == by_key["m2"]["id"]
        assert all(row["sort_order"] >= 0 for row in rows)
        assert conn.execute(
            "SELECT MAX(ply) AS max_ply FROM opening_positions WHERE line_id=?", (line["id"],)
        ).fetchone()["max_ply"] == 3
        validate_opening_move_tree(conn, [line["id"]])

        api_keys = {
            row["move_key"] for row in client.get(f"/api/openings/{line['id']}").json()["moves"]
        }
        assert api_keys == set(by_key)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        ([{"key": "x", "parent_key": "missing", "usi": "7g7f", "is_main": True}], "missing.*parent_key"),
        ([{"key": "x", "parent_key": None, "usi": "7g7f", "is_main": True},
          {"key": "x", "parent_key": None, "usi": "2g2f", "is_main": False}], "duplicate.*key"),
        ([{"key": "x", "parent_key": "y", "usi": "7g7f", "is_main": True},
          {"key": "y", "parent_key": "x", "usi": "3c3d", "is_main": True}], "cycle"),
        ([{"key": "x", "parent_key": None, "usi": "7g7g", "is_main": True}], "illegal.*USI"),
    ],
)
def test_stable_key_seed_rejects_invalid_graphs(nodes, message):
    with pytest.raises(ValueError, match=message):
        _prepare_opening_move_nodes({"move_nodes": nodes}, shogi.STARTING_SFEN)


def test_root_sort_order_is_unique_but_distinct_root_orders_are_allowed(client):
    conn = get_connection()
    try:
        line_id, rows = _line_and_rows(conn)
        root = next(row for row in rows if row["parent_move_id"] is None)
        values = (line_id, root["ply"], root["usi"], root["from_sfen"], root["to_sfen"], "extra-root")
        sql = """INSERT INTO opening_line_moves
                 (line_id, ply, usi, from_sfen, to_sfen, variation_group,
                  parent_move_id, sort_order, move_key, is_main)
                 VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)"""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (*values, root["sort_order"], "duplicate-root", 0))

        distinct_order = root["sort_order"] + 1
        conn.execute(sql, (*values, distinct_order, "distinct-root", 0))
        assert conn.execute(
            """SELECT 1 FROM opening_line_moves
               WHERE line_id=? AND parent_move_id IS NULL AND sort_order=?""",
            (line_id, distinct_order),
        ).fetchone()
    finally:
        conn.rollback()
        conn.close()


def test_tree_validator_normalizes_root_and_initial_positions(client):
    conn = get_connection()
    try:
        line_id, rows = _line_and_rows(conn)
        root = next(row for row in rows if row["parent_move_id"] is None)

        # The persisted full SFEN and its startpos alias describe one position.
        conn.execute("UPDATE opening_lines SET initial_sfen='startpos' WHERE id=?", (line_id,))
        validate_opening_move_tree(conn, [line_id])
        conn.execute(
            "UPDATE opening_lines SET initial_sfen=? WHERE id=?",
            (shogi.STARTING_SFEN, line_id),
        )
        conn.execute("UPDATE opening_line_moves SET from_sfen='startpos' WHERE id=?", (root["id"],))
        validate_opening_move_tree(conn, [line_id])

        # Use another valid position and a legal move from it; validation must
        # still reject the root because it is unrelated to the line's initial position.
        board = shogi.Board()
        board.push_usi("7g7f")
        unrelated_from = board.sfen()
        board.push_usi("3c3d")
        conn.execute(
            "UPDATE opening_line_moves SET usi='3c3d', from_sfen=?, to_sfen=? WHERE id=?",
            (unrelated_from, board.sfen(), root["id"]),
        )
        with pytest.raises(ValueError, match="root/initial SFEN mismatch"):
            validate_opening_move_tree(conn, [line_id])
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("UPDATE opening_line_moves SET is_main=0 WHERE line_id=? AND parent_move_id IS NULL", "exactly one main"),
        ("UPDATE opening_line_moves SET is_main=1 WHERE line_id=? AND parent_move_id=(SELECT parent_move_id FROM opening_line_moves WHERE line_id=? AND parent_move_id IS NOT NULL GROUP BY parent_move_id HAVING COUNT(*) > 1 LIMIT 1)", "exactly one main"),
        ("UPDATE opening_line_moves SET parent_move_id=999999 WHERE id=(SELECT id FROM opening_line_moves WHERE line_id=? ORDER BY ply DESC LIMIT 1)", "invalid opening parent"),
        ("UPDATE opening_line_moves SET parent_move_id=id WHERE id=(SELECT id FROM opening_line_moves WHERE line_id=? ORDER BY ply DESC LIMIT 1)", "opening cycle"),
        ("UPDATE opening_line_moves SET from_sfen='invalid sfen' WHERE id=(SELECT id FROM opening_line_moves WHERE line_id=? ORDER BY ply DESC LIMIT 1)", "SFEN mismatch"),
        ("UPDATE opening_line_moves SET usi='7g7g' WHERE id=(SELECT id FROM opening_line_moves WHERE line_id=? ORDER BY ply DESC LIMIT 1)", "illegal opening move"),
    ],
)
def test_tree_validator_rejects_broken_contract(client, mutation, message):
    conn = get_connection()
    try:
        line_id, _ = _line_and_rows(conn)
        if message == "invalid opening parent":
            conn.execute("PRAGMA foreign_keys=OFF")
        placeholders = mutation.count("?")
        conn.execute(mutation, tuple(line_id for _ in range(placeholders)))
        with pytest.raises((ValueError, Exception), match=message):
            validate_opening_move_tree(conn, [line_id])
    finally:
        conn.rollback()
        conn.close()
