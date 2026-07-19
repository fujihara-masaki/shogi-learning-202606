"""Resolve the current next-move dataset to one representative per problem."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

from .next_move_identity import normalize_candidates, problem_key

logger = logging.getLogger(__name__)
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[dict[str, Any], ...]] = {}


def resolve_problems(conn) -> list[dict[str, Any]]:
    """Load samples and candidates in two queries, then deterministically deduplicate."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(learning_samples)")}
    has_run = "extraction_run_key" in columns and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='extraction_runs'"
    ).fetchone()
    run_select = "er.extracted_at AS extracted_at," if has_run else "NULL AS extracted_at,"
    run_join = "LEFT JOIN extraction_runs er ON er.extraction_run_key=ls.extraction_run_key" if has_run else ""
    rows = [dict(row) for row in conn.execute(f"""
        SELECT ls.*, {run_select} bs.imported_at, bs.id source_id, bs.name source_name,
               bs.version source_version, bs.license_name, bs.source_url, bs.copyright_notice
        FROM learning_samples ls JOIN book_sources bs ON bs.id=ls.book_source_id {run_join}
    """)]
    position_ids = sorted({row["book_position_id"] for row in rows})
    moves: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if position_ids:
        # Stay comfortably below SQLite's host-parameter limit on old builds.
        for start in range(0, len(position_ids), 500):
            chunk = position_ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for move in conn.execute(f"""
            SELECT bm.position_id,bm.usi move_usi,bm.score,bm.depth,bm.pv,bm.raw,bm.sort_order,
              bs.id source_id,bs.name source_name,bs.version source_version,bs.license_name,
              bs.source_url,bs.copyright_notice
            FROM book_moves bm JOIN book_positions bp ON bp.id=bm.position_id
            JOIN book_sources bs ON bs.id=bp.source_id WHERE bm.position_id IN ({marks})
            """, chunk):
                item = dict(move)
                item.update(rank=item["sort_order"] + 1 if item["sort_order"] is not None else None,
                            license=item["license_name"])
                moves[item["position_id"]].append(item)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidates = normalize_candidates(moves[row["book_position_id"]])
        source = {"name": row["source_name"], "version": row["source_version"], "source_url": row["source_url"]}
        row["candidates"] = candidates
        row["problem_key"] = problem_key(source, row["sfen"], candidates)
        groups[row["problem_key"]].append(row)
    representatives = []
    for key, values in groups.items():
        values.sort(key=lambda r: (r["extracted_at"] or r["imported_at"] or "", -r["sample_rank"], -r["id"]), reverse=True)
        representative = values[0]
        metadata = {(r["opening_key"], r["opening_name"]) for r in values}
        if len(metadata) > 1:
            logger.warning("Conflicting metadata for problem_key %s; representative sample %s selected", key, representative["id"])
        representatives.append(representative)
    representatives.sort(key=lambda r: (r["sample_rank"], r["problem_key"]))
    return representatives


def cached_resolve_problems(conn, *, dataset_version: str, database_path: str,
                            opening_key: str | None = None) -> list[dict[str, Any]]:
    """Reuse the expensive immutable classification for a dataset generation."""
    cache_key = (database_path, dataset_version)
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached is None:
        resolved = tuple(resolve_problems(conn))
        with _cache_lock:
            # Retain only the current generation of a database path.
            for old_key in [key for key in _cache if key[0] == database_path and key != cache_key]:
                del _cache[old_key]
            cached = _cache.setdefault(cache_key, resolved)
    values = list(cached)
    return values if opening_key is None else [row for row in values if row["opening_key"] == opening_key]


def clear_resolver_cache() -> None:
    """Test/import hook; runtime generations normally evict automatically."""
    with _cache_lock:
        _cache.clear()


def serialize_problem(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("id", "book_source_id", "book_position_id", "opening_key", "opening_name",
            "sfen", "sample_rank", "sample_reason", "created_at", "problem_key")} | {
        "source": {"id": row["source_id"], "name": row["source_name"], "version": row["source_version"],
                   "license_name": row["license_name"], "source_url": row["source_url"],
                   "copyright_notice": row["copyright_notice"]},
        "candidates": row["candidates"],
    }
