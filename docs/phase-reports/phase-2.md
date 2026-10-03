# Phase 2 report: monolithic baseline, shared runtime and evaluation runner

Date: 2026-10-03. Last code commit: `55b31dc`. This report is a docs-only commit on top of it.

**All evidence in this report is scripted.** Tests drive the system with `models/scripted.py` and make no network calls. No live model has been called, because no endpoint or model is configured (section 6). No live gate is marked passed.

## 1. Scope delivered

- **Model client.**
  - `models/client.py`: the `ModelClient` protocol and typed errors.
  - `models/openai_compat.py`: OpenAI SDK pinned at 3.24.0. It reads `MODEL_BASE_URL`, `MODEL_API_KEY` and `MODEL_ID` from the environment and supports `json_schema` or `json_object` structured output. Timeouts, connection errors, 429 and 5xx get bounded retries with backoff; other 4xx errors are not retried. Error text never contains the key.
  - `models/scripted.py`: the scripted client used by every offline test.
  - `.env.example` holds placeholders only, and `.env` is git-ignored.
- **Shared runtime** (`runtime/`, `trace/`).
  - The executor is the only component that runs packet tools. It validates arguments against the registry and requires clinic and package IDs to come from a tool result this turn. It runs each distinct write at most once and `updateWorkingMemory` at most once, caps calls at 8, and refuses every call after `close()`.
  - Every request, accepted or rejected, is recorded as an `Observation`.
  - `outcome.py` has a single-assignment terminal-outcome slot: answered or escalated, with the stage and executed writes.
  - `evidence.py`, `grounding.py` and `validate.py` check that every amount and URL in a reply came from this turn's tool results, plus URL placement, card-number echoes and the escalation sentence and reason. They also build repair instructions.
  - `payment_data.py` redacts Luhn-valid card numbers before the model sees the message and in traces.
  - `finalize.py` is pure: it takes the outcome and memory and returns the `Reply`. Escalated replies get the A-18 fields; answered replies keep only the memory keys that changed.
- **Baseline, S0** (`baseline/monolithic.py`, decision record 0003).
  - It uses the verbatim legacy prompt, a contract appendix and all 14 tools, with up to 3 tool rounds.
  - Invalid JSON gets one repair; a failed validation gets one repair. A second failure of either escalates (stage `controller_failure` or `validation`).
  - A model-chosen escalation closes the executor, so no further tools run.
- **Pipeline and CLI.**
  - `runtime/pipeline.py` runs each item in isolation (own context, executor and outcome slot) with optional concurrency, and returns results in input order.
  - `doctours-reply run` writes the output file atomically, with traces in a separate directory.
  - Exit codes: 0 success, 2 invalid input or reference, 3 configuration, 4 model failure. On any failure nothing is written to the output.
- **Evaluation** (`evaluation/`, `doctours-reply eval`).
  - Suites load with hash checks for frozen sets. A per-case scorer covers escalation, tool selection, required and forbidden facts, URLs, memory and cost.
  - Reports go to `report.json`, `cases.jsonl` and `summary.md`, with Wilson 95% intervals.
  - Official-message checks follow the packet's grading note (L759). An optional judge must be a different model from the one under test.
  - `--dry-run` validates every label against the fixture without any model call.
  - Held-out runs require `--log-entry`: the entry is appended to `eval/results/heldout-log.md` before the run, and each schedule row allows one current entry.
- **Evaluation data.**

  | Suite | File | Cases |
  |---|---|---|
  | Official labels | `eval/official/labels.jsonl` | 5 |
  | Development | `eval/dev/v0.jsonl` | 100 |
  | Adversarial | `eval/adversarial/v0.jsonl` | 41 |
  | RC-E regression | `eval/regression/rc_e.jsonl` | 19 |
  | Held-out v1, frozen in commit `0039292` | `eval/heldout/v1.jsonl` | 98 |

  - The held-out sha256 is `667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464`.
  - The extractor now also writes the official messages and expected replies into `eval/official/`. The runtime never reads them.
- **CI and guidance.**
  - CI gains the step `uv run doctours-reply eval --dry-run --suite all` before the audit.
  - `AGENTS.md`, the `regression-eval` and `phase-gate` skills, `README.md` (initial run instructions), `docs/spec/traceability.md` and the ambiguity ledger are updated. A-02, A-04, A-05, A-08 and A-18 are marked accepted.

The five plan corrections are preserved:

