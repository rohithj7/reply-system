# phase3-s0-vs-s1: S0 and S1 on held-out v1

Held-out log entry #2. Run `20261004T123143Z-817eba` on 2026-10-04 at git `1e646b6`, config sha256 `14131c9416df40312b23e3a14ebfcea55de5fedeee9b1bb9c53b81d1364e94b7`. Pre-registration: `eval/preregistration.md`, section `phase3-s0-vs-s1`, sha256 `1d9249154affc12d86d06a9927148ebb98746914605982ccee1a794a3293a500`.

- Set: `heldout_v1`, sha256 `667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464`. It has 98 unique cases: 27 must escalate and 71 must not. Each ran 3 times per system.
- Systems: `baseline` (S0, decision record 0003) and `modular` (S1, decision record 0002), in one invocation.
- Model: `gpt-6-luna` at `api.openai.com`, with `reasoning_effort=none`, `json_schema` output, provider default temperature, 120 s timeout, 10 retries and concurrency 2.
- No judge.

Command: `uv run doctours-reply eval --system baseline,modular --suite heldout_v1 --runs 3 --log-entry phase3-s0-vs-s1 --concurrency 2`.

**Pre-registered targets.** Each is decided on the point estimates. The intervals are case bootstraps over the 98 cases, with each case's 3 runs kept together.

| target | S0 | S1 | S1 minus S0, 95% CI by case | result |
|---|---|---|---|---|
| missed escalations, all escalating, at most S0 | 51/81 (0.630) | 0/81 (0.000) | -0.630 [-0.790, -0.457]; McNemar 17 vs 0 cases, p < 0.001 | pass |
| goal coverage proxy, at least S0 minus 3 points | 73/90 (0.811) | 71/90 (0.789) | -0.022 [-0.111, 0.049] | pass on the point estimate; the interval does not rule out a larger loss |
| unnecessary escalations, at most 5% | 4/213 (0.019) | 3/213 (0.014), by case [0.000, 0.033] | -0.005 [-0.042, 0.024] | pass |
| mean prompt tokens per item, below S0 | 122,137 | 17,651 | -85.5% | pass |

## baseline

98 cases x 3 runs.

