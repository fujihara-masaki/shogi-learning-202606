"""Validate the canonical Wikipedia opening provenance audit artifact.

This is deliberately an offline development tool: application startup does not
load JSON Schema (or the audit documents).  Error codes are stable API for CI.
"""

from __future__ import annotations

import argparse
import ast
import ipaddress
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def _is_valid_https_url(value: Any) -> bool:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    hostname = parsed.hostname
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if len(hostname) > 253:
        return False
    labels = hostname.split(".")
    if any(not label for label in labels):
        return False
    for label in labels:
        try:
            ascii_label = label.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        if len(ascii_label) > 63 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", ascii_label):
            return False
    return True


def _note_claims_unrecorded_move(
    note: str,
    omitted_after: str | None,
    omitted_aliases: set[str] | None = None,
    recorded_notations: set[str] | None = None,
) -> bool:
    recorded_claims = ("手順化", "収録")
    exclusion = ("未収録", "収録していない", "手順化していない")
    continuation_markers = ("実戦以下", "続く", "続いて", "その後", "以降")
    aliases = ({omitted_after} if omitted_after else set()) | (omitted_aliases or set())
    move_notation = re.compile(
        r"(?:[1-9][a-i][1-9][a-i]\+?|[PLNSGBR]\*[1-9][a-i]|[▲△]?[1-9][一二三四五六七八九][歩香桂銀金角飛玉と杏圭全馬龍](?:成|打)?)"
    )
    # Split both sentences and contrastive/coordinating subclauses so an
    # exclusion for one move cannot negate a recorded claim about another.
    for clause in re.split(r"[。！？\n、]+|(?:だが|ですが|けれども|一方|なお)", note):
        if not any(word in clause for word in recorded_claims):
            continue

        occurrences = [
            (alias, match.start(), match.end())
            for alias in aliases
            for match in re.finditer(re.escape(alias), clause)
        ]
        if occurrences:
            for _alias, start, end in occurrences:
                scope_start = 0
                has_previous_move = False
                for match in move_notation.finditer(clause, 0, start):
                    scope_start = match.end()
                    has_previous_move = True
                scope_end = len(clause)
                for match in move_notation.finditer(clause, end):
                    scope_end = match.start()
                    break
                scopes = [clause[end:scope_end]]
                if not has_previous_move:
                    scopes.insert(0, clause[scope_start:start])
                for scope in scopes:
                    if any(word in scope for word in exclusion):
                        continue
                    if any(word in scope for word in recorded_claims):
                        return True
            # Explicit aliases make target-scoped evidence authoritative; an
            # unrelated exclusion or recording claim must not affect them.
            continue

        notation_matches = list(move_notation.finditer(clause))
        if recorded_notations is not None and notation_matches:
            for index, match in enumerate(notation_matches):
                notation = match.group(0)
                if notation in recorded_notations:
                    continue
                left = clause[notation_matches[index - 1].end() if index else 0:match.start()]
                right = clause[match.end():notation_matches[index + 1].start() if index + 1 < len(notation_matches) else len(clause)]
                for scope in (left, right):
                    if any(word in scope for word in exclusion):
                        continue
                    if any(word in scope for word in recorded_claims):
                        return True
            # Explicitly named recorded moves and explicit exclusions are more
            # precise than the continuation-marker fallback.
            continue

        if any(word in clause for word in exclusion):
            continue
        if any(marker in clause for marker in continuation_markers):
            return True
    return False


def _japanese_omitted_move_aliases(
    moves: list[str], omitted_after: str | None, initial_sfen: str | None = None
) -> set[str]:
    """Derive a piece-specific Japanese alias without asserting next-ply legality."""
    if not omitted_after:
        return set()
    import shogi

    try:
        board = shogi.Board(initial_sfen) if initial_sfen is not None else shogi.Board()
        for usi in moves:
            move = shogi.Move.from_usi(usi)
            if move not in board.legal_moves:
                return set()
            board.push(move)
        omitted_move = shogi.Move.from_usi(omitted_after)
    except (ValueError, TypeError, AttributeError):
        return set()
    rank_kanji = "一二三四五六七八九"
    destination_usi = omitted_after.split("*", 1)[-1][:2] if "*" in omitted_after else omitted_after[2:4]
    destination = destination_usi[0] + rank_kanji[ord(destination_usi[1]) - ord("a")]

    if "*" in omitted_after:
        try:
            piece_name = shogi.Piece.from_symbol(omitted_after[0]).japanese_symbol()
        except (ValueError, TypeError, AttributeError):
            return set()
        # The source may omit intervening plies, so the dropping side is not
        # inferred from board.turn.  This side-neutral alias matches either ▲/△.
        return {f"{destination}{piece_name}打"}

    piece = board.piece_at(omitted_move.from_square)
    if piece is None:
        return set()
    side = "▲" if piece.color == shogi.BLACK else "△"
    piece_name = piece.japanese_symbol()
    if omitted_after.endswith("+"):
        if piece.is_promoted():
            return set()
        piece_name += "成"
    neutral_alias = f"{destination}{piece_name}"
    return {f"{side}{neutral_alias}", neutral_alias}


