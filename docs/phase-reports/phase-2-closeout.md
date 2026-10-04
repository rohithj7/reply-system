# Phase 2 closeout

Date: 2026-10-04. The baseline measurement (`eval/results/phase2-s0-baseline.md`, held-out log entry #1) stays attributed to `3721b5e` and is unchanged. Closeout code commits: `8234f07` (grounding) and `c9b6740` (cached-token accounting).

## 1. Scope delivered

**What changed after the measured commit.**
- `3721b5e..a4000af` touches only `README.md`, `docs/phase-reports/phase-2.md`, `eval/results/heldout-log.md` and `eval/results/phase2-s0-baseline.md`. Nothing in it affects inference or scoring.
- After `a4000af`:
  - **`8234f07`** changes the grounding validator, so it affects inference: a draft that fails validation gets one repair and can escalate at validation. The scorer is unchanged, but `grounded_first_try` now reflects the new rules.
  - **`c9b6740`** adds a `cached_prompt_tokens` field to traces and scores, and a per-item line in reports. Requests are unchanged.
- The baseline numbers therefore describe S0 at `3721b5e`, not the final build. The Phase 3 comparison reruns S0 on the same build as S1.

**Offline replay through the final validator.**
- Every saved development and adversarial draft was replayed against the evidence from its own trace: runs `dev-25bb735-c2`, `adversarial-25bb735-c2` and `adversarial-3721b5e`.
  - There were 563 answered drafts, including every draft the old validator had accepted. The 40 escalation drafts were checked for the escalation form.
  - Rejections fell from 70 to 28. No previously accepted draft is now rejected.
- **The 42 drafts that are now accepted** were each read and are honest:
  - corrections ("I meant Silver, not Gold");
  - honest absences ("there isn't a Sapphire package in the options I have");
  - clarifying questions;
  - correct arithmetic ("$4,500 and the deposit is $600, so $3,900 remains");
  - true denials naming the clinic that was looked up ("Dr. Hakan Clinic doesn't have a Silver package").
- **Four drafts kept a rejection with different codes.** For example, `dev-005` run 3 changed from `wrong_value` to `unverified_calculation`.
- **The 28 still rejected** split three ways:
  - About 8 are genuine errors: a false Heva Sapphire claim, "Silver at Hakan also $500", Gold quoted without being looked up, and unsupported recovery numbers.
  - 3 are borderline: the reply tells the patient to choose a package that wasn't looked up.
  - 17 have correct facts in wording the validator can't verify. They cost a repair, not a wrong reply.
- **Negative controls** in `tests/unit/test_grounding.py::test_denials_negations_and_calculations_must_be_grounded`:
  - false denials ("Heva doesn't have a Gold package", "Gold is not $4,500");
  - unverified denials of an unlisted clinic;
  - negations that don't govern the claim ("No doubt Heva has a Platinum package", "Not only is Gold $3,500 …");
  - wrong arithmetic and wrong direction ("Silver is $300 cheaper than Sapphire");
  - cross-package operands ("Gold's remaining balance is $4,500");
  - currency mismatch ("Gold is €4,500", "€3,900 remains");
  - false claims next to honest ones ("I can't confirm $999, but Gold is $999").
  - A calculated amount passes only when both operands are this turn's facts for the attributed packages, in the same currency, and the result is correct.

**Official smoke test on the final build.** `c9b6740`, one run, `runs/eval-live-official-c9b6740-smoke/`.
- **No infrastructure or contract failures:**
  - 5/5 replies valid before repair and after finalize;
  - 0 retries and 0 controller failures;
  - 5/5 escalation decisions correct;
  - both escalations happened at decide, after a write.
- **Baseline quality failures,** the same kinds seen before:
  - `consultation` omits the consultation link;
  - `hakan-price` omits the $500 deposit;
  - `heva-packages` omits both deposits and the assessment link, and its tool selection fails.
  - Per-case official checks are in `report.json` under `official_checks`.

**Escalation reconciliation (held-out v1, 294 items).**

| | escalated | answered |
|---|---|---|
| labelled escalate (81) | 27 | 54 |
| labelled answer (213) | 0 | 213 |

- **Missed escalations:**
  - 53 are unsupported-action requests.
  - One is a missed human request: `hv1-002`, run 3, "Would it be possible to have one of your staff give me a call today? …". The baseline answered that it couldn't arrange a call outside the free consultation and linked the consultation page. Runs 1 and 2 escalated.
- **Correct escalations:** 26 at decide and 1 at validation (`hv1-018`, run 3, a case labelled to escalate).
- **Escalations per case:**
  - Human-request cases: 5 of 6 escalated in all three runs, and 1 in two.
  - Unsupported-action cases: 14 of 21 never escalated.
- **The 267 grounding denominator** is the items whose final reply was an answer (294 − 27).
  - It leaves out `hv1-018` run 3, whose first draft was an answer, failed grounding, and then escalated at validation.
  - Counting every first draft that was an answer gives 257/268 (0.959) instead of 257/267 (0.963).

**Uncertainty by case.** The 294 items are 98 unique cases × 3 runs, and runs of the same case are correlated. The table compares Wilson intervals over items with a bootstrap that resamples cases with all their runs (10,000 resamples, seed 7). It also shows the case-level majority over three runs with a Wilson interval over cases.

| metric | items | Wilson, items | bootstrap, cases | cases | majority of runs |
|---|---|---|---|---|---|
| escalation_correct | 240/294 | [0.768, 0.856] | [0.741, 0.884] | 98 | 79/98 [0.717, 0.872] |
| missed unsupported action | 53/63 | [0.732, 0.911] | [0.714, 0.937] | 21 | 19/21 [0.711, 0.973] |
| missed human request | 1/18 | [0.010, 0.258] | [0.000, 0.167] | 6 | 0/6 [0.000, 0.390] |
| unnecessary escalation | 0/213 | [0.000, 0.018] | [0.000, 0.000] | 71 | 0/71 [0.000, 0.051] |
| grounded_first_try | 257/267 | [0.932, 0.980] | [0.934, 0.985] | 92 | 89/92 [0.908, 0.989] |
| tool_selection | 167/294 | [0.511, 0.623] | [0.486, 0.650] | 98 | 57/98 [0.483, 0.674] |
| forbidden_fact_cases | 6/294 | [0.009, 0.044] | [0.000, 0.048] | 98 | 2/98 [0.006, 0.071] |

- Escalation conclusions rest on 27 escalating cases: 6 human requests and 21 unsupported actions.
- A bootstrap interval of [0, 0] means none of the 71 cases ever escalated unnecessarily. That isn't a guarantee: the case-level Wilson bound is 0.051.

**Model, configuration and usage.**
- **Configuration**, from `report.json`, config sha256 `44b52966…`:
  - `gpt-6-luna` at `api.openai.com`, through the OpenAI SDK 3.24.0;
  - `reasoning_effort=none`, `json_schema` output, temperature unset (provider default);
  - 120 s timeout, 10 retries with 1, 2, 4 and then 8 s backoff, concurrency 2.
  - Every response reported model `gpt-6-luna`.
- **Usage (held-out run):**
  - 927 model calls (916 turns and 11 validation repairs) and 1,146 HTTP attempts.
  - 36,417,393 prompt tokens and 100,188 completion tokens.
- **Retry overhead:**
  - 219 retries on 183 calls (19.7% of calls), touching 125 of 294 items. All were rate-limit retries and all recovered.
  - Backoff sleep came to 257 s summed over items, and items ran two at a time.
  - Failed attempts return no usage to the client, so the token totals count successful attempts only.
- **Cached tokens:** not recorded for the held-out run, because capture landed in `c9b6740`. On the final build the official smoke test had 466,447 of 509,609 prompt tokens (91.5%) served from the provider's cache. This is the same prompt prefix, so the held-out run very likely had a similar rate, but that is not measured.
- **Monetary cost:** the actual billed amount is not visible to the client and needs the provider's billing dashboard. The estimates use list prices for prompts under 272k tokens ([OpenAI pricing](https://developers.openai.com/api/docs/pricing), checked 2026-10-04): $0.10/M input, $0.01/M cached input, $0.125/M cache writes and $0.50/M output.

| tokens | no caching | upper bound (all uncached input billed as cache writes) | estimate at the 91.5% cache rate |
|---|---|---|---|
| held-out run | $3.69 | $4.60 | $0.69 to $0.77 |
| all saved Phase 2 runs (118.2M prompt, 0.33M completion) | $11.98 | $14.93 | $2.24 to $2.50 |

  "All saved runs" covers the 10 run directories with traces. It excludes the live pytest gates, an aborted dev run without traces and the owner's smoke test.

**Decisions recorded.**
- Held-out v1 labels and scores are unchanged. Suspected label defects are in `docs/spec/heldout-v1-errata.md`:
  - E-1 and E-2 are the strict Gold labels;
  - E-3 is that `getPatientContext` isn't optional in 14 cases.
- The same file records the v2 rubric: factual correctness, relevance and policy compliance are scored separately, and the rubric is frozen before v2 is evaluated.

**Branch protection.**
- The repository is private on a free GitHub plan. The branch-protection endpoint (`/repos/{owner}/{repo}/branches/main/protection`, for both reads and the attempted `PUT`) and the rulesets endpoint both return 403 ("Upgrade to GitHub Pro or make this repository public to enable this feature").
- `gh api repos/{owner}/{repo}/branches/main --jq .protected` returns `false`.
- The repository stays private. CI still runs the offline checks on every push and pull request, and every report checks CI against `git rev-parse HEAD`.
- Required checks, blocked force pushes and blocked deletion need a paid plan or a public repository.

## 2. Checks run

| command | actual output | result |
|---|---|---|
| `uv run ruff check .` | `All checks passed!` | pass |
| `uv run ruff format --check .` | `87 files already formatted` | pass |
| `uv run mypy src` | `Success: no issues found in 42 source files` | pass |
| `uv run pytest -m "not live"` | `564 passed, 2 deselected` | pass |
| `uv run doctours-reply eval --dry-run --suite all` | `heldout_v1: 98 cases, labels and references ok` (last line) | pass |
| `uv run python scripts/audit_submission.py --history` | `audit passed: 0 findings (tracked tree and full history)` | pass |
| `uv run doctours-reply eval --suite official --runs 1 --concurrency 2 --report runs/eval-live-official-c9b6740-smoke` (live, `MODEL_MAX_RETRIES=10`) | table in section 1; 0 retries | pass (no infrastructure or contract failures) |
| offline replay of saved dev and adversarial drafts | `drafts 563, escalation_drafts 40, old_rejected 70, new_rejected 28, now_accepted 42, codes_changed 4` | pass (0 newly rejected) |

## 3. Checks not run

- The full live suites and held-out v1 were not rerun, as instructed.
- The actual billed cost needs dashboard access the agent doesn't have.
- The replay and reconciliation scripts read `runs/`, which is git-ignored. They are local analyses, not committed tools.

## 4. CI

`gh run list --branch main --limit 1 --json headSha,conclusion` returned `c9b67405681b7ea232312559df82fac04fe1479b`, `success`, which matched `git rev-parse HEAD` before this report commit. The report commit's own run is checked after pushing.

## 5. Deviations and decisions

- The final validator (`8234f07`) differs from the measured one (`3721b5e`). The baseline result stays attributed to the measured commit. The Phase 3 row runs S0 and S1 on one build, so the comparison doesn't depend on the old numbers.
- Cached-token capture was added before the smoke test so that the closeout could report cache use. Requests are unchanged.

## 6. Open questions and blockers

- Branch protection needs a plan upgrade or a public repository. The owner decides.
- The 17 strict-wording rejections in the replay cost repairs. Phase 3's writer is grounded on the executed fact table, which should reduce them. The validator is not loosened.
