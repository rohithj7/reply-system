# 0003: A fair monolithic baseline

Status: accepted (Phase 2)

## Context

Later phases compare a modular system against the packet's single-prompt design. That comparison means something only if the baseline (S0, `baseline/monolithic.py`) is the packet's design run competently, not a weakened version.

## Decision

S0 keeps the packet's design:
- The verbatim legacy system prompt and user template, filled from the fixture constants (packet L29-33).
- All 14 packet functions as native tools, with their argument schemas from `tools/registry.py`.
- One model and one model ID for the whole turn.

S0 adds only what the assignment contract requires and what every system shares:
- A contract appendix restating the output contract (L7, L82). It quotes no packet message and no expected output.
- The shared executor: argument validation, ID provenance (IDs must come from a tool result this turn), each distinct write at most once, `updateWorkingMemory` at most once, and a budget of 8 calls.
- Bounded loops: at most 3 tool rounds, then a final call without tools; one JSON repair and one validation repair.
- The shared validators, redaction and pure finalizer. Card data is redacted before the model sees the message (A-21).

Evidence for grounding is what S0 was actually shown:
- Tool results from this turn.
- The $25 deposit cancellation fee, which the legacy prompt states as policy (L1147). The prompt's other amounts are examples, not facts.
- The legacy prompt's static links: image upload and consultation (L1453, L1462, L1467). Clinic pages count only for slugs returned this turn.
- Response URLs from the conversation history are not evidence. The prompt requires links to come from a tool this turn (L908, L1418) and forbids repeating sent links (L883).

When validation fails twice, or the model's JSON stays invalid, S0 escalates with a template (`unverified_reply`, `controller_failure`). It never sends an unverified reply.

Escalation stays available after a write. A model-chosen escalation keeps the model's sentence and reason when they pass the escalation checks, and falls back to the templates otherwise.

## Consequences

- S0 and later systems share the executor, validators, finalizer, traces and scorer, so differences come from routing and prompting, not from harness strictness.
- A legacy prompt that states an amount as policy must be added to `LEGACY_FACTS` with its packet lines, or grounding will reject that amount.
- Model selection is fair: every system in a comparison uses the same configured endpoint and model ID, recorded in the run's configuration hash.
