"""Fixed fictional stdio server/worker. No network, commands, artifacts or DB access."""
import json
from pathlib import Path
import sys


def usage_example():
    return {'kind': 'seed-loop-l2b0-usage', 'version': 1, 'simulated': True, 'result': {
        'rateLimitsByLimitId': {'codex': {'limitId': 'codex',
            'primary': {'usedPercent': 4, 'windowDurationMins': 300, 'resetsAt': 4102444800},
            'secondary': {'usedPercent': 6, 'windowDurationMins': 10080, 'resetsAt': 4102444800}}}}}


def main():
    mode, name = sys.argv[1:]
    data = json.loads(Path(name).read_text(encoding='utf-8'))
    if mode == 'usage':
        assert data['kind'] == 'seed-loop-l2b0-usage' and data['simulated'] is True
        def read():
            return json.loads(sys.stdin.readline())
        def send(value):
            print(json.dumps(value), flush=True)
        initial = read()
        assert initial['id'] == 1 and initial['method'] == 'initialize'
        send({'id': 1, 'result': {}})
        assert read() == {'method': 'initialized'}
        assert read() == {'id': 2, 'method': 'account/rateLimits/read', 'params': {}}
        # Deliberately mixed noise cannot reach the audited callback.
        send({'method': 'account/rateLimits/updated', 'params': usage_example()['result']})
        send({'id': 700, 'result': usage_example()['result']})
        send({'id': 2, 'result': data['result']})
    elif mode == 'worker':
        assert data['kind'] == 'l2b0-mock-request' and data['simulated'] is True
        assert data['step']['operation'] in ('generate', 'repair')
        assert data['step']['outcome'] in ('success', 'failed')
        print(json.dumps({**data, 'kind': 'l2b0-mock-result'}), flush=True)
    else:
        raise ValueError('unsupported simulated action')


if __name__ == '__main__':
    main()