- **Escalation after writes.** The escalated outcome records the writes already executed. The scorer reports `escalations_after_write`, and RC-W-4 and RC-W-9 test it.
- **Required memory-tool calls.** The baseline's model decides when to call `updateWorkingMemory`, as the packet does. The executor allows it once per item (RC-W-8), and the report measures `memory_tool_called_when_answered`.
- **Resources separated from evaluation answers.** The guards cover imports, paths, leakage, and texts shared across suites.
- **Grounded monetary claims.** Every amount must come from this turn's tool results. The one exception is the legacy prompt's stated $25 fee (`LEGACY_FACTS`, packet L1147). RC-G-1 to RC-G-13 cover this.
- **Fair model selection.** Decision record 0003 says S0 and later systems use the same model, endpoint, fixtures and validators. No model has been chosen yet.

## 2. Checks run

Run locally on 2026-10-03 at `55b31dc` with CPython 3.12.7.

| Check | Actual output | Result |
|---|---|---|
| `uv sync --locked` | `Resolved 28 packages`, `Checked 26 packages`, exit 0 | pass |
| `uv run ruff check .` | `All checks passed!` | pass |
| `uv run ruff format --check .` | `85 files already formatted` | pass |
| `uv run mypy src` | `Success: no issues found in 42 source files` | pass |
| `uv run pytest -m "not live"` | `501 passed, 2 deselected` (unit 196, conformance 222, guards 83) | pass |
| `uv run doctours-reply eval --dry-run --suite all` | `official: 5`, `dev: 100`, `adversarial: 41`, `regression: 19`, `heldout_v1: 98` cases, each `labels and references ok` | pass |
| `uv run python scripts/audit_submission.py --history` | `audit passed: 0 findings (tracked tree and full history)` | pass |
| `uv run python scripts/extract_packet.py --check` | no stale files, exit 0 | pass |
| `node --experimental-strip-types scripts/gen_tool_goldens.mjs --check` (Node v22.22.2) | `goldens unchanged: 170 cases (generated with node v22.22.2, checked with node v22.22.2)` | pass |
| `uv run pytest -m live -rs` (no `RUN_LIVE`) | `2 skipped`: `set RUN_LIVE=1 to run` | skipped, not passed |
| `doctours-reply run` and `eval --suite dev` with `MODEL_*` unset | `error: missing required environment variables: MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID`, exit 3 | pass (expected refusal) |
| `doctours-reply eval --suite heldout_v1` without `--log-entry` | `error: heldout_v1 runs only through the schedule; pass --log-entry`, exit 2 | pass (expected refusal) |

Scripted coverage of the requested verification items (all in `tests/unit/` unless noted):

- **Tool dependencies and failures.**
  - `test_executor.py`: IDs must come from a tool result this turn; patient IDs must be the trusted constants; arguments are validated against the registry. A seen but wrong ID yields a null result (RC-W-7), and a failing tool becomes an error observation.
  - `test_baseline.py`: tool rejections are shown to the model.
- **Write deduplication.** A repeated write executes once (RC-W-6). A write followed by two failed drafts keeps its record (RC-W-5).
- **Escalation stops further tools.** A model escalation after a write closes the executor, refuses later calls and records the write (RC-W-4). No tool runs after `close()`.
- **Memory.**
  - The baseline's memory call runs once (RC-W-8).
  - Answered replies keep only changed keys, and an all-unchanged diff becomes null.
  - Escalated replies carry A-18's `escalationFlags`.
  - Scorer memory labels are covered in `test_evaluation.py`.
- **Grounding failures and repair.** RC-G-1 to RC-G-13 in `test_grounding.py`. Policy amounts need their fact, and a changed fixture changes the verdict with no code change (RC-G-10). One repair is allowed, and a second failure escalates at `validation` (RC-G-11).
- **Redaction.** Luhn-valid card numbers of 13 to 19 digits and card fragments are redacted; non-card numbers are kept. Card digits never reach the model request, trace or reply (RC-E-8). Traces never contain the API key (`test_cli.py`).
- **Input and output ordering.** Replies follow input order under concurrency 4, with random per-item delays.
- **Per-item isolation.** Items share no state, and permuting the input gives the same per-item replies.
- **Malformed model responses.**
  - Invalid JSON gets one repair; a second failure escalates at `controller_failure`.
  - An invalid escalation sentence or reason falls back to the templates.
  - Tool rounds are bounded.
- **Provider outages.**
  - 429, 503, timeouts and connection errors are retried with bounded backoff, and exhaustion raises an error that contains no secrets. 400 and 401 are not retried.
  - An outage after a write stops the batch and keeps the trace with the write (RC-W-9).
  - The CLI exits 4 and leaves the previous output untouched.
- **Held-out schedule.** RC-V-1 to RC-V-4 in `test_evaluation.py`: held-out suites need a log entry, a repeat run is refused and voided entries are kept, a comparison row needs its preregistration, and a results summary without a log entry is flagged. `tests/guards/test_heldout_log.py` checks the committed log, summaries and frozen hashes.
- **Offline end-to-end eval.** A scripted run over official plus regression with 2 runs scores 24 cases per run and writes 48 case lines. This tests the runner's plumbing only; it measures nothing about a model.

