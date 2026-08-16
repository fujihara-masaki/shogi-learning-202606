import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.scripts.validate_opening_wikipedia_provenance import (
    ValidationError,
    _declared_snapshot_errors,
    _extract_snapshot_seed_lines,
    main,
    validate_artifact,
    validate_production_artifact,
)
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


def test_invalid_continuation_note_is_rejected_without_omitted_boundary():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-invalid-masuda.json").read_text())
    artifact["omitted_after"] = None
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


def test_node_continuation_evidence_is_rejected_without_omitted_boundary():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = None
    record["nodes"][0]["provenance"]["evidence_note"] = "▲4八玉、および実戦以下▲7六飛を手順化。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


@pytest.mark.parametrize(
    "note",
    [
        "▲4八玉までを収録。続く▲7六飛は未収録。",
        "引用sectionの終端である▲4八玉までを収録した。",
    ],
)
def test_terminal_recording_note_does_not_claim_unrecorded_move(note):
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = None
    record["evidence_note"] = note
    for node in record["nodes"]:
        node["provenance"]["evidence_note"] = note
    assert "note_claims_unrecorded_move" not in {error.code for error in validate_artifact(artifact)}


def test_terminal_recording_note_is_valid_with_omitted_boundary_on_line_and_nodes():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    note = "引用sectionの終端である▲4八玉までを収録した。"
    record["evidence_note"] = note
    for node in record["nodes"]:
        node["provenance"]["evidence_note"] = note
    assert "note_claims_unrecorded_move" not in {error.code for error in validate_artifact(artifact)}


def test_normal_masuda_note_is_valid_with_omitted_boundary():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    note = "▲4八玉までを収録。続く▲7六飛は未収録。"
    record["evidence_note"] = note
    for node in record["nodes"]:
        node["provenance"]["evidence_note"] = note
    assert "note_claims_unrecorded_move" not in {error.code for error in validate_artifact(artifact)}


def test_direct_omitted_usi_recording_claim_is_rejected():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["evidence_note"] = "7h7fを収録した。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


def test_unrelated_exclusion_does_not_hide_omitted_move_claim():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["evidence_note"] = "続く7h7fを収録した。なお8h8fは未収録。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


def test_unrelated_node_exclusion_does_not_hide_omitted_move_claim():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["nodes"][0]["provenance"]["evidence_note"] = "続く7h7fを収録した。なお8h8fは未収録。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


def test_exclusion_for_omitted_move_does_not_hide_unrelated_recording():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["evidence_note"] = "続く7h7fは未収録。なお8h8fを収録した。"
    assert "note_claims_unrecorded_move" not in {error.code for error in validate_artifact(artifact)}


def test_same_sentence_omitted_move_exclusion_is_not_overridden_by_other_recording():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["evidence_note"] = "続く7h7fは未収録だが、8h8fを収録した。"
    assert "note_claims_unrecorded_move" not in {error.code for error in validate_artifact(artifact)}


def test_same_sentence_omitted_move_recording_is_not_hidden_by_other_exclusion():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["evidence_note"] = "続く7h7fを収録したが、8h8fは未収録。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


@pytest.mark.parametrize("omitted_after", ["", "xxxx", "9z9z"])
def test_invalid_omitted_after_usi_is_rejected(omitted_after):
    artifact = _valid_record_artifact()
    artifact["records"][0]["coverage_boundary"]["omitted_after"] = omitted_after
    invalid = [error for error in validate_artifact(artifact) if error.code == "omitted_after_invalid_usi"]
    assert len(invalid) == 1
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "coverage_boundary.omitted_after"


@pytest.mark.parametrize("omitted_after", [None, "7h7f"])
def test_valid_omitted_after_values_are_accepted(omitted_after):
    artifact = _valid_record_artifact()
    artifact["records"][0]["coverage_boundary"]["omitted_after"] = omitted_after
    assert "omitted_after_invalid_usi" not in {error.code for error in validate_artifact(artifact)}


def test_canonical_masuda_omitted_after_remains_valid():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    masuda = next(record for record in artifact["records"] if record.get("line_name", "").startswith("升田式石田流"))
    assert masuda["coverage_boundary"]["omitted_after"] == "7h7f"
    assert "omitted_after_invalid_usi" not in {error.code for error in validate_artifact(artifact)}