def _recorded_move_notations(nodes: list[dict[str, Any]], initial_sfen: str | None = None) -> set[str]:
    """Return USIs plus safely reconstructable Japanese aliases for all tree nodes."""
    import shogi

    result = {node.get("usi") for node in nodes if isinstance(node.get("usi"), str)}
    by_key = {node.get("move_key"): node for node in nodes}
    after_positions: dict[str, str] = {}
    visiting: set[str] = set()
    rank_kanji = "一二三四五六七八九"

    def prepare(key: str) -> None:
        if key in after_positions or key in visiting or key not in by_key:
            return
        visiting.add(key)
        node = by_key[key]
        parent_key = node.get("parent_key")
        if parent_key is not None:
            prepare(parent_key)
            if parent_key not in after_positions:
                visiting.remove(key)
                return
        if parent_key is not None:
            board = shogi.Board(after_positions[parent_key])
        else:
            board = shogi.Board(initial_sfen) if initial_sfen is not None else shogi.Board()
        try:
            move = shogi.Move.from_usi(node["usi"])
            if move not in board.legal_moves:
                visiting.remove(key)
                return
            destination_usi = node["usi"].split("*", 1)[-1][:2] if "*" in node["usi"] else node["usi"][2:4]
            destination = destination_usi[0] + rank_kanji[ord(destination_usi[1]) - ord("a")]
            if "*" in node["usi"]:
                piece_name = shogi.Piece.from_symbol(node["usi"][0]).japanese_symbol()
                side = "▲" if board.turn == shogi.BLACK else "△"
                neutral_alias = f"{destination}{piece_name}打"
                result.update({f"{side}{neutral_alias}", neutral_alias})
            else:
                piece = board.piece_at(move.from_square)
                if piece is not None:
                    piece_name = piece.japanese_symbol() + ("成" if node["usi"].endswith("+") else "")
                    side = "▲" if piece.color == shogi.BLACK else "△"
                    neutral_alias = f"{destination}{piece_name}"
                    result.update({f"{side}{neutral_alias}", neutral_alias})
            board.push(move)
            after_positions[key] = board.sfen()
        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
            pass
        visiting.remove(key)

    for key in by_key:
        if isinstance(key, str):
            prepare(key)
    return result


