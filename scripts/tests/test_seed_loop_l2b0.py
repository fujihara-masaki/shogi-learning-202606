"""L2b-0: fictional inputs + real disk/locks/stdio/supervised mock worker processes."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.seed_loop import l2b
from scripts.seed_loop.l2b_inputs import (PROTOCOL, audit_raw, config, example, permission,
    policy_binding, repair_binding, simulated_adoption, validate)
from scripts.seed_loop.l2b_mock import usage_example
from scripts.seed_loop.state import LoopError, atomic_json, digest, read_json, file_lock
from scripts.seed_loop.usage import AppServerUsage, decision, normalize
from scripts.seed_loop.validation import execute
from test_seed_loop import ROOT
from test_seed_loop_preflight_locks import observe_contention


@contextmanager
def repo(data=None):
    with tempfile.TemporaryDirectory(prefix='L2b 日本語 空白 ') as temp:
        root = Path(temp)
        (root / '.gitignore').write_text('.seed-loop/\nwork/\n', encoding='utf-8')
        (root / 'input.txt').write_text('fictional', encoding='utf-8')
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Simulated', '-c',
                        'user.email=simulated@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        (root / 'work').mkdir()
        data = deepcopy(data or example())
        atomic_json(root / 'work/input.json', data)
        atomic_json(root / 'work/dependencies.json', l2b.dependency_example())
        atomic_json(root / 'work/usage.json', usage_example())
        yield root, data


def init(root, data, run='initial'):
    return l2b.initialize(root, data, l2b.dependency_example(), run)


def run(root, data, resume=False, **kwargs):
    return l2b.control(root, data, l2b.dependency_example(), 'resumed' if resume else 'initial',
                       root / 'work/usage.json', resume=resume, **kwargs)


def store(root, data):
    return l2b.Ledger(root, data['queue']['tasks'][0]['task_id'])


def adopt_repair(data):
    data['repair']['adoption'] = simulated_adoption(repair_binding(data))


def policy_b(data, selected='primary'):
    data['policy']['mode'] = 'B'
    absent = 'secondary' if selected == 'primary' else 'primary'
    data['policy']['expected'][absent] = {'state': 'null', 'duration_mins': None}
    data['adoption'] = simulated_adoption(policy_binding(data), [absent])
    adopt_repair(data)


def cli(root, command, *extra):
    args = [sys.executable, '-m', 'scripts.seed_loop.l2b', '--root', str(root), command]
    if command in ('init', 'simulate', 'resume'):
        args += ['--input', str(root / 'work/input.json'), '--dependencies', str(root / 'work/dependencies.json'),
                 '--run-id', 'separate-' + command, '--simulated']
        if command != 'init':
            args += ['--usage-fixture', str(root / 'work/usage.json')]
    with subprocess.Popen([*args, *extra], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8') as child:
        stdout, stderr = child.communicate(timeout=30)
        result = subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)
        result.process_id = child.pid
        return result


class InputAuditTests(unittest.TestCase):
    def context(self):
        return {'cli_version': PROTOCOL['cli_version'], 'observed_at': '2026-11-14T00:00:00+00:00',
                'request_id': 2, 'method': 'account/rateLimits/read'}

    def test_one_task_schema_disabled_unresolved_real_and_commands_rejected(self):
        data = example()
        changes = [lambda d: d['queue'].update(tasks=[]),
                   lambda d: d['queue']['tasks'].append(deepcopy(d['queue']['tasks'][0])),
                   lambda d: d['queue'].update(tasks='broken'),
                   lambda d: d['queue'].update(enabled=False),
                   lambda d: d['queue']['tasks'][0].update(enabled=False),
                   lambda d: d['queue']['tasks'][0].update(status='awaiting_research'),
                   lambda d: d['queue']['tasks'][0].update(allowed_paths=[]),
                   lambda d: d['queue']['tasks'][0].update(command='echo arbitrary'),
                   lambda d: d.update(version=True), lambda d: d.update(simulated=False),
                   lambda d: d['repair'].update(limit=True), lambda d: d.update(secret='do-not-save')]
        for change in changes:
            value = deepcopy(data)
            change(value)
            with self.subTest(value=value), self.assertRaises(LoopError):
                validate(value)
        validate(data)
        old_queue = read_json(ROOT / 'docs/opening-seed-loop-queue.example.json')
        data['queue'] = old_queue
        with self.assertRaises(LoopError):
            validate(data)

    def test_a_default_b_unadopted_and_simulated_adoption_binding(self):
        data = example()
        self.assertEqual(config(data)['windows'], ['primary', 'secondary'])
        self.assertIsNone(permission(data))
        policy_b(data)
        self.assertIsNone(permission(data))
        for key, value in [('adoption', None), ('adoption', {'simulated': True})]:
            changed = deepcopy(data)
            changed[key] = value
            self.assertEqual(permission(changed), 'policy_unadopted')
        for change in [lambda d: d['adoption'].update(nonprovided={}),
                       lambda d: d['adoption'].update(simulated=False),
                       lambda d: d['adoption'].update(kind='real-adoption'),
                       lambda d: d['adoption'].update(decided_by=''),
                       lambda d: d['adoption'].update(decided_at=''),
                       lambda d: d['adoption']['binding'].update(config_hash='0' * 64),
                       lambda d: d['adoption']['nonprovided']['secondary'].update(sha256='bad')]:
            changed = deepcopy(data)
            change(changed)
            self.assertEqual(permission(changed), 'policy_unadopted')
        data['repair']['limit'] = None
        self.assertEqual(permission(data), 'repair_limit_unadopted')
        data['simulated'] = False
        with self.assertRaises(LoopError):
            validate(data)

    def test_raw_primary_secondary_both_and_invalid_structures(self):
        for selected in ('primary', 'secondary', 'both'):
            data = example()
            raw = usage_example()['result']
            if selected != 'both':
                policy_b(data, selected)
                raw['rateLimitsByLimitId']['codex']['secondary' if selected == 'primary' else 'primary'] = None
            audit = audit_raw(raw, data, self.context())
            self.assertIsNone(audit['reason'])
            self.assertEqual(audit['S'], config(data)['windows'])
        for value in (True, '1', -1, 101, float('nan'), float('inf'), None):
            raw = usage_example()['result']
            raw['rateLimitsByLimitId']['codex']['secondary']['usedPercent'] = value
            self.assertIsNotNone(audit_raw(raw, example(), self.context())['reason'])
        for raw in ({}, {'rateLimits': {}}, {'rateLimits': {'primary': None, 'secondary': None}},
                    {'rateLimits': {'primary': [], 'secondary': 1}},
                    {'rateLimitsByLimitId': {}, 'rateLimits': usage_example()['result']['rateLimitsByLimitId']['codex']},
                    {'rateLimitsByLimitId': None, 'rateLimits': usage_example()['result']['rateLimitsByLimitId']['codex']}):
            self.assertIsNotNone(audit_raw(raw, example(), self.context())['reason'])

    def test_nonselected_null_to_object_and_missing_same_normalization_stop(self):
        data = example()
        policy_b(data)
        raw = usage_example()['result']
        bucket = raw['rateLimitsByLimitId']['codex']
        secondary = bucket['secondary']
        bucket['secondary'] = None
        reference = normalize(raw, config(data), observed_at=self.context()['observed_at'])
        self.assertIsNone(audit_raw(raw, data, self.context())['reason'])
        for value in ('missing', secondary):
            if value == 'missing':
                bucket.pop('secondary', None)
            else:
                bucket['secondary'] = value
            self.assertEqual(normalize(raw, config(data), observed_at=self.context()['observed_at']), reference)
            audit = audit_raw(raw, data, self.context())
            self.assertIsNotNone(audit['reason'])
            self.assertEqual(audit['windows']['secondary']['state'], 'missing' if value == 'missing' else 'object')

    def test_duration_cli_api_and_unknown_window_changes(self):
        for key in ('duration', 'cli', 'new-window', 'bucket'):
            raw, context = usage_example()['result'], self.context()
            if key == 'duration':
                raw['rateLimitsByLimitId']['codex']['primary']['windowDurationMins'] = 10080
            elif key == 'cli':
                context['cli_version'] = 'another-version'
            elif key == 'new-window':
                raw['rateLimitsByLimitId']['codex']['tertiary'] = {}
            else:
                raw['rateLimitsByLimitId']['codex']['limitId'] = 'other'
            self.assertIsNotNone(audit_raw(raw, example(), context)['reason'])
        for field in ('api', 'account_condition', 'cli_version'):
            data = example()
            data['protocol'][field] = 'changed'
            with self.assertRaises(LoopError):
                validate(data)

    def test_budget_boundaries_each_window_and_time(self):
        cfg = config(example())
        at = datetime.now(timezone.utc)
        for n in ('primary', 'secondary'):
            for value, expected in [(24.99, None), (25, 'no_new_task'), (29.99, 'no_new_task'), (30, 'budget_stop')]:
                raw = usage_example()['result']
                raw['rateLimitsByLimitId']['codex'][n]['usedPercent'] = value
                observed = normalize(raw, cfg, observed_at=at.isoformat())
                self.assertEqual(decision(observed, cfg, at), expected)
        for delta in (-121, 1):
            observed = normalize(usage_example()['result'], cfg, observed_at=(at + timedelta(seconds=delta)).isoformat())
            self.assertEqual(decision(observed, cfg, at), 'usage_stale')
        raw['rateLimitsByLimitId']['codex']['primary']['resetsAt'] = int(at.timestamp()) - 1
        observed = normalize(raw, cfg, observed_at=(at - timedelta(seconds=2)).isoformat())
        self.assertEqual(decision(observed, cfg, at), 'usage_stale')

    def test_real_stdio_id_audit_normalize_decision_and_sanitize(self):
        with repo() as (root, data):
            init(root, data)
            raw = usage_example()
            raw['result']['accountId'] = 'SECRET_ACCOUNT'
            raw['result']['rateLimitsByLimitId']['codex']['credits'] = {'secret': 'SECRET_CREDITS'}
            atomic_json(root / 'work/usage.json', raw)
            state = run(root, data)
            self.assertEqual(state['execution_status'], 'mock_completed')
            self.assertEqual(len(state['usage_history']), 2)
            self.assertTrue(all(e['request']['request_id'] == 2 and e['decision'] is None for e in state['usage_history']))
            content = ''.join(p.read_text(encoding='utf-8') for p in store(root, data).directory.rglob('*.json'))
            self.assertNotIn('SECRET', content)
            self.assertTrue(all(v['status'] == 'not_performed' for v in state['future'].values()))
            raw['result']['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = 30
            atomic_json(root / 'work/usage.json', raw)
            state = run(root, data, True)
            self.assertEqual(state['stop_reason'], 'budget_stop')  # noise has low usage; ID=2 wins
            self.assertEqual(len(state['attempts']), 1)

    def test_hook_not_called_on_protocol_errors_and_old_read_contract(self):
        fixture = ROOT / 'scripts/tests/fixtures/fake_app_server.py'
        for mode in ('error', 'eof', 'unsupported', 'malformed'):
            audit = Mock()
            observation = AppServerUsage(config(example()), [sys.executable, str(fixture), mode], 'fake-v1').read_audited(audit)
            audit.assert_not_called()
            self.assertNotEqual(observation['status'], 'known')
        audit = Mock(return_value='audit_denied')
        observation = AppServerUsage(config(example()), [sys.executable, str(fixture), 'valid'], 'fake-v1').read_audited(audit)
        self.assertEqual(observation['reason'], 'audit_denied')
        audit.assert_called_once()
        self.assertEqual(AppServerUsage(config(example()), [sys.executable, str(fixture), 'valid'], 'fake-v1').read()['status'], 'known')


class LedgerTests(unittest.TestCase):
    def test_cli_separate_process_pause_resume_no_success_reexecution(self):
        with repo() as (root, data):
            processes = []
            for command in ('init', 'simulate'):
                result = cli(root, command)
                processes.append(result.process_id)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            initial = store(root, data).load()
            self.assertEqual(cli(root, 'pause', '--task-id', store(root, data).task_id).returncode, 0)
            paused = store(root, data).load()
            self.assertEqual(paused['stop_reason'], 'manual_pause')
            resumed = cli(root, 'resume')
            processes.append(resumed.process_id)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            final = store(root, data).load()
            self.assertEqual(final['attempts'], initial['attempts'])
            self.assertGreater(len(final['usage_history']), len(initial['usage_history']))
            self.assertEqual(final['run_id'], 'separate-resume')
            self.assertEqual(len(set(processes)), 3)
            print(json.dumps({'boundary': 'L2b0-separate-resume', 'simulated': True,
                              'actual_local_controller_pids': processes, 'attempts_before': len(initial['attempts']),
                              'attempts_after': len(final['attempts']), 'fresh_usage_reads': len(final['usage_history']) - len(initial['usage_history']),
                              'repair_count': final['repair_count']}))
            self.assertEqual(cli(root, 'init').returncode, 2)  # new run cannot reset task
            self.assertEqual(cli(root, 'status', '--task-id', store(root, data).task_id).returncode, 0)

    def test_budget_pause_new_read_and_no_automatic_resume_at_tail(self):
        with repo() as (root, data):
            init(root, data)
            raw = usage_example()
            raw['result']['rateLimitsByLimitId']['codex']['secondary']['usedPercent'] = 30
            atomic_json(root / 'work/usage.json', raw)
            state = run(root, data)
            self.assertEqual((state['stop_reason'], len(state['attempts'])), ('budget_stop', 0))
            atomic_json(root / 'work/usage.json', usage_example())
            with self.assertRaisesRegex(LoopError, 'explicit resume'):
                run(root, data)
            self.assertEqual(run(root, data, True)['execution_status'], 'mock_completed')
            raw['result']['rateLimitsByLimitId']['codex']['secondary'] = None
            atomic_json(root / 'work/usage.json', raw)
            self.assertEqual(run(root, data, True)['stop_reason'], 'window_state_changed')
            self.assertEqual(len(store(root, data).load()['attempts']), 1)

    def test_b_adoption_and_repair_limit_missing_never_launch(self):
        for kind in ('policy', 'repair'):
            data = example()
            if kind == 'policy':
                policy_b(data)
                data['adoption'] = None
            else:
                data['repair'] = {'limit': None, 'adoption': None}
            with repo(data) as (root, data):
                if kind == 'policy':
                    raw = usage_example()
                    raw['result']['rateLimitsByLimitId']['codex']['secondary'] = None
                    atomic_json(root / 'work/usage.json', raw)
                init(root, data)
                worker = Mock(side_effect=AssertionError('no start'))
                state = run(root, data, executor=worker)
                self.assertEqual(state['stop_reason'], 'policy_unadopted' if kind == 'policy' else 'repair_limit_unadopted')
                worker.assert_not_called()
                self.assertEqual(state['attempts'], [])

    def test_simulated_b_success_does_not_enable_real_mode(self):
        data = example()
        policy_b(data, 'secondary')
        with repo(data) as (root, data):
            raw = usage_example()
            raw['result']['rateLimitsByLimitId']['codex']['primary'] = None
            atomic_json(root / 'work/usage.json', raw)
            init(root, data)
            self.assertEqual(run(root, data)['execution_status'], 'mock_completed')
            data['simulated'] = False
            with self.assertRaises(LoopError):
                run(root, data, True)

    def test_audit_or_reservation_save_failure_never_launches(self):
        for failure in ('audit-file', 'audit-ledger', 'reservation'):
            with repo() as (root, data):
                init(root, data)
                worker = Mock(side_effect=AssertionError('no unsaved launch'))
                original_save, original_atomic = l2b.Ledger.save, l2b.atomic_json
                def saving(s, value):
                    if failure == 'audit-ledger' and value['usage_history']:
                        raise OSError('disk')
                    if failure == 'reservation' and value['attempts']:
                        raise OSError('disk')
                    return original_save(s, value)
                def writing(path, value):
                    if failure == 'audit-file' and Path(path).parent.name == 'audits':
                        raise OSError('disk')
                    return original_atomic(path, value)
                with patch.object(l2b.Ledger, 'save', saving), patch.object(l2b, 'atomic_json', writing):
                    try:
                        state = run(root, data, executor=worker)
                        self.assertEqual(state['execution_status'], 'paused')
                    except OSError:
                        pass
                worker.assert_not_called()
                self.assertEqual(store(root, data).load()['attempts'], [])

    def test_atomic_replace_failure_utf8_corrupt_missing_version_and_evidence_hash(self):
        with repo() as (root, data):
            init(root, data)
            s = store(root, data)
            before = s.path.read_bytes()
            with patch('os.replace', side_effect=OSError('replace')):
                with self.assertRaises(OSError):
                    s.save(s.load())
            self.assertEqual(s.path.read_bytes(), before)
            self.assertEqual(list(s.directory.glob('.checkpoint-*')), [])
            envelope = read_json(s.path)
            for value in ({}, {**envelope, 'version': 2}, {**envelope, 'sha256': '0' * 64}):
                atomic_json(s.path, value)
                raw = s.path.read_bytes()
                with self.assertRaises(LoopError):
                    run(root, data, True)
                self.assertEqual(s.path.read_bytes(), raw)
            s.path.write_bytes(before)
            s.path.unlink()
            with self.assertRaises(LoopError):
                init(root, data, 'another-run')
            with self.assertRaises(LoopError):
                s.load()
            s.path.write_bytes(before)
            state = run(root, data)
            entry = state['usage_history'][0]
            path = s.directory / 'audits' / (entry['audit_id'] + '.json')
            path.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(LoopError, 'evidence hash'):
                run(root, data, True)

    def test_input_plan_dependency_code_scope_changes_invalidate_permanently(self):
        for kind in ('plan_commit', 'plan_blob_sha256', 'foundation_head', 'plan_head', 'task', 'policy', 'code', 'config', 'allowed_paths'):
            with self.subTest(kind=kind), repo() as (root, data):
                init(root, data)
                deps = l2b.dependency_example()
                changed = deepcopy(data)
                if kind in deps:
                    deps[kind] = '0' * len(deps[kind])
                elif kind == 'task':
                    changed['queue']['tasks'][0]['steps'][0]['outcome'] = 'failed'
                    adopt_repair(changed)
                elif kind in ('policy', 'config', 'allowed_paths', 'code'):
                    # Simulate a change at the boundary, keeping actual code files untouched.
                    pass
                original = l2b.binding
                def bound(*args):
                    value = original(*args)
                    if kind in ('policy', 'config', 'allowed_paths', 'code'):
                        value[kind + '_hash'] = 'changed'
                    return value
                with patch.object(l2b, 'binding', bound):
                    state = l2b.control(root, changed, deps, 'new-run', root / 'work/usage.json', resume=True)
                self.assertEqual(state['stop_reason'], 'inputs_changed')
                self.assertTrue(state['invalidated_by'])
                self.assertEqual(run(root, data, True)['stop_reason'], 'evidence_invalidated')
                self.assertEqual(state['attempts'], [])

    def test_repository_file_and_head_changes_stop(self):
        for kind in ('file', 'head'):
            with repo() as (root, data):
                init(root, data)
                if kind == 'file':
                    (root / 'input.txt').write_text('changed', encoding='utf-8')
                else:
                    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Simulated', '-c',
                                    'user.email=simulated@example.invalid', 'commit', '--allow-empty', '-qm', 'change'], check=True)
                self.assertEqual(run(root, data)['stop_reason'], 'inputs_changed')

    def test_cli_input_and_dependency_files_reread_at_launch_and_tail(self):
        for tail in (False, True):
            for kind in ('input', 'dependencies'):
                with self.subTest(tail=tail, kind=kind), repo() as (root, data):
                    init(root, data)
                    if tail:
                        run(root, data)
                    factory = l2b.simulated_reader(root / 'work/usage.json')
                    class Changing:
                        def read_audited(self, callback):
                            observed = factory(config(data)).read_audited(callback)
                            value = deepcopy(data) if kind == 'input' else l2b.dependency_example()
                            if kind == 'input':
                                value['repair']['limit'] = 3
                            else:
                                value['foundation_head'] = '0' * 40
                            atomic_json(root / ('work/' + kind + '.json'), value)
                            return observed
                    worker = Mock(side_effect=AssertionError('changed input must not launch'))
                    state = l2b.control(root, data, l2b.dependency_example(), 'changed-files',
                                        root / 'work/usage.json', resume=tail,
                                        reader_factory=lambda _: Changing(), executor=worker,
                                        input_path=root / 'work/input.json',
                                        dependencies_path=root / 'work/dependencies.json')
                    self.assertEqual(state['stop_reason'], 'inputs_changed')
                    self.assertEqual(len(state['attempts']), 1 if tail else 0)
                    worker.assert_not_called()

    def test_saved_worker_evidence_loss_never_reuses_success(self):
        with repo() as (root, data):
            init(root, data)
            state = run(root, data)
            s = store(root, data)
            evidence = next(iter(state['attempts'][0]['journal_hashes']))
            (s.directory / evidence).unlink()
            with self.assertRaisesRegex(LoopError, 'worker evidence hash'):
                run(root, data, True)

    def test_post_worker_last_read_input_change_is_not_completion(self):
        with repo() as (root, data):
            init(root, data)
            factory = l2b.simulated_reader(root / 'work/usage.json')
            calls = 0
            class Changing:
                def read_audited(self, callback):
                    nonlocal calls
                    calls += 1
                    observed = factory(config(data)).read_audited(callback)
                    if calls == 2:
                        changed = deepcopy(data)
                        changed['repair']['limit'] = 3
                        atomic_json(root / 'work/input.json', changed)
                    return observed
            state = l2b.control(root, data, l2b.dependency_example(), 'tail-change', root / 'work/usage.json',
                                reader_factory=lambda _: Changing(), input_path=root / 'work/input.json')
            self.assertEqual(state['stop_reason'], 'inputs_changed')
            self.assertEqual(state['attempts'][0]['status'], 'success')
            self.assertEqual(state['execution_status'], 'paused')

    def test_raw_collection_drift_revokes_old_evidence_even_after_response_reverts(self):
        data = example()
        policy_b(data)
        with repo(data) as (root, data):
            init(root, data)
            # The provided secondary was adopted as null: a new object revokes that adoption.
            state = run(root, data)
            self.assertEqual(state['stop_reason'], 'window_state_changed')
            self.assertTrue(state['invalidated_by'])
            raw = usage_example()
            raw['result']['rateLimitsByLimitId']['codex']['secondary'] = None
            atomic_json(root / 'work/usage.json', raw)
            self.assertEqual(run(root, data, True)['stop_reason'], 'evidence_invalidated')
            self.assertEqual(store(root, data).load()['attempts'], [])

    def test_pause_read_boundary_and_pause_before_start_zero_workers(self):
        with repo() as (root, data):
            init(root, data)
            entered, release = threading.Event(), threading.Event()
            results, errors = [], []
            factory = l2b.simulated_reader(root / 'work/usage.json')
            class Blocked:
                def read_audited(self, callback):
                    entered.set()
                    if not release.wait(5):
                        raise AssertionError('read not released')
                    return factory(config(data)).read_audited(callback)
            worker = Mock(side_effect=AssertionError('pause before reservation'))
            def controller():
                try:
                    results.append(run(root, data, reader_factory=lambda _: Blocked(), executor=worker))
                except BaseException as exc:
                    errors.append(exc)
            thread = threading.Thread(target=controller)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                l2b.pause(root, store(root, data).task_id)
            finally:
                release.set()
                thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            worker.assert_not_called()
            self.assertEqual((results[0]['stop_reason'], results[0]['attempts']), ('manual_pause', []))

    def test_pause_reservation_first_drains_and_pause_publication_first_no_attempt(self):
        for reservation_first in (True, False):
            with self.subTest(reservation_first=reservation_first), repo() as (root, data):
                init(root, data)
                reached, release, contested = threading.Event(), threading.Event(), threading.Event()
                drain, done = threading.Event(), threading.Event()
                results, errors = [], []
                original_save, original_atomic = l2b.Ledger.save, l2b.atomic_json
                factory = l2b.simulated_reader(root / 'work/usage.json')
                def saving(s, state):
                    original_save(s, state)
                    if reservation_first and state['attempts'] and state['attempts'][-1]['status'] == 'reserved':
                        reached.set()
                        if not release.wait(5):
                            raise AssertionError('reservation release')
                def writing(path, value):
                    if not reservation_first and Path(path).name == 'pause.json':
                        reached.set()
                        if not release.wait(5):
                            raise AssertionError('publication release')
                    return original_atomic(path, value)
                def executor(*args):
                    drain.set()
                    if not done.wait(5):
                        raise AssertionError('drain release')
                    return execute(*args)
                def controller():
                    try:
                        results.append(run(root, data, executor=executor))
                    except BaseException as exc:
                        errors.append(exc)
                def pauser():
                    try:
                        l2b.pause(root, store(root, data).task_id)
                    except BaseException as exc:
                        errors.append(exc)
                thread = threading.Thread(target=controller, name='controller')
                requester = threading.Thread(target=pauser, name='pauser')
                with patch.object(l2b.Ledger, 'save', saving), patch.object(l2b, 'atomic_json', writing), observe_contention('pauser' if reservation_first else 'controller', contested):
                    try:
                        if reservation_first:
                            thread.start()
                            self.assertTrue(reached.wait(5))
                            requester.start()
                        else:
                            requester.start()
                            self.assertTrue(reached.wait(5))
                            thread.start()
                        self.assertTrue(contested.wait(5))
                        release.set()
                        requester.join(5)
                        done.set()
                    finally:
                        release.set(); done.set()
                        if thread.ident: thread.join(10)
                        if requester.ident: requester.join(10)
                self.assertEqual(errors, [])
                self.assertFalse(thread.is_alive() or requester.is_alive())
                self.assertEqual(results[0]['stop_reason'], 'manual_pause')
                self.assertEqual(len(results[0]['attempts']), 1 if reservation_first else 0)
                self.assertEqual(drain.is_set(), reservation_first)

    def test_different_process_exclusion_for_simulate_and_double_resume(self):
        with repo() as (root, data):
            init(root, data)
            code = "from scripts.seed_loop.l2b import Ledger; from pathlib import Path; import sys\nwith Ledger(Path(sys.argv[1]),sys.argv[2]).lock():\n print('held',flush=True)\n sys.stdin.readline()"
            holder = subprocess.Popen([sys.executable, '-c', code, str(root), store(root, data).task_id],
                                      cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self.assertEqual(holder.stdout.readline().strip(), b'held')
                for command in ('simulate', 'resume', 'resume'):
                    result = cli(root, command)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('locked', result.stdout)
                self.assertEqual(store(root, data).load()['attempts'], [])
            finally:
                holder.kill(); holder.wait(timeout=5)
                holder.stdin.close(); holder.stdout.close()
            self.assertEqual(cli(root, 'simulate').returncode, 0)

    def test_repair_limits_two_three_and_cause_no_improvement_distinct(self):
        for limit, improved, expected in [(2, True, 'repair_limit_reached'), (3, True, 'repair_limit_reached'),
                                          (3, False, 'same_cause_no_improvement')]:
            data = example()
            data['repair']['limit'] = limit
            data['queue']['tasks'][0]['steps'] = [
                {'operation': 'generate' if i == 0 else 'repair', 'outcome': 'failed',
                 'cause': 'fixture-a', 'improved': improved} for i in range(4)]
            adopt_repair(data)
            with repo(data) as (root, data):
                init(root, data)
                state = run(root, data)
                consumed = 2 if not improved else limit
                self.assertEqual((state['stop_reason'], state['repair_count']), (expected, consumed))
                resumed = cli(root, 'resume')
                self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
                final = store(root, data).load()
                self.assertEqual(final['attempts'], state['attempts'])
                self.assertEqual(final['repair_count'], consumed)
                self.assertEqual(final['run_id'], 'separate-resume')
                print(json.dumps({'boundary': 'L2b0-repair', 'simulated': True, 'adopted_mock_limit': limit,
                                  'stop_reason': final['stop_reason'], 'repair_count_after_new_run': final['repair_count'],
                                  'attempts_unchanged': final['attempts'] == state['attempts']}))

    def test_crash_after_reservation_does_not_retry_or_refund_repair(self):
        data = example()
        data['queue']['tasks'][0]['steps'].append({'operation': 'repair', 'outcome': 'success',
                                                 'cause': 'fixture-a', 'improved': True})
        adopt_repair(data)
        with repo(data) as (root, data):
            init(root, data)
            code = """from scripts.seed_loop.l2b import *
