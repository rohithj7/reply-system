# Phase 3 report: modular system, versioned policies and the S0-S1 comparison

Date: 2026-10-04. Last code commit: `bb7d8b2`. Docs commit `f8cacb7` and pre-registration commit `1e646b6` follow it. The scheduled held-out comparison ran at `1e646b6`. The Phase 2 closeout is in `phase-2-closeout.md`.

Sections 1 to 6 describe the build measured at `1e646b6`. Section 7 is the closeout, which changed behavior after that measurement; its final checked commit is `c6791a1`. The semantic-review packet is `phase-3-review-packet.md`.

**Evidence comes in two kinds, labelled throughout.**

- **Scripted:** tests drive the system with `models/scripted.py` and make no network calls.
- **Live:** runs against `gpt-6-luna` at an OpenAI-compatible endpoint, with `reasoning_effort=none`, `json_schema` output, provider default temperature, 120 s timeout and 10 retries. The agent made every live run with the commands shown.

## 1. Scope delivered

- **Versioned policies** (`src/doctours_reply/policies/`, decision record 0004).
  - There are 24 modules: 3 core, 7 context, 12 skill and 2 writer. Each has TOML front matter: id, semver version, layer, summary, packet `sources`, `activates_on`, `requires`, `allowed_tools`, and optionally `when`, `facts`, `static_links` and `forbidden_patterns`.
  - `runtime/policy_loader.py` validates the front matter strictly and closes `requires`. It checks that the mandatory core set is present, matches `when` against fixture constants, builds the tool allowlist and renders modules. It records each loaded module's id, version and sha256 in the trace.
  - Overlays in `resources/policy_sets/` are `lean-as-soft-interest`, `checkout-only-links` and `deposit-fee-change`. Each replaces one module at version 1.0.0 with 1.1.0, and is hashed in the manifest.
  - New fixtures `sapphire-price-change` (Sapphire at $3,400) and `promo-active` are hashed in `resources/fixtures/manifest.json`.
- **S1, the modular system** (`runtime/modular.py`, decision record 0002).
  - The flow is route, load, decide, execute and observe, write, validate, commit memory. It is bounded to one route call, one extra skill load, 3 execute rounds and the executor's 8 calls.
  - `controller.py` and `decision.py` hold the route and decide steps, their schema and semantic checks, and one retry each. A second invalid decision becomes `controller_failure`.
  - `controller_io.py` (v1) is the fixed serialization: a system message, plus STATE as JSON. Message, context and tool results appear only as data.
  - `writer.py` is the grounded writer, with no tool client, one JSON repair and one validation repair.
  - Escalation uses each code's template sentence from `runtime/escalation.py`. The controller's reason is kept when it passes the shared checks.
  - Schema snapshots: `schemas/route.schema.json`, `decide.schema.json` and `decide_final.schema.json`.
- **Shared runtime changes.**
  - The executor returns `tool_not_loaded` for a call outside the loaded allowlist, at no budget cost. `commit_memory` runs the memory diff once, after validation, outside the budget.
  - `model_calls.py` holds the request-and-trace code both systems use. S0's copy moved there unchanged.
  - The trace records the system, call purposes, controller decisions, loaded policies, the fact table and end-to-end latency.
  - Grounding changes are in section 5.
- **Evaluation.**
  - The scorer records escalation code, JSON repairs, `tool_not_loaded`, skill loads and end-to-end latency.
  - The report adds missed escalations by labelled class, escalation-code accuracy, `goal_coverage_proxy`, `goal_complete_proxy`, repairs, skill loads and latency p50 and p95.
  - `evaluation/stats.py` adds the case bootstrap (10,000 resamples, seed 7), the paired difference and the exact McNemar test. With both systems, the report adds `modular_minus_baseline`.
- **Evaluation data.**
  - `eval/adversarial/v1.jsonl` has 71 cases: v0's 41 plus 30 new. The new cases are 13 unsupported actions, 4 human requests, 4 mixed intents and 9 controls (supported payment links, policy questions, negated or quoted human mentions, card data).
  - A guard fails any open case whose token-set Jaccard similarity to a held-out case reaches 0.75. The highest is 0.667.
- **Tests.**
  - There are 638 offline tests, up from 564 at the Phase 2 closeout.
  - `test_modular.py` (30) covers the answered flow, RC-PL-1, RC-PL-4, RC-PL-5, RC-W-1 to RC-W-8, invalid escalation reasons and the rounds bound. It also checks that injected text is treated as STATE data, the policy fee change, and that the writer, validators and finalizer get no tool client.
  - `test_policy_loader.py` (24) covers the loader.
  - `tests/live/test_rc_live.py` has 27 live checks: RC-PL-2, RC-PL-3, the fact change, the fee change and the 19 RC-E cases. Each runs 3 times.
- **Docs.** README, `AGENTS.md` layout, decision records 0002 and 0004, and the `phase3-s0-vs-s1` section of `eval/preregistration.md`.

## 2. Checks run

### Offline

Run locally with CPython 3.12.7 at `1e646b6`. The code is the same as at `bb7d8b2`.

