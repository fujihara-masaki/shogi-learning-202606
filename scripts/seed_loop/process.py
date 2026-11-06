"""Owned process groups only; no shell evaluation or global process searches."""
import os
import signal
import subprocess


def spawn(command, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, shell=False, **kwargs)


def terminate(child):
    if os.name == "nt":
        # PID is the handle we created, never a caller-supplied process selector.
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        # Even if the parent exited, descendants may still own its process group.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