def test_mixed_segment_contradictory_evidence_note_is_rejected():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid-mixed-verified.json").read_text())
    record = artifact["records"][0]
    record["coverage_boundary"]["omitted_after"] = "7h7f"
    record["segments"][0]["evidence_note"] = "続く7h7fを収録した。"
    assert "note_claims_unrecorded_move" in {error.code for error in validate_artifact(artifact)}


def test_valid_mixed_segment_evidence_notes_are_accepted():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid-mixed-verified.json").read_text())
    assert validate_artifact(artifact) == []


@pytest.mark.parametrize("canonical_url", ["garbage", "http://ja.wikipedia.org/wiki/石田流", "https://"])
def test_needs_review_invalid_canonical_url_is_rejected(canonical_url):
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["verification"]["status"] = "needs_review"
    record["source"]["canonical_url"] = canonical_url
    invalid = [error for error in validate_artifact(artifact) if error.code == "canonical_url_invalid"]
    assert len(invalid) == 1
    assert invalid[0].record_id == record["record_id"]
    assert invalid[0].path == "source.canonical_url"


@pytest.mark.parametrize("canonical_url", [None, "https://ja.wikipedia.org/wiki/石田流"])
def test_needs_review_null_or_https_canonical_url_is_accepted(canonical_url):
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["verification"]["status"] = "needs_review"
    record["source"]["canonical_url"] = canonical_url
    assert "canonical_url_invalid" not in {error.code for error in validate_artifact(artifact)}


@pytest.mark.parametrize(
    ("artifact_text", "schema_text", "expected_codes"),
    [
        ('{"broken":', json.dumps(SCHEMA), ["artifact_json_invalid"]),
        (json.dumps({"valid": "artifact"}), '{"broken":', ["schema_json_invalid"]),
        ('{"broken":', '{"also-broken":', ["artifact_json_invalid", "schema_json_invalid"]),
    ],
)
def test_cli_serializes_malformed_json(tmp_path, monkeypatch, capsys, artifact_text, schema_text, expected_codes):
    artifact_path = tmp_path / "artifact.json"
    schema_path = tmp_path / "schema.json"
    artifact_path.write_text(artifact_text)
    schema_path.write_text(schema_text)
    monkeypatch.setattr(
        "sys.argv",
        ["validate_opening_wikipedia_provenance", str(artifact_path), "--schema", str(schema_path)],
    )

    assert main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is False
    assert [error["code"] for error in output["errors"]] == expected_codes
    assert [error["path"] for error in output["errors"]] == [
        "artifact" if code.startswith("artifact") else "schema" for code in expected_codes
    ]


def test_canonical_artifact_matches_every_wikipedia_seed_node():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    assert validate_artifact(artifact, SCHEMA, SAMPLE_OPENING_LINES) == []


def test_production_validation_always_checks_canonical_seed():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    record = artifact["records"][0]
    record["moves"][0] = "1a1b"
    main_root = next(node for node in record["nodes"] if node["parent_key"] is None and node["is_main"])
    main_root["usi"] = "1a1b"

    # The synthetic semantic-only API sees matching declarations, while the
    # production entry point must compare them with SAMPLE_OPENING_LINES.
    assert "semantic_main_chain_mismatch" not in {error.code for error in validate_artifact(artifact)}
    codes = {error.code for error in validate_production_artifact(artifact, SCHEMA)}
    assert {"seed_main_moves_mismatch", "seed_node_tree_mismatch"} <= codes


def test_production_validation_requires_schema():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    assert [error.code for error in validate_production_artifact(artifact, None)] == ["production_schema_required"]


def test_fixture_version_cannot_bypass_production_schema_validation():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    artifact["fixture_version"] = "legacy-bypass-attempt"
    artifact.pop("generated_on")
    codes = {error.code for error in validate_production_artifact(artifact, SCHEMA)}
    assert "schema_validation_error" in codes


def test_canonical_seed_snapshot_references_audited_revision():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    assert artifact["seed_snapshot"] == {
        "commit": "8a0ec732a799f95b58546feb4f9e0413b8af61a7",
        "source_file": "backend/app/seed.py",
        "line_count": 34,
        "node_count": 328,
    }


