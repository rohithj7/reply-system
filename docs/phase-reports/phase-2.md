# Phase 2 report: monolithic baseline, shared runtime and evaluation runner

Date: 2026-10-04. Last code commit: `3721b5e`. The held-out baseline ran on it, and this report update is a docs and results commit on top of it. Later closeout checks are in `phase-2-closeout.md`.

**Evidence comes in two kinds, labelled throughout.**

- **Scripted:** tests drive the system with `models/scripted.py` and make no network calls.
- **Live:** runs against `gpt-6-luna` at an OpenAI-compatible endpoint with `reasoning_effort=none` (section 2, live gates). The live smoke test was run by the owner. Every other live run was made by the agent with the commands shown.

## 1. Scope delivered

- **Model client.**
  - `models/client.py`: the `ModelClient` protocol and typed errors.
  - `models/openai_compat.py`: OpenAI SDK pinned at 3.24.0.
    - It reads `MODEL_BASE_URL`, `MODEL_API_KEY` and `MODEL_ID` from the environment, plus optional timeout, retries, structured-output mode (`json_schema` or `json_object`), temperature and `MODEL_REASONING_EFFORT`.
    - Temperature and reasoning effort are sent only when set.
    - Timeouts, connection errors, 429 and 5xx get bounded retries with backoff; other 4xx errors are not retried.
    - Error text never contains the key.
  - `models/scripted.py`: the scripted client used by every offline test.
  - `.env.example` holds placeholders only, and `.env` is git-ignored.
- **Shared runtime** (`runtime/`, `trace/`).
  - The executor is the only component that runs packet tools. It validates arguments against the registry and requires clinic and package IDs to come from a tool result this turn. It runs each distinct write at most once and `updateWorkingMemory` at most once, caps calls at 8, and refuses every call after `close()`.
  - Every request, accepted or rejected, is recorded as an `Observation`.
  - `outcome.py` has a single-assignment terminal-outcome slot: answered or escalated, with the stage and executed writes.
  - `evidence.py`, `grounding.py` and `validate.py` check that every amount and URL in a reply came from this turn's tool results, plus URL placement, card-number echoes and the escalation sentence and reason. They also build repair instructions.
    - Three forms are not claims: a negated patient amount ("not $3,500"), a package the patient named in a negated clause or a question, and a cued difference that equals price minus deposit or a gap between two packages ("$3,900 remains", "$200 cheaper").
  - `payment_data.py` redacts Luhn-valid card numbers before the model sees the message and in traces. UUIDs and hex digests are kept even when their digits pass Luhn.
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
  - Phase 3 later extended both v0 suites to v1 by appending cases. The v0 files this report used are `git show 95e9f77:eval/dev/v0.jsonl` (sha256 `3e30a19277a669d1c28bf57b574036aa83eb12a89b15a7081a0e85093ba0962b`) and `git show 94286bf:eval/adversarial/v0.jsonl` (sha256 `e49065de9150f362c87895945022ff15c0f7c342cb9dc77b42b3d66fe026ef6d`). They are also the first 100 and 41 lines of the v1 files.
  - The extractor now also writes the official messages and expected replies into `eval/official/`. The runtime never reads them.
- **CI and guidance.**
  - CI gains the step `uv run doctours-reply eval --dry-run --suite all` before the audit.
  - `AGENTS.md`, the `regression-eval` and `phase-gate` skills, `README.md` (initial run instructions), `docs/spec/traceability.md` and the ambiguity ledger are updated. A-02, A-04, A-05, A-08 and A-18 are marked accepted.

The five plan corrections are preserved:

- **Escalation after writes.** The escalated outcome records the writes already executed. The scorer reports `escalations_after_write`, and RC-W-4 and RC-W-9 test it.
- **Required memory-tool calls.** The baseline's model decides when to call `updateWorkingMemory`, as the packet does. The executor allows it once per item (RC-W-8), and the report measures `memory_tool_called_when_answered`.
- **Resources separated from evaluation answers.** The guards cover imports, paths, leakage, and texts shared across suites.
- **Grounded monetary claims.** Every amount must come from this turn's tool results. The one exception is the legacy prompt's stated $25 fee (`LEGACY_FACTS`, packet L1147). RC-G-1 to RC-G-13 cover this.
- **Fair model selection.** Decision record 0003 says S0 and later systems use the same model, endpoint, fixtures and validators. The model is `gpt-6-luna` with `reasoning_effort=none`, and each report records its config sha256.

