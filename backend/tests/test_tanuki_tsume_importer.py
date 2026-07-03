import json

from app.importers.tanuki_tsume import import_tanuki, move_to_usi
from app.database import get_connection


def test_move_to_usi_supports_board_moves_and_drops():
    assert move_to_usi({"from": "5c", "to": "5b", "promote": True}) == "5c5b+"
    assert move_to_usi({"drop": "G", "to": "5b", "promote": False}) == "G*5b"


def test_import_tanuki_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "test.db"))
    fixture = tmp_path / "1.json"
    fixture.write_text(json.dumps([
        {
            "id": "sample-1",
            "mateLength": 1,
            "initial": "4k4/9/5+B3/9/9/9/9/9/9 b G 1",
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
        assert json.loads(row["solution_moves"]) == ["G*5b"]
        metadata = json.loads(row["source_metadata"])
        assert metadata["quality"] == "test"
        assert metadata["score"] == 10
    finally:
        conn.close()
