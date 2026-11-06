"""Fixed validation profiles calling the existing repository gates."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from .process import spawn, terminate
from .state import LoopError, now


@dataclass
class Stage:
    id: str
    command: list[str]
    cwd: str
    target: str | None = None
    diagnostic: bool = False
    e2e: bool = False

    def record(self):
        return {**asdict(self), "status": "not_run", "attempts": []}


def npm(*args):
    if os.name == "nt":
        return ["cmd.exe", "/d", "/s", "/c", "npm.cmd", *args]
    return ["npm", *args]


def plan(root, profile):
    artifacts = sorted((root / "backend/app/wikipedia_opening_artifacts").glob("*.json"))
    if not artifacts:
        raise LoopError("no bundled canonical artifacts found")
    stages = [Stage("artifact-" + p.stem,
                    [sys.executable, "backend/scripts/validate_wikipedia_opening_artifact.py", str(p)],
                    str(root), str(p.relative_to(root)), True) for p in artifacts]
    if profile == "full":
        stages = [Stage("foundation", [sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-v"], str(root))] + stages
        stages += [
            Stage("backend", [sys.executable, "-m", "pytest", "-q"], str(root / "backend")),
            Stage("vitest", npm("exec", "--no", "--", "vitest", "run"), str(root / "frontend")),
            Stage("lint", npm("run", "lint"), str(root / "frontend")),
            Stage("build", npm("run", "build"), str(root / "frontend")),
            Stage("chromium", npm("run", "test:e2e", "--", "--project=chromium", "--workers=1"),
                  str(root / "frontend"), e2e=True),
        ]
    return stages


def child_environment(directory, config, e2e=False):
    env = dict(os.environ)
    for key in ("SHOGI_DB_PATH", "NEXT_MOVE_DB_PATH", "SHOGI_CORS_ORIGINS"):
        env.pop(key, None)
    env.update({"CI": "1", "PYTHON": sys.executable, "PYTHONIOENCODING": "utf-8",
                "E2E_BACKEND_PORT": str(config["e2e_backend_port"]),
                "E2E_FRONTEND_PORT": str(config["e2e_frontend_port"])})
    if not e2e:
        # Guard even commands whose tests normally override DB paths themselves.
        env["SHOGI_DB_PATH"] = str(directory / "isolated-shogi.db")
        env["NEXT_MOVE_DB_PATH"] = str(directory / "isolated-next-move.db")
    return env


def check_ports(config):
    sockets = []
    try:
        for key in ("e2e_backend_port", "e2e_frontend_port"):
            sock = socket.socket()
            sockets.append(sock)
            try:
                sock.bind(("127.0.0.1", config[key]))
            except OSError as exc:
                raise LoopError(f"E2E port unavailable: {config[key]}") from exc
    finally:
        for sock in sockets:
            sock.close()


def parse_diagnostic(path, returncode):
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(result, dict) or type(result.get("valid")) is not bool or
                not isinstance(result.get("errors"), list) or returncode not in (0, 1, 2)):
            raise ValueError("invalid diagnostic shape/exit code")
        for error in result["errors"]:
            if not isinstance(error, dict) or any(not isinstance(error.get(k), str) for k in ("path", "code", "message")):
                raise ValueError("invalid error item")
        if ((returncode == 0) != result["valid"] or
                result["valid"] != (not result["errors"])):
            raise ValueError("inconsistent diagnostic/exit code")
        return result
    except (OSError, ValueError, UnicodeError) as exc:
        raise LoopError("D1b diagnostic parser failed") from exc


def execute(stage, directory, config, attempt):
    prefix = f"{stage.id}-{attempt}"
    stdout = directory / (prefix + ".stdout.log")
    stderr = directory / (prefix + ".stderr.log")
    result = {"command": stage.command, "cwd": stage.cwd, "target": stage.target,
              "started_at": now(), "exit_code": None, "status": "operational_error",
              "stdout": str(stdout), "stderr": str(stderr), "diagnostic": None}
    child = None
    started = time.monotonic()
    try:
        if stage.e2e:
            check_ports(config)
        with stdout.open("wb") as out, stderr.open("wb") as err:
            child = spawn(stage.command, cwd=stage.cwd,
                          env=child_environment(directory, config, stage.e2e),
                          stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            result["exit_code"] = child.wait(timeout=config["stage_timeout_seconds"])
        result["status"] = "success" if result["exit_code"] == 0 else "failed"
        if stage.diagnostic:
            result["diagnostic"] = parse_diagnostic(stdout, result["exit_code"])
            if result["exit_code"] == 2:
                result["status"] = "operational_error"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except KeyboardInterrupt:
        result["status"] = "interrupted"
    except (OSError, LoopError) as exc:
        result["reason"] = str(exc) if isinstance(exc, LoopError) else type(exc).__name__
        result["status"] = "operational_error"
    finally:
        if child is not None:
            terminate(child)
            if result["exit_code"] is None:
                result["exit_code"] = child.returncode
        result["finished_at"] = now()
        result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result
