"""Book source and license APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..database import get_connection

router = APIRouter(tags=["book"])


def _source(row: Any, include_license_text: bool = False) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "source_url": row["source_url"],
        "license_name": row["license_name"],
        "copyright_notice": row["copyright_notice"],
        "file_name": row["file_name"],
        "file_sha256": row["file_sha256"],
        "imported_at": row["imported_at"],
        "position_count": row["position_count"],
        "move_count": row["move_count"],
        "note": row["note"],
    }
    if include_license_text:
        data["license_text"] = row["license_text"]
    return data


@router.get("/api/book/candidates")
def get_book_candidates(sfen: str = Query(..., min_length=1)) -> dict[str, Any]:
    normalized_sfen = sfen.strip()
    if not normalized_sfen:
        raise HTTPException(status_code=422, detail="sfen must not be blank")

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                bm.id AS move_id,
                bm.usi AS move_usi,
                bm.score,
                bm.depth,
                bm.pv,
                bm.raw,
                bm.sort_order,
                bp.id AS position_id,
                bs.id AS source_id,
                bs.name AS source_name,
                bs.version AS source_version,
                bs.source_url,
                bs.license_name,
                bs.copyright_notice
            FROM book_positions bp
            JOIN book_moves bm ON bm.position_id = bp.id
            JOIN book_sources bs ON bs.id = bp.source_id
            WHERE bp.sfen = ?
            ORDER BY
                CASE WHEN bm.sort_order IS NULL THEN 1 ELSE 0 END ASC,
                bm.sort_order ASC,
                CASE WHEN bm.score IS NULL THEN 1 ELSE 0 END ASC,
                bm.score DESC,
                CASE WHEN bm.depth IS NULL THEN 1 ELSE 0 END ASC,
                bm.depth DESC,
                bs.imported_at DESC,
                bs.id DESC,
                bm.id ASC
            """,
            (normalized_sfen,),
        ).fetchall()
        candidates = [
            {
                "move_usi": row["move_usi"],
                "rank": row["sort_order"] + 1 if row["sort_order"] is not None else None,
                "score": row["score"],
                "depth": row["depth"],
                "pv": row["pv"],
                "raw": row["raw"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "source_version": row["source_version"],
                "license": row["license_name"],
                "license_name": row["license_name"],
                "source_url": row["source_url"],
                "copyright_notice": row["copyright_notice"],
            }
            for row in rows
        ]
        return {"sfen": normalized_sfen, "found": bool(candidates), "candidates": candidates}
    finally:
        conn.close()


@router.get("/api/book/sources")
def list_book_sources() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM book_sources ORDER BY imported_at DESC, id DESC").fetchall()
        return [_source(row) for row in rows]
    finally:
        conn.close()


@router.get("/api/book/sources/{source_id}")
def get_book_source(source_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM book_sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="book source not found")
        return _source(row, include_license_text=True)
    finally:
        conn.close()


@router.get("/api/book/sources/{source_id}/learning-samples/summary")
def get_learning_sample_summary(source_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        source = conn.execute("SELECT id, name, version, license_name, source_url FROM book_sources WHERE id = ?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="book source not found")
        rows = conn.execute(
            """
            SELECT opening_key, opening_name, COUNT(*) AS sample_count
            FROM learning_samples
            WHERE book_source_id = ?
            GROUP BY opening_key, opening_name
            ORDER BY sample_count DESC, opening_key
            """,
            (source_id,),
        ).fetchall()
        return {
            "source": dict(source),
            "total_samples": sum(row["sample_count"] for row in rows),
            "unclassified_samples": sum(row["sample_count"] for row in rows if row["opening_key"] == "unclassified"),
            "openings": [dict(row) for row in rows],
        }
    finally:
        conn.close()


@router.get("/api/licenses")
def list_licenses() -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM book_sources ORDER BY imported_at DESC, id DESC").fetchall()
        return {"book_sources": [_source(row, include_license_text=True) for row in rows]}
    finally:
        conn.close()
