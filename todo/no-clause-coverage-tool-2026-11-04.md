# No clause coverage, trace or port counts

**Status: open (idea).**

Clausal has no `trace/0`, no `spy/1` and no per-clause port counts. The only
tracing is the failure-trace diagnostics, which run after a failed `test/1`
(`clausal/testing.py`). Profilers in `benchmarks/` report only per predicate
(one Python function per predicate).

Coverage-guided test generation for rulebases needs to know which clauses and
which body goals ran.

## What works today

Generated predicate code keeps its source line numbers, so Python 3.13's
`sys.monitoring` LINE events give coverage per clause and per goal:

- generated code has `co_filename == '<template>'` and
  `co_qualname == '<name>__<arity>'`;
- `frame.f_globals['__file__']` is the source file;
- the line number is the source line.

How to read the events:

- **Clause entered:** the line of its first body goal fires. The head line and
  the last line fire for every clause tried.
- **Clause exit:** this is not visible, because the last body line also holds
  the undo code.
- **Facts:** these give no per-fact signal.
- **Noise:** line 1 (synthetic scaffolding) and lines past the end of the file.

## Possible work

- A small supported API, for example `clausal.coverage`, that records clause
  entry, goal reach and clause exit from the existing line positions.
- A distinct position for each clause's exit, so that success is visible.
- Per-fact counts for fact tables.
