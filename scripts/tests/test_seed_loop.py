"""Boundary tests: real D1b, subprocess protocol and durable recovery."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.seed_loop.controller import control, pause, replay
from scripts.seed_loop.state import (LoopError, Store, atomic_json, config_from,
                                    identity, read_json)
from scripts.seed_loop.usage import AppServerUsage, decision, normalize
from scripts.seed_loop.validation import (Stage, check_ports, child_environment,
                                          execute, plan)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


def snapshot(primary=0, secondary=0):
    return {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": primary},
                           "secondary": {"usedPercent": secondary}}}


def success(*_):
    return {"status": "success", "exit_code": 0, "finished_at": "simulated-test"}


@contextmanager
def repo():
    with tempfile.TemporaryDirectory(prefix="seed 日本語 空白 ") as directory:
        root = Path(directory)
        for name in ("backend/app/wikipedia_opening_validator.py",
                     "backend/app/wikipedia_opening_artifact.schema.json",
                     "backend/scripts/validate_wikipedia_opening_artifact.py",
                     "backend/app/wikipedia_opening_artifacts/yokofudori-2c-pawn.json"):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (root / ".gitignore").write_text(".seed-loop/\nwork/\n__pycache__/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                        "user.email=test@example.test", "commit", "-qm", "baseline"], check=True)
        yield root


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.config = config_from()

    def test_absolute_thresholds_and_multiple_windows(self):
        for value, expected in [(0, None), (24.999, None), (25, "no_new_task"),
                                (29.999, "no_new_task"), (30, "budget_stop"), (31, "budget_stop")]:
            for which in (0, 1):
                with self.subTest(value=value, window=which):
                    values = [0, 0]
                    values[which] = value
                    self.assertEqual(decision(normalize(snapshot(*values), self.config), self.config), expected)

    def test_null_missing_invalid_are_unknown(self):
        for value in (None, -1, 101, True, "0", float("nan")):
            with self.subTest(value=value):
                self.assertEqual(normalize(snapshot(value), self.config)["status"], "unknown")
        for result in ({}, {"rateLimits": {}}, {"rateLimits": {"primary": {"usedPercent": 0}}}):
            self.assertEqual(normalize(result, self.config)["status"], "unknown")

    def test_optional_metadata_and_explicit_window(self):
        result = normalize(snapshot(4, 6), self.config)
        self.assertEqual(result["status"], "known")
        self.assertIsNone(result["windows"]["primary"]["resets_at"])
        config = {**self.config, "windows": ["primary"]}
        self.assertEqual(normalize({"rateLimits": {"primary": {"usedPercent": 2}}}, config)["status"], "known")

    def test_only_selected_bucket_and_compatibility(self):
        data = {"rateLimits": snapshot(90)["rateLimits"], "rateLimitsByLimitId": {
            "codex": snapshot(1)["rateLimits"], "other": snapshot(100)["rateLimits"]}}
        self.assertIsNone(decision(normalize(data, self.config), self.config))
        data["rateLimitsByLimitId"] = {}
        self.assertEqual(normalize(data, self.config)["reason"], "bucket_unavailable")
        self.assertEqual(normalize(snapshot(), {**self.config, "bucket": "other"})["status"], "unknown")
        self.assertEqual(normalize({"rateLimits": {"primary": {"usedPercent": 0}}},
                                  {**self.config, "bucket": "other"})["status"], "unknown")

    def test_stale_future_and_reset_crossing(self):
        at = datetime.now(timezone.utc)
        for offset in (-121, 1):
            usage = normalize(snapshot(), self.config, observed_at=(at + timedelta(seconds=offset)).isoformat())
            self.assertEqual(decision(usage, self.config, at), "usage_stale")
        data = snapshot()
        data["rateLimits"]["primary"]["resetsAt"] = int(at.timestamp()) - 1
        old = normalize(data, self.config, observed_at=(at - timedelta(seconds=2)).isoformat())
        self.assertEqual(decision(old, self.config, at), "usage_stale")
        fresh = normalize(data, self.config, observed_at=at.isoformat())
        self.assertIsNone(decision(fresh, self.config, at))

    def test_bad_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config.json"
            for update in ({"schema_version": 2}, {"bucket": ""}, {"windows": []},
                           {"new_task_percent": 31}, {"stage_timeout_seconds": 0},
                           {"e2e_frontend_port": 18000}, {"unknown": True}):
                atomic_json(p, update)
                with self.subTest(update=update), self.assertRaises(LoopError):
                    config_from(p)


class ProtocolTests(unittest.TestCase):
    def test_real_adapter_over_stdio(self):
        for mode, status, reason in [("valid", "known", None), ("error", "unknown", "rpc_error"),
                                     ("eof", "unknown", "eof"), ("timeout", "unknown", "timeout"),
                                     ("malformed", "unknown", "malformed_protocol"),
                                     ("unsupported", "unsupported", "unsupported_protocol"),
                                     ("handshake-error", "unsupported", "unsupported_protocol")]:
            with self.subTest(mode=mode):
                config = {**config_from(), "usage_timeout_seconds": 0.5 if mode == "timeout" else 3}
                usage = AppServerUsage(config, [sys.executable, str(FIXTURES / "fake_app_server.py"), mode], "fake-v1").read()
                self.assertEqual(usage["status"], status)
                self.assertEqual(usage["reason"], reason)
                self.assertNotIn("SECRET", json.dumps(usage))
                if status == "known":
                    self.assertEqual(usage["windows"]["primary"]["used_percent"], 24)
                    self.assertEqual(usage["selected_limit_id"], "codex")

    def test_missing_real_cli_does_not_fallback(self):
        config = {**config_from(), "codex_binary": "codex-executable-does-not-exist"}
        usage = AppServerUsage(config).read()
        self.assertEqual(usage["status"], "unknown")
        self.assertEqual(usage["provider"], "codex-app-server")


class ValidationTests(unittest.TestCase):
    def test_real_d1b_exit_codes_and_json(self):
        config = config_from()
        with repo() as root:
            directory = root / ".seed-loop"
            directory.mkdir()
            original = plan(root, "artifacts")[0]
            for index, (content, rc, status) in enumerate([(None, 0, "success"), ("{}", 1, "failed"), ("{", 2, "operational_error")]):
                if content is None:
                    stage = original
                else:
                    path = directory / f"input-{index}.json"
                    path.write_text(content, encoding="utf-8")
                    stage = Stage("invalid", [sys.executable, original.command[1], str(path)], str(root), diagnostic=True)
                result = execute(stage, directory, config, index)
                self.assertEqual((result["exit_code"], result["status"]), (rc, status))
                self.assertEqual(result["diagnostic"]["valid"], rc == 0)
                self.assertTrue(Path(result["stdout"]).exists())

    def test_zero_targets_parser_timeout_interrupt_and_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(LoopError):
                plan(root, "artifacts")
            for name, code, diagnostic, expected in [
                ("parser", "print('broken')", True, "operational_error"),
                ("inconsistent", "print('{\"valid\":false,\"errors\":[]}')", True, "operational_error"),
                ("timeout", "import time; time.sleep(5)", False, "timeout")]:
                stage = Stage(name, [sys.executable, "-c", code], tmp, diagnostic=diagnostic)
                self.assertEqual(execute(stage, root, {**config_from(), "stage_timeout_seconds": 0.1}, 1)["status"], expected)
            stage = Stage("interrupt", [sys.executable, "-c", "pass"], tmp)
            from scripts.seed_loop.process import spawn as real_spawn
            def interrupting_spawn(*args, **kwargs):
                child = real_spawn(*args, **kwargs)
                wait = child.wait
                calls = 0
                def interrupted_wait(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        raise KeyboardInterrupt()
                    return wait(*args, **kwargs)
                child.wait = interrupted_wait
                return child
            with patch("scripts.seed_loop.validation.spawn", side_effect=interrupting_spawn):
                self.assertEqual(execute(stage, root, config_from(), 1)["status"], "interrupted")
            self.assertEqual(stage.record()["status"], "not_run")

    def test_e2e_sanitization_and_port_conflict(self):
        with patch.dict(os.environ, {"SHOGI_DB_PATH": "ordinary", "NEXT_MOVE_DB_PATH": "ordinary2",
                                     "SHOGI_CORS_ORIGINS": "ordinary3"}):
            env = child_environment(Path("/tmp/test"), config_from(), True)
        self.assertFalse(any(k in env for k in ("SHOGI_DB_PATH", "NEXT_MOVE_DB_PATH", "SHOGI_CORS_ORIGINS")))
        self.assertEqual(env["CI"], "1")
        self.assertEqual(env["PYTHON"], sys.executable)
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            with self.assertRaises(LoopError):
                check_ports({**config_from(), "e2e_backend_port": sock.getsockname()[1]})


class StateTests(unittest.TestCase):
    def test_atomic_replace_failure_preserves_old_state_and_utf8_crlf(self):
        with tempfile.TemporaryDirectory(prefix="状態 空白 ") as tmp:
            path = Path(tmp) / "状態.json"
            atomic_json(path, {"value": "将棋"})
            with patch("os.replace", side_effect=OSError("interrupted save")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"value": "new"})
            self.assertEqual(read_json(path), {"value": "将棋"})
            path.write_bytes(b'{\r\n "value": 3\r\n}\r\n')
            self.assertEqual(read_json(path), {"value": 3})
            self.assertEqual(list(Path(tmp).glob(".checkpoint-*")), [])

    def test_corrupt_state_is_not_initialized(self):
        with repo() as root:
            store = Store(root, "corrupt")
            atomic_json(store.path, {"schema_version": 1})
            before = store.path.read_bytes()
            with self.assertRaises(LoopError):
                control(root, "corrupt", config_from(), resume=True)
            self.assertEqual(store.path.read_bytes(), before)
            for bad in ("../escape", "空白", "a/b", ""):
                with self.assertRaises(LoopError):
                    Store(root, bad)

    def test_os_lock_exclusion_and_crash_release(self):
        with repo() as root:
            code = "from pathlib import Path; from scripts.seed_loop.state import Store; import sys; s=Store(Path(sys.argv[1]),'locked');\nwith s.lock():\n print('locked',flush=True)\n sys.stdin.readline()"
            p = subprocess.Popen([sys.executable, "-c", code, str(root)], cwd=ROOT,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self.assertEqual(p.stdout.readline().strip(), b"locked")
                with self.assertRaises(LoopError):
                    with Store(root, "locked").lock():
                        pass
            finally:
                p.kill()
                p.wait(timeout=5)
                p.stdin.close()
                p.stdout.close()
            with Store(root, "locked").lock():
                pass

    def test_dirty_and_untracked_identity_and_invalidation(self):
        with repo() as root:
            first = identity(root)
            (root / "追加 日本語.txt").write_text("untracked", encoding="utf-8")
            second = identity(root)
            self.assertEqual(first["head"], second["head"])
            self.assertNotEqual(first["digest"], second["digest"])
            self.assertIn("追加 日本語.txt", second["files"])
            self.assertTrue(second["dirty"])
            state = control(root, "dirty", config_from(), usage_reader=lambda: normalize(snapshot(30), config_from()))
            (root / "追加 日本語.txt").write_text("changed", encoding="utf-8")
            state = control(root, "dirty", config_from(), resume=True)
            self.assertEqual(state["stop_reason"], "inputs_changed")
            self.assertIn("追加 日本語.txt", state["invalidated_by"])

    def test_artifact_and_config_changes_invalidate(self):
        for kind in ("artifact", "config"):
            with self.subTest(kind=kind), repo() as root:
                config = config_from()
                control(root, "change", config, usage_reader=lambda: normalize(snapshot(30), config))
                if kind == "config":
                    config["stage_timeout_seconds"] += 1
                else:
                    p = next((root / "backend/app/wikipedia_opening_artifacts").glob("*.json"))
                    p.write_bytes(p.read_bytes() + b"\n")
                self.assertEqual(control(root, "change", config, resume=True)["stop_reason"], "inputs_changed")

    def test_invalidated_evidence_stays_invalid_after_revert(self):
        with repo() as root:
            config = config_from()
            control(root, "revert", config, usage_reader=lambda: normalize(snapshot(30), config))
            p = root / "untracked.py"
            p.write_text("change", encoding="utf-8")
            self.assertEqual(control(root, "revert", config, resume=True)["stop_reason"], "inputs_changed")
            p.unlink()
            with self.assertRaises(LoopError):
                control(root, "revert", config, resume=True)

    def test_new_stage_gate_and_drain_after_usage_increases(self):
        for value, reason in [(25, "no_new_task"), (30, "budget_stop")]:
            with self.subTest(value=value), repo() as root:
                source = next((root / "backend/app/wikipedia_opening_artifacts").glob("*.json"))
                shutil.copyfile(source, source.with_name("second.json"))
                config = config_from()
                usages = iter([snapshot(0), snapshot(value)])
                state = control(root, "increase", config, usage_reader=lambda: normalize(next(usages), config))
                self.assertEqual(state["stop_reason"], reason)
                self.assertEqual([s["status"] for s in state["stages"]], ["success", "not_run"])
                self.assertEqual(state["next_stage"], 1)

    def test_no_automatic_resume_and_no_same_run_concurrent_worker(self):
        with repo() as root:
            config = config_from()
            control(root, "paused", config, usage_reader=lambda: normalize(snapshot(30), config))
            with self.assertRaises(LoopError):
                control(root, "paused", config, usage_reader=lambda: normalize(snapshot(0), config))
            with Store(root, "paused").lock():
                with self.assertRaises(LoopError):
                    control(root, "paused", config, resume=True)

    def test_persist_real_results_and_recover_in_new_process_without_codex(self):
        with repo() as root:
            config = {**config_from(), "codex_binary": "not-installed"}
            state = control(root, "real", config, mode="validation-only")
            self.assertEqual(state["execution_status"], "completed")
            self.assertEqual(state["stages"][0]["attempts"][0]["diagnostic"], {"valid": True, "errors": []})
            result = subprocess.run([sys.executable, "-m", "scripts.seed_loop", "--root", str(root),
                                     "status", "--run-id", "real"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["execution_status"], "completed")
            self.assertEqual(state["source_review"], "not_performed")
            self.assertIsNone(state["pr"])
            with self.assertRaises(LoopError):
                control(root, "real", config, mode="validation-only")

    def test_budget_pause_resume_unknown_and_manual_drain(self):
        with repo() as root:
            config = config_from()
            reader = lambda: normalize(snapshot(30), config)
            state = control(root, "budget", config, usage_reader=reader)
            self.assertEqual(state["stop_reason"], "budget_stop")
            self.assertEqual(state["stages"][0]["attempts"], [])
            state = control(root, "budget", config, resume=True,
                            usage_reader=lambda: normalize(snapshot(None), config))
            self.assertEqual(state["stop_reason"], "usage_unknown")
            state = control(root, "budget", config, resume=True,
                            usage_reader=lambda: normalize(snapshot(0), config))
            self.assertEqual(state["execution_status"], "completed")
            def draining(stage, directory, cfg, attempt):
                pause(root, "manual")
                return execute(stage, directory, cfg, attempt)
            state = control(root, "manual", config, mode="validation-only", executor=draining)
            self.assertEqual((state["execution_status"], state["stop_reason"]), ("paused", "manual_pause"))
            self.assertEqual(state["stages"][0]["status"], "success")
            resumed = control(root, "manual", config, mode="validation-only", resume=True)
            self.assertEqual(resumed["execution_status"], "completed")
            self.assertEqual(len(resumed["stages"][0]["attempts"]), 1)

    def test_process_dies_after_stage_started_retry_is_explicit(self):
        with repo() as root:
            code = "from pathlib import Path; import os,sys; from scripts.seed_loop.controller import control; from scripts.seed_loop.state import config_from; control(Path(sys.argv[1]),'crash',config_from(),mode='validation-only',executor=lambda *args:os._exit(9))"
            result = subprocess.run([sys.executable, "-c", code, str(root)], cwd=ROOT)
            self.assertEqual(result.returncode, 9)
            state = Store(root, "crash").load()
            self.assertEqual(state["stages"][0]["status"], "running")
            state = control(root, "crash", config_from(), mode="validation-only", resume=True)
            attempts = state["stages"][0]["attempts"]
            self.assertEqual([a["status"] for a in attempts], ["interrupted", "success"])
            self.assertEqual(attempts[0]["reason"], "worker_lost")

    def test_post_result_crash_does_not_relaunch_recorded_success(self):
        with repo() as root:
            state = control(root, "done", config_from(), mode="validation-only")
            state["execution_status"] = "running"
            Store(root, "done").save(state)
            state = control(root, "done", config_from(), mode="validation-only", resume=True,
                            executor=lambda *_: self.fail("must not relaunch saved success"))
            self.assertEqual(state["execution_status"], "completed")

    def test_result_save_failure_never_reuses_unsaved_success(self):
        with repo() as root:
            original = Store.save
            calls = 0
            def saving(store, state):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("disk failure after result")
                original(store, state)
            with patch.object(Store, "save", saving), self.assertRaises(OSError):
                control(root, "disk", config_from(), mode="validation-only")
            self.assertEqual(Store(root, "disk").load()["stages"][0]["status"], "running")
            state = control(root, "disk", config_from(), mode="validation-only", resume=True)
            self.assertEqual([a["status"] for a in state["stages"][0]["attempts"]], ["interrupted", "success"])

    def test_replay_stays_paused_after_reset_until_explicit_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = replay(Path(tmp), FIXTURES / "pause-reset-resume.json", config_from())
            self.assertEqual([h["execution_status"] for h in result["history"]],
                             ["running", "paused", "paused", "running", "paused"])
            self.assertTrue(result["simulated"])
            self.assertEqual(result["validation"], "not_run")
            self.assertEqual(result["source_review"], "not_performed")
            self.assertEqual(read_json(result["record"])["mode"], "replay")


if __name__ == "__main__":
    unittest.main()
