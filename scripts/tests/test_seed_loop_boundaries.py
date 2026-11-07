"""Regressions A-E: actual children/stdio plus deterministic stop ordering."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from test_seed_loop import ROOT, repo, snapshot
from scripts.seed_loop.controller import control, pause
from scripts.seed_loop.state import Store, atomic_json, config_from
from scripts.seed_loop.ownership import recovery_problem
from scripts.seed_loop.usage import AppServerUsage, normalize
from scripts.seed_loop.validation import Stage, execute, npm


def until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("fixture synchronization timed out")


class ProcessReference:
    """Hold an OS identity before killing the controller, never kill a reused PID."""
    def __init__(self, pid):
        self.pid = pid
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.api = ctypes.WinDLL("kernel32", use_last_error=True)
            self.api.OpenProcess.restype = wintypes.HANDLE
            self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.api.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.api.OpenProcess(0x100001, False, pid)
            if not self.handle:
                if ctypes.get_last_error() == 87:
                    raise ProcessLookupError(pid)
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            self.handle = os.pidfd_open(pid)

    def alive(self):
        if os.name == "nt":
            return self.api.WaitForSingleObject(self.handle, 0) == 258
        import select
        return not select.select([self.handle], [], [], 0)[0]

    def close(self):
        if self.alive():
            if os.name == "nt":
                self.api.TerminateProcess(self.handle, 9)
            else:
                signal.pidfd_send_signal(self.handle, signal.SIGKILL)
        if os.name == "nt":
            self.api.CloseHandle(self.handle)
        else:
            os.close(self.handle)


class StopBoundaryTests(unittest.TestCase):
    def test_d_pause_while_usage_read_never_starts_not_run_stage(self):
        with repo() as root:
            entered, finish = threading.Event(), threading.Event()
            result, errors = [], []
            config = config_from()
            def reader():
                entered.set()
                if not finish.wait(5):
                    raise AssertionError("pause test failed to release usage read")
                return normalize(snapshot(), config)
            from unittest.mock import Mock
            executor = Mock(side_effect=AssertionError("stage must stay not_run"))
            def work():
                try:
                    result.append(control(root, "read-pause", config, usage_reader=reader, executor=executor))
                except BaseException as exc:
                    errors.append(exc)
            worker = threading.Thread(target=work)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                stopped = pause(root, "read-pause")
                self.assertTrue(stopped["pause_requested"])
                self.assertEqual(stopped["stages"][0]["status"], "not_run")
            finally:
                finish.set()
                worker.join(8)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            executor.assert_not_called()
            self.assertEqual(result[0]["stop_reason"], "manual_pause")
            self.assertEqual(result[0]["stages"][0]["attempts"], [])
            print(json.dumps({'boundary':'D','executor_calls':executor.call_count,'attempts':0,
                              'stop_reason':result[0]['stop_reason']}))

    def test_b_unconfirmed_or_corrupt_owner_refuses_resume_without_retry(self):
        for owner in ({"schema_version":1,"status":"cleanup_unconfirmed","cleanup_confirmed":False}, {}):
            with self.subTest(owner=owner), repo() as root:
                config = config_from()
                control(root, 'uncertain', config, usage_reader=lambda: normalize(snapshot(30), config))
                store = Store(root, 'uncertain')
                atomic_json(store.directory/'fixture.ownership.json', owner)
                state = control(root,'uncertain',config,resume=True,
                                executor=lambda *_: self.fail('uncertain ownership must not retry'))
                self.assertEqual(state['stop_reason'],'cleanup_unconfirmed')
                self.assertEqual(state['stages'][0]['attempts'],[])
                self.assertIn('recovery',state['recovery'])

    def test_e_final_stage_resume_refreshes_budget_unknown_and_stale(self):
        for condition in ("budget", "unknown", "stale"):
            with self.subTest(condition=condition), repo() as root:
                config = config_from()
                def blocked():
                    if condition == "budget":
                        return normalize(snapshot(30), config)
                    if condition == "unknown":
                        return normalize(snapshot(None), config)
                    old = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
                    return normalize(snapshot(), config, observed_at=old)
                observations = iter([normalize(snapshot(), config), blocked()])
                state = control(root, "final", config, usage_reader=lambda: next(observations))
                self.assertEqual(state["execution_status"], "paused")
                self.assertEqual(state["next_stage"], len(state["stages"]))
                reads = []
                def read_again():
                    reads.append(True)
                    return blocked()
                state = control(root, "final", config, resume=True, usage_reader=read_again)
                self.assertEqual(len(reads), 1)
                self.assertEqual(state["execution_status"], "paused")
                self.assertEqual(state["stop_reason"], {"budget":"budget_stop", "unknown":"usage_unknown", "stale":"usage_stale"}[condition])
                state = control(root, "final", config, resume=True,
                                usage_reader=lambda: normalize(snapshot(), config))
                self.assertEqual(state["execution_status"], "completed")
                self.assertEqual(len(state["stages"][0]["attempts"]), 1)
                print(json.dumps({'boundary':'E','condition':condition,'resume_reads':len(reads),
                                  'recovered':state['execution_status'],'attempt_count':1}))

    def test_c_real_closed_stdin_is_unknown_and_controller_checkpoints_pause(self):
        for timing in ("before", "after"):
            with self.subTest(timing=timing), repo() as root:
                config = {**config_from(), "usage_timeout_seconds": 3}
                script = "import json,os,sys,time; "
                if timing == "after":
                    script += "r=json.loads(sys.stdin.readline()); os.close(0); print(json.dumps({'id':r['id'],'result':{}}),flush=True); "
                else:
                    script += "os.close(0); "
                script += "time.sleep(2)"
                adapter = AppServerUsage(config, [sys.executable, "-c", script], "closed-stdin-fixture")
                usage = adapter.read()
                self.assertEqual(usage["status"], "unknown")
                state = control(root, "closed", config, usage_reader=adapter.read)
                self.assertEqual((state["execution_status"],state["stop_reason"]), ("paused","usage_unknown"))
                self.assertEqual(state["stages"][0]["attempts"], [])
                self.assertEqual(Store(root, "closed").load()["usage"]["status"], "unknown")
                print(json.dumps({'boundary':'C','timing':timing,'reason':usage['reason'],
                                  'cleanup_errors':usage.get('cleanup_errors',[]),'stage_attempts':0}))


@unittest.skipUnless(sys.platform == "linux" or os.name == "nt", "owned-process supervision supports Linux/Windows")
class ProcessBoundaryTests(unittest.TestCase):
    def test_detached_descendant_timeout_is_cleaned_on_linux_and_windows(self):
        with tempfile.TemporaryDirectory(prefix='descendant 空白 ') as tmp:
            root = Path(tmp)
            marker = root/'server.json'
            server = "import json,os,socket,sys,time; from pathlib import Path; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'port':s.getsockname()[1]})); time.sleep(30)"
            launcher = "import os,subprocess,sys; kwargs={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}; p=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]],**kwargs); p.wait()"
            ref=None
            try:
                result=execute(Stage('detached',[sys.executable,'-c',launcher,server,str(marker)],tmp),
                               root,{**config_from(),'stage_timeout_seconds':2},1)
                self.assertTrue(marker.is_file(),result)
                info=json.loads(marker.read_text())
                try:
                    ref=ProcessReference(info['pid'])
                except ProcessLookupError:
                    pass
                self.assertEqual(result['status'],'timeout',result)
                self.assertTrue(result['cleanup_confirmed'],result)
                self.assertTrue(ref is None or not ref.alive())
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',info['port']))
                print(json.dumps({'boundary':'A-platform','platform':sys.platform,
                                  'cleanup_confirmed':True,'port_released':True}))
            finally:
                if ref is not None:
                    ref.close()

    def test_journal_io_failure_still_terminates_actual_owned_child(self):
        with tempfile.TemporaryDirectory(prefix='journal 障害 ') as tmp:
            root = Path(tmp)
            marker = root/'child.pid'
            owner = root/'attempt.ownership.json'
            spec = root/'attempt.spec.json'
            token = 'journal-io-fixture'
            atomic_json(owner, {'schema_version':1,'token':token,'status':'starting','cleanup_confirmed':False})
            child_code = "import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"
            atomic_json(spec, {'token':token,'owner':str(owner),'result':str(root/'attempt.result.json'),
                              'stdout':str(root/'stdout.log'),'stderr':str(root/'stderr.log'),
                              'cwd':tmp,'command':[sys.executable,'-c',child_code,str(marker)],'timeout':10})
            code = """import sys,time