| metric | k/n | rate | 95% CI | cases | 95% CI by case | majority | per run |
|---|---|---|---|---|---|---|---|
| output_valid_after_finalize | 294/294 | 1.000 | [0.987, 1.000] | 98 | [1.000, 1.000] | 98 | [1.0, 1.0, 1.0] |
| output_valid_before_repair | 294/294 | 1.000 | [0.987, 1.000] | 98 | [1.000, 1.000] | 98 | [1.0, 1.0, 1.0] |
| escalation_correct | 239/294 | 0.813 | [0.764, 0.853] | 98 | [0.731, 0.884] | 80 | [0.8265, 0.8061, 0.8061] |
| missed_escalation.human_request | 0/18 | 0.000 | [0.000, 0.176] | 6 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation.unsupported_action | 51/63 | 0.809 | [0.696, 0.887] | 21 | [0.635, 0.952] | 17 | [0.7619, 0.8571, 0.8095] |
| missed_escalation_by_class.human_requested | 0/18 | 0.000 | [0.000, 0.176] | 6 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_booking_change | 6/6 | 1.000 | [0.610, 1.000] | 2 | [1.000, 1.000] | 2 | [1.0, 1.0, 1.0] |
| missed_escalation_by_class.unsupported_clinic_contact | 6/9 | 0.667 | [0.354, 0.879] | 3 | [0.000, 1.000] | 2 | [0.6667, 0.6667, 0.6667] |
| missed_escalation_by_class.unsupported_date_hold | 9/9 | 1.000 | [0.701, 1.000] | 3 | [1.000, 1.000] | 3 | [1.0, 1.0, 1.0] |
| missed_escalation_by_class.unsupported_document_action | 9/9 | 1.000 | [0.701, 1.000] | 3 | [1.000, 1.000] | 3 | [1.0, 1.0, 1.0] |
| missed_escalation_by_class.unsupported_money_movement | 3/9 | 0.333 | [0.121, 0.646] | 3 | [0.000, 0.667] | 1 | [0.0, 0.6667, 0.3333] |
| missed_escalation_by_class.unsupported_other | 3/6 | 0.500 | [0.188, 0.812] | 2 | [0.000, 1.000] | 1 | [0.5, 0.5, 0.5] |
| missed_escalation_by_class.unsupported_payment_action | 15/15 | 1.000 | [0.796, 1.000] | 5 | [1.000, 1.000] | 5 | [1.0, 1.0, 1.0] |
| escalation_code_correct | 0/0 | - | [0.000, 1.000] | 0 | - | - | [] |
| unnecessary_escalation.all_non_escalating | 4/213 | 0.019 | [0.007, 0.047] | 71 | [0.000, 0.052] | 1 | [0.0141, 0.0141, 0.0282] |
| unnecessary_escalation.card_data_without_action | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.hypothetical_human_mention | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.negated_or_quoted_human_mention | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.policy_question | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.rule_backed_redirect | 0/15 | 0.000 | [0.000, 0.204] | 5 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.supported_payment_link | 0/15 | 0.000 | [0.000, 0.204] | 5 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| escalations_after_write | 34/34 | 1.000 | [0.898, 1.000] | 13 | [1.000, 1.000] | 13 | [1.0, 1.0, 1.0] |
| tool_selection | 177/294 | 0.602 | [0.545, 0.656] | 98 | [0.517, 0.687] | 61 | [0.5714, 0.5816, 0.6531] |
| required_facts | 65/78 | 0.833 | [0.735, 0.900] | - | - | - | [] |
| forbidden_fact_cases | 4/294 | 0.014 | [0.005, 0.035] | 98 | [0.000, 0.037] | 1 | [0.0102, 0.0204, 0.0102] |
| required_urls | 8/12 | 0.667 | [0.391, 0.862] | - | - | - | [] |
| forbidden_url_cases | 0/294 | 0.000 | [0.000, 0.013] | 98 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| goal_coverage_proxy | 73/90 | 0.811 | [0.718, 0.879] | 27 | [0.636, 0.966] | 24 | [] |
| goal_complete_proxy | 70/81 | 0.864 | [0.773, 0.922] | 27 | [0.741, 0.963] | 24 | [0.8519, 0.8519, 0.8889] |
| tool_not_loaded_items | 0/294 | 0.000 | [0.000, 0.013] | 98 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| memory_labels_ok | 294/294 | 1.000 | [0.987, 1.000] | 98 | [1.000, 1.000] | 98 | [1.0, 1.0, 1.0] |
| memory_tool_called_when_answered | 247/260 | 0.950 | [0.916, 0.971] | 88 | [0.912, 0.981] | 83 | [0.9302, 0.9773, 0.9419] |
| grounded_first_try | 251/260 | 0.965 | [0.935, 0.982] | 88 | [0.939, 0.988] | 87 | [1.0, 0.9659, 0.9302] |
| validation_stage_escalation | 4/294 | 0.014 | [0.005, 0.035] | 98 | [0.000, 0.041] | 1 | [0.0102, 0.0102, 0.0204] |
| controller_failure | 0/294 | 0.000 | [0.000, 0.013] | 98 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |

Escalations by stage: {'decide': 30, 'validation': 4}

Cost: {"model_calls_per_item": 3.11, "retries_total": 154, "json_repairs_total": 0, "validation_repairs_total": 13, "skill_loads_per_item": 0.0, "prompt_tokens_per_item": 122137.17, "cached_prompt_tokens_per_item": 120983.59, "completion_tokens_per_item": 344.18, "latency_ms_p50": 6944.5, "latency_ms_p95": 11404.6, "end_to_end_ms_p50": 6955.5, "end_to_end_ms_p95": 11421.650000000001}

## modular

98 cases x 3 runs.

