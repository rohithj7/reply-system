# doctours-take-home

A reply system for the packet in `docs/assignment/pre-deposit-respond-packet.md`. It reads a JSON array of `{id, text}` messages and writes one `Reply` per message, in the same order.

Status: Phase 3. There are two systems behind the same executor, validators and finalizer:
- S0, the monolithic baseline: the packet's legacy prompt and its 14 tools (`docs/decisions/0003-baseline-fairness.md`).
- S1, the modular system: a controller routes the message, loads only the policy modules it needs, plans tool calls, and hands the observations to a grounded writer (`docs/decisions/0002-modular-system.md`). Policies are versioned modules (`docs/decisions/0004-versioned-policies.md`).

This README covers running them; the design write-up comes later.

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/) 0.10 or later. A CPU-only machine is enough.
- An OpenAI-compatible chat endpoint that supports tool calls, and a fixed model ID.

## Install

```sh
uv sync --locked
```

## Configure

Set these in your shell, or copy `.env.example` to `.env` (git-ignored) and export it:

```sh
export MODEL_BASE_URL=https://your-endpoint.example/v1
export MODEL_API_KEY=...
export MODEL_ID=...
```

Optional settings: `MODEL_TIMEOUT_SECONDS` (default 60), `MODEL_MAX_RETRIES` (default 3; applies to timeouts, connection errors, 429 and 5xx) and `MODEL_STRUCTURED_OUTPUT` (`json_schema`, the default, or `json_object` for endpoints without JSON-schema support). `MODEL_TEMPERATURE` and `MODEL_REASONING_EFFORT` (`none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`) are unset by default and sent only when set; some reasoning models need `MODEL_REASONING_EFFORT=none` for tool calling. `CONTROLLER_MODEL_ID` and `WRITER_MODEL_ID` send the modular system's controller and writer calls to other models at the same endpoint; each defaults to `MODEL_ID`, and the baseline always uses `MODEL_ID`. These are the only settings the client reads; concurrency is the `--concurrency` flag.

## Run

```sh
uv run doctours-reply run --input messages.json --output replies.json
```

- `--system baseline` (the default) runs S0; `--system modular` runs S1.
- `--input -` reads stdin and `--output -` writes stdout. The output file is written atomically.
- `--concurrency N` (1-16) runs items in parallel. Every item is isolated, and the output keeps the input order.
- Traces go to `runs/<run id>/traces.jsonl`, or to `--trace-dir`, never to the output. Card numbers are redacted before the model call and in traces.
- Exit codes: 0 success; 2 invalid input or reference; 3 missing or invalid model configuration; 4 model failure. On any failure, nothing is written to the output.

## Evaluate

```sh
uv run doctours-reply eval --dry-run --suite all        # validate every case and label; no model calls
uv run doctours-reply eval --suite dev,adversarial,regression --runs 3
uv run doctours-reply eval --system baseline,modular --suite dev,adversarial --runs 3
```

Reports go to `runs/eval-<run id>/`: `report.json`, `cases.jsonl` and `summary.md`. They give Wilson 95% intervals over items and, with more than one run, 95% intervals from a case bootstrap, which treats a case's runs as one unit. With both systems, `modular_minus_baseline` gives the paired difference per metric, its case-level interval and an exact McNemar test on each case's majority outcome. The official five messages (`--suite official`) are a sanity check only. The held-out set runs only through its schedule row, for example `--suite heldout_v1 --log-entry phase2-s0-baseline --runs 3`, which first appends an entry to `eval/results/heldout-log.md`. Rows `phase2-s0-baseline` and `phase3-s0-vs-s1` have run; their results are in `eval/results/`. Held-out v2 (`heldout_v2`, rows `phase5-s0-s3` and `phase6-hosted-parity`) is guarded and frozen by hash the same way. Its cases and hash are not committed yet; until either is, `--suite all` skips it and `--suite heldout_v2` fails.

Each baseline model call sends about 39k prompt tokens, because the legacy prompt is long. Under a 2M tokens-per-minute limit, `--concurrency 2` with `MODEL_MAX_RETRIES=10` completed every run; `--concurrency 4` exhausted the default 3 retries on 429 responses. S1 sends about 17k prompt tokens per item over about 3 calls, and its development runs at `--concurrency 4` needed no rate-limit retries.

## Develop

`AGENTS.md` lists the checks CI runs. The test suite is network-free; `RUN_LIVE=1 uv run pytest -m live` runs the live checks against the configured endpoint. They are the smoke test and, in `tests/live/test_rc_live.py`, S1's policy-change, fact-change and escalation checks, each repeated `LIVE_RUNS` times (default 3).

A policy change is a module edit with a version bump, or an overlay in `resources/policy_sets/` (`.agents/skills/policy-change/SKILL.md`).
