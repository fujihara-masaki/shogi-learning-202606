import os
import sqlite3
from pathlib import Path

from app.database import get_connection, latest_next_move_result, latest_next_move_results
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
             (sample["problem_key"], "5a5b", 422, "NEXT_MOVE_ILLEGAL_MOVE"),
             (sample["problem_key"], "3c3d", 422, "NEXT_MOVE_ILLEGAL_MOVE"),
             (sample["problem_key"], "P*5e", 422, "NEXT_MOVE_ILLEGAL_MOVE"),
             (sample["problem_key"], "7g7f+", 422, "NEXT_MOVE_ILLEGAL_MOVE")]
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


def test_backend_calculates_top_strong_listed_and_unlisted(client):
    seed()
    db = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
    position_id = db.execute("SELECT book_position_id FROM learning_samples WHERE id=1").fetchone()[0]
    db.executemany("INSERT INTO book_moves(position_id,usi,score,depth,sort_order) VALUES(?,?,?,?,?)",
                   [(position_id, "5g5f", 5, 5, 2), (position_id, "9g9f", 1, 1, 3)])
    db.commit(); db.close()
    sample = client.get("/api/learning-samples/1").json()
    expected = [(sample["candidates"][0]["move_usi"], "top"), ("2g2f", "strong"),
                ("9g9f", "listed"), ("1g1f", "unlisted")]
    for move, verdict in expected:
        response = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
            "move_usi": move, "hint_count": 0, "elapsed_ms": 1})
        assert response.status_code == 200
        assert response.json()["verdict"] == verdict


def test_database_replacement_and_top_order_change_return_409(client):
    seed()
    original = client.get("/api/learning-samples/1").json()
    db = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
    db.execute("UPDATE learning_samples SET sfen=replace(sfen, ' b ', ' w ') WHERE id=1")
    db.commit(); db.close()
    response = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": original["problem_key"],
        "move_usi": "7g7f", "hint_count": 0, "elapsed_ms": 0})
    assert response.status_code == 409

    # Restore the position, make candidates tied, capture its key, then swap only their score order.
    db = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
    db.execute("UPDATE learning_samples SET sfen=? WHERE id=1", (original["sfen"],))
    position_id = db.execute("SELECT book_position_id FROM learning_samples WHERE id=1").fetchone()[0]
    db.execute("UPDATE book_moves SET sort_order=0, score=CASE usi WHEN '7g7f' THEN 100 ELSE 0 END WHERE position_id=?", (position_id,))
    db.commit(); db.close()
    tied = client.get("/api/learning-samples/1").json()
    db = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
    db.execute("UPDATE book_moves SET score=CASE usi WHEN '7g7f' THEN 0 ELSE 100 END WHERE position_id=?", (position_id,))
    db.commit(); db.close()
    response = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": tied["problem_key"],
        "move_usi": "7g7f", "hint_count": 0, "elapsed_ms": 0})
    assert response.status_code == 409


def test_source_sha_snapshot_is_saved_and_updated_without_changing_problem_key(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    for digest in ("first", "second"):
        db = sqlite3.connect(os.environ["NEXT_MOVE_DB_PATH"])
        db.execute("UPDATE book_sources SET file_sha256=?", (digest,)); db.commit(); db.close()
        current = client.get("/api/learning-samples/1").json()
        assert current["problem_key"] == sample["problem_key"]
        assert client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
            "move_usi": "7g7f", "hint_count": 0, "elapsed_ms": 0}).status_code == 200
        conn = get_connection()
        try: assert conn.execute("SELECT last_source_file_sha256 FROM next_move_problem_refs").fetchone()[0] == digest
        finally: conn.close()


def test_result_insert_failure_rolls_back_problem_ref(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    conn = get_connection()
    conn.execute("CREATE TRIGGER fail_result BEFORE INSERT ON next_move_results BEGIN SELECT RAISE(ABORT, 'boom'); END")
    conn.commit(); conn.close()
    response = client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
        "move_usi": "7g7f", "hint_count": 0, "elapsed_ms": 0})
    assert response.status_code == 500
    conn = get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM next_move_problem_refs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM next_move_results").fetchone()[0] == 0
    finally: conn.close()


def test_latest_result_uses_id_for_same_second(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    for move in ("7g7f", "5g5f"):
        assert client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
            "move_usi": move, "hint_count": 0, "elapsed_ms": 0}).status_code == 200
    conn = get_connection()
    try:
        conn.execute("UPDATE next_move_results SET answered_at='2026-01-01 00:00:00'"); conn.commit()
        assert latest_next_move_result(conn, sample["problem_key"])["move_usi"] == "5g5f"
    finally: conn.close()


def test_progress_and_status_share_latest_distinct_result(client):
    seed()
    sample = client.get("/api/learning-samples/1").json()
    initial = client.get("/api/next-move/progress").json()["openings"][0]
    assert initial["total"] == 1 and initial["answered"] == 0
    assert client.get(f"/api/next-move/status?opening_key={sample['opening_key']}").json()["items"][0]["verdict"] is None
    for move in (sample["candidates"][0]["move_usi"], "5g5f"):
        client.post("/api/next-move/results", json={"sample_id": 1, "problem_key": sample["problem_key"],
            "move_usi": move, "hint_count": 0, "elapsed_ms": 1})
    conn = get_connection()
    conn.execute("UPDATE next_move_results SET answered_at='2026-01-01 00:00:00'")
    conn.commit(); conn.close()
    progress = client.get("/api/next-move/progress").json()["openings"][0]
    status = client.get(f"/api/next-move/status?opening_key={sample['opening_key']}").json()["items"][0]
    assert progress["answered"] == 1
    assert progress["verdict_counts"]["unlisted"] == 1
    assert status["verdict"] == "unlisted"


def test_bulk_latest_results_chunks_more_than_1000_keys_and_deduplicates(client):
    conn = get_connection()
    keys = [f"problem-{index}" for index in range(1201)]
    conn.executemany("""INSERT INTO next_move_problem_refs(
        problem_key,stable_source_key,normalized_sfen,candidate_definition_fingerprint)
        VALUES(?,?,?,?)""", [(key, "source", "sfen", "candidates") for key in keys])
    conn.executemany("""INSERT INTO next_move_results(
        problem_key,move_usi,verdict,hint_count,elapsed_ms,answered_at)
        VALUES(?,?,?,?,?,?)""", [(key, "7g7f", "top", 0, 1, "2026-01-01 00:00:00") for key in keys])
    # Same timestamp must still select the larger result id.
    conn.execute("""INSERT INTO next_move_results(
        problem_key,move_usi,verdict,hint_count,elapsed_ms,answered_at)
        VALUES(?,?,?,?,?,?)""", (keys[-1], "5g5f", "unlisted", 0, 1, "2026-01-01 00:00:00"))
    conn.commit()
    previous_limit = conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 500)
    try:
        assert latest_next_move_results(conn, []) == {}
        results = latest_next_move_results(conn, keys + keys[:25])
    finally:
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous_limit)
        conn.close()
    assert len(results) == 1201
    assert results[keys[0]]["verdict"] == "top"
    assert results[keys[-1]]["verdict"] == "unlisted"
