"""L2b-0 one-task ledger and bounded CLI. All providers are explicitly simulated."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

from .l2b_inputs import (PINS, PLAN, PLAN_SHA256, PROTOCOL, audit_raw, config, example,
                         identifier, keys, permission, require, validate)
from .ownership import recovery_problem
from .state import (LoopError, LockTimeout, atomic_json, digest, file_lock, git,
                    identity, now, read_json)
from .usage import AppServerUsage, decision
from .validation import Stage, execute

KIND = 'seed-loop-l2b0-task'
MOCK = Path(__file__).with_name('l2b_mock.py').resolve()
LOCK_TIMEOUT = 5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_input(path):
    return validate(read_json(path))


def dependencies(value):
    keys(value, {'kind', 'version', 'simulated', *PINS}, 'dependency observation')
    require(value['kind'] == 'seed-loop-l2b0-dependencies' and type(value['version']) is int and
            value['version'] == 1 and value['simulated'] is True, 'only simulated dependency observation connected')
    return value


def dependency_example():
    return {'kind': 'seed-loop-l2b0-dependencies', 'version': 1, 'simulated': True, **PINS}


def binding(root, data, deps):
    """Caller supplies a dependency observation. No remote ref fetch or network here."""
    dependencies(deps)
    ident = identity(root)
    code = {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    local_plan = 'not_present_in_temporary_simulated_repo'
    if (root / 'docs/opening-seed-loop-poc-plan.md').exists():
        blob = git(root, 'show', PLAN + ':docs/opening-seed-loop-poc-plan.md')
        require(hashlib.sha256(blob).hexdigest() == PLAN_SHA256, 'pinned plan blob mismatch')
        git(root, 'merge-base', '--is-ancestor', PLAN, 'HEAD')
        local_plan = 'git_blob_and_ancestry_verified'
    return {'input_hash': digest(data), 'task_hash': digest(data['queue']['tasks'][0]),
            'queue_hash': digest(data['queue']), 'config_hash': digest(config(data)),
            'allowed_paths_hash': digest(data['queue']['tasks'][0]['allowed_paths']),
            'policy_hash': digest(data['policy']), 'adoption_hash': digest(data['adoption']),
            'repair_adoption_hash': digest(data['repair']), 'dependency_hash': digest(deps),
            'dependencies': deps, 'pins': dict(PINS), 'code_hash': digest(code),
            'code_files': code, 'repository': ident, 'local_plan_check': local_plan}


class Ledger:
    def __init__(self, root, task_id):
        self.task_id = identifier(task_id)
        self.directory = Path(root) / '.seed-loop/l2b0/tasks' / task_id
        self.path = self.directory / 'ledger.json'
        self.anchor = self.directory / 'anchor.json'
        self.pause_path = self.directory / 'pause.json'

    def lock(self):
        return file_lock(self.directory / 'task.lock')

    def transition(self):
        return file_lock(self.directory / 'launch.lock', timeout=LOCK_TIMEOUT)

    def save(self, state):
        state['updated_at'] = now()
        atomic_json(self.path, {'kind': KIND, 'version': 1, 'payload': state, 'sha256': digest(state)})

    def load(self):
        envelope = read_json(self.path)
        keys(envelope, {'kind', 'version', 'payload', 'sha256'}, 'ledger envelope')
        s = envelope['payload']
        require(envelope['kind'] == KIND and type(envelope['version']) is int and envelope['version'] == 1 and
                isinstance(s, dict) and envelope['sha256'] == digest(s), 'corrupt/unsupported ledger; preserved')
        anchor = read_json(self.anchor)
        require(anchor == {'kind': KIND, 'version': 1, 'task_id': self.task_id, 'ledger_id': s.get('ledger_id')},
                'ledger anchor mismatch; no implicit migration/reset')
        try:
            require(s['task_id'] == self.task_id and s['simulated'] is True and s['phase'] == 'mock_worker' and
                    s['execution_status'] in ('initialized', 'running', 'paused', 'mock_completed') and
                    isinstance(s['attempts'], list) and isinstance(s['usage_history'], list) and
                    isinstance(s['run_history'], list) and type(s['repair_count']) is int and
                    s['repair_count'] >= 0 and isinstance(s['binding'], dict), 'corrupt ledger state')
            attempts = s['attempts']
            require(len({a['attempt_id'] for a in attempts}) == len(attempts) and
                    s['repair_count'] == sum(a['operation'] == 'repair' for a in attempts), 'corrupt repair accounting')
            for i, a in enumerate(attempts):
                require(a['index'] == i and a['input_hash'] == s['binding']['input_hash'] and
                        a['status'] in ('reserved', 'result_unknown', 'success', 'failed') and
                        a['operation'] in ('generate', 'repair'), 'corrupt attempt')
                if a['status'] in ('success', 'failed'):
                    require(a['result_hash'] == digest(a['result']), 'attempt result hash mismatch')
        except (KeyError, TypeError, ValueError) as exc:
            raise LoopError('corrupt ledger; preserved for diagnosis') from exc
        return s

    def evidence(self, s):
        for entry in s['usage_history']:
            path = self.directory / 'audits' / (entry['audit_id'] + '.json')
            require(path.is_file() and sha(path) == entry['sha256'], 'audit evidence hash mismatch/missing')
        for attempt in s['attempts']:
            if attempt['status'] in ('success', 'failed'):
                require(bool(attempt.get('journal_hashes')), 'worker evidence missing')
                for name, expected in attempt['journal_hashes'].items():
                    require(Path(name).name == name, 'invalid worker evidence path')
                    path = self.directory / name
                    require(path.is_file() and sha(path) == expected, 'worker evidence hash mismatch/missing')


def initialize(root, data, deps, run_id):
    validate(data)
    identifier(run_id)
    dependencies(deps)
    require(all(deps[k] == v for k, v in PINS.items()), 'fixed dependencies changed')
    store = Ledger(root, data['queue']['tasks'][0]['task_id'])
    with store.lock():
        require(not store.path.exists() and not store.anchor.exists(), 'task already exists; use explicit resume; no run-ID reset')
        require(not any(p.name != 'task.lock' for p in store.directory.iterdir()), 'existing task evidence; refusing initialization')
        state = {'ledger_id': uuid.uuid4().hex, 'task_id': store.task_id, 'run_id': run_id,
                 'run_history': [{'run_id': run_id, 'at': now(), 'action': 'init'}],
                 'simulated': True, 'providers': {'usage': 'simulated-stdio-app-server', 'worker': 'fixed-mock-worker'},
                 'phase': 'mock_worker', 'execution_status': 'initialized', 'stop_reason': 'not_started',
                 'created_at': now(), 'binding': binding(root, data, deps), 'invalidated_by': [],
                 'repair_limit': data['repair']['limit'], 'repair_count': 0, 'cause_history': [],
                 'attempts': [], 'usage_history': [], 'last_gate': None,
                 'future': {k: {'status': 'not_performed', 'evidence': []} for k in
                            ('source_material', 'extraction', 'source_review', 'artifact_application', 'validation_runs', 'remote', 'poc')}}
        atomic_json(store.anchor, {'kind': KIND, 'version': 1, 'task_id': store.task_id, 'ledger_id': state['ledger_id']})
        store.save(state)
        return state


def stop(store, state, reason):
    state.update(execution_status='paused', stop_reason=reason)
    store.save(state)
    return state


def pause(root, task_id):
    store = Ledger(root, task_id)
    store.load()  # Missing/corrupt state must not create a task.
    try:
        with store.transition():
            store.load()
            atomic_json(store.pause_path, {'reason': 'manual_pause', 'requested_at': now()})
    except LockTimeout as exc:
        raise LockTimeout('pause request not published: ' + str(exc)) from exc
    try:
        with store.lock():
            return stop(store, store.load(), 'manual_pause')
    except LoopError as exc:
        if str(exc) != 'run is locked by an active worker':
            raise
    return {'task_id': task_id, 'simulated': True, 'pause_requested': True,
            'pause_policy': 'drain already reserved mock attempt; do not reserve another'}


def simulated_reader(fixture):
    # Fixed executable and fixed script, no config-supplied commands, codex binary or shell.
    path = Path(fixture).resolve()
    data = read_json(path)
    keys(data, {'kind', 'version', 'simulated', 'result'}, 'usage fixture')
    require(data['kind'] == 'seed-loop-l2b0-usage' and type(data['version']) is int and
            data['version'] == 1 and data['simulated'] is True, 'explicit simulated usage required')
    return lambda cfg: AppServerUsage(cfg, [sys.executable, str(MOCK), 'usage', str(path)],
                                      PROTOCOL['cli_version'])


def command_for(store, attempt):
    return [sys.executable, str(MOCK), 'worker', str(store.directory / (attempt['attempt_id'] + '.request.json'))]


def reconcile(store, state, attempt):
    """Only terminal supervisor evidence + exact request/output permits result reuse."""
    problem = recovery_problem(store.directory)
    if problem:
        return problem['reason']
    prefix = 'mock-' + attempt['attempt_id'] + '-1'
    try:
        spec = read_json(store.directory / (prefix + '.spec.json'))
        owner = read_json(store.directory / (prefix + '.ownership.json'))
        result = read_json(store.directory / (prefix + '.result.json'))
        request = read_json(store.directory / (attempt['attempt_id'] + '.request.json'))
        expected_request = {'kind': 'l2b0-mock-request', 'simulated': True, 'task_id': store.task_id,
                            'attempt_id': attempt['attempt_id'], 'input_hash': attempt['input_hash'],
                            'step': attempt['step']}
        require(request == expected_request and spec['command'] == command_for(store, attempt) and
                spec['token'] == owner['token'] == result['token'] and
                owner['status'] == 'cleaned' and owner['cleanup_confirmed'] is True and
                result['cleanup_confirmed'] is True, 'worker ownership/result mismatch')
        require(result['status'] == 'success' and type(result['exit_code']) is int and result['exit_code'] == 0,
                'worker did not finish known mock operation')
        output = read_json(store.directory / (prefix + '.stdout.log'))
        require(output == {**expected_request, 'kind': 'l2b0-mock-result'}, 'worker response mismatch')
        attempt.update(status=attempt['step']['outcome'], result=output, result_hash=digest(output),
                       ownership_token=result['token'], finished_at=result['finished_at'])
        attempt['journal_hashes'] = {prefix + suffix: sha(store.directory / (prefix + suffix))
                                     for suffix in ('.spec.json', '.ownership.json', '.result.json', '.stdout.log')}
        if attempt['operation'] == 'repair':
            if not any(h['attempt_id'] == attempt['attempt_id'] for h in state['cause_history']):
                state['cause_history'].append({'attempt_id': attempt['attempt_id'],
                                               'cause': attempt['step']['cause'], 'improved': attempt['step']['improved']})
        store.save(state)
        return None
    except (LoopError, KeyError, TypeError, OSError):
        attempt['status'] = 'result_unknown'
        store.save(state)
        return 'worker_result_unknown'


def repair_stop(state):
    history = state['cause_history']
    for cause in {h['cause'] for h in history}:
        relevant = [h for h in history if h['cause'] == cause]
        if len(relevant) >= 2 and not any(h['improved'] for h in relevant[-2:]):
            return 'same_cause_no_improvement'
    if state['repair_limit'] is None:
        return 'repair_limit_unadopted'
    if state['repair_count'] >= state['repair_limit']:
        return 'repair_limit_reached'
    return None


def control(root, data, deps, run_id, fixture, *, resume=False, reader_factory=None, executor=execute,
            input_path=None, dependencies_path=None):
    validate(data)
    identifier(run_id)
    store = Ledger(root, data['queue']['tasks'][0]['task_id'])
    def current_binding():
        return binding(root, load_input(input_path) if input_path else data,
                       dependencies(read_json(dependencies_path)) if dependencies_path else deps)

    with store.lock():
        state = store.load()
        current = current_binding()
        if state['invalidated_by']:
            return stop(store, state, 'evidence_invalidated')
        if state['binding'] != current:
            state['invalidated_by'] = [k for k in current if current[k] != state['binding'].get(k)]
            return stop(store, state, 'inputs_changed')
        store.evidence(state)
        require(resume or state['execution_status'] == 'initialized', 'explicit resume required')
        problem = recovery_problem(store.directory)
        if problem:
            return stop(store, state, problem['reason'])
        state['run_id'] = run_id
        state['run_history'].append({'run_id': run_id, 'at': now(), 'action': 'resume' if resume else 'simulate'})
        if resume:
            with store.transition():
                if store.pause_path.exists():
                    store.pause_path.unlink()
        state.update(execution_status='running', stop_reason=None)
        store.save(state)
        cfg = config(data)
        factory = reader_factory or simulated_reader(fixture)

        def gate():
            if store.pause_path.exists():
                return 'manual_pause'
            audit_id = uuid.uuid4().hex
            entry = None

            def auditor(raw, context):
                nonlocal entry
                evidence = audit_raw(raw, data, context)
                evidence.update(audit_id=audit_id, input_hash=state['binding']['input_hash'], run_id=run_id,
                                next_attempt_index=len(state['attempts']))
                path = store.directory / 'audits' / (audit_id + '.json')
                atomic_json(path, evidence)
                entry = {'audit_id': audit_id, 'sha256': sha(path), 'request': context,
                         'reason': evidence['reason'], 'usage': None, 'decision': 'not_evaluated'}
                state['usage_history'].append(entry)
                if evidence['reason'] and evidence['reason'] not in ('policy_unadopted', 'repair_limit_unadopted'):
                    state['invalidated_by'] = ['raw_monitoring_conditions:' + evidence['reason']]
                store.save(state)  # Permission cannot use unsaved audit evidence.
                return evidence['reason']

            observation = factory(cfg).read_audited(auditor)
            observation['provider'] = 'simulated-stdio-app-server'
            reason = entry['reason'] if entry and entry['reason'] else decision(observation, cfg)
            if entry:
                entry.update(usage=observation, decision=reason)
            state['last_gate'] = {'audit_id': audit_id if entry else None, 'usage': observation,
                                  'decision': reason, 'fixture_sha256': sha(fixture) if fixture else None,
                                  'simulated': True}
            store.save(state)
            if store.pause_path.exists():
                return 'manual_pause'
            if current_binding() != state['binding']:
                state['invalidated_by'] = ['post_read_inputs']
                return 'inputs_changed'
            return reason

        try:
            # Always a new read, even when all steps have already finished.
            reason = gate()
            if reason:
                return stop(store, state, reason)
            for attempt in state['attempts']:
                if attempt['status'] in ('reserved', 'result_unknown'):
                    reason = reconcile(store, state, attempt)
                    if reason:
                        return stop(store, state, reason)
            steps = data['queue']['tasks'][0]['steps']
            while len(state['attempts']) < len(steps):
                step = steps[len(state['attempts'])]
                if step['operation'] == 'repair':
                    reason = repair_stop(state)
                    if reason:
                        return stop(store, state, reason)
                with store.transition():
                    if store.pause_path.exists():
                        return stop(store, state, 'manual_pause')
                    # Recheck content at the launch boundary; no changed inputs can reuse permission.
                    if current_binding() != state['binding']:
                        state['invalidated_by'] = ['launch_boundary_inputs']
                        return stop(store, state, 'inputs_changed')
                    store.evidence(state)
                    attempt = {'attempt_id': uuid.uuid4().hex, 'index': len(state['attempts']),
                               'run_id': run_id, 'operation': step['operation'], 'step': deepcopy(step),
                               'input_hash': state['binding']['input_hash'], 'status': 'reserved',
                               'audit_id': state['last_gate']['audit_id'], 'reserved_at': now()}
                    state['attempts'].append(attempt)
                    if step['operation'] == 'repair':
                        state['repair_count'] += 1
                    store.save(state)  # Durable reservation and repair consumption BEFORE launch.
                request = {'kind': 'l2b0-mock-request', 'simulated': True, 'task_id': store.task_id,
                           'attempt_id': attempt['attempt_id'], 'input_hash': attempt['input_hash'], 'step': step}
                atomic_json(store.directory / (attempt['attempt_id'] + '.request.json'), request)
                stage = Stage('mock-' + attempt['attempt_id'], command_for(store, attempt), str(root))
                process_result = executor(stage, store.directory, cfg, 1)
                if process_result.get('cleanup_confirmed') is not True:
                    attempt['status'] = 'result_unknown'
                    return stop(store, state, process_result.get('reason') or 'cleanup_unconfirmed')
                reason = reconcile(store, state, attempt)
                if reason:
                    return stop(store, state, reason)
                if current_binding() != state['binding']:
                    state['invalidated_by'] = ['post_worker_inputs']
                    return stop(store, state, 'inputs_changed')
                reason = gate()
                if reason:
                    return stop(store, state, reason)
            # Stops apply at the tail too. A failed last result is never completion.
            if state['attempts'][-1]['status'] != 'success':
                return stop(store, state, repair_stop(state) or 'mock_failed')
            state.update(execution_status='mock_completed', stop_reason=None)
            store.save(state)
            return state
        except LockTimeout:
            return stop(store, state, 'launch_lock_timeout')
        except KeyboardInterrupt:
            return stop(store, state, 'interrupted')


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='L2b-0 simulated preparation only; no real providers')
    p.add_argument('--root', type=Path, default=Path.cwd())
    subs = p.add_subparsers(dest='command', required=True)
    ex = subs.add_parser('example')
    ex.add_argument('--directory', type=Path, required=True)
    for name in ('init', 'simulate', 'resume'):
        c = subs.add_parser(name)
        c.add_argument('--input', type=Path, required=True)
        c.add_argument('--dependencies', type=Path, required=True)
        c.add_argument('--run-id', required=True)
        c.add_argument('--simulated', action='store_true', required=True)
        if name != 'init':
            c.add_argument('--usage-fixture', type=Path, required=True)
    for name in ('status', 'pause'):
        subs.add_parser(name).add_argument('--task-id', required=True)
    a = p.parse_args(argv)
    try:
        root = a.root.resolve()
        if a.command == 'example':
            from .l2b_mock import usage_example
            target = a.directory.resolve()
            for name, value in [('input', example()), ('dependencies', dependency_example()), ('usage', usage_example())]:
                path = target / (name + '.json')
                require(not path.exists(), 'example destination already exists')
                atomic_json(path, value)
            result = {'simulated': True, 'directory': str(target), 'source_review': 'not_performed'}
        elif a.command in ('status', 'pause'):
            store = Ledger(root, a.task_id)
            result = pause(root, a.task_id) if a.command == 'pause' else store.load()
            if a.command == 'status':
                store.evidence(result)
                result = {**result, 'pause_requested': store.pause_path.exists(),
                          'process_recovery': recovery_problem(store.directory)}
        else:
            data = load_input(a.input)
            deps = dependencies(read_json(a.dependencies))
            result = (initialize(root, data, deps, a.run_id) if a.command == 'init' else
                      control(root, data, deps, a.run_id, a.usage_fixture, resume=a.command == 'resume',
                              input_path=a.input, dependencies_path=a.dependencies))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 3 if a.command in ('simulate', 'resume') and result.get('execution_status') == 'paused' else 0
    except (LoopError, OSError, ValueError) as exc:
        print(json.dumps({'kind': KIND, 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
