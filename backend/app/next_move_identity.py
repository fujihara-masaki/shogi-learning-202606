"""Stable identities shared by next-move import, runtime, and validation."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

import shogi

PROBLEM_DEFINITION_VERSION = 1


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    if isinstance(value, tuple):
        return [_nfc(item) for item in value]
    if isinstance(value, dict):
        return {_nfc(key): _nfc(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_nfc(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return "v1:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_source_key(source: Mapping[str, Any]) -> str:
    return canonical_hash({"name": source.get("name"), "source_url": source.get("source_url"), "version": source.get("version")})


def normalize_sfen(sfen: str) -> str:
    # python-shogi canonicalizes board, turn and hand. Ply is deliberately excluded.
    return " ".join(shogi.Board(sfen).sfen().split()[:3])


def normalize_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for index, candidate in enumerate(candidates, 1):
        rank = candidate.get("effective_rank", candidate.get("rank"))
        if rank is None:
            sort_order = candidate.get("sort_order")
            rank = sort_order + 1 if sort_order is not None else index
        values.append({**dict(candidate), "effective_rank": int(rank)})
    values.sort(key=lambda c: (
        c["effective_rank"], c.get("score") is None, -(c.get("score") or 0),
        c.get("depth") is None, -(c.get("depth") or 0), c["move_usi"],
    ))
    return [{**candidate, "judgment_position": index} for index, candidate in enumerate(values, 1)]


def candidate_definition_fingerprint(candidates: Iterable[Mapping[str, Any]]) -> str:
    return canonical_hash([{
        "judgment_position": c["judgment_position"], "effective_rank": c["effective_rank"], "move_usi": c["move_usi"],
    } for c in normalize_candidates(candidates)])


def problem_key(source: Mapping[str, Any], sfen: str, candidates: Iterable[Mapping[str, Any]], *, problem_definition_version: int = PROBLEM_DEFINITION_VERSION) -> str:
    return canonical_hash({
        "candidate_definition_fingerprint": candidate_definition_fingerprint(candidates),
        "normalized_sfen": normalize_sfen(sfen),
        "problem_definition_version": problem_definition_version,
        "stable_source_key": stable_source_key(source),
    })


def extraction_run_key(metadata: Mapping[str, Any]) -> str:
    return canonical_hash(dict(metadata))


def file_dataset_version(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "v1:sha256-file:" + digest.hexdigest()


def get_dataset_version(conn, path: Path) -> str:
    table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='database_metadata'").fetchone()
    if table:
        row = conn.execute("SELECT value FROM database_metadata WHERE key='dataset_version'").fetchone()
        if row and row[0]:
            return row[0]
    return file_dataset_version(path)
