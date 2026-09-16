"""Preserve current Docker configuration and set an 8192-token thinking default."""
import ast
import pathlib
import urllib.request
import json

# Load only the Docker client definitions, never the upgrade procedure.
tree = ast.parse(pathlib.Path(__file__).with_name('upgrade_090.py').read_text())
nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef))]
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<docker-client>', 'exec'))
name = 'halogen-flash-server'
backup = name + '-before-thinking8192-20260915'
staged = name + '-thinking8192-staged'
health = json.load(urllib.request.urlopen('http://127.0.0.1:8731/health'))
if health.get('in_flight') or health.get('queued'):
    raise SystemExit('Active requests exist; refusing to interrupt them')
old = api('GET', '/containers/' + name + '/json')
config = old['Config'].copy()
config['Image'] = old['Image']
config['HostConfig'] = old['HostConfig']
config['Env'] = [e for e in config['Env'] if not e.startswith('HALOGEN_MAX_THINKING_TOKENS=')]
config['Env'].append('HALOGEN_MAX_THINKING_TOKENS=8192')
api('POST', '/containers/create?name=' + staged, config)
api('POST', '/containers/' + name + '/stop?t=30')
api('POST', '/containers/' + name + '/rename?name=' + backup)
api('POST', '/containers/' + staged + '/rename?name=' + name)
api('POST', '/containers/' + name + '/start')
print('Started with default thinking budget 8192; backup:', backup)
