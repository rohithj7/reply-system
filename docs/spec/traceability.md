# Requirement traceability

Every requirement maps to packet lines (`L<n>` in `docs/assignment/pre-deposit-respond-packet.md`), a component and a test or check. Component paths are relative to `src/doctours_reply/`. Status is as of Phase 1: "done" items exist and are tested; everything else is planned.

## Packet requirements

| ID | Requirement | Packet lines | Component | Test or check | Status |
|---|---|---|---|---|---|
| R-01 | Read an array of `{id, text}` and write one `Reply` per item, same count and order | L29, L33, L690 | `cli.py`, `contract/io.py` | `tests/unit/test_input_contract.py`; `tests/integration/test_cli_contract.py` | `io.py` done; CLI planned |
| R-02 | No added fields such as `id` | L37-49 | `contract/reply.py` | `tests/unit/test_reply_schema.py`, `schemas/reply.schema.json` snapshot | done |
| R-03 | Exact types, nullability and enums | L37-80 | `contract/reply.py` | enum sweep and round-trip tests in `tests/unit/test_reply_schema.py` | done |
| R-04 | `templateId` is always null | L82 | `contract/reply.py`, `runtime/finalize.py` | contract test; invariant test across all outcomes | contract done; finalizer planned |
| R-05 | `escalate` only when a person must take over; short `escalationReason`, else null | L7, L82 | `contract/reply.py`, `runtime/outcome.py`, `runtime/finalize.py` | contract test; outcome-to-Reply mapping tests; escalation suite (RC-E) | contract done; rest planned |
| R-06 | Requests for a human escalate in any phrasing, but not negated, quoted or hypothetical mentions | L7 | route step, `policies/core/escalation.md` | RC-E cases on dev, held-out and adversarial sets | planned |
| R-07 | Actions no tool or rule can perform escalate; polite action requests differ from policy questions | L7 | route and decide steps, escalation taxonomy | RC-E cases with balanced controls | planned |
| R-08 | Escalation replies are one short sentence and the turn stops: no sales answer, no card data | L7, L759 | `runtime/escalation.py`, `runtime/validate.py` | RC-E mixed-intent cases; escalation-form unit tests | planned |
| R-09 | Plain text; any URL is on the last line | L82, L879, L1005 | `runtime/validate.py` | unit tests | planned |
| R-10 | At most 3 attachments, all returned by a tool this turn | L82, L1025 | `contract/reply.py`, `runtime/evidence.py` | contract test (max 3); provenance tests | max-3 done; provenance planned |
| R-11 | Fill the prompt with the constants, use the user template, offer only the supplied functions | L31-33, L673-686 | `resources/fixtures/packet/`, `prompts/legacy/`, `tools/registry.py`, `baseline/monolithic.py`, `runtime/context.py` | `tests/unit/test_packet_fixture.py` (placeholder fill); `tests/conformance/test_registry.py` (exactly 14 functions) | fixtures and registry done; runtime planned |
| R-12 | Items are independent | L690 | `runtime/context.py` | permutation-invariance and cross-item leakage probes | planned |
| R-13 | Faithful tools: `xTool` maps to `x`, shared IDs, null never filled in, canned writes preserved | L319, L321-671 | `tools/` | `tests/conformance/test_packet_tools.py` (TypeScript goldens), `tests/conformance/test_registry.py` | done |
| R-14 | Expected outputs are evaluation-only and never special-cased | L719 | `evaluation/` only | `tests/guards/test_eval_leakage.py`, `tests/guards/test_import_boundary.py` (CI) | guards done |
| R-15 | README: logic, structure, what stays loaded, escalation, prerequisites, install, key, command | L24-27 | `README.md` | Phase 7 gate | planned |
| R-16 | GitHub repo with full reviewer access | L22 | repository settings | Phase 7 gate | planned |
| R-17 | Generalization to unseen inputs | L29, L719 | whole system | dev, held-out and sealed sets on a fixed schedule | planned |
| R-18 | Improve on the block prompt and explain the improvement | L1-18 | modular runtime, policy manifests, traces, per-policy tests | baseline versus modular comparison | planned |
| R-19 | Preserve legacy behavior the assignment contract does not supersede | L761-1555 | `policies/**`, with source line references | per-policy tests | planned |

## Requirements from the brief

| ID | Requirement | Component | Test or check | Status |
|---|---|---|---|---|
| U-01 | Two repositories with a one-way dependency; this one never references the other | `scripts/audit_submission.py` | audit in CI; `tests/guards/test_import_boundary.py` | done |
| U-02 | No weights or adapters anywhere in the submission, including history | `scripts/audit_submission.py`, `.gitignore` | `audit_submission.py --history` in CI; `tests/guards/test_audit.py` | done |
| U-03 | Model access through `MODEL_BASE_URL`, `MODEL_API_KEY` and `MODEL_ID` | `models/openai_compat.py` | client tests | planned |
| U-04 | Reviewers can run on a CPU-only machine | whole system | Phase 7 fresh-clone gate | planned |
| U-05 | Export boundary and manifests | `resources/fixtures/manifest.json`, `resources/policy_sets/manifest.json`, `datasets/manifest.json` | audit manifest checks in CI | resource manifests done; datasets planned |
| U-06 | The monolithic baseline is not weakened | `baseline/monolithic.py` | decision record 0003 | planned |
| U-07 | Network-free CI plus an opt-in live suite | `tests/conftest.py`, pytest `live` marker | `tests/guards/test_network_guard.py` | done |
| U-08 | Policy and fact changes need no retraining | policies, fixtures | RC-PL-2, RC-PL-3, RC-G-10 | planned |
| U-09 | Exported evaluations reproduce from submission artifacts alone | `runtime/refs.py` | RC-R-1 to RC-R-3 (`tests/unit/test_refs.py`, `tests/guards/test_eval_refs_resolve.py`) | done |
