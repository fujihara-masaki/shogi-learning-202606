"""タイムアタック API。"""
from fastapi import APIRouter

from ..database import get_connection
from ..schemas import TimeAttackResult, TimeAttackResultCreate

router = APIRouter(prefix="/api/time-attack", tags=["time-attack"])


def row_to_result(row) -> TimeAttackResult:
    return TimeAttackResult(
        id=row["id"],
        mode=row["mode"],
        mate_length=row["mate_length"],
        total_questions=row["total_questions"],
        correct_count=row["correct_count"],
        mistake_count=row["mistake_count"],
        elapsed_ms=row["elapsed_ms"],
        played_at=row["played_at"],
    )


@router.post("/result", response_model=TimeAttackResult, status_code=201)
def save_result(body: TimeAttackResultCreate):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO time_attack_results
              (mode, mate_length, total_questions, correct_count, mistake_count, elapsed_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                body.mode,
                body.mate_length,
                body.total_questions,
                body.correct_count,
                body.mistake_count,
                body.elapsed_ms,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM time_attack_results WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return row_to_result(row)
    finally:
        conn.close()


@router.get("/results", response_model=list[TimeAttackResult])
def list_results(mate_length: int | None = None, limit: int = 50):
    conn = get_connection()
    try:
        sql = "SELECT * FROM time_attack_results"
        params: list = []
        if mate_length is not None:
            sql += " WHERE mate_length = ?"
            params.append(mate_length)
        sql += " ORDER BY played_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [row_to_result(r) for r in rows]
    finally:
        conn.close()
