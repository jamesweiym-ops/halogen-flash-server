# Feature: per-request usage ledger + `/report` dashboard (pp/tg rates, cache tokens, hour/day/week/month)

**Image:** `ghcr.io/peonist-ai/halogen-flash-server:0.11.1`
**Front-end:** `tools/serve_api.py` (no engine change — everything is already on the D line)

## What I wanted

A usage page like llama.cpp-hub's 用量报表: total input / output / cache-hit tokens, bucketed by
hour / day / week / month, plus a per-request log with time, endpoint, prompt tokens, cached
tokens, output tokens, and **both** pp and tg rates.

`/metrics` already has the lifetime counters, but it is cumulative-only and its rate gauges reset
on every scrape, so there is no history and no per-request record.

## What I built

A ~380-line patch to `tools/serve_api.py` that adds:

1. **`RequestLedger`** — one JSONL line per finished request, written at the existing
   `engine.metrics.record(timings(d), ...)` call site. Every field is the engine's own D line
   copied through `timings()`; nothing is re-measured:

   `ts, endpoint, model, client, stream, status, prompt_tokens, cached_tokens, output_tokens,
   prefill_ms, decode_ms, prompt_per_second, predicted_per_second, draft_n, draft_n_accepted,
   structured, elapsed_ms`

   Path: `$HALOGEN_LEDGER`, default `/models/halogen-usage.jsonl` (the model bind-mount, so it
   survives the container being replaced). Rotates to `<path>.1` at 64 MB. A write failure is
   swallowed — it can never break serving.

2. **Endpoints**
   - `GET /report` — the dashboard (self-contained HTML, vanilla canvas, no chart lib)
   - `GET /api/report/usage?unit=hour|day|week|month&count=N` — bucketed series
   - `GET /api/report/logs?page=N&pageSize=N` — paged per-request log
   - `GET /api/report/totals` — lifetime sums + per-endpoint breakdown + hit rate

3. **`ctx` threading** — `serve()` builds `{endpoint, model, client, stream, structured,
   t_start}` once and passes it into `run()`, which hands it to the ledger beside the D line.
   `endpoint` is passed by the route rather than derived from `wire`, because `wire` says how
   bytes are serialized, not who asked.

## Notes on the numbers

`prompt_per_second` is the engine's processed-prompt rate (prompt minus the cached prefix), i.e.
the same definition `timings()` already uses for issue #48 — so a warm 97k-token turn reads as a
real prefill rate, not as 53,000 tok/s. The report shows it as a separate **pp tok/s** column
beside **tg tok/s** rather than one merged `tok/s`, because conflating them is what made the
first cut of this page look like it "had no pp speed".

## The deployment problem this exposes

I run the front-end as a bind-mount over `/halogen/tools/serve_api.py`, which is how the
existing `HALOGEN_*` override workflow already works. That has a sharp edge worth documenting:

`HALOGEN_IMAGE_VERSION` is an env var, and `/health` reports `version.match` by comparing it to
the engine's self-reported version. A bind-mounted front-end keeps reporting `match: true` while
running arbitrary Python against a different engine build. My rebase check is now:

```
docker cp <new-image>:/halogen/tools/serve_api.py /tmp/pristine.py
diff /tmp/pristine.py <mine>   # must show ONLY my feature hunks
```

If the pristine file differs from my base anywhere outside those hunks, the mount is stale.
Would a `--check-base <sha>` flag (front-end refuses to start if its own file hash doesn't match
what the image recorded at build) be worth having? That turns a silent drift into a startup error.

## Repro / verification

Deployed on a Strix Halo (gfx1151), 2 slots, 1M ctx, prompt cache mode 2. Live ledger line:

```json
{"ts": 1789568143.237, "endpoint": "/v1/chat/completions", "model": "halogen-qwen3.8-flash-next",
 "client": "172.17.0.1", "stream": false, "status": "length", "prompt_tokens": 57,
 "cached_tokens": 0, "output_tokens": 8, "prefill_ms": 689.0, "decode_ms": 178.5,
 "prompt_per_second": 82.729, "predicted_per_second": 44.818, "draft_n": 1,
 "draft_n_accepted": 1, "structured": false, "elapsed_ms": 871.6}
```

Bucketing verified against synthetic records spanning today / yesterday / last month for all four
units (hour/day/week/month), including ISO week labels.

## Patch

Attached: `report.patch` — `diff -u` against the 0.11.1 `tools/serve_api.py` as shipped
(234,400 bytes, md5 `9265df06010e2e778bc78248c93a081d`). 386 added lines, 5 changed.

I read CONTRIBUTING.md — I know you can't take the diff into a proprietary build, and I'm not
asking you to. The mechanism and the measurements are the useful part; if this lands, it'll be
your implementation and I'd just like the diagnosis credited.
