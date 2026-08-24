import json
from pathlib import Path

import shogi

from app.database import get_connection, init_db
from app.seed import (
    apply_bundled_wikipedia_opening_artifacts,
    seed_if_empty,
    seed_opening_catalog_if_empty,
    seed_openings_if_empty,
)
from app.wikipedia_opening_importer import compare_canonical_to_legacy, compare_canonical_to_runtime
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact


ARTIFACT_PATH = Path(__file__).parents[1] / "app/wikipedia_opening_artifacts/new-haya-ishida.json"
LINE_NAME = "新・早石田（鈴木流急戦・Wikipedia明示手順）"


def _artifact():
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_canonical_artifact_legality_and_coverage_boundary():
    artifact = _artifact()
    assert validate_wikipedia_opening_artifact(artifact) == ()
    record = artifact["records"][0]
    assert record["revision"] == 107928861
    assert "oldid=107928861" in record["source"]["url"]
    assert record["coverage"] == {
        "covered_through_ply": 17,
        "covered_through_move": "B*5e",
        "omitted_after": {"usi": "P*7c", "note": "同節に続きとして明記される次の手。"},
    }
    board = shogi.Board(record["initial_sfen"])
    for node in record["nodes"]:
        assert node["from_sfen"] == board.sfen()
        move = shogi.Move.from_usi(node["usi"])
        assert move in board.legal_moves
        board.push(move)
        assert node["to_sfen"] == board.sfen()
    assert shogi.Move.from_usi("P*7c") in board.legal_moves

    legacy = json.loads(
        (Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json").read_text(encoding="utf-8")
    )
    comparison = compare_canonical_to_legacy(record, legacy)
    assert comparison["status"] == "changed"
    assert comparison["unverifiable"] == ["revision", "review", "canonical_url"]
    assert [node["key"] for node in comparison["nodes"] if node["status"] == "added"] == [
        f"main-{ply}" for ply in range(8, 18)
    ]


def test_normal_seed_claims_existing_line_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        seed_openings_if_empty(conn)
        old = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchone()
        old_nodes = conn.execute(
            "SELECT id, move_key, comment FROM opening_line_moves WHERE line_id=? ORDER BY ply", (old["id"],)
        ).fetchall()
        old_other = conn.execute("SELECT id, updated_at FROM opening_lines WHERE name='棒銀'").fetchone()
        conn.commit()
    finally:
        conn.close()

    seed_if_empty()
    seed_if_empty()
    conn = get_connection()
    try:
        seed_openings_if_empty(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        apply_bundled_wikipedia_opening_artifacts(conn)
        rows = conn.execute("SELECT * FROM opening_lines WHERE name=?", (LINE_NAME,)).fetchall()
        assert len(rows) == 1
        line = rows[0]
        assert line["id"] == old["id"]
        assert line["line_key"] == "wikipedia.ishida.new-haya-ishida"
        assert line["seed_key"] == f"sample:{LINE_NAME}"
        assert line["source_url"].endswith("oldid=107928861")
        assert (line["source_section"], line["source_license"], line["source_retrieved_at"]) == (
            "新・早石田", "CC BY-SA 4.0", "2026-08-24"
        )
        assert line["opening_type_id"] == old["opening_type_id"]
        assert line["tags"] == old["tags"]
        nodes = conn.execute(
            "SELECT * FROM opening_line_moves WHERE line_id=? ORDER BY ply", (line["id"],)
        ).fetchall()
        assert len(nodes) == 17 and nodes[-1]["usi"] == "B*5e"
        assert [row["id"] for row in nodes[:7]] == [row["id"] for row in old_nodes]
        assert [row["comment"] for row in nodes[:7]] == [row["comment"] for row in old_nodes]
        assert [row["parent_move_id"] for row in nodes] == [None, *[row["id"] for row in nodes[:-1]]]
        positions = conn.execute(
            "SELECT ply FROM opening_positions WHERE line_id=? ORDER BY ply", (line["id"],)
        ).fetchall()
        assert [row["ply"] for row in positions] == list(range(18))
        report = compare_canonical_to_runtime(conn, _artifact()["records"][0])
        assert report["status"] == "unchanged"
        assert conn.execute("SELECT id, updated_at FROM opening_lines WHERE name='棒銀'").fetchone()["id"] == old_other["id"]
    finally:
        conn.close()


def test_api_returns_canonical_main_tree_and_attribution(client):
    line = next(row for row in client.get("/api/openings").json() if row["name"] == LINE_NAME)
    detail = client.get(f"/api/openings/{line['id']}").json()
    assert line["move_count"] == 17
    assert len(detail["moves"]) == 17
    assert detail["moves"][-1]["usi"] == "B*5e"
    assert all(node["is_main"] for node in detail["moves"])
    assert detail["source"]["source_url"].endswith("oldid=107928861")
    assert detail["source"]["source_section"] == "新・早石田"
    assert [tag["tag"] for tag in detail["tags"]] == ["haya_ishida"]
    assert detail["opening_type"] == "振り飛車"
