"""Deterministic launch-lock ordering and pre-spawn Linux ownership checks."""
from contextlib import contextmanager
import json
import os
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from test_seed_loop import ROOT, repo, snapshot
from scripts.seed_loop import controller, process_tree
from scripts.seed_loop.controller import control, pause
from scripts.seed_loop.state import LockTimeout, Store, atomic_json, config_from, file_lock
from scripts.seed_loop.usage import normalize
from scripts.seed_loop.validation import execute


@contextmanager
def observe_contention(thread_name, event):
    # Observe the actual failed OS acquisition, not merely entry to a Python wrapper.
    if os.name == 'nt':
        import msvcrt as api
        name = 'locking'
    else:
        import fcntl as api
        name = 'flock'
    original = getattr(api, name)
    def acquiring(*args):
        try:
            return original(*args)
        except OSError:
            if threading.current_thread().name == thread_name:
                event.set()
            raise
    with patch.object(api, name, acquiring):
        yield


class LaunchLockTests(unittest.TestCase):
    def test_controller_reservation_first_pause_waits_then_drains_one_stage(self):
        with repo() as root:
            artifact = next((root/'backend/app/wikipedia_opening_artifacts').glob('*.json'))
            shutil.copyfile(artifact, artifact.with_name('second.json'))
            reserved, unlock, pause_attempted, pause_done, draining = (threading.Event() for _ in range(5))
            finish = threading.Event()
            states, errors = {}, []
            original_save = Store.save
            def saving(store, state):
                original_save(store, state)
                if (threading.current_thread().name == 'controller' and
                        state['stages'][0]['status'] == 'running'):
                    reserved.set()
                    if not unlock.wait(5):
                        raise AssertionError('reservation not released')
            def executor(*args):
                draining.set()
                if not finish.wait(5):
                    raise AssertionError('drain not released')
                return execute(*args)
            def run():
                try:
                    states['control'] = control(root,'reservation-first',config_from(),mode='validation-only',executor=executor)
                except BaseException as exc:
                    errors.append(exc)
            def pauser():
                try:
                    states['pause'] = pause(root,'reservation-first')
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    pause_done.set()
            worker = threading.Thread(target=run,name='controller')
            requester = threading.Thread(target=pauser,name='pauser')
            with patch.object(Store,'save',saving), observe_contention('pauser',pause_attempted):
                worker.start()
                try:
                    self.assertTrue(reserved.wait(5))
                    requester.start()
                    self.assertTrue(pause_attempted.wait(5))
                    unlock.set()
                    self.assertTrue(draining.wait(5))
                    self.assertTrue(pause_done.wait(5))
                    self.assertEqual(errors,[])
                    self.assertTrue(Store(root,'reservation-first').pause_path.is_file())
                finally:
                    unlock.set(); finish.set()
                    worker.join(10)
                    if requester.ident is not None:
                        requester.join(10)
            self.assertFalse(worker.is_alive() or requester.is_alive())
            self.assertEqual(errors,[])
            state=states['control']
            self.assertEqual((state['execution_status'],state['stop_reason']),('paused','manual_pause'))
            self.assertEqual([len(s['attempts']) for s in state['stages']],[1,0])
            self.assertTrue(state['stages'][0]['attempts'][0]['diagnostic']['valid'])

    def test_pause_publication_first_controller_waits_without_starting_stage(self):
        with repo() as root:
            reading, release_read, publishing, release_publish, reserving = (threading.Event() for _ in range(5))
            errors, states = [], {}
            config = config_from()
            executor = Mock(side_effect=AssertionError('must stay not_run'))
            def reader():
                reading.set()
                if not release_read.wait(5):
                    raise AssertionError('usage read not released')
                return normalize(snapshot(),config)
            def writing(path, value):
                if Path(path).name == 'pause.json':
                    publishing.set()
                    if not release_publish.wait(5):
                        raise AssertionError('pause publication not released')
                return atomic_json(path,value)
            def run():
                try:
                    states['control']=control(root,'pause-first',config,usage_reader=reader,executor=executor)
                except BaseException as exc:
                    errors.append(exc)
            def pauser():
                try:
                    states['pause']=pause(root,'pause-first')
                except BaseException as exc:
                    errors.append(exc)
            worker=threading.Thread(target=run,name='controller')
            requester=threading.Thread(target=pauser,name='pauser')
            with patch.object(controller,'atomic_json',writing), observe_contention('controller',reserving):
                worker.start()
                try:
                    self.assertTrue(reading.wait(5))
                    requester.start()
                    self.assertTrue(publishing.wait(5))
                    release_read.set()
                    self.assertTrue(reserving.wait(5))
                    release_publish.set()
                finally:
                    release_read.set(); release_publish.set()
                    worker.join(10)
                    if requester.ident is not None:
                        requester.join(10)
            self.assertFalse(worker.is_alive() or requester.is_alive())
            self.assertEqual(errors,[])
            executor.assert_not_called()
            self.assertEqual(states['control']['stop_reason'],'manual_pause')
            self.assertEqual(states['control']['stages'][0]['attempts'],[])
            self.assertTrue(Store(root,'pause-first').pause_path.is_file())


    def test_pause_wait_limit_does_not_claim_request_was_published(self):
        with repo() as root:
            cfg = config_from()
            control(root,'pause-timeout',cfg,usage_reader=lambda:normalize(snapshot(30),cfg))
            store=Store(root,'pause-timeout')
            held,release=threading.Event(),threading.Event()
            def holder():
                with file_lock(store.directory/'launch.lock'):
                    held.set()
                    if not release.wait(5):
                        raise AssertionError('lock holder not released')
            worker=threading.Thread(target=holder)
            worker.start()
            try:
                self.assertTrue(held.wait(5))
                with patch.object(controller,'LAUNCH_LOCK_TIMEOUT_SECONDS',0.05):
                    with self.assertRaisesRegex(LockTimeout,'pause request not published'):
                        pause(root,'pause-timeout')
                self.assertFalse(store.pause_path.exists())
                self.assertEqual(store.load()['stop_reason'],'budget_stop')
            finally:
                release.set(); worker.join(5)
            self.assertFalse(worker.is_alive())

    def test_controller_wait_limit_saves_pause_without_creating_attempt(self):
        with repo() as root:
            entered,resume=threading.Event(),threading.Event()
            cfg=config_from()
            states,errors=[],[]
            executor=Mock(side_effect=AssertionError('must stay not_run'))
            def reader():
                entered.set()
                if not resume.wait(5):
                    raise AssertionError('read not released')
                return normalize(snapshot(),cfg)
            def run():
                try:
                    states.append(control(root,'controller-timeout',cfg,usage_reader=reader,executor=executor))
                except BaseException as exc:
                    errors.append(exc)
            worker=threading.Thread(target=run)
            with patch.object(controller,'LAUNCH_LOCK_TIMEOUT_SECONDS',0.05):
                worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    with file_lock(Store(root,'controller-timeout').directory/'launch.lock'):
                        resume.set()
                        worker.join(5)
                finally:
                    resume.set(); worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors,[])
            executor.assert_not_called()
            self.assertEqual((states[0]['execution_status'],states[0]['stop_reason']),('paused','launch_lock_timeout'))
            self.assertEqual(states[0]['stages'][0]['attempts'],[])


