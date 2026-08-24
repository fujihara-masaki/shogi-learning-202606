from copy import deepcopy
import json

import jsonschema
import pytest
import shogi

from app.wikipedia_opening_validator import SCHEMA_PATH, validate_wikipedia_opening_artifact


def _node(key, parent, usi, from_sfen, *, order=0, main=True, provenance="A", segment=None,
          source_section="Main line", evidence_note=None, variation_group="main"):
    board = shogi.Board(from_sfen)
    board.push_usi(usi)
    node = {"key": key, "parent_key": parent, "usi": usi, "sort_order": order,
            "is_main": main, "from_sfen": from_sfen, "to_sfen": board.sfen(),
            "variation_group": variation_group,
            "provenance": provenance, "source_section": source_section,
            "evidence_note": evidence_note or f"Evidence for {key}"}
    if segment is not None:
        node["segment_key"] = segment
    return node


def _document(*records, review=None):
    return {
        "artifact_version": 1,
        "review": review or {
            "review_status": "reviewed",
            "reviewed_by": "reviewer@example.com",
            "reviewed_on": "2026-08-20",
            "legality_checks": {
                "backend_python_shogi": "passed", "frontend_tsshogi": "passed"
            },
        },
        "records": list(records),
    }


def _pending_review(**legality_overrides):
    legality_checks = {
        "backend_python_shogi": "passed",
        "frontend_tsshogi": "passed",
    }
    legality_checks.update(legality_overrides)
    return {"review_status": "pending", "legality_checks": legality_checks}


def _artifact(*, branched=False, mixed=False):
    start = shogi.STARTING_SFEN
    n1 = _node("n1", None, "7g7f", start)
    n2 = _node("n2", "n1", "3c3d", n1["to_sfen"])
    n3 = _node("n3", "n2", "2g2f", n2["to_sfen"])
    nodes = [n1, n2, n3]
    if branched:
        nodes.append(_node("branch", "n2", "6g6f", n2["to_sfen"], order=1, main=False,
                           source_section="Alternative line",
                           evidence_note="Alternative line explicitly gives 6g6f",
                           variation_group="早石田の変化"))
    record = {
        "record_type": "move_line",
        "record_key": "wikipedia.test", "line_key": "test-line", "line_name": "升田式石田流",
        "source": {"url": "https://ja.wikipedia.org/wiki/Test", "title": "Test", "section": "Opening"},
        "license": "CC BY-SA 4.0", "retrieved_date": "2026-08-20", "revision": 12345,
        "provenance": "A", "initial_sfen": start,
        "coverage_status": "complete_for_cited_sequence",
        "coverage": {"covered_through_ply": 3, "covered_through_move": "2g2f", "omitted_after": None},
        "source_note": "この表示文は判定されない", "nodes": nodes,
    }
    if mixed:
        record["provenance"] = "M"
        record["coverage_status"] = "mixed"
        for node in nodes:
            if node["key"] == "n1":
                node.update(provenance="A", segment_key="explicit")
            else:
                node.update(provenance="B", segment_key="diagram")
        record["segments"] = [
            {"key": "explicit", "provenance": "A", "start_node_key": "n1", "end_node_key": "n1", "source_section": "Opening", "evidence_note": "explicit moves"},
            {"key": "diagram", "provenance": "B", "start_node_key": "n2", "end_node_key": "n3", "source_section": "Diagram 1", "evidence_note": "reconstructed from diagram"},
        ]
    return _document(record)


def _repetition_artifact(*, extra_move=False):
    initial = "4k4/9/9/9/9/9/9/4G4/4K4 b - 1"
    usis = ["5h4h", "5a4a", "4h5h", "4a5a"] * 3
    if extra_move:
        usis.append("5h4h")
    nodes = []
    current = initial
    for index, usi in enumerate(usis):
        node = _node(
            f"rep-{index + 1}",
            None if index == 0 else f"rep-{index}",
            usi,
            current,
        )
        nodes.append(node)
        current = node["to_sfen"]
    record = _artifact()["records"][0]
    record["initial_sfen"] = initial
    record["nodes"] = nodes
    record["coverage"] = {
        "covered_through_ply": len(nodes),
        "covered_through_move": nodes[-1]["usi"],
        "omitted_after": None,
    }
    return _document(record)


