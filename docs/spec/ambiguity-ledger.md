# Ambiguity and precedence ledger

Where the packet's sources conflict, this ledger records which one wins and why. Line numbers refer to `docs/assignment/pre-deposit-respond-packet.md`. Judgment calls that needed confirmation say when they were accepted.

## Precedence, highest first

1. The assignment contract (L1-82, L319, L673-690).
2. The tools' actual behavior (L321-671) over prose that describes them.
3. Legacy HARD and CRITICAL rules, then the remaining legacy rules. Within the legacy prompt, the more specific rule wins (for example L971).
4. Fixture constants.

Expected outputs are never a source. A conflict between them and the sources above is recorded here, not copied.

## Entries

**A-01. Who owns escalation.**
- Conflict: the legacy prompt assumes routing happens upstream and bans handoff language (L876, L913-914, L1317, L1407). The assignment makes this system escalate (L7).
- Resolution: the assignment wins. Handoff wording is allowed only in an escalated outcome. The legacy ban on handoff wording stays in force for every other reply.

**A-02. Decline scripts versus escalation, and policy questions versus action requests.** Accepted 2026-10-03.
- Conflict: the legacy prompt has decline scripts for date holds, refunds, clinic contact, extra calls and discounts (L775, L903, L913, L922, L980, L1317, L1407). The assignment lists "contacting a clinic to hold a date" as an escalation (L7).
- Resolution, with the full taxonomy planned for `policies/core/escalation.md`:
  - Escalate when the patient makes an action request, in any politeness form ("hold a date for me", "can you hold a date for me?", "could you call the clinic?"), that no supplied tool, documented self-service link or rule-backed redirect can satisfy.
  - Escalate on a current, first-person request for a human.
  - Answer a policy question ("do you offer date holds?", "can dates be held?") from policy.
  - Answer rule-backed redirects: creators pointed to Molly (L957), "can I message the clinic myself" on the first ask (L980), and revision requests (L1433).

**A-03. One sentence or two.**
- Conflict: the mandate says "one short sentence" (L7), but the expected charge-card reply has two (L754).
- Resolution: exactly one sentence of 20 words or fewer. It may name what cannot be done. The grading note (L759) does not count sentences.

**A-04. Re-sending a link already sent.** Accepted 2026-10-03; the grading note informed this rule.
- Conflict: the legacy prompt bans repeat links unless the patient asks (L883, L1267, L1549). Step 0 says to fetch the assessment link whenever it needs sharing (L1270-1271, L1312), and the grading note expects the assessment link (L759).
- Resolution: re-send a link when the current request is to act on that resource (pay or book from it, open it, find it) or when the patient asks for it. Otherwise do not repeat it.

**A-05. Consultation duration.** Accepted 2026-10-03.
- Conflict: a duration appears only in an expected reply (L742). Grounding rules forbid stating ungrounded consultation-format facts (L930, L946).
- Resolution: state no duration. This knowingly deviates on one official check.

**A-06. The no-CTA rule versus the consultation link.**
- Conflict: a simple factual question gets "no next-step CTA" (L994). Operational knowledge gives the consultation's location as a link (L1453).
- Resolution: include the consultation link as the location of the thing asked about. Never add a funnel question to a simple question. Advance the funnel only on a decision or readiness signal (L1324).

**A-07. Tool names.**
- Conflict: the prompt says `xTool` while the functions are `x` (L319). `updateWorkingMemory` has no suffix (L1472).
- Resolution: model-facing names are the function names, and the registry resolves `xTool` aliases (`tools/registry.py`).

**A-08. Capabilities the prompt mentions but the packet does not supply.** Accepted 2026-10-03.
- Missing tools: getBookingPackageDetailsTool, getTripRecommendationsTool, searchAirportsTool, updateUserAirportTool, updateFlightPreferencesTool, getTripDetailsTool.
- Missing systems: the booking-documents link (L897), the revision detector (L901, L1433) and Mastra memory (L1551-1554).
- Resolution: none of these are exposed, and booked-tier rules are dropped. A request that needs one of them is an unsupported action and escalates (A-02). Revision requests keep the packet's stated behavior; the packet describes the revision queue as external automation, which this harness does not implement, and the README will say so.

**A-09. Output fields described in prose but absent from tools.**
- Absent: `availableAddons`, `addons[]`, `listPrice`, the hotel lists, airports, `itinerary`, `purchasedAddons`, `ai_context.badFor`/`ranking`/`status`, and `dropped` reasons.
- Resolution: an absent field means "I don't have that detail". With no tier status, no tier restrictions apply. The saved clinics are the assessment recommendations.

