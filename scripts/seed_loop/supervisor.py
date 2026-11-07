"""One validation attempt, independent of controller lifetime. No inference or DB code."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import time

# Direct script launch also works when a test's validation cwd is another repository.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.seed_loop.process_tree import owned_tree
from scripts.seed_loop.state import atomic_json, file_lock, now, read_json


def supervise(spec_path):
    spec = read_json(spec_path)
    owner_path = Path(spec['owner'])
    owner = read_json(owner_path)
    lost = threading.Event()
    def parent_pipe():
        try:
            os.read(sys.stdin.fileno(), 1)
        except OSError:
            pass  # A broken lifecycle pipe is also a lost controller.
        finally:
            lost.set()
    threading.Thread(target=parent_pipe, daemon=True).start()
    tree = None
    child = None
    result = {'schema_version':1, 'token':spec['token'], 'status':'operational_error', 'exit_code':None, 'started_at':now()}
    with file_lock(owner_path.parent / 'execution.lock'):
        owner.update(status='supervising', supervisor_pid=os.getpid(), started_at=now())
        atomic_json(owner_path, owner)
        try:
            tree = owned_tree()  # Establish ownership before any validation process can run.
            if lost.is_set():
                result.update(status='interrupted', reason='controller_lost_before_launch')
            else:
                with open(spec['stdout'],'wb') as out, open(spec['stderr'],'wb') as err:
                    child = tree.start(spec['command'], cwd=spec['cwd'], env=os.environ,
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                    owner.update(root_pid=child.pid, owned_processes=tree.identities())
                    atomic_json(owner_path, owner)
                    deadline = time.monotonic() + spec['timeout']
                    while child.poll() is None:
                        if lost.is_set():
                            result.update(status='interrupted', reason='controller_lost')
                            break
                        if time.monotonic() >= deadline:
                            result.update(status='timeout')
                            break
                        lost.wait(0.02)
                    else:
                        result['status'] = 'success' if child.returncode == 0 else 'failed'
        except OSError as exc:
            result.update(status='operational_error', reason=type(exc).__name__)
        finally:
            confirmed = tree is None  # Backend setup failure occurred before spawning any child.
            try:
                if tree is not None:
                    try:
                        owner['owned_processes'] = tree.identities()
                        atomic_json(owner_path, owner)
                    except OSError as exc:
                        result['journal_error'] = type(exc).__name__
                        result.update(status='operational_error', reason='ownership_journal_io_error')
                    # Diagnostic writes must never prevent an attempt to end owned children.
                    confirmed = tree.cleanup()
            except (OSError, subprocess.TimeoutExpired) as exc:
                result['cleanup_error'] = type(exc).__name__
                confirmed = False
            finally:
                if tree is not None:
                    tree.close()
            if child is not None:
                result['exit_code'] = child.poll()
            result.update(cleanup_confirmed=confirmed, finished_at=now())
            if not confirmed:
                result.update(status='operational_error', reason='cleanup_unconfirmed')
            # Keep result first; a crash before the clean journal remains a safe refusal.
            atomic_json(spec['result'], result)
            owner.update(status='cleaned' if confirmed else 'cleanup_unconfirmed',
                         cleanup_confirmed=confirmed, finished_at=now(),
                         result=spec['result'])
            atomic_json(owner_path, owner)
    return 0 if confirmed else 2


if __name__ == '__main__':
    raise SystemExit(supervise(Path(sys.argv[1])))
