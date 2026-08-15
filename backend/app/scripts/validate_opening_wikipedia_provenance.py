"""Validate the canonical Wikipedia opening provenance audit artifact.

This is deliberately an offline development tool: application startup does not
load JSON Schema (or the audit documents).  Error codes are stable API for CI.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROVENANCE_COVERAGE = {
    "explicit_sequence": {"complete_for_cited_sequence", "partial_explicit_sequence"},
    "diagram_reconstruction": {"diagram_reconstruction"},
    "name_only": {"name_only"},
    "mixed": {"mixed"},
}


@dataclass(frozen=True)
class ValidationError:
    code: str
    record_id: str | None = None
    path: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {key: value for key, value in vars(self).items() if value is not None}


def _error(code: str, record: dict[str, Any] | None = None, path: str | None = None) -> ValidationError:
    return ValidationError(code, record.get("record_id") if record else None, path)


def _note_claims_unrecorded_move(note: str, omitted_after: str | None) -> bool:
    if not omitted_after:
        return False
    recorded_claims = ("手順化", "収録済み", "収録した", "収録しています")
    exclusion = ("未収録", "収録していない", "手順化していない")
    return any(word in note for word in recorded_claims) and not any(word in note for word in exclusion)


def _semantic_errors(record: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    provenance = record.get("provenance_class")
    coverage = record.get("coverage")
    if provenance not in PROVENANCE_COVERAGE:
        errors.append(_error("invalid_provenance_class", record))
    elif coverage not in PROVENANCE_COVERAGE[provenance]:
        errors.append(_error("invalid_provenance_coverage", record))

    # D0's intentionally small legacy fixture exercises the note rule directly.
    if "fixture_version" in record:
        if _note_claims_unrecorded_move(record.get("source_note", ""), record.get("omitted_after")):
            errors.append(_error("note_claims_unrecorded_move", record))
        return errors
    if record.get("subject_kind") == "catalog_item":
        return errors
    if record.get("subject_kind") != "move_line":
        return errors

    moves, nodes = record.get("moves", []), record.get("nodes", [])
    boundary = record.get("coverage_boundary", {})
    if record.get("move_count") != len(moves):
        errors.append(_error("move_count_mismatch", record))
    if record.get("node_count") != len(nodes):
        errors.append(_error("node_count_mismatch", record))
    if boundary.get("covered_through_ply") != len(moves):
        errors.append(_error("covered_through_ply_mismatch", record))
    if moves and boundary.get("covered_through_move") != moves[-1]:
        errors.append(_error("covered_through_move_mismatch", record))

    notes = [record.get("evidence_note", "")]
    notes += [node.get("provenance", {}).get("evidence_note", "") for node in nodes]
    if any(_note_claims_unrecorded_move(note, boundary.get("omitted_after")) for note in notes):
        errors.append(_error("note_claims_unrecorded_move", record))

    source, verification = record.get("source", {}), record.get("verification", {})
    status = verification.get("status")
    if status == "verified":
        required = ("canonical_url", "source_section", "revision_id", "revision_timestamp", "retrieved_at", "source_license")
        if any(not source.get(field) for field in required):
            errors.append(_error("verified_source_metadata_missing", record))
    if status == "unavailable" and any(source.get(field) is not None for field in ("canonical_url", "revision_id", "revision_timestamp")):
        errors.append(_error("unavailable_source_metadata_inferred", record))

    keys = {node.get("move_key") for node in nodes}
    if len(keys) != len(nodes):
        errors.append(_error("duplicate_move_key", record))
    for index, node in enumerate(nodes):
        parent = node.get("parent_key")
        if parent is not None and parent not in keys:
            errors.append(_error("parent_key_missing", record, f"nodes[{index}]"))
        node_provenance = node.get("provenance", {})
        if node_provenance.get("review_status") == "verified" and not node_provenance.get("source_section"):
            errors.append(_error("verified_node_source_section_missing", record, f"nodes[{index}]"))

    segments = record.get("segments", [])
    if provenance == "mixed":
        unresolved = "mixed_segment_boundary_unresolved" in record.get("audit_issues", [])
        if status == "verified" and unresolved:
            errors.append(_error("mixed_segment_boundary_unresolved", record))
        if segments:
            classes = {segment.get("provenance_class") for segment in segments}
            if not {"explicit_sequence", "diagram_reconstruction"} <= classes:
                errors.append(_error("mixed_missing_provenance_class", record))
            covered = [ply for segment in segments for ply in range(segment.get("start_ply", 0), segment.get("end_ply", -1) + 1)]
            if covered != list(range(1, len(moves) + 1)):
                errors.append(_error("mixed_segment_range_invalid", record))
            for index, node in enumerate(nodes):
                ply = index + 1
                matching = [s for s in segments if s["start_ply"] <= ply <= s["end_ply"]]
                if matching and node.get("provenance", {}).get("provenance_class") != matching[0]["provenance_class"]:
                    errors.append(_error("node_segment_provenance_mismatch", record, f"nodes[{index}]"))
        elif not (status in {"unavailable", "needs_review"} and unresolved):
            errors.append(_error("mixed_segments_missing", record))
    elif segments:
        errors.append(_error("segments_for_non_mixed", record))
    return errors


def _seed_errors(artifact: dict[str, Any], seed_lines: list[dict[str, Any]]) -> list[ValidationError]:
    from app.seed import _prepare_opening_move_nodes
    import shogi

    from app.seed import _opening_source_metadata

    wikipedia = [line for line in seed_lines if _opening_source_metadata(line).get("source_type") in {"wikipedia", "wikibooks"}]
    records = {record.get("line_name"): record for record in artifact.get("records", []) if record.get("subject_kind") == "move_line"}
    errors: list[ValidationError] = []
    if len(records) != len(wikipedia):
        errors.append(_error("seed_line_count_mismatch"))
    for line in wikipedia:
        record = records.get(line["name"])
        if not record:
            errors.append(ValidationError("seed_line_missing", line["name"]))
            continue
        initial = line.get("initial_sfen", shogi.STARTING_SFEN)
        prepared = _prepare_opening_move_nodes(line, initial)
        expected = [{"move_key": n["key"], "parent_key": n["parent_key"], "usi": n["usi"], "is_main": n["is_main"], "sort_order": n["sort_order"], "variation_group": n["variation_group"]} for n in prepared]
        actual = [{key: n.get(key) for key in expected[0]} for n in record.get("nodes", [])] if expected else []
        if {tuple(item.items()) for item in expected} != {tuple(item.items()) for item in actual}:
            errors.append(_error("seed_node_tree_mismatch", record))
        if record.get("moves") != line.get("moves"):
            errors.append(_error("seed_main_moves_mismatch", record))
    if artifact.get("seed_snapshot", {}).get("node_count") != sum(len(r.get("nodes", [])) for r in records.values()):
        errors.append(_error("seed_snapshot_node_count_mismatch"))
    return errors


def validate_artifact(data: dict[str, Any], schema: dict[str, Any] | None = None, seed_lines: list[dict[str, Any]] | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if schema is not None and "fixture_version" not in data:
        from jsonschema import Draft7Validator, FormatChecker

        validator = Draft7Validator(schema, format_checker=FormatChecker())
        for failure in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
            errors.append(ValidationError("schema_validation_error", path="/".join(map(str, failure.absolute_path))))
        if errors:
            return errors
    records = data.get("records", [data])
    for record in records:
        errors.extend(_semantic_errors(record))
    if seed_lines is not None:
        errors.extend(_seed_errors(data, seed_lines))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--check-seed", action="store_true")
    args = parser.parse_args()
    data, schema = json.loads(args.artifact.read_text()), json.loads(args.schema.read_text())
    seed_lines = None
    if args.check_seed:
        from app.seed import SAMPLE_OPENING_LINES
        seed_lines = SAMPLE_OPENING_LINES
    errors = validate_artifact(data, schema, seed_lines)
    print(json.dumps({"valid": not errors, "errors": [error.as_dict() for error in errors]}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
