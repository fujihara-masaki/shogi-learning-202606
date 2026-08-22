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


def matching_legacy(record, **overrides):
    source = {
        "revision_id": record["revision"],
        "source_title": record["source"]["title"],
        "source_section": record["source"]["section"],
        "source_type": "wikipedia",
        "retrieved_at": record["retrieved_date"],
        "source_license": record["license"],
        "canonical_url": record["source"]["url"],
        "requested_url": record["source"]["url"],
    }
    source.update(overrides.pop("source", {}))
    legacy_record = {
        "line_name": record["line_name"],
        "source": source,
        "coverage": record["coverage_status"],
        "legacy_coverage_status": "legacy display text",
        "verification": {"status": "verified"},
        "nodes": [{
            "move_key": node["key"],
            "parent_key": node["parent_key"],
            "usi": node["usi"],
            "sort_order": node["sort_order"],
            "is_main": node["is_main"],
            "variation_group": node["variation_group"],
        } for node in record["nodes"]],
    }
    legacy_record.update(overrides)
    return {"records": [legacy_record]}


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
    assert report["unverifiable"] == ["revision", "verified_section", "review", "canonical_url"]


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
                "canonical_url": record["source"]["url"],
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
                "canonical_url": record["source"]["url"],
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
                "canonical_url": record["source"]["url"],
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


@pytest.mark.parametrize(
    ("canonical_source_url", "legacy_canonical_url", "review", "changed", "unverifiable"),
    [
        (
            "https://ja.wikipedia.org/wiki/Test",
            "https://ja.wikipedia.org/wiki/Test",
            "verified", False, [],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test?oldid=1",
            "https://ja.wikipedia.org/wiki/Test",
            "verified", False, [],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test",
            "https://ja.wikipedia.org/wiki/Test#History",
            "verified", False, [],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test",
            "https://ja.wikipedia.org/wiki/Other",
            "verified", True, [],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test",
            "https://ja.wikibooks.org/wiki/Test",
            "verified", True, [],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test",
            None,
            "unavailable", False, ["review", "canonical_url"],
        ),
        (
            "https://ja.wikipedia.org/wiki/Test",
            "https://ja.wikipedia.org/wiki/Test",
            "needs_review", False, ["review"],
        ),
    ],
)
def test_legacy_canonical_url_compares_normalized_article_identity(
    canonical_source_url, legacy_canonical_url, review, changed, unverifiable
):
    record = artifact()["records"][0]
    record["source"]["url"] = canonical_source_url
    legacy = matching_legacy(
        record,
        source={
            "canonical_url": legacy_canonical_url,
            # A redirect/request URL is deliberately not part of the diff.
            "requested_url": "https://ja.wikipedia.org/wiki/Redirect_name",
        },
        verification={"status": review},
    )
    report = compare_canonical_to_legacy(record, legacy)
    assert report["status"] == ("changed" if changed else "unchanged")
    assert ("canonical_url" in report["metadata_changed"]) is changed
    assert report["unverifiable"] == unverifiable
    assert "requested_url" not in report["metadata_changed"]


@pytest.mark.parametrize(
    ("legacy_coverage", "legacy_text", "review", "metadata_changed"),
    [
        ("complete_for_cited_sequence", "different text", "verified", []),
        (
            "partial_explicit_sequence", "legacy display text", "verified",
            ["coverage_status"],
        ),
        (
            "partial_explicit_sequence", "legacy display text", "needs_review",
            ["coverage_status"],
        ),
    ],
)
def test_legacy_normalized_coverage_is_compared_without_free_text(
    legacy_coverage, legacy_text, review, metadata_changed
):
    record = artifact()["records"][0]
    legacy = matching_legacy(
        record,
        coverage=legacy_coverage,
        legacy_coverage_status=legacy_text,
        verification={"status": review},
    )
    report = compare_canonical_to_legacy(record, legacy)
    assert report["status"] == ("changed" if metadata_changed else "unchanged")
    assert report["metadata_changed"] == metadata_changed
    assert report["unverifiable"] == (["review"] if review == "needs_review" else [])


def test_legacy_name_match_ambiguity_is_order_independent_and_not_guessed():
    record = artifact()["records"][0]
    first = matching_legacy(record)["records"][0]
    first["record_id"] = "legacy-a"
    first["source"]["revision_id"] = 999
    first["nodes"][0]["usi"] = "2g2f"
    second = deepcopy(matching_legacy(record)["records"][0])
    second["record_id"] = "legacy-b"
    second["source"]["source_title"] = "Different source"
    second["nodes"] = []

    reports = [
        compare_canonical_to_legacy(record, {"records": candidates})
        for candidates in ([first, second], [second, first])
    ]
    assert reports[0] == reports[1]
    assert reports[0] == {
        "line_key": record["line_key"],
        "status": "ambiguous",
        "metadata_changed": [],
        "nodes": [],
        "unverifiable": ["legacy_record_match"],
    }


