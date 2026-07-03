import json

from app.database import get_connection
from app.importers.tanuki_tsume import import_tanuki, initial_to_sfen, move_to_usi


TANUKI_INITIAL = {
    "pieces": [
        {"type": "K", "owner": "defender", "square": "5a"},
        {"type": "+B", "owner": "attacker", "square": "4c"},
        {"type": "+R", "owner": "defender", "square": "9i"},
    ],
    "hands": {
        "attacker": {"G": 1, "P": 2},
        "defender": {"R": 1, "p": 3},
    },
    "sideToMove": "attacker",
}


def test_move_to_usi_supports_board_moves_and_drops():
    assert move_to_usi({"from": "5c", "to": "5b", "promote": True}) == "5c5b+"
    assert move_to_usi({"drop": "G", "to": "5b", "promote": False}) == "G*5b"


def test_initial_to_sfen_converts_tanuki_initial_object():
    assert initial_to_sfen(TANUKI_INITIAL) == "4k4/9/5+B3/9/9/9/9/9/+r8 b G2Pr3p 1"


def test_import_tanuki_is_idempotent_with_real_initial_object(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "test.db"))
    fixture = tmp_path / "1.json"
    fixture.write_text(json.dumps([
        {
            "id": "sample-1",
            "mateLength": 1,
            "initial": TANUKI_INITIAL,
            "solution": [{"drop": "G", "to": "5b", "promote": False}],
            "quality": "test",
            "score": 10,
            "hash": "hash-sample-1",
        }
    ]), encoding="utf-8")

    first = import_tanuki([str(fixture)])
    second = import_tanuki([str(fixture)])
    assert first == {"total": 1, "imported": 1, "skipped": 0}
    assert second == {"total": 1, "imported": 0, "skipped": 1}

    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM tsume_problems WHERE source_name = 'tokuhirom/tanuki-tsume-shogi'").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["external_id"] == "sample-1"
        assert row["source_hash"] == "hash-sample-1"
        assert isinstance(row["initial_sfen"], str)
        assert row["initial_sfen"] == "4k4/9/5+B3/9/9/9/9/9/+r8 b G2Pr3p 1"
        assert json.loads(row["solution_moves"]) == ["G*5b"]
        metadata = json.loads(row["source_metadata"])
        assert metadata["initial"] == TANUKI_INITIAL
        assert metadata["quality"] == "test"
        assert metadata["score"] == 10
    finally:
        conn.close()
