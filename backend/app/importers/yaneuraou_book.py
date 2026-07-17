"""Importer for YaneuraOu text book files (commonly named ``book.db``).

The large external book itself must not be committed. This module supports a
safe dry-run and limited sample imports for license/source plumbing.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.next_move_database import get_next_move_write_connection, init_next_move_db

SFEN_RE = re.compile(r"^(?:sfen\s+)?(.+\s[bw]\s(?:-|[RBGSNLPrbgsnlp0-9+]+)\s\d+)$")
USI_RE = re.compile(r"^(?:[1-9][a-i][1-9][a-i][+]?|[RBGSNLP]\*[1-9][a-i])$")


@dataclass
class ParsedMove:
    usi: str
    score: int | None
    depth: int | None
    pv: str
    raw: str


@dataclass
class ParsedPosition:
    sfen: str
    line_no: int
    moves: list[ParsedMove]


@dataclass
class ImportResult:
    source_id: int | None
    file_sha256: str
    positions_read: int
    moves_read: int
    invalid_lines: int
    duplicate_positions: int
    imported_positions: int
    imported_moves: int
    dry_run: bool


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_move_line(text: str) -> ParsedMove | None:
    parts = text.split()
    if not parts or not USI_RE.match(parts[0]):
        return None
    ints = []
    rest = []
    for token in parts[1:]:
        if re.fullmatch(r"[-+]?\d+", token) and len(ints) < 2:
            ints.append(int(token))
        else:
            rest.append(token)
    return ParsedMove(parts[0], ints[0] if ints else None, ints[1] if len(ints) > 1 else None, " ".join(rest), text)


@dataclass
class ParseStats:
    positions_read: int = 0
    moves_read: int = 0
    invalid_lines: int = 0
    duplicate_positions: int = 0


def iter_book_positions(path: Path, *, limit: int | None = None, stats: ParseStats | None = None):
    current: ParsedPosition | None = None
    skipping_duplicate = False
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            m = SFEN_RE.match(text)
            if m:
                if current is not None:
                    yield current
                    current = None
                if limit is not None and stats is not None and stats.positions_read >= limit:
                    break
                sfen = m.group(1)
                if sfen in seen:
                    if stats is not None:
                        stats.duplicate_positions += 1
                    skipping_duplicate = True
                    continue
                seen.add(sfen)
                skipping_duplicate = False
                current = ParsedPosition(sfen=sfen, line_no=line_no, moves=[])
                if stats is not None:
                    stats.positions_read += 1
                continue
            move = parse_move_line(text)
            if move and current is not None:
                current.moves.append(move)
                if stats is not None:
                    stats.moves_read += 1
            elif move and skipping_duplicate:
                continue
            elif stats is not None:
                stats.invalid_lines += 1
    if current is not None:
        yield current


def parse_book(path: Path, *, limit: int | None = None) -> tuple[list[ParsedPosition], int, int]:
    stats = ParseStats()
    positions = list(iter_book_positions(path, limit=limit, stats=stats))
    return positions, stats.invalid_lines, stats.duplicate_positions


def import_book(path: Path, *, name: str, version: str = "", source_url: str = "", license_name: str = "", license_text: str = "", copyright_notice: str = "", note: str = "", dry_run: bool = False, limit: int | None = None) -> ImportResult:
    init_next_move_db()
    file_hash = sha256_file(path)
    stats = ParseStats()
    if dry_run:
        for _ in iter_book_positions(path, limit=limit, stats=stats):
            pass
        return ImportResult(None, file_hash, stats.positions_read, stats.moves_read, stats.invalid_lines, stats.duplicate_positions, 0, 0, True)
    conn = get_next_move_write_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO book_sources(name, version, source_url, license_name, license_text, copyright_notice, file_name, file_sha256, position_count, move_count, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (name, version, source_url, license_name, license_text, copyright_notice, path.name, file_hash, note),
        )
        source_id = int(cur.lastrowid)
        imported_moves = 0
        for pos in iter_book_positions(path, limit=limit, stats=stats):
            cur = conn.execute("INSERT INTO book_positions(source_id, sfen, line_no) VALUES (?, ?, ?)", (source_id, pos.sfen, pos.line_no))
            position_id = int(cur.lastrowid)
            conn.executemany(
                "INSERT INTO book_moves(position_id, usi, score, depth, pv, raw, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(position_id, m.usi, m.score, m.depth, m.pv, m.raw, i) for i, m in enumerate(pos.moves)],
            )
            imported_moves += len(pos.moves)
        conn.execute("UPDATE book_sources SET position_count = ?, move_count = ? WHERE id = ?", (stats.positions_read, stats.moves_read, source_id))
        conn.commit()
        return ImportResult(source_id, file_hash, stats.positions_read, stats.moves_read, stats.invalid_lines, stats.duplicate_positions, stats.positions_read, imported_moves, False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import YaneuraOu book.db text data")
    parser.add_argument("path")
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--license-name", default="")
    parser.add_argument("--license-text", default="")
    parser.add_argument("--copyright-notice", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = import_book(Path(args.path), name=args.name, version=args.version, source_url=args.source_url, license_name=args.license_name, license_text=args.license_text, copyright_notice=args.copyright_notice, note=args.note, dry_run=args.dry_run, limit=args.limit)
    print(f"sha256={result.file_sha256}")
    print(f"positions={result.positions_read} moves={result.moves_read} invalid_lines={result.invalid_lines} duplicate_positions={result.duplicate_positions}")
    print(f"imported_positions={result.imported_positions} imported_moves={result.imported_moves} dry_run={result.dry_run}")


if __name__ == "__main__":
    main()
