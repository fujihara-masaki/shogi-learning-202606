from copy import deepcopy
import json
import sqlite3

import pytest
import shogi

from app.database import get_connection
from app.wikipedia_opening_importer import (
    ArtifactImportError, apply_wikipedia_opening_artifact,
    compare_canonical_to_legacy, compare_canonical_to_runtime, _ordered_nodes,
)


def node(key, parent, usi, before, order=0, main=True, group="main"):
    board = shogi.Board(before); board.push_usi(usi)
    return {"key": key, "parent_key": parent, "usi": usi, "sort_order": order,
            "is_main": main, "variation_group": group, "from_sfen": before,
            "to_sfen": board.sfen(), "provenance": "A", "source_section": "節",
            "evidence_note": f"evidence {key}"}


def artifact(branched=False):
    start = shogi.STARTING_SFEN
    a = node("a", None, "7g7f", start)
    b = node("b", "a", "3c3d", a["to_sfen"])
    c = node("c", "b", "2g2f", b["to_sfen"])
    nodes = [a, b, c]
    if branched:
        nodes.append(node("d", "b", "6g6f", b["to_sfen"], 1, False, "alternative"))
    record = {"record_type": "move_line", "record_key": "record", "line_key": "stable-line",
              "line_name": "Test line", "source": {"url": "https://ja.wikipedia.org/wiki/Test", "title": "Test", "section": "節"},
              "license": "CC BY-SA 4.0", "retrieved_date": "2026-08-20", "revision": 1,
              "provenance": "A", "coverage_status": "complete_for_cited_sequence",
              "initial_sfen": start, "coverage": {"covered_through_ply": 3, "covered_through_move": "2g2f", "omitted_after": None},
              "source_note": "opaque note", "nodes": nodes}
    return {"artifact_version": 1, "review": {"review_status": "reviewed", "reviewed_by": "reviewer", "reviewed_on": "2026-08-20", "legality_checks": {"backend_python_shogi": "passed", "frontend_tsshogi": "passed"}}, "records": [record]}


def rows(conn, line_id):
    result = conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (line_id,)).fetchall()
    return {row["move_key"]: row for row in result}


def test_linear_and_branched_projection_is_exact_and_input_order_independent(client):
    conn = get_connection()
    try:
        data = artifact(True); data["records"][0]["nodes"].reverse()
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        actual = rows(conn, line_id)
        expected = {item["key"]: item for item in data["records"][0]["nodes"]}
        assert set(actual) == set(expected)
        for key, item in expected.items():
            assert (actual[key]["usi"], actual[key]["sort_order"], actual[key]["is_main"], actual[key]["variation_group"], actual[key]["from_sfen"], actual[key]["to_sfen"]) == (item["usi"], item["sort_order"], item["is_main"], item["variation_group"], item["from_sfen"], item["to_sfen"])
            parent = actual[key]["parent_move_id"]
            assert parent == (actual[item["parent_key"]]["id"] if item["parent_key"] else None)
        assert compare_canonical_to_runtime(conn, data["records"][0])["status"] == "unchanged"
    finally: conn.close()


def test_reapply_add_remove_reparent_and_reorder_preserve_stable_ids(client):
    conn = get_connection()
    try:
        data = artifact(True); line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        original = {key: row["id"] for key, row in rows(conn, line_id).items()}
        assert apply_wikipedia_opening_artifact(conn, data) == [line_id]
        assert {key: row["id"] for key, row in rows(conn, line_id).items()} == original
        changed = deepcopy(data); record = changed["records"][0]
        # Remove d, add e, and move c to root sibling. Regenerate legal SFEN.
        record["nodes"] = [n for n in record["nodes"] if n["key"] != "d"]
        c = next(n for n in record["nodes"] if n["key"] == "c")
        replacement = node("c", None, "2g2f", shogi.STARTING_SFEN, 1, False)
        c.update(replacement)
        record["nodes"].append(node("e", "b", "6g6f", next(n for n in record["nodes"] if n["key"] == "b")["to_sfen"], 0, True))
        record["coverage"].update(covered_through_move="6g6f")
        # b no longer has c, e is sole child; roots a/c retain exactly one main.
        apply_wikipedia_opening_artifact(conn, changed)
        after = rows(conn, line_id)
        assert "d" not in after and "e" in after
        assert after["a"]["id"] == original["a"] and after["b"]["id"] == original["b"] and after["c"]["id"] == original["c"]
        assert after["c"]["parent_move_id"] is None
    finally: conn.close()


