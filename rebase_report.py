#!/usr/bin/env python3
"""Re-land the /report feature onto a NEWER halogen image, then deploy it.

Run this on the AIPC after `docker pull`ing a new halogen-flash-server tag.
It never trusts the running container: it extracts the pristine
`serve_api.py` from the NEW image, applies the saved feature patch with a
3-way merge, auto-resolves the one known conflict shape (a new parameter
added to `serve()`'s signature), and only then swaps the bind-mount.

    sudo python3 rebase_report.py <new-image> [--name halogen-flash-server]

If the patch does not apply cleanly and the conflict is NOT the known shape,
it stops and prints the conflict for a human. It will not guess.

The ledger (/models/halogen-usage.jsonl) is on the model bind-mount and is
never touched here, so history survives every upgrade.
"""
import argparse
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

FEATURE_COMMIT_MSG = "FEATURE: /report usage dashboard"
PATCH = os.environ.get("REPORT_PATCH", "/home/james/halogen-serve/report.patch")
# The pristine front-end this patch was written against. It is the merge
# base: the 3-way merge needs it to tell "my change" from "upstream's
# change". Bumped to the running image (0.11.9) when the deployment was
# rebased onto it. Saved alongside the patch so the rebase never depends on
# the running container.
BASE_PRISTINE = os.environ.get("REPORT_BASE", "/home/james/halogen-serve/pristine-0.11.9.py")
STAGE = "/home/james/halogen-serve/serve_api.py"
MOUNT = f"{STAGE}:/halogen/tools/serve_api.py:ro"


class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def api(method, path, data=None):
    c = Docker()
    body = None if data is None else json.dumps(data)
    c.request(method, "/v1.47" + path, body, {"Content-Type": "application/json"})
    r = c.getresponse()
    out = r.read()
    if r.status >= 300:
        raise RuntimeError((r.status, out.decode(errors="replace")))
    return json.loads(out) if out else None


def sh(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)


def extract_pristine(image, dest):
    """Pull the untouched serve_api.py out of the new image without running it."""
    cid = sh(f"docker create --entrypoint /bin/true {image}").stdout.strip()
    if not cid:
        sys.exit(f"could not create a throwaway container from {image}")
    try:
        r = sh(f"docker cp {cid}:/halogen/tools/serve_api.py {dest}")
        if r.returncode != 0:
            sys.exit("could not read /halogen/tools/serve_api.py from the image:\n" + r.stderr)
    finally:
        sh(f"docker rm -f {cid} >/dev/null")
    return dest


def auto_resolve(path):
    """The one conflict shape we know: upstream added a parameter to
    serve()'s signature line, which sits right where we insert the ledger
    context. Resolution: keep OURS (upstream's signature), keep THEIRS
    (our inserted block) below it. Returns the number of blocks resolved."""
    s = open(path).read()
    pat = re.compile(r"<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*\n", re.S)

    def fix(m):
        ours, theirs = m.group(1), m.group(2)
        tl = theirs.split("\n")
        # ours = the signature line upstream now has; tl[1:] = our block
        return ours + "\n" + "\n".join(tl[1:]) + "\n"

    out, n = pat.subn(fix, s)
    open(path, "w").write(out)
    return n


def rebase(image, workdir):
    """Re-land the feature onto the new image's pristine front-end.

    Uses the cherry-pick flow (not `git apply -3`): the patch's pre-image
    is the saved 0.11.1 base, the new image's file is `ours`, the feature
    commit is `theirs`. That gives a real 3-way merge that can tell my
    inserted block apart from upstream's edits, and leaves conflict markers
    only where they genuinely overlap.
    """
    new_pristine = os.path.join(workdir, "new_pristine.py")
    extract_pristine(image, new_pristine)
    nb = open(new_pristine, "rb").read()
    print(f"pristine from {image}: {len(nb)} bytes")

    if not os.path.exists(BASE_PRISTINE):
        sys.exit(f"missing merge base {BASE_PRISTINE}; cannot rebase safely")
    base_bytes = open(BASE_PRISTINE, "rb").read()

    repo = os.path.join(workdir, "repo")
    os.makedirs(os.path.join(repo, "tools"), exist_ok=True)
    f = os.path.join(repo, "tools", "serve_api.py")
    def g(*args):
        import shlex
        return sh("git -C " + shlex.quote(repo)
                 + " -c user.email=r@r -c user.name=r "
                 + " ".join(shlex.quote(a) for a in args))

    # 1. base commit = the 0.11.1 the patch was written against
    open(f, "wb").write(base_bytes)
    g("init", "-q", ".")
    g("add", "-A")
    g("commit", "-qm", "base: 0.11.1")
    base_sha = g("rev-parse", "HEAD").stdout.strip()
    if not base_sha:
        sys.exit("could not create the base commit")

    # 2. feature commit = base + patch
    r = g("apply", PATCH)
    if r.returncode != 0:
        sys.exit("patch does not apply to the saved 0.11.1 base — the patch "
                 "or the base file is wrong:\n" + r.stderr)
    g("add", "-A")
    g("commit", "-qm", FEATURE_COMMIT_MSG)
    feat = g("rev-parse", "HEAD").stdout.strip()

    # 3. branch a SECOND line off base for the new image, so the feature is
    #    a sibling of upstream rather than its ancestor. Cherry-picking an
    #    ancestor is a no-op; cherry-picking a sibling is the real 3-way.
    g("checkout", "-q", base_sha)
    open(f, "wb").write(nb)
    g("add", "-A")
    g("commit", "-qm", "upstream: new image")
    cp = sh(f"git -C {repo} -c user.email=r@r -c user.name=r cherry-pick {feat}")
    merged = f
    text = open(merged).read()

    if cp.returncode != 0:
        if "<<<<<<<" not in text:
            sys.exit("cherry-pick failed with no conflict markers "
                    "(rename/delete?) — needs a human:\n" + cp.stderr)
        n = auto_resolve(merged)
        text = open(merged).read()
        print(f"auto-resolved {n} conflict block(s)")
        if "<<<<<<<" in text:
            print("\n".join(l for l in text.split("\n")
                           if re.match(r"^(<<<<<<<|=======|>>>>>>>)", l)))
            sys.exit("unresolved conflicts remain — needs a human. Not deploying.")
    else:
        print("cherry-pick applied cleanly (no conflict)")

    # syntax gate: never deploy a file that will not import
    r = sh(f"python3 -c \"import ast; ast.parse(open('{merged}').read())\"")
    if r.returncode != 0:
        sys.exit("merged file is not valid Python; not deploying.\n" + r.stderr)

    # sanity: the feature is actually present, and it is the CURRENT feature
    # (the years/months browser), not a stale copy of the patch.
    for probe in ("engine.ledger.record", "REPORT_HTML", "/api/report/usage",
                  "/api/report/months"):
        if probe not in text:
            sys.exit(f"feature marker {probe!r} missing after merge; not deploying.")

    return merged