@unittest.skipUnless(sys.platform=='linux','Linux ownership preflight')
class LinuxPreflightTests(unittest.TestCase):
    @staticmethod
    def proc_fixture(root, pid=123, start=10):
        def stat(pid, start):
            # pid + comm + fields 3..22. Only identity fields matter.
            return f'{pid} (fixture comm) ' + ' '.join(['R','1']+['0']*17+[str(start)])
        (root/'self').mkdir()
        (root/'self/stat').write_text(stat(pid,start))
        (root/'self/status').write_text(f'NSpid:\t{pid}\n')
        (root/'123').mkdir()
        (root/'123/stat').write_text(stat(123,start))

    def test_namespace_mismatch_refuses_before_any_process_launch(self):
        for mismatch in ('stat_pid','nested_even_if_numbers_coincide'):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                self.proc_fixture(root,pid=2174 if mismatch=='stat_pid' else 123)
                if mismatch != 'stat_pid':
                    (root/'self/status').write_text('NSpid:\t123\t123\n')
                with patch.object(process_tree,'PROC_ROOT',root), patch.object(process_tree.os,'getpid',return_value=5 if mismatch=='stat_pid' else 123), patch.object(process_tree.subprocess,'Popen') as spawning:
                    with self.assertRaises(OSError) as failure:
                        tree=process_tree.LinuxTree()
                        tree.start([sys.executable,'-c','pass'])
                    spawning.assert_not_called()
                    self.assertEqual(getattr(failure.exception,'reason',None),'linux_proc_pid_namespace_mismatch')

    def test_numeric_self_missing_or_inconsistent_refuses_before_launch(self):
        for condition in ('missing','different_pid','different_birth','malformed'):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                self.proc_fixture(root)
                target=root/'123/stat'
                if condition=='missing': target.unlink()
                elif condition=='different_pid': target.write_text(target.read_text().replace('123 (','124 ('))
                elif condition=='different_birth': target.write_text(target.read_text().rsplit(' ',1)[0]+' 999')
                else: (root/'self/stat').write_text('broken')
                with patch.object(process_tree,'PROC_ROOT',root,create=True), patch.object(process_tree.os,'getpid',return_value=123), patch.object(process_tree.subprocess,'Popen') as spawning:
                    with self.assertRaises(OSError) as failure:
                        tree=process_tree.LinuxTree()
                        tree.start([sys.executable,'-c','pass'])
                    spawning.assert_not_called()
                    self.assertIn(getattr(failure.exception,'reason',None),('linux_proc_self_unavailable','linux_proc_self_inconsistent'))

    def test_consistent_self_reference_passes_without_starting_any_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.proc_fixture(root)
            with patch.object(process_tree,'PROC_ROOT',root), patch.object(process_tree.os,'getpid',return_value=123), patch.object(process_tree.subprocess,'Popen') as spawning:
                process_tree.check_proc_identity()
                spawning.assert_not_called()

    def test_supervisor_records_namespace_rejection_before_child_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            proc=root/'proc'
            proc.mkdir()
            self.proc_fixture(proc,pid=2174)
            spec=root/'attempt.spec.json'
            owner=root/'attempt.ownership.json'
            result=root/'attempt.result.json'
            marker=root/'forbidden-child'
            atomic_json(owner,{'schema_version':1,'token':'preflight','status':'starting','cleanup_confirmed':False})
            atomic_json(spec,{'token':'preflight','owner':str(owner),'result':str(result),
                              'cwd':tmp,'stdout':str(root/'stdout.log'),'stderr':str(root/'stderr.log'),
                              'command':[sys.executable,'-c','pass'],'timeout':1})
            code="""from pathlib import Path
import sys
from unittest.mock import patch
from scripts.seed_loop import process_tree,supervisor
process_tree.PROC_ROOT=Path(sys.argv[2])
def forbidden(*args,**kwargs):
    Path(sys.argv[3]).touch()
    raise AssertionError('validation child must not launch')
with patch.object(process_tree.os,'getpid',return_value=5), patch.object(process_tree.subprocess,'Popen',side_effect=forbidden):
    supervisor.supervise(Path(sys.argv[1]))
"""
            guard=subprocess.Popen([sys.executable,'-c',code,str(spec),str(proc),str(marker)],cwd=ROOT,
                                   stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                guard.wait(timeout=5)
                self.assertEqual(guard.returncode,0,guard.stderr.read().decode(errors='replace'))
                self.assertFalse(marker.exists())
                diagnostic=json.loads(result.read_text())
                self.assertEqual(diagnostic['status'],'operational_error')
                self.assertEqual(diagnostic['reason'],'linux_proc_pid_namespace_mismatch')
                self.assertIn('validation child not started',diagnostic['detail'])
                self.assertIsNone(diagnostic['exit_code'])
                self.assertNotIn('root_pid',json.loads(owner.read_text()))
                self.assertTrue(diagnostic['cleanup_confirmed'])  # No validation process existed.
            finally:
                guard.stdin.close()
                if guard.poll() is None:
                    guard.kill()
                guard.wait(timeout=5)
                guard.stderr.close()