import os,sys
root=Path(sys.argv[1]); data=load_input(root/'work/input.json')
def executor(stage,directory,cfg,attempt):
    if 'repair' in read_json(Path(stage.command[-1]))['step']['operation']: os._exit(19)
    return execute(stage,directory,cfg,attempt)
control(root,data,dependency_example(),'crashing',root/'work/usage.json',executor=executor)
"""
            child = subprocess.run([sys.executable, '-c', code, str(root)], cwd=ROOT, timeout=30)
            self.assertEqual(child.returncode, 19)
            state = store(root, data).load()
            self.assertEqual(state['repair_count'], 1)
            self.assertEqual(state['attempts'][-1]['status'], 'reserved')
            worker = Mock(side_effect=AssertionError('unknown cannot relaunch'))
            state = run(root, data, True, executor=worker)
            self.assertEqual(state['stop_reason'], 'worker_result_unknown')
            self.assertEqual(state['repair_count'], 1)
            self.assertEqual(state['attempts'][-1]['status'], 'result_unknown')
            worker.assert_not_called()
            with self.assertRaises(LoopError):
                init(root, data, 'evade-count')

    def test_controller_crash_before_and_after_result_save_recovers_exact_terminal_evidence(self):
        for after_save in (False, True):
            with self.subTest(after_save=after_save), repo() as (root, data):
                init(root, data)
                code = """from scripts.seed_loop.l2b import *