def test_missing_declared_snapshot_commit_is_rejected():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    artifact["seed_snapshot"]["commit"] = "0" * 40
    assert [error.code for error in _declared_snapshot_errors(artifact)] == [
        "seed_snapshot_commit_unavailable"
    ]


def test_declared_snapshot_content_mismatch_is_rejected(monkeypatch):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    source = (DOCS.parent / "backend/app/seed.py").read_text()
    drifted_source = source.replace('"7g7f"', '"1a1b"', 1)
    monkeypatch.setattr(
        "app.scripts.validate_opening_wikipedia_provenance.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=drifted_source),
    )
    assert [error.code for error in _declared_snapshot_errors(artifact)] == [
        "seed_snapshot_content_mismatch"
    ]


def test_declared_snapshot_matching_content_is_valid(monkeypatch):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    source = (DOCS.parent / "backend/app/seed.py").read_text()
    monkeypatch.setattr(
        "app.scripts.validate_opening_wikipedia_provenance.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=source),
    )
    assert validate_production_artifact(artifact, SCHEMA) == []


def test_declared_snapshot_git_show_uses_utf8_and_parses_japanese(monkeypatch):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    source = (DOCS.parent / "backend/app/seed.py").read_text(encoding="utf-8")
    assert "升田式石田流" in source
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=source)

    monkeypatch.setattr(
        "app.scripts.validate_opening_wikipedia_provenance.subprocess.run",
        fake_run,
    )
    assert _declared_snapshot_errors(artifact) == []
    assert captured["text"] is True
    assert captured["encoding"] == "utf-8"


def test_declared_snapshot_decode_failure_is_stable_error(monkeypatch):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())

    def fail_decode(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(
        "app.scripts.validate_opening_wikipedia_provenance.subprocess.run",
        fail_decode,
    )
    assert [error.code for error in _declared_snapshot_errors(artifact)] == [
        "seed_snapshot_source_invalid"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "WIKIPEDIA_OPENING_SOURCE_DEFAULTS = {}\nWIKIPEDIA_OPENING_SOURCE_BY_NAME = {}",
        "SAMPLE_OPENING_LINES = make_lines()\nWIKIPEDIA_OPENING_SOURCE_DEFAULTS = {}\nWIKIPEDIA_OPENING_SOURCE_BY_NAME = {}",
    ],
)
def test_snapshot_source_parser_rejects_missing_or_nonliteral_seed(source):
    with pytest.raises(ValueError):
        _extract_snapshot_seed_lines(source)


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


def test_seed_entry_without_name_is_stable_validation_error():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    del seed_lines[0]["name"]
    invalid = [
        error for error in validate_artifact(artifact, None, seed_lines)
        if error.code == "seed_entry_invalid"
    ]
    assert invalid == [ValidationError("seed_entry_invalid", path="seed_lines[0]")]


def test_duplicate_seed_line_name_is_rejected_and_not_double_counted():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[1] = deepcopy(seed_lines[0])
    errors = validate_artifact(artifact, None, seed_lines)
    duplicates = [error for error in errors if error.code == "duplicate_seed_line_name"]
    assert len(duplicates) == 1
    assert duplicates[0].record_id == artifact["records"][0]["record_id"]
    assert duplicates[0].path == "seed_lines[1]"
    assert "seed_line_count_mismatch" in {error.code for error in errors}


def test_non_dict_seed_entry_is_stable_validation_error():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0] = None
    invalid = [
        error for error in validate_artifact(artifact, None, seed_lines)
        if error.code == "seed_entry_invalid"
    ]
    assert invalid == [ValidationError("seed_entry_invalid", path="seed_lines[0]")]


def test_invalid_seed_entry_does_not_stop_later_metadata_validation():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0] = None
    seed_lines[1]["source_title"] = "later line metadata drift"
    codes = {error.code for error in validate_artifact(artifact, None, seed_lines)}
    assert {"seed_entry_invalid", "seed_metadata_source_title_mismatch"} <= codes


