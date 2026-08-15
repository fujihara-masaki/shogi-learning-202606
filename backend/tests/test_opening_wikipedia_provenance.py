import json
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