## 2. Checks run

Run locally on 2026-10-03 at `55b31dc` with CPython 3.12.7. Each later code commit reran lint, format, types, tests, the dry run and the audit. At `3721b5e`:

- `pytest -m "not live"` gives `530 passed, 2 deselected`;
- `ruff format --check` reports `86 files already formatted`;
- the other checks give the same output as below.

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
| `uv run pytest -m live -rs` (no `RUN_LIVE`) | `2 skipped`: `set RUN_LIVE=1 to run` | skipped, as expected |
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
- **Redaction.** Luhn-valid card numbers of 13 to 19 digits and card fragments are redacted; non-card numbers are kept. Card digits never reach the model request, trace or reply (RC-E-8). Correction: until `490d09d`, a card number followed by a comma, a grouped card number followed by its expiry and code, and "Visa ending 1234" escaped redaction. Until `df46221`, so did the year and code after a one-digit expiry month that passed Luhn with the card number (`phase-3.md`, Card-redaction correction). Traces never contain the API key (`test_cli.py`).
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

### Live gates

Model `gpt-6-luna` with `reasoning_effort=none`, `json_schema` output and a 120 s timeout. Every eval ran with `--runs 3 --concurrency 2`, after `.env` was exported, with `MODEL_MAX_RETRIES=10` set for the run (section 5). Reports and traces are in the git-ignored `runs/`; only the held-out summary is committed.

| Gate | Command | Build | Actual output | Result |
|---|---|---|---|---|
| Live smoke | `RUN_LIVE=1 uv run pytest -m live` | `5cc958d` | `2 passed, 513 deselected in 20.46s` | pass, run by the owner |
| Official five | `eval --suite official` | `44a390d` | 15/15 valid, 15/15 escalation decisions correct | pass |
| Regression | `eval --suite regression` | `25bb735` | 57/57 valid, no controller failures | ran |
| Development | `eval --suite dev` | `25bb735` | 300/300 valid, no controller failures | ran |
| Adversarial | `eval --suite adversarial` | `25bb735`, rerun at `3721b5e` | 123/123 valid both times, no controller failures | ran |
| Held-out baseline | `eval --suite heldout_v1 --log-entry phase2-s0-baseline` | `3721b5e` | log entry #1; 294/294 valid, no controller failures | ran once, as scheduled |

The iteration suites and the held-out set have no pass threshold in Phase 2; they measure S0.

| Metric | Official | Regression | Dev | Adversarial (rerun) | Held-out |
|---|---|---|---|---|---|
| Valid after finalize | 15/15 | 57/57 | 300/300 | 123/123 | 294/294 |
| Escalation decision correct | 15/15 | 35/57 | 256/300 | 101/123 | 240/294 |
| Missed: unsupported action | 0/3 | 21/24 | 34/39 | 19/21 | 53/63 |
| Missed: human request | 0/3 | 0/6 | 1/12 | 3/15 | 1/18 |
| Unnecessary escalations | 0/9 | 1/27 | 9/249 | 0/87 | 0/213 |
| Validation-stage escalations | 0/15 | 3/57 | 10/300 | 2/123 | 1/294 |
| Grounded on first draft | 8/9 | 43/47 | 254/275 | 95/106 | 257/267 |
| Tool selection | 11/15 | 20/51 | 73/174 | 37/87 | 167/294 |
| Required facts | 14/21 | 3/9 | 58/72 | 17/21 | 56/78 |
| Forbidden-fact replies | 0/15 | 0/57 | 0/300 | 0/123 | 6/294 |
| Memory tool called when answering | 9/9 | 46/47 | 264/275 | 101/109 | 253/267 |
| Model calls per item | 2.73 | 3.21 | 3.11 | 2.96 | 3.15 |
| Prompt tokens per item | 107k | 126k | 122k | 116k | 124k |
| Rate-limit retries | 0 | 2 | 330 | 49 | 219 |

What the numbers say:

