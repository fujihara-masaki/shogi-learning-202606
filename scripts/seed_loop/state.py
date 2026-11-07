"""Versioned configuration, content identity and crash-safe local checkpoints."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile


class LoopError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError) as exc:
        raise LoopError(f"invalid JSON file: {path} ({type(exc).__name__})") from exc


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


DEFAULT_CONFIG = {
    "schema_version": 1, "bucket": "codex", "windows": ["primary", "secondary"],
    "new_task_percent": 25, "stop_percent": 30, "max_usage_age_seconds": 120,
    "usage_timeout_seconds": 15, "stage_timeout_seconds": 900,
    "codex_binary": "codex", "e2e_backend_port": 18000, "e2e_frontend_port": 15173,
}


def config_from(path=None):
    config = dict(DEFAULT_CONFIG)
    if path:
        supplied = read_json(path)
        if not isinstance(supplied, dict) or set(supplied) - set(config):
            raise LoopError("config must be an object with known keys")
        config.update(supplied)
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise LoopError("unsupported config schema_version")
    if not isinstance(config["bucket"], str) or not config["bucket"].strip():
        raise LoopError("bucket must be explicit")
    windows = config["windows"]
    if (not isinstance(windows, list) or not windows or
            any(w not in ("primary", "secondary") for w in windows) or
            len(set(windows)) != len(windows)):
        raise LoopError("windows must select primary and/or secondary once")
    for key in ("new_task_percent", "stop_percent", "max_usage_age_seconds",
                "usage_timeout_seconds", "stage_timeout_seconds"):
        value = config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise LoopError(f"invalid config {key}")
    if not 0 < config["new_task_percent"] <= config["stop_percent"] <= 100:
        raise LoopError("thresholds must satisfy 0 < new_task <= stop <= 100")
    for key in ("e2e_backend_port", "e2e_frontend_port"):
        if type(config[key]) is not int or not 1024 <= config[key] <= 65535:
            raise LoopError(f"invalid {key}")
    if config["e2e_backend_port"] == config["e2e_frontend_port"]:
        raise LoopError("E2E ports must differ")
    if not isinstance(config["codex_binary"], str) or not config["codex_binary"]:
        raise LoopError("codex_binary must be an executable path")
    return config


def git(root, *args):
    try:
        return subprocess.check_output(["git", "-C", str(root), *args],
                                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LoopError("Git inspection failed") from exc


def identity(root):
    """Hash tracked and nonignored untracked content, including dirty additions."""
    names = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    files = {}
    for raw in sorted(set(names.split(b"\0")) - {b""}):
        name = os.fsdecode(raw)
        # Output directories must never contribute to their own evidence.
        if name.startswith((".seed-loop/", "work/")):
            continue
        path = root / name
        if path.is_symlink():
            content = b"symlink:" + os.fsencode(os.readlink(path))
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b"missing"
        files[name] = hashlib.sha256(content).hexdigest()
    head = git(root, "rev-parse", "HEAD").decode().strip()
    return {"head": head, "files": files, "digest": digest(files),
            "dirty": bool(git(root, "status", "--porcelain")),
            "base_sha": os.environ.get("SEED_LOOP_BASE_SHA"),
            "pr_head_sha": os.environ.get("SEED_LOOP_HEAD_SHA"),
            "checkout_sha": head}


def environment():
    return {"python": sys.version.split()[0], "python_executable": sys.executable,
            "platform": platform.platform(), "node": tool_version("node"),
            "npm": tool_version("npm")}


def tool_version(tool):
    try:
        # Windows .cmd handling is limited to these fixed version commands.
        command = [tool, "--version"] if os.name != "nt" else (
            ["cmd.exe", "/d", "/s", "/c", "npm.cmd", "--version"]
            if tool == "npm" else [tool, "--version"])
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return p.stdout.strip()[:100] if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class Store:
    def __init__(self, root, run_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
            raise LoopError("invalid run ID (ASCII letters/digits, _ and -, max 80)")
        self.directory = Path(root) / ".seed-loop" / "runs" / run_id
        self.run_id = run_id
        self.path = self.directory / "state.json"
        self.pause_path = self.directory / "pause.json"

    def lock(self):
        return file_lock(self.directory / "worker.lock")

    def load(self):
        s = read_json(self.path)
        if (not isinstance(s, dict) or type(s.get("schema_version")) is not int or s["schema_version"] != 1 or
                s.get("run_id") != self.run_id or
                s.get("profile") not in ("artifacts", "full") or
                s.get("phase") not in ("validation", "validated") or
                s.get("execution_status") not in ("running", "paused", "completed", "failed") or
                s.get("mode") not in ("validation-only", "controlled") or
                not isinstance(s.get("stages"), list) or
                not isinstance(s.get("identity"), dict) or
                not isinstance(s["identity"].get("files"), dict) or
                not isinstance(s["identity"].get("head"), str) or
                not isinstance(s["identity"].get("digest"), str) or
                not isinstance(s.get("usage_history"), list) or
                not isinstance(s.get("config_hash"), str) or
                type(s.get("next_stage")) is not int or
                not 0 <= s["next_stage"] <= len(s["stages"])):
            raise LoopError("corrupt or unsupported state; preserved for diagnosis")
        for stage in s["stages"]:
            if (not isinstance(stage, dict) or not isinstance(stage.get("id"), str) or
                    stage.get("status") not in ("not_run", "running", "success", "failed",
                                               "timeout", "interrupted", "operational_error") or
                    not isinstance(stage.get("attempts"), list)):
                raise LoopError("corrupt stage; state preserved")
            if (stage["status"] != "not_run" and not stage["attempts"]) or any(
                    not isinstance(a, dict) or a.get("status") not in (
                        "running", "success", "failed", "timeout", "interrupted", "operational_error")
                    for a in stage["attempts"]):
                raise LoopError("corrupt attempt; state preserved")
            if stage["attempts"] and stage["status"] != stage["attempts"][-1]["status"]:
                raise LoopError("inconsistent stage attempt; state preserved")
        if len({stage["id"] for stage in s["stages"]}) != len(s["stages"]):
            raise LoopError("duplicate checkpoint stages")
        if any(s["stages"][i]["status"] != "success" for i in range(s["next_stage"])):
            raise LoopError("inconsistent checkpoint; state preserved")
        if s["execution_status"] == "completed" and s["next_stage"] != len(s["stages"]):
            raise LoopError("inconsistent completed checkpoint")
        return s

    def save(self, state):
        state["updated_at"] = now()
        atomic_json(self.path, state)


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # OS locks release after crashes. Never unlink the shared lock inode.
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LoopError("run is locked by an active worker") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