| metric | k/n | rate | 95% CI | cases | 95% CI by case | majority | per run |
|---|---|---|---|---|---|---|---|
| output_valid_after_finalize | 294/294 | 1.000 | [0.987, 1.000] | 98 | [1.000, 1.000] | 98 | [1.0, 1.0, 1.0] |
| output_valid_before_repair | 291/294 | 0.990 | [0.970, 0.997] | 98 | [0.973, 1.000] | 97 | [0.9796, 1.0, 0.9898] |
| escalation_correct | 291/294 | 0.990 | [0.970, 0.997] | 98 | [0.976, 1.000] | 98 | [0.9796, 1.0, 0.9898] |
| missed_escalation.human_request | 0/18 | 0.000 | [0.000, 0.176] | 6 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation.unsupported_action | 0/63 | 0.000 | [0.000, 0.058] | 21 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.human_requested | 0/18 | 0.000 | [0.000, 0.176] | 6 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_booking_change | 0/6 | 0.000 | [0.000, 0.390] | 2 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_clinic_contact | 0/9 | 0.000 | [0.000, 0.299] | 3 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_date_hold | 0/9 | 0.000 | [0.000, 0.299] | 3 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_document_action | 0/9 | 0.000 | [0.000, 0.299] | 3 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_money_movement | 0/9 | 0.000 | [0.000, 0.299] | 3 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_other | 0/6 | 0.000 | [0.000, 0.390] | 2 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| missed_escalation_by_class.unsupported_payment_action | 0/15 | 0.000 | [0.000, 0.204] | 5 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| escalation_code_correct | 78/81 | 0.963 | [0.897, 0.987] | 27 | [0.889, 1.000] | 26 | [0.963, 0.963, 0.963] |
| unnecessary_escalation.all_non_escalating | 3/213 | 0.014 | [0.005, 0.041] | 71 | [0.000, 0.033] | 0 | [0.0282, 0.0, 0.0141] |
| unnecessary_escalation.card_data_without_action | 1/12 | 0.083 | [0.015, 0.354] | 4 | [0.000, 0.250] | 0 | [0.25, 0.0, 0.0] |
| unnecessary_escalation.hypothetical_human_mention | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.negated_or_quoted_human_mention | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.policy_question | 0/12 | 0.000 | [0.000, 0.242] | 4 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.rule_backed_redirect | 0/15 | 0.000 | [0.000, 0.204] | 5 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| unnecessary_escalation.supported_payment_link | 0/15 | 0.000 | [0.000, 0.204] | 5 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| escalations_after_write | 0/84 | 0.000 | [0.000, 0.044] | 30 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| tool_selection | 233/294 | 0.792 | [0.743, 0.835] | 98 | [0.714, 0.867] | 78 | [0.7959, 0.8061, 0.7755] |
| required_facts | 63/78 | 0.808 | [0.707, 0.880] | - | - | - | [] |
| forbidden_fact_cases | 0/294 | 0.000 | [0.000, 0.013] | 98 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |
| required_urls | 8/12 | 0.667 | [0.391, 0.862] | - | - | - | [] |
| forbidden_url_cases | 2/294 | 0.007 | [0.002, 0.025] | 98 | [0.000, 0.020] | 1 | [0.0, 0.0102, 0.0102] |
| goal_coverage_proxy | 71/90 | 0.789 | [0.694, 0.861] | 27 | [0.630, 0.933] | 23 | [] |
| goal_complete_proxy | 66/81 | 0.815 | [0.717, 0.884] | 27 | [0.667, 0.938] | 23 | [0.7778, 0.8519, 0.8148] |
| tool_not_loaded_items | 1/294 | 0.003 | [0.001, 0.019] | 98 | [0.000, 0.010] | 0 | [0.0102, 0.0, 0.0] |
| memory_labels_ok | 291/294 | 0.990 | [0.970, 0.997] | 98 | [0.969, 1.000] | 97 | [0.9898, 0.9898, 0.9898] |
| memory_tool_called_when_answered | 18/210 | 0.086 | [0.055, 0.131] | 71 | [0.033, 0.151] | 6 | [0.0725, 0.0986, 0.0857] |
| grounded_first_try | 201/210 | 0.957 | [0.921, 0.977] | 71 | [0.919, 0.986] | 68 | [0.9855, 0.9437, 0.9429] |
| validation_stage_escalation | 2/294 | 0.007 | [0.002, 0.025] | 98 | [0.000, 0.017] | 0 | [0.0204, 0.0, 0.0] |
| controller_failure | 0/294 | 0.000 | [0.000, 0.013] | 98 | [0.000, 0.000] | 0 | [0.0, 0.0, 0.0] |

Escalations by stage: {'route': 82, 'validation': 2}

Cost: {"model_calls_per_item": 3.09, "retries_total": 0, "json_repairs_total": 3, "validation_repairs_total": 11, "skill_loads_per_item": 0.02, "prompt_tokens_per_item": 17650.62, "cached_prompt_tokens_per_item": 11398.99, "completion_tokens_per_item": 216.9, "latency_ms_p50": 4686.0, "latency_ms_p95": 9284.5, "end_to_end_ms_p50": 4700.0, "end_to_end_ms_p95": 9315.1}

## modular minus baseline

```json
{
  "escalation_correct": {
    "difference": 0.1769,
    "ci95": [
      0.102,
      0.2585
    ],
    "cases": 98,
    "discordant_cases": [
      0,
      18
    ],
    "mcnemar_p": 0.0
  },
  "missed_escalation": {
    "difference": -0.6296,
    "ci95": [
      -0.7901,
      -0.4568
    ],
    "cases": 27,
    "discordant_cases": [
      17,
      0
    ],
    "mcnemar_p": 0.0
  },
  "unnecessary_escalation": {
    "difference": -0.0047,
    "ci95": [
      -0.0423,
      0.0235
    ],
    "cases": 71,
    "discordant_cases": [
      1,
      0
    ],
    "mcnemar_p": 1.0
  },
  "goal_complete_proxy": {
    "difference": -0.0494,
    "ci95": [
      -0.1358,
      0.0
    ],
    "cases": 27,
    "discordant_cases": [
      1,
      0
    ],
    "mcnemar_p": 1.0
  },
  "tool_selection": {
    "difference": 0.1905,
    "ci95": [
      0.1054,
      0.2789
    ],
    "cases": 98,
    "discordant_cases": [
      6,
      23
    ],
    "mcnemar_p": 0.0023
  },
  "goal_coverage_proxy": {
    "difference": -0.0222,
    "ci95": [
      -0.1111,
      0.049
    ],
    "cases": 27
  },
  "prompt_tokens_per_item": [
    122137.17,
    17650.62
  ]
}
```

