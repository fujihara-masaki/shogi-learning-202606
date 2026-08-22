"""D1c projection of reviewed canonical Wikipedia artifacts into runtime seeds.

The D1b validator is deliberately the sole artifact gate.  Revision, node
provenance/evidence, segments, normalized coverage status and coverage boundary
remain in the canonical artifact as audit data because the runtime schema has
no lossless columns for them.  In particular, normalized ``coverage_status``
is never written to the legacy free-text column of the same name.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .seed import (
    static_opening_seed_key_for_name,
    upsert_opening_move_nodes,
    validate_opening_move_tree,
)
from .wikipedia_opening_validator import validate_wikipedia_opening_artifact


class ArtifactImportError(ValueError):
    """The artifact did not pass the canonical D1b gate."""


def _source_type(source_url: str) -> str:
    """Project the already-D1b-approved Wikimedia host to runtime metadata."""
    host = (urlsplit(source_url).hostname or "").lower()
    if host == "wikibooks.org" or host.endswith(".wikibooks.org"):
        return "wikibooks"
    if host == "wikipedia.org" or host.endswith(".wikipedia.org"):
        return "wikipedia"
    # This is unreachable after the D1b gate.  Keep failure explicit if that
    # contract ever changes rather than silently writing misleading metadata.
    raise ValueError(f"unsupported canonical source host: {host!r}")


def _article_identity(source_url: str) -> str:
    """Normalize article identity while ignoring only revision and fragment."""
    parsed = urlsplit(source_url)
    host = (parsed.hostname or "").lower()
    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    query = urlencode(sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "oldid"
    ))
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, query, ""))


def _move_records(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    if diagnostics:
        details = "; ".join(f"{item.path or '/'} [{item.code}] {item.message}" for item in diagnostics)
        raise ArtifactImportError(details)
    return [record for record in artifact["records"] if record["record_type"] == "move_line"]


def _ordered_nodes(record: dict[str, Any]) -> list[dict[str, Any]]:
    children: dict[str | None, list[str]] = defaultdict(list)
    for node in record["nodes"]:
        children[node["parent_key"]].append(node["key"])
    depth: dict[str, int] = {}
    pending = [(key, 1) for key in children[None]]
    while pending:
        key, current_depth = pending.pop()
        depth[key] = current_depth
        pending.extend((child, current_depth + 1) for child in children[key])

    return [
        {**node, "ply": depth[node["key"]]}
        for node in sorted(record["nodes"], key=lambda node: (depth[node["key"]], node["sort_order"], node["key"]))
    ]


def _main_projection(nodes: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        children[node["parent_key"]].append(node)
    moves, sfens = [], []
    parent = None
    while parent in children:
        node = next(item for item in children[parent] if item["is_main"])
        moves.append(node["usi"])
        sfens.append(node["to_sfen"])
        parent = node["key"]
    return moves, sfens


def apply_wikipedia_opening_artifact(conn, artifact: dict[str, Any]) -> list[int]:
    """Validate the complete artifact, then atomically apply each move line.

    ``catalog_name_only`` records are intentionally ignored: they cannot create
    move seeds and catalog synchronization is outside D1c.
    """
    records = _move_records(artifact)  # no write may precede this call
    name_counts = Counter(record["line_name"] for record in records)
    applied = []
    for ordinal, record in enumerate(records):
        savepoint = f"wikipedia_line_{ordinal}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            source_type = _source_type(record["source"]["url"])
            line = conn.execute(
                "SELECT * FROM opening_lines WHERE line_key=?", (record["line_key"],)
            ).fetchone()
            if line is None and name_counts[record["line_name"]] == 1:
                # One-time backwards-compatible claim.  Rename matching is
                # never used after line_key has been persisted.  Ambiguous
                # display names are never guessed from artifact record order.
                candidates = conn.execute(
                    "SELECT * FROM opening_lines WHERE line_key='' AND source_id IS NULL AND name=? ORDER BY id",
                    (record["line_name"],),
                ).fetchall()
                if len(candidates) == 1:
                    line = candidates[0]
                    seed_key = static_opening_seed_key_for_name(line["name"])
                    conn.execute(
                        "UPDATE opening_lines SET line_key=?, seed_key=? WHERE id=?",
                        (record["line_key"], seed_key, line["id"]),
                    )
            if line is None:
                line_id = int(conn.execute(
                    """INSERT INTO opening_lines
                       (line_key, name, opening_type, initial_sfen, moves, comments,
                        source_url, source_title, license, source_note, source_type,
                        source_section, source_license, source_retrieved_at)
                       VALUES (?, ?, '', ?, '[]', '[]', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record["line_key"], record["line_name"], record["initial_sfen"],
                     record["source"]["url"], record["source"]["title"], record["license"],
                     record["source_note"], source_type, record["source"]["section"], record["license"],
                     record["retrieved_date"]),
                ).lastrowid)
            else:
                line_id = int(line["id"])
            nodes = _ordered_nodes(record)
            main_moves, main_sfens = _main_projection(nodes)
            conn.execute(
                """UPDATE opening_lines SET name=?, initial_sfen=?, moves=?,
                   source_url=?, source_title=?, license=?, source_note=?, source_type=?,
                   source_section=?, source_license=?, source_retrieved_at=?, updated_at=datetime('now')
                   WHERE id=?""",
                (record["line_name"], record["initial_sfen"], json.dumps(main_moves),
                 record["source"]["url"], record["source"]["title"], record["license"],
                 record["source_note"], source_type, record["source"]["section"], record["license"],
                 record["retrieved_date"], line_id),
            )
            upsert_opening_move_nodes(conn, line_id, nodes)
            persisted = conn.execute(
                "SELECT move_key, comment FROM opening_line_moves WHERE line_id=?",
                (line_id,),
            ).fetchall()
            comments_by_key = {row["move_key"]: row["comment"] for row in persisted}
            main_comments = []
            parent_key = None
            children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
            for node in nodes:
                children[node["parent_key"]].append(node)
            while parent_key in children:
                main = next(node for node in children[parent_key] if node["is_main"])
                main_comments.append(comments_by_key[main["key"]])
                parent_key = main["key"]
            conn.execute(
                "UPDATE opening_lines SET comments=? WHERE id=?",
                (json.dumps(main_comments, ensure_ascii=False), line_id),
            )
            conn.execute("DELETE FROM opening_positions WHERE line_id=?", (line_id,))
            conn.execute("INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, 0, ?)", (line_id, record["initial_sfen"]))
            for ply, sfen in enumerate(main_sfens, 1):
                conn.execute("INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, ?, ?)", (line_id, ply, sfen))
            validate_opening_move_tree(conn, [line_id])
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            applied.append(line_id)
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
    return applied


