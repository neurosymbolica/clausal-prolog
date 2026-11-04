# No limit/2, offset/2 or resource-limited call/N

**Status: open, needs a ruling.**

When a query runs a rulebase with unbound inputs, nothing on the Prolog
surfaces bounds the search. On e1b23bfb, both `.pl` and `.clausal` raise
`existence_error(procedure, ...)` for each of these:

- `limit/2`, `offset/2`
- `call_with_depth_limit/3`
- `call_with_inference_limit/3`
- `call_with_time_limit/2`
- `findnsols/4`

What does exist:

- `call_nth/2`, `count_all/2` and `once/1`;
- the CLI's `-1` flag;
- `statistics/2` with only `wall_time`, `cpu_time` and `memory`; there is no
  inference counter;
- the quad runner's SIGALRM timeout, which has no CLI flag;
- `test/2`'s `timeout(Seconds)`, which is refused as unsupported
  (`clausal/testing.py`, `PLUNIT_UNSUPPORTED_OPTIONS`).

From Python, `itertools.islice` over `solve()` bounds the answer count, and a
`setitimer` SIGALRM around the loop bounds the time.

## The ruling needed

`limit/2` stops a goal's answers after N. Like `once/1` and `call_nth/2`, that
prunes the search. Decide whether that fits the cut-free design, and if it
does, which of the predicates above to provide, on which surfaces.

A time limit has to interrupt CPU-bound search. The quad runner's repeated
alarm is the existing mechanism; see `clausal/quad_runner.py` and
`todo/python-the-gc-runs-can-still-lose-a-signal-2026-10-25.md`.
