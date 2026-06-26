"""Imported opening line APIs."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..database import get_connection

router = APIRouter(tags=["openings"])

TAG_LABELS = {
    "nakabisha": "中飛車",
    "bougin": "棒銀",
    "mukaibisha": "向かい飛車",
    "other": "その他",
}


def _json_list(value: str) -> list[str]:
    data = json.loads(value or "[]")
    return data if isinstance(data, list) else []


def _line_row_to_summary(row: Any) -> dict[str, Any]:
    tags = _json_list(row["tags"])
    return {
        "id": row["id"],
        "name": row["name"],
        "opening_type": row["opening_type"],
        "initial_sfen": row["initial_sfen"],
        "move_count": row["move_count"],
        "tags": tags,
        "source": {
            "id": row["source_id"],
            "name": row["source_name"] or "",
            "license_name": row["license_name"] or "",
            "license_url": row["license_url"] or "",
        },
    }


@router.get("/api/openings/tags")
def list_opening_tags() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT tag, COUNT(*) AS count, MAX(score) AS max_score
            FROM opening_tags
            GROUP BY tag
            ORDER BY count DESC, tag ASC
            """
        ).fetchall()
        return [
            {
                "tag": row["tag"],
                "label": TAG_LABELS.get(row["tag"], row["tag"]),
                "count": row["count"],
                "max_score": row["max_score"],
            }
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/api/openings")
@router.get("/openings")
def list_openings(tag: str | None = Query(default=None)) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        params: list[Any] = []
        where = ""
        if tag:
            where = "WHERE EXISTS (SELECT 1 FROM opening_tags ot WHERE ot.line_id = ol.id AND ot.tag = ?)"
            params.append(tag)
        rows = conn.execute(
            f"""
            SELECT
                ol.id,
                ol.source_id,
                ol.name,
                ol.opening_type,
                ol.initial_sfen,
                ol.tags,
                (SELECT COUNT(*) FROM opening_line_moves om WHERE om.line_id = ol.id) AS move_count,
                os.name AS source_name,
                os.license_name,
                os.license_url
            FROM opening_lines ol
            LEFT JOIN opening_sources os ON os.id = ol.source_id
            {where}
            ORDER BY ol.id DESC
            """,
            params,
        ).fetchall()
        return [_line_row_to_summary(row) for row in rows]
    finally:
        conn.close()


@router.get("/api/openings/{line_id}")
@router.get("/api/opening-lines/{line_id}")
@router.get("/opening-lines/{line_id}")
def get_opening(line_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                ol.id,
                ol.source_id,
                ol.name,
                ol.opening_type,
                ol.initial_sfen,
                ol.moves,
                ol.comments,
                ol.tags,
                os.name AS source_name,
                os.license_name,
                os.license_url
            FROM opening_lines ol
            LEFT JOIN opening_sources os ON os.id = ol.source_id
            WHERE ol.id = ?
            """,
            (line_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="opening not found")
        positions = conn.execute(
            "SELECT ply, sfen FROM opening_positions WHERE line_id = ? ORDER BY ply",
            (line_id,),
        ).fetchall()
        moves = conn.execute(
            "SELECT ply, usi, from_sfen, to_sfen, comment, variation_group, parent_move_id, sort_order FROM opening_line_moves WHERE line_id = ? ORDER BY variation_group, ply, sort_order",
            (line_id,),
        ).fetchall()
        tags = conn.execute(
            "SELECT tag, score, reason FROM opening_tags WHERE line_id = ? ORDER BY score DESC, tag",
            (line_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "name": row["name"],
            "opening_type": row["opening_type"],
            "initial_sfen": row["initial_sfen"],
            "moves": [
                {
                    "ply": move["ply"],
                    "usi": move["usi"],
                    "from_sfen": move["from_sfen"],
                    "to_sfen": move["to_sfen"],
                    "comment": move["comment"],
                    "variation_group": move["variation_group"],
                    "parent_move_id": move["parent_move_id"],
                    "sort_order": move["sort_order"],
                }
                for move in moves
            ],
            "positions": [{"ply": pos["ply"], "sfen": pos["sfen"]} for pos in positions],
            "tags": [
                {"tag": tag["tag"], "label": TAG_LABELS.get(tag["tag"], tag["tag"]), "score": tag["score"], "reason": tag["reason"]}
                for tag in tags
            ],
            "source": {
                "id": row["source_id"],
                "name": row["source_name"] or "",
                "license_name": row["license_name"] or "",
                "license_url": row["license_url"] or "",
            },
        }
    finally:
        conn.close()


@router.get("/api/opening-lines/{line_id}/moves")
@router.get("/opening-lines/{line_id}/moves")
def get_opening_moves(line_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM opening_lines WHERE id = ?", (line_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="opening not found")
        rows = conn.execute(
            """
            SELECT ply, usi, from_sfen, to_sfen, comment, variation_group, parent_move_id, sort_order
            FROM opening_line_moves
            WHERE line_id = ?
            ORDER BY variation_group, ply, sort_order
            """,
            (line_id,),
        ).fetchall()
        return [
            {
                "ply": row["ply"],
                "usi": row["usi"],
                "from_sfen": row["from_sfen"],
                "to_sfen": row["to_sfen"],
                "comment": row["comment"],
                "variation_group": row["variation_group"],
                "parent_move_id": row["parent_move_id"],
                "sort_order": row["sort_order"],
            }
            for row in rows
        ]
    finally:
        conn.close()