def _codes(artifact):
    return [error.code for error in validate_wikipedia_opening_artifact(artifact)]


def _catalog_record():
    move_record = _artifact()["records"][0]
    catalog = {key: move_record[key] for key in (
        "record_key", "line_key", "source", "license", "retrieved_date", "revision"
    )}
    catalog.update(
        record_type="catalog_name_only",
        catalog_name="升田式石田流",
        provenance="C",
        coverage_status="name_only",
        source_note="名称一覧を確認した記録",
        evidence_note="名称が出典記事の一覧に掲載されている",
    )
    return catalog


def test_valid_linear_branch_and_mixed_artifacts_pass():
    assert validate_wikipedia_opening_artifact(_artifact()) == ()
    assert validate_wikipedia_opening_artifact(_artifact(branched=True)) == ()
    assert validate_wikipedia_opening_artifact(_artifact(mixed=True)) == ()


def test_line_name_preserves_unicode_and_is_required_nonempty():
    artifact = _artifact()
    assert artifact["records"][0]["line_name"] == "升田式石田流"
    assert validate_wikipedia_opening_artifact(artifact) == ()
    del artifact["records"][0]["line_name"]
    assert _codes(artifact) == ["schema"]
    artifact = _artifact()
    artifact["records"][0]["line_name"] = ""
    assert set(_codes(artifact)) == {"schema"}


@pytest.mark.parametrize("invalid_value", ["", " ", "   ", "\t\n"])
@pytest.mark.parametrize(
    "field_kind", ["line_name", "catalog_name", "variation_group", "source_title"]
)
def test_required_display_metadata_contains_non_whitespace(
    invalid_value, field_kind
):
    if field_kind == "catalog_name":
        record = _catalog_record()
        record["catalog_name"] = invalid_value
        artifact = _document(record)
    else:
        artifact = _artifact()
        record = artifact["records"][0]
        if field_kind == "line_name":
            record["line_name"] = invalid_value
        elif field_kind == "variation_group":
            record["nodes"][0]["variation_group"] = invalid_value
        else:
            record["source"]["title"] = invalid_value
    assert set(_codes(artifact)) == {"schema"}


def test_artifact_schema_is_valid_draft_2020_12():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("url", [
    "https://ja.wikipedia.org/wiki/Test",
    "https://en.wikipedia.org/wiki/Test",
    "https://ja.wikibooks.org/wiki/Test",
    "https://ja.wikipedia.org/wiki/Test?oldid=12345#Section",
])
def test_https_wikipedia_and_wikibooks_source_urls_pass(url):
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = url
    assert validate_wikipedia_opening_artifact(artifact) == ()


@pytest.mark.parametrize("url", [
    "https://ja.wikipedia.org/wiki/Test",
    "https://ja.wikipedia.org/w/index.php?oldid=12345",
    "https://ja.wikipedia.org/w/index.php?oldid=00012345",
    "https://ja.wikipedia.org/w/index.php?title=Test&oldid=12345&diff=prev",
])
def test_source_oldid_is_optional_or_matches_revision(url):
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = url
    assert validate_wikipedia_opening_artifact(artifact) == ()


@pytest.mark.parametrize("query", [
    "oldid=54321",
    "oldid=",
    "oldid=abc",
    "oldid=%EF%BC%91%EF%BC%92%EF%BC%93%EF%BC%94%EF%BC%95",
    "oldid=12345&oldid=12345",
])
def test_source_oldid_must_be_unambiguous_positive_decimal_matching_revision(query):
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = (
        f"https://ja.wikipedia.org/w/index.php?{query}"
    )
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == ["source_revision"]
    assert diagnostics[0].path == "/records/0/source/url"


def test_huge_oldid_is_rejected_without_integer_conversion_failure():
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = (
        "https://ja.wikipedia.org/w/index.php?oldid=" + "9" * 10000
    )
    first = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in first] == ["source_revision"]
    assert first == validate_wikipedia_opening_artifact(deepcopy(artifact))


def test_malformed_source_url_is_a_schema_error():
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = "not-a-url"
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == ["schema"]
    assert diagnostics[0].path == "/records/0/source/url"


@pytest.mark.parametrize("url", [
    "javascript:alert",
    "http://ja.wikipedia.org/wiki/Test",
    "https://example.com/wiki/Test",
    "https://evilwikipedia.org/wiki/Test",
    "https:///wiki/Test",
])
def test_uri_outside_https_wikimedia_contract_is_rejected(url):
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = url
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == ["source_url"]
    assert diagnostics[0].path == "/records/0/source/url"


