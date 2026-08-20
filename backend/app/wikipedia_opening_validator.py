"""Deterministic validation of already-structured Wikipedia opening audits.

This module deliberately treats prose notes as opaque display data.  Extracting
moves or provenance from Wikipedia (or from Japanese prose) belongs to the
author/reviewer of the artifact, not to this validator.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import shogi


SCHEMA_PATH = Path(__file__).with_name("wikipedia_opening_artifact.schema.json")


@dataclass(frozen=True, order=True)
class ValidationDiagnostic:
    path: str
    code: str
    message: str


def _pointer(parts: list[Any]) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _diag(errors: list[ValidationDiagnostic], code: str, path: str, message: str) -> None:
    errors.append(ValidationDiagnostic(path, code, message))


def validate_wikipedia_opening_artifact(artifact: Any) -> tuple[ValidationDiagnostic, ...]:
    """Return stable, machine-assertable diagnostics; an empty tuple means valid."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list[ValidationDiagnostic] = []
    _validate_schema_value(artifact, schema, schema, [], errors)
    if errors:
        return tuple(sorted(errors))

    record_keys: dict[str, int] = {}
    line_keys: dict[str, int] = {}
    for index, record in enumerate(artifact["records"]):
        base = f"/records/{index}"
        for field, seen, code in (
            ("record_key", record_keys, "duplicate_record_key"),
            ("line_key", line_keys, "duplicate_line_key"),
        ):
            value = record[field]
            if value in seen:
                _diag(errors, code, f"{base}/{field}", f"{value!r} is already used at /records/{seen[value]}/{field}")
            else:
                seen[value] = index
        if record["record_type"] == "move_line":
            _validate_record(record, base, errors)
    return tuple(sorted(errors))


