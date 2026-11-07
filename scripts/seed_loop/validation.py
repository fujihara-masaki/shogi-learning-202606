"""Fixed validation profiles calling the existing repository gates."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

from .process import spawn
from .ownership import RECOVERY, recovery_problem
from .state import LoopError, atomic_json, now, read_json


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
    interrupted = False
    started = time.monotonic()
    owner_path = directory / (prefix + ".ownership.json")
    spec_path = directory / (prefix + ".spec.json")
    result_path = directory / (prefix + ".result.json")
    supervisor_log = directory / (prefix + ".supervisor.log")
    token = uuid.uuid4().hex
    result.update(ownership=str(owner_path), supervisor_log=str(supervisor_log))
    try:
        problem = recovery_problem(directory)
        if problem:
            result.update(reason=problem["reason"], recovery=problem["recovery"], cleanup_confirmed=False)
            return result
        if stage.e2e:
            check_ports(config)
        atomic_json(spec_path, {"token": token, "command": stage.command, "cwd": stage.cwd,
                               "timeout": config["stage_timeout_seconds"], "owner": str(owner_path),
                               "result": str(result_path), "stdout": str(stdout), "stderr": str(stderr)})
        atomic_json(owner_path, {"schema_version": 1, "token": token,
                                "status": "starting", "cleanup_confirmed": False})
        with supervisor_log.open("wb") as log:
            try:
                child = spawn([sys.executable, str(Path(__file__).with_name("supervisor.py")), str(spec_path)],
                              cwd=stage.cwd, env=child_environment(directory, config, stage.e2e),
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            except OSError:
                atomic_json(owner_path, {"schema_version": 1, "token": token, "status": "cleaned",
                                        "cleanup_confirmed": True, "reason": "supervisor_not_started"})
                raise
            try:
                child.wait(timeout=config["stage_timeout_seconds"] + 15)
            except (KeyboardInterrupt, subprocess.TimeoutExpired) as exc:
                interrupted = isinstance(exc, KeyboardInterrupt)
                # EOF is the guard's cancellation request; it cleans detached descendants too.
                child.stdin.close()
                try:
                    child.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    result.update(reason="supervisor_not_finished", cleanup_confirmed=False,
                                  recovery=RECOVERY)
                    return result
        completed = read_json(result_path)
        owner = read_json(owner_path)
        if (not isinstance(completed, dict) or completed.get("token") != token or
                not isinstance(owner, dict) or owner.get("token") != token or
                completed.get("status") not in ("success", "failed", "timeout", "interrupted", "operational_error") or
                (completed.get("status") == "success" and
                 (completed.get("exit_code") != 0 or child.returncode != 0))):
            raise LoopError("invalid supervisor result/attempt identity")
        result.update(completed)
        if owner.get("cleanup_confirmed") is not True or owner.get("status") != "cleaned":
            result.update(status="operational_error", reason="cleanup_unconfirmed", recovery=RECOVERY)
        elif interrupted:
            result["status"] = "interrupted"
        if result["status"] == "success" or (stage.diagnostic and result["status"] == "failed"):
            if stage.diagnostic:
                result["diagnostic"] = parse_diagnostic(stdout, result["exit_code"])
                if result["exit_code"] == 2:
                    result["status"] = "operational_error"
    except (OSError, LoopError) as exc:
        result["reason"] = str(exc) if isinstance(exc, LoopError) else type(exc).__name__
        result["status"] = "operational_error"
        if owner_path.exists():
            result["recovery"] = RECOVERY
    finally:
        if child is not None and child.stdin is not None and not child.stdin.closed:
            child.stdin.close()  # Parent writes no buffered data on this lifecycle pipe.
        result["finished_at"] = now()
        result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result