def compare_canonical_to_runtime(conn, record: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic projection diff without conflating coverage fields."""
    line = conn.execute("SELECT * FROM opening_lines WHERE line_key=?", (record["line_key"],)).fetchone()
    if line is None:
        return {"line_key": record["line_key"], "status": "added", "nodes": []}
    rows = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (line["id"],)).fetchall()
    db = {row["move_key"]: row for row in rows}
    ordered_nodes = _ordered_nodes(record)
    canonical = {node["key"]: node for node in ordered_nodes}
    main_moves, main_sfens = _main_projection(ordered_nodes)
    changes = []
    for key in sorted(canonical.keys() | db.keys()):
        if key not in db:
            changes.append({"key": key, "status": "added"})
        elif key not in canonical:
            changes.append({"key": key, "status": "removed"})
        else:
            parent = db[key]["parent_move_id"]
            db_parent = next((row["move_key"] for row in rows if row["id"] == parent), None)
            fields = [name for name in ("ply", "usi", "is_main", "variation_group", "from_sfen", "to_sfen") if db[key][name] != canonical[key][name]]
            if db_parent != canonical[key]["parent_key"]:
                fields.append("parent")
            if db[key]["sort_order"] != canonical[key]["sort_order"]:
                fields.append("sort_order")
            changes.append({"key": key, "status": "changed" if fields else "unchanged", "fields": fields})
    metadata_fields = [
        ("name", "line_name"), ("initial_sfen", "initial_sfen"), ("source_url", None),
        ("source_title", None), ("source_section", None), ("source_type", None),
        ("license", "license"), ("source_license", "license"),
        ("source_note", "source_note"), ("source_retrieved_at", "retrieved_date"),
    ]
    expected = {
        "source_url": record["source"]["url"],
        "source_title": record["source"]["title"],
        "source_section": record["source"]["section"],
        "source_type": _source_type(record["source"]["url"]),
    }
    metadata = [
        db_name for db_name, artifact_name in metadata_fields
        if line[db_name] != (expected[db_name] if artifact_name is None else record[artifact_name])
    ]
    try:
        persisted_moves = json.loads(line["moves"])
    except (json.JSONDecodeError, TypeError):
        persisted_moves = line["moves"]
    moves_diff = {
        "status": "unchanged" if persisted_moves == main_moves else "changed",
        "expected": main_moves,
        "actual": persisted_moves,
    }
    expected_positions = [
        {"ply": ply, "sfen": sfen}
        for ply, sfen in enumerate([record["initial_sfen"], *main_sfens])
    ]
    actual_positions = [
        {"ply": row["ply"], "sfen": row["sfen"]}
        for row in conn.execute(
            "SELECT ply, sfen FROM opening_positions WHERE line_id=? ORDER BY ply, id",
            (line["id"],),
        ).fetchall()
    ]
    positions_diff = {
        "status": "unchanged" if actual_positions == expected_positions else "changed",
        "expected": expected_positions,
        "actual": actual_positions,
    }
    changed = (
        metadata
        or any(node["status"] != "unchanged" for node in changes)
        or moves_diff["status"] == "changed"
        or positions_diff["status"] == "changed"
    )
    return {
        "line_key": record["line_key"],
        "status": "changed" if changed else "unchanged",
        "metadata_changed": metadata,
        "nodes": changes,
        "moves": moves_diff,
        "positions": positions_diff,
        "canonical_only": [
            "revision", "provenance", "coverage_status", "coverage",
            "evidence_note", "segments",
        ],
    }


def compare_canonical_to_legacy(record: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
    """Compare known legacy snapshot values; report missing facts, never infer them."""
    candidates = [item for item in legacy.get("records", []) if item.get("line_name") == record["line_name"]]
    if not candidates:
        return {"line_key": record["line_key"], "status": "added", "unverifiable": []}
    old = candidates[0]
    old_nodes = {node["move_key"]: node for node in old.get("nodes", [])}
    node_changes = []
    for node in record["nodes"]:
        prior = old_nodes.get(node["key"])
        if prior is None:
            node_changes.append({"key": node["key"], "status": "added"})
            continue
        fields = [field for field in ("usi", "parent_key", "sort_order", "is_main", "variation_group") if prior.get(field) != node[field]]
        node_changes.append({"key": node["key"], "status": "changed" if fields else "unchanged", "fields": fields})
    node_changes.extend({"key": key, "status": "removed"} for key in sorted(old_nodes.keys() - {n["key"] for n in record["nodes"]}))
    unavailable = [
        field
        for field, value in (
            ("revision", old.get("source", {}).get("revision_id")),
            ("verified_section", old.get("source", {}).get("source_section")),
            ("review", old.get("verification", {}).get("status")),
        )
        if value in (None, "unavailable") or (field == "review" and value != "verified")
    ]
    legacy_source = old.get("source", {})
    canonical_url = legacy_source.get("canonical_url")
    if canonical_url is None:
        unavailable.append("canonical_url")
    metadata = []
    revision_id = legacy_source.get("revision_id")
    if revision_id not in (None, "unavailable") and revision_id != record["revision"]:
        metadata.append("revision")
    if canonical_url is not None and _article_identity(canonical_url) != _article_identity(record["source"]["url"]):
        metadata.append("canonical_url")
    for name, prior, current in (
        ("line_name", old.get("line_name"), record["line_name"]),
        ("source_title", legacy_source.get("source_title"), record["source"]["title"]),
        ("source_section", legacy_source.get("source_section"), record["source"]["section"]),
        ("source_type", legacy_source.get("source_type"), _source_type(record["source"]["url"])),
        ("retrieved_at", legacy_source.get("retrieved_at"), record["retrieved_date"]),
        ("license", legacy_source.get("source_license"), record["license"]),
    ):
        if prior is not None and prior != current:
            metadata.append(name)
    legacy_coverage = old.get("coverage")
    if legacy_coverage is not None and legacy_coverage != record["coverage_status"]:
        metadata.append("coverage_status")
    changed = metadata or any(item["status"] != "unchanged" for item in node_changes)
    return {"line_key": record["line_key"], "status": "changed" if changed else "unchanged", "metadata_changed": metadata, "nodes": node_changes, "unverifiable": unavailable}