def test_seed_metadata_normalization_failure_is_stable_error(monkeypatch):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    from app import seed as seed_module

    original = seed_module._opening_source_metadata

    def malformed_metadata(line):
        if line["name"] == seed_lines[0]["name"]:
            raise TypeError("malformed metadata")
        return original(line)

    monkeypatch.setattr(seed_module, "_opening_source_metadata", malformed_metadata)
    invalid = [
        error for error in validate_artifact(artifact, None, seed_lines)
        if error.code == "seed_entry_invalid"
    ]
    assert len(invalid) == 1
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "seed_lines[0]"


@pytest.mark.parametrize("invalid_move", ["xxxx", "1a1b"])
def test_invalid_seed_move_becomes_stable_validation_error(invalid_move):
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["moves"][0] = invalid_move
    errors = validate_artifact(artifact, None, seed_lines)
    invalid = [error for error in errors if error.code == "seed_tree_invalid"]
    assert invalid
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "seed"


def test_none_initial_sfen_becomes_stable_validation_error():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["initial_sfen"] = None
    errors = validate_artifact(artifact, None, seed_lines)
    invalid = [error for error in errors if error.code == "seed_tree_invalid"]
    assert invalid
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "seed"


def test_none_move_node_sort_order_becomes_stable_validation_error():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["move_nodes"] = [
        {
            "key": "main-1",
            "parent_key": None,
            "usi": "7g7f",
            "sort_order": None,
            "is_main": True,
        }
    ]
    errors = validate_artifact(artifact, None, seed_lines)
    invalid = [error for error in errors if error.code == "seed_tree_invalid"]
    assert invalid
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "seed"


def test_overflowing_move_node_sort_order_becomes_stable_validation_error():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["move_nodes"] = [
        {
            "key": "main-1",
            "parent_key": None,
            "usi": "7g7f",
            "sort_order": 1e309,
            "is_main": True,
        }
    ]
    errors = validate_artifact(artifact, None, seed_lines)
    invalid = [error for error in errors if error.code == "seed_tree_invalid"]
    assert invalid
    assert invalid[0].record_id == artifact["records"][0]["record_id"]
    assert invalid[0].path == "seed"


def test_invalid_seed_line_does_not_stop_validation_of_following_lines():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    seed_lines[0]["moves"][0] = "xxxx"
    seed_lines[1]["source_title"] = "later line metadata drift"
    codes = {error.code for error in validate_artifact(artifact, None, seed_lines)}
    assert {"seed_tree_invalid", "seed_metadata_source_title_mismatch"} <= codes


def _valid_record_artifact():
    return json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid.json").read_text())


def test_duplicate_record_id_is_rejected_without_seed_check():
    artifact = _valid_record_artifact()
    artifact["records"].append(deepcopy(artifact["records"][0]))
    assert "duplicate_record_id" in {error.code for error in validate_artifact(artifact)}


def test_duplicate_move_line_name_is_rejected_without_seed_check():
    artifact = _valid_record_artifact()
    duplicate = deepcopy(artifact["records"][0])
    duplicate["record_id"] = "fixture:duplicate-line-name"
    artifact["records"].append(duplicate)
    assert "duplicate_move_line_name" in {error.code for error in validate_artifact(artifact)}


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda nodes: nodes[1].update(move_key=nodes[0]["move_key"]), "duplicate_move_key"),
        (lambda nodes: nodes[1].update(parent_key="missing-parent"), "parent_key_missing"),
        (lambda nodes: nodes[0].update(parent_key=nodes[0]["move_key"]), "self_parent_cycle"),
        (
            lambda nodes: (
                nodes[0].update(parent_key=nodes[1]["move_key"]),
                nodes[1].update(parent_key=nodes[0]["move_key"]),
            ),
            "parent_cycle",
        ),
        (lambda nodes: nodes[1].update(is_main=False), "sibling_main_count_invalid"),
    ],
)
def test_canonical_node_structure_errors_are_stable(mutate, expected_code):
    artifact = _valid_record_artifact()
    mutate(artifact["records"][0]["nodes"])
    assert expected_code in {error.code for error in validate_artifact(artifact)}