| command | output | result |
|---|---|---|
| `uv sync --locked` | `Checked 26 packages` | pass |
| `uv run ruff check .` | `All checks passed!` | pass |
| `uv run ruff format --check .` | `130 files already formatted` | pass |
| `uv run mypy src` | `Success: no issues found in 49 source files` | pass |
| `uv run pytest -m "not live"` | `638 passed, 29 deselected` | pass |
| `uv run doctours-reply eval --dry-run --suite all` | official 5, dev 100, adversarial 71, regression 19, heldout_v1 98: `labels and references ok` | pass |
| `uv run python scripts/audit_submission.py --history` | `audit passed: 0 findings (tracked tree and full history)` | pass |
| `uv run python scripts/extract_packet.py --check` | exit 0, no output | pass |
| `node --experimental-strip-types scripts/gen_tool_goldens.mjs --check` (Node v22.22.2) | `goldens unchanged: 170 cases (generated with node v22.22.2, checked with node v22.22.2)` | pass |

**Differential replay of the grounding change** (`7b6cf58`). Every saved dev, adversarial, regression and official draft was checked by both the validator before the change and the one after, against the same evidence. The drafts come from the Phase 2 S0 runs in `runs/` and S1 iterations 1 to 3. Held-out runs were excluded.
- The result: `drafts 1047 changed 4`.
- dev-005, twice: still rejected, now as `unverified_calculation` with the right repair message, where before it was `wrong_value`.
- dev-045, twice: now accepted. Each clinic's own minimum is true for that clinic.
- No draft with a false claim was newly accepted. The replay script is a local analysis of the git-ignored `runs/` directory and is not committed.

### Live

**Official five on the final build** (`bb7d8b2`, S1, one run): `uv run doctours-reply eval --system modular --suite official --runs 1 --concurrency 5`.

| message | outcome | calls | prompt tokens (cached) | end-to-end |
|---|---|---|---|---|
| charge-card | escalated at route, `unsupported_payment_action` | 1 | 4,925 (3,122) | 1.9 s |
| demand-human | escalated at route, `human_requested` | 1 | 4,917 (3,122) | 1.3 s |
| consultation | free, booking link as the last line | 3 | 15,157 (9,354) | 4.2 s |
| hakan-price | Sapphire $3,200, $500 deposit | 4 | 23,220 (12,515) | 5.7 s |
| heva-packages | packages, prices and suitability right, but no deposits and no assessment link | 5 | 35,572 (15,676) | 8.8 s |

- All five replies were valid, with no infrastructure or contract failure.
- heva-packages is a quality failure: the router read "can I pay from the assessment?" as a policy question and did not load the assessment skill. The consultation reply omits that a phone call is offered. Neither was tuned against.

**Dev and adversarial iterations** (S1, 171 items, one run each, at concurrency 4). Each pass ran on the commit holding the previous pass's fixes.

| pass | commit | escalation correct | missed | unnecessary | code | goal coverage | grounded first try | controller retries / validation repairs | prompt (cached) per item | p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `1d960a4` | 167/171 | 1/50 | 3/121 | 46/49 | 30/43 | 114/118 | 8 / 4 | 16,177 (8,910) | 4.2 / 8.1 s |
| 2 | `a261ec3` | 168/171 | 0/50 | 3/121 | 48/50 | 40/43 | 110/117 | 10 / 7 | 16,448 (9,256) | 5.1 / 10.2 s |
| 3 | `0cd27b7` | 168/171 | 0/50 | 3/121 | 49/50 | 39/43 | 114/117 | 10 / 5 | 16,779 (9,426) | 5.4 / 10.1 s |
| 4 | `7b6cf58` | 171/171 | 0/50 | 0/121 | 49/50 | 40/43 | 114/120 | 19 / 6 | 16,957 (9,711) | 5.0 / 9.0 s |
| 5 | `fe3e8de` | 170/171 | 0/50 | 1/121 | 49/50 | 40/43 | 113/119 | 7 / 6 | 16,908 (11,509) | 4.5 / 8.4 s |
| 6 | `bb7d8b2` | 170/171 | 0/50 | 1/121 | 49/50 | 39/43 | 117/119 | 1 / 3 | 16,502 (9,541) | 4.3 / 8.6 s |

- Pass 3: dev-005 and dev-045 escalated as validator false failures, fixed in `7b6cf58`. dev-056 ("the link for" a clinic) was routed as an unsupported action; `core.escalation` 1.3.0 lists a clinic page link as tool-supported.
- Pass 4's 19 controller retries, across 16 items:
  - 8 gave one call id to both clinics' package calls in a round. The semantic check already rejected duplicate ids; `fe3e8de` adds "Unique among this decision's calls." to the id in the decide schema.
  - 7 asked to load a policy that was already loaded, or none at all.
  - 2 picked the context module `promo.none` as a skill at route.
  - 2 (adv-025) used call ids longer than the schema's 32 characters.
- Pass 5: adv-003 made the same already-loaded request twice and ended as `controller_failure`. The controller template now says loaded policies are not skills to load (`bb7d8b2`). Pass 6 had 1 retry and no controller failure.
- Pass 6's one unnecessary escalation is dev-005, a validator false failure (section 6). adv-053 (airport pickup) is coded `unsupported_booking_change`, against the label `unsupported_other`, in every pass.

**Live RC checks**: `RUN_LIVE=1 uv run pytest -m live tests/live/test_rc_live.py -s -rA`, 3 runs per case.

