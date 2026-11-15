"""L2b-1a bounded usage diagnostics. Workers and remote writes are disconnected."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

from . import live_contract as contract
from .l2b_inputs import PLAN, PLAN_SHA256, identifier, keys, require
from .state import LoopError, atomic_json, digest, file_lock, git, now, read_json
from .usage import AppServerUsage, decision, unknown

DOC = 'docs/opening-seed-loop-poc-operating-decisions.md'
KIND = 'seed-loop-live-diagnostic'
APPROVAL_MAX_AGE = 86400


def load(path):
    # Neither local paths nor parser messages enter public diagnostics.
    try:
        return read_json(path)
    except LoopError:
        raise LoopError('local_json_unavailable_or_corrupt') from None


def put(path, kind, payload):
    require(not path.exists(), 'record_exists_no_overwrite')
    atomic_json(path, {'kind': kind, 'version': 1, 'payload': payload, 'sha256': digest(payload)})
    return contract.sha(path)


def get(path, kind):
    e = load(path)
    keys(e, {'kind', 'version', 'payload', 'sha256'}, 'record envelope')
    require(e['kind'] == kind and type(e['version']) is int and e['version'] == 1 and
            isinstance(e['payload'], dict) and e['sha256'] == digest(e['payload']), 'record_corrupt')
    return e['payload']


class Store:
    def __init__(self, root, session):
        self.root = Path(root).resolve()
        self.session = identifier(session)
        self.directory = self.root / '.seed-loop/live-usage' / session

    def lock(self):
        return file_lock(self.directory / 'session.lock')

    def transition(self):
        return file_lock(self.directory / 'publication.lock', timeout=5)

    def key(self):
        path = self.directory / 'identity-key.bin'
        if not path.exists():
            require(not any(self.directory.glob('operations/*/request.json')), 'identity_key_missing')
            with path.open('xb') as stream:
                if os.name != 'nt':
                    os.fchmod(stream.fileno(), 0o600)
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        value = path.read_bytes()
        require(len(value) == 32, 'identity_key_corrupt')
        return value

    def op(self, operation_id):
        return self.directory / 'operations' / identifier(operation_id)

    def candidate(self, candidate_id):
        return self.directory / 'candidates' / (identifier(candidate_id) + '.json')

    def approval(self, approval_id):
        return self.directory / 'approvals' / (identifier(approval_id) + '.json')

    def evidence(self, operation_id):
        directory = self.op(operation_id)
        request = get(directory / 'request.json', KIND + '-request')
        result = get(directory / 'result.json', KIND)
        require(result['request_hash'] == contract.sha(directory / 'request.json'), 'request_evidence_changed')
        for name, expected in result['evidence_hashes'].items():
            require(name in ('audit.json', 'read.json'), 'invalid_evidence_name')
            require(contract.sha(directory / name) == expected, 'diagnostic_evidence_changed')
        require(request['operation_id'] == operation_id == result['operation_id'], 'operation_identity_changed')
        return result

    def history(self):
        values = []
        for directory in sorted((self.directory / 'operations').glob('*')):
            try:
                request = get(directory / 'request.json', KIND + '-request')
                try:
                    result = self.evidence(directory.name)
                    status = 'verified'
                except (LoopError, OSError, KeyError, TypeError):
                    result, status = None, 'incomplete_or_evidence_invalid'
                values.append({'operation_id': directory.name, 'created_at': request['created_at'],
                               'action': request['action'], 'integrity': status, 'result': result})
            except (LoopError, OSError, KeyError, TypeError):
                raise LoopError('history_corrupt_preserved') from None
        return sorted(values, key=lambda v: (v['created_at'], v['operation_id']))


class Runtime:
    origin = 'live'

    def binding(self, root, settings):
        require(os.name == 'nt', 'windows_live_executor_required')
        binary = Path(settings['codex_binary'])
        require(binary.is_absolute() and binary.is_file() and binary.suffix.lower() == '.cmd',
                'absolute_codex_cmd_required')
        git(root, 'merge-base', '--is-ancestor', PLAN, 'HEAD')
        git(root, 'merge-base', '--is-ancestor', contract.BASE, 'HEAD')
        require(hashlib.sha256(git(root, 'show', PLAN + ':docs/opening-seed-loop-poc-plan.md')).hexdigest()
                == PLAN_SHA256, 'pinned_plan_blob_changed')
        return {'plan_commit': PLAN, 'plan_blob_sha256': PLAN_SHA256, 'implementation_base': contract.BASE,
                'operating_doc_git_blob_sha256': hashlib.sha256(git(root, 'show', 'HEAD:' + DOC)).hexdigest(),
                'operating_doc_checkout_sha256': contract.sha(root / DOC),
                'implementation_hash': digest({p.name: contract.sha(p) for p in
                                               sorted(Path(__file__).parent.glob('*.py'))}),
                'cli_path_hash': digest(str(binary.resolve())), 'cli_shim_sha256': contract.sha(binary),
                'platform': sys.platform, 'python': sys.version.split()[0],
                'local_pins': 'git-blob-and-ancestry-verified-not-remote-ref-check'}

    def reader(self, settings, key):
        # Version is read on EVERY operation. No upgrade, auth change or fallback.
        return AppServerUsage(contract.config(settings),
            account_reader=lambda raw: contract.account_read(raw, key), required_version=contract.CLI,
            usage_params=contract.CONTRACT['usage_params'])


def settings_binding(store, settings_path, runtime):
    value = contract.policy(load(settings_path))
    binding = {**runtime.binding(store.root, value), 'settings_hash': digest(value),
               'config_hash': digest(contract.config(value)), 'contract_hash': contract.CONTRACT_HASH,
               'bucket': value['bucket'], 'expected': value['expected'], 'scope': contract.SCOPE,
               'session': store.session, 'origin': runtime.origin}
    return value, binding


def source_binding(grounds_path, conditions_path):
    g = contract.grounds(load(grounds_path))
    require(contract.sha(Path(conditions_path)) == g['conditions_sha256'], 'conditions_evidence_changed')
    return {'grounds_hash': digest(g), 'conditions_sha256': g['conditions_sha256']}


def candidate_for(store, observation_id, settings_path, grounds_path, conditions_path, runtime):
    with store.lock():
        value, binding = settings_binding(store, settings_path, runtime)
        result = store.evidence(observation_id)
        require(result['origin'] == runtime.origin and result['binding'] == binding and
                result['communication'] == 'response_received', 'observation_conditions_changed')
        audit = get(store.op(observation_id) / 'audit.json', KIND + '-audit')
        require(audit['schema_reason'] is None and audit['monitoring_reason'] is None and
                audit['account'] is not None, 'observation_not_adoptable')
        binding = {**binding, **source_binding(grounds_path, conditions_path), 'account': audit['account']}
        candidate_id = uuid.uuid4().hex
        candidate = {'kind': 'seed-loop-live-candidate', 'version': 1, 'origin': runtime.origin,
                     'candidate_id': candidate_id, 'created_at': now(), 'status': 'pending-human-approval',
                     'observation_id': observation_id,
                     'observation_hash': contract.sha(store.op(observation_id) / 'result.json'),
                     'binding': binding, 'approval_max_age_seconds': APPROVAL_MAX_AGE,
                     'scope': contract.SCOPE, 'worker_connected': False}
        put(store.candidate(candidate_id), KIND + '-candidate', candidate)
        return candidate


def confirm(store, candidate_id, actor, runtime, *, input_fn=input):
    """Production has no --yes/approval-import entry. Only a person at a local TTY."""
    import re
    require(re.fullmatch('[A-Za-z0-9_-]{1,64}', actor) is not None, 'local_actor_alias_required')
    with store.lock():
        c = get(store.candidate(candidate_id), KIND + '-candidate')
        require(c['kind'] == 'seed-loop-live-candidate' and c['origin'] == runtime.origin and
                c['status'] == 'pending-human-approval', 'candidate_kind_or_origin_mismatch')
        store.evidence(c['observation_id'])
        require(contract.sha(store.op(c['observation_id']) / 'result.json') == c['observation_hash'],
                'candidate_observation_changed')
        require(runtime.origin != 'live' or sys.stdin.isatty(), 'interactive_local_human_required')
        print(json.dumps(c, ensure_ascii=False, indent=2))
        phrase = 'APPROVE ' + digest(c)
        require(input_fn('Review evidence, account/plan and scope; type ' + phrase + ': ') == phrase,
                'approval_not_confirmed')
        approval = {'kind': 'seed-loop-live-approval' if runtime.origin == 'live' else 'seed-loop-test-approval',
                    'version': 1, 'origin': runtime.origin, 'candidate_hash': digest(c), 'binding': c['binding'],
                    'actor': actor, 'approved_at': now(), 'operation': 'interactive-human-confirmation',
                    'confirmation_hash': digest(phrase), 'scope': contract.SCOPE}
        require(contract.approval_valid(approval, c, runtime.origin), 'invalid_approval')
        # One immutable record per candidate. A repeated approve never overwrites it.
        put(store.approval(candidate_id), KIND + '-approval', approval)
        return {'approval_id': candidate_id, 'approval_hash': digest(approval), 'origin': runtime.origin,
                'worker_connected': False}


def approval_check(store, approval_id, binding, account, grounds_path, conditions_path, runtime):
    if approval_id is None:
        return 'policy_pending'
    try:
        require(not any(v['result'] and v['result'].get('approval_id') == approval_id and
                        v['result'].get('approval_invalidated') for v in store.history()),
                'approval_previously_invalidated')
        c = get(store.candidate(approval_id), KIND + '-candidate')
        a = get(store.approval(approval_id), KIND + '-approval')
        require(contract.approval_valid(a, c, runtime.origin), 'approval_kind_or_binding_invalid')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(a['approved_at'])).total_seconds()
        require(0 <= age <= APPROVAL_MAX_AGE, 'approval_stale')
        expected = {**binding, **source_binding(grounds_path, conditions_path), 'account': account}
        require(a['binding'] == expected, 'approval_conditions_changed')
        store.evidence(c['observation_id'])
        require(contract.sha(store.op(c['observation_id']) / 'result.json') == c['observation_hash'],
                'approval_observation_changed')
    except (LoopError, OSError, ValueError, KeyError, TypeError) as exc:
        return str(exc) if isinstance(exc, LoopError) else 'approval_evidence_unavailable'
    return None


def diagnose(store, settings_path, *, action='observe', approval_id=None, grounds_path=None,
             conditions_path=None, runtime=None):
    runtime = runtime or Runtime()
    require(action in ('observe', 'gate', 'resume'), 'unsupported_action')
    with store.lock():
        previous = store.history()
        gates = [v for v in previous if v['action'] in ('gate', 'resume') or v['integrity'] != 'verified']
        if action == 'gate' and gates:
            last = gates[-1]
            require(last['integrity'] == 'verified' and last['result']['monitoring_budget_permit'],
                    'explicit_resume_required')
        value, binding = settings_binding(store, settings_path, runtime)
        key = store.key()
        operation_id = uuid.uuid4().hex
        directory = store.op(operation_id)
        request = {'operation_id': operation_id, 'created_at': now(), 'action': action,
                   'origin': runtime.origin, 'binding': binding, 'approval_id': approval_id,
                   'previous': [{k: v[k] for k in ('operation_id', 'action', 'integrity')} for v in previous]}
        request_hash = put(directory / 'request.json', KIND + '-request', request)
        hashes, raw_audit = {}, None

        def auditor(raw, context):
            nonlocal raw_audit
            raw_audit = contract.audit(raw, value, context, key, runtime.origin)
            hashes['audit.json'] = put(directory / 'audit.json', KIND + '-audit', raw_audit)
            return raw_audit['reason']

        try:
            usage = runtime.reader(value, key).read_audited(auditor)
        except (OSError, LoopError, ValueError):
            usage = unknown('audit_or_local_io_failed', value['bucket'], contract.CLI)
        usage['provider'] = 'codex-app-server' if runtime.origin == 'live' else 'test-stdio-app-server'
        usage['origin'] = runtime.origin
        # The adapter captures version output internally; never save arbitrary CLI stdout.
        if usage.get('cli_version') != contract.CLI:
            usage['cli_version'] = 'unrecognized-version' if usage.get('cli_version') else None
        read_reason = decision(usage, contract.config(value))
        read_record = {'operation_id': operation_id, 'usage': usage, 'budget_decision': read_reason,
                       'cleanup_confirmed': not usage.get('cleanup_errors'),
                       'audit_reason': raw_audit['reason'] if raw_audit else 'raw_response_unavailable'}
        hashes['read.json'] = put(directory / 'read.json', KIND + '-read', read_record)
        boundary_checks = []

        def boundary(label):
            check = {'boundary': label, 'evidence': 'not_checked', 'usage_decision': 'not_evaluated'}
            boundary_checks.append(check)
            try:
                require(contract.sha(directory / 'request.json') == request_hash, 'request_evidence_changed')
                for name, expected in hashes.items():
                    require(contract.sha(directory / name) == expected, 'current_evidence_changed')
                current_value, current_binding = settings_binding(store, settings_path, runtime)
                require(current_binding == binding and current_value == value, 'inputs_changed')
                # Check the key itself, never recreate lost identity evidence.
                require((store.directory / 'identity-key.bin').read_bytes() == key, 'identity_key_changed')
                approval_reason = approval_check(store, approval_id, binding,
                    raw_audit['account'] if raw_audit else None, grounds_path, conditions_path, runtime)
                check.update(evidence='verified', approval=approval_reason or 'approved')
            except (LoopError, OSError, ValueError, KeyError, TypeError) as exc:
                category = 'invalid' if isinstance(exc, LoopError) else 'unavailable'
                check.update(evidence=category, checked_at=now(),
                             evidence_reason=str(exc) if isinstance(exc, LoopError) else 'local_io_unavailable')
                return label + '_evidence_' + category
            # Clock is read AFTER locks, input/evidence hashes and approval verification.
            check.update(checked_at=now(), usage_decision=decision(usage, contract.config(value)))
            return (raw_audit['reason'] if raw_audit else usage.get('reason') or 'usage_unknown') or \
                   check['usage_decision'] or approval_reason

        reason = boundary('after_read')
        # Publication remains serialized; waiting here can invalidate the same observation.
        with store.transition():
            reason = boundary('completion') or reason
            approval_state = boundary_checks[-1].get('approval', 'not_verified')
            result = {'operation_id': operation_id, 'kind': KIND, 'version': 1,
                      'created_at': request['created_at'], 'finished_at': now(), 'action': action,
                      'origin': runtime.origin,
                      'real_usage': runtime.origin == 'live' and raw_audit is not None,
                      'usage_status': usage['status'],
                      'communication': 'response_received' if raw_audit is not None and
                          not usage.get('cleanup_errors') else 'unconfirmed_or_failed',
                      'diagnostic_complete': 'audit.json' in hashes and not usage.get('cleanup_errors'),
                      'approval_state': approval_state, 'observation_only': action == 'observe',
                      'approval_id': approval_id,
                      'approval_invalidated': approval_id is not None and bool(
                          (raw_audit and (raw_audit['monitoring_reason'] or raw_audit['schema_reason'] in
                           ('protocol_conditions_changed', 'account_plan_mismatch', 'bucket_identity_mismatch'))) or
                          usage.get('reason') == 'cli_version_changed' or
                          approval_state in ('approval_conditions_changed', 'conditions_evidence_changed',
                                             'approval_previously_invalidated') or
                          any(v.get('evidence_reason') in ('inputs_changed', 'identity_key_changed')
                              for v in boundary_checks)),
                      'monitoring_budget_permit': action != 'observe' and reason is None,
                      'stop_reason': reason or ('observation_only' if action == 'observe' else None),
                      'budget_decision_at_read': read_reason, 'boundary_checks': boundary_checks,
                      'worker_connected': False, 'worker_start_permitted': False,
                      'business_operations': 0, 'real_repair_turns': 0,
                      'binding': binding, 'request_hash': request_hash, 'evidence_hashes': hashes}
            # No writes occur between this completed boundary and immutable result publication.
            put(directory / 'result.json', KIND, result)
        return result


def inspect(store):
    with store.lock():
        return {'kind': KIND + '-status', 'version': 1, 'session': store.session,
                'history': store.history(), 'worker_connected': False, 'worker_start_permitted': False}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='L2b-1a usage diagnostics only; no workers')
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--session', required=True)
    subs = p.add_subparsers(dest='command', required=True)
    for name in ('observe', 'gate', 'resume'):
        c = subs.add_parser(name)
        c.add_argument('--live-usage', action='store_true', required=True)
        c.add_argument('--settings', type=Path, required=True)
        c.add_argument('--approval-id')
        c.add_argument('--grounds', type=Path)
        c.add_argument('--conditions', type=Path)
    c = subs.add_parser('candidate')
    c.add_argument('--observation-id', required=True)
    c.add_argument('--settings', type=Path, required=True)
    c.add_argument('--grounds', type=Path, required=True)
    c.add_argument('--conditions', type=Path, required=True)
    c = subs.add_parser('approve')
    c.add_argument('--candidate-id', required=True)
    c.add_argument('--actor', required=True, help='local alias, no email or account ID')
    subs.add_parser('status')
    subs.add_parser('contract')
    subs.add_parser('show').add_argument('--operation-id', required=True)
    a = p.parse_args(argv)
    try:
        store = Store(a.root, a.session)
        runtime = Runtime()
        if a.command in ('observe', 'gate', 'resume'):
            result = diagnose(store, a.settings, action=a.command, approval_id=a.approval_id,
                              grounds_path=a.grounds, conditions_path=a.conditions, runtime=runtime)
        elif a.command == 'candidate':
            result = candidate_for(store, a.observation_id, a.settings, a.grounds, a.conditions, runtime)
        elif a.command == 'approve':
            result = confirm(store, a.candidate_id, a.actor, runtime)
        elif a.command == 'contract':
            result = {'contract': contract.CONTRACT, 'contract_hash': contract.CONTRACT_HASH,
                      'scope': contract.SCOPE, 'worker_connected': False}
        elif a.command == 'show':
            with store.lock():
                result = {'result': store.evidence(a.operation_id),
                          'audit': get(store.op(a.operation_id) / 'audit.json', KIND + '-audit'),
                          'read': get(store.op(a.operation_id) / 'read.json', KIND + '-read')}
        else:
            result = inspect(store)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if a.command in ('gate', 'resume') and not result['monitoring_budget_permit']:
            return 3
        if a.command == 'observe' and not result['diagnostic_complete']:
            return 3
        return 0
    except (LoopError, OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        # Paths, server text, auth errors, or raw identity are never interpolated.
        print(json.dumps({'kind': KIND, 'operation': a.command, 'error':
                          str(exc) if isinstance(exc, LoopError) else 'local_operation_failed',
                          'category': type(exc).__name__,
                          'worker_start_permitted': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
