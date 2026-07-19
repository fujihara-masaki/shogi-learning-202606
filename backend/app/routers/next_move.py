"""Transactional recording of next-move answers."""
from __future__ import annotations

import sqlite3
from typing import Literal

import shogi
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_connection
from ..next_move_database import NextMoveDatabaseUnavailable, get_next_move_connection
from ..next_move_identity import (PROBLEM_DEFINITION_VERSION, candidate_definition_fingerprint,
    normalize_candidates, normalize_sfen, problem_key, stable_source_key)

router = APIRouter(prefix="/api/next-move", tags=["next-move"])


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
          SELECT ls.*, bs.name source_name, bs.version source_version, bs.source_url
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
               row.get("extraction_run_key") or "unknown", ""))
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
