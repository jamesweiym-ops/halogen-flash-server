# /report usage dashboard — private deployment copy

My working copy of the halogen OpenAI front-end (`serve_api.py`): a
per-request usage ledger + `/report` dashboard, plus a fix so an omitted
output budget is clamped to the context room. Built on the current image's
file, `0.11.9`.

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
| `report.patch` | `git diff` of my changes vs the pristine 0.11.4 file |
| `pristine-0.11.9.py` | the untouched 0.11.9 front-end = the merge base |
| `pristine-0.11.4.py` | the earlier merge base, kept for history |
| `rebase_report.py` | re-lands the feature onto a NEWER image, then deploys |
| `ISSUE_report_feature.md` | the write-up for the upstream issue tracker |

Base file identity: `tools/serve_api.py` as shipped in
`ghcr.io/peonist-ai/halogen-flash-server:0.11.9`, 245548 bytes,
md5 `bb976e1e41c932e23eb2a6f11ee71bdd`. `report.patch` reproduces
`serve_api.py` from that base byte-for-byte.

Current deployment: **0.11.9**. Clean cherry-pick; the merge base is now
0.11.9 so the patch stays "my changes only" going forward. (The 0.11.4 rebase
had wrongly started deleting upstream's `cache_stats` fields `tapped`,
`full_hits` and `pool`; that is fixed, and `/cache` reports them again.)

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

The page is a month browser. Two views, one period each, chosen with the
year/month dropdowns:
- **按日** — every day of the selected month; for the current month the
  series stops at today so there are no future all-zero bars.
- **按小时** — the 24 hours of the selected month's last day (today, when
  the month is the current one), because the month's real last day is in
  the future then.

APIs: `/api/report/usage?unit=hour|day&year=YYYY&month=M`,
`/api/report/months`, `/api/report/logs?page=N&pageSize=N`,
`/api/report/totals`.

## /pulse — request-level dashboard (HALO-PULSE style)

A second page, `GET /pulse`, modeled on the community "HALO PULSE" board:
per-request scatter/lines instead of day/month aggregation. Backed by
`GET /api/pulse?window=5m|15m|30m|1h|3h|6h|12h|24h`.

- **每请求 DECODE 散点** — X=真实时间, Y=t/s, 点大小=输出 tok 数.
- **每请求 PREFILL t/s**, **每请求缓存命中 %**, **MTP commit/round**,
  **Prompt 规模 tokens** — per-request line charts.
- **KV 池占用时间线** — a 15s sampler (`_pool_sampler` in startup) reads
  `cache_stats()`'s `pool` block into a 5760-point ring (24h).
- **请求明细** — newest-first table.
- Summary cards: 请求数 / DECODE 均值 / DECODE P50 / PREFILL 加权 /
  缓存命中 / MTP commit / 输出总量 / 忙碌时长.

"空间不稀释": rates are each request's own tok÷dur (and PREFILL is the
window's Σtokens÷Σseconds), not a lifetime average — the same honest
口径 the community board uses. The ledger now also stores `rounds` and
`commit` per request so the MTP commit/round chart is exact.

The ledger keeps an in-memory ring (`recent`, 20k) seeded at startup so the
15s auto-refresh never re-reads the file.

## Omitted output budget is clamped to the room

Stock 0.11.4 fills an omitted `max_tokens` with the server default
(262144) and returns **400** when `prompt + default` exceeds the context —
so a ~950k-token prompt with no budget is refused even though the prompt
itself fits. This copy marks whether the client actually sent a budget
(`explicit_max`) and only shrinks it when the client did not:

- omitted budget + default does not fit → accept, set the budget to
  `context - prompt`. A default is the server's own number, not the
  client's ask, so it must not turn a long-context request into an error.
- **explicit** budget over the room → still a hard 400, never silently
  clamped (a truncated reply and a model that stopped look identical).

Verified live: an 850k-token prompt with no budget returns 200; the same
prompt with `max_output_tokens: 262144` still returns the 400.

## Over-context prompt returns a real 400, not a dead stream

The prompt ceiling (`len(ids) >= ctx`) used to be checked only inside the
body generator, i.e. after the streaming route had already sent its 200
headers. An over-context prompt therefore arrived as an in-stream error
event and OpenAI clients reported it as the opaque
`stream disconnected before completion: stream closed before
response.completed`. `serve()` now checks it before building the
`StreamingResponse`, so the client gets `400 prompt N tokens exceeds
context M` directly. (It also stops the omitted-budget clamp from masking
it, since the room is negative in that case.)

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
- 3-way merges my feature commit onto it (base = `pristine-0.11.9.py`),
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
`pristine-0.11.9.py` so `git diff` shows exactly what I changed.

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
