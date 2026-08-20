from copy import deepcopy

import shogi

from app.wikipedia_opening_validator import validate_wikipedia_opening_artifact


def _node(key, parent, usi, from_sfen, *, order=0, main=True, provenance="A", segment=None):
    board = shogi.Board(from_sfen)
    board.push_usi(usi)
    node = {"key": key, "parent_key": parent, "usi": usi, "sort_order": order,
            "is_main": main, "from_sfen": from_sfen, "to_sfen": board.sfen(),
            "provenance": provenance}
    if segment is not None:
        node["segment_key"] = segment
    return node


def _artifact(*, branched=False, mixed=False):
    start = shogi.STARTING_SFEN
    n1 = _node("n1", None, "7g7f", start)
    n2 = _node("n2", "n1", "3c3d", n1["to_sfen"])
    n3 = _node("n3", "n2", "2g2f", n2["to_sfen"])
    nodes = [n1, n2, n3]
    if branched:
        nodes.append(_node("branch", "n2", "6g6f", n2["to_sfen"], order=1, main=False))
    record = {
        "record_type": "move_line",
        "record_key": "wikipedia.test", "line_key": "test-line",
        "source": {"url": "https://ja.wikipedia.org/wiki/Test", "title": "Test", "section": "Opening"},
        "license": "CC BY-SA 4.0", "retrieved_date": "2026-08-20", "revision": "12345",
        "provenance": "A", "initial_sfen": start,
        "coverage": {"covered_through_ply": 3, "covered_through_move": "2g2f", "omitted_after": None},
        "source_note": "この表示文は判定されない", "nodes": nodes,
    }
    if mixed:
        record["provenance"] = "M"
        for node in nodes:
            if node["key"] == "n1":
                node.update(provenance="A", segment_key="explicit")
            else:
                node.update(provenance="B", segment_key="diagram")
        record["segments"] = [
            {"key": "explicit", "provenance": "A", "start_node_key": "n1", "end_node_key": "n1", "source_section": "Opening", "evidence_note": "explicit moves"},
            {"key": "diagram", "provenance": "B", "start_node_key": "n2", "end_node_key": "n3", "source_section": "Diagram 1", "evidence_note": "reconstructed from diagram"},
        ]
    return {"artifact_version": 1, "records": [record]}


def _codes(artifact):
    return [error.code for error in validate_wikipedia_opening_artifact(artifact)]


def test_valid_linear_branch_and_mixed_artifacts_pass():
    assert validate_wikipedia_opening_artifact(_artifact()) == ()
    assert validate_wikipedia_opening_artifact(_artifact(branched=True)) == ()
    assert validate_wikipedia_opening_artifact(_artifact(mixed=True)) == ()


def test_multiple_root_siblings_are_a_valid_initial_position_choice_set():
    artifact = _artifact()
    record = artifact["records"][0]
    alternative = _node("root-alt", None, "2g2f", record["initial_sfen"], order=1, main=False)
    record["nodes"].append(alternative)
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_catalog_c_is_name_only_and_cannot_contain_nodes():
    move_record = _artifact()["records"][0]
    catalog = {key: move_record[key] for key in ("record_key", "line_key", "source", "license", "retrieved_date", "revision")}
    catalog.update(record_type="catalog_name_only", provenance="C")
    assert validate_wikipedia_opening_artifact({"artifact_version": 1, "records": [catalog]}) == ()
    catalog["nodes"] = move_record["nodes"]
    assert _codes({"artifact_version": 1, "records": [catalog]}) == ["schema"]
    move_record["provenance"] = "C"
    assert _codes({"artifact_version": 1, "records": [move_record]}) == ["schema"]


def test_schema_and_provenance_enum_violations_are_stable():
    artifact = _artifact()
    del artifact["records"][0]["source"]["title"]
    first = validate_wikipedia_opening_artifact(artifact)
    assert first == validate_wikipedia_opening_artifact(deepcopy(artifact))
    assert first[0].code == "schema" and first[0].path == "/records/0/source"

    artifact = _artifact()
    artifact["records"][0]["provenance"] = "D"
    assert _codes(artifact) == ["schema"]


def test_invalid_usi_and_illegal_move_are_rejected():
    artifact = _artifact()
    artifact["records"][0]["nodes"][0]["usi"] = "not-a-move"
    assert _codes(artifact) == ["schema"]
    artifact = _artifact()
    artifact["records"][0]["nodes"][0]["usi"] = "7g7e"
    assert "illegal_move" in _codes(artifact)


