# Phase 1 report: contract, fixtures, faithful tools and boundaries

Date: 2026-10-03. Last code commit: `02ad6ff`. This report is a docs-only commit on top of it.

## 1. Scope delivered

- **Contract.** `contract/reply.py` (strict `Reply`, `WorkingMemoryUpdates`, `CollectionState`; extra fields rejected; `templateId` must be null; at most 3 `attachmentUrls`; `escalationReason` non-empty exactly when `escalate` is true). `contract/io.py` (input parsing with a typed `InputContractError`, output serialization omitting unset memory keys). `schemas/reply.schema.json` snapshot.
- **Fixtures and prompts.** `scripts/extract_packet.py` extracts `resources/fixtures/packet/constants.json` (42 constants), `prompts/legacy/system_prompt.txt`, `prompts/legacy/user_message.txt` and `tests/conformance/reference/packet_tools.ts` verbatim from the packet, with a `--check` mode.
- **Tools.** `tools/data.py`, `tools/packet_tools.py` (14 functions plus `findClinic`), `tools/registry.py` (strict argument models, 10 reads and 4 writes, `xTool` aliases).
- **Goldens.** `scripts/gen_tool_goldens.mjs` runs the verbatim TypeScript under Node and writes 170 cases to `tests/conformance/goldens/packet_tools.json`.
- **Resource resolution.** `runtime/refs.py` resolves fixtures and policy sets (`shipped`, snapshot, overlay) from `resources/`, verifying sha256 per file. Typed errors cover unknown IDs, hash mismatches and stale overlays. `resources/fixtures/manifest.json` hashes the packet fixture; `resources/policy_sets/manifest.json` has no sets yet.
- **Boundaries.** `scripts/audit_submission.py` (stdlib only). Guard tests: evaluation leakage, no answer keys in `resources/`, import and path boundary, evaluation references, network block, audit negative tests, CI workflow shape, rule and skill front matter.
- **CI.** `.github/workflows/ci.yml` runs steps 1-4 and 6: install, lint and format, types, network-free tests, audit with `--history`. Checkout uses `fetch-depth: 0`. Actions are pinned by commit SHA, and permissions are read-only.
- **Docs and guidance.** `docs/spec/traceability.md`, `docs/spec/ambiguity-ledger.md`, `docs/decisions/0001-repo-boundary.md`, `AGENTS.md`, three `.cursor/rules/*.mdc` files and three `.agents/skills/*/SKILL.md` files.
- **Private companion skeleton.** Created locally outside this checkout, with no remote.

## 2. Checks run

All were run locally on 2026-10-03 at `02ad6ff`, unless noted otherwise.

| Check | Actual output | Result |
|---|---|---|
| `gh repo view rohithj7/doctours-take-home --json visibility -q .visibility` | `PRIVATE` | pass |
| `git ls-files \| rg -n '(^\|/)\.cursor/plans/\|\.plan\.md$\|doctours-cursor-planning-prompt'` | no output (rg exit 1) | pass |
| same pattern over `git log --all --name-only --format=` | no output (rg exit 1) | pass |
| `.gitignore` guard entry | `30:.cursor/plans/` | pass |
| `shasum -a 256 docs/assignment/pre-deposit-respond-packet.md` | `d06e044a4e3e13b4bc72343593c15cf05196cd51c8eee671c9d05a2cfc6e7436` | pass |
| `uv sync --locked` | `Resolved 18 packages`, `Checked 17 packages` | pass |
| `uv run ruff check .` | `All checks passed!` | pass |
| `uv run ruff format --check .` | `35 files already formatted` | pass |
| `uv run mypy src` | `Success: no issues found in 11 source files` | pass |
| `uv run pytest -m "not live"` | `336 passed` (unit 62, conformance 222, guards 52) | pass |
| `node --experimental-strip-types scripts/gen_tool_goldens.mjs --check` (Node v22.22.2) | `goldens unchanged: 170 cases (generated with node v22.22.2, checked with node v22.22.2)` | pass |
| `uv run python scripts/extract_packet.py --check` | no stale files (exit 0) | pass |
| `uv run python scripts/audit_submission.py --history` | `audit passed: 0 findings (tracked tree and full history)` | pass |

Test coverage, by Phase 1 acceptance item:

