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
from urllib.parse import parse_qs, urlsplit

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
    if not parts:
        return ""
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _diag(errors: list[ValidationDiagnostic], code: str, path: str, message: str) -> None:
    errors.append(ValidationDiagnostic(path, code, message))


def validate_wikipedia_opening_artifact(artifact: Any) -> tuple[ValidationDiagnostic, ...]:
    """Return stable, machine-assertable diagnostics; an empty tuple means valid."""
    return _validate_wikipedia_opening_artifact(artifact, SCHEMA_PATH)


def _validate_wikipedia_opening_artifact(
    artifact: Any, schema_path: Path
) -> tuple[ValidationDiagnostic, ...]:
    """Validate with an injected schema path for CLI infrastructure tests."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
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
    if review["review_status"] == "pending":
        _diag(
            errors,
            "review_pending",
            "/review/review_status",
            "artifact review is still pending",
        )
    for engine, result in review["legality_checks"].items():
        if result == "failed":
            _diag(
                errors,
                "review_legality_failed",
                f"/review/legality_checks/{engine}",
                f"artifact records a failed {engine} legality check",
            )
        elif result == "pending":
            _diag(
                errors,
                "review_legality_pending",
                f"/review/legality_checks/{engine}",
                f"artifact has not completed the {engine} legality check",
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
        if not _is_allowed_source_url(record["source"]["url"]):
            _diag(
                errors,
                "source_url",
                f"{base}/source/url",
                "source URL must use HTTPS on wikipedia.org or wikibooks.org",
            )
        elif not _source_revision_matches(record["source"]["url"], record["revision"]):
            _diag(
                errors,
                "source_revision",
                f"{base}/source/url",
                "source URL oldid must be one positive decimal integer matching revision",
            )
        if record["record_type"] == "move_line":
            _validate_record(record, base, errors)
        else:
            _validate_coverage_status(record, base, errors)
    return tuple(sorted(errors))


def _is_allowed_wikimedia_host(host: str) -> bool:
    return (
        host == "wikipedia.org"
        or host.endswith(".wikipedia.org")
        or host == "wikibooks.org"
        or host.endswith(".wikibooks.org")
    )


def _is_allowed_source_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and host is not None
        and parsed.username is None
        and parsed.password is None
        and port is None
        and ":" not in parsed.netloc.rsplit("@", 1)[-1]
        and _is_allowed_wikimedia_host(host)
    )


def _source_revision_matches(url: str, revision: int) -> bool:
    oldids = parse_qs(urlsplit(url).query, keep_blank_values=True).get("oldid")
    if oldids is None:
        return True
    if len(oldids) != 1 or not oldids[0].isascii() or not oldids[0].isdigit():
        return False
    normalized = oldids[0].lstrip("0") or "0"
    return normalized != "0" and normalized == str(revision)


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
    _validate_coverage_status(record, base, errors)
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

    # Resolve each parent chain once.  ``cycle_reachable`` memoizes both
    # acyclic chains and chains which eventually enter a cycle.
    cycle_reachable: dict[str, str | None] = {}
    for key in sorted(by_key):
        if key in cycle_reachable:
            continue
        chain: list[str] = []
        positions: dict[str, int] = {}
        current = key
        while current in by_key and current not in cycle_reachable and current not in positions:
            positions[current] = len(chain)
            chain.append(current)
            parent = by_key[current][1]["parent_key"]
            if parent is None:
                current = ""
                break
            current = parent
        if current in positions:
            cycle_start = positions[current]
            outcome = min(chain[cycle_start:])
        else:
            outcome = cycle_reachable.get(current)
        for chain_key in reversed(chain):
            cycle_reachable[chain_key] = outcome

    for index, node in enumerate(nodes):
        cycle_key = cycle_reachable.get(node["key"])
        if cycle_key is not None:
            _diag(errors, "cycle", f"{base}/nodes/{index}/parent_key", f"cycle contains {cycle_key!r}")

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
    for key in sorted(by_key):
        if key in depths:
            continue
        chain: list[str] = []
        chain_keys: set[str] = set()
        current = key
        while current in by_key and current not in depths and current not in chain_keys:
            chain.append(current)
            chain_keys.add(current)
            parent_key = by_key[current][1]["parent_key"]
            if parent_key is None:
                current = ""
                base_depth = 0
                break
            current = parent_key
        else:
            base_depth = depths.get(current, -1 if current not in by_key else 0)
        for chain_key in reversed(chain):
            base_depth += 1
            depths[chain_key] = base_depth

    for key in sorted(by_key):
        index, node = by_key[key]
        parent_key = node["parent_key"]
        if parent_key is None:
            expected_from = initial.sfen() if initial else None
        elif parent_key in by_key:
            parent = by_key[parent_key][1]
            expected_from = parent["to_sfen"]
            if node["from_sfen"] != expected_from:
                _diag(errors, "parent_child_sfen", f"{base}/nodes/{index}/from_sfen", "from_sfen differs from parent to_sfen")
        else:
            expected_from = None
        if expected_from is not None and node["from_sfen"] != expected_from and parent_key is None:
            _diag(errors, "root_sfen", f"{base}/nodes/{index}/from_sfen", "root from_sfen differs from initial_sfen")
        try:
            shogi.Board(node["from_sfen"])
        except (ValueError, IndexError):
            _diag(errors, "invalid_node_sfen", f"{base}/nodes/{index}/from_sfen", "node SFEN cannot be loaded")

    terminal_node_keys: set[str] = set()
    if initial is not None:
        terminal_node_keys = _validate_move_replay(initial, base, children, errors)

    _validate_coverage(
        record, base, by_key, children, depths, terminal_node_keys, errors
    )
    _validate_provenance(record, base, by_key, children, errors)


def _validate_move_replay(initial, base, children, errors) -> set[str]:
    """Replay every branch once while preserving its root-to-node history."""
    board = shogi.Board(initial.sfen())
    terminal_node_keys: set[str] = set()
    stack: list[tuple[str, int | None, dict[str, Any] | None]] = [
        ("enter", index, node) for index, node in reversed(children[None])
    ]
    while stack:
        action, index, node = stack.pop()
        if action == "exit":
            board.pop()
            continue
        assert index is not None and node is not None
        if board.is_game_over():
            _diag(
                errors,
                "move_after_game_end",
                f"{base}/nodes/{index}/usi",
                "move appears after python-shogi reports the branch game is over",
            )
            stack.extend(
                ("ended", child_index, child)
                for child_index, child in reversed(children[node["key"]])
            )
            continue
        if action == "ended":
            _diag(
                errors,
                "move_after_game_end",
                f"{base}/nodes/{index}/usi",
                "move appears after python-shogi reports the branch game is over",
            )
            stack.extend(
                ("ended", child_index, child)
                for child_index, child in reversed(children[node["key"]])
            )
            continue
        try:
            move = shogi.Move.from_usi(node["usi"])
            if move not in board.legal_moves:
                _diag(errors, "illegal_move", f"{base}/nodes/{index}/usi", f"{node['usi']!r} is not legal in its branch history")
                continue
            board.push(move)
            if board.is_game_over():
                terminal_node_keys.add(node["key"])
            if board.sfen() != node["to_sfen"]:
                _diag(errors, "to_sfen_mismatch", f"{base}/nodes/{index}/to_sfen", "to_sfen does not equal the replayed position")
            stack.append(("exit", None, None))
            stack.extend(
                ("enter", child_index, child)
                for child_index, child in reversed(children[node["key"]])
            )
        except (ValueError, IndexError):
            _diag(errors, "invalid_node_sfen", f"{base}/nodes/{index}/from_sfen", "node move cannot be replayed")
    return terminal_node_keys


def _validate_coverage_status(record, base, errors) -> None:
    provenance = record["provenance"]
    status = record["coverage_status"]
    allowed = {
        "A": {"complete_for_cited_sequence", "partial_explicit_sequence"},
        "B": {"diagram_reconstruction"},
        "C": {"name_only"},
        "M": {"mixed"},
    }
    if status not in allowed[provenance]:
        _diag(errors, "coverage_status_provenance", f"{base}/coverage_status", f"coverage status {status!r} is inconsistent with provenance {provenance!r}")
    if provenance == "A":
        omitted = record["coverage"]["omitted_after"]
        if status == "complete_for_cited_sequence" and omitted is not None:
            _diag(errors, "coverage_status_boundary", f"{base}/coverage/omitted_after", "complete cited sequence cannot have an omitted continuation")
        elif status == "partial_explicit_sequence" and omitted is None:
            _diag(errors, "coverage_status_boundary", f"{base}/coverage/omitted_after", "partial explicit sequence requires an omitted continuation")


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
    inactive = shogi.WHITE if board.turn == shogi.BLACK else shogi.BLACK
    if king_counts[inactive] == 1 and board.is_attacked_by(board.turn, board.king_squares[inactive]):
        _diag(errors, "initial_inactive_king_in_check", f"{base}/initial_sfen", "side-to-move attacks the inactive king")
    for (color, file_index), count in sorted(unpromoted_pawns.items()):
        if count > 1:
            _diag(errors, "initial_nifu", f"{base}/initial_sfen", f"color {color} has {count} unpromoted pawns on file index {file_index}")
    for piece_type, limit in _INVENTORY_LIMIT.items():
        if counts[piece_type] > limit:
            _diag(errors, "initial_piece_inventory", f"{base}/initial_sfen", f"piece type {piece_type} count {counts[piece_type]} exceeds inventory limit {limit}")


def _validate_coverage(
    record, base, by_key, children, depths, terminal_node_keys, errors
) -> None:
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
        if main["key"] in terminal_node_keys:
            _diag(
                errors,
                "omitted_after_game_end",
                f"{base}/coverage/omitted_after/usi",
                "omitted continuation appears after the semantic-main game ended",
            )
            return
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
