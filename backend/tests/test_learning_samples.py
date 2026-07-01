import os
from pathlib import Path

import pytest

from app.database import get_connection, init_db
from app.importers.yaneuraou_book import import_book
from app.learning_samples import build_learning_sample_plan

FIXTURE = Path(__file__).parent / "fixtures" / "yaneuraou_book_sample.db"


def count_samples():
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM learning_samples").fetchone()[0]
    finally:
        conn.close()


def imported_source(tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "samples.db")
    result = import_book(FIXTURE, name="sample", license_name="MIT")
    return result.source_id


def test_extracts_samples_from_small_yaneuraou_fixture(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=10, per_opening_limit=10, seed=1, dry_run=False)
    assert plan.selected_count == 4
    assert count_samples() == 4
    assert "unclassified" in plan.by_opening


def test_limit_is_applied(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=2, per_opening_limit=10, seed=1, dry_run=False)
    assert plan.selected_count == 2
    assert count_samples() == 2


def test_per_opening_limit_is_applied(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=10, per_opening_limit=1, seed=1, dry_run=False)
    assert plan.by_opening["unclassified"]["selected_count"] == 1
    assert all(summary["selected_count"] <= 1 for summary in plan.by_opening.values())


def test_limit_validation_rejects_non_positive_values(tmp_path):
    source_id = imported_source(tmp_path)
    with pytest.raises(ValueError, match="limit must be 1 or greater"):
        build_learning_sample_plan(source_id, limit=0, per_opening_limit=10, seed=1, dry_run=True)
    with pytest.raises(ValueError, match="per_opening_limit must be 1 or greater"):
        build_learning_sample_plan(source_id, limit=10, per_opening_limit=0, seed=1, dry_run=True)


def test_dry_run_does_not_save_samples(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=10, per_opening_limit=10, seed=1, dry_run=True)
    assert plan.dry_run is True
    assert plan.selected_count == 4
    assert count_samples() == 0


def test_unclassified_positions_do_not_fail(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=10, per_opening_limit=10, seed=1, dry_run=False)
    assert plan.unclassified_count >= 1
    assert any(item["opening_key"] == "unclassified" for item in plan.selected)


def test_seed_makes_results_reproducible(tmp_path):
    source_id = imported_source(tmp_path)
    first = build_learning_sample_plan(source_id, limit=3, per_opening_limit=10, seed=7, dry_run=True)
    second = build_learning_sample_plan(source_id, limit=3, per_opening_limit=10, seed=7, dry_run=True)
    assert [x["book_position_id"] for x in first.selected] == [x["book_position_id"] for x in second.selected]


def test_learning_sample_summary_api(client, tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "api.db")
    init_db()
    result = import_book(FIXTURE, name="Sample YaneuraOu Book", version="fixture", license_name="MIT", copyright_notice="fixture copyright")
    build_learning_sample_plan(result.source_id, limit=2, per_opening_limit=10, seed=1, dry_run=False)

    response = client.get(f"/api/book/sources/{result.source_id}/learning-samples/summary")

    assert response.status_code == 200
    assert response.json()["total_samples"] == 2
    assert response.json()["source"]["name"] == "Sample YaneuraOu Book"
    assert response.json()["source"]["copyright_notice"] == "fixture copyright"


def test_classifies_aigakari_from_mutual_rook_pawn_shape():
    from app.learning_samples import classify_book_position

    sfen = "lnsgkgsnl/1r5b1/p1ppppppp/1p7/7P1/9/PPPPPPP1P/1B5R1/LNSGKGSNL b - 1"

    assert classify_book_position(sfen, ["2e2d", "8e8f"])[0] == "aigakari"


def test_classifies_bogin_from_silver_advance_shape():
    from app.learning_samples import classify_book_position

    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/6SP1/PPPPPPP1P/1B5R1/LNSGKG1NL b - 1"

    assert classify_book_position(sfen, ["2f2e"])[0] == "bogin"


def test_learning_sample_plan_includes_diagnostics(tmp_path):
    source_id = imported_source(tmp_path)
    plan = build_learning_sample_plan(source_id, limit=10, per_opening_limit=10, seed=1, dry_run=True)

    unclassified = plan.by_opening["unclassified"]
    assert unclassified["reason_counts"]
    assert unclassified["example_position_ids"]


def test_learning_samples_can_be_listed_by_opening_with_candidates(client, tmp_path):
    os.environ["SHOGI_DB_PATH"] = str(tmp_path / "samples_api.db")
    init_db()
    result = import_book(FIXTURE, name="Sample YaneuraOu Book", version="fixture", license_name="MIT")
    build_learning_sample_plan(result.source_id, limit=4, per_opening_limit=10, seed=1, dry_run=False)

    openings_response = client.get("/api/learning-samples/openings")
    assert openings_response.status_code == 200
    openings = openings_response.json()
    assert openings

    opening_key = openings[0]["opening_key"]
    samples_response = client.get(f"/api/learning-samples?opening_key={opening_key}")
    assert samples_response.status_code == 200
    samples = samples_response.json()
    assert samples
    assert all(sample["opening_key"] == opening_key for sample in samples)
    assert samples[0]["sfen"]
    assert samples[0]["candidates"]
    assert samples[0]["candidates"][0]["move_usi"]

    detail_response = client.get(f"/api/learning-samples/{samples[0]['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == samples[0]["id"]
