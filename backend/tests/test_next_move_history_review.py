import os

from app.database import get_connection
from app.next_move_database import get_next_move_write_connection, init_next_move_db
from app.next_move_resolver import clear_resolver_cache

SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - {}"


def seed_problems(count=5):
    init_next_move_db()
    conn = get_next_move_write_connection()
    source = conn.execute("""INSERT INTO book_sources(name,version,source_url,file_sha256)
        VALUES('history','v1','https://example.test','one')""").lastrowid
    for index in range(count):
        position = conn.execute("INSERT INTO book_positions(source_id,sfen) VALUES(?,?)",
                                (source, SFEN.format(index + 1))).lastrowid
        conn.execute("INSERT INTO book_moves(position_id,usi,sort_order) VALUES(?,?,0)",
                     (position, f"{index + 1}g{index + 1}f"))
        conn.execute("""INSERT INTO learning_samples(book_source_id,book_position_id,opening_key,
            opening_name,sfen,sample_rank) VALUES(?,?,?,?,?,?)""",
            (source, position, f"opening-{index}", f"戦型{index}", SFEN.format(index + 1), index + 1))
    conn.commit(); conn.close(); clear_resolver_cache()
    return []


def current_items(client):
    return client.get("/api/learning-samples?limit=100").json()["items"]


def add_result(problem, verdict, *, answered_at="2026-01-01 00:00:00", snapshot=None):
    conn = get_connection()
    conn.execute("""INSERT OR IGNORE INTO next_move_problem_refs(problem_key,stable_source_key,
        normalized_sfen,candidate_definition_fingerprint) VALUES(?,?,?,?)""",
        (problem["problem_key"], "source", problem["sfen"], "candidates"))
    opening_key, opening_name = snapshot or (problem["opening_key"], problem["opening_name"])
    cursor = conn.execute("""INSERT INTO next_move_results(problem_key,opening_key_at_answer,
        opening_name_at_answer,move_usi,verdict,hint_count,elapsed_ms,answered_at)
        VALUES(?,?,?,?,?,?,?,?)""", (problem["problem_key"], opening_key, opening_name,
        "7g7f", verdict, 0, 1234, answered_at))
    conn.commit(); result_id = cursor.lastrowid; conn.close()
    return result_id


def test_weak_api_uses_sqlite_rows_latest_verdict_exclusion_and_204(client):
    seed_problems(); items = current_items(client)
    add_result(items[0], "listed"); add_result(items[1], "unlisted")
    add_result(items[2], "top"); add_result(items[3], "strong")
    # items[4] is unattempted. This calls the real latest helper returning sqlite3.Row.
    choices = {client.get("/api/next-move/problems/next?policy=weak").json()["problem_key"]
               for _ in range(20)}
    assert choices == {items[0]["problem_key"], items[1]["problem_key"]}
    excluded = items[0]["problem_key"]
    response = client.get(f"/api/next-move/problems/next?policy=weak&exclude_problem_key={excluded}")
    assert response.status_code == 200 and response.json()["problem_key"] == items[1]["problem_key"]
    add_result(items[1], "top", answered_at="2026-01-02 00:00:00")
    assert client.get(f"/api/next-move/problems/next?policy=weak&exclude_problem_key={excluded}").status_code == 204


def test_history_counts_rate_order_current_metadata_and_snapshot_immutability(client):
    seed_problems(2); first, second = current_items(client)
    first_id = add_result(first, "top", snapshot=("old", "旧戦型"))
    second_id = add_result(second, "listed")
    add_result(first, "unlisted", answered_at="2026-01-02 00:00:00")
    data = client.get("/api/next-move/history").json()
    assert data["total_answers"] == 3
    assert data["verdict_counts"] == {"top": 1, "strong": 0, "listed": 1, "unlisted": 1}
    assert data["top_rate"] == 1 / 3
    assert [row["id"] for row in data["recent_results"]] == [3, second_id, first_id]
    assert data["recent_results"][-1]["opening_name"] == first["opening_name"]
    db = get_next_move_write_connection()
    db.execute("UPDATE learning_samples SET opening_key='new', opening_name='新戦型' WHERE id=?", (first["id"],))
    db.commit(); db.close(); clear_resolver_cache()
    assert client.get("/api/next-move/history").json()["recent_results"][-1]["opening_name"] == "新戦型"
    history = get_connection()
    snapshot = history.execute("SELECT opening_key_at_answer,opening_name_at_answer FROM next_move_results WHERE id=?", (first_id,)).fetchone()
    history.close()
    assert tuple(snapshot) == ("old", "旧戦型")