from pathlib import Path
from scripts.seed_loop import supervisor as s
real=s.atomic_json
def failing(path,value):
    if value.get('root_pid'):
        deadline=time.monotonic()+5
        while not Path(sys.argv[2]).exists():
            if time.monotonic()>deadline: raise AssertionError('child not launched')
            time.sleep(.02)
        raise OSError('fixture journal write failure')
    real(path,value)
s.atomic_json=failing
s.supervise(Path(sys.argv[1]))
"""
            guard=subprocess.Popen([sys.executable,'-c',code,str(spec),str(marker)],cwd=ROOT,
                                   stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            ref=None
            try:
                until(marker.is_file)
                try:
                    ref=ProcessReference(int(marker.read_text()))
                except ProcessLookupError:
                    pass
                guard.wait(timeout=12)
                self.assertTrue(ref is None or not ref.alive(),'journal write failure skipped process cleanup')
                result=json.loads((root/'attempt.result.json').read_text())
                self.assertTrue(result['cleanup_confirmed'])
                self.assertEqual(result['status'],'operational_error')
                self.assertIsNotNone(recovery_problem(root),'unconfirmed journal must block reuse')
            finally:
                guard.stdin.close()
                if guard.poll() is None:
                    guard.kill()
                guard.wait(timeout=5)
                guard.stderr.close()
                if ref is not None:
                    ref.close()

    def test_b_controller_kill_after_real_child_launch_cannot_overlap_resume(self):
        with repo() as root:
            fixture = root / "backend/scripts/validate_wikipedia_opening_artifact.py"
            fixture.write_text("""import os,time,json
