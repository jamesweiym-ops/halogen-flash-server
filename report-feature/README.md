# /report usage dashboard — private deployment copy

This directory holds my working copy of the halogen OpenAI front-end
(`serve_api.py`) with a per-request usage ledger and a `/report` dashboard
added on top of the `0.11.1` image's file.

**This is a PRIVATE repository.** `serve_api.py` is the proprietary
front-end that ships inside `ghcr.io/peonist-ai/halogen-flash-server` and
is deliberately **not** in the public `peonist-ai/halogen-flash-server`
tree. It is kept here under the halogen EULA for my own use only.

Per `LICENSE.md` §3.1: modifying your own copy for your own use is
permitted; redistributing a modified copy, or presenting a derivative as
halogen, is not. This repo is not a fork and must not be made public.

## Contents

| file | what |
|---|---|
| `serve_api.py` | the patched front-end, running on the AIPC now |
| `report.patch` | `diff -u` of my changes against the pristine 0.11.1 file |
| `ISSUE_report_feature.md` | the write-up intended for the upstream issue tracker |

## Base file identity

Patched against `tools/serve_api.py` as shipped in
`ghcr.io/peonist-ai/halogen-flash-server:0.11.1`:

```
size  234400 bytes
md5   9265df06010e2e778bc78248c93a081d
```

`report.patch` applies cleanly to that file and reproduces `serve_api.py`
byte-for-byte (verified with `patch -p1` + `diff -q`).

## Deploy

The patched file is bind-mounted over the in-image copy:

```
-v /home/james/halogen-serve/serve_api.py:/halogen/tools/serve_api.py:ro
```

Ledger: `/models/halogen-usage.jsonl` (override with `HALOGEN_LEDGER`).
Timezone for bucket labels: `HALOGEN_TZ_OFFSET` (hours, default `8`).

Page: `http://10.10.0.111:8731/report`

## Upgrade hazard

`HALOGEN_IMAGE_VERSION` is an env var and `/health`'s `version.match`
compares it to the engine's self-report — a bind-mounted front-end keeps
saying `match: true` while running arbitrary Python against a different
engine build. Before trusting a mount after any image bump:

```
docker cp <new-container>:/halogen/tools/serve_api.py /tmp/pristine.py
diff /tmp/pristine.py /home/james/halogen-serve/serve_api.py
```

Only the feature hunks in `report.patch` should differ. Anything else means
the mount is stale against the running engine.