def test_multiple_virtual_root_children_are_valid_with_one_semantic_main():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    branch = deepcopy(record["nodes"][0])
    branch.update(move_key="root-branch", usi="2g2f", is_main=False, sort_order=1)
    record["nodes"].append(branch)
    record["node_count"] += 1
    errors = {error.code for error in validate_artifact(artifact)}
    assert "sibling_main_count_invalid" not in errors
    assert "node_not_connected_to_virtual_root" not in errors


@pytest.mark.parametrize(
    ("branch_overrides", "expected_code"),
    [
        ({"usi": "7g7f", "sort_order": 1}, "duplicate_sibling_usi"),
        ({"usi": "2g2f", "sort_order": 0}, "duplicate_sibling_sort_order"),
    ],
)
def test_virtual_root_sibling_values_are_unique(branch_overrides, expected_code):
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    branch = deepcopy(record["nodes"][0])
    branch.update(move_key="root-branch", is_main=False, **branch_overrides)
    record["nodes"].append(branch)
    record["node_count"] += 1
    assert expected_code in {error.code for error in validate_artifact(artifact)}


def test_verified_move_line_rejects_unverified_node():
    artifact = _valid_record_artifact()
    artifact["records"][0]["nodes"][1]["provenance"]["review_status"] = "needs_review"
    codes = {error.code for error in validate_artifact(artifact)}
    assert "verified_line_node_unverified" in codes


def test_non_mixed_main_chain_must_match_declared_moves_without_seed_check():
    artifact = _valid_record_artifact()
    artifact["records"][0]["nodes"][1]["usi"] = "2g2f"
    codes = {error.code for error in validate_artifact(artifact)}
    assert "semantic_main_chain_mismatch" in codes


def test_explicit_line_rejects_diagram_node_provenance():
    artifact = _valid_record_artifact()
    artifact["records"][0]["nodes"][1]["provenance"]["provenance_class"] = "diagram_reconstruction"
    assert "node_line_provenance_mismatch" in {error.code for error in validate_artifact(artifact)}


def test_diagram_line_rejects_explicit_node_provenance():
    artifact = _valid_record_artifact()
    record = artifact["records"][0]
    record["provenance_class"] = "diagram_reconstruction"
    record["coverage"] = "diagram_reconstruction"
    for node in record["nodes"]:
        node["provenance"]["provenance_class"] = "diagram_reconstruction"
    record["nodes"][1]["provenance"]["provenance_class"] = "explicit_sequence"
    assert "node_line_provenance_mismatch" in {error.code for error in validate_artifact(artifact)}


def test_seed_snapshot_line_count_drift_is_rejected():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    artifact["seed_snapshot"]["line_count"] += 1
    errors = validate_artifact(artifact, None, SAMPLE_OPENING_LINES)
    assert "seed_snapshot_line_count_mismatch" in {error.code for error in errors}


def test_new_wikipedia_seed_without_audit_record_is_rejected():
    artifact = json.loads((DOCS / "opening-wikipedia-provenance-audit.json").read_text())
    seed_lines = deepcopy(SAMPLE_OPENING_LINES)
    new_line = deepcopy(seed_lines[0])
    new_line.update(name="監査未登録Wikipedia line", source_type="wikipedia")
    seed_lines.append(new_line)
    codes = {error.code for error in validate_artifact(artifact, None, seed_lines)}
    assert {"seed_snapshot_line_count_mismatch", "seed_line_count_mismatch", "seed_line_missing"} <= codes


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


def test_malformed_mixed_main_cycle_terminates_with_stable_errors():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid-mixed-verified.json").read_text())
    nodes = artifact["records"][0]["nodes"]
    nodes[0]["parent_key"] = nodes[1]["move_key"]
    nodes[1]["parent_key"] = nodes[0]["move_key"]
    codes = {error.code for error in validate_artifact(artifact)}
    assert "parent_cycle" in codes
    assert "semantic_main_chain_mismatch" in codes


def test_mixed_unresolved_marker_cannot_coexist_with_segments():
    artifact = json.loads((DOCS / "fixtures/opening-wikipedia-provenance-valid-mixed-verified.json").read_text())
    artifact["records"][0]["audit_issues"].append("mixed_segment_boundary_unresolved")
    codes = {error.code for error in validate_artifact(artifact)}
    assert "mixed_unresolved_with_segments" in codes


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
