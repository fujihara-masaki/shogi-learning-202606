"""Read-only Codex App Server JSONL adapter and absolute-used budget policy."""
from datetime import datetime, timezone
import json
import math
import queue
import subprocess
import threading
import time

from .process import spawn, terminate
from .state import now


class ProtocolError(Exception):
    def __init__(self, reason):
        self.reason = reason


def unknown(reason, bucket, version=None, provider="codex-app-server"):
    return {"status": "unsupported" if reason == "unsupported_protocol" else "unknown",
            "reason": reason, "provider": provider, "bucket": bucket,
            "cli_version": version, "observed_at": now(), "windows": {}}


def normalize(result, config, version=None, provider="codex-app-server", observed_at=None):
    """Select exactly one bucket; absence of a monitored window is unknown."""
    bucket = config["bucket"]
    if not isinstance(result, dict):
        return unknown("malformed_response", bucket, version, provider)
    multi = result.get("rateLimitsByLimitId")
    selection = "rateLimitsByLimitId"
    if multi is not None:
        if not isinstance(multi, dict) or bucket not in multi:
            return unknown("bucket_unavailable", bucket, version, provider)
        selected = multi[bucket]
    else:
        selected = result.get("rateLimits")
        selection = "rateLimits"
        # Historical payload without limitId is only compatible with codex.
        if not isinstance(selected, dict) or selected.get("limitId", "codex") not in (bucket, None):
            return unknown("bucket_unavailable", bucket, version, provider)
        if selected.get("limitId") is None and bucket != "codex":
            return unknown("bucket_identity_unavailable", bucket, version, provider)
    if not isinstance(selected, dict) or selected.get("limitId") not in (None, bucket):
        return unknown("bucket_identity_mismatch", bucket, version, provider)
    windows = {}
    for name in config["windows"]:
        w = selected.get(name)
        if not isinstance(w, dict):
            return unknown("window_unavailable", bucket, version, provider)
        used = w.get("usedPercent")
        if type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100:
            return unknown("used_percent_unavailable", bucket, version, provider)
        normalized = {"used_percent": used}
        for source, target in (("windowDurationMins", "window_duration_mins"), ("resetsAt", "resets_at")):
            value = w.get(source)
            if value is not None and (type(value) is not int or value < 0):
                return unknown("malformed_window", bucket, version, provider)
            normalized[target] = value
        windows[name] = normalized
    return {"status": "known", "reason": None, "provider": provider, "bucket": bucket,
            "selection": selection, "selected_limit_id": selected.get("limitId") or bucket,
            "observed_at": observed_at or now(), "cli_version": version, "windows": windows}


def decision(usage, config, at=None):
    """A snapshot never grants permission when missing, stale or crossing a reset."""
    if not isinstance(usage, dict) or usage.get("status") != "known":
        return "usage_unknown"
    try:
        observed = datetime.fromisoformat(usage["observed_at"])
        current = at or datetime.now(timezone.utc)
        age = (current - observed).total_seconds()
        if age < 0 or age > config["max_usage_age_seconds"]:
            return "usage_stale"
        if usage["bucket"] != config["bucket"]:
            return "usage_unknown"
        values = []
        for name in config["windows"]:
            w = usage["windows"][name]
            value = w["used_percent"]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                return "usage_unknown"
            reset = w.get("resets_at")
            if reset is not None and observed.timestamp() < reset <= current.timestamp():
                return "usage_stale"
            values.append(value)
    except (KeyError, ValueError, TypeError, OverflowError):
        return "usage_unknown"
    if any(x >= config["stop_percent"] for x in values):
        return "budget_stop"
    if any(x >= config["new_task_percent"] for x in values):
        return "no_new_task"
    return None


