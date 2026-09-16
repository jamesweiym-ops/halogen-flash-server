# AIPC dynamic output budget

Updated on 2026-09-15, rebased onto the bundled Halogen 0.9.0 API source.

- Context / actual KV pool: 1048576; two slots; static YaRN factor 4.
- 1M deployment: HALOGEN_ROPE_YARN=4, HALOGEN_CTX=1048576,
  HALOGEN_KV_POOL_POSITIONS=1048576, HALOGEN_MAX_TOK=16384.
- The one 1M-position pool is shared by two slots; slots do not create two
  separate 1M pools. Requests reserve prompt plus output positions and queue
  when the shared pool cannot fit them.
- API cap: 524288; the omitted-budget default remains 262144. Omitted output
  budget is computed after rendering the complete prompt and expanding image
  tokens: min(cap, context - prompt - 1024).
- Explicit output budgets retain upstream validation and are never silently
  increased or clamped. Remove client max_tokens / max_completion_tokens /
  max_output_tokens settings to use automatic budgeting. A client setting of
  65536 still limits that request to 65536.
- Queue timeout: 14400 seconds, to accommodate longer requests.
  Automatic-budget requests reserve almost the entire pool; other requests
  may queue even with two slots. Explicit smaller budgets allow concurrency.
- An explicit max_output_tokens / max_completion_tokens / max_tokens of up to
  524288 is now accepted, but prompt plus that output must still fit the 1M
  context and the shared pool can make the second slot queue.
- Thinking settings, MTP, vision and model weights are unchanged. The prefill
  width is 16384 for the 1M configuration.
- The /health output_budget_policy field describes the dynamic policy;
  max_tokens_default reflects the configured nominal ceiling, not the actual
  per-request allowance. Logs record prompt length and effective budget.

Source: serve_api_090_dynamic.py. Remote persistent copy:
/home/james/halogen-models/serve_api_090_dynamic.py, mounted read-only at
/halogen/tools/serve_api.py. Container restart policy: unless-stopped.

This is a local API patch. Before upgrading the Halogen image, rebase the
small budget changes onto its bundled API; do not reuse this entire 0.9.0
file over a newer API.

Rollback container (stopped, preserved):
halogen-flash-server-080-backup-20260914 (previous live version).
Older backup:
halogen-flash-server-256k-64k-backup-20260913.
The previous dynamic-budget single-slot container is also preserved as
halogen-flash-server-dynamic-1slot-backup-20260913.
Stop the current container, rename it to an unused name, rename the backup
to halogen-flash-server, and start the backup to restore the former policy.

Validation: budget helper tests at short/long/full-context boundaries; live
automatic chat and Responses requests; explicit 128k request; explicit
one-token completion; above-cap rejection; streaming completion; full-context
prompt rejection. These are functional tests, not a sustained throughput
benchmark or proof that a 200k-token reasoning chain will finish with prose.

0.9.0 upgrade verification: API/engine both report 0.9.0; four budget unit
tests pass; direct streaming Chat and Responses explicit-budget requests
and an automatic-budget Responses request return terminal markers.
Vision remains enabled; composable context remains disabled. On 2026-09-15,
HALOGEN_MAX_THINKING_TOKENS=8192 was configured as the server default;
explicit request thinking budgets override it. Total output policy is unchanged.
The long-output proxy failure is not proven fixed.

1M/two-slot rollout verification on 2026-09-15: /health reports context and KV
pool 1048576 with YaRN factor 4 and two slots; a direct non-thinking Chat smoke
request returned OK. Startup measured 68.0 GiB weights, 28.8 GiB KV, 12.3 GiB
working memory (109.1 GiB total), and warned about 1226 compaction stalls (109
failed), so this configuration is resource-tight on the shared host. These are
short direct API checks, not a sustained throughput benchmark.
