# pl_parity: signal and process edges (low)

Found reviewing `clausal/tools/pl_parity.py` at 04dc0921. None of these can hide a result: a bad row goes red.

- **A slow probe mislabels a timeout as a crash.** If a probe stalls more than about 4 s past a call's deadline, the call child's SIGALRM backstop fires first. The row then reads `crash: signal 14` instead of `timeout` and gets no retry. Fix: map SIGALRM to "timeout" in `_isolated`.
- **Ctrl-C no longer reaches the probes.** Each probe runs in its own session, so a terminal Ctrl-C misses them, and the non-timeout path never kills the probe's group.
- **`communicate()` after the group kill has no bound.** It would hang if a descendant left the group while holding the pipes. None does today.
- **The probe itself has no time limit.** If the parent is killed, the call children end through their backstop, but the probe has none of its own.
- **No test covers `--update` retrying timeouts.** The behaviour was verified by a stub only.
