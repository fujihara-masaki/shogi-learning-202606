"""A separate JSONL server process. Reject any unexpected/inference request."""
import json
import sys
import time

mode = sys.argv[1]

def read():
    return json.loads(sys.stdin.readline())


def send(value):
    print(json.dumps(value), flush=True)

first = read()
assert first["id"] == 1 and first["method"] == "initialize"
assert first["params"]["clientInfo"]["name"] == "shogi_seed_loop"
if mode == "handshake-error":
    send({"id": 1, "error": {"code": -32601, "message": "unsupported"}})
    sys.exit()
send({"method": "account/rateLimits/updated", "params": {"rateLimits": {}}})
send({"id": 901, "result": {"unrelated": True}})
send({"id": 1, "result": {"userAgent": "fake"}})
assert read() == {"method": "initialized"}
request = read()
assert request == {"id": 2, "method": "account/rateLimits/read", "params": {}}
if mode == "timeout":
    time.sleep(10)
elif mode == "eof":
    sys.exit()
elif mode == "malformed":
    print("not JSON", flush=True)
elif mode == "error":
    send({"id": 2, "error": {"code": -32000, "message": "unauthenticated SECRET_MUST_NOT_LEAK"}})
elif mode == "unsupported":
    send({"id": 2, "error": {"code": -32601, "message": "unsupported"}})
else:
    # Notification falsely advertises 0%; only the explicit response may be used.
    send({"method": "account/rateLimits/updated", "params": {"rateLimits": {"primary": {"usedPercent": 0}}}})
    send({"id": 88, "result": {"rateLimits": {"primary": {"usedPercent": 0}}}})
    send({"id": 2, "result": {"rateLimits": {}, "rateLimitsByLimitId": {
        "unrelated": {"primary": {"usedPercent": 100}},
        "codex": {"limitId": "codex", "primary": {"usedPercent": 24},
                  "secondary": {"usedPercent": 8, "windowDurationMins": 10080, "resetsAt": None}}}}})
