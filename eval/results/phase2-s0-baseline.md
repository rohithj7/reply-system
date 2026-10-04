# phase2-s0-baseline: S0 on held-out v1

Held-out log entry #1. Run `20261004T023036Z-5b78d8` on 2026-10-04 at git `3721b5e`, config sha256 `44b5296684736d8028e3138ea68c4011eff43ef99bfd90149ede04d9d562e0b1`.

- Set: `heldout_v1`, sha256 `667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464`, 98 cases x 3 runs.
- System: `baseline` (S0, decision record 0003).
- Model: `gpt-6-luna` with `reasoning_effort=none`, `json_schema` output, provider default temperature, 120 s timeout, 10 retries, concurrency 2.
- No judge.

Command: `uv run doctours-reply eval --suite heldout_v1 --log-entry phase2-s0-baseline --runs 3 --concurrency 2`.

| metric | k/n | rate | 95% CI | per run |
|---|---|---|---|---|
| output_valid_after_finalize | 294/294 | 1.000 | [0.987, 1.000] | [1.0, 1.0, 1.0] |
| output_valid_before_repair | 294/294 | 1.000 | [0.987, 1.000] | [1.0, 1.0, 1.0] |
| escalation_correct | 240/294 | 0.816 | [0.768, 0.856] | [0.8163, 0.8163, 0.8163] |
| missed_escalation.human_request | 1/18 | 0.056 | [0.010, 0.258] | [0.0, 0.0, 0.1667] |
| missed_escalation.unsupported_action | 53/63 | 0.841 | [0.732, 0.911] | [0.8571, 0.8571, 0.8095] |
| unnecessary_escalation.all_non_escalating | 0/213 | 0.000 | [0.000, 0.018] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.card_data_without_action | 0/12 | 0.000 | [0.000, 0.242] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.hypothetical_human_mention | 0/12 | 0.000 | [0.000, 0.242] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.negated_or_quoted_human_mention | 0/12 | 0.000 | [0.000, 0.242] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.policy_question | 0/12 | 0.000 | [0.000, 0.242] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.rule_backed_redirect | 0/15 | 0.000 | [0.000, 0.204] | [0.0, 0.0, 0.0] |
| unnecessary_escalation.supported_payment_link | 0/15 | 0.000 | [0.000, 0.204] | [0.0, 0.0, 0.0] |
| escalations_after_write | 27/27 | 1.000 | [0.875, 1.000] | [1.0, 1.0, 1.0] |
| tool_selection | 167/294 | 0.568 | [0.511, 0.623] | [0.4898, 0.6122, 0.602] |
| required_facts | 56/78 | 0.718 | [0.610, 0.806] | [] |
| forbidden_fact_cases | 6/294 | 0.020 | [0.009, 0.044] | [0.0204, 0.0204, 0.0204] |
| required_urls | 8/12 | 0.667 | [0.391, 0.862] | [] |
| forbidden_url_cases | 0/294 | 0.000 | [0.000, 0.013] | [0.0, 0.0, 0.0] |
| memory_labels_ok | 293/294 | 0.997 | [0.981, 0.999] | [1.0, 1.0, 0.9898] |
| memory_tool_called_when_answered | 253/267 | 0.948 | [0.914, 0.969] | [0.9551, 0.9438, 0.9438] |
| grounded_first_try | 257/267 | 0.963 | [0.932, 0.980] | [0.9663, 0.9551, 0.9663] |
| validation_stage_escalation | 1/294 | 0.003 | [0.001, 0.019] | [0.0, 0.0, 0.0102] |
| controller_failure | 0/294 | 0.000 | [0.000, 0.013] | [0.0, 0.0, 0.0] |

Escalations by stage: 26 at decide, 1 at validation.

Cost per item: 3.15 model calls, 123,869 prompt tokens, 341 completion tokens. Latency p50 6.9 s, p95 11.6 s. Rate-limit retries: 219 in total, all recovered.

Reading notes:

- **Escalations are mostly missed.** 53 of 63 unsupported-action requests went unescalated: the legacy prompt has decline scripts for them, while ledger A-02 says to escalate. There were no unnecessary escalations.
- **Forbidden facts, 6 hits.**
  - `hv1-017`, all three runs: the baseline answered a request it should have escalated, quoting the Silver deposit.
  - `hv1-097` and `hv1-034`, three hits between them: the reply named Gold with correct facts, which those labels forbid.
  - The labels and scorer are unchanged after this run.
- **The validation-stage escalation** (`hv1-018`, run 3) was on a case labelled to escalate.