def _validate_schema_value(value, rule, root, path, errors) -> None:
    """Evaluate the deliberately small JSON-Schema vocabulary used by our contract."""
    if "$ref" in rule:
        target = root
        for part in rule["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        _validate_schema_value(value, target, root, path, errors)
        return
    if "anyOf" in rule:
        trials = []
        for choice in rule["anyOf"]:
            trial = []
            _validate_schema_value(value, choice, root, path, trial)
            trials.append(trial)
        if all(trials):
            errors.extend(min(trials, key=lambda trial: (len(trial), trial)))
        return
    expected = rule.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    matches = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
               "string": lambda: isinstance(value, str), "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
               "boolean": lambda: isinstance(value, bool), "null": lambda: value is None}
    if types and not any(matches[k]() for k in types):
        _diag(errors, "schema", _pointer(path), f"expected {' or '.join(types)}")
        return
    if "const" in rule and value != rule["const"]:
        _diag(errors, "schema", _pointer(path), f"expected constant {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        _diag(errors, "schema", _pointer(path), f"expected one of {rule['enum']!r}")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            _diag(errors, "schema", _pointer(path), "string is too short")
        if "pattern" in rule and re.fullmatch(rule["pattern"], value) is None:
            _diag(errors, "schema", _pointer(path), "string does not match required pattern")
        if rule.get("format") == "date":
            try:
                from datetime import date
                date.fromisoformat(value)
            except ValueError:
                _diag(errors, "schema", _pointer(path), "invalid date")
    if isinstance(value, int) and not isinstance(value, bool) and value < rule.get("minimum", value):
        _diag(errors, "schema", _pointer(path), f"value is below minimum {rule['minimum']}")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            _diag(errors, "schema", _pointer(path), "array is too short")
        if "items" in rule:
            for index, item in enumerate(value):
                _validate_schema_value(item, rule["items"], root, path + [index], errors)
    if isinstance(value, dict):
        for name in rule.get("required", []):
            if name not in value:
                _diag(errors, "schema", _pointer(path), f"required property {name!r} is missing")
        properties = rule.get("properties", {})
        if rule.get("additionalProperties") is False:
            for name in value.keys() - properties.keys():
                _diag(errors, "schema", _pointer(path + [name]), "additional property is not allowed")
        for name in value.keys() & properties.keys():
            _validate_schema_value(value[name], properties[name], root, path + [name], errors)


def _validate_record(record: dict[str, Any], base: str, errors: list[ValidationDiagnostic]) -> None:
    nodes = record["nodes"]
    by_key: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, node in enumerate(nodes):
        if node["key"] in by_key:
            _diag(errors, "duplicate_node_key", f"{base}/nodes/{index}/key", f"duplicate node key {node['key']!r}")
        else:
            by_key[node["key"]] = (index, node)

    children: dict[str | None, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, node in enumerate(nodes):
        parent = node["parent_key"]
        children[parent].append((index, node))
        if parent is not None and parent not in by_key:
            _diag(errors, "orphan_parent", f"{base}/nodes/{index}/parent_key", f"parent {parent!r} does not exist")

    if not children[None]:
        _diag(errors, "root_count", f"{base}/nodes", "expected at least one root sibling")

    # Parent chains make cycle diagnostics independent of input ordering.
    for index, node in enumerate(nodes):
        chain: set[str] = set()
        current = node
        while current["parent_key"] in by_key:
            if current["key"] in chain:
                _diag(errors, "cycle", f"{base}/nodes/{index}/parent_key", f"cycle contains {current['key']!r}")
                break
            chain.add(current["key"])
            current = by_key[current["parent_key"]][1]

    for parent, siblings in children.items():
        usis: dict[str, int] = {}
        orders: dict[int, int] = {}
        mains = 0
        for index, node in siblings:
            for field, seen, code in (
                ("usi", usis, "duplicate_sibling_usi"),
                ("sort_order", orders, "duplicate_sibling_sort_order"),
            ):
                value = node[field]
                if value in seen:
                    _diag(errors, code, f"{base}/nodes/{index}/{field}", f"duplicate among children of {parent!r}")
                else:
                    seen[value] = index
            mains += node["is_main"] is True
        if mains != 1:
            _diag(errors, "semantic_main_count", f"{base}/nodes", f"children of {parent!r} have {mains} semantic main nodes; expected 1")

    try:
        initial = shogi.Board(record["initial_sfen"])
        if initial.sfen() != record["initial_sfen"]:
            _diag(errors, "initial_sfen_noncanonical", f"{base}/initial_sfen", "initial SFEN is not canonical")
    except (ValueError, IndexError):
        initial = None
        _diag(errors, "invalid_initial_sfen", f"{base}/initial_sfen", "initial SFEN cannot be loaded")

    depths: dict[str, int] = {}
    visiting: set[str] = set()
    def replay(key: str) -> None:
        if key in depths or key in visiting:
            return
        visiting.add(key)
        index, node = by_key[key]
        parent_key = node["parent_key"]
        if parent_key is None:
            expected_from = initial.sfen() if initial else None
            depth = 1
        elif parent_key in by_key:
            replay(parent_key)
            parent = by_key[parent_key][1]
            expected_from = parent["to_sfen"]
            depth = depths.get(parent_key, 0) + 1
            if node["from_sfen"] != expected_from:
                _diag(errors, "parent_child_sfen", f"{base}/nodes/{index}/from_sfen", "from_sfen differs from parent to_sfen")
        else:
            expected_from = None
            depth = 0
        depths[key] = depth
        visiting.remove(key)
        if expected_from is not None and node["from_sfen"] != expected_from and parent_key is None:
            _diag(errors, "root_sfen", f"{base}/nodes/{index}/from_sfen", "root from_sfen differs from initial_sfen")
        try:
            board = shogi.Board(node["from_sfen"])
            move = shogi.Move.from_usi(node["usi"])
            if move not in board.legal_moves:
                _diag(errors, "illegal_move", f"{base}/nodes/{index}/usi", f"{node['usi']!r} is not legal from from_sfen")
                return
            board.push(move)
            if board.sfen() != node["to_sfen"]:
                _diag(errors, "to_sfen_mismatch", f"{base}/nodes/{index}/to_sfen", "to_sfen does not equal the replayed position")
        except (ValueError, IndexError):
            _diag(errors, "invalid_node_sfen", f"{base}/nodes/{index}/from_sfen", "node SFEN cannot be loaded")
    for key in sorted(by_key):
        replay(key)

    _validate_coverage(record, base, by_key, children, depths, errors)
    _validate_provenance(record, base, by_key, children, errors)


def _validate_coverage(record, base, by_key, children, depths, errors) -> None:
    coverage = record["coverage"]
    main = next((node for _, node in children[None] if node["is_main"]), None)
    seen: set[str] = set()
    while main is not None and main["key"] not in seen:
        seen.add(main["key"])
        next_main = [node for _, node in children[main["key"]] if node["is_main"]]
        if not next_main:
            break
        main = next_main[0]
    if main is None:
        return
    expected_ply = depths.get(main["key"], 0)
    if coverage["covered_through_ply"] != expected_ply:
        _diag(errors, "coverage_ply", f"{base}/coverage/covered_through_ply", f"expected terminal semantic-main ply {expected_ply}")
    if coverage["covered_through_move"] != main["usi"]:
        _diag(errors, "coverage_move", f"{base}/coverage/covered_through_move", f"expected terminal semantic-main move {main['usi']!r}")
    omitted = coverage["omitted_after"]
    if omitted is not None:
        try:
            board = shogi.Board(main["to_sfen"])
            move = shogi.Move.from_usi(omitted["usi"])
            if move not in board.legal_moves:
                _diag(errors, "illegal_omitted_move", f"{base}/coverage/omitted_after/usi", "omitted continuation is not legal after the coverage boundary")
        except (ValueError, IndexError):
            _diag(errors, "illegal_omitted_move", f"{base}/coverage/omitted_after/usi", "omitted continuation cannot be replayed")


def _validate_provenance(record, base, by_key, children, errors) -> None:
    provenance = record["provenance"]
    segments = record.get("segments", [])
    if provenance != "M":
        if segments:
            _diag(errors, "unexpected_segments", f"{base}/segments", "segments are only allowed for mixed provenance")
        for index, node in enumerate(record["nodes"]):
            if node["provenance"] != provenance or node.get("segment_key") is not None:
                _diag(errors, "node_provenance", f"{base}/nodes/{index}/provenance", "node must match the record provenance and have no segment")
        return
    if not segments:
        _diag(errors, "mixed_segments_required", f"{base}/segments", "mixed provenance requires segments")
        return
    segment_provenances = {segment["provenance"] for segment in segments}
    if segment_provenances != {"A", "B"}:
        _diag(errors, "mixed_provenance_set", f"{base}/segments", "mixed provenance requires at least one A segment and one B segment")
    segment_by_key: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, segment in enumerate(segments):
        key = segment["key"]
        if key in segment_by_key:
            _diag(errors, "duplicate_segment_key", f"{base}/segments/{index}/key", f"duplicate segment key {key!r}")
        segment_by_key[key] = (index, segment)
    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, node in enumerate(record["nodes"]):
        key = node.get("segment_key")
        if key not in segment_by_key:
            _diag(errors, "unknown_segment", f"{base}/nodes/{index}/segment_key", f"segment {key!r} does not exist")
            continue
        segment = segment_by_key[key][1]
        members[key].append(node)
        if node["provenance"] != segment["provenance"]:
            _diag(errors, "segment_provenance", f"{base}/nodes/{index}/provenance", "node and segment provenance differ")
    for key, (index, segment) in segment_by_key.items():
        group = members[key]
        starts = [node for node in group if node["parent_key"] is None or by_key.get(node["parent_key"], (None, {}))[1].get("segment_key") != key]
        ends = [node for node in group if not children[node["key"]] or any(child.get("segment_key") != key for _, child in children[node["key"]])]
        if len(starts) != 1 or starts[0]["key"] != segment["start_node_key"]:
            _diag(errors, "segment_start", f"{base}/segments/{index}/start_node_key", "segment must have one matching structural start")
        if len(ends) != 1 or ends[0]["key"] != segment["end_node_key"]:
            _diag(errors, "segment_end", f"{base}/segments/{index}/end_node_key", "segment must have one matching structural end")
