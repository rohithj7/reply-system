# 0004: Versioned runtime policies and overlays

Status: accepted (Phase 3)

## Context

The packet's legacy prompt mixes rules for every situation into one text. A policy change means editing that text and hoping nothing else moves. S1 needs policy it can load per turn, trace by version, and change without code or retraining.

## Decision

Policies are Markdown modules under `src/doctours_reply/policies/`. Each starts with TOML front matter, which `policy_loader.py` validates strictly:
- `id`, `version` (semver), `layer`, `summary`, and the packet lines it comes from as `sources`;
- `activates_on`, the cues the router reads in the skill catalog;
- `requires`, other modules that load with it, closed transitively;
- `allowed_tools`, the tools a step may call while it is loaded;
- optional `when`, `facts`, `static_links` and `forbidden_patterns`.

There are four layers:
- `core` modules (identity, boundaries, escalation) load on every controller step.
- `context` modules load when their `when` matches a fixture constant, for example the pipeline stage or whether a promo is active.
- `skill` modules load when the router or decide step picks them.
- `writer` modules (output format, memory labels) go to the writer only.

Facts and links are evidence:
- A loaded module's `facts`, such as the $25 deposit cancellation fee (packet L1147), and its `static_links` count as evidence for grounding.
- An amount stated in policy text but not declared as a fact is rejected, as in S0.
- A loaded module's `forbidden_patterns` are checked against the reply and reported with the module's id.

Policy sets:
- `shipped` is the module directory.
- An overlay in `resources/policy_sets/` replaces named modules of a base set. Its manifest entry gives the module, its sha256 and `replaces_version`. `refs.py` refuses an overlay whose hash or replaced version does not match.
- The overlays are `lean-as-soft-interest` (clinics.selection 1.1.0), `checkout-only-links` (payments.links 1.1.0) and `deposit-fee-change` (payments.terms 1.1.0, a $40 fee).
- They exist to show that a policy change moves behavior without a code change. The tests and live checks run against them.

The trace records every loaded module's id, version and sha256, so a reply can be traced to the exact policy text it saw.

## Consequences

- A policy edit bumps the module's version. If an overlay replaces that module, its `replaces_version` and manifest hash are updated too (`.agents/skills/policy-change/SKILL.md`).
- A change of fact, such as a new price in a fixture's tool data, needs no policy edit. Facts come from tools, and the policies say which tool to call.
- The runtime reads policies from `src/` and `resources/` only. Neither holds labels or expected answers, and the leakage guard checks both.
- The controller sees a catalog of summaries and cues rather than every rule. Rules only matter once the router has loaded the right skill, so a routing miss means a rule never applies. Each skill's `activates_on` cues are therefore part of its policy.
