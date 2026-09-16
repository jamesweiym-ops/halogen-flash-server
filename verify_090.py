import json
import urllib.request

base = 'http://10.10.0.111:8731'
health = json.load(urllib.request.urlopen(base + '/health', timeout=10))
assert health['version'] == {'api': '0.9.0', 'engine': '0.9.0', 'match': True}, health['version']
assert health['slots'] == 4 and health['context'] == 262144
assert health['local_patch'] == 'remaining-context-budget-v1'
assert health['vision']['enabled']
print('health/version/config OK')
for route, payload in [
    ('/v1/chat/completions', {'messages': [{'role':'user','content':'Reply only OK.'}], 'max_tokens':32}),
    ('/v1/responses', {'input':'Reply only OK.', 'max_output_tokens':32}),
    ('/v1/responses', {'input':'Reply only OK.'}),
]:
    payload.update(model=health['model'], stream=True, enable_thinking=False)
    req = urllib.request.Request(base + route, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=60) as res:
        body = res.read().decode()
    terminal = 'response.completed' if route.endswith('responses') else '[DONE]'
    assert terminal in body, body[-1500:]
    print(route, 'automatic' if not any(k.startswith('max_') for k in payload) else 'explicit', 'terminal OK', body[-400:])
