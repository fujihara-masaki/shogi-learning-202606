#!/usr/bin/env python3
"""Validate a canonical Wikipedia opening artifact and emit one JSON result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.wikipedia_opening_validator import (  # noqa: E402
    SCHEMA_PATH,
    _validate_wikipedia_opening_artifact,
)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"valid": False, "errors": [{"path": "", "code": code, "message": message}]}


def _read_json(path: Path, prefix: str) -> tuple[Any | None, dict[str, Any] | None]:
    if not path.exists():
        return None, _error(f"{prefix}_not_found", f"{prefix} file does not exist: {path}")
    if not path.is_file():
        return None, _error(f"{prefix}_not_file", f"{prefix} path is not a file: {path}")
    try:
        contents = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return None, _error(f"{prefix}_invalid_utf8", f"{prefix} is not valid UTF-8: {exc}")
    except OSError as exc:
        return None, _error(f"{prefix}_read_error", f"could not read {prefix}: {exc}")
    try:
        return json.loads(contents), None
    except json.JSONDecodeError as exc:
        return None, _error(f"{prefix}_json_invalid", f"{prefix} is not valid JSON: {exc}")


def validate_path(
    artifact_path: Path, *, schema_path: Path = SCHEMA_PATH
) -> tuple[int, dict[str, Any]]:
    """Return the process status and JSON payload; schema injection is test-only."""
    artifact, error = _read_json(artifact_path, "artifact")
    if error is not None:
        return 2, error

    _, schema_error = _read_json(schema_path, "schema")
    if schema_error is not None:
        return 2, schema_error

    try:
        diagnostics = _validate_wikipedia_opening_artifact(artifact, schema_path)
    except jsonschema.exceptions.SchemaError as exc:
        return 2, _error("schema_definition_invalid", f"canonical schema is invalid: {exc.message}")

    errors = [
        {"path": item.path, "code": item.code, "message": item.message}
        for item in diagnostics
    ]
    return (1 if errors else 0), {"valid": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a D1b canonical Wikipedia opening artifact."
    )
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    status, result = validate_path(args.artifact)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
