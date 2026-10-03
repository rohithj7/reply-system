---
name: phase-gate
description: Run a phase's verification commands and record the real results in docs/phase-reports/phase-N.md. Run manually as /phase-gate N.
disable-model-invocation: true
---

# Phase gate

This skill sequences checks and writes them up. CI is what enforces them.

1. Run the CI checks in order and keep the full output:

   ```sh
   uv sync --locked
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pytest -m "not live"
   uv run doctours-reply eval --dry-run --suite all
   uv run python scripts/audit_submission.py --history
   ```

2. Run the development-only regeneration checks from `AGENTS.md` and record the Node version. Their outcomes are also asserted by `tests/unit/test_packet_fixture.py` and `tests/conformance/test_packet_tools.py`.
3. Push, then compare CI on the head commit:

   ```sh
   gh run list --branch main --limit 1 --json headSha,conclusion
   git rev-parse HEAD
   ```

4. Fill `docs/phase-reports/phase-N.md` with the template in `AGENTS.md`, quoting actual output. Keep checks run separate from checks not run.
5. Report pass only if every check passed and CI shows `success` for the head SHA. Never mark a gate passed while CI is red or pending.