import os,sys
root=Path(sys.argv[1]); data=load_input(root/'work/input.json')
original=Ledger.save
def saving(self,state):
    if state['attempts'] and state['attempts'][-1]['status']=='success':
        if sys.argv[2]=='True': original(self,state)
        os._exit(21)
    return original(self,state)
Ledger.save=saving
control(root,data,dependency_example(),'crashing',root/'work/usage.json')
"""
                result = subprocess.run([sys.executable, '-c', code, str(root), str(after_save)], cwd=ROOT, timeout=30)
                self.assertEqual(result.returncode, 21)
                before = store(root, data).load()
                self.assertEqual(before['attempts'][-1]['status'], 'success' if after_save else 'reserved')
                worker = Mock(side_effect=AssertionError('terminal result must not be rerun'))
                state = run(root, data, True, executor=worker)
                self.assertEqual(state['execution_status'], 'mock_completed')
                self.assertEqual(len(state['attempts']), 1)
                worker.assert_not_called()

    def test_unconfirmed_ownership_and_active_worker_never_resume(self):
        with repo() as (root, data):
            init(root, data)
            s = store(root, data)
            atomic_json(s.directory / 'lost.ownership.json', {'schema_version': 1, 'token': 'fixture', 'status': 'supervising'})
            self.assertEqual(run(root, data)['stop_reason'], 'cleanup_unconfirmed')
            (s.directory / 'lost.ownership.json').unlink()
            with file_lock(s.directory / 'execution.lock'):
                self.assertEqual(run(root, data, True)['stop_reason'], 'previous_attempt_active')
            self.assertEqual(s.load()['attempts'], [])

    def test_post_result_save_failure_keeps_unknown_and_reconciles_without_reexecution(self):
        with repo() as (root, data):
            init(root, data)
            original = l2b.Ledger.save
            def saving(s, state):
                if state['attempts'] and state['attempts'][-1]['status'] == 'success':
                    raise OSError('result save failed')
                return original(s, state)
            with patch.object(l2b.Ledger, 'save', saving):
                state = run(root, data)
            self.assertEqual(state['stop_reason'], 'worker_result_unknown')
            self.assertEqual(state['attempts'][-1]['status'], 'result_unknown')
            worker = Mock(side_effect=AssertionError('must reconcile persisted worker evidence'))
            state = run(root, data, True, executor=worker)
            self.assertEqual(state['execution_status'], 'mock_completed')
            worker.assert_not_called()

    def test_no_real_usage_inference_network_github_or_artifact_paths(self):
        with repo() as (root, data):
            init(root, data)
            def forbidden(*args, **kwargs):
                raise AssertionError('real path invoked')
            original = subprocess.run
            def git_only(command, **kwargs):
                if command[0] != 'git':
                    raise AssertionError('unexpected executable: ' + str(command))
                return original(command, **kwargs)
            with patch('scripts.seed_loop.usage.subprocess.run', side_effect=git_only), \
                 patch('urllib.request.urlopen', side_effect=forbidden):
                state = run(root, data)
            self.assertEqual(state['execution_status'], 'mock_completed')
            self.assertFalse((root / 'backend').exists())
            self.assertFalse((root / 'work/l2b0-mock-output.json').exists())
            self.assertEqual(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain']), b'')


if __name__ == '__main__':
    unittest.main()
