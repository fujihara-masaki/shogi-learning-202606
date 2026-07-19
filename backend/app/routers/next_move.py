"""Transactional recording of next-move answers."""
from __future__ import annotations

import sqlite3
import logging
import random
from typing import Literal

import shogi
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_connection, latest_next_move_results
from ..next_move_database import NextMoveDatabaseUnavailable, get_next_move_connection
from ..next_move_identity import (PROBLEM_DEFINITION_VERSION, candidate_definition_fingerprint, get_dataset_version,
    normalize_candidates, normalize_sfen, problem_key, stable_source_key)
from ..next_move_resolver import cached_resolve_problems, serialize_problem
from ..next_move_database import next_move_db_path

router = APIRouter(prefix="/api/next-move", tags=["next-move"])
logger = logging.getLogger(__name__)


class ResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: int
    problem_key: str
    move_usi: str
    hint_count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)


def error(status: int, detail: str, code: str) -> HTTPException:
    # FastAPI normally nests detail; returning this value is normalized by the app handler.
    return HTTPException(status_code=status, detail={"detail": detail, "code": code})


def _load(sample_id: int):
    try:
        conn = get_next_move_connection()
    except NextMoveDatabaseUnavailable as exc:
        raise error(503, str(exc), "NEXT_MOVE_DATABASE_UNAVAILABLE") from exc
    try:
        row = conn.execute("""
          SELECT ls.*, bs.name source_name, bs.version source_version, bs.source_url, bs.file_sha256
          FROM learning_samples ls JOIN book_sources bs ON bs.id=ls.book_source_id WHERE ls.id=?
        """, (sample_id,)).fetchone()
        if not row:
            raise error(404, "問題が見つかりません", "NEXT_MOVE_PROBLEM_NOT_FOUND")
        moves = [dict(r) for r in conn.execute(
            "SELECT usi move_usi, score, depth, sort_order FROM book_moves WHERE position_id=?",
            (row["book_position_id"],),
        )]
        candidates = normalize_candidates(moves)
        source = {"name": row["source_name"], "version": row["source_version"], "source_url": row["source_url"]}
        return dict(row), candidates, source
    finally:
        conn.close()


@router.post("/results")
def record_result(body: ResultInput):
    row, candidates, source = _load(body.sample_id)
    current_key = problem_key(source, row["sfen"], candidates)
    if current_key != body.problem_key:
        raise error(409, "問題データが更新されました。再読み込みしてください", "NEXT_MOVE_PROBLEM_CHANGED")
    try:
        board = shogi.Board(row["sfen"])
        move = shogi.Move.from_usi(body.move_usi)
    except (ValueError, TypeError, IndexError):
        raise error(422, "指し手の形式が正しくありません", "NEXT_MOVE_MOVE_FORMAT_INVALID")
    if move not in board.legal_moves:
        raise error(422, "この局面では指せない手です", "NEXT_MOVE_ILLEGAL_MOVE")
    found = next((c for c in candidates if c["move_usi"] == body.move_usi), None)
    position = found["judgment_position"] if found else None
    rank = found["effective_rank"] if found else None
    verdict: Literal["top", "strong", "listed", "unlisted"] = (
        "unlisted" if not found else "top" if position == 1 else "strong" if rank <= 3 else "listed"
    )
    conn = get_connection()
    try:
        with conn:
            conn.execute("""INSERT INTO next_move_problem_refs(
                problem_key,stable_source_key,normalized_sfen,candidate_definition_fingerprint,
                problem_definition_version,last_extraction_run_key,last_source_file_sha256)
              VALUES(?,?,?,?,?,?,?) ON CONFLICT(problem_key) DO UPDATE SET
                last_extraction_run_key=excluded.last_extraction_run_key,
                last_source_file_sha256=excluded.last_source_file_sha256,last_seen_at=datetime('now')""",
              (current_key, stable_source_key(source), normalize_sfen(row["sfen"]),
               candidate_definition_fingerprint(candidates), PROBLEM_DEFINITION_VERSION,
               row.get("extraction_run_key") or "unknown", row["file_sha256"]))
            cursor = conn.execute("""INSERT INTO next_move_results(
                problem_key,opening_key_at_answer,opening_name_at_answer,move_usi,verdict,
                candidate_rank,judgment_position,hint_count,elapsed_ms)
                VALUES(?,?,?,?,?,?,?,?,?)""", (current_key, row["opening_key"], row["opening_name"], body.move_usi,
                verdict, rank, position, body.hint_count, body.elapsed_ms))
        return {"id": cursor.lastrowid, "verdict": verdict, "candidate_rank": rank, "judgment_position": position}
    except sqlite3.Error as exc:
        conn.rollback()
        raise error(500, "解答記録を保存できませんでした", "NEXT_MOVE_RESULT_SAVE_FAILED") from exc
    finally:
        conn.close()