class AppServerUsage:
    def __init__(self, config, command=None, version=None):
        self.config = config
        self.command = command or [config["codex_binary"], "app-server", "--listen", "stdio://"]
        self.version = version

    def read(self):
        config = self.config
        version = self.version
        child = None
        reader = None
        closing = threading.Event()
        observation = None
        cleanup_errors = []
        try:
            if version is None:
                p = subprocess.run([config["codex_binary"], "--version"], capture_output=True,
                                   text=True, timeout=config["usage_timeout_seconds"])
                if p.returncode:
                    raise ProtocolError("cli_unavailable")
                version = p.stdout.strip()[:100]
            child = spawn(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
            messages = queue.Queue(maxsize=256)

            def enqueue(message):
                while not closing.is_set():
                    try:
                        messages.put(message, timeout=0.1)
                        return
                    except queue.Full:
                        continue

            def receive():
                try:
                    while True:
                        line = child.stdout.readline(1024 * 1024 + 1)
                        if not line:
                            enqueue(None)
                            return
                        if len(line) > 1024 * 1024:
                            enqueue(ProtocolError("oversized_message"))
                            return
                        enqueue(json.loads(line))
                except (ValueError, OSError):
                    enqueue(ProtocolError("malformed_protocol"))

            reader = threading.Thread(target=receive, daemon=True)
            reader.start()
            deadline = time.monotonic() + config["usage_timeout_seconds"]

            def send(message):
                child.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
                child.stdin.flush()

            def response(request_id):
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ProtocolError("timeout")
                    try:
                        message = messages.get(timeout=remaining)
                    except queue.Empty:
                        raise ProtocolError("timeout") from None
                    if message is None:
                        raise ProtocolError("eof")
                    if isinstance(message, ProtocolError):
                        raise message
                    if not isinstance(message, dict):
                        raise ProtocolError("malformed_protocol")
                    if "method" in message:
                        if "id" in message:
                            raise ProtocolError("unsupported_server_request")
                        # Partial notifications are never merged into a snapshot.
                        continue
                    if type(message.get("id")) is not int or message["id"] != request_id:
                        continue
                    if "error" in message:
                        error = message["error"]
                        code = error.get("code") if isinstance(error, dict) else None
                        raise ProtocolError("unsupported_protocol" if code == -32601 else "rpc_error")
                    if "result" not in message or not isinstance(message["result"], dict):
                        raise ProtocolError("malformed_response")
                    return message["result"]

            send({"id": 1, "method": "initialize", "params": {
                "clientInfo": {"name": "shogi_seed_loop", "title": "Seed validation", "version": "1"},
                "capabilities": {"experimentalApi": False}}})
            response(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "account/rateLimits/read", "params": {}})
            result = response(2)
            observation = normalize(result, config, version)
        except ProtocolError as exc:
            observation = unknown(exc.reason, config["bucket"], version)
        except subprocess.TimeoutExpired:
            observation = unknown("timeout", config["bucket"], version)
        except BrokenPipeError:
            observation = unknown("closed_stdin", config["bucket"], version)
        except OSError:
            observation = unknown("cli_or_transport_unavailable", config["bucket"], version)
        finally:
            if child is not None:
                closing.set()
                try:
                    terminate(child)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    cleanup_errors.append("terminate_" + type(exc).__name__)
                    try:
                        child.kill()  # The held Popen handle, never a persisted bare PID.
                        child.wait(timeout=2)
                    except (OSError, subprocess.TimeoutExpired) as fallback:
                        cleanup_errors.append("fallback_" + type(fallback).__name__)
                if reader is not None:
                    reader.join(timeout=2)
                for stream in (child.stdin, child.stdout):
                    if stream is child.stdout and reader is not None and reader.is_alive():
                        cleanup_errors.append("stdout_reader_not_stopped")
                        continue  # Do not block forever on a BufferedReader lock.
                    try:
                        stream.close()
                    except OSError as exc:
                        cleanup_errors.append("stream_close_" + type(exc).__name__)
        if cleanup_errors:
            if observation is not None:
                observation["cleanup_errors"] = cleanup_errors
                if observation["status"] == "known":
                    observation = {**unknown("cleanup_failed", config["bucket"], version),
                                   "cleanup_errors": cleanup_errors}
        return observation
