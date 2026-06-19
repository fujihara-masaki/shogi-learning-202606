def valid_body():
    return {
        "title": "API作成テスト",
        "initial_sfen": "4k4/9/5+B3/9/9/9/9/9/9 b G 1",
        "mate_length": 1,
        "solution_moves": ["G*5b"],
        "opponent_moves": [],
        "difficulty": 1,
        "tags": ["api"],
        "explanation": "金で詰み",
        "is_favorite": True,
    }


def test_validate_create_update_delete_problem(client):
    body = valid_body()
    res = client.post("/api/tsume-problems/validate", json=body)
    assert res.status_code == 200
    assert res.json()["valid"] is True

    res = client.post("/api/tsume-problems", json=body)
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["is_favorite"] is True

    updated_body = {**body, "title": "更新後", "is_favorite": False, "tags": ["updated"]}
    res = client.put(f"/api/tsume-problems/{created['id']}", json=updated_body)
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "更新後"
    assert res.json()["is_favorite"] is False

    res = client.delete(f"/api/tsume-problems/{created['id']}")
    assert res.status_code == 204
    assert client.get(f"/api/tsume-problems/{created['id']}").status_code == 404


def test_validate_reports_errors(client):
    bad = {**valid_body(), "initial_sfen": "bad", "solution_moves": ["bad"]}
    res = client.post("/api/tsume-problems/validate", json=bad)
    assert res.status_code == 200
    assert res.json()["valid"] is False
    assert res.json()["errors"]
