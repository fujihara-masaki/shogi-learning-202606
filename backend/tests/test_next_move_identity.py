from app.next_move_identity import canonical_hash, canonical_json, normalize_candidates, normalize_sfen, problem_key


def test_canonical_serialization_golden_and_semantics():
    assert canonical_json({"z": "e\u0301", "a": None, "b": ""}) == '{"a":null,"b":"","z":"é"}'
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert canonical_hash({"value": None}) != canonical_hash({"value": ""})
    assert canonical_hash({"value": "é"}) == canonical_hash({"value": "e\u0301"})


def test_problem_key_golden_and_only_meaningful_inputs_affect_it():
    source = {"name": "テスト", "version": None, "source_url": ""}
    sfen = "lnsgkgsnl/1r5b1/p1pppp1pp/9/9/9/P1PPPP1PP/1B5R1/LNSGKGSNL b - 1"
    candidates = [{"move_usi": "7g7f", "sort_order": 0, "score": 10, "depth": 2}]
    assert problem_key(source, sfen, candidates) == "v1:60d74efe668c355b78dd69d1952679fccec9ce2272826c961c863a6f2a65e474"
    assert problem_key(source, sfen.replace(" 1", " 99"), candidates) == problem_key(source, sfen, candidates)


def test_candidate_order_is_deterministic_and_score_only_changes_key_when_order_changes():
    candidates = [
        {"move_usi": "7g7f", "rank": 1, "score": None, "depth": 9},
        {"move_usi": "2g2f", "rank": 1, "score": 20, "depth": None},
        {"move_usi": "5g5f", "rank": 1, "score": 20, "depth": 4},
    ]
    normalized = normalize_candidates(candidates)
    assert [(c["move_usi"], c["effective_rank"], c["judgment_position"]) for c in normalized] == [
        ("5g5f", 1, 1), ("2g2f", 1, 2), ("7g7f", 1, 3)]
    source = {"name": "source", "version": "1", "source_url": "url"}
    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    base_key = problem_key(source, sfen, candidates)
    same_order = [{**c, "score": 21 if c["move_usi"] == "5g5f" else c["score"]} for c in candidates]
    changed_order = [{**c, "score": 30 if c["move_usi"] == "2g2f" else c["score"]} for c in candidates]
    assert problem_key(source, sfen, same_order) == base_key
    assert problem_key(source, sfen, changed_order) != base_key


def test_problem_key_dependency_boundaries_and_row_order():
    source = {"name": "source", "version": "1", "source_url": "url", "file_sha256": "a"}
    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    candidates = [{"id": 99, "move_usi": "7g7f", "rank": 1, "score": 1, "depth": 1},
                  {"id": 1, "move_usi": "2g2f", "rank": 2, "score": 2, "depth": 2}]
    key = problem_key(source, sfen, candidates)
    assert problem_key({**source, "opening_key": "changed", "limit": 1,
                        "per_opening_limit": 2, "seed": 999}, sfen, candidates) == key
    assert problem_key({**source, "file_sha256": "b"}, sfen, list(reversed(candidates))) == key
    assert problem_key(source, sfen, [{**c, "id": c["id"] + 100} for c in candidates]) == key
    assert problem_key(source, sfen, [{**c, "rank": 4} if c["move_usi"] == "2g2f" else c for c in candidates]) != key
    assert problem_key({**source, "name": "other"}, sfen, candidates) != key
    assert problem_key(source, sfen, candidates + [{"move_usi": "5g5f", "rank": 3}]) != key
    assert problem_key(source, sfen, candidates, problem_definition_version=2) != key


def test_normalize_sfen_drops_ply():
    base = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b -"
    assert normalize_sfen(base + " 1") == normalize_sfen(base + " 42") == base
