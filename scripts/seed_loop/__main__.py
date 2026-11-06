"""Public schema-v1 CLI. Run from the repository root with python -m scripts.seed_loop."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys
import uuid

from .controller import control, pause, replay
from .state import LoopError, Store, config_from, environment, identity
from .usage import AppServerUsage
from .validation import plan


def summary(state):
    result = dict(state)
    if "identity" in result:
        result["identity"] = {k: v for k, v in result["identity"].items() if k != "files"}
    return result


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Seed validation foundation (no inference/remote writes)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--live-usage", action="store_true")
    for name in ("dry-run", "validate", "run", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--profile", choices=("artifacts", "full"), default="artifacts")
        if name != "dry-run":
            command.add_argument("--run-id", required=name in ("run", "resume"))
        if name == "resume":
            command.add_argument("--validation-only", action="store_true")
    for name in ("status", "pause"):
        commands.add_parser(name).add_argument("--run-id", required=True)
    commands.add_parser("replay").add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == "status":
            store = Store(root, args.run_id)
            state = store.load()
            result = summary(state)
            result["pause_requested"] = store.pause_path.exists()
            try:
                with store.lock():
                    result["worker_active"] = False
            except LoopError:
                result["worker_active"] = True
            code = 0
        elif args.command == "pause":
            result, code = summary(pause(root, args.run_id)), 0
        else:
            config = config_from(args.config)
            if args.command == "preflight":
                deps = {name: importlib.util.find_spec(name) is not None
                        for name in ("pytest", "jsonschema", "shogi", "fastapi", "uvicorn")}
                result = {"schema_version": 1, "mode": "preflight", "environment": environment(),
                          "dependencies": deps, "identity": identity(root), "config": config,
                          "frontend_installed": (root / "frontend/node_modules/.bin").is_dir(),
                          "artifact_count": len(plan(root, "artifacts")), "usage": None,
                          "validation": "not_run"}
                if args.live_usage:
                    result["usage"] = AppServerUsage(config).read()
                result = summary(result)
                code = 0 if (all(deps.values()) and result["environment"]["node"] and
                              result["environment"]["npm"] and result["frontend_installed"]) else 2
                if args.live_usage and result["usage"]["status"] != "known":
                    code = 2
            elif args.command == "dry-run":
                result = {"schema_version": 1, "mode": "dry-run", "validation": "not_run",
                          "stages": [s.record() for s in plan(root, args.profile)]}
                code = 0
            elif args.command == "replay":
                result, code = replay(root, args.fixture, config), 0
            else:
                run_id = args.run_id or uuid.uuid4().hex
                mode = "validation-only" if (args.command == "validate" or
                         getattr(args, "validation_only", False)) else "controlled"
                state = control(root, run_id, config, args.profile, mode, args.command == "resume")
                result = summary(state)
                result["state_path"] = str(Store(root, run_id).path)
                status = state["execution_status"]
                code = {"completed": 0, "paused": 3, "failed": 1}[status]
                if state["stop_reason"] == "stage_operational_error":
                    code = 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (LoopError, OSError) as exc:
        print(json.dumps({"schema_version": 1, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(3)