@pytest.mark.parametrize("url", [
    "https://user@ja.wikipedia.org/wiki/Test",
    "https://user:password@ja.wikibooks.org/wiki/Test",
    "https://ja.wikipedia.org:/wiki/Test",
    "https://ja.wikibooks.org:/wiki/Test",
    "https://ja.wikipedia.org:443/wiki/Test",
    "https://ja.wikipedia.org:65536/wiki/Test",
    "https://ja.wikipedia.org:not-a-port/wiki/Test",
])
def test_source_url_userinfo_and_explicit_ports_are_rejected_without_exceptions(url):
    artifact = _artifact()
    artifact["records"][0]["source"]["url"] = url
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == ["source_url"]
    assert diagnostics[0].path == "/records/0/source/url"


def test_json_pointer_uses_empty_string_for_document_root():
    diagnostics = validate_wikipedia_opening_artifact([])
    assert diagnostics[0].code == "schema"
    assert diagnostics[0].path == ""

    artifact = _artifact()
    del artifact["records"]
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert diagnostics[0].code == "schema"
    assert diagnostics[0].path == ""

    artifact = _artifact()
    artifact["records"][0]["line_name"] = ""
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert diagnostics[0].code == "schema"
    assert diagnostics[0].path == "/records/0/line_name"


def test_coverage_status_positive_provenance_combinations():
    assert validate_wikipedia_opening_artifact(_artifact()) == ()

    partial = _artifact()
    partial["records"][0]["coverage_status"] = "partial_explicit_sequence"
    partial["records"][0]["coverage"]["omitted_after"] = {"usi": "8c8d"}
    assert validate_wikipedia_opening_artifact(partial) == ()

    diagram = _artifact()
    diagram_record = diagram["records"][0]
    diagram_record["provenance"] = "B"
    diagram_record["coverage_status"] = "diagram_reconstruction"
    for node in diagram_record["nodes"]:
        node["provenance"] = "B"
    assert validate_wikipedia_opening_artifact(diagram) == ()

    assert validate_wikipedia_opening_artifact(_document(_catalog_record())) == ()
    assert validate_wikipedia_opening_artifact(_artifact(mixed=True)) == ()


@pytest.mark.parametrize(
    ("provenance", "status"),
    [
        ("A", "diagram_reconstruction"),
        ("B", "complete_for_cited_sequence"),
        ("B", "partial_explicit_sequence"),
        ("M", "complete_for_cited_sequence"),
    ],
)
def test_move_line_coverage_status_must_match_provenance(provenance, status):
    artifact = _artifact(mixed=provenance == "M")
    record = artifact["records"][0]
    record["provenance"] = provenance
    record["coverage_status"] = status
    if provenance == "B":
        for node in record["nodes"]:
            node["provenance"] = "B"
    assert "coverage_status_provenance" in _codes(artifact)


def test_catalog_coverage_status_must_be_name_only():
    catalog = _catalog_record()
    catalog["coverage_status"] = "mixed"
    assert _codes(_document(catalog)) == ["coverage_status_provenance"]


@pytest.mark.parametrize(
    ("status", "omitted_after"),
    [
        ("complete_for_cited_sequence", {"usi": "8c8d"}),
        ("partial_explicit_sequence", None),
    ],
)
def test_a_coverage_status_must_match_structured_boundary(status, omitted_after):
    artifact = _artifact()
    record = artifact["records"][0]
    record["coverage_status"] = status
    record["coverage"]["omitted_after"] = omitted_after
    assert "coverage_status_boundary" in _codes(artifact)


def test_main_and_branch_can_carry_distinct_source_sections():
    artifact = _artifact(branched=True)
    nodes = artifact["records"][0]["nodes"]
    assert nodes[2]["source_section"] == "Main line"
    assert nodes[3]["source_section"] == "Alternative line"
    assert nodes[2]["evidence_note"] == "Evidence for n3"
    assert nodes[3]["evidence_note"] == "Alternative line explicitly gives 6g6f"
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_variation_group_is_required_nonempty_unicode_display_metadata():
    artifact = _artifact(branched=True)
    nodes = artifact["records"][0]["nodes"]
    assert nodes[0]["variation_group"] == "main"
    assert nodes[3]["variation_group"] == "早石田の変化"
    assert validate_wikipedia_opening_artifact(artifact) == ()

    del nodes[0]["variation_group"]
    assert _codes(artifact) == ["schema"]

    artifact = _artifact()
    artifact["records"][0]["nodes"][0]["variation_group"] = ""
    assert set(_codes(artifact)) == {"schema"}


