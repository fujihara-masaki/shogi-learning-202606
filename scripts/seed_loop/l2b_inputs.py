"""L2b-0 input contract and sanitized raw-window audit (simulation only)."""
from copy import deepcopy
from datetime import datetime
import math
import re

from .state import LoopError, DEFAULT_CONFIG, digest

PLAN = 'd9299b4d897849c218695f0cf1d5057e43e30af2'
FOUNDATION = 'b438609f4bd7c04ff812d64e7de74718b935a39f'
PLAN_SHA256 = 'bfe9187863c66828c3f7edee175ee1b718a37651c6b213db9e031b748e076924'
PINS = {'plan_commit': PLAN, 'plan_head': PLAN, 'foundation_head': FOUNDATION,
        'plan_blob_sha256': PLAN_SHA256}
NAMES = ('primary', 'secondary')
PROTOCOL = {'cli_version': 'simulated-l2a-v1', 'api': 'account/rateLimits/read@L2a-v1',
            'account_condition': 'simulated-no-account'}


def require(condition, reason):
    if not condition:
        raise LoopError(reason)


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), 'invalid ' + label + ' schema')


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value),
            'invalid task/run ID')
    return value


def adoption(record, binding, *, nonprovided=()):
    expected = {'kind', 'version', 'simulated', 'decision', 'decided_by', 'decided_at', 'binding', 'nonprovided'}
    try:
        keys(record, expected, 'adoption')
        require(record['kind'] == 'simulated-adoption' and type(record['version']) is int and
                record['version'] == 1 and record['simulated'] is True and record['decision'] == 'adopt',
                'simulated adoption required')
        require(record['decided_by'] == 'simulated-reviewer' and
                datetime.fromisoformat(record['decided_at']).utcoffset() is not None,
                'adoption decision identity/time missing')
        require(record['binding'] == binding, 'adoption binding mismatch')
        require(isinstance(record['nonprovided'], dict) and set(record['nonprovided']) == set(nonprovided),
                'nonprovided evidence missing')
        for evidence in record['nonprovided'].values():
            keys(evidence, {'provenance', 'sha256'}, 'nonprovided evidence')
            require(evidence['provenance'] == 'simulated-fixture' and
                    isinstance(evidence['sha256'], str) and re.fullmatch('[a-f0-9]{64}', evidence['sha256']),
                    'nonprovided evidence missing')
    except (LoopError, ValueError, TypeError, KeyError):
        return False
    return True


def config(data):
    return {**DEFAULT_CONFIG, 'windows': [n for n in NAMES if data['policy']['expected'][n]['state'] == 'object']}


def policy_binding(data):
    return {'plan_commit': PLAN, 'config_hash': digest(config(data)),
            'policy_hash': digest(data['policy']), 'protocol_hash': digest(data['protocol'])}


def repair_binding(data):
    return {**policy_binding(data), 'task_hash': digest(data['queue']['tasks'][0]),
            'repair_limit': data['repair']['limit']}


def validate(data):
    keys(data, {'kind', 'version', 'simulated', 'queue', 'policy', 'protocol', 'adoption', 'repair'}, 'input')
    require(data['kind'] == 'seed-loop-l2b0-input' and type(data['version']) is int and data['version'] == 1,
            'unsupported input kind/version')
    require(data['simulated'] is True, 'real workers/usage are not connected in L2b-0')
    q = data['queue']
    keys(q, {'schema_version', 'enabled', 'tasks'}, 'queue')
    require(type(q['schema_version']) is int and q['schema_version'] == 1 and q['enabled'] is True,
            'disabled or unsupported queue')
    require(isinstance(q['tasks'], list) and len(q['tasks']) == 1, 'exactly one task required; duplicates forbidden')
    task = q['tasks'][0]
    keys(task, {'task_id', 'simulated', 'enabled', 'status', 'allowed_paths', 'steps'}, 'task')
    identifier(task['task_id'])
    require(task['simulated'] is True and task['enabled'] is True and task['status'] == 'simulated_ready',
            'task unresolved/disabled; no automatic promotion')
    # Mock workers never apply these paths; all production paths stay disconnected.
    require(task['allowed_paths'] == ['work/l2b0-mock-output.json'], 'mock allowed scope must be explicit')
    steps = task['steps']
    require(isinstance(steps, list) and 1 <= len(steps) <= 4, 'invalid bounded mock steps')
    for i, step in enumerate(steps):
        keys(step, {'operation', 'outcome', 'cause', 'improved'}, 'mock step')
        require(step['operation'] == ('generate' if i == 0 else 'repair') and
                step['outcome'] in ('success', 'failed') and step['cause'] in ('fixture-a', 'fixture-b') and
                type(step['improved']) is bool, 'unsupported mock operation')
    p = data['policy']
    keys(p, {'mode', 'expected'}, 'policy')
    require(p['mode'] in ('A', 'B'), 'unknown policy')
    keys(p['expected'], NAMES, 'expected windows')
    for expectation in p['expected'].values():
        keys(expectation, {'state', 'duration_mins'}, 'window expectation')
        require(expectation['state'] in ('object', 'null') and
                ((expectation['state'] == 'null' and expectation['duration_mins'] is None) or
                 (expectation['state'] == 'object' and type(expectation['duration_mins']) is int and
                  expectation['duration_mins'] > 0)), 'invalid expected window')
    require(any(w['state'] == 'object' for w in p['expected'].values()), 'empty expected S')
    require(p['mode'] != 'A' or all(w['state'] == 'object' for w in p['expected'].values()),
            'policy A requires both windows')
    keys(data['protocol'], PROTOCOL, 'protocol')
    require(data['protocol'] == PROTOCOL, 'unsupported CLI/API/account conditions')
    keys(data['repair'], {'limit', 'adoption'}, 'repair')
    limit = data['repair']['limit']
    require(limit is None or (type(limit) is int and limit in (2, 3)), 'repair limit must be explicitly 2 or 3')
    # Missing/unadopted records are valid pending inputs, never a start permit.
    return deepcopy(data)


