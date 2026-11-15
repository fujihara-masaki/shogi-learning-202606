"""L2b-1a tests: same adapter/disk/locks/pure budget, explicitly TEST origin."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.seed_loop import live_contract as c, live_usage as live
from scripts.seed_loop.l2b_inputs import simulated_adoption
from scripts.seed_loop.state import LoopError, atomic_json, digest, file_lock
from scripts.seed_loop.usage import AppServerUsage, decision, normalize

ROOT = Path(__file__).resolve().parents[2]
SERVER = Path(__file__).parent / 'fixtures/live_app_server.py'


def sample():
    bucket = {'limitId': 'codex', 'limitName': 'SECRET_DISPLAY', 'normalModelSlug': None,
              'primary': {'usedPercent': 1, 'windowDurationMins': 10080, 'resetsAt': 4102444800},
              'secondary': None, 'planType': 'pro', 'spendControlReached': False,
              'rateLimitReachedType': None, 'individualLimit': None,
              'credits': {'hasCredits': False, 'unlimited': False, 'balance': 'SECRET_BALANCE'}}
    return {'account': {'account': {'type': 'chatgpt', 'email': 'SECRET_EMAIL',
                                  'planType': 'pro', 'workspaceName': 'SECRET_WORKSPACE'},
                        'requiresOpenaiAuth': True},
            'result': {'rateLimits': deepcopy(bucket), 'rateLimitsByLimitId': {'codex': bucket},
                       'accountId': 'SECRET_ACCOUNT_ID', 'ordinaryUsageAllowed': True,
                       'rateLimitResetCredits': None, 'rateLimitUpsell': None}}


class TestRuntime(live.Runtime):
    origin = 'test'

    def __init__(self, root, *, wrapper=False):
        self.root = root
        self.fixture = root / 'work/応答 input.json'
        self.trace = root / 'work/methods.jsonl'
        self.wrapper = wrapper

    def binding(self, root, settings):
        return {'local_pins': 'simulated-not-GitHub', 'test_contract': c.CONTRACT_HASH}

    def reader(self, settings, key):
        if self.wrapper:
            return super().reader(settings, key)
        version = subprocess.check_output([sys.executable, str(SERVER), '--version', str(self.fixture)],
                                          text=True, encoding='utf-8').strip()
        cfg = {**c.config(settings), 'usage_timeout_seconds': 0.5}
        return AppServerUsage(cfg, [sys.executable, str(SERVER), str(self.fixture), str(self.trace)], version,
            account_reader=lambda raw: c.account_read(raw, key), required_version=c.CLI,
            usage_params=c.CONTRACT['usage_params'])


@contextmanager
def case():
    with tempfile.TemporaryDirectory(prefix='L2b live 日本語 空白 ') as t:
        root = Path(t)
        (root / 'work').mkdir()
        settings = {'kind': 'seed-loop-live-settings', 'version': 1, 'bucket': 'codex',
                    'expected': {'primary': {'state': 'object', 'duration_mins': 10080},
                                 'secondary': {'state': 'null', 'duration_mins': None}},
                    'codex_binary': str(root / '日本語 空白 codex.cmd'), 'cli_version': c.CLI}
        atomic_json(root / 'work/settings.json', settings)
        runtime = TestRuntime(root)
        atomic_json(runtime.fixture, sample())
        conditions = root / 'work/conditions.txt'
        conditions.write_bytes('TEST ONLY 条件\r\n'.encode('utf-8'))
        atomic_json(root / 'work/grounds.json', {'kind': 'seed-loop-live-grounds', 'version': 1,
            'official_contract_hash': c.CONTRACT_HASH, 'conditions_sha256': c.sha(conditions),
            'sufficient_for_conditional_scope': True, 'scope': c.SCOPE})
        yield root, settings, runtime, live.Store(root, 'test-session')


def read(store, runtime, action='observe', approval=None):
    root = store.root
    return live.diagnose(store, root / 'work/settings.json', action=action, approval_id=approval,
        grounds_path=root / 'work/grounds.json', conditions_path=root / 'work/conditions.txt', runtime=runtime)


def adopt(store, runtime, observation=None):
    observation = observation or read(store, runtime)
    root = store.root
    candidate = live.candidate_for(store, observation['operation_id'], root / 'work/settings.json',
        root / 'work/grounds.json', root / 'work/conditions.txt', runtime)
    with redirect_stdout(io.StringIO()):
        live.confirm(store, candidate['candidate_id'], 'test-human', runtime,
                     input_fn=lambda prompt: 'APPROVE ' + digest(candidate))
    return candidate['candidate_id']


def alter(runtime, change):
    raw = live.load(runtime.fixture)
    change(raw)
    atomic_json(runtime.fixture, raw)


class ContractTests(unittest.TestCase):
    def audit(self, raw=None, settings=None):
        raw = raw or sample()
        settings = settings or {'bucket': 'codex', 'expected': {
            'primary': {'state': 'object', 'duration_mins': 10080},
            'secondary': {'state': 'null', 'duration_mins': None}}}
        context = {'request_id': 2, 'method': 'account/rateLimits/read', 'cli_version': c.CLI,
                   'observed_at': datetime.now(timezone.utc).isoformat(),
                   'account': c.account_read(raw['account'], b'x' * 32)}
        return c.audit(raw['result'], settings, context, b'x' * 32, 'test')

    def test_null_both_and_secondary_only_are_explicit(self):
        self.assertIsNone(self.audit()['reason'])
        with case() as (root, settings, runtime, store):
            for mode in ('both', 'secondary'):
                v = sample()
                b = v['result']['rateLimitsByLimitId']['codex']
                b['secondary'] = deepcopy(b['primary'])
                settings['expected']['secondary'] = {'state': 'object', 'duration_mins': 10080}
                if mode == 'secondary':
                    b['primary'] = None
                    settings['expected']['primary'] = {'state': 'null', 'duration_mins': None}
                self.assertIsNone(self.audit(v, settings)['reason'])
                self.assertEqual(self.audit(v, settings)['S'], c.config(settings)['windows'])

    def test_raw_shapes_unknown_metadata_and_no_compatibility_escape(self):
        changes = [lambda v: v['result']['rateLimitsByLimitId']['codex'].pop('secondary'),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(secondary={}),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(primary=[]),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(limitId='other'),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(tertiary=None),
            lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(extra=1),
            lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(resetsAt=2**80),
            lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(windowDurationMins=300),
            lambda v: v['result'].update(rateLimitsByLimitId={}),
            lambda v: v['result'].update(rateLimitsByLimitId=None),
            lambda v: v['result'].update(extra='SECRET'),
            lambda v: v['result'].update(ordinaryUsageAllowed='SECRET'),
            lambda v: v['result'].update(rateLimitUpsell={'unknown': 'SECRET'}),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(credits={'extra': 1}),
            lambda v: v['result']['rateLimitsByLimitId']['codex'].update(normalModelSlug=True),
            lambda v: v['result'].update(rateLimitResetCredits={'availableCount': True}),
            lambda v: v['result'].update(accountId=None)]
        for change in changes:
            raw = sample()
            change(raw)
            with self.subTest(change=change):
                self.assertIsNotNone(self.audit(raw)['reason'])
                self.assertNotIn('SECRET', json.dumps(self.audit(raw)))
        raw = sample()
        raw['result']['rateLimitsByLimitId']['codex']['secondary'] = deepcopy(
            raw['result']['rateLimitsByLimitId']['codex']['primary'])
        self.assertEqual(self.audit(raw)['monitoring_reason'], 'window_state_changed')
        raw['result'].pop('rateLimitsByLimitId')
        self.assertEqual(self.audit(raw)['selection'], 'rateLimits')

    def test_numeric_and_shared_budget_time_boundaries(self):
        with case() as (root, settings, runtime, store):
            cfg = c.config(settings)
            at = datetime.now(timezone.utc)
            for percent, expected in [(24.99, None), (25, 'no_new_task'), (29.99, 'no_new_task'), (30, 'budget_stop')]:
                raw = sample()
                raw['result']['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = percent
                u = normalize(raw['result'], cfg, observed_at=at.isoformat())
                self.assertEqual(decision(u, cfg, at), expected)
            for percent in (True, float('nan'), float('inf'), -1, 101, None, '1', 24.99):
                raw = sample()
                raw['result']['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = percent
                self.assertIsNotNone(self.audit(raw)['schema_reason'])
            u = normalize(sample()['result'], cfg, observed_at=at.isoformat())
            self.assertIsNone(decision(u, cfg, at + timedelta(seconds=120)))
            self.assertEqual(decision(u, cfg, at + timedelta(seconds=120.001)), 'usage_stale')
            self.assertEqual(decision(u, cfg, at - timedelta(seconds=1)), 'usage_stale')
            u['windows']['primary']['resets_at'] = int(at.timestamp()) + 1
            self.assertEqual(decision(u, cfg, at + timedelta(seconds=2)), 'usage_stale')

    def test_server_denials_never_infer_from_percent_or_credit_balance(self):
        for change in [lambda v: v['result'].update(ordinaryUsageAllowed=False),
                       lambda v: v['result']['rateLimitsByLimitId']['codex'].update(spendControlReached=True),
                       lambda v: v['result']['rateLimitsByLimitId']['codex'].update(
                           rateLimitReachedType='workspace_owner_credits_depleted'),
                       lambda v: v['result']['rateLimitsByLimitId']['codex'].update(individualLimit={
                           'limit': '100', 'used': '100', 'remainingPercent': 0, 'resetsAt': 4102444800})]:
            raw = sample()
            change(raw)
            self.assertEqual(self.audit(raw)['server_reason'], 'server_usage_denied')
        raw = sample()
        raw['result']['ordinaryUsageAllowed'] = None
        self.assertEqual(self.audit(raw)['server_reason'], 'server_permission_unavailable')
        self.assertIsNone(self.audit()['reason'])  # hasCredits=false does not imply denied included usage


class DiagnosticTests(unittest.TestCase):
    def test_unapproved_observation_candidate_is_not_approval(self):
        with case() as (root, settings, runtime, store):
            observed = read(store, runtime)
            self.assertEqual(observed['communication'], 'response_received')
            self.assertEqual(observed['approval_state'], 'policy_pending')
            self.assertFalse(observed['monitoring_budget_permit'])
            self.assertEqual(observed['origin'], 'test')
            self.assertFalse(observed['real_usage'])
            self.assertEqual(read(store, runtime, 'gate')['stop_reason'], 'policy_pending')
            approval = adopt(store, runtime, observed)
            with self.assertRaises(LoopError):
                read(store, runtime, 'gate', approval)
            result = read(store, runtime, 'resume', approval)
            self.assertTrue(result['monitoring_budget_permit'])
            self.assertFalse(result['worker_start_permitted'])
            self.assertFalse(result['worker_connected'])
            self.assertEqual(result['business_operations'], 0)

    def test_fresh_reads_threshold_stops_and_diagnostics_not_budget_gated(self):
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            for used, reason in [(24, None), (25, 'no_new_task'), (29, 'no_new_task'), (30, 'budget_stop')]:
                alter(runtime, lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(usedPercent=used))
                result = read(store, runtime, 'resume', approval)
                self.assertEqual(result['stop_reason'], reason)
                self.assertEqual(result['monitoring_budget_permit'], reason is None)
            diagnostic = read(store, runtime)
            self.assertEqual(diagnostic['communication'], 'response_received')
            self.assertEqual(diagnostic['stop_reason'], 'budget_stop')
            with self.assertRaises(LoopError):
                read(store, runtime, 'gate', approval)
            methods = [json.loads(s) for s in runtime.trace.read_text(encoding='utf-8').splitlines()]
            self.assertEqual({v['method'] for v in methods}, set(c.CONTRACT['methods']))
            self.assertEqual(sum(v['method'] == 'account/rateLimits/read' for v in methods), 6)
            text = ''.join(p.read_text(encoding='utf-8') for p in store.directory.rglob('*.json'))
            self.assertNotIn('SECRET', text)
            self.assertNotIn('simulated-l2a-v1', text)
            self.assertNotIn('simulated-no-account', text)

    def test_missing_simulated_expired_and_changed_approval(self):
        for mode in ('missing', 'simulated', 'expired', 'future', 'binding'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                path = store.approval(approval)
                if mode == 'missing':
                    path.unlink()
                else:
                    record = live.get(path, live.KIND + '-approval')
                    if mode == 'simulated':
                        record = simulated_adoption({})
                    elif mode in ('expired', 'future'):
                        record['approved_at'] = (datetime.now(timezone.utc) + timedelta(
                            days=-2 if mode == 'expired' else 2)).isoformat()
                    else:
                        record['binding']['contract_hash'] = '0' * 64
                    atomic_json(path, {'kind': live.KIND + '-approval', 'version': 1,
                                     'payload': record, 'sha256': digest(record)})
                self.assertFalse(read(store, runtime, 'gate', approval)['monitoring_budget_permit'])

    def test_settings_version_account_plan_and_set_changes_require_readoption(self):
        changes = [lambda v: v['result'].update(accountId='OTHER_PRIVATE_ID'),
                   lambda v: v['account']['account'].update(email='OTHER_EMAIL'),
                   lambda v: v['account']['account'].update(planType='plus'),
                   lambda v: v['result']['rateLimitsByLimitId']['codex'].update(secondary={
                       'usedPercent': 1, 'windowDurationMins': 300, 'resetsAt': 4102444800}),
                   lambda v: v.update(cli_version='codex-cli 0.168.0'),
                   lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(windowDurationMins=300)]
        for change in changes:
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                alter(runtime, change)
                result = read(store, runtime, 'gate', approval)
                self.assertFalse(result['monitoring_budget_permit'])
                self.assertNotIn('OTHER_', json.dumps(result))
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            settings['expected']['primary']['duration_mins'] = 300
            atomic_json(root / 'work/settings.json', settings)
            self.assertFalse(read(store, runtime, 'gate', approval)['monitoring_budget_permit'])

    def test_observed_drift_invalidates_approval_even_after_revert(self):
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            alter(runtime, lambda v: v['result']['rateLimitsByLimitId']['codex']['primary'].update(windowDurationMins=300))
            changed = read(store, runtime, 'gate', approval)
            self.assertTrue(changed['approval_invalidated'])
            atomic_json(runtime.fixture, sample())
            restored = read(store, runtime, 'resume', approval)
            self.assertFalse(restored['monitoring_budget_permit'])
            self.assertEqual(restored['approval_state'], 'approval_previously_invalidated')
            new_approval = adopt(store, runtime)
            self.assertTrue(read(store, runtime, 'resume', new_approval)['monitoring_budget_permit'])

    def test_cleanup_failure_keeps_transport_unconfirmed(self):
        from scripts.seed_loop import usage as transport
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            terminate = transport.terminate
            def cleanup(child):
                terminate(child)
                raise OSError('SECRET cleanup failure')
            with patch.object(transport, 'terminate', cleanup):
                result = read(store, runtime, 'gate', approval)
            self.assertFalse(result['monitoring_budget_permit'])
            self.assertFalse(result['diagnostic_complete'])
            self.assertEqual(result['communication'], 'unconfirmed_or_failed')
            self.assertNotIn('SECRET', json.dumps(result))

    def test_actual_publication_lock_wait_and_post_hash_time_expiry(self):
        from test_seed_loop_preflight_locks import observe_contention
        from scripts.seed_loop import usage as transport
        for where in ('lock', 'evidence'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                current = [datetime.now(timezone.utc)]
                outcomes, errors = [], []
                contended = threading.Event()
                def run():
                    try:
                        outcomes.append(read(store, runtime, 'gate', approval))
                    except Exception as exc:
                        errors.append(exc)
                with patch.object(transport, 'datetime', wraps=datetime) as clock, \
                     patch.object(transport, 'now', side_effect=lambda: current[0].isoformat()):
                    clock.now.side_effect = lambda tz: current[0]
                    if where == 'lock':
                        with store.transition(), observe_contention('live-diagnostic', contended):
                            thread = threading.Thread(target=run, name='live-diagnostic')
                            thread.start()
                            self.assertTrue(contended.wait(5))
                            current[0] += timedelta(seconds=121)
                        thread.join(10)
                        self.assertFalse(thread.is_alive())
                    else:
                        original = live.source_binding
                        def checking(*args):
                            result = original(*args)
                            current[0] += timedelta(seconds=121)
                            return result
                        with patch.object(live, 'source_binding', checking):
                            run()
                self.assertFalse(errors, errors)
                self.assertEqual(outcomes[0]['stop_reason'], 'usage_stale')
                self.assertIsNone(outcomes[0]['budget_decision_at_read'])
                self.assertFalse(outcomes[0]['worker_start_permitted'])

    def test_transport_failures_no_fallback_and_account_read_bracket(self):
        for mode in ('eof', 'error', 'unsupported', 'malformed', 'timeout'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                alter(runtime, lambda v: v.update(mode=mode))
                result = read(store, runtime, 'gate', approval)
                self.assertFalse(result['monitoring_budget_permit'])
                self.assertEqual(result['communication'], 'unconfirmed_or_failed')
                self.assertNotIn('audit.json', result['evidence_hashes'])
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            raw = sample()
            raw['account_after'] = deepcopy(raw['account'])
            raw['account_after']['account']['planType'] = 'plus'
            atomic_json(runtime.fixture, raw)
            result = read(store, runtime, 'gate', approval)
            self.assertEqual(result['stop_reason'], 'account_changed_during_read')
            self.assertTrue(result['approval_invalidated'])
            atomic_json(runtime.fixture, sample())
            self.assertFalse(read(store, runtime, 'resume', approval)['monitoring_budget_permit'])
        with case() as (root, settings, runtime, store):
            with patch.object(runtime, 'reader', side_effect=OSError('SECRET_CLI_PATH')):
                result = read(store, runtime)
            saved = live.get(store.op(result['operation_id']) / 'read.json', live.KIND + '-read')
            self.assertIsNone(saved['usage']['cli_version'])
            self.assertFalse(result['monitoring_budget_permit'])
            self.assertNotIn('SECRET', json.dumps(result))

    def test_test_approval_never_live_and_no_noninteractive_real_approval(self):
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            a = live.get(store.approval(approval), live.KIND + '-approval')
            candidate = live.get(store.candidate(approval), live.KIND + '-candidate')
            self.assertFalse(c.approval_valid(a, candidate, 'live'))
            candidate['origin'] = 'live'
            atomic_json(store.candidate(approval), {'kind': live.KIND + '-candidate', 'version': 1,
                'payload': candidate, 'sha256': digest(candidate)})
            with patch('sys.stdin.isatty', return_value=False), self.assertRaises(LoopError):
                live.confirm(store, approval, 'human', live.Runtime(), input_fn=lambda p: 'APPROVE ' + digest(candidate))
            with self.assertRaises(LoopError):
                live.Runtime().binding(root, settings)

    def test_mutable_inputs_and_current_evidence_rechecked_at_completion(self):
        for mode in ('missing', 'changed', 'unreadable', 'settings', 'conditions', 'key'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                original_transition = store.transition
                @contextmanager
                def transition():
                    with original_transition():
                        request = sorted((store.directory / 'operations').glob('*/request.json'),
                                         key=lambda p: p.stat().st_mtime_ns)[-1]
                        path = request.parent / 'audit.json'
                        if mode == 'missing':
                            path.unlink()
                        elif mode == 'changed':
                            path.write_bytes(b'{}')
                        elif mode == 'unreadable':
                            original = Path.read_bytes
                            def inaccessible(p):
                                if p == path:
                                    raise PermissionError()
                                return original(p)
                            with patch.object(Path, 'read_bytes', inaccessible):
                                yield
                            return
                        elif mode == 'settings':
                            settings['expected']['primary']['duration_mins'] = 300
                            atomic_json(root / 'work/settings.json', settings)
                        elif mode == 'conditions':
                            (root / 'work/conditions.txt').write_bytes(b'changed')
                        else:
                            (store.directory / 'identity-key.bin').write_bytes(b'z' * 32)
                        yield
                with patch.object(store, 'transition', transition):
                    result = read(store, runtime, 'gate', approval)
                self.assertFalse(result['monitoring_budget_permit'])
                self.assertIsNotNone(result['stop_reason'])

    def test_waiting_publication_expires_snapshot_after_all_hashes(self):
        for mode in ('age', 'reset'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                original = store.transition
                real_decision = decision
                def expired(usage, cfg, at=None):
                    observed = datetime.fromisoformat(usage['observed_at'])
                    if mode == 'reset':
                        usage = deepcopy(usage)
                        usage['windows']['primary']['resets_at'] = int(observed.timestamp()) + 1
                    return real_decision(usage, cfg, observed + timedelta(seconds=121 if mode == 'age' else 2))
                @contextmanager
                def transition():
                    with original(), patch.object(live, 'decision', expired):
                        yield
                with patch.object(store, 'transition', transition):
                    result = read(store, runtime, 'gate', approval)
                self.assertEqual(result['stop_reason'], 'usage_stale')
                self.assertIsNone(result['budget_decision_at_read'])
                self.assertFalse(result['monitoring_budget_permit'])

    def test_saving_failures_corruption_no_overwrite_no_recreated_evidence(self):
        for target in ('audit.json', 'read.json', 'result.json'):
            with case() as (root, settings, runtime, store):
                approval = adopt(store, runtime)
                original = live.atomic_json
                def fail(path, value):
                    if path.name == target:
                        raise OSError('SECRET_PATH')
                    return original(path, value)
                with patch.object(live, 'atomic_json', fail):
                    if target == 'audit.json':
                        result = read(store, runtime, 'gate', approval)
                        self.assertFalse(result['monitoring_budget_permit'])
                    else:
                        with self.assertRaises(OSError):
                            read(store, runtime, 'gate', approval)
                if target != 'audit.json':
                    self.assertEqual(live.inspect(store)['history'][-1]['integrity'], 'incomplete_or_evidence_invalid')
                result = read(store, runtime, 'resume', approval)
                self.assertTrue(result['monitoring_budget_permit'])
                with redirect_stdout(io.StringIO()), self.assertRaises(LoopError):
                    live.confirm(store, approval, 'test-human', runtime,
                        input_fn=lambda p: 'APPROVE ' + digest(live.get(store.candidate(approval), live.KIND + '-candidate')))
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            result = read(store, runtime, 'gate', approval)
            original_result = (store.op(result['operation_id']) / 'result.json').read_bytes()
            (store.op(result['operation_id']) / 'audit.json').unlink()
            self.assertEqual(live.inspect(store)['history'][-1]['integrity'], 'incomplete_or_evidence_invalid')
            read(store, runtime, 'resume', approval)
            self.assertEqual((store.op(result['operation_id']) / 'result.json').read_bytes(), original_result)
            self.assertFalse((store.op(result['operation_id']) / 'audit.json').exists())

    def test_approval_and_candidate_save_failure_and_ground_pending(self):
        with case() as (root, settings, runtime, store):
            observation = read(store, runtime)
            with patch.object(live, 'atomic_json', side_effect=OSError()), self.assertRaises(OSError):
                live.candidate_for(store, observation['operation_id'], root / 'work/settings.json',
                    root / 'work/grounds.json', root / 'work/conditions.txt', runtime)
            candidate = live.candidate_for(store, observation['operation_id'], root / 'work/settings.json',
                    root / 'work/grounds.json', root / 'work/conditions.txt', runtime)
            with redirect_stdout(io.StringIO()), patch.object(live, 'atomic_json', side_effect=OSError()), self.assertRaises(OSError):
                live.confirm(store, candidate['candidate_id'], 'test-human', runtime,
                             input_fn=lambda p: 'APPROVE ' + digest(candidate))
            self.assertFalse(store.approval(candidate['candidate_id']).exists())
            grounds = live.load(root / 'work/grounds.json')
            grounds['sufficient_for_conditional_scope'] = False
            atomic_json(root / 'work/grounds.json', grounds)
            with self.assertRaises(LoopError):
                adopt(store, runtime, observation)

    def test_saved_gate_loses_effective_integrity_if_approval_evidence_disappears(self):
        for target in ('candidate', 'approval', 'observation'):
            with case() as (root, settings, runtime, store):
                approval_id = adopt(store, runtime)
                result = read(store, runtime, 'gate', approval_id)
                self.assertTrue(result['monitoring_budget_permit'])
                self.assertIsNotNone(result['approval_evidence'])
                result_path = store.op(result['operation_id']) / 'result.json'
                preserved = result_path.read_bytes()
                if target == 'candidate':
                    store.candidate(approval_id).unlink()
                elif target == 'approval':
                    store.approval(approval_id).unlink()
                else:
                    candidate = live.get(store.candidate(approval_id), live.KIND + '-candidate')
                    (store.op(candidate['observation_id']) / 'audit.json').unlink()
                self.assertEqual(live.inspect(store)['history'][-1]['integrity'], 'incomplete_or_evidence_invalid')
                self.assertEqual(result_path.read_bytes(), preserved)
                denied = read(store, runtime, 'resume', approval_id)
                self.assertFalse(denied['monitoring_budget_permit'])

    def test_os_lock_duplicate_operation_and_separate_process_reconfirmation(self):
        with case() as (root, settings, runtime, store):
            approval = adopt(store, runtime)
            env = dict(os.environ)
            env['PYTHONPATH'] = str(ROOT / 'scripts/tests') + os.pathsep + str(ROOT)
            command = [sys.executable, '-c',
                'import sys,json; from pathlib import Path; from test_seed_loop_live_usage import TestRuntime,read; '
                'from scripts.seed_loop.live_usage import Store; p=Path(sys.argv[1]); '
                'print(json.dumps(read(Store(p,"test-session"),TestRuntime(p),"resume",sys.argv[2])))',
                str(root), approval]
            with store.lock():
                duplicate = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env, timeout=10)
            self.assertNotEqual(duplicate.returncode, 0)
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)['monitoring_budget_permit'])
            self.assertEqual(len(live.inspect(store)['history']), 3)
            self.assertFalse((root / '.seed-loop/l2b0').exists())

    @unittest.skipUnless(os.name == 'nt', 'PowerShell parser requires Windows CI')
    def test_powershell_instructions_parse_without_executing_live_commands(self):
        import re
        blocks = re.findall(r'```powershell\n(.*?)```',
            (ROOT / live.DOC).read_text(encoding='utf-8'), re.S)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            with tempfile.TemporaryDirectory(prefix='PowerShell 日本語 ') as t:
                path = Path(t) / 'instructions.ps1'
                path.write_text(block, encoding='utf-8')
                script = 'param([string]$Target); $t=$null; $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($Target,[ref]$t,[ref]$e); if($e.Count){$e | ForEach-Object {Write-Error $_.Message}; exit 1}'
                checker = Path(t) / 'parse.ps1'
                checker.write_text(script, encoding='utf-8')
                parsed = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-File',
                    str(checker), str(path)], capture_output=True, text=True, encoding='utf-8', timeout=10)
                self.assertEqual(parsed.returncode, 0, parsed.stderr)

    @unittest.skipUnless(os.name == 'nt', 'Windows .cmd launch and termination require Windows')
    def test_windows_cmd_absolute_japanese_space_crlf_and_cleanup(self):
        with case() as (root, settings, runtime, store):
            binary = Path(settings['codex_binary'])
            # Fixed test shim only, not a replacement for the user's installed CLI.
            text = '@echo off\r\nif "%~1"=="--version" (\r\n' + \
                '  "' + sys.executable + '" "' + str(SERVER) + '" --version "' + str(runtime.fixture) + '"\r\n' + \
                '  exit /b %errorlevel%\r\n)\r\n' + \
                '"' + sys.executable + '" "' + str(SERVER) + '" "' + str(runtime.fixture) + '" "' + str(runtime.trace) + '"\r\n'
            # cmd.exe reads the Windows OEM code page; UTF-8 is enabled by this fixed shim.
            binary.write_bytes(('@chcp 65001 >nul\r\n' + text).encode('utf-8'))
            runtime.wrapper = True
            observation = read(store, runtime)
            self.assertEqual(observation['communication'], 'response_received')
            self.assertTrue(live.get(store.op(observation['operation_id']) / 'read.json', live.KIND + '-read')['cleanup_confirmed'])
            approval = adopt(store, runtime, observation)
            self.assertTrue(read(store, runtime, 'gate', approval)['monitoring_budget_permit'])


if __name__ == '__main__':
    unittest.main()
