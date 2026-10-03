---
name: regression-eval
description: Run the network-free regression checks and summarize failures. Use after a behavior change and before opening a pull request.
---

# Regression eval

1. Run the network-free suite and the audit:

   ```sh
   uv run pytest -m "not live"
   uv run python scripts/audit_submission.py --history
   ```

2. Report failures grouped by test file, with the first assertion message for each.
3. Never run held-out or sealed sets from this skill. They run only through the logged schedule.
