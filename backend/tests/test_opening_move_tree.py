import pytest
import shogi

from app.database import get_connection
from app.seed import seed_openings_if_empty, validate_opening_move_tree


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