def test_validation_rejection_and_mid_apply_failure_leave_no_partial_write(client, monkeypatch):
    conn = get_connection()
    try:
        baseline = conn.total_changes
        for review, result in (("pending", "passed"), ("reviewed", "pending"), ("reviewed", "failed")):
            bad = artifact(); bad["review"] = ({"review_status": "pending", "legality_checks": {"backend_python_shogi": result, "frontend_tsshogi": "passed"}} if review == "pending" else {**bad["review"], "legality_checks": {"backend_python_shogi": result, "frontend_tsshogi": "passed"}})
            with pytest.raises(ArtifactImportError): apply_wikipedia_opening_artifact(conn, bad)
        assert conn.total_changes == baseline
        import app.wikipedia_opening_importer as module
        monkeypatch.setattr(module, "upsert_opening_move_nodes", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError): apply_wikipedia_opening_artifact(conn, artifact())
        assert conn.execute("SELECT 1 FROM opening_lines WHERE line_key='stable-line'").fetchone() is None
    finally: conn.close()


def test_other_line_untouched_catalog_ignored_and_coverage_boundary_is_explicit(client):
    conn = get_connection()
    try:
        other = conn.execute("SELECT * FROM opening_lines ORDER BY id LIMIT 1").fetchone()
        other_moves = [tuple(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (other["id"],))]
        data = artifact(); catalog = {"record_type": "catalog_name_only", "record_key": "catalog", "line_key": "catalog-only", "catalog_name": "Catalog", "source": data["records"][0]["source"], "license": "CC BY-SA 4.0", "retrieved_date": "2026-08-20", "revision": 1, "provenance": "C", "coverage_status": "name_only", "source_note": "name", "evidence_note": "listed"}
        data["records"].append(catalog); line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        assert conn.execute("SELECT 1 FROM opening_lines WHERE line_key='catalog-only'").fetchone() is None
        assert dict(conn.execute("SELECT * FROM opening_lines WHERE id=?", (other["id"],)).fetchone()) == dict(other)
        assert [tuple(row) for row in conn.execute("SELECT * FROM opening_line_moves WHERE line_id=?", (other["id"],))] == other_moves
        line = conn.execute("SELECT * FROM opening_lines WHERE id=?", (line_id,)).fetchone()
        assert line["coverage_status"] == ""  # legacy free text is not normalized canonical coverage
        report = compare_canonical_to_runtime(conn, data["records"][0])
        assert "coverage_status" in report["canonical_only"]
    finally: conn.close()


def test_legacy_diff_reports_changes_and_unknowns_without_inference():
    data = artifact(); record = data["records"][0]
    legacy = {"records": [{"line_name": "Test line", "source": {"revision_id": None, "source_section": None}, "verification": {"status": "unavailable"}, "nodes": [{"move_key": "a", "parent_key": None, "usi": "7g7f", "sort_order": 9, "is_main": True, "variation_group": "main"}, {"move_key": "old", "parent_key": "a", "usi": "3c3d", "sort_order": 0, "is_main": True, "variation_group": "main"}]}]}
    report = compare_canonical_to_legacy(record, legacy)
    by_key = {item["key"]: item for item in report["nodes"]}
    assert by_key["a"] == {"key": "a", "status": "changed", "fields": ["sort_order"]}
    assert by_key["old"]["status"] == "removed" and by_key["b"]["status"] == "added"
    assert report["unverifiable"] == ["revision", "verified_section", "review"]


