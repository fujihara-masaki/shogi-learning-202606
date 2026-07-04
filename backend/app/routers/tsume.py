"""詰め将棋問題 API。"""
import json
import sqlite3

from fastapi import APIRouter, HTTPException

from ..database import get_connection
from ..schemas import (
    FavoriteUpdate,
    ProblemResult,
    ProblemResultCreate,
    ProblemStats,
    TsumeProblem,
    TsumeTagSummary,
    TsumeProblemCreate,
    TsumeProblemUpdate,
    ValidationResponse,
)
from ..shogi_utils import validate_problem

router = APIRouter(prefix="/api/tsume-problems", tags=["tsume"])

STATS_SQL = """
SELECT
  SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
  SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
  MAX(answered_at) AS last_answered_at,
  CAST(AVG(elapsed_ms) AS INTEGER) AS avg_elapsed_ms
FROM problem_results WHERE problem_id = ?
"""


def row_to_problem(conn: sqlite3.Connection, row: sqlite3.Row) -> TsumeProblem:
    s = conn.execute(STATS_SQL, (row["id"],)).fetchone()
    stats = ProblemStats(
        correct_count=s["correct_count"] or 0,
        wrong_count=s["wrong_count"] or 0,
        last_answered_at=s["last_answered_at"],
        avg_elapsed_ms=s["avg_elapsed_ms"],
    )
    return TsumeProblem(
        id=row["id"],
        title=row["title"],
        initial_sfen=row["initial_sfen"],
        mate_length=row["mate_length"],
        solution_moves=json.loads(row["solution_moves"]),
        opponent_moves=json.loads(row["opponent_moves"]),
        difficulty=row["difficulty"],
        tags=json.loads(row["tags"]),
        explanation=row["explanation"],
        is_favorite=bool(row["is_favorite"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        source_license=row["source_license"],
        source_copyright=row["source_copyright"],
        external_id=row["external_id"],
        source_hash=row["source_hash"],
        source_metadata=json.loads(row["source_metadata"] or "{}"),
        stats=stats,
    )


def fetch_problem(conn: sqlite3.Connection, problem_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM tsume_problems WHERE id = ?", (problem_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="問題が見つかりません")
    return row


@router.post("/validate", response_model=ValidationResponse)
def validate_problem_body(body: TsumeProblemCreate):
    errors = validate_problem(
        body.initial_sfen, body.solution_moves, body.opponent_moves, body.mate_length
    )
    return ValidationResponse(valid=not errors, errors=errors)


def validate_or_400(body: TsumeProblemCreate | TsumeProblemUpdate) -> None:
    errors = validate_problem(
        body.initial_sfen, body.solution_moves, body.opponent_moves, body.mate_length
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})


@router.get("/tags", response_model=list[TsumeTagSummary])
def list_tags(mate_length: int | None = None):
    conn = get_connection()
    try:
        sql = """
            SELECT json_each.value AS tag, COUNT(DISTINCT tsume_problems.id) AS count
            FROM tsume_problems, json_each(tsume_problems.tags)
            WHERE json_each.value != ''
        """
        params: list = []
        if mate_length is not None:
            sql += " AND tsume_problems.mate_length = ?"
            params.append(mate_length)
        sql += " GROUP BY json_each.value ORDER BY json_each.value"
        rows = conn.execute(sql, params).fetchall()
        return [TsumeTagSummary(tag=row["tag"], count=row["count"]) for row in rows]
    finally:
        conn.close()


@router.get("", response_model=list[TsumeProblem])
def list_problems(
    mate_length: int | None = None,
    tag: str | None = None,
    favorite: bool | None = None,
    random_order: bool = False,
    limit: int | None = None,
    offset: int = 0,
):
    conn = get_connection()
    try:
        sql = "SELECT * FROM tsume_problems WHERE 1=1"
        params: list = []
        if mate_length is not None:
            sql += " AND mate_length = ?"
            params.append(mate_length)
        if tag:
            # tags は JSON 配列文字列。完全一致の要素を含むものを抽出する。
            sql += " AND EXISTS (SELECT 1 FROM json_each(tsume_problems.tags) WHERE json_each.value = ?)"
            params.append(tag)
        if favorite is not None:
            sql += " AND is_favorite = ?"
            params.append(1 if favorite else 0)
        sql += " ORDER BY RANDOM()" if random_order else " ORDER BY mate_length, id"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [row_to_problem(conn, r) for r in rows]
    finally:
        conn.close()


@router.get("/{problem_id}", response_model=TsumeProblem)
def get_problem(problem_id: int):
    conn = get_connection()
    try:
        return row_to_problem(conn, fetch_problem(conn, problem_id))
    finally:
        conn.close()


@router.post("", response_model=TsumeProblem, status_code=201)
def create_problem(body: TsumeProblemCreate):
    validate_or_400(body)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO tsume_problems
              (title, initial_sfen, mate_length, solution_moves, opponent_moves,
               difficulty, tags, explanation, is_favorite, source_name, source_url,
               source_license, source_copyright, external_id, source_hash, source_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.title,
                body.initial_sfen,
                body.mate_length,
                json.dumps(body.solution_moves),
                json.dumps(body.opponent_moves),
                body.difficulty,
                json.dumps(body.tags, ensure_ascii=False),
                body.explanation,
                1 if body.is_favorite else 0,
                body.source_name, body.source_url, body.source_license, body.source_copyright,
                body.external_id, body.source_hash, json.dumps(body.source_metadata, ensure_ascii=False),
            ),
        )
        conn.commit()
        return row_to_problem(conn, fetch_problem(conn, cur.lastrowid))
    finally:
        conn.close()


@router.put("/{problem_id}", response_model=TsumeProblem)
def update_problem(problem_id: int, body: TsumeProblemUpdate):
    validate_or_400(body)
    conn = get_connection()
    try:
        fetch_problem(conn, problem_id)
        conn.execute(
            """
            UPDATE tsume_problems SET
              title = ?, initial_sfen = ?, mate_length = ?, solution_moves = ?,
              opponent_moves = ?, difficulty = ?, tags = ?, explanation = ?,
              is_favorite = ?, source_name = ?, source_url = ?, source_license = ?,
              source_copyright = ?, external_id = ?, source_hash = ?, source_metadata = ?,
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                body.title,
                body.initial_sfen,
                body.mate_length,
                json.dumps(body.solution_moves),
                json.dumps(body.opponent_moves),
                body.difficulty,
                json.dumps(body.tags, ensure_ascii=False),
                body.explanation,
                1 if body.is_favorite else 0,
                body.source_name, body.source_url, body.source_license, body.source_copyright,
                body.external_id, body.source_hash, json.dumps(body.source_metadata, ensure_ascii=False),
                problem_id,
            ),
        )
        conn.commit()
        return row_to_problem(conn, fetch_problem(conn, problem_id))
    finally:
        conn.close()


@router.delete("/{problem_id}", status_code=204)
def delete_problem(problem_id: int):
    conn = get_connection()
    try:
        fetch_problem(conn, problem_id)
        conn.execute("DELETE FROM tsume_problems WHERE id = ?", (problem_id,))
        conn.commit()
    finally:
        conn.close()


@router.post("/{problem_id}/result", response_model=ProblemResult, status_code=201)
def add_result(problem_id: int, body: ProblemResultCreate):
    conn = get_connection()
    try:
        fetch_problem(conn, problem_id)
        cur = conn.execute(
            """
            INSERT INTO problem_results (problem_id, is_correct, elapsed_ms, mistake_count)
            VALUES (?, ?, ?, ?)
            """,
            (problem_id, 1 if body.is_correct else 0, body.elapsed_ms, body.mistake_count),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM problem_results WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return ProblemResult(
            id=row["id"],
            problem_id=row["problem_id"],
            is_correct=bool(row["is_correct"]),
            elapsed_ms=row["elapsed_ms"],
            mistake_count=row["mistake_count"],
            answered_at=row["answered_at"],
        )
    finally:
        conn.close()


@router.post("/{problem_id}/favorite", response_model=TsumeProblem)
def set_favorite(problem_id: int, body: FavoriteUpdate):
    conn = get_connection()
    try:
        fetch_problem(conn, problem_id)
        conn.execute(
            "UPDATE tsume_problems SET is_favorite = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if body.is_favorite else 0, problem_id),
        )
        conn.commit()
        return row_to_problem(conn, fetch_problem(conn, problem_id))
    finally:
        conn.close()