def test_legacy_name_match_zero_one_and_multiple_canonical_keys():
    record = artifact()["records"][0]
    assert compare_canonical_to_legacy(record, {"records": []}) == {
        "line_key": record["line_key"], "status": "added", "unverifiable": [],
    }
    assert compare_canonical_to_legacy(
        record, matching_legacy(record)
    )["status"] == "unchanged"

    duplicate_legacy = matching_legacy(record)["records"] * 2
    other_canonical = deepcopy(record)
    other_canonical["line_key"] = "other-line-key"
    for canonical in (record, other_canonical):
        report = compare_canonical_to_legacy(
            canonical, {"records": duplicate_legacy}
        )
        assert report["line_key"] == canonical["line_key"]
        assert report["status"] == "ambiguous"
        assert report["nodes"] == []
        assert report["metadata_changed"] == []
        assert report["unverifiable"] == ["legacy_record_match"]


@pytest.mark.parametrize("identical_payload", [False, True])
def test_duplicate_legacy_move_keys_are_ambiguous_and_order_independent(
    identical_payload
):
    record = artifact()["records"][0]
    legacy = matching_legacy(record)
    duplicate_a = deepcopy(legacy["records"][0]["nodes"][0])
    duplicate_b = deepcopy(duplicate_a)
    if not identical_payload:
        duplicate_b.update(
            usi="2g2f",
            parent_key="different-parent",
            provenance={
                "provenance_class": "diagram_reconstruction",
                "source_section": "Different section",
                "evidence_note": "Different evidence",
                "review_status": "needs_review",
            },
        )

    reports = []
    for nodes in ([duplicate_a, duplicate_b], [duplicate_b, duplicate_a]):
        snapshot = deepcopy(legacy)
        snapshot["records"][0]["nodes"] = nodes
        reports.append(compare_canonical_to_legacy(record, snapshot))

    assert reports[0] == reports[1]
    assert reports[0] == {
        "line_key": record["line_key"],
        "status": "ambiguous",
        "metadata_changed": [],
        "nodes": [],
        "unverifiable": ["legacy_move_key"],
    }


def test_multiple_duplicate_legacy_move_keys_and_missing_key_are_not_guessed():
    record = artifact()["records"][0]
    base = matching_legacy(record)
    node_a = deepcopy(base["records"][0]["nodes"][0])
    node_b = deepcopy(base["records"][0]["nodes"][1])
    for nodes in (
        [node_a, deepcopy(node_a), node_b, deepcopy(node_b)],
        [{"usi": "7g7f"}],
    ):
        legacy = deepcopy(base)
        legacy["records"][0]["nodes"] = nodes
        report = compare_canonical_to_legacy(record, legacy)
        assert report["status"] == "ambiguous"
        assert report["metadata_changed"] == []
        assert report["nodes"] == []
        assert report["unverifiable"] == ["legacy_move_key"]


@pytest.mark.parametrize(
    (
        "provenance_class", "legacy_section", "legacy_evidence", "review_status",
        "canonical_provenance", "expected_fields", "expected_unverifiable",
    ),
    [
        (
            "explicit_sequence", "節", "evidence a", "verified", "A", [], [],
        ),
        (
            "explicit_sequence", "節", "evidence a", "verified", "B",
            ["provenance"], [],
        ),
        (
            "explicit_sequence", "different", "evidence a", "verified", "A",
            ["source_section"], [],
        ),
        (
            "explicit_sequence", "節", "different evidence", "verified", "A",
            ["evidence_note"], [],
        ),
        (
            "explicit_sequence", "different", "different evidence", "verified", "B",
            ["provenance", "source_section", "evidence_note"], [],
        ),
        (
            "explicit_sequence", "節", "evidence a", "needs_review", "A", [],
            ["review"],
        ),
        (
            "explicit_sequence", "節", "evidence a", "unavailable", "B",
            ["provenance"], ["review"],
        ),
        (
            None, "節", "evidence a", "verified", "A", [], ["provenance"],
        ),
        (
            "explicit_sequence", None, "evidence a", "verified", "A", [],
            ["source_section"],
        ),
    ],
)
def test_legacy_node_provenance_comparison_is_explicit_and_deterministic(
    provenance_class, legacy_section, legacy_evidence, review_status,
    canonical_provenance, expected_fields, expected_unverifiable,
):
    record = artifact()["records"][0]
    record["nodes"][0]["provenance"] = canonical_provenance
    legacy = matching_legacy(record)
    legacy["records"][0]["nodes"][0]["provenance"] = {
        "provenance_class": provenance_class,
        "source_section": legacy_section,
        "evidence_note": legacy_evidence,
        "review_status": review_status,
    }
    report = compare_canonical_to_legacy(record, legacy)
    result = next(item for item in report["nodes"] if item["key"] == "a")
    assert result["status"] == ("changed" if expected_fields else "unchanged")
    assert result["fields"] == expected_fields
    if expected_unverifiable:
        assert result["unverifiable"] == expected_unverifiable
    else:
        assert "unverifiable" not in result