def test_variation_group_may_be_shared_by_multiple_nodes():
    artifact = _artifact()
    for node in artifact["records"][0]["nodes"]:
        node["variation_group"] = "共通の変化"
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_node_source_section_is_required_and_nonempty():
    artifact = _artifact()
    del artifact["records"][0]["nodes"][1]["source_section"]
    assert _codes(artifact) == ["schema"]
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["source_section"] = ""
    assert set(_codes(artifact)) == {"schema"}


@pytest.mark.parametrize("whitespace", [" ", "   ", "\t\n"])
@pytest.mark.parametrize("section_kind", ["record", "node", "segment"])
def test_mandatory_source_sections_require_non_whitespace(
    whitespace, section_kind
):
    artifact = _artifact(mixed=section_kind == "segment")
    if section_kind == "record":
        artifact["records"][0]["source"]["section"] = whitespace
    elif section_kind == "node":
        artifact["records"][0]["nodes"][0]["source_section"] = whitespace
    else:
        artifact["records"][0]["segments"][0]["source_section"] = whitespace
    assert _codes(artifact) == ["schema"]


@pytest.mark.parametrize("record_kind", ["move_line", "catalog_name_only"])
@pytest.mark.parametrize("invalid_note", [None, "", " ", "   ", "\t\n"])
def test_source_note_is_required_and_contains_non_whitespace(
    record_kind, invalid_note
):
    record = (
        _artifact()["records"][0]
        if record_kind == "move_line"
        else _catalog_record()
    )
    if invalid_note is None:
        del record["source_note"]
    else:
        record["source_note"] = invalid_note
    assert set(_codes(_document(record))) == {"schema"}


def test_node_evidence_note_is_required_and_nonempty():
    artifact = _artifact()
    del artifact["records"][0]["nodes"][1]["evidence_note"]
    assert _codes(artifact) == ["schema"]
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["evidence_note"] = ""
    assert set(_codes(artifact)) == {"schema"}


@pytest.mark.parametrize("whitespace", [" ", "   ", "\t\n"])
@pytest.mark.parametrize("evidence_kind", ["node", "segment", "catalog"])
def test_mandatory_evidence_requires_a_non_whitespace_character(
    whitespace, evidence_kind
):
    if evidence_kind == "catalog":
        catalog = _catalog_record()
        catalog["evidence_note"] = whitespace
        artifact = _document(catalog)
    else:
        artifact = _artifact(mixed=evidence_kind == "segment")
        if evidence_kind == "node":
            artifact["records"][0]["nodes"][0]["evidence_note"] = whitespace
        else:
            artifact["records"][0]["segments"][0]["evidence_note"] = whitespace
    assert _codes(artifact) == ["schema"]


def test_multiple_root_siblings_are_a_valid_initial_position_choice_set():
    artifact = _artifact()
    record = artifact["records"][0]
    alternative = _node("root-alt", None, "2g2f", record["initial_sfen"], order=1, main=False)
    record["nodes"].append(alternative)
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_catalog_c_is_name_only_and_cannot_contain_nodes():
    move_record = _artifact()["records"][0]
    catalog = _catalog_record()
    assert validate_wikipedia_opening_artifact(_document(catalog)) == ()
    catalog["nodes"] = move_record["nodes"]
    assert _codes(_document(catalog)) == ["schema"]
    move_record["provenance"] = "C"
    assert _codes(_document(move_record)) == ["schema"]


def test_catalog_name_preserves_unicode_and_is_required_nonempty():
    catalog = _catalog_record()
    assert catalog["catalog_name"] == "升田式石田流"
    assert validate_wikipedia_opening_artifact(_document(catalog)) == ()
    del catalog["catalog_name"]
    assert _codes(_document(catalog)) == ["schema"]
    catalog = _catalog_record()
    catalog["catalog_name"] = ""
    assert set(_codes(_document(catalog))) == {"schema"}