def permission(data):
    absent = [n for n in NAMES if data['policy']['expected'][n]['state'] == 'null']
    if data['policy']['mode'] == 'B' and not adoption(data['adoption'], policy_binding(data), nonprovided=absent):
        return 'policy_unadopted'
    if data['repair']['limit'] is None or not adoption(data['repair']['adoption'], repair_binding(data)):
        return 'repair_limit_unadopted'
    return None


def classify(value):
    if value is None:
        return {'state': 'null', 'type': 'null'}
    if not isinstance(value, dict):
        return {'state': 'invalid', 'type': type(value).__name__}
    result = {'state': 'object', 'type': 'object'}
    # Only numeric API fields are retained. Secrets and unexpected values are excluded.
    for name in ('usedPercent', 'windowDurationMins', 'resetsAt'):
        v = value.get(name)
        valid = (type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100) if name == 'usedPercent' else (
            type(v) is int and v > 0)
        if not valid:
            result['state'] = 'invalid'
            result[name] = {'present': name in value, 'type': type(v).__name__, 'valid': False}
        else:
            result[name] = v
    if set(value) - {'usedPercent', 'windowDurationMins', 'resetsAt'}:
        result['state'] = 'invalid'
        result['unknown_fields'] = True
    return result


def audit_raw(result, data, context):
    """Select full bucket, classify BOTH keys, preserve null vs missing; never infer."""
    evidence = {'simulated': True, 'provider': 'simulated-stdio-app-server', 'context': context,
                'bucket': config(data)['bucket'], 'selection': None, 'windows': {}, 'S': [], 'reason': None}
    reason = None
    if (context.get('cli_version') != data['protocol']['cli_version'] or
            context.get('method') != 'account/rateLimits/read' or context.get('request_id') != 2):
        reason = 'protocol_conditions_changed'
    bucket = evidence['bucket']
    selected = None
    if not isinstance(result, dict):
        reason = 'malformed_response'
    elif 'rateLimitsByLimitId' in result:
        evidence['selection'] = 'rateLimitsByLimitId'
        multi = result['rateLimitsByLimitId']
        if not isinstance(multi, dict) or bucket not in multi:
            reason = 'bucket_unavailable'
        else:
            selected = multi[bucket]
    else:
        evidence['selection'] = 'rateLimits'
        selected = result.get('rateLimits')
    if not reason and (not isinstance(selected, dict) or selected.get('limitId') not in (None, bucket)):
        reason = 'bucket_identity_mismatch'
    if not reason:
        # Unknown window formats are denied; unrelated account/credit metadata is never copied.
        if set(selected) - {'limitId', 'limitName', 'planType', 'credits', *NAMES}:
            reason = 'unknown_bucket_fields'
        for n in NAMES:
            w = classify(selected[n]) if n in selected else {'state': 'missing', 'type': 'missing'}
            evidence['windows'][n] = w
            if w['state'] == 'object':
                evidence['S'].append(n)
            expected = data['policy']['expected'][n]
            if w['state'] != expected['state']:
                reason = reason or 'window_state_changed'
            elif w['state'] == 'object' and w['windowDurationMins'] != expected['duration_mins']:
                reason = reason or 'window_duration_changed'
        expected_s = [n for n in NAMES if data['policy']['expected'][n]['state'] == 'object']
        if not evidence['S'] or evidence['S'] != expected_s:
            reason = reason or 'window_set_changed'
    reason = reason or permission(data)
    evidence['reason'] = reason
    evidence['policy_hash'] = digest(data['policy'])
    evidence['adoption_hash'] = digest(data['adoption'])
    evidence['config_hash'] = digest(config(data))
    return evidence


def example():
    """Fictional, explicitly simulated inputs; never an operational approval."""
    data = {'kind': 'seed-loop-l2b0-input', 'version': 1, 'simulated': True,
            'queue': {'schema_version': 1, 'enabled': True, 'tasks': [{
                'task_id': 'fictional-l2b0', 'simulated': True, 'enabled': True, 'status': 'simulated_ready',
                'allowed_paths': ['work/l2b0-mock-output.json'], 'steps': [
                    {'operation': 'generate', 'outcome': 'success', 'cause': 'fixture-a', 'improved': True}]}]},
            'policy': {'mode': 'A', 'expected': {
                'primary': {'state': 'object', 'duration_mins': 300},
                'secondary': {'state': 'object', 'duration_mins': 10080}}},
            'protocol': dict(PROTOCOL), 'adoption': None, 'repair': {'limit': 2, 'adoption': None}}
    data['repair']['adoption'] = simulated_adoption(repair_binding(data))
    return data


def simulated_adoption(binding, absent=()):
    return {'kind': 'simulated-adoption', 'version': 1, 'simulated': True, 'decision': 'adopt',
            'decided_by': 'simulated-reviewer', 'decided_at': '2026-11-14T00:00:00+00:00', 'binding': binding,
            'nonprovided': {n: {'provenance': 'simulated-fixture', 'sha256': digest({'fictional': n})} for n in absent}}
