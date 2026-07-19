"""Perform a complete, read-only validation of a next-move SQLite database."""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.next_move_identity import problem_key

REQUIRED = {"book_sources", "book_positions", "book_moves", "learning_samples"}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-learning-samples", type=int)
    args = parser.parse_args()
    if not args.path.is_file():
        parser.error(f"database does not exist: {args.path}")
    conn = sqlite3.connect(f"file:{args.path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        errors = []
        if missing := REQUIRED - tables: errors.append(f"missing tables: {', '.join(sorted(missing))}")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok": errors.append(f"integrity_check: {integrity}")
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys: errors.append(f"foreign_key_check: {len(foreign_keys)} violation(s)")
        if not errors:
            modern = {"extraction_runs", "database_metadata"}.issubset(tables) and "extraction_run_key" in {
                r[1] for r in conn.execute("PRAGMA table_info(learning_samples)")}
            if modern:
                missing_runs = conn.execute("""SELECT COUNT(*) FROM learning_samples ls LEFT JOIN extraction_runs er
                    ON er.extraction_run_key=ls.extraction_run_key WHERE er.extraction_run_key IS NULL""").fetchone()[0]
                metadata = conn.execute("SELECT value FROM database_metadata WHERE key='dataset_version'").fetchone()
                if missing_runs: errors.append(f"invalid extraction_run reference: {missing_runs}")
                if not metadata or not str(metadata[0]).startswith("v1:"): errors.append("missing/invalid dataset_version")
                print("schema=new")
            else:
                print("WARNING: legacy schema (extraction metadata unavailable)")
            orphan_sources = conn.execute("SELECT COUNT(*) FROM learning_samples ls LEFT JOIN book_sources bs ON bs.id=ls.book_source_id WHERE bs.id IS NULL").fetchone()[0]
            orphan_positions = conn.execute("SELECT COUNT(*) FROM learning_samples ls LEFT JOIN book_positions bp ON bp.id=ls.book_position_id WHERE bp.id IS NULL").fetchone()[0]
            duplicates = conn.execute("SELECT COUNT(*) FROM (SELECT book_source_id,book_position_id FROM learning_samples GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0]
            missing_license = conn.execute("SELECT COUNT(*) FROM book_sources WHERE trim(license_name)='' OR trim(source_url)='' ").fetchone()[0]
            for label, count in [("orphan source", orphan_sources),("orphan position",orphan_positions),("duplicate sample",duplicates),("source missing license/url",missing_license)]:
                if count: errors.append(f"{label}: {count}")
            keys: dict[str, tuple[str, str]] = {}
            sample_rows = conn.execute("""SELECT ls.opening_key,ls.opening_name,ls.sfen,ls.book_position_id,
                bs.name,bs.version,bs.source_url FROM learning_samples ls JOIN book_sources bs ON bs.id=ls.book_source_id""")
            for sample in sample_rows:
                candidates = [dict(move_usi=r[0], score=r[1], depth=r[2], sort_order=r[3]) for r in conn.execute(
                    "SELECT usi,score,depth,sort_order FROM book_moves WHERE position_id=?", (sample["book_position_id"],))]
                try:
                    key = problem_key({"name": sample["name"], "version": sample["version"], "source_url": sample["source_url"]}, sample["sfen"], candidates)
                except Exception as exc:
                    errors.append(f"canonical key calculation failed: {exc}")
                    continue
                metadata_pair = (sample["opening_key"], sample["opening_name"])
                if key in keys:
                    print(f"WARNING: duplicate problem_key: {key}")
                    if keys[key] != metadata_pair: errors.append(f"metadata conflict for problem_key: {key}")
                keys[key] = metadata_pair
            for table in sorted(REQUIRED): print(f"{table}={conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
            learning_sample_count = conn.execute("SELECT COUNT(*) FROM learning_samples").fetchone()[0]
            if args.expected_learning_samples is not None and learning_sample_count != args.expected_learning_samples:
                errors.append(
                    "learning_samples count: "
                    f"expected {args.expected_learning_samples}, actual {learning_sample_count}"
                )
        if errors:
            for error in errors: print(f"ERROR: {error}")
            return 1
        print("validation=ok")
        return 0
    finally: conn.close()

if __name__ == "__main__": raise SystemExit(main())
