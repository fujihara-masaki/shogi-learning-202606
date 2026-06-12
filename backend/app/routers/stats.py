"""学習履歴・統計 API。"""
from fastapi import APIRouter

from ..database import get_connection
from ..schemas import OverallStats, StatsResponse, TsumeProblem
from .tsume import row_to_problem

router = APIRouter(prefix="/api", tags=["stats"])


def aggregate(rows) -> OverallStats:
    total = len(rows)
    correct = sum(1 for r in rows if r["is_correct"])
    wrong = total - correct
    elapsed = [r["elapsed_ms"] for r in rows if r["elapsed_ms"] > 0]
    return OverallStats(
        total_answers=total,
        total_correct=correct,
        total_wrong=wrong,
        accuracy=round(correct / total, 4) if total else 0.0,
        avg_elapsed_ms=int(sum(elapsed) / len(elapsed)) if elapsed else None,
    )


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT pr.*, tp.mate_length, tp.title
            FROM problem_results pr
            JOIN tsume_problems tp ON tp.id = pr.problem_id
            ORDER BY pr.answered_at DESC, pr.id DESC
            """
        ).fetchall()
        by_len: dict[str, list] = {}
        for r in rows:
            by_len.setdefault(str(r["mate_length"]), []).append(r)
        recent = [
            {
                "id": r["id"],
                "problem_id": r["problem_id"],
                "title": r["title"],
                "mate_length": r["mate_length"],
                "is_correct": bool(r["is_correct"]),
                "elapsed_ms": r["elapsed_ms"],
                "mistake_count": r["mistake_count"],
                "answered_at": r["answered_at"],
            }
            for r in rows[:50]
        ]
        return StatsResponse(
            overall=aggregate(rows),
            by_mate_length={k: aggregate(v) for k, v in by_len.items()},
            recent_results=recent,
        )
    finally:
        conn.close()


@router.get("/review-problems", response_model=list[TsumeProblem])
def review_problems():
    """一度でも間違えたことのある問題(復習モード用)。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT tp.*
            FROM tsume_problems tp
            JOIN problem_results pr ON pr.problem_id = tp.id AND pr.is_correct = 0
            ORDER BY tp.mate_length, tp.id
            """
        ).fetchall()
        return [row_to_problem(conn, r) for r in rows]
    finally:
        conn.close()