def test_legacy_needs_review_is_not_treated_as_verified():
    record = artifact()["records"][0]
    legacy = {
        "records": [{
            "line_name": record["line_name"],
            "source": {
                "revision_id": record["revision"],
                "source_title": record["source"]["title"],
                "source_section": record["source"]["section"],
                "source_type": "wikipedia",
                "retrieved_at": record["retrieved_date"],
                "source_license": record["license"],
            },
            "verification": {"status": "needs_review"},
            "nodes": [{
                "move_key": node["key"],
                "parent_key": node["parent_key"],
                "usi": node["usi"],
                "sort_order": node["sort_order"],
                "is_main": node["is_main"],
                "variation_group": node["variation_group"],
            } for node in record["nodes"]],
        }]
    }
    report = compare_canonical_to_legacy(record, legacy)
    assert report["unverifiable"] == ["review"]
    assert report["metadata_changed"] == []


@pytest.mark.parametrize(
    ("revision_id", "status", "metadata_changed", "revision_unverifiable"),
    [
        (1, "unchanged", [], False),
        (999, "changed", ["revision"], False),
        (None, "unchanged", [], True),
        ("unavailable", "unchanged", [], True),
    ],
)
def test_legacy_revision_is_compared_only_when_known(
    revision_id, status, metadata_changed, revision_unverifiable
):
    record = artifact()["records"][0]
    legacy = {
        "records": [{
            "line_name": record["line_name"],
            "source": {
                "revision_id": revision_id,
                "source_title": record["source"]["title"],
                "source_section": record["source"]["section"],
                "source_type": "wikipedia",
                "retrieved_at": record["retrieved_date"],
                "source_license": record["license"],
            },
            "verification": {"status": "verified"},
            "nodes": [{
                "move_key": node["key"],
                "parent_key": node["parent_key"],
                "usi": node["usi"],
                "sort_order": node["sort_order"],
                "is_main": node["is_main"],
                "variation_group": node["variation_group"],
            } for node in record["nodes"]],
        }]
    }
    report = compare_canonical_to_legacy(record, legacy)
    assert report["status"] == status
    assert report["metadata_changed"] == metadata_changed
    assert ("revision" in report["unverifiable"]) is revision_unverifiable


@pytest.mark.parametrize(
    ("source_type", "retrieved_at", "review", "metadata_changed"),
    [
        ("wikipedia", "2026-08-20", "verified", []),
        ("wikibooks", "2026-08-20", "verified", ["source_type"]),
        ("wikipedia", "2026-08-19", "verified", ["retrieved_at"]),
        (
            "wikibooks", "2026-08-19", "verified",
            ["source_type", "retrieved_at"],
        ),
        (
            "wikibooks", "2026-08-19", "needs_review",
            ["source_type", "retrieved_at"],
        ),
    ],
)
def test_legacy_source_type_and_retrieved_at_are_compared_when_known(
    source_type, retrieved_at, review, metadata_changed
):
    record = artifact()["records"][0]
    legacy = {
        "records": [{
            "line_name": record["line_name"],
            "source": {
                "revision_id": record["revision"],
                "source_title": record["source"]["title"],
                "source_section": record["source"]["section"],
                "source_type": source_type,
                "retrieved_at": retrieved_at,
                "source_license": record["license"],
            },
            "verification": {"status": review},
            "nodes": [{
                "move_key": node["key"],
                "parent_key": node["parent_key"],
                "usi": node["usi"],
                "sort_order": node["sort_order"],
                "is_main": node["is_main"],
                "variation_group": node["variation_group"],
            } for node in record["nodes"]],
        }]
    }
    report = compare_canonical_to_legacy(record, legacy)
    assert report["status"] == ("changed" if metadata_changed else "unchanged")
    assert report["metadata_changed"] == metadata_changed
    assert report["unverifiable"] == (["review"] if review == "needs_review" else [])


