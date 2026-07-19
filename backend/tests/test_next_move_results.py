from pathlib import Path

from app.database import get_connection, latest_next_move_result
from app.importers.yaneuraou_book import import_book
from app.learning_samples import build_learning_sample_plan

FIXTURE = Path(__file__).parent / "fixtures" / "yaneuraou_book_sample.db"


def seed():
    source = import_book(FIXTURE, name="Results fixture", license_name="MIT", source_url="https://example.test", limit=1)
    build_learning_sample_plan(source.source_id, limit=1, per_opening_limit=1, seed=1, dry_run=False)


def test_records_top_and_unlisted_answers_transactionally(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    top = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
        "move_usi": sample["candidates"][0]["move_usi"], "hint_count": 1, "elapsed_ms": 25})
    assert top.status_code == 200
    assert top.json()["verdict"] == "top"
    unlisted = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
        "move_usi": "5g5f", "hint_count": 0, "elapsed_ms": 30})
    assert unlisted.status_code == 200
    assert unlisted.json()["verdict"] == "unlisted"
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM next_move_problem_refs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM next_move_results").fetchone()[0] == 2
        assert latest_next_move_result(conn, sample["problem_key"])["id"] == unlisted.json()["id"]
    finally: conn.close()


def test_rejects_changed_key_invalid_and_illegal_moves_without_writes(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    cases = [("wrong", "7g7f", 409, "NEXT_MOVE_PROBLEM_CHANGED"),
             (sample["problem_key"], "bad", 422, "NEXT_MOVE_MOVE_FORMAT_INVALID"),
             (sample["problem_key"], "5a5b", 422, "NEXT_MOVE_ILLEGAL_MOVE")]
    for key, move, status, code in cases:
        response = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": key,
            "move_usi": move, "hint_count": 0, "elapsed_ms": 0})
        assert response.status_code == status
        assert response.json()["code"] == code
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM next_move_problem_refs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM next_move_results").fetchone()[0] == 0
    finally: conn.close()
