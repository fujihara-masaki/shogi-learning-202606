import importlib.util
import json
from pathlib import Path
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "validate_wikipedia_opening_artifact.py"


def artifact():
    return {
        "artifact_version": 1,
        "review": {
            "review_status": "reviewed",
            "reviewed_by": "査読者",
            "reviewed_on": "2026-08-20",
            "legality_checks": {
                "backend_python_shogi": "passed",
                "frontend_tsshogi": "passed",
            },
        },
        "records": [{
            "record_type": "catalog_name_only",
            "record_key": "wikipedia.test",
            "line_key": "test-line",
            "catalog_name": "升田式石田流",
            "source": {
                "url": "https://ja.wikipedia.org/wiki/Test",
                "title": "テスト",
                "section": "戦法",
            },
            "license": "CC BY-SA 4.0",
            "retrieved_date": "2026-08-20",
            "revision": 12345,
            "provenance": "C",
            "coverage_status": "name_only",
            "source_note": "名称を確認",
            "evidence_note": "一覧に掲載",
        }],
    }


def write_artifact(tmp_path, value=None):
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact() if value is None else value), encoding="utf-8")
    return path


def run_cli(path, *, cwd=BACKEND):
    command = [sys.executable, "scripts/validate_wikipedia_opening_artifact.py", str(path)]
    if cwd != BACKEND:
        command[1] = str(SCRIPT)
    completed = subprocess.run(command, cwd=cwd, shell=False, text=True, capture_output=True)
    return completed, json.loads(completed.stdout)


def test_valid_artifact_direct_execution_from_backend_and_repository_root(tmp_path):
    path = write_artifact(tmp_path)
    for cwd in (BACKEND, BACKEND.parent):
        completed, result = run_cli(path, cwd=cwd)
        assert completed.returncode == 0
        assert result == {"valid": True, "errors": []}
        assert "升田式" not in completed.stdout  # output is diagnostics, not input echo
        assert completed.stdout.endswith("\n")
        assert "Traceback" not in completed.stderr


def test_schema_violation_exits_one(tmp_path):
    value = artifact()
    del value["records"][0]["catalog_name"]
    completed, result = run_cli(write_artifact(tmp_path, value))
    assert completed.returncode == 1
    assert result["valid"] is False
    assert {error["code"] for error in result["errors"]} == {"schema"}


def test_semantic_violation_preserves_diagnostic(tmp_path):
    value = artifact()
    value["records"][0]["source"]["url"] = "https://example.com/wiki/Test"
    completed, result = run_cli(write_artifact(tmp_path, value))
    assert completed.returncode == 1
    assert [(item["code"], item["path"]) for item in result["errors"]] == [
        ("source_url", "/records/0/source/url")
    ]


def test_malformed_json_exits_two_without_traceback(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not JSON", encoding="utf-8")
    completed, result = run_cli(path)
    assert completed.returncode == 2
    assert result["errors"][0]["code"] == "artifact_json_invalid"
    assert "Traceback" not in completed.stderr


def test_invalid_utf8_exits_two(tmp_path):
    path = tmp_path / "bad-utf8.json"
    path.write_bytes(b"\xff\xfe")
    completed, result = run_cli(path)
    assert completed.returncode == 2
    assert result["errors"][0]["code"] == "artifact_invalid_utf8"


def test_missing_file_exits_two(tmp_path):
    completed, result = run_cli(tmp_path / "missing.json")
    assert completed.returncode == 2
    assert result["errors"][0]["code"] == "artifact_not_found"


def test_directory_exits_two(tmp_path):
    completed, result = run_cli(tmp_path)
    assert completed.returncode == 2
    assert result["errors"][0]["code"] == "artifact_not_file"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("validator_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_malformed_canonical_schema_is_an_operational_error(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text("{bad", encoding="utf-8")
    status, result = load_cli_module().validate_path(write_artifact(tmp_path), schema_path=schema)
    assert status == 2
    assert result["errors"][0]["code"] == "schema_json_invalid"


def test_invalid_schema_definition_is_an_operational_error(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": 7}))
    status, result = load_cli_module().validate_path(write_artifact(tmp_path), schema_path=schema)
    assert status == 2
    assert result["errors"][0]["code"] == "schema_definition_invalid"


def test_unresolved_schema_reference_is_an_operational_error(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/missing",
    }))
    status, result = load_cli_module().validate_path(write_artifact(tmp_path), schema_path=schema)
    assert status == 2
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "schema_definition_invalid"
