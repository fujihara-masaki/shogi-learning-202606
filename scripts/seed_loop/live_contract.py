"""L2b-1a contracts. No transport, approval generation, or worker execution here."""
from datetime import datetime
import hashlib
import hmac
import re

from .l2b_inputs import NAMES, classify, keys, require
from .state import DEFAULT_CONFIG, LoopError, digest
from .usage import ProtocolError

BASE = '75718764a5794321a55b9b01f130a1c1eb4480f5'
CLI = 'codex-cli 0.167.0'
SOURCE = '086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a'
SCHEMAS = {
    'GetAccountRateLimitsResponse.json': '9c0def7f8ab2396122af939dffbf01b34b8d66082fe4129dd20917bfd4313fdc',
    'GetAccountResponse.json': '1d44d4274ea35e1f866c4b0e3db64678fab108914c276353bdc3b1b0de286459',
    'InitializeCapabilities.ts': '744ccfe4b48827f351d00f4fcaf8b28596f1710f37036850ffeda1b4e4412408',
    'GetAccountParams.ts': '73feed16e294673d984618e2264a32be4b20bfe45973fdba064bddd2e6c6c18a',
    'GetAccountRateLimitsParams.ts': '2777710a93776ec971d9f4a016b20d8f555525d1f40de4a5e7bec6e58ce37e97',
}
CONTRACT = {'source_commit': SOURCE, 'cli_version': CLI, 'schema_sha256': SCHEMAS,
            'methods': ['initialize', 'initialized', 'account/read', 'account/rateLimits/read'],
            'usage_params': {'supportsLunaReserve': False, 'excludeResetCreditDetails': True},
            'account_params': {'refreshToken': False}, 'experimentalApi': False,
            'requestAttestation': False}
CONTRACT_HASH = digest(CONTRACT)
SCOPE = ['api-provided-codex-windows-only', 'null-is-observation-not-permanent-absence',
         'other-buckets-hidden-billing-limits-unmonitored', 'workers-always-disconnected']
PLANS = ('free go plus pro prolite promax team self_serve_business_prolite '
         'self_serve_business_usage_based business ent26 enterprise_cbp_automation '
         'enterprise_cbp_usage_based enterprise edu edu_plus edu_pro sci sci_plus').split()
REACHED = ('rate_limit_reached workspace_owner_credits_depleted workspace_member_credits_depleted '
           'workspace_owner_usage_limit_reached workspace_member_usage_limit_reached').split()
TOP = {'accountId', 'ordinaryUsageAllowed', 'rateLimitResetCredits', 'rateLimitUpsell',
       'rateLimits', 'rateLimitsByLimitId'}