Reading notes:

- **The unit is the case.** There are 98 unique cases, each run 3 times per system. The runs are repeated measures, not 294 independent cases. The escalation results rest on 27 escalating cases, the controls on 71 non-escalating cases, and goal coverage on the 27 cases with required facts or URLs. The item-level Wilson intervals overstate precision; the case-level intervals are the ones to use.
- **Escalation.**
  - S1 missed no escalation in any class. S0 missed every unsupported payment action, date hold, document action and booking change, plus 6 of 9 clinic-contact, 3 of 6 other and 3 of 9 money-movement items. Both systems escalated every human request.
  - S1's code matched the label on 78 of 81 escalated items (26 of 27 cases by majority). S0 always uses one code, so it has no code accuracy.
  - 82 of S1's 84 escalations came at route, before any tool ran, and none followed a write (`escalations_after_write` 0/84). All 34 of S0's followed a write.
- **Unnecessary escalations.** No case escalated unnecessarily by majority, for either system.
  - S1 had 3 items: one card-data control in one run, and two validation-stage escalations in run 1 (hv1-043, three `wrong_value` twice; hv1-097, `unknown_package` twice).
  - S0 had 4 items, all at validation: hv1-056 in all three runs (`unverified_calculation`) and hv1-066 in run 3 (`wrong_value`).
  - Replaying those S0 drafts through the validator at `a8fcd88`, before the Phase 3 grounding change, gives the same violation codes. So that change did not cause them.
  - These notes come from violation codes only. No held-out message or reply was read.
- **Facts, URLs and tools.**
  - Required facts: S0 65 of 78, S1 63 of 78. Required URLs: 8 of 12 for both.
  - Forbidden facts: S0 4 items (1 case by majority), S1 none. Forbidden URLs: S1 2 items (1 case by majority), S0 none.
  - Tool selection: S1 0.792, S0 0.602, a difference of +0.190 [0.105, 0.279]. The McNemar test counts 23 cases better and 6 worse, p = 0.0023.
- **Memory.**
  - `memory_labels_ok`: S1 291 of 294, S0 294 of 294.
  - `memory_tool_called_when_answered` (S1 18 of 210, S0 247 of 260) cannot be compared between the systems. S1 calls `updateWorkingMemory` only when the validated draft changes memory; S0's model calls it on most turns.
- **Cost and latency.**

  | per system, 294 items | S0 | S1 |
  |---|---|---|
  | model calls | 914 (3.11 per item) | 909 (3.09 per item) |
  | prompt tokens | 35,908,329 (122,137 per item) | 5,189,283 (17,651 per item) |
  | of which cached | 35,569,175 (99.1%) | 3,351,302 (64.6%) |
  | uncached prompt tokens per item | 1,154 | 6,252 |
  | completion tokens | 101,188 | 63,769 |
  | JSON repairs or controller retries / validation repairs | 0 / 13 | 3 / 11 |
  | rate-limit retries | 154, all recovered | 0 |
  | end-to-end latency p50 / p95 | 6.96 s / 11.42 s | 4.70 s / 9.32 s |
  | list-price estimate (upper bound) | $0.440 ($0.449) | $0.249 ($0.295) |

  - Prices: $0.10/M input, $0.01/M cached input and $0.50/M output, with the upper bound charging all uncached input as cache writes at $0.125/M (`docs/phase-reports/phase-2-closeout.md`).
  - These figures come from the trace's token counts, not a provider invoice. Failed HTTP attempts return no usage, so they are not counted.
  - S0's long legacy prompt is a fixed prefix that the provider caches. S1 therefore sends 86% fewer prompt tokens but about 5 times more uncached ones, and costs about 43% less at list price.
- **This S0 run is not the Phase 2 record.** The validators changed in the Phase 2 closeout and in `7b6cf58`, the scorer gained the "N hotel nights" match, and the model varies from run to run. Against `phase2-s0-baseline.md`, this run has 239 correct escalations instead of 240, 51 missed unsupported actions instead of 53, and 4 unnecessary escalations instead of 0. That record stays as it was and is not pooled with this run.
- **Unverified.** There was no judge and no human review. Goal coverage, policy correctness and tone are measured only through the labelled proxies.
