"""Importer for tokuhirom/tanuki-tsume-shogi puzzle JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from ..database import get_connection, init_db

SOURCE_NAME = "tokuhirom/tanuki-tsume-shogi"
SOURCE_URL = "https://github.com/tokuhirom/tanuki-tsume-shogi"
LICENSE_NAME = "MIT License"
COPYRIGHT_NOTICE = "Copyright (c) 2026 tokuhirom"
MIT_LICENSE_TEXT = """MIT License

Copyright (c) 2026 tokuhirom

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
RAW_BASE = "https://raw.githubusercontent.com/tokuhirom/tanuki-tsume-shogi/main/puzzles"
EXPECTED_COUNTS = {1: 228, 3: 543, 5: 296}
RANKS = "abcdefghi"

PIECE_ORDER = "RBGSNLP"


def _piece_type(value: Any) -> str:
    piece = str(value)
    if not piece:
        raise ValueError("missing piece type")
    if piece.startswith("+"):
        return "+" + piece[1:].upper()
    return piece.upper()


def _piece_to_sfen(piece_type: Any, owner: str) -> str:
    piece = _piece_type(piece_type)
    if owner == "defender":
        if piece.startswith("+"):
            return "+" + piece[1:].lower()
        return piece.lower()
    if owner != "attacker":
        raise ValueError(f"unsupported owner: {owner!r}")
    return piece


def _piece_square(piece: dict[str, Any]) -> str:
    for key in ("square", "position", "pos"):
        if key in piece:
            return _square(piece[key])
    if "file" in piece or "x" in piece:
        return _square(piece)
    raise ValueError(f"missing piece square: {piece!r}")


def _pieces_to_board_sfen(pieces: Any) -> str:
    board: dict[tuple[int, str], str] = {}
    if isinstance(pieces, dict):
        iterable = []
        for square, piece in pieces.items():
            if isinstance(piece, str):
                iterable.append({"square": square, "type": piece, "owner": "attacker"})
            else:
                item = dict(piece)
                item.setdefault("square", square)
                iterable.append(item)
    else:
        iterable = pieces or []

    for piece in iterable:
        if not isinstance(piece, dict):
            raise ValueError(f"unsupported piece entry: {piece!r}")
        square = _piece_square(piece)
        file = int(square[0])
        rank = square[1]
        owner = str(piece.get("owner") or piece.get("side") or "attacker")
        board[(file, rank)] = _piece_to_sfen(piece.get("type") or piece.get("piece"), owner)

    ranks: list[str] = []
    for rank in RANKS:
        empty = 0
        row = ""
        for file in range(9, 0, -1):
            piece = board.get((file, rank))
            if piece:
                if empty:
                    row += str(empty)
                    empty = 0
                row += piece
            else:
                empty += 1
        if empty:
            row += str(empty)
        ranks.append(row)
    return "/".join(ranks)


def _iter_hand_counts(hand: Any) -> list[tuple[str, int]]:
    if not hand:
        return []
    if isinstance(hand, dict):
        return [(str(piece), int(count)) for piece, count in hand.items() if int(count) > 0]
    if isinstance(hand, list):
        counts: dict[str, int] = {}
        for item in hand:
            if isinstance(item, str):
                counts[item] = counts.get(item, 0) + 1
            elif isinstance(item, dict):
                piece = str(item.get("type") or item.get("piece"))
                count = int(item.get("count", 1))
                counts[piece] = counts.get(piece, 0) + count
            else:
                raise ValueError(f"unsupported hand item: {item!r}")
        return [(piece, count) for piece, count in counts.items() if count > 0]
    raise ValueError(f"unsupported hand: {hand!r}")


def _hands_to_sfen(hands: dict[str, Any] | None) -> str:
    if not hands:
        return "-"
    by_piece: dict[str, int] = {}
    for owner, hand in (("attacker", hands.get("attacker")), ("defender", hands.get("defender"))):
        for piece, count in _iter_hand_counts(hand):
            sfen_piece = _piece_to_sfen(piece, owner)
            by_piece[sfen_piece] = by_piece.get(sfen_piece, 0) + count

    parts: list[str] = []
    for piece in PIECE_ORDER:
        count = by_piece.get(piece, 0)
        if count:
            parts.append((str(count) if count > 1 else "") + piece)
    for piece in PIECE_ORDER.lower():
        count = by_piece.get(piece, 0)
        if count:
            parts.append((str(count) if count > 1 else "") + piece)
    return "".join(parts) or "-"