from pathlib import Path
base=Path('.seed-loop')
(base/('child-'+str(os.getpid()))).write_text(str(os.getpid()))
while not (base/'release').exists(): time.sleep(.02)
print(json.dumps({'valid':True,'errors':[]}))
""", encoding="utf-8")
            code = "from pathlib import Path; import sys; from scripts.seed_loop.controller import control; from scripts.seed_loop.state import config_from; s=control(Path(sys.argv[1]),'killed',dict(config_from(),stage_timeout_seconds=12),mode='validation-only',resume=sys.argv[2]=='resume'); print(s['stop_reason'],flush=True)"
            workers, references = [], []
            def worker(action):
                p = subprocess.Popen([sys.executable,"-c",code,str(root),action],cwd=ROOT,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                workers.append(p)
                return p
            def markers():
                return list((root/'.seed-loop').glob('child-*'))
            try:
                first = worker('run')
                until(lambda: len(markers()) == 1)
                old = ProcessReference(int(markers()[0].read_text()))
                references.append(old)
                self.assertTrue(old.alive())
                first.kill()
                first.wait(timeout=5)
                second = worker('resume')
                until(lambda: second.poll() is not None or len(markers()) >= 2)
                if len(markers()) >= 2:
                    new_path = next(p for p in markers() if int(p.read_text()) != old.pid)
                    new = ProcessReference(int(new_path.read_text()))
                    references.append(new)
                    self.assertFalse(old.alive() and new.alive(), 'same stage overlapped after controller death')
                (root/'.seed-loop/release').touch()
                second.wait(timeout=15)
                self.assertEqual(second.returncode,0,second.stderr.read().decode(errors='replace'))
                until(lambda:not old.alive())
                until(lambda: recovery_problem(Store(root,'killed').directory) is None)
                # A bounded refusal while the guard is cleaning is valid; retry once clean.
                third = worker('resume')
                third.wait(timeout=15)
                self.assertEqual(third.returncode,0,third.stderr.read().decode(errors='replace'))
                self.assertEqual(Store(root,'killed').load()['execution_status'],'completed')
                print(json.dumps({'boundary':'B','controller_force_killed':True,
                                  'old_child_ended':not old.alive(),'resumed':'completed','overlap':False}))
            finally:
                (root/'.seed-loop/release').touch()
                for p in workers:
                    if p.poll() is None:
                        p.kill()
                    p.wait(timeout=5)
                    p.stdout.close()
                    p.stderr.close()
                for ref in references:
                    ref.close()

    @unittest.skipUnless(sys.platform == 'linux', 'real Playwright detached webServer regression on Linux')
    def test_a_real_playwright_readiness_timeout_releases_owned_server_port(self):
        cli = ROOT/'frontend/node_modules/@playwright/test/cli.js'
        if not cli.is_file():
            self.skipTest('Playwright dependency absent; Linux full CI installs npm ci before this suite')
        with tempfile.TemporaryDirectory(prefix='playwright 所有 ') as tmp:
            root = Path(tmp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); second_port=sock.getsockname()[1]
            (root/'package.json').write_text(json.dumps({'scripts':{'test':'node runner.cjs test'}}))
            (root/'runner.cjs').write_text("const fs=require('fs');fs.writeFileSync('runner.json',fs.readFileSync('/proc/self/stat'));require("+json.dumps(str(cli))+ ");")
            (root/'server.cjs').write_text("const fs=require('fs');require('http').createServer((q,s)=>{s.statusCode=404;s.end('waiting')}).listen("+str(port)+",'127.0.0.1',()=>fs.writeFileSync('server.json',fs.readFileSync('/proc/self/stat')));")
            (root/'playwright.config.cjs').write_text("module.exports={webServer:{command:'node server.cjs',url:'http://127.0.0.1:"+str(port)+"',timeout:30000},testDir:'./tests'};")
            (root/'tests').mkdir()
            (root/'tests/wait.spec.js').write_text("const {test}=require("+json.dumps(str(cli.parent))+ ");test('unused',()=>{});")
            config={**config_from(),'stage_timeout_seconds':3,'e2e_backend_port':port,'e2e_frontend_port':second_port}
            ref=None
            unrelated=subprocess.Popen([sys.executable,'-c',
                "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); sys.stdin.readline()"],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            unrelated_port=int(unrelated.stdout.readline())
            try:
                result=execute(Stage('playwright',npm('run','test'),str(root),e2e=True),root,config,1)
                self.assertTrue((root/'server.json').is_file(),result)
                server=(root/'server.json').read_text().rpartition(')')[2].split()
                runner=(root/'runner.json').read_text().rpartition(')')[2].split()
                self.assertNotEqual(server[2],runner[2], 'fixture must really use separate process groups')
                pid=int((root/'server.json').read_text().split(' ',1)[0])
                try:
                    ref=ProcessReference(pid)
                except ProcessLookupError:
                    pass
                self.assertEqual(result['status'],'timeout',result)
                self.assertTrue(ref is None or not ref.alive(),'Playwright webServer survived normal timeout')
                self.assertIsNone(unrelated.poll(),'cleanup must leave an unrelated server alive')
                with socket.socket() as other:
                    self.assertEqual(other.connect_ex(('127.0.0.1',unrelated_port)),0)
                with socket.socket() as sock:
                    self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    sock.bind(('127.0.0.1',port))
                print(json.dumps({'boundary':'A-Playwright','status':result['status'],
                                  'cleanup_confirmed':result.get('cleanup_confirmed'),
                                  'different_process_groups':True,'port_released':True,'unrelated_server_alive':True}))
            finally:
                if ref is not None:
                    ref.close()
                unrelated.stdin.close()
                unrelated.wait(timeout=5)
                unrelated.stdout.close()