def deploy(name, merged_path, image):
    health = json.load(urllib.request.urlopen(f"http://127.0.0.1:8731/health"))
    if health.get("in_flight") or health.get("queued"):
        sys.exit("active requests; refusing to interrupt")

    old = api("GET", "/containers/" + name + "/json")
    config = json.loads(json.dumps(old["Config"]))
    hostconfig = json.loads(json.dumps(old["HostConfig"]))
    binds = [b for b in (hostconfig.get("Binds") or []) if "serve_api.py" not in b]
    binds.append(MOUNT)
    hostconfig["Binds"] = binds
    hostconfig["Mounts"] = [m for m in (hostconfig.get("Mounts") or [])
                           if "serve_api" not in json.dumps(m)]
    config["HostConfig"] = hostconfig

    # Switch to the NEW image. The old container's Config carries the old
    # tag, and its HALOGEN_IMAGE_VERSION env would otherwise keep /health
    # reporting the old version against the new engine.
    config["Image"] = image
    tag = image.rsplit(":", 1)[-1] if ":" in image.rsplit("/", 1)[-1] else "latest"
    env = [e for e in config.get("Env", [])
           if not e.startswith("HALOGEN_IMAGE_VERSION=")]
    env.append("HALOGEN_IMAGE_VERSION=" + tag)
    config["Env"] = env
    try:
        config["Labels"] = api("GET", "/images/" + image + "/json")["Config"].get("Labels", {})
    except Exception:
        pass

    backup = f"{name}-before-report-rebase-{time.strftime('%Y%m%d-%H%M%S')}"
    print(f"switching image -> {image}")
    print(f"stopping {name}; backup -> {backup}")
    api("POST", f"/containers/{name}/stop?t=40")
    api("POST", f"/containers/{name}/rename?name={backup}")
    created = api("POST", "/containers/create?name=" + name, config)
    api("POST", f"/containers/{created['Id']}/start")
    print("started", created["Id"][:12], "— waiting for /health")
    for _ in range(180):
        time.sleep(2)
        try:
            h = json.load(urllib.request.urlopen("http://127.0.0.1:8731/health", timeout=3))
            if h.get("status") == "ok":
                print("healthy. version:", h.get("version"))
                break
        except Exception:
            pass
    else:
        sys.exit(f"not healthy in 360s. Roll back: docker stop {name} && "
                f"docker rename {name} {name}-bad && docker rename {backup} {name} && docker start {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="new halogen image, e.g. ghcr.io/.../halogen-flash-server:0.12.0")
    ap.add_argument("--name", default="halogen-flash-server")
    ap.add_argument("--dry-run", action="store_true", help="rebase and report, do not deploy")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as wd:
        merged = rebase(a.image, wd)
        if a.dry_run:
            print(f"\n[dry-run] merged cleanly to {merged}; not deploying.")
            return
        # stage it where the bind-mount points
        os.makedirs(os.path.dirname(STAGE), exist_ok=True)
        if os.path.exists(STAGE):
            os.replace(STAGE, STAGE + ".old")
        with open(merged) as f, open(STAGE, "w") as t:
            t.write(f.read())
        print("staged ->", STAGE)
        deploy(a.name, STAGE, a.image)
        for p in ("/report", "/api/report/totals"):
            try:
                r = urllib.request.urlopen("http://127.0.0.1:8731" + p, timeout=5)
                print(p, "->", r.status)
            except Exception as e:
                print(p, "FAILED", e)


if __name__ == "__main__":
    main()
