import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "test.db")
    from app.main import app

    with TestClient(app) as c:
        yield c
    os.environ.pop("SHOGI_DB_PATH", None)


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200


def test_seeded_problems(client):
    res = client.get("/api/tsume-problems")
    assert res.status_code == 200
    problems = res.json()
    assert len(problems) == 7
    lengths = sorted({p["mate_length"] for p in problems})
    assert lengths == [1, 3, 5]


def test_filter_by_mate_length(client):
    res = client.get("/api/tsume-problems", params={"mate_length": 3})
    assert res.status_code == 200
    assert all(p["mate_length"] == 3 for p in res.json())
    assert len(res.json()) == 3


def test_filter_by_tag(client):
    res = client.get("/api/tsume-problems", params={"tag": "頭金"})
    assert res.status_code == 200
    assert len(res.json()) >= 2
    assert all("頭金" in p["tags"] for p in res.json())


def test_get_problem(client):
    pid = client.get("/api/tsume-problems").json()[0]["id"]
    res = client.get(f"/api/tsume-problems/{pid}")
    assert res.status_code == 200
    body = res.json()
    assert body["initial_sfen"]
    assert isinstance(body["solution_moves"], list)


def test_get_problem_404(client):
    assert client.get("/api/tsume-problems/99999").status_code == 404


def test_create_problem_validates_mate(client):
    # 詰まない手順は 400 になる
    res = client.post(
        "/api/tsume-problems",
        json={
            "title": "invalid",
            "initial_sfen": "4k4/9/9/9/9/9/9/9/9 b G 1",
            "mate_length": 1,
            "solution_moves": ["G*5c"],
            "opponent_moves": [],
        },
    )
    assert res.status_code == 400


def test_create_and_update_and_delete_problem(client):
    body = {
        "title": "新規問題",
        "initial_sfen": "4k4/9/5+B3/9/9/9/9/9/9 b G 1",
        "mate_length": 1,
        "solution_moves": ["G*5b"],
        "opponent_moves": [],
        "difficulty": 1,
        "tags": ["1手詰", "頭金"],
        "explanation": "テスト",
    }
    res = client.post("/api/tsume-problems", json=body)
    assert res.status_code == 201
    pid = res.json()["id"]

    body["title"] = "更新済み"
    res = client.put(f"/api/tsume-problems/{pid}", json=body)
    assert res.status_code == 200
    assert res.json()["title"] == "更新済み"

    assert client.delete(f"/api/tsume-problems/{pid}").status_code == 204
    assert client.get(f"/api/tsume-problems/{pid}").status_code == 404


def test_record_result_and_stats(client):
    pid = client.get("/api/tsume-problems").json()[0]["id"]
    res = client.post(
        f"/api/tsume-problems/{pid}/result",
        json={"is_correct": True, "elapsed_ms": 4000, "mistake_count": 0},
    )
    assert res.status_code == 201
    res = client.post(
        f"/api/tsume-problems/{pid}/result",
        json={"is_correct": False, "elapsed_ms": 9000, "mistake_count": 2},
    )
    assert res.status_code == 201

    prob = client.get(f"/api/tsume-problems/{pid}").json()
    assert prob["stats"]["correct_count"] == 1
    assert prob["stats"]["wrong_count"] == 1
    assert prob["stats"]["avg_elapsed_ms"] == 6500

    stats = client.get("/api/stats").json()
    assert stats["overall"]["total_answers"] == 2
    assert stats["overall"]["total_correct"] == 1
    assert len(stats["recent_results"]) == 2


def test_review_problems(client):
    problems = client.get("/api/tsume-problems").json()
    wrong_id, right_id = problems[0]["id"], problems[1]["id"]
    client.post(
        f"/api/tsume-problems/{wrong_id}/result",
        json={"is_correct": False, "elapsed_ms": 1000, "mistake_count": 1},
    )
    client.post(
        f"/api/tsume-problems/{right_id}/result",
        json={"is_correct": True, "elapsed_ms": 1000, "mistake_count": 0},
    )
    review = client.get("/api/review-problems").json()
    ids = [p["id"] for p in review]
    assert wrong_id in ids
    assert right_id not in ids


def test_favorite(client):
    pid = client.get("/api/tsume-problems").json()[0]["id"]
    res = client.post(f"/api/tsume-problems/{pid}/favorite", json={"is_favorite": True})
    assert res.status_code == 200
    assert res.json()["is_favorite"] is True
    favs = client.get("/api/tsume-problems", params={"favorite": True}).json()
    assert [p["id"] for p in favs] == [pid]


def test_time_attack(client):
    res = client.post(
        "/api/time-attack/result",
        json={
            "mode": "normal",
            "mate_length": 1,
            "total_questions": 10,
            "correct_count": 8,
            "mistake_count": 2,
            "elapsed_ms": 123456,
        },
    )
    assert res.status_code == 201
    res = client.get("/api/time-attack/results")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["correct_count"] == 8


def test_random_order_with_limit(client):
    res = client.get(
        "/api/tsume-problems",
        params={"mate_length": 1, "random_order": True, "limit": 2},
    )
    assert res.status_code == 200
    assert len(res.json()) == 2