def initial_to_sfen(initial: Any) -> str:
    """Convert tanuki initial object ({pieces, hands, sideToMove}) to SFEN."""
    if isinstance(initial, str):
        return initial
    if not isinstance(initial, dict):
        raise ValueError(f"unsupported initial: {initial!r}")
    board = _pieces_to_board_sfen(initial.get("pieces"))
    side = initial.get("sideToMove", "attacker")
    if side == "attacker":
        side_sfen = "b"
    elif side == "defender":
        side_sfen = "w"
    else:
        raise ValueError(f"unsupported sideToMove: {side!r}")
    hands = _hands_to_sfen(initial.get("hands") or {})
    return f"{board} {side_sfen} {hands} 1"


def _square(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        file, rank = value
        if isinstance(rank, int):
            rank = RANKS[rank - 1]
        return f"{file}{rank}"
    if isinstance(value, dict):
        file = value.get("file") or value.get("x")
        rank = value.get("rank") or value.get("y")
        if isinstance(rank, int):
            rank = RANKS[rank - 1]
        return f"{file}{rank}"
    raise ValueError(f"unsupported square: {value!r}")


def move_to_usi(move: Any) -> str:
    """Convert a tanuki move object ({from/to/promote} or {drop/to}) to USI."""
    if isinstance(move, str):
        return move
    if not isinstance(move, dict):
        raise ValueError(f"unsupported move: {move!r}")
    promote = "+" if move.get("promote") else ""
    to_sq = _square(move["to"])
    if move.get("drop"):
        return f"{str(move['drop']).upper()}*{to_sq}{promote}"
    return f"{_square(move['from'])}{to_sq}{promote}"


def normalize_puzzle(raw: dict[str, Any], fallback_mate_length: int) -> dict[str, Any]:
    mate_length = int(raw.get("mateLength") or raw.get("mate_length") or fallback_mate_length)
    solution_raw = raw.get("solution") or raw.get("moves") or []
    line = [move_to_usi(m) for m in solution_raw]
    solution_moves = line[0::2]
    opponent_moves = line[1::2]
    external_id = str(raw.get("id") or raw.get("external_id") or raw.get("hash") or "")
    return {
        "title": f"[tanuki] {mate_length}手詰 #{external_id or raw.get('hash', '')}",
        "initial_sfen": initial_to_sfen(raw.get("initial") or raw.get("initial_sfen") or raw.get("sfen")),
        "mate_length": mate_length,
        "solution_moves": solution_moves,
        "opponent_moves": opponent_moves,
        "difficulty": max(1, min(5, (mate_length + 1) // 2)),
        "tags": [f"{mate_length}手詰", "tanuki-tsume-shogi"],
        "explanation": "tokuhirom/tanuki-tsume-shogi 由来の詰将棋データです。",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_license": LICENSE_NAME,
        "source_copyright": COPYRIGHT_NOTICE,
        "external_id": external_id,
        "source_hash": str(raw.get("hash") or ""),
        "source_metadata": json.dumps({k: raw.get(k) for k in ("id", "mateLength", "initial", "solution", "quality", "score", "hash") if k in raw}, ensure_ascii=False),
    }


def load_json(path_or_url: str) -> list[dict[str, Any]]:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        with urlopen(path_or_url) as res:  # noqa: S310 - explicit user/import URL
            return json.load(res)
    with Path(path_or_url).open(encoding="utf-8") as fh:
        return json.load(fh)


def import_tanuki(paths: list[str] | None = None, *, dry_run: bool = False) -> dict[str, int]:
    init_db()
    paths = paths or [f"{RAW_BASE}/{n}.json" for n in (1, 3, 5)]
    imported = skipped = total = 0
    conn = get_connection()
    try:
        for path in paths:
            fallback = int(Path(path).stem) if Path(path).stem.isdigit() else 0
            for raw in load_json(path):
                total += 1
                p = normalize_puzzle(raw, fallback)
                if not p["initial_sfen"]:
                    raise ValueError(f"missing initial in {path}: {raw!r}")
                if dry_run:
                    imported += 1
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO tsume_problems
                      (title, initial_sfen, mate_length, solution_moves, opponent_moves, difficulty, tags, explanation,
                       source_name, source_url, source_license, source_copyright, external_id, source_hash, source_metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (p["title"], p["initial_sfen"], p["mate_length"], json.dumps(p["solution_moves"]), json.dumps(p["opponent_moves"]), p["difficulty"], json.dumps(p["tags"], ensure_ascii=False), p["explanation"], p["source_name"], p["source_url"], p["source_license"], p["source_copyright"], p["external_id"], p["source_hash"], p["source_metadata"]),
                )
                if cur.rowcount:
                    imported += 1
                else:
                    skipped += 1
        conn.commit()
    finally:
        conn.close()
    return {"total": total, "imported": imported, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="JSON files/URLs; defaults to puzzles/1.json, 3.json, 5.json from GitHub")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_tanuki(args.paths or None, dry_run=args.dry_run), ensure_ascii=False))


if __name__ == "__main__":
    main()