def test_history_deleted_and_missing_database_use_snapshots(client, tmp_path):
    seed_problems(1); problem = current_items(client)[0]
    add_result(problem, "top", snapshot=("snapshot", "解答時戦型"))
    db = get_next_move_write_connection(); db.execute("DELETE FROM learning_samples"); db.commit(); db.close(); clear_resolver_cache()
    item = client.get("/api/next-move/history").json()["recent_results"][0]
    assert (item["opening_name"], item["sample_id"], item["available"]) == ("解答時戦型", None, False)
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "missing.db"); clear_resolver_cache()
    response = client.get("/api/next-move/history")
    assert response.status_code == 200 and response.json()["recent_results"][0]["opening_key"] == "snapshot"


def test_review_tie_breaks_latest_and_filters_verdicts(client):
    seed_problems(4); listed_top, top_listed, unlisted, strong = current_items(client)
    add_result(listed_top, "listed"); add_result(listed_top, "top")
    add_result(top_listed, "top"); latest_id = add_result(top_listed, "listed")
    add_result(unlisted, "unlisted"); add_result(strong, "strong")
    review = client.get("/api/next-move/review").json()["items"]
    assert {item["problem_key"] for item in review} == {top_listed["problem_key"], unlisted["problem_key"]}
    reviewed = next(item for item in review if item["problem_key"] == top_listed["problem_key"])
    status = client.get(f"/api/next-move/status?opening_key={top_listed['opening_key']}").json()["items"][0]
    assert reviewed["result_id"] == status["result_id"] == latest_id
    progress = client.get("/api/next-move/progress").json()["openings"]
    opening_progress = next(item for item in progress if item["opening_key"] == top_listed["opening_key"])
    assert opening_progress["verdict_counts"]["listed"] == 1


def test_review_deduplicates_current_samples_and_uses_current_or_snapshot_metadata(client, tmp_path):
    seed_problems(1); problem = current_items(client)[0]
    add_result(problem, "listed", snapshot=("old", "旧戦型"))
    db = get_next_move_write_connection()
    db.execute("UPDATE learning_samples SET opening_key='new', opening_name='新戦型'")
    source = db.execute("""INSERT INTO book_sources(name,version,source_url,file_sha256)
        VALUES('history','v1','https://example.test','duplicate')""").lastrowid
    position = db.execute("INSERT INTO book_positions(source_id,sfen) VALUES(?,?)", (source, problem["sfen"])).lastrowid
    db.execute("INSERT INTO book_moves(position_id,usi,sort_order) VALUES(?,?,0)", (position, "1g1f"))
    db.execute("""INSERT INTO learning_samples(book_source_id,book_position_id,opening_key,opening_name,sfen,sample_rank)
        VALUES(?,?,?,?,?,99)""", (source, position, "new", "新戦型", problem["sfen"]))
    db.commit(); db.close(); clear_resolver_cache()
    review = client.get("/api/next-move/review").json()["items"]
    assert len(review) == 1 and review[0]["opening_name"] == "新戦型" and review[0]["available"]
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "missing.db"); clear_resolver_cache()
    missing = client.get("/api/next-move/review").json()["items"]
    assert len(missing) == 1 and missing[0]["opening_name"] == "旧戦型"
    assert missing[0]["sample_id"] is None and not missing[0]["available"]
