# doctours-take-home

A reply system for the packet in `docs/assignment/pre-deposit-respond-packet.md`. It reads a JSON array of `{id, text}` messages and writes one `Reply` per message, in the same order.

Status: Phase 2. The command runs S0, the monolithic baseline: the packet's legacy prompt and its 14 tools, behind a shared executor, validators and finalizer (`docs/decisions/0003-baseline-fairness.md`). The modular system comes in a later phase. This README covers running it; the design write-up comes later.

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

Optional settings: `MODEL_TIMEOUT_SECONDS` (default 60), `MODEL_MAX_RETRIES` (default 3; applies to timeouts, connection errors, 429 and 5xx) and `MODEL_STRUCTURED_OUTPUT` (`json_schema`, the default, or `json_object` for endpoints without JSON-schema support). `MODEL_TEMPERATURE` and `MODEL_REASONING_EFFORT` (`none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`) are unset by default and sent only when set; some reasoning models need `MODEL_REASONING_EFFORT=none` for tool calling. These are the only settings the client reads; concurrency is the `--concurrency` flag.

## Run

```sh
uv run doctours-reply run --input messages.json --output replies.json
```

- `--input -` reads stdin and `--output -` writes stdout. The output file is written atomically.
- `--concurrency N` (1-16) runs items in parallel. Every item is isolated, and the output keeps the input order.
- Traces go to `runs/<run id>/traces.jsonl`, or to `--trace-dir`, never to the output. Card numbers are redacted before the model call and in traces.
- Exit codes: 0 success; 2 invalid input or reference; 3 missing or invalid model configuration; 4 model failure. On any failure, nothing is written to the output.

## Evaluate

```sh
uv run doctours-reply eval --dry-run --suite all        # validate every case and label; no model calls
uv run doctours-reply eval --suite dev,adversarial,regression --runs 3
```

Reports go to `runs/eval-<run id>/`: `report.json`, `cases.jsonl` and `summary.md`, with Wilson 95% intervals. The official five messages (`--suite official`) are a sanity check only. The held-out set runs only through its schedule row, for example `--suite heldout_v1 --log-entry phase2-s0-baseline --runs 3`, which first appends an entry to `eval/results/heldout-log.md`. That row has been run; its results are in `eval/results/phase2-s0-baseline.md`.

Each baseline model call sends about 39k prompt tokens, because the legacy prompt is long. Under a 2M tokens-per-minute limit, `--concurrency 2` with `MODEL_MAX_RETRIES=10` completed every run; `--concurrency 4` exhausted the default 3 retries on 429 responses.

## Develop

`AGENTS.md` lists the checks CI runs. The test suite is network-free; `RUN_LIVE=1 uv run pytest -m live` runs the live smoke test against the configured endpoint.
