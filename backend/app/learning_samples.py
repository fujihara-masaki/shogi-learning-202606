"""Learning sample extraction from imported book positions."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from .next_move_database import get_next_move_write_connection, init_next_move_db
from .next_move_identity import canonical_hash, extraction_run_key

EXTRACTOR_VERSION = "1"

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


RANKS = "abcdefghi"


def _parse_sfen_board(sfen: str) -> tuple[dict[tuple[int, str], str], str, str]:
    parts = sfen.split()
    placement = parts[0] if parts else ""
    side = parts[1] if len(parts) > 1 else "b"
    hand = parts[2] if len(parts) > 2 else "-"
    board: dict[tuple[int, str], str] = {}
    for rank_index, row in enumerate(placement.split("/")):
        if rank_index >= len(RANKS):
            break
        rank = RANKS[rank_index]
        file_no = 9
        i = 0
        while i < len(row) and file_no >= 1:
            ch = row[i]
            if ch.isdigit():
                file_no -= int(ch)
            elif ch == "+" and i + 1 < len(row):
                board[(file_no, rank)] = row[i : i + 2]
                file_no -= 1
                i += 1
            else:
                board[(file_no, rank)] = ch
                file_no -= 1
            i += 1
    return board, side, hand


def _piece_at(board: dict[tuple[int, str], str], square: str) -> str | None:
    if len(square) != 2 or not square[0].isdigit():
        return None
    return board.get((int(square[0]), square[1]))


def _has_piece(board: dict[tuple[int, str], str], piece: str, squares: set[str]) -> bool:
    return any(_piece_at(board, sq) == piece for sq in squares)


def _hand_contains(hand: str, piece: str) -> bool:
    return hand != "-" and piece in hand


def classify_book_position(sfen: str, moves: list[str]) -> tuple[str, str]:
    """Classify a book position using SFEN piece placement and candidate moves.

    YaneuraOu book rows do not include move history, so the classifier combines
    stable board-shape clues (piece locations, hands, advanced pawns) with the
    current candidate moves.  Rules are ordered from most distinctive to more
    generic so common candidate moves do not over-classify early positions.
    """
    board, _side, hand = _parse_sfen_board(sfen)
    move_set = set(moves)
    black_bishop_on_board = any(piece == "B" for piece in board.values())
    white_bishop_on_board = any(piece == "b" for piece in board.values())
    bishop_in_hand = _hand_contains(hand, "B") or _hand_contains(hand, "b")
    black_rook = next((sq for sq, piece in board.items() if piece == "R"), None)
    white_rook = next((sq for sq, piece in board.items() if piece == "r"), None)

    # Ranging-rook families: use rook placement before static-rook pawn-shape rules.
    if (black_rook and black_rook[0] == 5) or (white_rook and white_rook[0] == 5):
        return "nakabisha", "rook is placed on the central file"
    if (black_rook and black_rook[0] == 6) or (white_rook and white_rook[0] == 4):
        return "shikenbisha", "rook is placed on the fourth-file ranging-rook file"
    if (black_rook and black_rook[0] == 8) or (white_rook and white_rook[0] == 2):
        return "mukaibisha", "rook is placed on the opposing-rook file"
    if {"2h5h", "8b5b", "5g5f", "5c5d"} & move_set:
        return "nakabisha", "central-file rook/pawn candidate suggests Nakabisha"
    if {"2h6h", "8b4b", "6g6f", "4c4d"} & move_set:
        return "shikenbisha", "fourth-file rook/pawn candidate suggests Shikenbisha"
    if {"2h8h", "8b2b", "8g8f", "2c2d"} & move_set:
        return "mukaibisha", "opposing-rook candidate suggests Mukaibisha"

    promoted_bishop_on_board = any(piece in {"+B", "+b"} for piece in board.values())
    bishop_drop_candidate = any(m.startswith(("B*", "b*")) for m in move_set)

    # Bishop-exchange: require an actual bishop in hand / missing bishop, not merely a capture candidate.
    has_missing_bishop = not (black_bishop_on_board and white_bishop_on_board)
    if bishop_in_hand or promoted_bishop_on_board or has_missing_bishop:
        if (
            {"8h2b", "2b8h"} & move_set
            or bishop_drop_candidate
            or bishop_in_hand
            or promoted_bishop_on_board
        ):
            return "kakugawari", "bishop in hand or absent from board suggests bishop exchange"

    black_2_pawn = _has_piece(board, "P", {"2f", "2e", "2d"})
    white_8_pawn = _has_piece(board, "p", {"8d", "8e", "8f"})
    black_7_pawn = _has_piece(board, "P", {"7f", "7e"})
    white_3_pawn = _has_piece(board, "p", {"3d", "3e"})
    bishops_home_or_open = black_bishop_on_board and white_bishop_on_board

    if black_2_pawn and white_8_pawn and bishops_home_or_open:
        return "aigakari", "both rook pawns are advanced while bishops remain on board"
    if {"2e2d", "8e8f", "2f2e", "8d8e"} & move_set and black_2_pawn and white_8_pawn:
        return "aigakari", "mutual rook-pawn candidate/shape suggests Aigakari"
    if {"2e2d", "8e8f", "3d3c"} & move_set and has_missing_bishop:
        return "yokofudori", "rook-pawn capture after bishop opening suggests Yokofudori"

    has_yagura_shape = (
        _has_piece(board, "S", {"7g", "6g", "7h"})
        and _has_piece(board, "s", {"3c", "4c", "3b"})
        and black_7_pawn
        and white_3_pawn
    )
    if has_yagura_shape or {"7i6h", "3a4b", "6h7g", "4b3c"} & move_set:
        return "yagura", "Yagura silver-and-pawn structure detected"
    has_bogin_shape = _has_piece(board, "S", {"2g", "3f", "2f"}) and black_2_pawn
    if has_bogin_shape or {"3i3h", "3h2g", "2g3f", "7a7b", "7b8c", "8c7d"} & move_set:
        return "bogin", "silver advance near rook pawn suggests Bogin"

    return UNKNOWN_OPENING, "no board-shape or candidate-move rule matched"


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
    init_next_move_db()
    rng = random.Random(seed)
    conn = get_next_move_write_connection()
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
            items.sort(
                key=lambda x: (
                    -int(x["move_count"] or 0),
                    -int(x["max_depth"] or 0),
                    int(x["max_abs_score"] or 0),
                    x["tie_breaker"],
                    x["book_position_id"],
                )
            )
            picks = items[:per_opening_limit]
            reason_counts: dict[str, int] = {}
            for item in items:
                reason = str(item["sample_reason"])
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            by_opening[key] = {
                "opening_name": OPENING_LABELS.get(key, key),
                "candidate_count": len(items),
                "selected_count": len(picks),
                "reason_counts": dict(
                    sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))[:5]
                ),
                "example_position_ids": [item["book_position_id"] for item in items[:3]],
            }
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
            source = conn.execute("SELECT file_sha256 FROM book_sources WHERE id=?", (source_id,)).fetchone()
            extracted_at = datetime.now(timezone.utc).isoformat()
            run_metadata = {"extractor_version": EXTRACTOR_VERSION, "limit": limit,
                "per_opening_limit": per_opening_limit, "seed": seed,
                "source_file_sha256": source["file_sha256"], "extracted_at": extracted_at}
            run_key = extraction_run_key(run_metadata)
            conn.execute("""INSERT INTO extraction_runs
                (extraction_run_key,extractor_version,"limit",per_opening_limit,seed,source_file_sha256,extracted_at)
                VALUES(?,?,?,?,?,?,?)""", (run_key, EXTRACTOR_VERSION, limit, per_opening_limit, seed,
                source["file_sha256"], extracted_at))
            conn.execute("DELETE FROM learning_samples WHERE book_source_id = ?", (source_id,))
            conn.executemany(
                """
                INSERT INTO learning_samples(book_source_id, book_position_id, opening_key, opening_name, sfen, sample_rank, sample_reason, extraction_run_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        x["book_source_id"],
                        x["book_position_id"],
                        x["opening_key"],
                        x["opening_name"],
                        x["sfen"],
                        x["sample_rank"],
                        x["sample_reason"],
                        run_key,
                    )
                    for x in selected
                ],
            )
            counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("book_sources", "book_positions", "book_moves", "learning_samples")}
            runs = [r[0] for r in conn.execute("SELECT extraction_run_key FROM extraction_runs ORDER BY extraction_run_key")]
            hashes = [r[0] for r in conn.execute("SELECT DISTINCT file_sha256 FROM book_sources ORDER BY file_sha256")]
            dataset_version = canonical_hash({"schema_version": 1, "generated_at": extracted_at,
                "extractor_version": EXTRACTOR_VERSION, "extraction_run_keys": runs,
                "source_file_sha256_values": hashes, "row_counts": counts})
            conn.execute("INSERT OR REPLACE INTO database_metadata(key,value) VALUES('dataset_version',?)", (dataset_version,))
            conn.commit()
        return LearningSamplePlan(
            source_id,
            sum(len(v) for v in grouped.values()),
            len(selected),
            len(grouped.get(UNKNOWN_OPENING, [])),
            by_opening,
            selected,
            dry_run,
        )
    finally:
        conn.close()