def test_invalid_initial_sfen_and_replay_mismatches_are_rejected():
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = "not sfen"
    assert "invalid_initial_sfen" in _codes(artifact)
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["from_sfen"] = shogi.STARTING_SFEN
    assert "parent_child_sfen" in _codes(artifact)
    artifact = _artifact()
    artifact["records"][0]["nodes"][0]["to_sfen"] = shogi.STARTING_SFEN
    assert "to_sfen_mismatch" in _codes(artifact)


def test_orphan_cycle_and_root_failures_are_rejected():
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["parent_key"] = "missing"
    assert "orphan_parent" in _codes(artifact)
    artifact = _artifact()
    nodes = artifact["records"][0]["nodes"]
    nodes[0]["parent_key"] = "n3"
    assert {"cycle", "root_count"} <= set(_codes(artifact))


def test_sibling_uniqueness_and_semantic_main_are_rejected():
    for field, value, code in [
        ("usi", "2g2f", "duplicate_sibling_usi"),
        ("sort_order", 0, "duplicate_sibling_sort_order"),
    ]:
        artifact = _artifact(branched=True)
        artifact["records"][0]["nodes"][3][field] = value
        assert code in _codes(artifact)
    artifact = _artifact(branched=True)
    artifact["records"][0]["nodes"][2]["is_main"] = False
    assert "semantic_main_count" in _codes(artifact)
    artifact = _artifact(branched=True)
    artifact["records"][0]["nodes"][3]["is_main"] = True
    assert "semantic_main_count" in _codes(artifact)


def test_coverage_boundaries_and_omission_metadata_are_rejected():
    artifact = _artifact()
    artifact["records"][0]["coverage"]["covered_through_ply"] = 2
    artifact["records"][0]["coverage"]["covered_through_move"] = "3c3d"
    assert {"coverage_ply", "coverage_move"} <= set(_codes(artifact))
    artifact = _artifact()
    artifact["records"][0]["coverage"]["omitted_after"] = {"usi": "8c8d"}
    assert validate_wikipedia_opening_artifact(artifact) == ()
    artifact["records"][0]["coverage"]["omitted_after"] = {"usi": "7g7f"}
    assert "illegal_omitted_move" in _codes(artifact)
    artifact["records"][0]["coverage"]["omitted_after"] = True
    assert _codes(artifact) == ["schema"]


def test_invalid_mixed_segments_are_rejected():
    artifact = _artifact(mixed=True)
    artifact["records"][0]["nodes"][1]["segment_key"] = "missing"
    assert "unknown_segment" in _codes(artifact)
    artifact = _artifact(mixed=True)
    artifact["records"][0]["segments"][1]["start_node_key"] = "n3"
    assert "segment_start" in _codes(artifact)
    artifact = _artifact(mixed=True)
    del artifact["records"][0]["segments"][0]["evidence_note"]
    assert _codes(artifact) == ["schema"]


def test_mixed_requires_both_a_and_b_and_forbids_c():
    artifact = _artifact(mixed=True)
    for segment in artifact["records"][0]["segments"]:
        segment["provenance"] = "B"
    for node in artifact["records"][0]["nodes"]:
        node["provenance"] = "B"
    assert "mixed_provenance_set" in _codes(artifact)
    artifact = _artifact(mixed=True)
    for segment in artifact["records"][0]["segments"]:
        segment["provenance"] = "A"
    for node in artifact["records"][0]["nodes"]:
        node["provenance"] = "A"
    assert "mixed_provenance_set" in _codes(artifact)
    artifact = _artifact(mixed=True)
    artifact["records"][0]["segments"][0]["provenance"] = "C"
    assert _codes(artifact) == ["schema"]


def test_segment_with_multiple_structural_ends_is_rejected():
    artifact = _artifact(branched=True, mixed=True)
    # The B segment branches to n3 and branch, so a singular end_node_key cannot
    # truthfully describe it. Split it into linear segments instead.
    assert "segment_end" in _codes(artifact)


def test_stable_record_and_node_keys_are_unique():
    artifact = _artifact()
    artifact["records"].append(deepcopy(artifact["records"][0]))
    assert {"duplicate_record_key", "duplicate_line_key"} <= set(_codes(artifact))
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["key"] = "n1"
    assert "duplicate_node_key" in _codes(artifact)


def test_free_text_changes_cannot_change_diagnostics():
    artifact = _artifact()
    artifact["records"][0]["source_note"] = "収録予定・未収録・収録候補"
    artifact["records"][0]["nodes"][0]["evidence_note"] = "否定表現でも棋譜aliasでもない"
    assert validate_wikipedia_opening_artifact(artifact) == ()
    artifact["records"][0]["source_note"] = "完全に逆の自然言語"
    artifact["records"][0]["nodes"][0]["evidence_note"] = "▲７六歩"
    assert validate_wikipedia_opening_artifact(artifact) == ()