def test_pending_and_reviewed_audit_metadata_are_structured():
    pending = _document(
        _artifact()["records"][0], review=_pending_review()
    )
    diagnostics = validate_wikipedia_opening_artifact(pending)
    assert [diagnostic.code for diagnostic in diagnostics] == ["review_pending"]
    assert diagnostics[0].path == "/review/review_status"
    reviewed = {"review_status": "reviewed", "reviewed_by": "reviewer@example.com",
                "reviewed_on": "2026-08-20", "legality_checks": {
                    "backend_python_shogi": "passed", "frontend_tsshogi": "passed"}}
    assert validate_wikipedia_opening_artifact(
        _document(_artifact()["records"][0], review=reviewed)
    ) == ()
    del reviewed["reviewed_by"]
    assert _codes(_document(_artifact()["records"][0], review=reviewed)) == ["schema"]


@pytest.mark.parametrize("invalid_reviewer", ["", " ", "   ", "\t\n"])
def test_reviewed_by_contains_non_whitespace(invalid_reviewer):
    artifact = _artifact()
    artifact["review"]["reviewed_by"] = invalid_reviewer
    assert set(_codes(artifact)) == {"schema"}


@pytest.mark.parametrize("pending_engine", [
    "backend_python_shogi", "frontend_tsshogi"
])
def test_pending_legality_result_is_not_gate_success(pending_engine):
    artifact = _document(
        _artifact()["records"][0],
        review=_pending_review(**{pending_engine: "pending"}),
    )
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "review_legality_pending", "review_pending"
    ]
    assert [diagnostic.path for diagnostic in diagnostics] == [
        f"/review/legality_checks/{pending_engine}", "/review/review_status"
    ]


def test_both_pending_legality_results_have_deterministic_engine_diagnostics():
    artifact = _document(
        _artifact()["records"][0],
        review=_pending_review(
            backend_python_shogi="pending", frontend_tsshogi="pending"
        ),
    )
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "review_legality_pending", "review_legality_pending", "review_pending"
    ]
    assert [diagnostic.path for diagnostic in diagnostics] == [
        "/review/legality_checks/backend_python_shogi",
        "/review/legality_checks/frontend_tsshogi",
        "/review/review_status",
    ]
    assert diagnostics == validate_wikipedia_opening_artifact(deepcopy(artifact))


@pytest.mark.parametrize("failed_engine", ["backend_python_shogi", "frontend_tsshogi"])
def test_reviewed_failed_legality_result_is_a_semantic_failure(failed_engine):
    review = {"review_status": "reviewed", "reviewed_by": "reviewer@example.com",
              "reviewed_on": "2026-08-20", "legality_checks": {
                  "backend_python_shogi": "passed", "frontend_tsshogi": "passed"}}
    review["legality_checks"][failed_engine] = "failed"
    diagnostics = validate_wikipedia_opening_artifact(
        _document(_artifact()["records"][0], review=review)
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["review_legality_failed"]
    assert diagnostics[0].path == f"/review/legality_checks/{failed_engine}"


@pytest.mark.parametrize("failed_engine", ["backend_python_shogi", "frontend_tsshogi"])
def test_pending_failed_legality_result_is_a_semantic_failure(failed_engine):
    artifact = _document(
        _artifact()["records"][0],
        review=_pending_review(**{failed_engine: "failed"}),
    )
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "review_legality_failed", "review_pending"
    ]
    assert [diagnostic.path for diagnostic in diagnostics] == [
        f"/review/legality_checks/{failed_engine}", "/review/review_status"
    ]


def test_stored_legality_result_never_skips_backend_replay():
    artifact = _artifact()
    artifact["review"]["legality_checks"]["backend_python_shogi"] = "passed"
    artifact["review"]["legality_checks"]["frontend_tsshogi"] = "passed"
    artifact["records"][0]["nodes"][0]["usi"] = "7g7e"
    assert "illegal_move" in _codes(artifact)


@pytest.mark.parametrize("revision", [0, -1, "unknown", "12345"])
@pytest.mark.parametrize("record_factory", [lambda: _artifact()["records"][0], _catalog_record])
def test_revision_must_be_a_positive_canonical_integer(record_factory, revision):
    record = record_factory()
    record["revision"] = revision
    assert _codes(_document(record)) == ["schema"]