def _current_problems(opening_key: str | None = None):
    try:
        conn = get_next_move_connection()
    except NextMoveDatabaseUnavailable as exc:
        raise error(503, str(exc), "NEXT_MOVE_DATABASE_UNAVAILABLE") from exc
    try:
        version = get_dataset_version(conn, next_move_db_path())
        return cached_resolve_problems(conn, dataset_version=version, database_path=str(next_move_db_path()), opening_key=opening_key)
    finally:
        conn.close()


def select_next_problem(problems: list[dict], *, policy: str, latest: dict,
                        exclude_problem_key: str | None = None,
                        rng: random.Random | random.SystemRandom = random.SystemRandom()):
    """Select from resolved (therefore distinct) problems; injectable RNG keeps tests deterministic."""
    candidates = [p for p in problems if p["problem_key"] != exclude_problem_key]
    if policy == "unattempted":
        candidates = [p for p in candidates if p["problem_key"] not in latest]
    return rng.choice(candidates) if candidates else None


@router.get("/problems/next")
def next_problem(policy: Literal["random", "unattempted"], opening_key: str | None = None,
                 exclude_problem_key: str | None = None):
    problems = _current_problems(opening_key)
    if exclude_problem_key and not exclude_problem_key.startswith("v1:"):
        logger.warning("Ignoring malformed exclude_problem_key: %s", exclude_problem_key)
        exclude_problem_key = None
    latest: dict = {}
    if policy == "unattempted":
        history = get_connection()
        try:
            latest = latest_next_move_results(history, [p["problem_key"] for p in problems])
        finally:
            history.close()
    selected = select_next_problem(problems, policy=policy, latest=latest,
                                   exclude_problem_key=exclude_problem_key)
    if selected is None:
        from fastapi import Response
        return Response(status_code=204)
    return serialize_problem(selected)


@router.get("/progress")
def progress():
    problems = _current_problems()
    history = get_connection()
    try:
        latest = latest_next_move_results(history, [p["problem_key"] for p in problems])
    finally:
        history.close()
    openings: dict[str, dict] = {}
    for problem in problems:
        item = openings.setdefault(problem["opening_key"], {"opening_key": problem["opening_key"],
            "opening_name": problem["opening_name"], "total": 0, "answered": 0,
            "verdict_counts": {v: 0 for v in ("top", "strong", "listed", "unlisted")}})
        item["total"] += 1
        result = latest.get(problem["problem_key"])
        if result:
            item["answered"] += 1
            item["verdict_counts"][result["verdict"]] += 1
    for item in openings.values():
        item["top_rate"] = item["verdict_counts"]["top"] / item["answered"] if item["answered"] else 0
    return {"openings": sorted(openings.values(), key=lambda x: x["opening_key"])}


@router.get("/status")
def status(opening_key: str):
    problems = _current_problems(opening_key)
    history = get_connection()
    try:
        latest = latest_next_move_results(history, [p["problem_key"] for p in problems])
    finally:
        history.close()
    return {"opening_key": opening_key, "items": [{"problem_key": p["problem_key"],
        "verdict": latest[p["problem_key"]]["verdict"] if p["problem_key"] in latest else None,
        "result_id": latest[p["problem_key"]]["id"] if p["problem_key"] in latest else None} for p in problems]}
