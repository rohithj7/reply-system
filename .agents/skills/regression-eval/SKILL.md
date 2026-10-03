---
name: regression-eval
description: Run the network-free regression checks and summarize failures. Use after a behavior change and before opening a pull request.
---

# Regression eval

1. Run the network-free suite and the audit:

   ```sh
   uv run pytest -m "not live"
   uv run doctours-reply eval --dry-run --suite all
   uv run python scripts/audit_submission.py --history
   ```

2. Report failures grouped by test file, with the first assertion message for each.
3. With `MODEL_*` configured, live runs of the iteration suites are allowed: `doctours-reply eval --suite dev,adversarial,regression --runs 3`. Report them as live evidence, separately from the scripted results.
4. Never run held-out or sealed sets from this skill. They run only through the logged schedule.
