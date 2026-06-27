"""Learning sample extraction from imported book positions."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .database import get_connection, init_db

UNKNOWN_OPENING = "unclassified"

OPENING_LABELS = {
    "bogin": "棒銀",
    "nakabisha": "中飛車",
    "shikenbisha": "四間飛車",
    "mukaibisha": "向かい飛車",
    "yagura": "矢倉",
    "kakugawari": "角換わり",
    "aigakari": "相掛かり",
    "yokofudori": "横歩取り",
    UNKNOWN_OPENING: "未分類",
}


def classify_book_position(sfen: str, moves: list[str]) -> tuple[str, str]:
    """Classify a book position using lightweight SFEN/candidate-move rules.

    Imported YaneuraOu positions do not keep the move history, so these rules are
    intentionally conservative and return ``unclassified`` when no representative
    clue is present.
    """
    s = sfen.split()[0]
    move_set = set(moves)
    if "8h2b" in move_set or "2b8h" in move_set or "+B" in s or "+b" in s:
        return "kakugawari", "candidate move/piece placement suggests bishop exchange"
    if {"2g2f", "2f2e"} & move_set and {"8c8d", "8d8e"} & move_set:
        return "aigakari", "both rook pawns are candidate plans"
    if "3d3c" in move_set or "3c3d" in move_set:
        return "yagura", "silver development around 3c/3d suggests Yagura"
    if "2e2d" in move_set or "8e8f" in move_set:
        return "yokofudori", "rook-pawn capture candidate suggests Yokofudori"
    if "5g5f" in move_set or "5c5d" in move_set or "/4R4/" in s or "/4r4/" in s:
        return "nakabisha", "central-file pawn/rook clue suggests Nakabisha"
    if "6h7h" in move_set or "3b4b" in move_set or "/5R3/" in s or "/5r3/" in s:
        return "shikenbisha", "fourth-file rook/silver clue suggests Shikenbisha"
    if "2h8h" in move_set or "8b2b" in move_set or "/1R7/" in s or "/1r7/" in s:
        return "mukaibisha", "opposing-rook clue suggests Mukaibisha"
    if "2g2f" in move_set and ("3i3h" in move_set or "3h2g" in move_set):
        return "bogin", "rook-pawn and silver advance candidates suggest Bogin"
    return UNKNOWN_OPENING, "no simple opening rule matched"


@dataclass(frozen=True)
class LearningSamplePlan:
    source_id: int
    total_candidates: int
    selected_count: int
    unclassified_count: int
    by_opening: dict[str, dict[str, Any]]
    selected: list[dict[str, Any]]
    dry_run: bool


def _candidate_rows(conn, source_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            bp.id AS book_position_id,
            bp.sfen,
            GROUP_CONCAT(bm.usi, ' ') AS move_usis,
            COUNT(bm.id) AS move_count,
            MAX(COALESCE(bm.depth, 0)) AS max_depth,
            MAX(ABS(COALESCE(bm.score, 0))) AS max_abs_score
        FROM book_positions bp
        LEFT JOIN book_moves bm ON bm.position_id = bp.id
        WHERE bp.source_id = ?
        GROUP BY bp.id, bp.sfen
        ORDER BY bp.id
        """,
        (source_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def validate_sample_limits(*, limit: int, per_opening_limit: int) -> None:
    if limit < 1:
        raise ValueError("limit must be 1 or greater")
    if per_opening_limit < 1:
        raise ValueError("per_opening_limit must be 1 or greater")


def build_learning_sample_plan(source_id: int, *, limit: int, per_opening_limit: int, seed: int, dry_run: bool) -> LearningSamplePlan:
    validate_sample_limits(limit=limit, per_opening_limit=per_opening_limit)
    init_db()
    rng = random.Random(seed)
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM book_sources WHERE id = ?", (source_id,)).fetchone():
            raise ValueError(f"book source not found: {source_id}")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in _candidate_rows(conn, source_id):
            moves = str(row.get("move_usis") or "").split()
            opening_key, reason = classify_book_position(row["sfen"], moves)
            item = {
                "book_source_id": source_id,
                "book_position_id": row["book_position_id"],
                "opening_key": opening_key,
                "opening_name": OPENING_LABELS.get(opening_key, opening_key),
                "sfen": row["sfen"],
                "sample_reason": reason,
                "move_count": row["move_count"],
                "max_depth": row["max_depth"],
                "max_abs_score": row["max_abs_score"],
                "tie_breaker": rng.random(),
            }
            grouped.setdefault(opening_key, []).append(item)
        selected: list[dict[str, Any]] = []
        by_opening: dict[str, dict[str, Any]] = {}
        for key in sorted(grouped):
            items = grouped[key]
            items.sort(key=lambda x: (-int(x["move_count"] or 0), -int(x["max_depth"] or 0), int(x["max_abs_score"] or 0), x["tie_breaker"], x["book_position_id"]))
            picks = items[:per_opening_limit]
            by_opening[key] = {"opening_name": OPENING_LABELS.get(key, key), "candidate_count": len(items), "selected_count": len(picks)}
            selected.extend(picks)
        selected.sort(key=lambda x: (x["tie_breaker"], x["opening_key"], x["book_position_id"]))
        selected = selected[:limit]
        for i, item in enumerate(selected, start=1):
            item["sample_rank"] = i
            item.pop("tie_breaker", None)
        selected_by_key: dict[str, int] = {}
        for item in selected:
            selected_by_key[item["opening_key"]] = selected_by_key.get(item["opening_key"], 0) + 1
        for key, summary in by_opening.items():
            summary["selected_count"] = selected_by_key.get(key, 0)
        if not dry_run:
            conn.execute("DELETE FROM learning_samples WHERE book_source_id = ?", (source_id,))
            conn.executemany(
                """
                INSERT INTO learning_samples(book_source_id, book_position_id, opening_key, opening_name, sfen, sample_rank, sample_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(x["book_source_id"], x["book_position_id"], x["opening_key"], x["opening_name"], x["sfen"], x["sample_rank"], x["sample_reason"]) for x in selected],
            )
            conn.commit()
        return LearningSamplePlan(source_id, sum(len(v) for v in grouped.values()), len(selected), len(grouped.get(UNKNOWN_OPENING, [])), by_opening, selected, dry_run)
    finally:
        conn.close()
