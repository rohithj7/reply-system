---
name: policy-change
description: Change a runtime policy module under src/doctours_reply/policies/ safely. Use when adding, editing or removing a policy module or a policy-set overlay.
---

# Policy change

1. Edit the module and bump `version` in its `+++` front matter. Keep `sources` pointing at packet lines, and add no fixture facts or evaluation text.
2. If an overlay in `resources/policy_sets/` replaces the module, update its `replaces_version` and manifest hash. Otherwise the resolver raises `StaleOverlayError`.
3. Add or adjust the tests for the behavior the module controls.
4. Run the network-free suite:

   ```sh
   uv run pytest -m "not live"
   ```

5. State in the commit message whether retraining is needed. Normally it is not, because policies are loaded at runtime.
