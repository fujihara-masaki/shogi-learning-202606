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
from typing import Iterable, Sequence

import shogi

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.database import get_connection, init_db  # noqa: E402
from app.seed import seed_opening_catalog_if_empty  # noqa: E402

TAG_LABELS = {
    "nakabisha": "中飛車",
    "bougin": "棒銀",
    "mukaibisha": "向かい飛車",
}

OPENING_TYPE_TAGS = {
    "nakabisha": "中飛車",
    "bougin": "棒銀",
    "mukaibisha": "向かい飛車",
}

OPENING_KEYWORDS = {
    "棒銀": [["棒銀"]],
    "原始棒銀": [["原始", "棒銀"]],
    "矢倉棒銀": [["矢倉", "棒銀"]],
    "角換わり棒銀": [["角換わり", "棒銀"], ["角換り", "棒銀"]],
    "角換わり早繰り銀": [["角換わり", "早繰り銀"], ["角換り", "早繰り銀"]],
    "角換わり腰掛け銀": [["角換わり", "腰掛け銀"], ["角換り", "腰掛け銀"]],
    "右四間飛車": [["右四間"]],
    "四間飛車": [["四間飛車"], ["ノーマル", "四間"]],
    "角交換四間飛車": [["角交換", "四間"], ["角交換四間"]],
    "ゴキゲン中飛車": [["ゴキ中"], ["ゴキゲン", "中飛車"]],
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



def normalize_opening_text(text: str) -> str:
    table = str.maketrans({
        " ": "",
        "　": "",
        "-": "",
        "_": "",
        "・": "",
        "／": "",
        "/": "",
        "（": "",
        "）": "",
        "(": "",
        ")": "",
    })
    normalized = text.translate(table)
    for suffix in ("戦法", "戦型", "定跡"):
        normalized = normalized.replace(suffix, "")
    return normalized


def _load_opening_type_rows(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name_ja, aliases
        FROM opening_types
        WHERE is_active = 1
        ORDER BY LENGTH(name_ja) DESC, sort_order ASC, id ASC
        """
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            aliases = json.loads(row["aliases"] or "[]")
        except json.JSONDecodeError:
            aliases = []
        out.append({"id": row["id"], "name_ja": row["name_ja"], "aliases": aliases})
    return out


def infer_opening_type(conn, texts: Sequence[str], heuristic_tags: Sequence[OpeningTag] = ()) -> tuple[int | None, str, OpeningTag]:
    haystack = " ".join(text for text in texts if text)
    normalized = normalize_opening_text(haystack)
    rows = _load_opening_type_rows(conn)

    def found(row: dict, score: float, reason: str) -> tuple[int, str, OpeningTag]:
        return row["id"], row["name_ja"], OpeningTag(normalize_opening_text(row["name_ja"]), score, reason)

    # 1. 明示的な戦型名の完全一致（表記ゆれの「戦法」等は正規化）。
    for row in rows:
        name = normalize_opening_text(row["name_ja"])
        if normalized == name or name in normalized:
            return found(row, 1.0, "戦型名の完全一致")

    # 2. alias 一致。
    for row in rows:
        for alias in row["aliases"]:
            alias_norm = normalize_opening_text(str(alias))
            if alias_norm and (normalized == alias_norm or alias_norm in normalized):
                return found(row, 0.95, "alias一致")

    # 3. 複合キーワード一致。
    for row in rows:
        for keyword_group in OPENING_KEYWORDS.get(row["name_ja"], []):
            normalized_group = [normalize_opening_text(keyword) for keyword in keyword_group]
            if len(normalized_group) > 1 and all(keyword in normalized for keyword in normalized_group):
                return found(row, 0.85, "複合キーワード一致")

    # 4. 単独キーワード一致。
    for row in rows:
        for keyword_group in OPENING_KEYWORDS.get(row["name_ja"], []):
            for keyword in keyword_group:
                keyword_norm = normalize_opening_text(keyword)
                if keyword_norm and keyword_norm in normalized:
                    return found(row, 0.7, "単独キーワード一致")

    # 既存の盤面ベース簡易分類も維持する。
    if heuristic_tags:
        primary = max(heuristic_tags, key=lambda tag: tag.score)
        opening_type_name = OPENING_TYPE_TAGS.get(primary.tag)
        if opening_type_name:
            for row in rows:
                if row["name_ja"] == opening_type_name:
                    return row["id"], row["name_ja"], primary

    # 5. 分類不能な場合は未分類。
    for row in rows:
        if row["name_ja"] == "未分類":
            return row["id"], row["name_ja"], OpeningTag("unclassified", 0.1, "分類不能なため未分類")
    return None, "未分類", OpeningTag("unclassified", 0.1, "分類不能なため未分類")

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
            type_id, opening_type_name, inferred_tag = infer_opening_type(conn, [path.stem, text], tags)
            primary = inferred_tag
            tag_values = [tag.tag for tag in tags]
            if inferred_tag.tag not in tag_values:
                tag_values.append(inferred_tag.tag)
            name = f"{path.stem} #{line_no}"
            cur = conn.execute(
                """
                INSERT INTO opening_lines(source_id, opening_type_id, name, opening_type, initial_sfen, moves, comments, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    type_id,
                    name,
                    opening_type_name,
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
            parent_id = None
            for ply, usi, before, after in move_rows:
                move_key = f"main-{ply}"
                move_cur = conn.execute(
                    "INSERT INTO opening_line_moves(line_id, ply, usi, from_sfen, to_sfen, parent_move_id, move_key, is_main) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (line_id, ply, usi, before, after, parent_id, move_key),
                )
                parent_id = int(move_cur.lastrowid)
            stored_tags = list(tags)
            if inferred_tag.tag not in {tag.tag for tag in stored_tags}:
                stored_tags.append(inferred_tag)
            conn.executemany(
                "INSERT INTO opening_tags(line_id, tag, score, reason) VALUES (?, ?, ?, ?)",
                [(line_id, tag.tag, tag.score, tag.reason) for tag in stored_tags],
            )
            imported += 1
        conn.commit()
        return imported
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_opening_catalog_seeded() -> None:
    conn = get_connection()
    try:
        seed_opening_catalog_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def import_directory(directory: Path, *, license_name: str, license_url: str) -> int:
    init_db()
    ensure_opening_catalog_seeded()
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