def test_static_seed_does_not_overwrite_claimed_canonical_line_or_duplicate_after_rename(
    client, monkeypatch
):
    from app import seed

    bundled = {
        "name": "Test line", "opening_type": "test", "description": "bundled",
        "tag": "bundled", "moves": ["7g7f", "3c3d", "2g2f"],
        "comments": ["keep a", "keep b", "keep c"],
    }
    monkeypatch.setattr(seed, "SAMPLE_OPENING_LINES", [bundled])
    conn = get_connection()
    try:
        seed.seed_openings_if_empty(conn)
        conn.commit()
        line_count = conn.execute("SELECT COUNT(*) AS n FROM opening_lines").fetchone()["n"]
        original = conn.execute("SELECT * FROM opening_lines WHERE name='Test line'").fetchone()
        data = artifact(True)
        key_map = {"a": "main-1", "b": "main-2", "c": "main-3", "d": "branch"}
        for item in data["records"][0]["nodes"]:
            item["key"] = key_map[item["key"]]
            if item["parent_key"] is not None:
                item["parent_key"] = key_map[item["parent_key"]]
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        assert line_id == original["id"]
        conn.commit()
        canonical_rows = rows(conn, line_id)
        canonical_ids = {
            key: (row["id"], row["parent_move_id"])
            for key, row in canonical_rows.items()
        }
        # Canonical has no comment field: comments on retained stable keys stay
        # runtime-owned rather than being silently erased.
        assert [canonical_rows[key]["comment"] for key in ("main-1", "main-2", "main-3")] == [
            "keep a", "keep b", "keep c"
        ]

        renamed = deepcopy(data)
        renamed["records"][0]["line_name"] = "Canonical renamed line"
        apply_wikipedia_opening_artifact(conn, renamed)
        conn.commit()
        seed.seed_openings_if_empty(conn)

        assert conn.execute("SELECT COUNT(*) AS n FROM opening_lines").fetchone()["n"] == line_count
        assert conn.execute("SELECT 1 FROM opening_lines WHERE name='Test line'").fetchone() is None
        line = conn.execute("SELECT * FROM opening_lines WHERE id=?", (line_id,)).fetchone()
        assert line["name"] == "Canonical renamed line"
        assert line["line_key"] == "stable-line"
        assert line["seed_key"] == "sample:Test line"
        after = rows(conn, line_id)
        assert set(after) == set(canonical_rows)
        assert {key: (row["id"], row["parent_move_id"]) for key, row in after.items()} == canonical_ids
    finally:
        conn.close()


def test_ordered_nodes_handles_more_than_one_thousand_deep_nodes_iteratively():
    nodes = []
    for index in range(1501):
        nodes.append({
            "key": f"n{index}",
            "parent_key": None if index == 0 else f"n{index - 1}",
            "sort_order": 0,
        })
    ordered = _ordered_nodes({"nodes": list(reversed(nodes))})
    assert len(ordered) == 1501
    assert ordered[0]["key"] == "n0" and ordered[0]["ply"] == 1
    assert ordered[-1]["key"] == "n1500" and ordered[-1]["ply"] == 1501


@pytest.mark.parametrize(
    ("url", "expected_type"),
    [
        ("https://ja.wikipedia.org/wiki/Test", "wikipedia"),
        ("https://ja.wikibooks.org/wiki/Test", "wikibooks"),
    ],
)
def test_source_host_projects_to_runtime_source_type_and_is_compared(
    client, url, expected_type
):
    conn = get_connection()
    try:
        data = artifact()
        record = data["records"][0]
        record["source"]["url"] = url
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        line = conn.execute(
            "SELECT source_url, source_type FROM opening_lines WHERE id=?", (line_id,)
        ).fetchone()
        assert dict(line) == {"source_url": url, "source_type": expected_type}
        assert compare_canonical_to_runtime(conn, record)["status"] == "unchanged"

        conn.execute(
            "UPDATE opening_lines SET source_type='incorrect' WHERE id=?", (line_id,)
        )
        report = compare_canonical_to_runtime(conn, record)
        assert report["status"] == "changed"
        assert report["metadata_changed"] == ["source_type"]
    finally:
        conn.close()