def test_positive_integer_revision_is_valid_for_move_line_and_catalog():
    assert validate_wikipedia_opening_artifact(_artifact()) == ()
    assert validate_wikipedia_opening_artifact(
        _document(_catalog_record())
    ) == ()


def test_catalog_evidence_note_is_required_and_nonempty():
    catalog = _catalog_record()
    del catalog["evidence_note"]
    assert _codes(_document(catalog)) == ["schema"]
    catalog = _catalog_record()
    catalog["evidence_note"] = ""
    assert set(_codes(_document(catalog))) == {"schema"}


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


@pytest.mark.parametrize("sfen", [
    "9/9/9/9/9/9/9/9/9 b - 1",
    "4k4/9/9/9/9/9/9/9/9 b - 1",
    "4k4/4k4/9/9/9/9/9/9/4K4 b - 1",
])
def test_initial_sfen_requires_exactly_one_king_per_color(sfen):
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = sfen
    assert "initial_king_count" in _codes(artifact)


def test_initial_sfen_cannot_exceed_standard_piece_inventory():
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = "4k4/9/9/9/9/9/9/9/4K4 b 19P 1"
    assert "initial_piece_inventory" in _codes(artifact)
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = "4k4/9/9/9/9/9/9/9/+P3K4 b 18P 1"
    assert "initial_piece_inventory" in _codes(artifact)


@pytest.mark.parametrize("sfen", [
    "P3k4/9/9/9/9/9/9/9/4K4 b - 1",  # black pawn on rank 1
    "4k4/9/9/9/9/9/9/9/p3K4 b - 1",  # white pawn on rank 9
    "L3k4/9/9/9/9/9/9/9/4K4 b - 1",  # black lance on rank 1
    "4k4/9/9/9/9/9/9/9/l3K4 b - 1",  # white lance on rank 9
    "N3k4/9/9/9/9/9/9/9/4K4 b - 1",  # black knight on rank 1
    "4k4/9/9/9/9/9/9/n8/4K4 b - 1",  # white knight on rank 8
])
def test_initial_sfen_rejects_unpromoted_dead_rank_pieces(sfen):
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = sfen
    assert "initial_dead_rank_piece" in _codes(artifact)


@pytest.mark.parametrize("sfen", [
    "4k4/9/9/9/9/9/9/P8/P3K4 b - 1",
    "4k3p/8p/9/9/9/9/9/9/4K4 b - 1",
])
def test_initial_sfen_rejects_nifu_for_both_colors(sfen):
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = sfen
    assert "initial_nifu" in _codes(artifact)


@pytest.mark.parametrize("sfen", [
    "4k4/4R4/9/9/9/9/9/9/4K4 b - 1",
    "4k4/9/9/9/9/9/9/4r4/4K4 w - 1",
    "4k4/4K4/9/9/9/9/9/9/9 b - 1",
])
def test_initial_sfen_rejects_inactive_king_in_check(sfen):
    artifact = _artifact()
    artifact["records"][0]["initial_sfen"] = sfen
    assert "initial_inactive_king_in_check" in _codes(artifact)


def test_side_to_move_may_start_in_check_and_evade_with_root_move():
    artifact = _artifact()
    record = artifact["records"][0]
    initial = "4k4/9/9/9/9/9/9/4r4/4K4 b - 1"
    board = shogi.Board(initial)
    assert board.is_check()
    legal_usi = next(move.usi() for move in board.legal_moves)
    record["initial_sfen"] = initial
    record["nodes"] = [_node("n1", None, legal_usi, initial)]
    record["coverage"] = {"covered_through_ply": 1, "covered_through_move": legal_usi, "omitted_after": None}
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_promoted_pawn_does_not_count_as_nifu():
    artifact = _artifact()
    record = artifact["records"][0]
    initial = "4k4/9/9/9/9/9/P8/+P8/4K4 b - 1"
    record["initial_sfen"] = initial
    record["nodes"] = [_node("n1", None, "9g9f", initial)]
    record["coverage"] = {"covered_through_ply": 1, "covered_through_move": "9g9f", "omitted_after": None}
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_deep_parent_chain_does_not_use_python_recursion():
    artifact = _artifact()
    record = artifact["records"][0]
    template = record["nodes"][0]
    record["nodes"] = [
        {**template, "key": f"deep-{index}",
         "parent_key": None if index == 0 else f"deep-{index - 1}"}
        for index in range(1100)
    ]
    record["coverage"] = {"covered_through_ply": 1100,
                          "covered_through_move": template["usi"], "omitted_after": None}
    first = validate_wikipedia_opening_artifact(artifact)
    assert first
    assert first == validate_wikipedia_opening_artifact(deepcopy(artifact))


