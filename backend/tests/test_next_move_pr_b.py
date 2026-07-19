import logging
import os

from app.next_move_database import get_next_move_write_connection, init_next_move_db
from app.next_move_resolver import clear_resolver_cache, resolve_problems

SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - {}"


def _source(conn, digest: str, imported: str = "2026-01-01"):
    return conn.execute("""INSERT INTO book_sources(name,version,source_url,file_sha256,imported_at)
      VALUES('same','v1','https://example.test',?,?)""", (digest, imported)).lastrowid


def _sample(conn, source, sfen, move, rank, opening, run=None):
    position = conn.execute("INSERT INTO book_positions(source_id,sfen) VALUES(?,?)", (source, sfen)).lastrowid
    conn.execute("INSERT INTO book_moves(position_id,usi,sort_order) VALUES(?,?,0)", (position, move))
    return conn.execute("""INSERT INTO learning_samples(book_source_id,book_position_id,opening_key,opening_name,
      sfen,sample_rank,extraction_run_key) VALUES(?,?,?,?,?,?,?)""",
      (source, position, opening, opening, sfen, rank, run)).lastrowid


def test_duplicate_problem_uses_latest_run_then_rank_then_id_and_warns(client, tmp_path, caplog):
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "duplicates.db")
    init_next_move_db()
    conn = get_next_move_write_connection()
    conn.executemany("INSERT INTO extraction_runs VALUES(?,?,?,?,?,?,?)", [
        ("old", "1", 1, 1, 1, "a", "2026-01-01"), ("new", "1", 1, 1, 1, "b", "2026-02-01")])
    old_source, new_source, tie_source = (_source(conn, value) for value in ("a", "b", "c"))
    _sample(conn, old_source, SFEN.format(1), "7g7f", 1, "old-opening", "old")
    expected = _sample(conn, new_source, SFEN.format(2), "7g7f", 5, "representative", "new")
    # Same run and rank loses by the final sample-id tie breaker.
    _sample(conn, tie_source, SFEN.format(3), "7g7f", 5, "later-id", "new")
    conn.commit()
    with caplog.at_level(logging.WARNING):
        resolved = resolve_problems(conn)
    conn.close()
    assert len(resolved) == 1
    assert resolved[0]["id"] == expected
    assert resolved[0]["opening_key"] == "representative"
    assert "Conflicting metadata" in caplog.text
    page = client.get("/api/learning-samples?offset=0&limit=100").json()
    assert page["total"] == 1 and len(page["items"]) == 1


def test_250_distinct_problems_page_without_gaps_in_rank_key_order(client, tmp_path):
    os.environ["NEXT_MOVE_DB_PATH"] = str(tmp_path / "paging.db")
    init_next_move_db()
    conn = get_next_move_write_connection()
    source = _source(conn, "paging")
    for index in range(250):
        _sample(conn, source, SFEN.format(index + 1), f"move-{index}", (index * 37) % 250, "opening")
    conn.execute("INSERT OR REPLACE INTO database_metadata VALUES('dataset_version','v1:paging')")
    conn.commit(); conn.close(); clear_resolver_cache()
    pages = [client.get(f"/api/learning-samples?offset={offset}&limit=100").json() for offset in (0, 100, 200)]
    items = [item for page in pages for item in page["items"]]
    assert [len(page["items"]) for page in pages] == [100, 100, 50]
    assert len({item["problem_key"] for item in items}) == 250
    assert [(item["sample_rank"], item["problem_key"]) for item in items] == sorted(
        (item["sample_rank"], item["problem_key"]) for item in items)
    assert {page["dataset_version"] for page in pages} == {"v1:paging"}
