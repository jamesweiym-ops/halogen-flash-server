# /report usage dashboard — private deployment copy

My working copy of the halogen OpenAI front-end (`serve_api.py`) with a
per-request usage ledger and a `/report` dashboard added on top of the
`0.11.1` image's file.

**PRIVATE repo.** `serve_api.py` is the proprietary front-end that ships
inside `ghcr.io/peonist-ai/halogen-flash-server` and is deliberately **not**
in the public `peonist-ai/halogen-flash-server` tree. Kept here under the
halogen EULA for my own use only. Per `LICENSE.md` §3.1: modifying your own
copy for your own use is permitted; redistributing a modified copy, or
presenting a derivative as halogen, is not. Do not make this repo public.

## Files

| file | what |
|---|---|
| `serve_api.py` | the patched front-end currently running on the AIPC |
| `report.patch` | `git diff` of my changes vs the pristine 0.11.1 file |
| `pristine-0.11.1.py` | the untouched 0.11.1 front-end = the merge base |
| `rebase_report.py` | re-lands the feature onto a NEWER image, then deploys |
| `ISSUE_report_feature.md` | the write-up for the upstream issue tracker |

Base file identity: `tools/serve_api.py` as shipped in
`ghcr.io/peonist-ai/halogen-flash-server:0.11.1`, 234400 bytes,
md5 `9265df06010e2e778bc78248c93a081d`. `report.patch` reproduces
`serve_api.py` from that base byte-for-byte.

## What it records

One JSONL line per finished request at the existing
`engine.metrics.record(timings(d), ...)` call site — every number is the
engine's own D line, nothing re-measured:

`ts, endpoint, model, client, stream, status, prompt_tokens, cached_tokens,
output_tokens, prefill_ms, decode_ms, prompt_per_second,
predicted_per_second, draft_n, draft_n_accepted, structured, elapsed_ms`

Ledger: `/models/halogen-usage.jsonl` (override `HALOGEN_LEDGER`).
Bucket timezone: `HALOGEN_TZ_OFFSET` hours, default `8`.
Page: `http://10.10.0.111:8731/report`
APIs: `/api/report/usage?unit=hour|day|week|month&count=N`,
`/api/report/logs?page=N&pageSize=N`, `/api/report/totals`.

## Deploy (current shape)

The patched file is bind-mounted over the in-image copy:

```
-v /home/james/halogen-serve/serve_api.py:/halogen/tools/serve_api.py:ro
```

The ledger lives in `/models` (already mounted), so it survives every swap.

## How to restore the dashboard after a halogen upgrade

**Do not** just `docker pull && docker run` — that drops the bind-mount and
the page 404s silently. Use the rebase script, which re-lands the feature
onto the new image's own front-end:

```bash
# 1. pull the new image
docker pull ghcr.io/peonist-ai/halogen-flash-server:<NEW>

# 2. dry-run: rebase only, report whether it merges cleanly
cd /home/james/halogen-serve
sudo python3 rebase_report.py ghcr.io/peonist-ai/halogen-flash-server:<NEW> --dry-run

# 3. if the dry-run says "applied cleanly" or "auto-resolved 1 block", deploy
sudo python3 rebase_report.py ghcr.io/peonist-ai/halogen-flash-server:<NEW>
```

The script:
- extracts the pristine `serve_api.py` from the NEW image (throwaway
  container, never runs it),
- 3-way merges my feature commit onto it (base = `pristine-0.11.1.py`),
- auto-resolves the one known conflict shape (a new param added to
  `serve()`'s signature — keeps upstream's signature, keeps my block),
- gates on: no leftover conflict markers, valid Python AST, feature markers
  present. If any gate fails it **stops and does not deploy**, printing the
  conflict for a human.
- then stops the live container, renames it to a dated backup, and starts a
  fresh one from the NEW image with the merged file bind-mounted.

Verified against a simulated 0.12.0 that adds a comment + a new `serve()`
param: auto-resolves to 1 block, upstream changes survive, ledger + page
present, AST OK.

### If the script says "needs a human"

Upstream moved a region I touch. Open the printed conflict, keep upstream's
lines and re-add my block below them, then re-run. The merge base is
`pristine-0.11.1.py` so `git diff` shows exactly what I changed.

### Rollback

The previous container is renamed, not deleted:

```bash
docker stop halogen-flash-server
docker rename halogen-flash-server halogen-flash-server-bad
docker rename <backup-name> halogen-flash-server
docker start halogen-flash-server
```

## Upgrade hazard (why the rebase script exists)

`HALOGEN_IMAGE_VERSION` is an env var and `/health`'s `version.match`
compares it to the engine's self-report — a bind-mounted front-end keeps
saying `match: true` while running arbitrary Python against a different
engine build. The rebase script avoids this by rebuilding the merged file
from the NEW image's own pristine front-end each time, rather than pinning
an old one.