**A-10. Canned, non-persistent writes.**
- The four write functions return fixed results. `getPatientContext` still shows null selections after a save. The preferences function neither checks package-clinic membership nor accepts `tentativeProcedureDates` (despite the prose at L1414).
- Resolution: preserve all of this exactly (`tests/conformance/`). A write's actual return value is shown to the controller as an observation. Nothing persists across items. Unknown arguments are rejected with a recorded observation. No rollback is attempted.

**A-11. The clinic `url` field.**
- Conflict: `getAllClinics` returns a `url` equal to the Doctours clinic page (L331), while the prose calls it the clinic's own site (L866-868).
- Resolution: on a repeat website ask, say that page is the one on file. Do not resend it or invent a domain.

**A-12. Clock.** The current time is fixed in the fixture (L1509). The system clock is never used.

**A-13. Static message classification.** "Category: pricing" is the same for every item (L1530-1532). The baseline keeps it verbatim; the modular system never routes on it.

**A-14. Placeholders.** `{{clinic.slug}}` is a model-facing template. Fill only placeholders that match a constant name, and assert that `{{clinic.slug}}` is the only one remaining (`tests/unit/test_packet_fixture.py`).

**A-15. Memory channel.**
- Conflict: the legacy prompt says "the entire JSON" and "do not remove empty sections" (L1501-1502), but also "merged; only changed fields" (L1505). The Reply carries a `workingMemoryUpdates` field (L48).
- Resolution:
  - `workingMemoryUpdates` is a separate Reply output field: a partial diff of changed fields, or null when nothing changed. Unset keys are omitted (`contract/reply.py`).
  - The packet requires a memory call whenever relevant information arrives (L1472, L1503). On a non-escalated turn whose validated diff is non-empty, the executor runs exactly one `updateWorkingMemory` call with `{"memory": <diff>}`, the merge form (L1505).
  - The canned `{success: true}` result is recorded as an observation and is never treated as persistence.
  - The modular controller cannot plan `updateWorkingMemory`; the memory commit is the only path, and the executor allows at most one call per item.
  - Escalated turns make no memory call. Their returned field follows A-18.
  - The baseline exposes all 14 functions, so its model decides when to call `updateWorkingMemory`, through the same executor and the same once-per-item limit.
  - The finalizer stays pure and executes nothing. Tentative dates never go into memory (L1414).

**A-16. Consultation history.** The summary says the consultation is not scheduled (L93), and the reschedule tool returns `no_consultation`, but a completed consultation call is on record (L103). Resolution: never say the patient has not had one, never push booking, and send no reschedule link.

**A-17. Empty attachments.** `attachmentUrls` is `[]` when empty, following "leave empty" (L1025).

**A-18. Escalated replies.** Accepted 2026-10-03 as a design choice:
- `shouldFollowUp=false`, `followUpTiming=null`, `attachmentUrls=[]`.
- `intent` is a short phrase.
- `highEngagement=false`.
- `workingMemoryUpdates={"escalationFlags": <reason code>}`.

**A-19. Stale examples.**
- The legacy prompt names entities missing from the fixtures: Heva VIP, MetropolMED, Diamond, No Shave FUE, Esthetic Hair and Art Line. Some example facts conflict with the fixtures (L1041, L1395).
- Incisions: Sapphire's `aiContext` covers drawing the hairline, not incisions, so the Dr. Hakan rule applies. Gold's `aiContext` overrides.
- Resolution: rewrite examples with neutral placeholders, and never assert that a non-fixture entity exists.

**A-20. Mixed intents.** "Answer all questions" (L781) conflicts with "do not keep answering" (L7). Resolution: escalation is terminal for the whole message.

**A-21. Card data.** Card numbers and card fragments are redacted from the patient text before any model call and in traces, and never echoed in a reply. Redaction is independent of escalation: card data alone never decides intent.

**A-22. Unusual input.**
- Duplicate IDs are accepted, and an empty array produces `[]`.
- Blank text gets a short clarifying Reply.
- Extra keys on an input item are ignored.
- Wrong types or missing fields cause a non-zero exit with nothing written (`contract/io.py` raises `InputContractError`).

**A-23. Model outage.** Retry with bounded backoff, since model calls are idempotent. If retries run out, exit non-zero with the failing item's index and write nothing. Never fabricate an escalation to cover the failure. Tools already executed in that item are recorded in its trace.
