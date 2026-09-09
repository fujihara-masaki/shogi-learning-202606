import json
from collections import defaultdict
from pathlib import Path
import shogi
from app.database import get_connection, init_db
from app.seed import (
    apply_bundled_wikipedia_opening_artifacts,
    seed_opening_catalog_if_empty,
    seed_openings_if_empty,
)
from app.wikipedia_opening_importer import (
    compare_canonical_to_legacy,
    compare_canonical_to_runtime,
)
from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact

P = (
    Path(__file__).parents[1]
    / "app/wikipedia_opening_artifacts/yokofudori-4e-bishop.json"
)
AUDIT = Path(__file__).parents[2] / "docs/opening-wikipedia-provenance-audit.json"
COMMON = "7g7f 3c3d 2g2f 8c8d 2f2e 8d8e 6i7h 4a3b 2e2d 2c2d 2h2d 8e8f 8g8f 8b8f 2d3d 2b8h+ 7i8h P*2h 3i2h B*4e".split()
TAILS = [
    ["B*7g", "8f8h+", "7g8h", "4e3d", "8h1a+", "S*8g"],
    ["3d2d", "P*2c", "B*7g", "8f8h+", "7g8h", "2c2d", "8h1a+"],
    ["P*8g"],
    ["3d3e"],
]


def artifact():
    return json.loads(P.read_text(encoding="utf-8"))


def test_contract_legality_paths_and_tree_signature():
    d = artifact()
    assert validate_wikipedia_opening_artifact(d) == ()
    r = d["records"][0]
    assert (r["revision"], r["license"], r["retrieved_date"]) == (
        88731470,
        "CC BY-SA 4.0",
        "2026-09-08",
    )
    assert r["coverage_status"] == "partial_explicit_sequence"
    assert r["coverage"] == {
        "covered_through_ply": 26,
        "covered_through_move": "S*8g",
        "omitted_after": {
            "usi": "1a7g",
            "note": "本線終端の次に同節で明記された▲7七馬。今回の収録範囲外。",
        },
    }
    assert len(r["nodes"]) == 35
    nodes = {x["key"]: x for x in r["nodes"]}
    children = defaultdict(list)
    for x in r["nodes"]:
        b = shogi.Board(x["from_sfen"])
        m = shogi.Move.from_usi(x["usi"])
        assert m in b.legal_moves
        b.push(m)
        assert b.sfen() == x["to_sfen"]
        if x["parent_key"]:
            assert nodes[x["parent_key"]]["to_sfen"] == x["from_sfen"]
        children[x["parent_key"]].append(x)
    for siblings in children.values():
        assert (
            len({x["usi"] for x in siblings})
            == len(siblings)
            == len({x["sort_order"] for x in siblings})
        )
        assert sum(x["is_main"] for x in siblings) == 1
    assert [(x["usi"], x["sort_order"], x["is_main"]) for x in children["main-20"]] == [
        ("B*7g", 0, True),
        ("3d2d", 1, False),
        ("P*8g", 2, False),
        ("3d3e", 3, False),
    ]

    def path(x):
        out = []
        while x:
            out.append(x["usi"])
            x = nodes.get(x["parent_key"])
        return out[::-1]

    leaves = [x for x in r["nodes"] if x["key"] not in children]
    assert [path(x) for x in leaves] == [COMMON + t for t in TAILS]
    assert len(leaves) == 4
    assert max(len(path(x)) for x in leaves) == 27


def test_static_claim_idempotency_noninterference_and_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOGI_DB_PATH", str(tmp_path / "seed.db"))
    init_db()
    con = get_connection()
    try:
        seed_opening_catalog_if_empty(con)
        seed_openings_if_empty(con)
        old = dict(
            con.execute(
                "select * from opening_lines where name='横歩取り△4五角'"
            ).fetchone()
        )
        oldnodes = {
            x["move_key"]: dict(x)
            for x in con.execute(
                "select * from opening_line_moves where line_id=?", (old["id"],)
            )
        }
        others = {
            x["name"]: x["id"]
            for x in con.execute(
                "select id,name from opening_lines where name in ('横歩取り','相横歩取り')"
            )
        }
        apply_bundled_wikipedia_opening_artifacts(con)
        line = dict(
            con.execute(
                "select * from opening_lines where name='横歩取り△4五角'"
            ).fetchone()
        )
        rows = [
            dict(x)
            for x in con.execute(
                "select * from opening_line_moves where line_id=? order by id",
                (line["id"],),
            )
        ]
        by = {x["move_key"]: x for x in rows}
        assert (line["id"], line["seed_key"], line["line_key"]) == (
            old["id"],
            "sample:横歩取り△4五角",
            "wikipedia.yokofudori.bishop-4e",
        )
        assert len(rows) == 35
        for k, x in oldnodes.items():
            assert (by[k]["id"], by[k]["comment"]) == (x["id"], x["comment"])
        assert others == {
            x["name"]: x["id"]
            for x in con.execute(
                "select id,name from opening_lines where name in ('横歩取り','相横歩取り')"
            )
        }
        first = rows
        seed_openings_if_empty(con)
        apply_bundled_wikipedia_opening_artifacts(con)
        assert first == [
            dict(x)
            for x in con.execute(
                "select * from opening_line_moves where line_id=? order by id",
                (line["id"],),
            )
        ]
        assert (
            compare_canonical_to_runtime(con, artifact()["records"][0])["status"]
            == "unchanged"
        )
    finally:
        con.close()
    assert (
        compare_canonical_to_legacy(
            artifact()["records"][0], json.loads(AUDIT.read_text(encoding="utf-8"))
        )["status"]
        == "added"
    )


def test_api_catalog_and_type_routes(client):
    summary = next(
        x for x in client.get("/api/openings").json() if x["name"] == "横歩取り△4五角"
    )
    detail = client.get(f"/api/openings/{summary['id']}").json()
    assert (summary["move_count"], len(detail["moves"]), detail["opening_type"]) == (
        26,
        35,
        "相居飛車",
    )
    assert [x["tag"] for x in detail["tags"]] == ["yokofudori"]
    assert detail["source"]["source_section"] == "概要"
    types = client.get("/api/opening-types").json()
    own = next(x for x in types if x["name_ja"] == "横歩取り△4五角")
    parent = next(x for x in types if x["name_ja"] == "横歩取り")
    assert own["parent_id"] == parent["id"]
    assert any(
        x["id"] == summary["id"]
        for x in client.get(f"/api/opening-types/{own['id']}/lines").json()
    )