BUCKET = {'limitId', 'limitName', 'normalModelSlug', 'primary', 'secondary', 'credits',
          'individualLimit', 'spendControlReached', 'planType', 'rateLimitReachedType'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(key, value):
    return hmac.new(key, digest(value).encode('ascii'), hashlib.sha256).hexdigest()


def policy(value):
    keys(value, {'kind', 'version', 'bucket', 'expected', 'codex_binary', 'cli_version'}, 'live settings')
    require(value['kind'] == 'seed-loop-live-settings' and type(value['version']) is int and
            value['version'] == 1 and value['bucket'] == 'codex' and value['cli_version'] == CLI,
            'unsupported_live_settings')
    require(isinstance(value['codex_binary'], str) and value['codex_binary'] and
            not any(c in value['codex_binary'] for c in '\r\n"&|<>^%!'), 'unsafe_cli_path')
    keys(value['expected'], NAMES, 'live expected windows')
    for item in value['expected'].values():
        keys(item, {'state', 'duration_mins'}, 'live window expectation')
        require((item['state'] == 'null' and item['duration_mins'] is None) or
                (item['state'] == 'object' and type(item['duration_mins']) is int and
                 item['duration_mins'] > 0), 'invalid_live_expectation')
    require(any(v['state'] == 'object' for v in value['expected'].values()), 'empty_monitoring_set')
    return value


def config(value):
    return {**DEFAULT_CONFIG, 'bucket': value['bucket'], 'codex_binary': value['codex_binary'],
            'windows': [n for n in NAMES if value['expected'][n]['state'] == 'object']}


def account_read(raw, key):
    """No raw identity leaves this function; a second account/read must agree."""
    try:
        require(isinstance(raw, dict) and not set(raw) - {'account', 'requiresOpenaiAuth'} and
                type(raw.get('requiresOpenaiAuth')) is bool, 'unsupported_account_schema')
        a = raw.get('account')
        require(isinstance(a, dict) and not set(a) - {'type', 'email', 'planType', 'workspaceName'} and
                a.get('type') == 'chatgpt' and a.get('planType') in PLANS and
                (a.get('email') is None or isinstance(a['email'], str)) and
                (a.get('workspaceName') is None or isinstance(a['workspaceName'], str)),
                'chatgpt_account_conditions_unavailable')
        return {'auth_type': 'chatgpt', 'plan_type': a['planType'],
                'account_read_hmac': fingerprint(key, a),
                'identity_method': 'account-read-and-usage-account-id-hmac'}
    except LoopError as exc:
        raise ProtocolError(str(exc)) from None


def metadata_shape(selected):
    """Recognized versioned metadata; display strings/credit balances are never evidence."""
    for n in ('limitId', 'limitName', 'normalModelSlug'):
        if selected.get(n) is not None and not isinstance(selected[n], str):
            return False
    if selected.get('planType') not in (None, *PLANS):
        return False
    if selected.get('rateLimitReachedType') not in (None, *REACHED):
        return False
    if selected.get('spendControlReached') is not None and type(selected['spendControlReached']) is not bool:
        return False
    credits = selected.get('credits')
    if credits is not None and not (isinstance(credits, dict) and
            not set(credits) - {'hasCredits', 'unlimited', 'balance'} and
            type(credits.get('hasCredits')) is bool and type(credits.get('unlimited')) is bool and
            (credits.get('balance') is None or isinstance(credits['balance'], str))):
        return False
    limit = selected.get('individualLimit')
    if limit is not None and not (isinstance(limit, dict) and
            set(limit) == {'limit', 'used', 'remainingPercent', 'resetsAt'} and
            all(isinstance(limit[n], str) for n in ('limit', 'used')) and
            type(limit['remainingPercent']) is int and 0 <= limit['remainingPercent'] <= 100 and
            type(limit['resetsAt']) is int and limit['resetsAt'] > 0):
        return False
    return True


def reset_credits_shape(value):
    if value is None:
        return True
    if not (isinstance(value, dict) and not set(value) - {'availableCount', 'credits'} and
            type(value.get('availableCount')) is int and value['availableCount'] >= 0):
        return False
    details = value.get('credits')
    if details is None:
        return True
    if not isinstance(details, list) or len(details) > 1000:
        return False
    for row in details:
        if not (isinstance(row, dict) and not set(row) - {
                'id', 'resetType', 'status', 'grantedAt', 'expiresAt', 'title', 'description'} and
                isinstance(row.get('id'), str) and row.get('resetType') == 'codexRateLimits' and
                row.get('status') in ('available', 'redeeming', 'redeemed') and
                type(row.get('grantedAt')) is int and
                (row.get('expiresAt') is None or type(row['expiresAt']) is int) and
                all(row.get(n) is None or isinstance(row[n], str) for n in ('title', 'description'))):
            return False
    return True


def audit(raw, value, context, key, origin):
    """ID-matched raw -> allowlisted evidence. No mock protocol/adoption is used."""
    evidence = {'kind': 'seed-loop-live-audit', 'version': 1, 'origin': origin,
                'provider': 'codex-app-server' if origin == 'live' else 'test-stdio-app-server',
                'context': context, 'bucket': value['bucket'], 'selection': None,
                'windows': {}, 'S': [], 'schema_reason': None, 'monitoring_reason': None,
                'server_reason': None, 'account': None, 'metadata': {}}
    reason = None
    if (context.get('cli_version') != CLI or context.get('request_id') != 2 or
            context.get('method') != 'account/rateLimits/read'):
        reason = 'protocol_conditions_changed'
    selected = None
    if not isinstance(raw, dict) or set(raw) - TOP or not isinstance(raw.get('rateLimits'), dict):
        reason = reason or 'unknown_response_schema'
    else:
        if 'rateLimitsByLimitId' in raw:
            evidence['selection'] = 'rateLimitsByLimitId'
            multi = raw['rateLimitsByLimitId']
            if not isinstance(multi, dict) or value['bucket'] not in multi:
                reason = reason or 'bucket_unavailable'
            else:
                selected = multi[value['bucket']]
        else:
            evidence['selection'] = 'rateLimits'
            selected = raw['rateLimits']
    if selected is not None:
        if not isinstance(selected, dict) or selected.get('limitId') != value['bucket']:
            reason = reason or 'bucket_identity_mismatch'
        elif set(selected) - BUCKET or not metadata_shape(selected):
            reason = reason or 'unknown_bucket_schema'
        # Both keys are audited even when other fields already deny the read.
        if isinstance(selected, dict):
            for name in NAMES:
                w = classify(selected[name]) if name in selected else {'state': 'missing', 'type': 'missing'}
                # The pinned JSON schema uses int32 (the server rounds core percentages).
                if w['state'] == 'object' and type(w['usedPercent']) is not int:
                    w = {'state': 'invalid', 'type': 'object', 'integer_percent_required': True}
                evidence['windows'][name] = w
                if w['state'] == 'object':
                    evidence['S'].append(name)
                expected = value['expected'][name]
                if w['state'] in ('invalid', 'missing'):
                    reason = reason or 'window_invalid_or_missing'
                if w['state'] != expected['state']:
                    evidence['monitoring_reason'] = 'window_state_changed'
                elif w['state'] == 'object' and w['windowDurationMins'] != expected['duration_mins']:
                    evidence['monitoring_reason'] = 'window_duration_changed'
            if not evidence['S']:
                reason = reason or 'empty_monitoring_set'
    else:
        reason = reason or 'bucket_unavailable'
    if isinstance(raw, dict):
        allowed = raw.get('ordinaryUsageAllowed')
        if allowed is not None and type(allowed) is not bool:
            reason = reason or 'invalid_server_permission'
        if not reset_credits_shape(raw.get('rateLimitResetCredits')):
            reason = reason or 'unknown_reset_credit_schema'
        # This arbitrary JSON banner has no stable restriction schema: diagnostic only.
        if raw.get('rateLimitUpsell') is not None:
            reason = reason or 'unsupported_upsell_metadata'
        raw_id = raw.get('accountId')
        account = context.get('account')
        if isinstance(account, dict) and isinstance(raw_id, str) and raw_id:
            evidence['account'] = {**account, 'usage_account_hmac': fingerprint(key, raw_id)}
        else:
            reason = reason or 'account_identity_unavailable'
        if isinstance(selected, dict) and metadata_shape(selected):
            evidence['metadata'] = {'ordinary_usage_allowed': allowed,
                'spend_control_reached': selected.get('spendControlReached'),
                'rate_limit_reached_type': selected.get('rateLimitReachedType'),
                'plan_type': selected.get('planType'),
                'individual_limit': None if selected.get('individualLimit') is None else {
                    n: selected['individualLimit'][n] for n in ('remainingPercent', 'resetsAt')}}
            if evidence['account'] and selected.get('planType') not in (None, evidence['account']['plan_type']):
                reason = reason or 'account_plan_mismatch'
            if allowed is False or selected.get('spendControlReached') is True or selected.get('rateLimitReachedType'):
                evidence['server_reason'] = 'server_usage_denied'
            elif allowed is not True or selected.get('spendControlReached') is not False:
                evidence['server_reason'] = 'server_permission_unavailable'
            limit = selected.get('individualLimit')
            if limit and limit['remainingPercent'] == 0:
                evidence['server_reason'] = 'server_usage_denied'
    evidence['schema_reason'] = reason
    evidence['reason'] = reason or evidence['monitoring_reason'] or evidence['server_reason']
    return evidence


def grounds(value):
    keys(value, {'kind', 'version', 'official_contract_hash', 'conditions_sha256',
                 'sufficient_for_conditional_scope', 'scope'}, 'adoption grounds')
    require(value['kind'] == 'seed-loop-live-grounds' and type(value['version']) is int and
            value['version'] == 1 and value['official_contract_hash'] == CONTRACT_HASH and
            isinstance(value['conditions_sha256'], str) and
            re.fullmatch('[a-f0-9]{64}', value['conditions_sha256']) and
            value['sufficient_for_conditional_scope'] is True and value['scope'] == SCOPE,
            'grounds_pending_or_unsupported')
    return value


def approval_valid(record, candidate, origin):
    try:
        keys(record, {'kind', 'version', 'origin', 'candidate_hash', 'binding', 'actor',
                      'approved_at', 'operation', 'confirmation_hash', 'scope'}, 'approval')
        require(record['kind'] == ('seed-loop-live-approval' if origin == 'live' else 'seed-loop-test-approval') and
                type(record['version']) is int and record['version'] == 1 and record['origin'] == origin and
                record['candidate_hash'] == digest(candidate) and record['binding'] == candidate['binding'] and
                record['scope'] == SCOPE and record['operation'] == 'interactive-human-confirmation' and
                isinstance(record['actor'], str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', record['actor']) and
                record['confirmation_hash'] == digest('APPROVE ' + digest(candidate)) and
                datetime.fromisoformat(record['approved_at']).utcoffset() is not None,
                'invalid_live_approval')
        require(datetime.fromisoformat(record['approved_at']) >= datetime.fromisoformat(candidate['created_at']),
                'approval_predates_candidate')
    except (LoopError, ValueError, KeyError, TypeError):
        return False
    return True