def _semantic_errors(record: dict[str, Any], initial_sfen: str | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    provenance = record.get("provenance_class")
    coverage = record.get("coverage")
    if provenance not in PROVENANCE_COVERAGE:
        errors.append(_error("invalid_provenance_class", record))
    elif coverage not in PROVENANCE_COVERAGE[provenance]:
        errors.append(_error("invalid_provenance_coverage", record))

    source = record.get("source", {})
    requested_url = source.get("requested_url")
    if requested_url is not None and not _is_valid_https_url(requested_url):
        errors.append(_error("requested_url_invalid", record, "source.requested_url"))
    canonical_url = source.get("canonical_url")
    if canonical_url is not None and not _is_valid_https_url(canonical_url):
        errors.append(_error("canonical_url_invalid", record, "source.canonical_url"))

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

    omitted_after = boundary.get("omitted_after")
    if omitted_after is not None:
        import shogi

        try:
            shogi.Move.from_usi(omitted_after)
        except (ValueError, TypeError):
            errors.append(_error("omitted_after_invalid_usi", record, "coverage_boundary.omitted_after"))
    omitted_aliases = _japanese_omitted_move_aliases(moves, omitted_after, initial_sfen)
    recorded_notations = _recorded_move_notations(nodes, initial_sfen)

    notes = [record.get("evidence_note", "")]
    notes += [node.get("provenance", {}).get("evidence_note", "") for node in nodes]
    notes += [segment.get("evidence_note", "") for segment in record.get("segments", [])]
    if any(
        _note_claims_unrecorded_move(note, omitted_after, omitted_aliases, recorded_notations)
        for note in notes
    ):
        errors.append(_error("note_claims_unrecorded_move", record))

    verification = record.get("verification", {})
    status = verification.get("status")
    if status == "verified":
        required = ("canonical_url", "source_section", "revision_id", "revision_timestamp", "retrieved_at", "source_license")
        if any(not source.get(field) for field in required):
            errors.append(_error("verified_source_metadata_missing", record))
    if status == "unavailable" and any(source.get(field) is not None for field in ("canonical_url", "revision_id", "revision_timestamp")):
        errors.append(_error("unavailable_source_metadata_inferred", record))

    keys = {node.get("move_key") for node in nodes}
    duplicate_keys = len(keys) != len(nodes)
    if duplicate_keys:
        errors.append(_error("duplicate_move_key", record))
    for index, node in enumerate(nodes):
        parent = node.get("parent_key")
        if parent is not None and parent not in keys:
            errors.append(_error("parent_key_missing", record, f"nodes[{index}]"))
        node_provenance = node.get("provenance", {})
        if status == "verified" and node_provenance.get("review_status") != "verified":
            errors.append(_error("verified_line_node_unverified", record, f"nodes[{index}]"))
        if node_provenance.get("review_status") == "verified" and not node_provenance.get("source_section"):
            errors.append(_error("verified_node_source_section_missing", record, f"nodes[{index}]"))
        if node_provenance.get("review_status") == "verified" and node_provenance.get("provenance_class") not in {
            "explicit_sequence", "diagram_reconstruction"
        }:
            errors.append(_error("verified_node_provenance_invalid", record, f"nodes[{index}]"))
        if provenance in {"explicit_sequence", "diagram_reconstruction"} and node_provenance.get("provenance_class") != provenance:
            errors.append(_error("node_line_provenance_mismatch", record, f"nodes[{index}]"))

    siblings: dict[str | None, list[dict[str, Any]]] = {}
    for node in nodes:
        siblings.setdefault(node.get("parent_key"), []).append(node)
    for parent_key, children in siblings.items():
        if sum(child.get("is_main") is True for child in children) != 1:
            errors.append(_error("sibling_main_count_invalid", record, f"parent[{parent_key}]"))
        if len({child.get("usi") for child in children}) != len(children):
            errors.append(_error("duplicate_sibling_usi", record, f"parent[{parent_key}]"))
        if len({child.get("sort_order") for child in children}) != len(children):
            errors.append(_error("duplicate_sibling_sort_order", record, f"parent[{parent_key}]"))

    # A duplicate key makes parent lookup ambiguous, so report it above and do
    # not pretend that a cycle/root result from an arbitrary duplicate is valid.
    if not duplicate_keys:
        by_key = {node.get("move_key"): node for node in nodes}
        reported_cycles: set[frozenset[str]] = set()
        for start_key in by_key:
            path: list[str] = []
            positions: dict[str, int] = {}
            key: str | None = start_key
            while key is not None and key in by_key and key not in positions:
                positions[key] = len(path)
                path.append(key)
                key = by_key[key].get("parent_key")
            if key in positions:
                cycle = frozenset(path[positions[key]:])
                if cycle not in reported_cycles:
                    reported_cycles.add(cycle)
                    code = "self_parent_cycle" if len(cycle) == 1 else "parent_cycle"
                    errors.append(_error(code, record, f"nodes[{start_key}]"))
            elif key is not None:
                # Missing parents have their own precise error, while this code
                # states the resulting invariant failure explicitly.
                errors.append(_error("node_not_connected_to_virtual_root", record, f"nodes[{start_key}]"))

    # Reconstruct the semantic main chain for every move-line.  Array order is
    # only serialization order and branches may occur anywhere in ``nodes``.
    main_chain: list[dict[str, Any]] = []
    parent_key = None
    visited_main: set[str] = set()
    while parent_key in siblings:
        main_children = [node for node in siblings[parent_key] if node.get("is_main") is True]
        if len(main_children) != 1:
            # sibling_main_count_invalid above carries the structural detail.
            break
        node = main_children[0]
        move_key = node.get("move_key")
        if move_key in visited_main:
            errors.append(_error("semantic_main_chain_cycle", record))
            break
        visited_main.add(move_key)
        main_chain.append(node)
        parent_key = move_key
    if len(main_chain) != len(moves) or [node.get("usi") for node in main_chain] != moves:
        errors.append(_error("semantic_main_chain_mismatch", record))

    segments = record.get("segments", [])
    if provenance == "mixed":
        unresolved = "mixed_segment_boundary_unresolved" in record.get("audit_issues", [])
        if unresolved and segments:
            errors.append(_error("mixed_unresolved_with_segments", record))
        if status == "verified" and unresolved:
            errors.append(_error("mixed_segment_boundary_unresolved", record))
        if segments:
            classes = {segment.get("provenance_class") for segment in segments}
            if not {"explicit_sequence", "diagram_reconstruction"} <= classes:
                errors.append(_error("mixed_missing_provenance_class", record))
            covered = [ply for segment in segments for ply in range(segment.get("start_ply", 0), segment.get("end_ply", -1) + 1)]
            if covered != list(range(1, len(moves) + 1)):
                errors.append(_error("mixed_segment_range_invalid", record))
            for ply, node in enumerate(main_chain, start=1):
                matching = [s for s in segments if s["start_ply"] <= ply <= s["end_ply"]]
                if matching and node.get("provenance", {}).get("provenance_class") != matching[0]["provenance_class"]:
                    errors.append(_error("node_segment_provenance_mismatch", record, f"nodes[{node.get('move_key')}]"))
        elif not (status in {"unavailable", "needs_review"} and unresolved):
            errors.append(_error("mixed_segments_missing", record))
    elif segments:
        errors.append(_error("segments_for_non_mixed", record))
    return errors


def _seed_errors(artifact: dict[str, Any], seed_lines: list[dict[str, Any]]) -> list[ValidationError]:
    from app.seed import _prepare_opening_move_nodes
    import shogi

    from app.seed import _opening_source_metadata

    records = {record.get("line_name"): record for record in artifact.get("records", []) if record.get("subject_kind") == "move_line"}
    errors: list[ValidationError] = []
    normalized: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_names: set[str] = set()
    for index, raw_line in enumerate(seed_lines):
        path = f"seed_lines[{index}]"
        if not isinstance(raw_line, dict):
            errors.append(ValidationError("seed_entry_invalid", path=path))
            continue
        name = raw_line.get("name")
        if not isinstance(name, str) or not name:
            errors.append(ValidationError("seed_entry_invalid", path=path))
            continue
        if name in seen_names:
            errors.append(_error("duplicate_seed_line_name", records.get(name), path))
            continue
        seen_names.add(name)
        try:
            metadata = _opening_source_metadata(raw_line)
        except (ValueError, TypeError, AttributeError, KeyError):
            errors.append(_error("seed_entry_invalid", records.get(name), path))
            continue
        normalized.append((raw_line, metadata))

    # Membership is the union of audited names and normalized current source
    # types.  Thus metadata drift cannot hide an existing line and a newly
    # introduced Wikipedia/Wikibooks line cannot evade the audit.
    wikipedia = [
        (line, metadata) for line, metadata in normalized
        if line["name"] in records or metadata.get("source_type") in {"wikipedia", "wikibooks"}
    ]
    snapshot_line_count = artifact.get("seed_snapshot", {}).get("line_count")
    if snapshot_line_count != len(records) or snapshot_line_count != len(wikipedia):
        errors.append(_error("seed_snapshot_line_count_mismatch"))
    if len(records) != len(wikipedia):
        errors.append(_error("seed_line_count_mismatch"))
    for line, metadata in wikipedia:
        record = records.get(line["name"])
        if not record:
            errors.append(ValidationError("seed_line_missing", line["name"]))
            continue
        initial = line.get("initial_sfen", shogi.STARTING_SFEN)
        try:
            prepared = _prepare_opening_move_nodes(line, initial)
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
            # The parser/legality/tree error text is intentionally not part of
            # the stable API.  Keep validating the remaining audited lines and
            # let the CLI serialize this record-scoped failure as JSON.
            errors.append(_error("seed_tree_invalid", record, "seed"))
            continue
        expected = [{"move_key": n["key"], "parent_key": n["parent_key"], "usi": n["usi"], "is_main": n["is_main"], "sort_order": n["sort_order"], "variation_group": n["variation_group"]} for n in prepared]
        actual = [{key: n.get(key) for key in expected[0]} for n in record.get("nodes", [])] if expected else []
        if {tuple(item.items()) for item in expected} != {tuple(item.items()) for item in actual}:
            errors.append(_error("seed_node_tree_mismatch", record))
        if record.get("moves") != line.get("moves"):
            errors.append(_error("seed_main_moves_mismatch", record))
        source = record.get("source", {})
        comparisons = {
            "source_url": (metadata.get("source_url"), source.get("requested_url")),
            "source_title": (metadata.get("source_title"), source.get("source_title")),
            "source_type": (metadata.get("source_type"), source.get("source_type")),
            "source_section": (metadata.get("source_section") or None, source.get("source_section") or None),
            "source_license": (metadata.get("source_license"), source.get("source_license")),
            "source_note": (metadata.get("source_note"), record.get("evidence_note")),
            "coverage_status": (metadata.get("coverage_status"), record.get("legacy_coverage_status")),
        }
        for field, (seed_value, audit_value) in comparisons.items():
            if seed_value != audit_value:
                errors.append(_error(f"seed_metadata_{field}_mismatch", record, field))
    if artifact.get("seed_snapshot", {}).get("node_count") != sum(len(r.get("nodes", [])) for r in records.values()):
        errors.append(_error("seed_snapshot_node_count_mismatch"))
    return errors


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError(f"missing literal assignment: {name}")


def _extract_snapshot_seed_lines(source: str) -> list[dict[str, Any]]:
    """Safely extract the audited seed and its literal metadata defaults."""
    try:
        tree = ast.parse(source)
        lines = _literal_assignment(tree, "SAMPLE_OPENING_LINES")
        defaults = _literal_assignment(tree, "WIKIPEDIA_OPENING_SOURCE_DEFAULTS")
        by_name = _literal_assignment(tree, "WIKIPEDIA_OPENING_SOURCE_BY_NAME")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise ValueError("snapshot source is not a supported literal seed") from exc
    if not isinstance(lines, list) or not isinstance(defaults, dict) or not isinstance(by_name, dict):
        raise ValueError("snapshot seed literals have invalid types")

    # Freeze the historical defaults into each line.  _seed_errors may then
    # reuse today's canonical normalizer without silently substituting today's
    # defaults for values declared by the historical source.
    result = []
    metadata_keys = {
        "source_url", "source_title", "license", "source_type", "source_section",
        "source_license", "source_retrieved_at", "source_note", "coverage_status",
    }
    for raw_line in lines:
        if not isinstance(raw_line, dict) or not isinstance(raw_line.get("name"), str):
            raise ValueError("snapshot opening line is invalid")
        line = dict(raw_line)
        metadata = dict(defaults)
        override = by_name.get(line["name"], {})
        if not isinstance(override, dict):
            raise ValueError("snapshot metadata override is invalid")
        metadata.update(override)
        metadata.update({key: line[key] for key in metadata_keys if key in line})
        line.update({key: value for key, value in metadata.items() if key in metadata_keys})
        result.append(line)
    return result


def _normalized_initial_sfen(line: dict[str, Any]) -> str:
    import shogi

    initial = line.get("initial_sfen", shogi.STARTING_SFEN)
    if initial == "startpos":
        initial = shogi.STARTING_SFEN
    return shogi.Board(initial).sfen()


def _initial_positions_match(
    artifact: dict[str, Any], current_lines: list[dict[str, Any]], snapshot_lines: list[dict[str, Any]]
) -> bool:
    audited_names = {
        record.get("line_name") for record in artifact.get("records", [])
        if record.get("subject_kind") == "move_line"
    }
    current = {line.get("name"): line for line in current_lines if isinstance(line, dict) and line.get("name") in audited_names}
    snapshot = {line.get("name"): line for line in snapshot_lines if isinstance(line, dict) and line.get("name") in audited_names}
    if set(current) != audited_names or set(snapshot) != audited_names:
        return False
    try:
        return all(_normalized_initial_sfen(current[name]) == _normalized_initial_sfen(snapshot[name]) for name in audited_names)
    except (ValueError, TypeError, AttributeError, KeyError):
        return False


def _declared_snapshot_errors(
    artifact: dict[str, Any], repo_root: Path | None = None, current_seed_lines: list[dict[str, Any]] | None = None
) -> list[ValidationError]:
    snapshot = artifact.get("seed_snapshot", {})
    commit, source_file = snapshot.get("commit"), snapshot.get("source_file")
    root = repo_root or Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{source_file}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except UnicodeDecodeError:
        return [ValidationError("seed_snapshot_source_invalid")]
    except OSError:
        return [ValidationError("seed_snapshot_commit_unavailable")]
    if completed.returncode != 0:
        return [ValidationError("seed_snapshot_commit_unavailable")]
    try:
        snapshot_lines = _extract_snapshot_seed_lines(completed.stdout)
    except ValueError:
        return [ValidationError("seed_snapshot_source_invalid")]
    if _seed_errors(artifact, snapshot_lines):
        return [ValidationError("seed_snapshot_content_mismatch")]
    if current_seed_lines is not None and not _initial_positions_match(artifact, current_seed_lines, snapshot_lines):
        return [ValidationError("seed_snapshot_content_mismatch", path="initial_sfen")]
    return []


def validate_artifact(data: dict[str, Any], schema: dict[str, Any] | None = None, seed_lines: list[dict[str, Any]] | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if schema is not None:
        from jsonschema import Draft7Validator, FormatChecker

        validator = Draft7Validator(schema, format_checker=FormatChecker())
        for failure in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
            errors.append(ValidationError("schema_validation_error", path="/".join(map(str, failure.absolute_path))))
        if errors:
            return errors
    records = data.get("records", [data])
    record_ids = [record.get("record_id") for record in records if record.get("record_id") is not None]
    if len(record_ids) != len(set(record_ids)):
        errors.append(ValidationError("duplicate_record_id"))
    line_names = [
        record.get("line_name") for record in records
        if record.get("subject_kind") == "move_line" and record.get("line_name") is not None
    ]
    if len(line_names) != len(set(line_names)):
        errors.append(ValidationError("duplicate_move_line_name"))
    initial_by_line_name: dict[str, str] = {}
    if seed_lines is not None:
        for line in seed_lines:
            if not isinstance(line, dict) or not isinstance(line.get("name"), str):
                continue
            try:
                initial_by_line_name[line["name"]] = _normalized_initial_sfen(line)
            except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
                # _seed_errors reports malformed canonical seed data using its
                # stable seed_tree_invalid/seed_entry_invalid contract.
                continue
    for record in records:
        errors.extend(_semantic_errors(record, initial_by_line_name.get(record.get("line_name"))))
    if seed_lines is not None:
        errors.extend(_seed_errors(data, seed_lines))
    return errors


def validate_production_artifact(data: dict[str, Any], schema: dict[str, Any] | None) -> list[ValidationError]:
    """Validate an artifact through the production path, including the seed.

    ``validate_artifact(..., seed_lines=None)`` remains useful for deliberately
    synthetic semantic fixtures.  Production callers must use this entry point
    so positionally invalid or drifted moves cannot pass merely by changing both
    ``moves`` and the node snapshot to the same value.
    """
    if schema is None:
        return [ValidationError("production_schema_required")]

    from app.seed import SAMPLE_OPENING_LINES

    errors = validate_artifact(data, schema, SAMPLE_OPENING_LINES)
    if any(error.code == "schema_validation_error" for error in errors):
        return errors
    errors.extend(_declared_snapshot_errors(data, current_seed_lines=SAMPLE_OPENING_LINES))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    # Retained as a no-op for compatibility with the D1 command documented
    # during review.  The production CLI now *always* checks the seed.
    parser.add_argument("--check-seed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    decode_errors = []
    try:
        data = json.loads(args.artifact.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        decode_errors.append(ValidationError("artifact_json_invalid", path="artifact"))
        data = None
    try:
        schema = json.loads(args.schema.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        decode_errors.append(ValidationError("schema_json_invalid", path="schema"))
        schema = None
    if decode_errors:
        print(json.dumps({"valid": False, "errors": [error.as_dict() for error in decode_errors]}, ensure_ascii=False))
        return 1
    errors = validate_production_artifact(data, schema)
    print(json.dumps({"valid": not errors, "errors": [error.as_dict() for error in errors]}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
