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
from typing import Any

import jsonschema
import shogi


SCHEMA_PATH = Path(__file__).with_name("wikipedia_opening_artifact.schema.json")

_UNPROMOTED_TYPE = {
    shogi.PROM_PAWN: shogi.PAWN,
    shogi.PROM_LANCE: shogi.LANCE,
    shogi.PROM_KNIGHT: shogi.KNIGHT,
    shogi.PROM_SILVER: shogi.SILVER,
    shogi.PROM_BISHOP: shogi.BISHOP,
    shogi.PROM_ROOK: shogi.ROOK,
}
_INVENTORY_LIMIT = {
    shogi.PAWN: 18,
    shogi.LANCE: 4,
    shogi.KNIGHT: 4,
    shogi.SILVER: 4,
    shogi.GOLD: 4,
    shogi.BISHOP: 2,
    shogi.ROOK: 2,
    shogi.KING: 2,
}


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
    jsonschema.Draft202012Validator.check_schema(schema)
    errors: list[ValidationDiagnostic] = []
    schema_validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    schema_errors = []
    for error in schema_validator.iter_errors(artifact):
        schema_errors.extend(_schema_error_leaves(error))
    for error in sorted(
        schema_errors,
        key=lambda item: (tuple(map(str, item.absolute_path)), item.message),
    ):
        _diag(errors, "schema", _pointer(list(error.absolute_path)), error.message)
    if errors:
        return tuple(sorted(errors))

    review = artifact["review"]
    for engine, result in review["legality_checks"].items():
        if result == "failed":
            _diag(
                errors,
                "review_legality_failed",
                f"/review/legality_checks/{engine}",
                f"artifact records a failed {engine} legality check",
            )

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


def _schema_error_leaves(error):
    """Select the closest failing ``anyOf`` branch, then expose actionable leaves."""
    if not error.context:
        return [error]
    if error.validator == "anyOf":
        branches: dict[Any, list[Any]] = defaultdict(list)
        for child in error.context:
            relative = list(child.relative_schema_path)
            branch = relative[0] if relative else -1
            branches[branch].append(child)
        selected = min(
            branches.values(),
            key=lambda items: (
                sum(len(_schema_error_leaves(item)) for item in items),
                str(items[0].absolute_schema_path),
            ),
        )
        return [leaf for child in selected for leaf in _schema_error_leaves(child)]
    return [leaf for child in error.context for leaf in _schema_error_leaves(child)]


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
        _validate_initial_inventory(initial, base, errors)
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


def _validate_initial_inventory(board, base, errors) -> None:
    counts: dict[int, int] = defaultdict(int)
    king_counts = {shogi.BLACK: 0, shogi.WHITE: 0}
    unpromoted_pawns: dict[tuple[int, int], int] = defaultdict(int)
    for square in range(81):
        piece = board.piece_at(square)
        if piece is None:
            continue
        rank = square // 9
        file_index = square % 9
        dead_rank = (
            piece.color == shogi.BLACK
            and (
                piece.piece_type in (shogi.PAWN, shogi.LANCE) and rank == 0
                or piece.piece_type == shogi.KNIGHT and rank <= 1
            )
            or piece.color == shogi.WHITE
            and (
                piece.piece_type in (shogi.PAWN, shogi.LANCE) and rank == 8
                or piece.piece_type == shogi.KNIGHT and rank >= 7
            )
        )
        if dead_rank:
            _diag(errors, "initial_dead_rank_piece", f"{base}/initial_sfen", f"unpromoted piece at {shogi.SQUARE_NAMES[square]} has no legal forward move")
        if piece.piece_type == shogi.PAWN:
            unpromoted_pawns[(piece.color, file_index)] += 1
        piece_type = _UNPROMOTED_TYPE.get(piece.piece_type, piece.piece_type)
        counts[piece_type] += 1
        if piece_type == shogi.KING:
            king_counts[piece.color] += 1
    for hand in board.pieces_in_hand:
        for piece_type, count in hand.items():
            counts[_UNPROMOTED_TYPE.get(piece_type, piece_type)] += count
    for color, label in ((shogi.BLACK, "black"), (shogi.WHITE, "white")):
        if king_counts[color] != 1:
            _diag(errors, "initial_king_count", f"{base}/initial_sfen", f"expected exactly one {label} king, found {king_counts[color]}")
    for (color, file_index), count in sorted(unpromoted_pawns.items()):
        if count > 1:
            _diag(errors, "initial_nifu", f"{base}/initial_sfen", f"color {color} has {count} unpromoted pawns on file index {file_index}")
    for piece_type, limit in _INVENTORY_LIMIT.items():
        if counts[piece_type] > limit:
            _diag(errors, "initial_piece_inventory", f"{base}/initial_sfen", f"piece type {piece_type} count {counts[piece_type]} exceeds inventory limit {limit}")


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
