# 0001: Repository boundary and plan location

Status: accepted (Phase 1)

## Context

Reviewers clone this repository and run it. It must be self-contained, and it must not carry planning material, model weights, credentials, or data-generation and training tooling. Separate private work may depend on this repository at a pinned commit; this repository must never depend on, import or name it.

## Decision

- The full implementation plan lives outside this checkout. `.gitignore` lists `.cursor/plans/` only as a guard against accidental commits.
- The repository holds no weights, adapters, checkpoints, generation code, teacher instructions or credentials. Model access is configured through environment variables only.
- Runtime code reads `resources/` (fixtures and policy sets, hash-listed in manifests) and never `eval/` or `docs/`. `resources/` never holds labels or expected answers; those live under `eval/`.
- The packet copy in `docs/assignment/` is verbatim and hash-checked. Tests read it; the runtime does not.

## Enforcement

CI enforces the boundary; development rules and skills only guide.

- `scripts/audit_submission.py --history` fails on tracked or historical planning files and the planning prompt, weights extensions, blobs over 5 MB, LFS entries, secret patterns, references to private repositories, a changed packet, stale or incomplete resource manifests, and banned export substrings.
- `tests/guards/` checks that runtime code imports no evaluation code and joins no `eval/` or `docs/` paths, that runtime files contain no official message or expected answer, that `resources/` has no answer keys, and that the audit fails on planted violations in temporary repositories.

## Consequences

- A history hit cannot be fixed by deleting the file; it needs a history rewrite, which requires explicit owner approval.
- The verbatim legacy prompt quotes one official message as an example, so the leakage guard exempts the two legacy template files, which are byte-pinned to the packet.
