"""Book source and license APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

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


@router.get("/api/licenses")
def list_licenses() -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM book_sources ORDER BY imported_at DESC, id DESC").fetchall()
        return {"book_sources": [_source(row, include_license_text=True) for row in rows]}
    finally:
        conn.close()
