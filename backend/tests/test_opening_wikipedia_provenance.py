import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.scripts.validate_opening_wikipedia_provenance import validate_artifact
from app.seed import SAMPLE_OPENING_LINES


DOCS = Path(__file__).parents[2] / "docs"
SCHEMA = json.loads((DOCS / "opening-wikipedia-provenance-audit.schema.json").read_text())


@pytest.mark.parametrize(
    "fixture",
    [
        "opening-wikipedia-provenance-valid.json",
        "opening-wikipedia-provenance-valid-name-only.json",
        "opening-wikipedia-provenance-valid-name-only-verified.json",
        "opening-wikipedia-provenance-valid-mixed-unavailable.json",
        "opening-wikipedia-provenance-valid-mixed-unresolved.json",
        "opening-wikipedia-provenance-valid-mixed-verified.json",
    ],
)
def test_valid_provenance_fixtures(fixture):
    artifact = json.loads((DOCS / "fixtures" / fixture).read_text())
    assert validate_artifact(artifact, SCHEMA) == []


def test_invalid_masuda_note_has_stable_error_code():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-invalid-masuda.json").read_text())
    assert [error.code for error in validate_artifact(artifact)] == artifact["expected_errors"]


def test_canonical_artifact_matches_every_wikipedia_seed_node():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    assert validate_artifact(artifact, SCHEMA, SAMPLE_OPENING_LINES) == []


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("source_url", "seed_metadata_source_url_mismatch"),
        ("source_title", "seed_metadata_source_title_mismatch"),
        ("source_type", "seed_metadata_source_type_mismatch"),
        ("source_section", "seed_metadata_source_section_mismatch"),
        ("source_license", "seed_metadata_source_license_mismatch"),
        ("source_note", "seed_metadata_source_note_mismatch"),
        ("coverage_status", "seed_metadata_coverage_status_mismatch"),
    ],
)
def test_seed_metadata_drift_has_stable_error_code(field, code):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0][field] = "intentional validator regression drift"
    assert code in {error.code for error in validate_artifact(artifact, None, seed_lines)}


def test_seed_retrieved_date_is_not_compared_with_audit_attempt_date():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["source_retrieved_at"] = "2000-01-01"
    assert validate_artifact(artifact, None, seed_lines) == []


def test_verified_mixed_segments_follow_semantic_main_chain_not_node_order():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid-mixed-verified.json").read_text())
    record = artifact["records"][0]
    branch = deepcopy(record["nodes"][0])
    branch.update(
        move_key="branch-1",
        parent_key="main-1",
        usi="2g2f",
        is_main=False,
        sort_order=1,
        variation_group="検証分岐",
    )
    branch["provenance"] = {
        "provenance_class": "diagram_reconstruction",
        "source_section": "検証用図示分岐",
        "evidence_note": "分岐node自身の図示根拠。",
        "review_status": "verified",
    }
    record["nodes"] = [record["nodes"][1], branch, record["nodes"][0]]
    record["node_count"] += 1
    artifact["seed_snapshot"]["node_count"] += 1
    assert validate_artifact(artifact, SCHEMA) == []


def test_masuda_boundary_and_metadata_only_change_are_fixed():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    record = next(record for record in artifact["records"] if record.get("line_name", "").startswith("升田式石田流"))
    assert record["coverage_boundary"] == {
        "covered_through_ply": 7,
        "covered_through_move": "5i4h",
        "omitted_after": "7h7f",
    }
    assert "未収録" in record["evidence_note"]
    seed = next(line for line in SAMPLE_OPENING_LINES if line["name"] == record["line_name"])
    assert seed["moves"] == ["7g7f", "3c3d", "7f7e", "8c8d", "2h7h", "8d8e", "5i4h"]
    assert "未収録" in seed["source_note"]