def test_mixed_boundary_change_is_detected_without_structural_change():
    record = artifact()["records"][0]
    record["provenance"] = "M"
    record["coverage_status"] = "mixed"
    record["nodes"][1]["provenance"] = "B"
    legacy = matching_legacy(record)
    legacy["records"][0]["nodes"][1]["provenance"] = {
        "provenance_class": "explicit_sequence",
        "source_section": record["nodes"][1]["source_section"],
        "evidence_note": record["nodes"][1]["evidence_note"],
        "review_status": "verified",
    }
    report = compare_canonical_to_legacy(record, legacy)
    changed = next(item for item in report["nodes"] if item["key"] == "b")
    assert changed == {"key": "b", "status": "changed", "fields": ["provenance"]}


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


@pytest.mark.parametrize("record_order", [("line-a", "line-b"), ("line-b", "line-a")])
def test_duplicate_canonical_display_names_never_claim_legacy_row_by_order(
    client, record_order
):
    conn = get_connection()
    try:
        legacy_line_id = int(conn.execute(
            """INSERT INTO opening_lines
               (name, opening_type, initial_sfen, moves, comments)
               VALUES ('Same name', 'legacy', ?, '[]', '["legacy line comment"]')""",
            (shogi.STARTING_SFEN,),
        ).lastrowid)
        first = artifact()["records"][0]["nodes"][0]
        legacy_move_id = int(conn.execute(
            """INSERT INTO opening_line_moves
               (line_id, ply, usi, from_sfen, to_sfen, comment, variation_group,
                parent_move_id, sort_order, move_key, is_main)
               VALUES (?, 1, ?, ?, ?, 'legacy move comment', 'main', NULL, 0, 'pending', 1)""",
            (legacy_line_id, first["usi"], first["from_sfen"], first["to_sfen"]),
        ).lastrowid)
        conn.execute(
            "UPDATE opening_line_moves SET move_key=? WHERE id=?",
            (f"legacy-{legacy_move_id}", legacy_move_id),
        )
        legacy_before = dict(conn.execute(
            "SELECT * FROM opening_lines WHERE id=?", (legacy_line_id,)
        ).fetchone())
        legacy_move_before = dict(conn.execute(
            "SELECT * FROM opening_line_moves WHERE id=?", (legacy_move_id,)
        ).fetchone())

        records = []
        for line_key in record_order:
            record = deepcopy(artifact()["records"][0])
            record["record_key"] = f"record-{line_key}"
            record["line_key"] = line_key
            record["line_name"] = "Same name"
            records.append(record)
        data = artifact()
        data["records"] = records
        applied = apply_wikipedia_opening_artifact(conn, data)

        assert dict(conn.execute(
            "SELECT * FROM opening_lines WHERE id=?", (legacy_line_id,)
        ).fetchone()) == legacy_before
        assert dict(conn.execute(
            "SELECT * FROM opening_line_moves WHERE id=?", (legacy_move_id,)
        ).fetchone()) == legacy_move_before
        canonical = conn.execute(
            "SELECT id, line_key FROM opening_lines WHERE line_key IN ('line-a', 'line-b')"
        ).fetchall()
        assert {row["line_key"] for row in canonical} == {"line-a", "line-b"}
        assert set(applied) == {row["id"] for row in canonical}
        assert legacy_line_id not in applied
        canonical_comments = conn.execute(
            """SELECT comment FROM opening_line_moves
               WHERE line_id IN (?, ?) ORDER BY line_id, id""",
            tuple(row["id"] for row in canonical),
        ).fetchall()
        assert canonical_comments
        assert all(row["comment"] != "legacy move comment" for row in canonical_comments)
    finally:
        conn.close()


def test_single_canonical_display_name_still_claims_legacy_line_and_comments(client):
    conn = get_connection()
    try:
        record = artifact()["records"][0]
        line_id = int(conn.execute(
            """INSERT INTO opening_lines
               (name, opening_type, initial_sfen, moves, comments)
               VALUES (?, 'legacy', ?, '[]', '["legacy comment"]')""",
            (record["line_name"], record["initial_sfen"]),
        ).lastrowid)
        root = record["nodes"][0]
        move_id = int(conn.execute(
            """INSERT INTO opening_line_moves
               (line_id, ply, usi, from_sfen, to_sfen, comment, variation_group,
                parent_move_id, sort_order, move_key, is_main)
               VALUES (?, 1, ?, ?, ?, 'retained comment', 'main', NULL, 0, 'pending', 1)""",
            (line_id, root["usi"], root["from_sfen"], root["to_sfen"]),
        ).lastrowid)
        conn.execute(
            "UPDATE opening_line_moves SET move_key=? WHERE id=?",
            (f"legacy-{move_id}", move_id),
        )

        assert apply_wikipedia_opening_artifact(conn, artifact()) == [line_id]
        claimed = conn.execute(
            "SELECT id, move_key, comment FROM opening_line_moves WHERE id=?", (move_id,)
        ).fetchone()
        assert dict(claimed) == {
            "id": move_id, "move_key": "a", "comment": "retained comment",
        }
    finally:
        conn.close()


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