def test_fourfold_repetition_ending_move_is_valid():
    artifact = _repetition_artifact()
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_move_after_fourfold_repetition_is_rejected_stably():
    artifact = _repetition_artifact(extra_move=True)
    diagnostics = validate_wikipedia_opening_artifact(artifact)
    after_end = [
        diagnostic for diagnostic in diagnostics
        if diagnostic.code == "move_after_game_end"
    ]
    assert len(after_end) == 1
    assert after_end[0].path == "/records/0/nodes/12/usi"
    assert diagnostics == validate_wikipedia_opening_artifact(deepcopy(artifact))


def test_omitted_move_after_fourfold_repetition_is_rejected_stably():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    record["coverage_status"] = "partial_explicit_sequence"
    record["coverage"]["omitted_after"] = {"usi": "5h4h"}
    first = validate_wikipedia_opening_artifact(artifact)
    omitted = [
        diagnostic for diagnostic in first
        if diagnostic.code == "omitted_after_game_end"
    ]
    assert len(omitted) == 1
    assert omitted[0].path == "/records/0/coverage/omitted_after/usi"
    assert first == validate_wikipedia_opening_artifact(deepcopy(artifact))


def test_omitted_move_that_completes_fourfold_repetition_is_valid():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    record["nodes"].pop()
    record["coverage_status"] = "partial_explicit_sequence"
    record["coverage"] = {
        "covered_through_ply": 11,
        "covered_through_move": "4h5h",
        "omitted_after": {"usi": "4a5a"},
    }
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_repetition_history_does_not_leak_between_branches():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    first = record["nodes"][0]
    record["nodes"].append(
        _node(
            "branch-safe",
            first["key"],
            "5a6a",
            first["to_sfen"],
            order=1,
            main=False,
            variation_group="別分岐",
        )
    )
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_branch_repetition_state_does_not_leak_into_main_omitted_move():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    first = record["nodes"][0]
    record["nodes"][1]["is_main"] = False
    record["nodes"].append(
        _node(
            "main-safe",
            first["key"],
            "5a6a",
            first["to_sfen"],
            order=1,
            main=True,
            variation_group="本線",
        )
    )
    record["coverage_status"] = "partial_explicit_sequence"
    record["coverage"] = {
        "covered_through_ply": 2,
        "covered_through_move": "5a6a",
        "omitted_after": {"usi": "4h5h"},
    }
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_repetition_history_does_not_leak_between_virtual_root_siblings():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    record["nodes"].append(
        _node(
            "root-safe",
            None,
            "5h6h",
            record["initial_sfen"],
            order=1,
            main=False,
            variation_group="別初手",
        )
    )
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_virtual_root_repetition_state_does_not_leak_into_main_omitted_move():
    artifact = _repetition_artifact()
    record = artifact["records"][0]
    record["nodes"][0]["is_main"] = False
    record["nodes"].append(
        _node(
            "root-main-safe",
            None,
            "5h6h",
            record["initial_sfen"],
            order=1,
            main=True,
            variation_group="本線初手",
        )
    )
    record["coverage_status"] = "partial_explicit_sequence"
    record["coverage"] = {
        "covered_through_ply": 1,
        "covered_through_move": "5h6h",
        "omitted_after": {"usi": "5a4a"},
    }
    assert validate_wikipedia_opening_artifact(artifact) == ()


def test_orphan_cycle_and_root_failures_are_rejected():
    artifact = _artifact()
    artifact["records"][0]["nodes"][1]["parent_key"] = "missing"
    assert "orphan_parent" in _codes(artifact)
    artifact = _artifact()
    nodes = artifact["records"][0]["nodes"]
    nodes[0]["parent_key"] = "n3"
    assert {"cycle", "root_count"} <= set(_codes(artifact))
    first = validate_wikipedia_opening_artifact(artifact)
    assert first == validate_wikipedia_opening_artifact(deepcopy(artifact))


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
    artifact["records"][0]["coverage_status"] = "partial_explicit_sequence"
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