| check | at `fe3e8de` | at `bb7d8b2` (final) |
|---|---|---|
| RC-PL-2 shipped: a lean saves `selectedClinicId` | 3/3 | 3/3 |
| RC-PL-2 `lean-as-soft-interest`: a lean saves `softClinicInterestIds` only | **2/3 (fail)** | 3/3 |
| RC-PL-3 shipped: Sapphire payment link as the last line, never checkout | 3/3 | 3/3 |
| RC-PL-3 `checkout-only-links`: Dr. Hakan checkout link, never payment | 3/3 | 3/3 |
| fact change: packet $3,200; `sapphire-price-change` $3,400 | 3/3 and 3/3 | 3/3 and 3/3 |
| policy fee change: shipped $25; `deposit-fee-change` $40 | 3/3 and 3/3 | 3/3 and 3/3 |
| RC-E-1 to RC-E-19 (escalate cases need 3/3, controls 2/3) | 19 of 19 at 3/3 | 19 of 19 at 3/3 |
| pytest | `1 failed, 26 passed` | `27 passed` |

- The `fe3e8de` failure saved nothing in one run, and the live test kept no trace of it. Six further runs of the same input, with traces, all saved `softClinicInterestIds` only.
- The test now prints a failing run's tool calls and controller output. The `bb7d8b2` run is a run of the final build, not a retry of the failed one; both are reported.

**Live smoke** at `1e646b6`: `RUN_LIVE=1 uv run pytest -m live tests/live/test_live_smoke.py`, `2 passed`.

