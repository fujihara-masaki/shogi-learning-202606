"""Attempt leases and journals; uncertain cleanup never permits another launch."""
from pathlib import Path

from .state import LoopError, file_lock, read_json

RECOVERY = ("Inspect status, ownership/result JSON and supervisor log. If the supervisor is still "
            "cleaning, wait and resume again. For unconfirmed cleanup, verify the recorded "
            "OS identities and that all owned descendants have exited; do not kill a bare PID "
            "or bypass the guard with a new run ID. Archive the run after operator recovery.")


def recovery_problem(directory):
    directory = Path(directory)
    try:
        with file_lock(directory / "execution.lock"):
            for path in sorted(directory.glob("*.ownership.json")):
                owner = read_json(path)
                if (not isinstance(owner, dict) or type(owner.get("schema_version")) is not int or
                        owner["schema_version"] != 1 or not isinstance(owner.get("token"), str) or
                        owner.get("status") != "cleaned" or owner.get("cleanup_confirmed") is not True):
                    return {"reason": "cleanup_unconfirmed", "record": str(path), "recovery": RECOVERY}
                if owner.get("reason") != "supervisor_not_started":
                    result_path = path.with_name(path.name.removesuffix("ownership.json") + "result.json")
                    result = read_json(result_path)
                    if (not isinstance(result, dict) or result.get("token") != owner["token"] or
                            result.get("cleanup_confirmed") is not True):
                        return {"reason": "cleanup_unconfirmed", "record": str(path), "recovery": RECOVERY}
    except LoopError as exc:
        if str(exc) == "run is locked by an active worker":
            return {"reason": "previous_attempt_active", "recovery": RECOVERY}
        return {"reason": "cleanup_unconfirmed", "recovery": RECOVERY}
    return None