- **Contract.** Required fields; wrong types, including strict bool and int; extra fields; every enum value and null; max 3 attachments; escalation-reason consistency; unset memory keys omitted; schema snapshot.
- **Input.** A valid array; `[]` and duplicate IDs accepted; ten malformed inputs raise `InputContractError`.
- **Fixtures.** Packet hash; constants equal the packet parse; byte-equal legacy templates; only `{{clinic.slug}}` remains after filling; manifest hashes.
- **Tool conformance.**
  - All 170 golden cases match, including key order.
  - The reference defines exactly the ported functions, and results are deep copies.
  - The registry holds exactly 14 functions, classified as reads and writes.
  - Aliases resolve; unknown names, unknown keys and wrong types are rejected.
  - A mutation check confirmed the goldens catch JavaScript-versus-Python trim differences (U+FEFF, U+0085, U+001C).
- **References.**
  - RC-R-2: a one-byte change gives a hash mismatch.
  - RC-R-3: an overlay goes stale after a base version bump, and an overlay of a missing module also fails.
  - Snapshot hashes, escaping paths and missing files are covered.
  - RC-R-1 passes over the committed case files; there are none yet, see section 3.
- **Guards.**
  - Runtime files contain no official message, expected sentence, expected `escalationReason` or hyphenated official ID.
  - `resources/` holds no answer keys.
  - No runtime module imports evaluation code or joins `eval/` or `docs/` paths.
  - Each scanner flags planted violations.
- **Audit negative tests.**
  - RC-B-1 and RC-B-2: planning files and the planning-prompt filename fail, both tracked and history-only.
  - RC-B-3: weights, LFS, five secret patterns, a private-repository import and oversized blobs fail.
  - Also covered: mismatched and unlisted manifest entries, and banned export substrings.
  - RC-B-4: the workflow uses `fetch-depth: 0`, and its steps run in order, ending with `--history`.

## 3. Checks not run, and why

- **CI step 5 (`eval --dry-run --suite all`)** is not present. The CLI arrives in Phase 2; until then, `tests/guards/test_eval_refs_resolve.py` covers references.
- **RC-R-1 over real cases.** It passes vacuously, because no files exist yet under `eval/` or `datasets/`. A negative test with temporary rows shows the checker reports missing and unresolvable references.
- **Live tests.** None exist yet; the `live` marker and the socket-guard exemption are in place.
- **Branch protection.** Not configured or verified. The CI check on the head SHA is the gate.
- **Golden regeneration in CI.** Not run; it needs Node 22.6+ and is a development step. CI checks the Python port against the committed goldens.
- **Fresh-clone and CPU-only gates.** These belong to Phase 7.

## 4. CI

```text
$ gh run list --branch main --limit 1 --json headSha,conclusion   # run 37112683647
[{"conclusion":"success","headSha":"02ad6ff0f7080f149c69fd167a77152a3790c8c3"}]
$ git rev-parse HEAD   # before this report commit
02ad6ff0f7080f149c69fd167a77152a3790c8c3
```

Steps in that run: Install, Lint, Types, Tests (`336 passed`), Audit (`audit passed: 0 findings (tracked tree and full history)`), all `success`. CI used Python 3.12.3 on Ubuntu; locally, uv selected CPython 3.12.7. The CI result for this report commit is checked after it is pushed.

## 5. Deviations and decisions

- **Dependencies added** (need owner review): runtime `pydantic` 2.13.5; development `mypy` 2.4.0, `pytest` 9.1.1, `ruff` 0.16.10. All are locked in `uv.lock`. Nothing else was added. The audit, extractor and guard tests use only the standard library.
- **`tool_data.json` provenance.** It was produced once by importing the verbatim TypeScript reference under Node 22 and serializing its tables and canned results. Its correctness is established by the 170 golden cases, which pass through every table. The extractor handles the text-only files.
- **Leakage-guard exemption.** The packet's own system prompt quotes one official message as an example. The two legacy template files are therefore exempt from the leakage scan, and both are byte-pinned to the packet by `tests/unit/test_packet_fixture.py`.
- **Input items ignore extra keys.** Types stay strict, and missing fields still fail. This was added to ledger entry A-22.
- **RC-B-4 reads the workflow as text**, without a YAML parser, to avoid a new dependency.
- **Skills cite only checks that exist now.** The live dev subset and the eval-runner diff join `regression-eval` in Phase 2. A test asserts that every `uv run` check a skill or `AGENTS.md` cites is a CI step.
- **The import-boundary guard exempts only `evaluation/`.** Phase 2's CLI `eval` command will need an explicit decision there.

## 6. Open questions and blockers

- **No blockers.**
- **Reviewer confirmation still needed:** ledger entries A-02, A-04, A-05, A-08 and A-18, and the dependency list above.
- **Private companion remote.** It has none yet; the owner creates it as a private repository.
