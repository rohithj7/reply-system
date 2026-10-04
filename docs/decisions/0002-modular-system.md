# 0002: A modular reply system

Status: accepted (Phase 3)

## Context

S0 sends the whole legacy prompt (about 39k tokens) on every call and lets one model call choose tools, write the reply and decide escalation together. On held-out v1 it missed 53 of 63 unsupported-action escalations, because the prompt scripts declines for them while ledger A-02 says to escalate. S1 (`runtime/modular.py`) splits the turn into steps a controller can be checked on, and loads only the policy that a turn needs.

## Decision

The flow is route, load, decide, execute and observe, write, validate, commit memory.

- **Route.** One controller call classifies each intent: its kind, what supports it (`tool:<name>`, `self_service:`, `rule:` or `none`) and, for an escalation, the code. It picks the skills to load. An unsupported action or a human request escalates here.
- **Load.** `policy_loader.py` renders the core and matching context modules on every step, plus the chosen skills and their `requires`. The tools a step may call are the union of the loaded modules' `allowed_tools` (decision record 0004).
- **Decide.** One controller call per round either plans tool calls from that allowlist, loads more skills (at most once), or chooses answer, clarify or escalate. The first decide call must review the route.
- **Execute and observe.** The shared executor runs the calls in their listed order, with its argument checks, ID provenance, single writes and budget of 8 calls. A call outside the allowlist returns `tool_not_loaded` and spends no budget. There are at most 3 execute rounds, then a final decision without tools.
- **Write.** The writer has no tool client. It sees the loaded skills, the writer modules, the context and this turn's observations, and drafts the reply and its memory update.
- **Validate.** The shared validators check the draft against evidence: this turn's tool results, the loaded policies' facts and links, and what the writer was shown. There is one JSON repair and one validation repair, as in S0. A draft that still fails escalates as `unverified_reply`.
- **Commit memory.** The finalizer's memory diff runs as one `updateWorkingMemory` call after validation, outside the budget, so a rejected draft writes nothing.

Escalation:
- An escalation closes the executor, so no tool or memory call follows it.
- The patient sees the code's template sentence from `runtime/escalation.py`. There is no escalation writer call.
- The controller's reason is kept when it passes the shared escalation-reason checks, and replaced by the template's reason otherwise.
- A controller decision that fails its schema or semantic checks gets one retry listing the problems. A second failure escalates as `controller_failure`.

Serialization:
- `controller_io.py` (v1) fixes the format of every step: one system message (the step template and the policies every step loads) and one user message holding STATE as JSON.
- The patient's message, the context and tool results appear only inside STATE, as data.
- The decision models in `runtime/decision.py` are the contract, snapshotted in `schemas/route.schema.json`, `schemas/decide.schema.json` and `schemas/decide_final.schema.json`.

## Consequences

- S0 and S1 share the client, tools, executor, validators, redaction, finalizer, traces and scorer (decision record 0003). A comparison between them measures routing, policy loading and prompting.
- A controller served from elsewhere only has to produce JSON matching the decision schemas from the documented STATE. The runtime imports no training code.
- The template sentence for each code is fixed, so escalations read the same whatever the controller wrote. The cost is less tailored handoff wording.
- Cost per item is capped: at most 6 controller steps (route, one skill load, 3 execute rounds, a final decision), each with one retry, then the writer and its two repairs.
