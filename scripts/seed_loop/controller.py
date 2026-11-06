"""Checkpoint orchestration. A stage is bounded, read-only validation work."""
import uuid

from .state import LoopError, Store, atomic_json, digest, environment, identity, now, read_json
from .usage import AppServerUsage, decision, normalize
from .validation import execute, plan


def stop(store, state, reason, failed=False):
    state["execution_status"] = "failed" if failed else "paused"
    state["stop_reason"] = reason
    store.save(state)
    return state


def control(root, run_id, config, profile="artifacts", mode="controlled", resume=False,
            usage_reader=None, executor=execute):
    store = Store(root, run_id)
    with store.lock():
        stages = plan(root, profile)
        current = identity(root)
        if resume:
            state = store.load()
            if state.get("invalidated_by"):
                raise LoopError("previous evidence was invalidated; start a new run ID")
            if state["mode"] != mode or state["profile"] != profile:
                raise LoopError("mode/profile changed; start a new run ID")
            changes = []
            if state["config_hash"] != digest(config):
                changes.append("config")
            old = state["identity"]
            if old != current:
                changes += [name for name in sorted(set(old["files"]) | set(current["files"]))
                            if old["files"].get(name) != current["files"].get(name)]
                if old["head"] != current["head"]:
                    changes.append("HEAD")
                if not changes:
                    changes.append("Git/CI context")
            if [s["id"] for s in state["stages"]] != [s.id for s in stages]:
                changes.append("stage plan")
            if changes:
                state["invalidated_by"] = changes
                return stop(store, state, "inputs_changed")
            if state["execution_status"] == "completed":
                return state
            if store.pause_path.exists():
                store.pause_path.unlink()
            # Previous running result is unknown; retry only our fixed validations.
            for s in state["stages"]:
                if s["status"] == "running":
                    s["status"] = "interrupted"
                    s["attempts"][-1].update(status="interrupted", reason="worker_lost",
                                               finished_at=now())
        else:
            if store.path.exists():
                raise LoopError("run already exists; use explicit resume or a new run ID")
            state = {"schema_version": 1, "config_version": config["schema_version"],
                     "run_id": run_id, "task_id": "existing-bundled-validation",
                     "mode": mode, "profile": profile, "phase": "validation",
                     "execution_status": "running", "stop_reason": None, "next_stage": 0,
                     "identity": current, "config_hash": digest(config),
                     "queue_hash": None, "queue": "implicit sorted existing bundled artifacts; no seed tasks",
                     "artifact_hashes": {k: v for k, v in current["files"].items()
                                         if k.startswith("backend/app/wikipedia_opening_artifacts/")},
                     "environment": environment(), "created_at": now(), "usage": None,
                     "usage_history": [], "source_review": "not_performed",
                     "pr": None, "repair_attempts": 0,
                     "stages": [s.record() for s in stages]}
        state.update(execution_status="running", stop_reason=None)
        store.save(state)
        reader = usage_reader or AppServerUsage(config).read

        def gate():
            if store.pause_path.exists():
                return "manual_pause"
            if mode == "controlled":
                state["usage"] = reader()
                state["usage_history"].append(state["usage"])
                return decision(state["usage"], config)
            return None

        try:
            while state["next_stage"] < len(stages):
                reason = gate()
                if reason:
                    return stop(store, state, reason)
                index = state["next_stage"]
                stage = state["stages"][index]
                stage["status"] = "running"
                stage["attempts"].append({"status": "running", "started_at": now(),
                                           "command": stages[index].command, "exit_code": None})
                store.save(state)  # Before launch: no manufactured success after crash.
                result = executor(stages[index], store.directory, config, len(stage["attempts"]))
                stage["attempts"][-1] = result
                stage["status"] = result["status"]
                if result["status"] == "success":
                    state["next_stage"] += 1
                store.save(state)  # A result must reach disk before it is reusable.
                after = identity(root)
                if after != current:
                    state["invalidated_by"] = [k for k in sorted(set(current["files"]) | set(after["files"]))
                                               if current["files"].get(k) != after["files"].get(k)] or ["Git/CI context"]
                    return stop(store, state, "inputs_changed")
                if result["status"] != "success":
                    return stop(store, state, "stage_" + result["status"],
                                failed=result["status"] != "interrupted")
                # Even the last stage's result can end in a budget/manual pause.
                reason = gate()
                if reason:
                    return stop(store, state, reason)
            state.update(phase="validated", execution_status="completed", stop_reason=None)
            store.save(state)
            return state
        except KeyboardInterrupt:
            return stop(store, state, "interrupted")


def pause(root, run_id):
    store = Store(root, run_id)
    state = store.load()  # Fail closed; never initialize a missing/corrupt run.
    if state["execution_status"] == "completed":
        return state
    atomic_json(store.pause_path, {"requested_at": now(), "reason": "manual_pause"})
    try:
        with store.lock():
            state = store.load()
            if state["execution_status"] != "completed":
                return stop(store, state, "manual_pause")
    except LoopError as exc:
        if "locked by an active worker" not in str(exc):
            raise
    return {**state, "pause_requested": True,
            "pause_policy": "drain current stage within its timeout, then checkpoint"}


def replay(root, fixture, config):
    """Explicit simulated transitions. No validation success or source review claim."""
    data = read_json(fixture)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("events"), list):
        raise LoopError("invalid replay fixture")
    state = {"schema_version": 1, "mode": "replay", "simulated": True,
             "execution_status": "paused", "phase": "simulation", "stop_reason": "not_started",
             "validation": "not_run", "source_review": "not_performed", "history": [],
             "fixture_hash": digest(data), "config_hash": digest(config)}
    for event in data["events"]:
        if not isinstance(event, dict) or event.get("action") not in ("start", "resume", "observe", "pause"):
            raise LoopError("invalid replay event")
        action = event["action"]
        if action == "pause":
            state.update(execution_status="paused", stop_reason="manual_pause")
        else:
            usage = normalize(event.get("result"), config, "fixture", "simulated",
                              event.get("observed_at"))
            reason = decision(usage, config)
            state["usage"] = usage
            if action in ("start", "resume") or state["execution_status"] == "running":
                state.update(execution_status="paused" if reason else "running", stop_reason=reason)
        state["history"].append({"action": action, "execution_status": state["execution_status"],
                                 "stop_reason": state["stop_reason"]})
    path = root / ".seed-loop" / "replays" / (uuid.uuid4().hex + ".json")
    atomic_json(path, state)
    return {**state, "record": str(path)}
