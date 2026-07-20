"""Transactional recording of next-move answers."""
from __future__ import annotations

import sqlite3
import logging
import random
from typing import Literal, Callable

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


def choose_opening(problems: list[dict], rng: Callable | random.Random | random.SystemRandom):
    """Choose an opening with equal weight, irrespective of its problem count."""
    keys = sorted({problem.get("opening_key", "") for problem in problems})
    return rng.choice(keys) if keys else None


def choose_problem(problems: list[dict], rng: Callable | random.Random | random.SystemRandom):
    """Choose one distinct resolved problem from an already filtered opening."""
    return rng.choice(problems) if problems else None


def select_next_problem(problems: list[dict], *, policy: str, latest: dict,
                        exclude_problem_key: str | None = None,
                        opening_key: str | None = None,
                        rng: random.Random | random.SystemRandom = random.SystemRandom()):
    """Select from resolved (therefore distinct) problems; injectable RNG keeps tests deterministic."""
    candidates = [p for p in problems if p["problem_key"] != exclude_problem_key]
    if policy == "unattempted":
        candidates = [p for p in candidates if p["problem_key"] not in latest]
    elif policy == "weak":
        candidates = [p for p in candidates if latest.get(p["problem_key"], {}).get("verdict") in ("listed", "unlisted")]
    if not candidates:
        return None
    selected_opening = opening_key or choose_opening(candidates, rng)
    return choose_problem([p for p in candidates if p.get("opening_key", "") == selected_opening], rng)


@router.get("/problems/next")
def next_problem(policy: Literal["random", "unattempted", "weak"], opening_key: str | None = None,
                 exclude_problem_key: str | None = None):
    problems = _current_problems(opening_key)
    if exclude_problem_key and not exclude_problem_key.startswith("v1:"):
        logger.warning("Ignoring malformed exclude_problem_key: %s", exclude_problem_key)
        exclude_problem_key = None
    latest: dict = {}
    if policy in ("unattempted", "weak"):
        history = get_connection()
        try:
            latest = latest_next_move_results(history, [p["problem_key"] for p in problems])
        finally:
            history.close()
    selected = select_next_problem(problems, policy=policy, latest=latest,
                                   exclude_problem_key=exclude_problem_key, opening_key=opening_key)
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


def _current_problem_map() -> dict[str, dict]:
    """Best-effort current metadata; history must survive a missing distribution DB."""
    try:
        return {problem["problem_key"]: problem for problem in _current_problems()}
    except HTTPException as exc:
        if exc.status_code == 503:
            return {}
        raise


@router.get("/history")
def history(limit: int = 20):
    limit = max(1, min(limit, 100))
    current = _current_problem_map()
    conn = get_connection()
    try:
        counts = {name: 0 for name in ("top", "strong", "listed", "unlisted")}
        for row in conn.execute("SELECT verdict, COUNT(*) count FROM next_move_results GROUP BY verdict"):
            if row["verdict"] in counts:
                counts[row["verdict"]] = row["count"]
        total = sum(counts.values())
        rows = conn.execute(
            "SELECT * FROM next_move_results ORDER BY answered_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    recent = []
    for row in rows:
        item = dict(row)
        problem = current.get(row["problem_key"])
        item.update(
            opening_key=problem["opening_key"] if problem else row["opening_key_at_answer"],
            opening_name=problem["opening_name"] if problem else row["opening_name_at_answer"],
            sample_id=problem["id"] if problem else None,
            available=problem is not None,
            unavailable_reason=None if problem else "現在の問題データには存在しません",
        )
        recent.append(item)
    return {"total_answers": total, "verdict_counts": counts,
            "top_rate": counts["top"] / total if total else 0, "recent_results": recent}


@router.get("/review")
def review():
    current = _current_problem_map()
    conn = get_connection()
    try:
        keys = [row["problem_key"] for row in conn.execute("SELECT DISTINCT problem_key FROM next_move_results")]
        latest = latest_next_move_results(conn, keys)
    finally:
        conn.close()
    items = []
    for key, row in latest.items():
        if row["verdict"] not in ("listed", "unlisted"):
            continue
        problem = current.get(key)
        items.append({"problem_key": key, "sample_id": problem["id"] if problem else None,
            "opening_key": problem["opening_key"] if problem else row["opening_key_at_answer"],
            "opening_name": problem["opening_name"] if problem else row["opening_name_at_answer"],
            "verdict": row["verdict"], "move_usi": row["move_usi"],
            "answered_at": row["answered_at"], "result_id": row["id"],
            "available": problem is not None,
            "unavailable_reason": None if problem else "現在の問題データには存在しません"})
    items.sort(key=lambda item: (item["answered_at"], item["result_id"]), reverse=True)
    return {"items": items}
