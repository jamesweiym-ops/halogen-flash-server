import copy
import http.client
import json
import socket
import urllib.request


class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def api(method, path, body=None):
    conn = Docker()
    payload = None if body is None else json.dumps(body)
    headers = {} if payload is None else {"Content-Type": "application/json"}
    conn.request(method, "/v1.47" + path, payload, headers)
    response = conn.getresponse()
    data = response.read()
    if response.status >= 300:
        raise RuntimeError(f"{response.status}: {data.decode()}")
    return json.loads(data) if data else None


def replace_env(env, prefix, value):
    return [item for item in env if not item.startswith(prefix)] + [value]


name = "halogen-flash-server"
staged = "halogen-flash-server-output512-staged"
backup = "halogen-flash-server-before-output512-20260915"

health = json.load(urllib.request.urlopen("http://127.0.0.1:8731/health", timeout=10))
if health.get("in_flight") or health.get("queued"):
    raise SystemExit("Active requests exist; refusing to interrupt them")

old = api("GET", f"/containers/{name}/json")
config = copy.deepcopy(old["Config"])
config["Env"] = replace_env(
    config["Env"], "HALOGEN_MAX_TOKENS_CAP=", "HALOGEN_MAX_TOKENS_CAP=524288"
)
# Keep the ordinary omitted-budget default at 256k; only explicit requests
# can use the new 512k ceiling.
config["Env"] = replace_env(
    config["Env"], "HALOGEN_MAX_TOKENS_DEFAULT=", "HALOGEN_MAX_TOKENS_DEFAULT=262144"
)

api("POST", f"/containers/create?name={staged}", {
    **config,
    "HostConfig": copy.deepcopy(old["HostConfig"]),
})
try:
    api("POST", f"/containers/{name}/stop?t=30")
    api("POST", f"/containers/{name}/rename?name={backup}")
    api("POST", f"/containers/{staged}/rename?name={name}")
    api("POST", f"/containers/{name}/start")
except Exception:
    print(f"Rollout failed; old container preserved as {backup}")
    raise

print(f"Started output-cap rollout; rollback container: {backup}")
