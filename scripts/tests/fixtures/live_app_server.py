"""Fixed CI-only 0.167.0 stdio server. No account, token, network or worker."""
import json
from pathlib import Path
import sys
import time

if sys.argv[1] == '--version':
    value = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    print(value.get('cli_version', 'codex-cli 0.167.0'))
    raise SystemExit()
fixture, trace = (Path(p) for p in sys.argv[1:3])
value = json.loads(fixture.read_text(encoding='utf-8'))


def receive():
    request = json.loads(sys.stdin.buffer.readline())
    with trace.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(request) + '\n')
    return request


def send(value):
    sys.stdout.buffer.write((json.dumps(value) + '\r\n').encode('utf-8'))
    sys.stdout.buffer.flush()


request = receive()
assert request['method'] == 'initialize'
assert request['params']['capabilities'] == {'experimentalApi': False, 'requestAttestation': False}
send({'id': 1, 'result': {'userAgent': 'test-only', 'codexHome': 'SECRET_LOCAL_PATH',
                         'platformFamily': 'windows', 'platformOs': 'windows'}})
assert receive() == {'method': 'initialized'}
request = receive()
assert request == {'id': 3, 'method': 'account/read', 'params': {'refreshToken': False}}
send({'id': 3, 'result': value['account']})
request = receive()
assert request == {'id': 2, 'method': 'account/rateLimits/read', 'params': {
    'supportsLunaReserve': False, 'excludeResetCreditDetails': True}}
mode = value.get('mode')
if mode == 'timeout':
    time.sleep(20)
if mode == 'eof':
    raise SystemExit()
if mode in ('error', 'unsupported'):
    send({'id': 2, 'error': {'code': -32601 if mode == 'unsupported' else -32000,
                            'message': 'SECRET_SERVER_ERROR'}})
    sys.stdin.buffer.read()
    raise SystemExit()
if mode == 'malformed':
    print('not-json', flush=True)
    sys.stdin.buffer.read()
    raise SystemExit()
send({'method': 'account/rateLimits/updated', 'params': {'rateLimits': {'primary': {'usedPercent': 0}}}})
send({'id': 999, 'result': {'rateLimits': {}}})
send({'id': 2, 'result': value['result']})
request = receive()
assert request == {'id': 4, 'method': 'account/read', 'params': {'refreshToken': False}}
send({'id': 4, 'result': value.get('account_after', value['account'])})
sys.stdin.buffer.read()  # The real adapter must terminate and close this owned server.
