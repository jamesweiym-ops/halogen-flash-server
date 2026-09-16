"""Run on AIPC after staging the rebased API. Preserve the previous container."""
import http.client
import json
import socket
import urllib.request

class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost')
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect('/var/run/docker.sock')

def api(method, path, data=None):
    conn = Docker()
    conn.request(method, '/v1.47' + path,
                 None if data is None else json.dumps(data),
                 {'Content-Type': 'application/json'})
    res = conn.getresponse()
    body = res.read()
    if res.status >= 300:
        raise RuntimeError((res.status, body.decode()))
    return json.loads(body) if body else None

name = 'halogen-flash-server'
backup = 'halogen-flash-server-090-env-backup-20260914'
health = json.load(urllib.request.urlopen('http://127.0.0.1:8731/health'))
if health.get('in_flight') or health.get('queued'):
    raise SystemExit('Active requests exist; refusing to interrupt them')
old = api('GET', '/containers/' + name + '/json')
config = old['Config'].copy()
config['Image'] = 'ghcr.io/peonist-ai/halogen-flash-server:0.9.0'
config['Env'] = [e for e in config['Env'] if not e.startswith('HALOGEN_IMAGE_VERSION=')]
config['Env'].append('HALOGEN_IMAGE_VERSION=0.9.0')
config['HostConfig'] = old['HostConfig']
config['HostConfig']['Binds'] = [
    b.replace('serve_api_080_dynamic.py', 'serve_api_090_dynamic.py')
    for b in config['HostConfig']['Binds']]
# Use the new image metadata, not the previous image's version labels.
config['Labels'] = api('GET', '/images/' + config['Image'] + '/json')['Config'].get('Labels', {})
api('POST', '/containers/create?name=' + name + '-090-staged', config)
try:
    api('POST', '/containers/' + name + '/stop?t=30')
    api('POST', '/containers/' + name + '/rename?name=' + backup)
    api('POST', '/containers/' + name + '-090-staged/rename?name=' + name)
    api('POST', '/containers/' + name + '/start')
except Exception:
    print('Upgrade failed; old container preserved as', backup)
    raise
print('Started 0.9.0; rollback container:', backup)
