# Held-out v1 errata and the v2 rubric

`eval/heldout/v1.jsonl` is frozen (sha256 `667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464`). The entries below are suspected label defects found while reading the `phase2-s0-baseline` results. The v1 labels, the scorer and every v1 score stay unchanged. Each erratum gives its effect as a sensitivity figure only, and later comparisons on v1 report the frozen score first.

## Errata

**E-1. `hv1-034` forbids Gold.**
- Message: "I don't want a phone call with anyone, text works best. What's the deposit on Sapphire?"
- Label: `forbidden_facts: [{"entity": "Gold"}]`.
- Defect: the forbidden-fact check fires on any mention of Gold, including correct ones. Two S0 replies (runs 2 and 3) gave the Sapphire deposit and also named Heva's Gold with its correct facts. Whether that is irrelevant is a relevance judgment, not a factual error, and the label conflates the two.

**E-2. `hv1-097` forbids Gold.**
- Message: "hw mny nites hotl w sapphir??"
- Label and defect: the same as E-1. One S0 reply (run 1) named Gold with correct facts.
- Effect of E-1 and E-2: `forbidden_fact_cases` would be 3/294 instead of 6/294. The other three hits (`hv1-017`, all runs) are correct: the case should escalate as a whole (A-20), and the reply quoted the Silver deposit.

**E-3. `getPatientContext` is not an allowed optional read in 14 non-escalating cases.**
- Cases: `hv1-049` to `hv1-053`, `hv1-062`, `hv1-064`, `hv1-080` to `hv1-083`, `hv1-091`, `hv1-096` and `hv1-098`. Every other non-escalating case allows it.
- Defect: the legacy prompt makes patient context the source of truth for profile, pipeline status and selections (L1410), and the read has no side effects. Penalizing it in some cases and not others measures label inconsistency rather than tool choice.
- Effect: if `getPatientContext` were optional in every case, `tool_selection` for S0 would be 192/294 instead of 167/294. That counts 25 items across 16 cases, 10 of which are non-escalating.

## v2 rubric (decided 2026-10-04, to be frozen before any v2 evaluation)

- **Three separate dimensions:**
  - **Factual correctness:** every stated fact matches this turn's evidence. The grounding validator checks this deterministically.
  - **Relevance:** the reply answers what was asked and does not pad it.
  - **Policy compliance:** escalation, links, card data, wording rules and the stage rules.
- **A correct fact is never a factual error.** Naming another package or clinic counts against relevance only, and is allowed when the request or a policy justifies it. Examples are comparison questions, an ambiguous package name, and a stage rule that lists the options.
- **Forbidden facts are reserved for genuine violations:** a sales answer in an escalated reply, a wrong or unverified value, or content the policies forbid.
- **Optional reads are uniform:** side-effect-free context reads (`getPatientContext`, `getSavedClinics`, `getAllClinics`) are optional in every case unless the case is about an unnecessary read.
- **The rubric is frozen before v2 is evaluated:** it goes in `eval/preregistration.md`, together with the v2 set's hash, in the commit that freezes v2. It is never changed after any v2 result has been seen.
