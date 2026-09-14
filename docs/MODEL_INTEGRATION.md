# Live model integration: NVIDIA Nemotron via Nebius Token Factory

**Status: implemented to spec, not yet verified against a real account.**
This document exists so nobody mistakes "the code is written" for "the
integration has been tested." As of this document's last edit, the
development session that wrote `app/providers/nebius.py` had no
`NEBIUS_API_KEY` available, so `scripts/model_smoke_test.py` has not been
run successfully. Everything below that reads like a confirmed fact about
Nebius/Nemotron behavior is instead a statement of what the code assumes
from Nebius's public documentation — treat it as unverified until someone
runs the smoke test with real credentials and this document is updated
with actual output.

## What is implemented

- `app/providers/base.py` — the `Provider` interface (`generate(role,
  system_prompt, input_payload, output_model, prompt_version)`) that both
  `MockProvider` and `NebiusProvider` implement identically.
- `app/providers/nebius.py` — `NebiusProvider`, built against the
  documented OpenAI-compatible Chat Completions shape:
  - Base URL: `https://api.tokenfactory.nebius.com/v1/`
  - Auth: `NEBIUS_API_KEY` (server-side environment variable only — never
    sent to the browser, never logged, never written to a report).
  - Model: `NEBIUS_MODEL`, an exact ID that must be copied from whatever
    the Nebius model catalog shows for the account in use at the time —
    no ID is hardcoded or assumed here.
  - Structured output: the request currently asks for JSON via the
    system/user prompt plus the target Pydantic model's JSON schema
    embedded in the user message, and validates strictly on the client
    side with `output_model.model_validate_json(...)`. This is the
    `json_object`-style fallback from plan 2.2 ("If only json_object is
    supported, include the full schema in the prompt and retain strict
    local validation"). **Not verified:** whether the specific Nemotron
    model available to a real account also supports a stricter
    `json_schema` response-format mode, which would be preferable once
    confirmed.
  - Retry policy: at most two attempts per logical call. 401/403 never
    retries. 429/5xx/timeout retries once with small bounded backoff.
    Invalid JSON/empty content/truncated output each retry once. Attempts
    exhausted → raises `ModelOutputError` with a sanitized category
    (`auth_error`, `timeout`, `transient_error`, `invalid_schema`,
    `empty_output`, `truncated`, `provider_error`) — never the raw
    exception message, which could carry response bodies or headers.
- `app/council/` — the four-pass council (Planner, Red-team, Privacy,
  Arbiter) and `app/counterfactuals/` — the five controlled perturbations,
  both provider-agnostic: they call whatever `Provider` they're given.
  Swapping `MockProvider` for `NebiusProvider` is the only change needed
  to go from mock to live.
- `app/services/live_runner.py` — the async job queue or 202 + polling
  wrapper described in plan 2.6, with a per-run request budget, a shared
  daily call cap (in-memory, resets on restart — see the caveat in
  `app/providers/budget.py`), a whole-run deadline, and startup recovery
  that marks any run stuck in `evaluating` across a restart as `failed`
  rather than silently resuming it.

## What has NOT been verified

- That `NEBIUS_MODEL` values referenced anywhere are actually available to
  a real account — none is hardcoded; the operator must supply one that
  exists in their current catalog.
- Actual latency, token usage, or success rate against a live model.
- Whether the model reliably returns valid JSON on the first attempt, or
  needs the corrective retry in practice.
- Whether Nebius's endpoint behaves exactly like OpenAI's Chat Completions
  API for every parameter used here (`temperature=0`, `max_tokens`,
  `response_format` is not currently sent — see above).
- Any real injection-resistance or counterfactual-stability result. The
  automated test suite (`tests/test_council.py`,
  `tests/test_counterfactuals.py`, `tests/test_provider_validation.py`,
  `tests/test_live_failure_states.py`) exercises this entire pipeline
  end-to-end using `MockProvider` and fake/mocked HTTP clients — real
  logic, zero paid inference — but that is a test of the *code*, not of
  NVIDIA Nemotron's *behavior*.

## How to actually verify it

1. Get a Nebius Token Factory account with Nemotron access and note the
   exact model ID from the current catalog.
2. `export NEBIUS_API_KEY=... NEBIUS_MODEL=...` (never commit these).
3. `cd apps/api && source .venv/bin/activate`
4. `python ../../scripts/model_smoke_test.py` — this sends one Planner
   call with the retention-v1 fixture and validates the response locally.
   It prints the model ID, attempt count, duration, token usage, and
   whether any file ID was invented. It does not write to the runtime
   database.
5. Only after that passes twice in a row (plan 2.2 acceptance: "Two
   consecutive small live smoke tests return locally valid output") should
   `MODEL_MODE=live` be considered demoable, and this document should be
   updated with the actual model ID, response-format mode that worked, and
   real latency/usage numbers observed — replacing this section, not
   appended blindly next to unverified claims.
6. Run the five counterfactual perturbations live (drive
   `POST /api/v1/evaluations` with `mode=live` and the seeded task, then
   inspect `extensions.counterfactual_summary` in the resulting report) and
   record the actual stability/injection numbers with their sample size,
   per plan 2.7's manual checklist.

## Known simplifications, stated rather than hidden

- The daily model-call cap (`DAILY_MODEL_CALL_CAP`) is an in-memory
  counter local to one process; it is not a durable, cross-restart rate
  limiter.
- The per-run request budget counts logical `provider.generate()` calls,
  not raw HTTP attempts (a provider's internal retry is still one logical
  call).
- Only one live run is processed at a time in this backend instance
  (`LIVE_RUN_CONCURRENCY`), enforced by counting rows with
  `status="evaluating"`, not a distributed lock.
