import random
import logging
import os

from app.database import get_connection
from app.next_move_database import get_next_move_write_connection, init_next_move_db
from app.next_move_resolver import clear_resolver_cache
from app.routers.next_move import select_next_problem

SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - {}"


def _seed_policy_data():
    init_next_move_db()
    conn = get_next_move_write_connection()
    source = conn.execute("""INSERT INTO book_sources(name,version,source_url,file_sha256)
      VALUES('policy','v1','https://example.test','digest')""").lastrowid
    ids = []
    for rank, opening, ply in ((1, "a", 1), (2, "a", 2), (3, "b", 3)):
        position = conn.execute("INSERT INTO book_positions(source_id,sfen) VALUES(?,?)",
                                (source, SFEN.format(ply))).lastrowid
        conn.execute("INSERT INTO book_moves(position_id,usi,sort_order) VALUES(?,?,0)",
                     (position, f"{rank}g{rank}f"))
        ids.append(conn.execute("""INSERT INTO learning_samples(book_source_id,book_position_id,
          opening_key,opening_name,sfen,sample_rank) VALUES(?,?,?,?,?,?)""",
          (source, position, opening, opening, SFEN.format(ply), rank)).lastrowid)
    # A second sample for the first semantic problem must not become another candidate.
    duplicate_source = conn.execute("""INSERT INTO book_sources(name,version,source_url,file_sha256)
      VALUES('policy','v1','https://example.test','other-digest')""").lastrowid
    duplicate_position = conn.execute("INSERT INTO book_positions(source_id,sfen) VALUES(?,?)",
                                      (duplicate_source, SFEN.format(1))).lastrowid
    conn.execute("INSERT INTO book_moves(position_id,usi,sort_order) VALUES(?,?,0)",
                 (duplicate_position, "1g1f"))
    ids.append(conn.execute("""INSERT INTO learning_samples(book_source_id,book_position_id,
      opening_key,opening_name,sfen,sample_rank) VALUES(?,?,?,?,?,?)""",
      (duplicate_source, duplicate_position, "a", "a", SFEN.format(1), 99)).lastrowid)
    conn.commit(); conn.close(); clear_resolver_cache()
    return ids


def test_random_selection_is_distinct_and_seedable():
    problems = [{"problem_key": "v1:a"}, {"problem_key": "v1:b"}]
    selected = select_next_problem(problems, policy="random", latest={}, rng=random.Random(0))
    assert selected == problems[1]


def test_unattempted_and_problem_key_exclusion():
    problems = [{"problem_key": "v1:a"}, {"problem_key": "v1:b"}]
    assert select_next_problem(problems, policy="unattempted", latest={"v1:a": {}},
                               rng=random.Random(0)) == problems[1]
    assert select_next_problem(problems, policy="random", latest={}, exclude_problem_key="v1:a",
                               rng=random.Random(0)) == problems[1]
    assert select_next_problem([problems[0]], policy="random", latest={},
                               exclude_problem_key="v1:a", rng=random.Random(0)) is None


def test_weak_uses_only_latest_listed_or_unlisted():
    problems = [{"problem_key": f"v1:{key}", "opening_key": "a"} for key in "abcde"]
    latest = {"v1:a": {"verdict": "top"}, "v1:b": {"verdict": "strong"},
              "v1:c": {"verdict": "listed"}, "v1:d": {"verdict": "unlisted"}}
    choices = {select_next_problem(problems, policy="weak", latest=latest,
                                   rng=random.Random(seed))["problem_key"] for seed in range(5)}
    assert choices == {"v1:c", "v1:d"}


def test_all_openings_are_chosen_before_problem_count():
    problems = ([{"problem_key": f"v1:a{i}", "opening_key": "a"} for i in range(10)]
                + [{"problem_key": "v1:b", "opening_key": "b"}])
    # Seed 0 chooses opening b. Direct choice over eleven problems would not.
    assert select_next_problem(problems, policy="random", latest={},
                               rng=random.Random(0))["opening_key"] == "b"


def test_selection_api_random_opening_exclude_and_detail_contract(client):
    ids = _seed_policy_data()
    all_items = client.get("/api/learning-samples?limit=100").json()["items"]
    assert len(all_items) == 3  # duplicate samples resolve to one problem_key
    response = client.get("/api/next-move/problems/next?policy=random&opening_key=b")
    assert response.status_code == 200
    assert response.json()["opening_key"] == "b"
    assert {"id", "problem_key"} <= response.json().keys()
    excluded = all_items[0]["problem_key"]
    choices = {client.get(f"/api/next-move/problems/next?policy=random&opening_key=a&exclude_problem_key={excluded}").json()["problem_key"] for _ in range(5)}
    assert choices == {all_items[1]["problem_key"]}
    assert client.get(f"/api/next-move/problems/next?policy=random&opening_key=b&exclude_problem_key={response.json()['problem_key']}").status_code == 204
    assert client.get("/api/next-move/problems/next?policy=random&exclude_problem_key=v1:not-present").status_code == 200
    assert client.get(f"/api/learning-samples/{ids[0]}").status_code == 200
    assert "/api/next-move/problems/next" in client.get("/openapi.json").json()["paths"]


def test_selection_api_unattempted_and_exhaustion(client):
    _seed_policy_data()
    items = client.get("/api/learning-samples?limit=100").json()["items"]
    history = get_connection()
    for item in items:
        history.execute("""INSERT INTO next_move_problem_refs(problem_key,stable_source_key,
          normalized_sfen,candidate_definition_fingerprint) VALUES(?,?,?,?)""",
          (item["problem_key"], "source", item["sfen"], "candidates"))
        history.execute("""INSERT INTO next_move_results(problem_key,opening_key_at_answer,
          opening_name_at_answer,move_usi,verdict,hint_count,elapsed_ms) VALUES(?,?,?,?,?,?,?)""",
          (item["problem_key"], item["opening_key"], item["opening_name"], "7g7f", "top", 0, 1))
        history.commit()
        response = client.get("/api/next-move/problems/next?policy=unattempted")
        if item != items[-1]:
            assert response.status_code == 200
            assert response.json()["problem_key"] not in {row["problem_key"] for row in items[:items.index(item) + 1]}
    assert response.status_code == 204
    history.close()


def test_malformed_exclude_warns_and_missing_database_is_503(client, tmp_path, caplog):
    _seed_policy_data()
    with caplog.at_level(logging.WARNING):
        assert client.get("/api/next-move/problems/next?policy=random&exclude_problem_key=bad").status_code == 200
    assert "malformed exclude_problem_key" in caplog.text
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "does-not-exist.db")
    clear_resolver_cache()
    assert client.get("/api/next-move/problems/next?policy=random").status_code == 503