## 3. Checks not run, and why

The model configuration is missing (`MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_ID` are unset), so none of these live gates have been run or passed:

| Gate | Command |
|---|---|
| Live smoke | `RUN_LIVE=1 uv run pytest -m live` |
| Official five messages | `uv run doctours-reply eval --suite official --runs 3` |
| Iteration suites | `uv run doctours-reply eval --suite dev,adversarial,regression --runs 3` |
| Scheduled baseline measurement | `uv run doctours-reply eval --suite heldout_v1 --log-entry phase2-s0-baseline --runs 3` |
| Judge scoring | add `--judge` once `JUDGE_*` names a different model |

**Baseline measurements: none.** No live results exist, so there are no escalation, grounding, validity or cost numbers to report. The `phase2-s0-baseline` row has no log entry, because one is appended only when a configured run starts; the held-out set is still unused.

Also not run:

- **The default `node`** here is v20.19.5, which rejects `--experimental-strip-types`. The golden check was run with Homebrew `node@22` (v22.22.2).
- **Branch protection** is still not configured. The CI check on the head SHA is the gate.
- **The fresh-clone and CPU-only gates** belong to later phases.

## 4. CI

```text
$ gh run list --branch main --limit 1 --json headSha,conclusion   # run 37159954054
[{"conclusion":"success","headSha":"55b31dc5504b6b9840a1b4acd7d6f3fc8edef0b4"}]
$ git rev-parse HEAD   # before this report commit
55b31dc5504b6b9840a1b4acd7d6f3fc8edef0b4
```

All CI steps succeeded: Install, Lint, Types, Tests (network-free), Eval suites (dry run, no model calls), Audit tree and history. The CI result for this report commit is checked after it is pushed.

Commits in this phase, after `f70e26a`:

- `05d05c2`: model client.
- `add94ed`: runtime core.
- `3c4558b`: baseline, pipeline and CLI.
- `3c0698f`: evaluation runner.
- `0039292`: held-out v1 freeze.
- `c4de6d0`: iteration suites.
- `55b31dc`: CI and docs.

## 5. Deviations and decisions

- **Dependencies.** Only the approved `openai==3.24.0` was added. Its own requirements came with it: `anyio` 4.15.1, `h11` 0.16.0, `httpcore2` 2.13.1, `httpx2` 2.13.1, `httpx2-jsfetch` 1.0, `idna` 3.20, `jiter` 0.17.0, `sniffio` 1.3.1 and `truststore` 0.10.4, all locked in `uv.lock`.
- **Held-out v1 authorship.** A separate agent session wrote it from the assignment contract, the legacy prompt's rules, the fixture and the label schema. It could not read the other suites or the official messages.
  - It wrote 101 cases. Before freezing, and before any model saw them, 3 were removed:
    - `hv1-094`, which repeated dev's text `ok`;
    - `hv1-086` and `hv1-092`, which closely paraphrased `dev-062` and `dev-031`. `hv1-086` traces to an example phrase in the author's brief.
  - The remaining IDs keep their gaps.
  - `tests/guards/test_eval_sets.py` now fails if any text appears in two suites.
- **Escalation scoring.** The official-message checks follow L759 but do not count sentences for escalations, per A-03.
- **One current log entry per schedule row.** This is stricter than the plan. A rerun needs `--void-previous` with an infrastructure reason, and the voided row stays in the log.
- **Cost** is reported as calls, retries, tokens and p50/p95 latency. There are no dollar figures until a model and its prices are fixed.
- **Argument correctness is part of tool selection.** Expected tool multisets carry clinic and package arguments.
- **RC-G-10** builds its changed fixture in the test, a modified copy of the tool data, instead of shipping a second resource fixture.
- **The `eval` command's import exception** (left open in Phase 1). `cli.py` imports `evaluation.cli` lazily, only for `eval`. The import guard allows exactly that import, and a subprocess test shows `run` never loads an evaluation module.
- **Provider checks for the modular steps** (route, decide) move to Phase 3, where those steps exist.

## 6. Open questions and blockers

- **Blocker: model configuration.** It needs three variables:
  - `MODEL_BASE_URL`: an OpenAI-compatible endpoint with tool calls;
  - `MODEL_API_KEY`;
  - `MODEL_ID`: one fixed model, chosen under decision record 0003 and used for every system compared.
- **Optional for judge scores:** `JUDGE_BASE_URL`, `JUDGE_API_KEY` and `JUDGE_MODEL_ID`. The judge must be a different model.
- **Once configured,** the gates in section 3 run in the order listed, and the baseline measurement is recorded from them.
- **Follow-up: the private companion's remote.** It has none yet; the owner creates it as a private repository.
- **Open question: branch protection.** Should it require the CI check on `main`?
