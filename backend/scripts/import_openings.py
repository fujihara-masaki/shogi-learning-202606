"""Import reusable SFEN/USI opening lines into SQLite.

Input files are read from data/openings/*.sfen by default. Each non-empty,
non-comment line must be one of:

- startpos moves 7g7f 3c3d ...
- sfen <board> <turn> <hands> <move_number> moves 7g7f ...

License metadata is stored in opening_sources. The importer intentionally keeps
classification simple; tags can be refined later without changing the source
format.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import shogi

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.database import get_connection, init_db  # noqa: E402

TAG_LABELS = {
    "nakabisha": "中飛車",
    "bougin": "棒銀",
    "mukaibisha": "向かい飛車",
}


@dataclass(frozen=True)
class ParsedLine:
    initial_sfen: str
    moves: list[str]


@dataclass(frozen=True)
class OpeningTag:
    tag: str
    score: float
    reason: str


def parse_usi_line(text: str) -> ParsedLine:
    parts = text.strip().split()
    if not parts:
        raise ValueError("empty line")
    if parts[0] == "startpos":
        if len(parts) == 1:
            return ParsedLine(shogi.STARTING_SFEN, [])
        if len(parts) < 3 or parts[1] != "moves":
            raise ValueError("startpos line must be 'startpos moves ...'")
        return ParsedLine(shogi.STARTING_SFEN, parts[2:])
    if parts[0] == "sfen":
        try:
            moves_index = parts.index("moves")
        except ValueError:
            moves_index = len(parts)
        sfen_parts = parts[1:moves_index]
        if len(sfen_parts) != 4:
            raise ValueError("sfen line must contain 4 SFEN fields before moves")
        return ParsedLine(" ".join(sfen_parts), parts[moves_index + 1 :])
    raise ValueError("line must start with 'startpos' or 'sfen'")


def board_snapshots(parsed: ParsedLine) -> tuple[list[str], list[tuple[int, str, str, str]]]:
    board = shogi.Board(parsed.initial_sfen)
    positions = [board.sfen()]
    moves: list[tuple[int, str, str, str]] = []
    for ply, usi in enumerate(parsed.moves, start=1):
        before = board.sfen()
        move = shogi.Move.from_usi(usi)
        if move not in board.legal_moves:
            raise ValueError(f"illegal move at ply {ply}: {usi}")
        board.push(move)
        after = board.sfen()
        positions.append(after)
        moves.append((ply, usi, before, after))
    return positions, moves


def rook_files_by_ply(positions: Iterable[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for ply, sfen in enumerate(positions):
        board = shogi.Board(sfen)
        for square in shogi.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.piece_type == shogi.ROOK:
                name = shogi.SQUARE_NAMES[square]
                out.append((ply, int(name[0]), name))
    return out


def classify_opening(positions: list[str], moves: list[str]) -> list[OpeningTag]:
    tags: list[OpeningTag] = []
    early_positions = positions[:41]
    rook_files = rook_files_by_ply(early_positions)

    if any(file_no == 5 for _, file_no, _ in rook_files):
        tags.append(OpeningTag("nakabisha", 0.9, "序盤40手以内に飛車が5筋にいる"))

    # 棒銀: 銀が2筋/8筋の攻め筋へ早く出る簡易判定。
    silver_attack_squares = {"2f", "2e", "2d", "8d", "8e", "8f"}
    for ply, sfen in enumerate(early_positions):
        board = shogi.Board(sfen)
        if any(
            (piece := board.piece_at(square))
            and piece.piece_type == shogi.SILVER
            and shogi.SQUARE_NAMES[square] in silver_attack_squares
            for square in shogi.SQUARES
        ):
            tags.append(OpeningTag("bougin", 0.5, f"{ply}手目までに銀が2筋/8筋へ進出"))
            break

    # 向かい飛車: 飛車が相手飛車の筋(先手8筋/後手2筋)へ移動する簡易判定。
    if any(square in {"8h", "2b"} for _, _, square in rook_files):
        tags.append(OpeningTag("mukaibisha", 0.6, "序盤40手以内に飛車が向かい飛車の筋へいる"))

    if not tags:
        tags.append(OpeningTag("other", 0.1, "簡易分類に該当しない"))
    return tags


def import_file(path: Path, *, license_name: str, license_url: str) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO opening_sources(name, file_path, license_name, license_url) VALUES (?, ?, ?, ?)",
            (path.stem, str(path), license_name, license_url),
        )
        source_id = int(cur.lastrowid)
        imported = 0
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            parsed = parse_usi_line(text)
            positions, move_rows = board_snapshots(parsed)
            tags = classify_opening(positions, parsed.moves)
            primary = max(tags, key=lambda t: t.score)
            tag_values = [tag.tag for tag in tags]
            name = f"{path.stem} #{line_no}"
            cur = conn.execute(
                """
                INSERT INTO opening_lines(source_id, name, opening_type, initial_sfen, moves, comments, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    name,
                    TAG_LABELS.get(primary.tag, primary.tag),
                    positions[0],
                    json.dumps(parsed.moves, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps(tag_values, ensure_ascii=False),
                ),
            )
            line_id = int(cur.lastrowid)
            conn.executemany(
                "INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, ?, ?)",
                [(line_id, ply, sfen) for ply, sfen in enumerate(positions)],
            )
            conn.executemany(
                "INSERT INTO opening_moves(line_id, ply, usi, from_sfen, to_sfen) VALUES (?, ?, ?, ?, ?)",
                [(line_id, ply, usi, before, after) for ply, usi, before, after in move_rows],
            )
            conn.executemany(
                "INSERT INTO opening_tags(line_id, tag, score, reason) VALUES (?, ?, ?, ?)",
                [(line_id, tag.tag, tag.score, tag.reason) for tag in tags],
            )
            imported += 1
        conn.commit()
        return imported
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def import_directory(directory: Path, *, license_name: str, license_url: str) -> int:
    init_db()
    count = 0
    for path in sorted(directory.glob("*.sfen")):
        count += import_file(path, license_name=license_name, license_url=license_url)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SFEN/USI opening data")
    parser.add_argument("directory", nargs="?", default=str(ROOT / "data" / "openings"))
    parser.add_argument("--license-name", default="", help="License name for imported source files")
    parser.add_argument("--license-url", default="", help="License URL for imported source files")
    args = parser.parse_args()
    count = import_directory(Path(args.directory), license_name=args.license_name, license_url=args.license_url)
    print(f"imported {count} opening lines")


if __name__ == "__main__":
    main()
