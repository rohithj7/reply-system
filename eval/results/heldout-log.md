# Held-out and sealed run log

Append-only, written by `doctours-reply eval --log-entry <row>` before the run starts. Each schedule row in `src/doctours_reply/evaluation/schedule.py` has at most one current entry. `--void-previous "<reason>"` marks an earlier entry void for an infrastructure failure and never deletes it.

| # | date | purpose | set | set sha256 | systems | config sha256 | git sha | prereg sha256 | status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-04 | phase2-s0-baseline | heldout_v1 | 667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464 | baseline | 44b5296684736d8028e3138ea68c4011eff43ef99bfd90149ede04d9d562e0b1 | 3721b5e848406747eb9507e8482dacb03a031997 | dd95bd901b5e54cce701edbcc4c136bb1b0ddbfbf4984dbdd080b234a4a55847 | valid |
| 2 | 2026-10-04 | phase3-s0-vs-s1 | heldout_v1 | 667c618260abec2e0d3d0f730d4bc6536793a3a83e3412e8c0456e75f48c8464 | baseline,modular | 14131c9416df40312b23e3a14ebfcea55de5fedeee9b1bb9c53b81d1364e94b7 | 1e646b6f6b1b23b026cc586e7d95ac742cb30c2e | 1d9249154affc12d86d06a9927148ebb98746914605982ccee1a794a3293a500 | valid |
