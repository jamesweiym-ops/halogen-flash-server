import copy
import http.client
import json
import socket


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


name = "9router"
staged = "9router-bundle-staged"
backup = "9router-source-only-20260915"
image = "9router:reasoning-fix-20260915-bundle2"

old = api("GET", f"/containers/{name}/json")
config = copy.deepcopy(old["Config"])
config["Image"] = image
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
    print(f"Upgrade failed; old container preserved as {backup}")
    raise

print(f"Started {name} with compiled bundle fix; rollback container: {backup}")