**Scheduled held-out comparison** (log entry #2): `uv run doctours-reply eval --system baseline,modular --suite heldout_v1 --runs 3 --log-entry phase3-s0-vs-s1 --concurrency 2`, at `1e646b6`, run `20261004T123143Z-817eba`. Full results and reading notes are in `eval/results/phase3-s0-vs-s1.md`. The unit of analysis is the 98 unique cases, with 3 runs each, and the intervals are case bootstraps.

| pre-registered target | S0 | S1 | S1 minus S0 [95% CI by case] | result |
|---|---|---|---|---|
| missed escalations, at most S0 | 51/81 | 0/81 | -0.630 [-0.790, -0.457]; 17 vs 0 discordant cases | pass |
| goal coverage proxy, at least S0 minus 3 points | 0.811 | 0.789 | -0.022 [-0.111, 0.049] | pass on the point estimate only |
| unnecessary escalations, at most 5% | 4/213 | 3/213 | -0.005 [-0.042, 0.024] | pass |
| prompt tokens per item, below S0 | 122,137 | 17,651 | -85.5% | pass |

Other measurements:

| measure | S0 | S1 |
|---|---|---|
| escalation correct | 239/294 | 291/294 (+0.177 [0.102, 0.259]; 18 vs 0 discordant cases) |
| missed human requests | 0/18 | 0/18 |
| missed unsupported actions | 51/63 | 0/63 |
| escalation code correct | n/a (constant code) | 78/81 |
| tool selection | 0.602 | 0.792 (+0.190 [0.105, 0.279], p = 0.0023) |
| required facts / URLs | 65/78, 8/12 | 63/78, 8/12 |
| forbidden fact / URL items | 4 / 0 | 0 / 2 |
| grounded first try | 251/260 | 201/210 |
| model calls per item | 3.11 | 3.09 |
| JSON repairs or controller retries / validation repairs | 0 / 13 | 3 / 11 |
| end-to-end p50 / p95 | 6.96 / 11.42 s | 4.70 / 9.32 s |

- Missed escalations by class: S0 missed all 15 unsupported payment actions, 9 date holds, 9 document actions and 6 booking changes, plus 6 of 9 clinic contacts, 3 of 6 other and 3 of 9 money movements. S1 missed none in any class.
- The controls show no unnecessary escalation by majority in any class, for either system.

### Usage and cost

Tokens come from the traces. Prices are list prices: $0.10/M input, $0.01/M cached input and $0.50/M output. The upper bound bills all uncached input as cache writes at $0.125/M (`phase-2-closeout.md`). These are not invoice amounts; failed HTTP attempts return no usage and are not counted.

| run | items | calls | prompt (cached) | completion | rate-limit retries | estimate (upper bound) |
|---|---|---|---|---|---|---|
| held-out, S0 | 294 | 914 | 35,908,329 (35,569,175) | 101,188 | 154 | $0.440 ($0.449) |
| held-out, S1 | 294 | 909 | 5,189,283 (3,351,302) | 63,769 | 0 | $0.249 ($0.295) |
| dev and adversarial passes 1 to 6, S1 | 1,026 | 3,076 | 17,060,953 (9,978,476) | 204,128 | 0 | $0.910 ($1.087) |
| official five, three S1 runs | 15 | 48 | 276,118 (141,924) | 3,977 | 0 | $0.017 ($0.020) |

- S0's legacy prompt is a fixed prefix, so 99.1% of its prompt tokens were cached; S1's step state varies, so 64.6% were. S1 sends 86% fewer prompt tokens but about 5 times more uncached ones per item: 6,252 against 1,154. It costs about 43% less at list price.
- The live RC checks (two runs of 81 items), the RC-PL-2 diagnostic (6 items) and the smoke tests keep no traces. At S1's held-out average of $0.00085 per item, the RC checks and diagnostic come to about $0.14.
- Model and configuration for every run: `gpt-6-luna` at `api.openai.com`, `reasoning_effort=none`, `json_schema`, no temperature sent, 120 s timeout and 10 retries. The held-out config sha256 is `14131c9416df40312b23e3a14ebfcea55de5fedeee9b1bb9c53b81d1364e94b7`.

### Unverified semantic metrics

There was no independent judge or human review, so these are unverified:
- whether a reply answers what was asked, beyond required facts and URLs;
- policy correctness beyond labelled facts, forbidden facts and escalation;
- tone, length and SMS style;
- whether an escalation reason is apt;
- whether a clarifying question was needed.

`goal_coverage_proxy` and `goal_complete_proxy` count labelled facts and URLs only.

## 3. Checks not run, and why

- **A judge or human review** was not run, because no independent judge model or reviewer was configured. The semantic metrics above stay unverified.
- **S0 on adversarial v1** was not run. The pre-registered S0-S1 comparison is the held-out row, and dev and adversarial were for S1 iteration only.
- **The live RC checks at `fe3e8de` were not repeated.** The 2/3 result stands for that build.
- **Held-out v1 was not run outside row `phase3-s0-vs-s1`.** No held-out message or reply was read; the reading notes use aggregates, case IDs and violation codes.
- **Phase 4, data generation, training and hosting** have not started.

## 4. CI

`gh run list --branch main --limit 1 --json headSha,conclusion` at the held-out run commit returned `[{"conclusion":"success","headSha":"1e646b6f6b1b23b026cc586e7d95ac742cb30c2e"}]`, and `git rev-parse HEAD` returned `1e646b6f6b1b23b026cc586e7d95ac742cb30c2e`. CI also passed on every Phase 3 code commit: `c34664d`, `05fcf1b`, `94286bf`, `1d960a4`, `a261ec3`, `0cd27b7`, `7b6cf58`, `fe3e8de` and `bb7d8b2`.

This report and the held-out results were committed on top of `1e646b6` as `533d947`, docs and results only. There, the same command returned `[{"conclusion":"success","headSha":"533d947ce96bfe70668e016515b9894b41fd256a"}]`, matching `git rev-parse HEAD`.

## 5. Deviations and decisions

- **Escalation wording comes from templates; there is no escalation-writer call.** Every escalation code has a fixed handoff sentence. This removes a model call and an unvalidated sentence from every escalation, at the cost of less tailored wording.
- **Calls run in the order the controller lists them; there is no `depends_on`.** A call that needs an earlier result goes in a later round, and the executor's ID provenance check enforces this. On the official heva-packages message, a same-round save was rejected, then succeeded in round 2.
- **Some policy edits were informed by the official messages.**
  - The consultation link as the last line, and the assessment link when the patient is about to pay from it, were written after the first live S1 smoke run on the official five.
  - Both rest on packet text (L759, L994) and on ledger entries A-04 and A-06, not on expected-reply wording. The leakage guard passes.
  - The official five are a sanity check, not a measure.
- **Shared validator changes**, which apply to S0 and S1 alike (commit `7b6cf58`):
  - "cheaper by $X" counts as a calculation cue, so the amount must equal a real gap.
  - A "starts at" amount is checked against the clinic named in its own clause, so "Heva's start at $3,000, and Dr. Hakan's start at $3,200" passes.
  - The differential replay in section 2 showed no draft newly accepted with a false claim.
  - The Phase 2 S0 record stays attributed to `3721b5e` and its validators.
- **S1 checks one thing S0 cannot.** A loaded policy's `forbidden_patterns` is checked against S1's draft (`check_policy_phrases`). S0 loads no policy modules, so this check never applies to it. Every other validator is shared.
- **A scorer change.** A string fact such as "4 night" now matches "4 hotel nights", allowing one word in between. This applies to both systems in the Phase 3 run; the Phase 2 record is unchanged.
- **Adversarial v0 became v1** by appending 30 cases, with the first 41 kept verbatim. adv-054 originally conflicted with dev-086's label and was rewritten ("Order me the post-op shampoo...", `unsupported_other`) to agree with the Phase 2 labels.
- **Controller retries are counted as `json_repairs_total`.** A route or decide step that fails its checks is retried once with the problems listed. The trace marks it `json_repair`, so this one count covers controller retries and writer JSON repairs together.
- **Iteration used development and adversarial cases only.** The live RC checks, the official smoke and six dev and adversarial passes were the only feedback. No held-out case, label or output was read before or after the scheduled run, apart from the aggregate report and the case IDs it lists.
- **Commit `fe3e8de` has an inaccurate message.** It says 19 of 171 items spent a controller retry on duplicate call ids. In fact, that pass had 19 retries across 16 items, and 8 of them were duplicate ids (section 2). The commit stays as pushed rather than rewriting history.

## 6. Open questions and blockers

- **Semantic quality is unverified.** No judge or human review was run, so goal coverage, policy correctness and tone are measured only through labelled proxies: required and forbidden facts and URLs, escalation, tool selection and memory labels. These cannot tell a relevant, complete answer from one that only contains the right facts. The closeout's `phase-3-review-packet.md` is prepared for that review and has not been reviewed.
- **Validator false failures remain.** The shared validator rejects some true drafts:
  - A package and a clinic named earlier in the same sentence count as a mismatch ("Sapphire at Dr. Hakan Clinic is $3,200, so Silver is $200 cheaper"). Fixed at the closeout in `72e8f5d`.
  - A calculated amount whose packages were named in the previous sentence is unverified, by design.
  - "X for Silver and Y for Gold" can credit Y to Silver. Still open at the closeout (section 7).
  - On dev and adversarial these cost a repair, and once (dev-005, iteration 6) an `unverified_reply` escalation. Loosening them needs new negative controls first.
- **Tool selection is a weak label.** `packages.pricing` tells S1 to fetch packages from every clinic when the patient names a package without its clinic, while most labels expect a single clinic. Tool selection therefore stays near 0.78 on dev and adversarial. It is not a target.
- **Routing misses remain.** On the final-build official smoke, S1 treated "can I pay from the assessment?" as a policy question and never fetched the assessment link. It was not tuned on the official five, because that would be special-casing. The closeout fixed the general failure from the packet's policies, tested on new dev cases (section 7, `0816652` and `fce1d04`).
- **Held-out v2.** Per the owner's decision, v2 labels will separate factual correctness from relevance and from policy compliance. Another package's name will be allowed only when the request and the policies justify it. The rubric will be frozen before v2 is evaluated. v1 labels and scores stay as they are; suspected defects are in `docs/spec/heldout-v1-errata.md`.
- **Branch protection is unavailable.** The repository is private on a free plan, and the protection and rulesets endpoints return 403. It stays private. Required checks, blocked force pushes and blocked deletion need a paid plan or a public repository.
- Not tagged `v0.3.0`. Phase 4, data generation, training and hosting have not started. The runtime imports no training code.

## 7. Closeout

Two closeout passes followed the held-out measurement. The first ended at `65f14e7`. The second fixed the failures that the first pass's live runs exposed, and ended at `c6791a1`. Neither changed the held-out set, its labels, its schedule row or its measurements, and held-out v1 was not rerun.

### Which commit each result belongs to

- **Measured:** the held-out row `phase3-s0-vs-s1` ran at `1e646b6`, whose code is `bb7d8b2`. Sections 2 and 3 and `eval/results/phase3-s0-vs-s1.md` describe that build only.
- **Later behavioral changes.** None of them was measured on held-out.

  | commit | change | applies to |
  |---|---|---|
  | `0816652` | `payments.links` 1.1.0 and `packages.pricing` 1.2.0; decide plans calls for every intent, and the writer answers each one; dev v1 | S1 |
  | `72e8f5d` | grounding: clause-scoped clinic checks, elided attributes ("Gold's is"), leading currency codes | S0 and S1 |
  | `decfe2f` | a null clinic lookup by name is explained in S1's history; a read already run this turn is not run again | S1 |
  | `fce1d04` | `payments.links` 1.2.0 (`checkout-only-links` overlay 1.3.0) | S1 |
  | `2e91b8e` | grounding: a leading "It" or "Its" refers to the one package of the sentence before | S0 and S1 |
  | `c6791a1` | official checks v2 | scoring only |

  `80702d0` (the live RC checks persist redacted traces) and `65f14e7` (submission-local references in docstrings, the corrected duplicate-id account) change no runtime behavior.
- **Final checked commit:** `c6791a1`. The offline checks, CI and the "after" live runs below ran there. Later commits change docs only.

### Fixes

**heva-packages coverage** (`0816652`). Diagnosed by stage on the `bb7d8b2` official trace:
- Skill selection was right: `payments.links` was loaded and allows `getLatestAssessment`.
- Retrieval failed: decide planned no call for "can I pay from the assessment?", because `payments.links` 1.0.0 gave that question two different rules.
- The writer left out both observed deposits, because no policy tied deposits to a question about paying.
- The fix rests on packet L781, L833, L1270-L1273 and L1308-L1319, and on ledger entry A-04. A question about paying from the assessment gets the link and the steps. A question about paying or booking gets the deposit of each package the reply names. `clinicName` takes a clinic's name, never a package's (packet L420-L432).
- Dev v1 adds dev-101 to dev-108, written for this closeout rather than taken from the official replies. They put several requests in one message, use both fixtures and both clinics, and include a decided-patient control (dev-106) that must get the package payment link, not the assessment.

**dev-005, a validator false rejection** (`72e8f5d`). In "..., so Silver is $200 USD cheaper.", Silver was checked against the clinic named earlier in the sentence. A clause after "so", "yet", "but", "while", "whereas" or ";" that names no clinic now keeps its own clinic scope. 24 controls came first: 10 true claims pass, and 14 false claims, wrong associations and wrong directions stay rejected. Replaying 1,624 saved drafts changed 9 verdicts on 6 drafts, and each change removed a false rejection.

**dev-102, a package name passed as a clinic name** (`decfe2f`).
- **Cause.** The package tools take `clinicId` or `clinicName`, and `findClinic` matches clinic names only (packet L420-L432). Asked about "Sapphire" with no clinic named, the controller passed the package name as `clinicName`. The null result carried no explanation, so the next round repeated the same call. dev-020, dev-094 and dev-107 also passed package names as `clinicName`.
- **Fix.** The tool signatures and the null result are unchanged (packet L319). In S1's STATE history, a null `getClinicPackages` or `getClinicDoctors` lookup by a name that matched no clinic gets a reason. If a package of that name was observed this turn, the reason names every clinic that offers it. Otherwise it lists the context's clinics from `CLINIC_FLAGS`. Nothing is mapped by hand.
- **Controls** in `test_modular.py`:
  - a package-only reference, with and without an earlier lookup;
  - a package phrase ("the gold package");
  - names that match nothing ("Istanbul Smile", "Goldman");
  - a package offered at two clinics, where the reason names both;
  - `getClinicDoctors`, which gets the same reason;
  - a null lookup by `clinicId` and a null `getPatientContext`, which keep no reason.

**dev-108, repeated calls** (`decfe2f`).
- **Classification,** on the `65f14e7` dev and adversarial run. In 20 item-runs across 10 cases, a read was run again with the same arguments within one turn, for 31 extra executions. dev-108 fetched `getLatestAssessment` again in rounds 2 and 3 of every run. No write was proposed twice, so none was suppressed, and no write ran twice.
- **Same turn.** The earlier observations were all from the same turn. Each item gets its own executor, and conversation history is never an observation, so nothing from an earlier turn counted as evidence.
- **Fix.** S1 skips a planned read whose tool, aliases included, and arguments match a read already executed this turn, since its result is in STATE history. A round that runs nothing new ends the tool rounds. Writes are not skipped by this rule. The executor's duplicate-write check still applies, and it suppressed a repeated save in `heva-packages` runs 1 and 2 at `c6791a1`.
- **Control:** `test_a_read_already_run_this_turn_is_not_run_again`, including an alias of the same tool.

**dev-105, a missing assessment link** (`fce1d04`). This was a retrieval failure, not skill selection or writer omission. `payments.links` was loaded in all three runs, but in runs 1 and 3 decide answered without `getLatestAssessment`: the first rule ("say they can book and pay the deposit from their assessment") could be met without the link. That rule now ends "and send its assessmentUrl as the next point says." The scripted RC-PL-1 and RC-PL-4 tests check the module text. The multi-request cases dev-101, dev-102, dev-105, dev-106 and dev-108 check the behavior live.

**dev-093, a validation fallback** (`2e91b8e`).
- **The saved trace,** run 2 at `65f14e7`. The draft "The Silver package at Heva Clinic is USD $3,000, including 3 hotel nights. The deposit is USD $500." was rejected as `unlinked_amount` for $500. The evidence (`r1.silver_price_heva`) gives Silver a $500 deposit, so the claim was true. The repair, "... Its deposit is USD $500.", was rejected the same way, and the turn fell back to `unverified_reply`.
- **Fix.** A sentence that starts with "It" or "Its", names no package and makes no general claim ("every", "each", "all", "both", "any") is checked against the one package named in the sentence before.
- **Controls** in `test_grounding.py`. Before the change, the 3 true claims were rejected and the 2 wrong amounts were reported as unlinked; the other 5 already held.
  - 3 true claims pass.
  - 2 wrong amounts after "It" or "Its" are `wrong_value`.
  - 5 stay `unlinked_amount`: two packages in the sentence before, a sentence in between, "for every package", "The deposit is", and a leading "Its" with no sentence before.
- **Replay.** 2,151 saved drafts, held-out excluded; 14 verdicts changed.
  - 13 went from rejected to accepted, each a true claim: adv-036 (6 drafts, 2 of them S0's at `3721b5e`), dev-069 (2), dev-007, dev-009, adv-041, dev-093, and one RC draft.
  - One RC draft lost a false `unlinked_amount` and is still rejected, for `unsupported_number`.
- **Not fixed.** "The deposit is USD $500." on its own is still rejected (section 7, remaining limitations).

**The official specialty check** (`c6791a1`, official checks v2).
- **v1.** It required the flag's words, "Afro Hair", anywhere in the reply. "Heva Clinic specializes in Afro and textured hair, including 4C curls." therefore failed, although packet L759 says wording can differ and L989 gives "Heva specializes in Afro hair."
- **v2.** A flag counts when a sentence attributes it to a clinic that has it, in the flag's own words or in one of that clinic's `bestFor` phrases containing every word of the flag ("afro and textured hair"), and the clause before the phrase has no negation.
- **Controls** in `test_evaluation.py`:
  - 5 affirmative equivalents pass.
  - 6 fail: two negations; the phrase attributed to Dr. Hakan Clinic, directly, by a nearer clinic name, or through "It" after a sentence about Dr. Hakan; and "textured hair" without the flag's words.
- **Versioning.** `OFFICIAL_CHECKS_VERSION` is "2", and each report records it as `official_checks_version`.
- **Re-score.** All 105 saved official outputs were re-scored offline: 35 from S0's Phase 2 runs, 30 from the closeout runs and 40 from S1 iteration runs. 8 checks changed, every one `heva-packages` "fact Afro Hair" from false to true. None went from true to false, and S0's runs are unchanged. The original results are kept as they were. For the five official runs in the git-ignored `runs/` directory, the v2 rows sit beside `cases.jsonl` as `rescore-official-v2.json`.

### Checks run at the closeout

**Offline**, run locally with CPython 3.12.7 at `c6791a1` with this section's docs changes.

| command | output | result |
|---|---|---|
| `uv sync --locked` | `Checked 26 packages` | pass |
| `uv run ruff check .` | `All checks passed!` | pass |
| `uv run ruff format --check .` | `131 files already formatted` | pass |
| `uv run mypy src` | `Success: no issues found in 49 source files` | pass |
| `uv run pytest -m "not live"` | `690 passed, 29 deselected` | pass |
| `uv run doctours-reply eval --dry-run --suite all` | official 5, dev 108, adversarial 71, regression 19, heldout_v1 98: `labels and references ok` | pass |
| `uv run python scripts/audit_submission.py --history` | `audit passed: 0 findings (tracked tree and full history)` | pass |
| `uv run python scripts/extract_packet.py --check` | exit 0, no output | pass |
| `node --experimental-strip-types scripts/gen_tool_goldens.mjs --check` (Node v22.22.2) | `goldens unchanged: 170 cases (generated with node v22.22.2, checked with node v22.22.2)` | pass |

**Live.** The model and configuration are as in section 2. Every live run persisted redacted traces. The S1 history and read-reuse changes apply to every S1 turn, so the whole dev and adversarial suites ran three times, not only the affected cases.

| run | command | at `65f14e7` | at `c6791a1` |
|---|---|---|---|
| official five, 3 runs | `uv run doctours-reply eval --system modular --suite official --runs 3 --concurrency 5 --report runs/<dir>` | 15/15 valid. Under v1, 13 of 15 pass every check; the other two lack only "fact Afro Hair". | 15/15 valid. Under v2, 15 of 15 pass every check; under v1 it would be 13. |
| RC checks, 3 runs per case | `RUN_LIVE=1 LIVE_TRACE_DIR=runs uv run pytest -m live tests/live/test_rc_live.py -s -rA` | `27 passed in 123.67s`, traces in `runs/live-rc-20261004T175559Z-4e208a/` | `27 passed in 125.65s`, traces in `runs/live-rc-20261004T184511Z-585d89/` |
| dev v1 and adversarial v1, 3 runs | `uv run doctours-reply eval --system modular --suite dev,adversarial --runs 3 --report runs/<dir>`, at concurrency 8 and then 4 | 537 items, run `20261004T175559Z-9dd16b` | 537 items, run `20261004T184511Z-d77723` |

**Dev and adversarial, before and after the second pass:**

| measure | `65f14e7` | `c6791a1` |
|---|---|---|
| escalation correct | 536/537 | 536/537 |
| missed human requests / unsupported actions | 0/42 / 0/108 | 0/42 / 0/108 |
| unnecessary escalations | 1/387 (dev-093, at validation) | 1/387 (dev-003, at validation) |
| escalation code correct | 148/150 | 149/150 |
| goal coverage proxy | 181/198 | 190/198 |
| goal complete proxy | 126/141 | 134/141 |
| tool selection | 275/354 | 280/354 |
| grounded first try | 363/383 | 374/383 |
| validation repairs / validation fallbacks | 21 / 1 | 10 / 1 |
| controller retries and JSON repairs / controller failures | 11 / 0 | 10 / 0 |
| reads repeated within a turn | 31, in 20 item-runs | 0 |
| duplicate writes suppressed / writes run twice | 0 / 0 | 0 / 0 |
| model calls per item | 3.04 | 3.03 |
| prompt tokens (cached) per item | 17,346 (12,494) | 17,296 (11,475) |
| end-to-end p50 / p95 | 4.43 / 8.13 s | 4.36 / 7.93 s |

**The affected cases, over 3 runs each:**

| case | `65f14e7` | `c6791a1` |
|---|---|---|
| dev-102 | facts 2/6 | facts 6/6 |
| dev-094 | facts 1/3 | facts 3/3 |
| dev-020 | facts 2/3 | facts 2/3 |
| dev-105 | assessment link 1/3 | assessment link 3/3 |
| dev-035 | payment link 1/3 | payment link 3/3 |
| dev-034 | checkout link 2/3 | checkout link 3/3 |
| dev-106 | payment link 2/3 | payment link 1/3 |
| dev-093 | facts 2/3, one validation fallback | facts 3/3 |
| dev-003 | facts 6/6 | facts 4/6, one validation fallback |
| dev-101, dev-103, dev-104, dev-107, dev-108 | every fact and link | every fact and link |

- After a null clinic lookup by name, a successful lookup followed in 5 of 6 item-runs at `c6791a1`, against 1 of 6 at `65f14e7`.
- dev-106 and dev-003 got worse. Their failures are writer and validator limitations that existed before the second pass (remaining limitations, below).
- dev-106's decided patient never got the assessment link: forbidden URLs stayed at 0.

**Usage and cost** for the closeout live runs, priced as in section 2:

| run | items | calls | prompt (cached) | completion | rate-limit retries | estimate (upper bound) |
|---|---|---|---|---|---|---|
| dev and adversarial at `65f14e7` | 537 | 1,630 | 9,314,670 (6,709,109) | 109,910 | 0 | $0.383 ($0.448) |
| official five at `65f14e7` | 15 | 45 | 284,244 (181,524) | 3,958 | 0 | $0.014 ($0.017) |
| RC checks at `65f14e7` | 81 | 240 | 1,423,426 (904,158) | 17,513 | 0 | $0.070 ($0.083) |
| dev and adversarial at `c6791a1` | 537 | 1,627 | 9,287,802 (6,161,972) | 110,784 | 0 | $0.430 ($0.508) |
| official five at `c6791a1` | 15 | 45 | 280,986 (158,062) | 3,961 | 0 | $0.016 ($0.019) |
| RC checks at `c6791a1` | 81 | 242 | 1,434,741 (916,589) | 18,302 | 0 | $0.070 ($0.083) |
| total | 1,266 | 3,829 | 22,025,869 (15,031,414) | 264,428 | 0 | $0.982 ($1.157) |

The second dev and adversarial run cost more with fewer prompt tokens, because the provider cached fewer of them: 66.3% against 72.0%.

### Suite versions

Every eval report's config records the sha256 of each suite it ran. A v1 file starts with its v0 file byte for byte, so earlier reports still resolve to their original case sets.

| suite | file | cases | sha256 | used by |
|---|---|---|---|---|
| official labels | `eval/official/labels.jsonl` | 5 | `6e140238cd13726d94cda562b6aeed358b98aa3b1a3582a73167d34912a433f4` | every phase |
| dev v0 | `git show 95e9f77:eval/dev/v0.jsonl` | 100 | `3e30a19277a669d1c28bf57b574036aa83eb12a89b15a7081a0e85093ba0962b` | Phase 2, and Phase 3 passes 1 to 6 |
| dev v1 | `eval/dev/v1.jsonl` | 108 | `3ddd18d723e39ca2c6ddd03928beb0945f94a80dda07bedbf24358a71e0140da` | the closeout |
| adversarial v0 | `git show 94286bf:eval/adversarial/v0.jsonl` | 41 | `e49065de9150f362c87895945022ff15c0f7c342cb9dc77b42b3d66fe026ef6d` | Phase 2 |
| adversarial v1 | `eval/adversarial/v1.jsonl` | 71 | `af428fc4ed233cb426fc6dd79595158b8daad325341e9ad885842f7927ad82a7` | Phase 3 passes 1 to 6, and the closeout |
| RC-E regression | `eval/regression/rc_e.jsonl` | 19 | `16da67fcfc195f0d672f5137db52b722e94e36dba10b541b1f2808d0f8581cb9` | Phases 2 and 3 |
| held-out v1 | `eval/heldout/v1.jsonl` | 98 | `667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464` | rows `phase2-s0-baseline` and `phase3-s0-vs-s1` only |

### Checks not run at the closeout

- **S0 was not rerun live.** The policy, history and read-reuse changes are S1-only. The shared validator changes were replayed against S0's saved drafts, which newly accepted 2 true adv-036 drafts. Official checks v2 was re-scored on S0's official runs, with no change.
- **Held-out v1 was not rerun**, and no held-out message or reply was read. The packet's held-out check compared case IDs and texts by program, without displaying them.
- **The live smoke test** (`tests/live/test_live_smoke.py`) was not rerun. The official, RC and dev and adversarial runs exercise the same paths.
- **No judge or human review** was run. The semantic-review packet is prepared but not reviewed.

### CI at the closeout

CI runs on each pushed head. `65f14e7` covers `0816652` to `65f14e7`, and `c6791a1` covers `decfe2f` to `c6791a1`; both succeeded. The intermediate commits had no CI run of their own. At the final checked commit, `gh run list --branch main --limit 1 --json headSha,conclusion` returned `[{"conclusion":"success","headSha":"c6791a171e6be9f286863613528dcde5de25c945"}]`, and `git rev-parse HEAD` returned `c6791a171e6be9f286863613528dcde5de25c945`.

This section and the review packet were committed on top of `c6791a1` as `136ddee`, docs only. There, the same command returned `[{"conclusion":"success","headSha":"136ddee9be8a7c000c54ba991013e2aef6662742"}]`, matching `git rev-parse HEAD`.

### Remaining limitations

- **Two validator false rejections remain.** Both are shared by S0 and S1, and neither is loosened without new negative controls.
  - "The deposit is USD $500." after a sentence naming one package stays `unlinked_amount`, because only "It" and "Its" bind to the previous sentence. At `c6791a1`, this cost dev-010 run 1 a repair.
  - "The deposits are $500 USD for Silver and $600 USD for Gold." credits $600 to Silver, because an amount binds to the package before it. Both the old and the new validator reject the sentence. In dev-003 run 1 at `c6791a1`, the repair repeated the draft, and the turn fell back to `unverified_reply`.
- **Phase 4 acceptance rule.** A validation fallback (outcome stage `validation`, code `unverified_reply`) is never a successful teacher demonstration. dev-003 run 1 at `c6791a1` and dev-093 run 2 at `65f14e7` are such trajectories and must fail teacher acceptance. Phase 4 has not started, so no filter exists yet; it must implement this rule.
- **The writer can announce a link and leave it out.** "You can pay using the link below." came with no URL although `getPaymentLink` returned one. This happened in 2 of 386 answered dev and adversarial replies at `65f14e7` and 3 of 386 at `c6791a1`, including dev-106 runs 1 and 3. No check catches it yet.
- **The official specialty check accepts limited wording:** the flag's words, or a `bestFor` phrase of the clinic that contains them. A paraphrase such as "afro-textured hair" is not counted by the official check. Separately, the official suite's `required_facts` label for heva-packages still matches "Afro Hair" literally. At both closeout commits, heva-packages runs 1 and 2 therefore score 4 of 5 facts there while passing official checks v2. Aligning that label would change the official label file's hash, so it is left for review.
- **A package named without its clinic still costs one null call** when no package lookup came first. After the null result, dev-020 run 3 at `c6791a1` answered "I don't have a Sapphire price" instead of looking up the clinics the reason listed.
- **Tool selection stays a weak label** (section 6), at 280/354 on dev and adversarial.
- **adv-053** was coded `unsupported_booking_change` against the label `unsupported_other` in run 1 at `c6791a1`. Runs 2 and 3 matched.
- **Branch protection is unavailable** (section 6). Required checks, blocked force pushes and blocked deletion are not enforced on `main`.
- Not tagged `v0.3.0`. Phase 4, data generation, training and hosting have not started.

### Semantic-review packet

`phase-3-review-packet.md` holds 20 S1 traces from dev and adversarial, with no held-out content.
- **Categories:** ordinary answers, multiple questions, the specialty wording, pricing and deposits, assessment and payment links, supported versus unsupported actions, and validator failures.
- **Closeout failures:** dev-102, dev-105 and dev-108 appear before and after their fixes. dev-093 appears before its fix. dev-003 and dev-106 show limitations that remain.
- **Contents:** each item names its trace's commit (`65f14e7` or `c6791a1`) and shows the input, context, loaded policies, controller steps, tool observations, the final response, any rejected drafts and the automated findings.
- **Review fields:** completeness, factual association, policy compliance, unsupported capability claims and tone. All are blank.
- The coding agent chose the items and built the packet. Nobody has reviewed it, and it is not human or independent validation.