- **The baseline's main weakness is unsupported actions.** It usually declines them with the legacy prompt's scripts instead of escalating as ledger A-02 requires: 53 of 63 were missed on the held-out set. Missed human requests are rare, and with the fixed validator there are no unnecessary escalations.
- **Format and contract are not the problem.** Every reply is valid after finalizing. Only one adversarial item per run needed a repair before its output was valid.
- **Validator false positives, fixed before the held-out run** (`3721b5e`).
  - At `25bb735`, all 21 unnecessary escalations in dev and adversarial were validator false positives:
    - negated or questioned package names ("I don't see a Sapphire package");
    - corrections of patient amounts ("not $3,500", "I can't confirm $999");
    - derived amounts ("$3,900 remains", "$200 cheaper");
    - "Heva Clinic package" being read as a package named Clinic.
  - Replaying every rejected draft from the three iteration suites through the fixed validator removes 55 rejections and adds none. A false Sapphire claim made alongside an honest sentence is still rejected.
  - The live adversarial rerun took unnecessary escalations from 12/87 to 0/87, and correct escalation decisions from 88/123 to 101/123.
  - Dev and regression were not rerun on `3721b5e`; their columns are from `25bb735`.
- **The held-out forbidden-fact hits.**
  - `hv1-017` (3 hits): a request that should have escalated was answered with the Silver deposit.
  - `hv1-097` and `hv1-034` (3 hits between them): the reply named Gold with correct facts, which those labels forbid.
- **Required URLs are often left out.** On the official set, the baseline answered both link-bearing messages correctly but left out the consultation and assessment links (0/6).
- **Cost.** About 39k prompt tokens per call and 3.1 calls per item. The phase used about 118M prompt tokens and 311k completion tokens. That includes 4.8M in an aborted concurrency-4 attempt (section 5).

## 3. Checks not run, and why

- **Judge scoring.** No `JUDGE_*` model is configured, so reply quality has not been judged; only the label-based scores above exist.
- **Dev, regression and official reruns on `3721b5e`.** These were not repeated after the validator fix, to save about 46M tokens; the adversarial rerun and the offline replay cover the change. Official was last run at `44a390d`.
- **The default `node`** here is v20.19.5, which rejects `--experimental-strip-types`. The golden check was run with Homebrew `node@22` (v22.22.2).
- **Branch protection** is still not configured. The CI check on the head SHA is the gate.
- **The fresh-clone and CPU-only gates** belong to later phases.

## 4. CI

```text
$ gh run list --branch main --limit 1 --json headSha,conclusion   # run 37170871245
[{"conclusion":"success","headSha":"3721b5e848406747eb9507e8482dacb03a031997"}]
$ git rev-parse HEAD   # before this report update
3721b5e848406747eb9507e8482dacb03a031997
```

Every earlier commit in the phase also passed:

- run 37159954054 on `55b31dc`;
- run 37160132778 on `ac66de2`;
- run 37160378771 on `828d0ad`;
- run 37160419705 on `fca2078`;
- run 37167900704 on `5cc958d`;
- run 37168364819 on `44a390d`;
- run 37168525351 on `25bb735`.

All CI steps succeeded: Install, Lint, Types, Tests (network-free), Eval suites (dry run, no model calls), Audit tree and history. The CI result for this report commit is checked after it is pushed.

Commits in this phase, after `f70e26a`:

- `05d05c2`: model client.
- `add94ed`: runtime core.
- `3c4558b`: baseline, pipeline and CLI.
- `3c0698f`: evaluation runner.
- `0039292`: held-out v1 freeze.
- `c4de6d0`: iteration suites.
- `55b31dc`: CI and docs.
- `ac66de2`: this report.
- `828d0ad`: the scorer fix.
- `fca2078`: report update for the scorer fix.
- `5cc958d`: `MODEL_REASONING_EFFORT`.
- `44a390d` and `25bb735`: card redaction keeps UUIDs and hex digests.
- `3721b5e`: grounding non-claims.
- The held-out log entry, results summary and this update follow as a docs and results commit.

## 5. Deviations and decisions