def test_runtime_comparison_includes_persisted_source_license(client):
    conn = get_connection()
    try:
        data = artifact()
        record = data["records"][0]
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        assert compare_canonical_to_runtime(conn, record)["status"] == "unchanged"

        conn.execute(
            "UPDATE opening_lines SET source_license='incorrect' WHERE id=?", (line_id,)
        )
        report = compare_canonical_to_runtime(conn, record)
        assert report["status"] == "changed"
        assert report["metadata_changed"] == ["source_license"]
    finally:
        conn.close()


def test_legacy_move_claim_preserves_main_and_branch_comments(client):
    conn = get_connection()
    try:
        data = artifact(True)
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        before = rows(conn, line_id)
        comments = {"a": "legacy main a", "b": "legacy main b", "c": "legacy main c", "d": "legacy branch d"}
        for key, row in before.items():
            conn.execute(
                "UPDATE opening_line_moves SET move_key=?, comment=? WHERE id=?",
                (f"legacy-{row['id']}", comments[key], row["id"]),
            )

        apply_wikipedia_opening_artifact(conn, data)
        after = rows(conn, line_id)
        assert {key: row["id"] for key, row in after.items()} == {
            key: row["id"] for key, row in before.items()
        }
        assert {key: row["move_key"] for key, row in after.items()} == {
            key: key for key in comments
        }
        assert {key: row["comment"] for key, row in after.items()} == comments
        line_comments = json.loads(conn.execute(
            "SELECT comments FROM opening_lines WHERE id=?", (line_id,)
        ).fetchone()["comments"])
        assert line_comments == [comments["a"], comments["b"], comments["c"]]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("corrupt", "report_section", "detail"),
    [
        ("node_ply", "nodes", "ply"),
        ("position_sfen", "positions", None),
        ("position_missing", "positions", None),
        ("position_ply", "positions", None),
        ("position_extra", "positions", None),
        ("line_moves", "moves", None),
    ],
)
def test_runtime_comparison_detects_complete_persisted_projection(
    client, corrupt, report_section, detail
):
    conn = get_connection()
    try:
        data = artifact()
        record = data["records"][0]
        line_id = apply_wikipedia_opening_artifact(conn, data)[0]
        assert compare_canonical_to_runtime(conn, record)["status"] == "unchanged"

        if corrupt == "node_ply":
            conn.execute(
                "UPDATE opening_line_moves SET ply=99 WHERE line_id=? AND move_key='b'",
                (line_id,),
            )
        elif corrupt == "position_sfen":
            conn.execute(
                "UPDATE opening_positions SET sfen='wrong' WHERE line_id=? AND ply=1",
                (line_id,),
            )
        elif corrupt == "position_missing":
            conn.execute(
                "DELETE FROM opening_positions WHERE line_id=? AND ply=1", (line_id,)
            )
        elif corrupt == "position_ply":
            conn.execute(
                "UPDATE opening_positions SET ply=99 WHERE line_id=? AND ply=1", (line_id,)
            )
        elif corrupt == "position_extra":
            conn.execute(
                "INSERT INTO opening_positions(line_id, ply, sfen) VALUES (?, 99, 'extra')",
                (line_id,),
            )
        else:
            conn.execute(
                "UPDATE opening_lines SET moves='[]' WHERE id=?", (line_id,)
            )

        report = compare_canonical_to_runtime(conn, record)
        assert report["status"] == "changed"
        if report_section == "nodes":
            changed = next(node for node in report["nodes"] if node["key"] == "b")
            assert detail in changed["fields"]
        else:
            assert report[report_section]["status"] == "changed"
            assert report[report_section]["actual"] != report[report_section]["expected"]
    finally:
        conn.close()
