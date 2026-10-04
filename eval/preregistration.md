# Pre-registration

One section per scheduled comparison in `src/doctours_reply/evaluation/schedule.py`, committed before its run. The log entry records this file's sha256 at run time, and the runner refuses a comparison row whose `## <row id>` section is missing.

`phase2-s0-baseline` is a single-system measurement and needs no section.

## phase3-s0-vs-s1

S0 (`baseline`, decision record 0003) against S1 (`modular`, decision record 0002) on held-out v1, once, at the commit that adds this section.

Command: `uv run doctours-reply eval --system baseline,modular --suite heldout_v1 --runs 3 --log-entry phase3-s0-vs-s1 --concurrency 2`.

**Held constant.** Both systems run in the same invocation, at the same commit, with the same:
- model and client: `gpt-6-luna`, `reasoning_effort=none`, `json_schema` output, provider default temperature (none sent), 120 s timeout, 10 retries, concurrency 2, the same `OpenAICompatClient`;
- tool implementations, `packet` fixture and `shipped` policy set;
- shared validators, redaction and finalizer.

S0 is rerun here, so the comparison uses this build's validators for both systems. The Phase 2 S0 record (`eval/results/phase2-s0-baseline.md`, git `3721b5e`) stays as it was and is not pooled with this run.

**Unit of analysis.** The 98 unique cases. The 3 runs per case are repeated measures of one case, not independent cases.
- Case-level 95% intervals use a case bootstrap: 10,000 resamples, seed 7, each resample drawing cases with all of their runs.
- The S1 minus S0 difference is paired by case and bootstrapped the same way.
- The exact McNemar test runs on each case's majority outcome across its runs.
- Item-level Wilson intervals over 294 items are reported but are not the basis for any claim.

**Targets.** Each is a pass or fail on the point estimates, with the case-level interval reported beside it:
1. Missed escalations, over all escalating cases (`missed_escalation` in the comparison block): S1 at most S0.
2. Goal coverage proxy (`goal_coverage_proxy`, required facts and URLs hit over required): S1 at least S0 minus 3 points.
3. Unnecessary escalations, over all non-escalating cases: S1 at most 5%.
4. Mean prompt tokens per item: S1 below S0.

**Reported without a target.**
- Missed escalations by labelled class (`missed_escalation_by_class`), and unnecessary escalations by control class.
- `escalation_code_correct` (S1 only; S0 emits one constant code).
- Tool selection, required and forbidden facts and URLs, and memory labels.
- Grounded first try, escalations by stage, validation-stage escalations, controller failures, and `tool_not_loaded` items.
- Cost: model calls, JSON repairs, validation repairs, skill loads, prompt, cached and completion tokens per item, retries, and end-to-end latency p50 and p95.

**Unverified.** There is no judge and no human review. Goal coverage, policy correctness and tone are measured only through the labelled proxies above, which check facts, URLs and escalation, not whether the reply answers well.

**Rules.**
- Held-out v1 labels and the scorer stay as committed. Suspected label defects go to `docs/spec/heldout-v1-errata.md` and do not change scores.
- Held-out failures do not become development or adversarial cases, and they do not drive policy or prompt changes.
- A repeat needs `--void-previous` with an infrastructure reason: a provider outage, credential failure or exhausted rate-limit retries. A system's own failure, including a controller failure, is a result, not a reason to repeat.