- **Dependencies.** Only the approved `openai==3.24.0` was added. Its own requirements came with it: `anyio` 4.15.1, `h11` 0.16.0, `httpcore2` 2.13.1, `httpx2` 2.13.1, `httpx2-jsfetch` 1.0, `idna` 3.20, `jiter` 0.17.0, `sniffio` 1.3.1 and `truststore` 0.10.4, all locked in `uv.lock`.
- **Held-out v1 authorship.** A separate agent session wrote it from the assignment contract, the legacy prompt's rules, the fixture and the label schema. It could not read the other suites or the official messages.
  - It wrote 101 cases. Before freezing, and before any model saw them, 3 were removed:
    - `hv1-094`, which repeated dev's text `ok`;
    - `hv1-086` and `hv1-092`, which closely paraphrased `dev-062` and `dev-031`. `hv1-086` traces to an example phrase in the author's brief.
  - The remaining IDs keep their gaps.
  - `tests/guards/test_eval_sets.py` now fails if any text appears in two suites.
- **Escalation scoring.** The official-message checks follow L759 but do not count sentences for escalations, per A-03.
- **One current log entry per schedule row.** This is stricter than one entry per run. A rerun needs `--void-previous` with an infrastructure reason, and the voided row stays in the log.
- **Cost** is reported as calls, retries, tokens and p50/p95 latency. There are no dollar figures, because provider prices are not part of the repo.
- **Argument correctness is part of tool selection.** Expected tool multisets carry clinic and package arguments.
- **RC-G-10** builds its changed fixture in the test, a modified copy of the tool data, instead of shipping a second resource fixture.
- **The `eval` command's import exception** (left open in Phase 1). `cli.py` imports `evaluation.cli` lazily, only for `eval`. The import guard allows exactly that import, and a subprocess test shows `run` never loads an evaluation module.
- **Scorer fix after review of the held-out labels** (`828d0ad`).
  - String facts used to match as substrings, so "3 night" counted in "13 nights" and "Wed" in "allowed". They now match whole words, with a plural allowed.
  - `bookableWeekdays` facts accept a day's name or abbreviation, or a stated range such as "Monday through Friday".
  - `check_case` now verifies weekday labels against the fixture, and all three held-out weekday labels pass.
  - The frozen set and its hash are unchanged, and the fix came before any held-out run.
- **Provider checks for the modular steps** (route, decide) move to Phase 3, where those steps exist.
- **`MODEL_REASONING_EFFORT`** (`5cc958d`). The model needs `reasoning_effort="none"` for tool calls through Chat Completions. The client validates the value against the SDK's allowed values, sends it only when set, and records it in each report's config.
- **Card redaction kept identifiers whole** (`44a390d`, `25bb735`). The first live official run showed the Heva clinic UUID and a package UUID rewritten as card numbers in traces; a request digest followed. Their digit runs pass Luhn.
  - UUIDs and 32+ character hex strings are now left alone, and card numbers are still redacted.
  - Scores were unaffected, since the scorer reads the in-memory result. Official was rerun at `44a390d`.
- **Rate limits.** Each call sends about 39k prompt tokens against a 2M tokens-per-minute limit.
  - The first iteration attempt, at concurrency 4 with 3 retries, exhausted its retries on 429 responses and stopped with exit 4. Nothing was scored, and its 4.8M prompt tokens are counted in the total.
  - All later runs used concurrency 2 and `MODEL_MAX_RETRIES=10`, set for the run rather than in `.env`. Every retry recovered.
- **The validator fix came from iteration evidence** (`3721b5e`; section 2, live gates). It was made from dev and adversarial drafts and tested on them, before the held-out run. The tests use those drafts, plus near misses that must still fail.
- **Held-out labels are left as frozen.** Three forbidden-fact hits come from labels that forbid naming Gold even when the facts are correct. Changing labels or the scorer after the run would make the measurement post hoc, so neither was changed.

## 6. Open questions and blockers

- **No blockers.** The model is configured and every Phase 2 live gate has run.
- **Optional for judge scores:** `JUDGE_BASE_URL`, `JUDGE_API_KEY` and `JUDGE_MODEL_ID`. The judge must be a different model from `gpt-6-luna`.
- **For review: unsupported actions.** The legacy prompt's decline scripts conflict with ledger A-02's escalation rule. That conflict is the largest S0 gap (53/63 missed on held-out). The modular system targets it in Phase 3.
- **For review: the strict Gold labels** in `hv1-097` and `hv1-034`. They stay as frozen for v1. Any held-out v2 could allow other packages when their facts are correct.
- **Follow-up: the private companion's remote.** It has none yet; the owner creates it as a private repository.
- **Open question: branch protection.** Should it require the CI check on `main`?
