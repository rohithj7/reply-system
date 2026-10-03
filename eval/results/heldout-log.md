# Held-out and sealed run log

Append-only, written by `doctours-reply eval --log-entry <row>` before the run starts. Each schedule row in `src/doctours_reply/evaluation/schedule.py` has at most one current entry. `--void-previous "<reason>"` marks an earlier entry void for an infrastructure failure and never deletes it.

| # | date | purpose | set | set sha256 | systems | config sha256 | git sha | prereg sha256 | status |
|---|---|---|---|---|---|---|---|---|---|
