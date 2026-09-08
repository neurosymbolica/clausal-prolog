# Spawn boundaries are absolute leader-stack indices

Raised by the opus review of `fix/wfs-goal-leader-2026-09-08` (2026-09-08,
finding 6). **NOT reproduced** — filed as a reading of the code, not a
measured defect, so anyone acting on it should build the witness first.

`_spawn_ctx.boundaries` holds `len(_leader_ctx.stack)` snapshots, and
`_streaming_consumer_leader` compares a stack INDEX against them. Since
2026-09-08 `seam.judged_answers` detaches its leader segment from the stack at
every yield and re-appends it on resume (so two judged goals alive at once do
not charge each other), which means a stack position is no longer stable
across a judged yield.

CORRECTION 2026-09-08: the companion claim in the goal-position todo that a
3-node mutual-recursion probe "never reached the shape" rests on a probe that
imported CANONICAL clausal rather than the worktree under test (the sys.path
trap in [[running-tests-in-bug-fix-clone]]), so it tested a tree with neither
the `_sources` channel nor the edge forwarding. That result is WITHDRAWN as
inconclusive, not disproven. Rebuild it with
`sys.path.insert(0, os.getcwd())` before drawing any conclusion.

Why it may well be unreachable as written: a spawn drive is synchronous, and
everything SUSPENDED is now detached, so the stack depth below a live boundary
is the same at the yield and at the resume. The shape to try is a `--` goal
reached from inside a spawned NAF drive, suspended across another judged
goal's whole lifetime.

The review's second half is a real if transient rough edge: `reattach` appends
the detached segment wherever the stack happens to be, while `pop_leader`
removes by identity. On a GC-deferred close of an abandoned judged generator
the segment is appended onto whatever context is running, and only the leader
itself is removed by the following `pop_leader` — the parked tabled frames
come off as their own `finally`s run when the solve generator is torn down
immediately after. Pinned behaviour today:
`test_break_after_the_first_answer_leaves_no_leader_behind` and
`test_a_body_exception_leaves_no_leader_behind`.

Fix directions if a witness is found: record spawn boundaries as the entry
object at the boundary (or a monotonic token) rather than an index, and
restore the detached segment by identity-checked reinsertion.

## Related

- `clausal/logic/tabling.py::_streaming_consumer_leader`, `::_spawn_ctx`
- `clausal/logic/seam.py::judged_answers` (`detach`/`reattach`)
