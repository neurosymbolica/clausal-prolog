# JIT indexing + indexing-threshold profiling + user directive

The current argument-indexing pass (`clausal/logic/compiler/arg_index.py`)
runs at compile time and uses static thresholds:

- `_INDEX_THRESHOLD = 4` — minimum clauses before indexing kicks in
- `_JOINT_COVERAGE_THRESHOLD = 0.8` — min fraction of clauses needing
  joint key for Phase 9b

These numbers were picked by hand. They should be validated against
profiling data on representative workloads. If 4 is wrong, lots of
small predicates are either under-indexed (slow) or over-indexed
(bloat + indirection cost).

Three related items:

## 1. Profile the indexing thresholds

Build a benchmark that measures dispatch time for predicates at
varying clause counts (1, 2, 4, 8, 16, 32, 64). Compare:
- unindexed (all-clauses linear scan)
- indexed (groundness-keyed dispatch)

Find the break-even point for typical clauses. Check whether it
differs for shallow vs trampoline, for bound-first vs bound-all
call patterns, and for predicates with high vs low key cardinality.

## 2. User directive for explicit indexing control

Right now the compiler chooses. Users have no way to say:

- "Always index this hot predicate, even if it has 3 clauses."
- "Never index this predicate — I know it'll never be called with
  a ground first arg and indexing is just overhead."

Proposed directive (syntax TBD):

```clausal
-index([append/3 as pos(0), reach/2 as joint(0, 1)])
-no_index([debug_log/2])
```

The analysis phase should honour the directive before falling back to
the automatic heuristic.

## 3. JIT indexing

A bigger idea: delay the indexing decision until runtime. The first
N calls to a predicate record the distribution of ground/unbound
args and bucket keys; after enough samples, rebuild the dispatch
with an index that matches the observed call pattern.

Plausible design:

- Start with the all-clauses fallback (or a very cheap single-arg index).
- Every call increments a counter in the dispatch wrapper. At some
  threshold (say 10k calls), the counter triggers a "recompile with
  better index" step.
- Recompilation uses the recorded call-pattern histogram to pick the
  best indexing plan for this workload.
- Replace the installed dispatch function on the predicate class /
  in the database. The old version lingers only in any still-running
  generators, which is fine (they finish on the old dispatch).

Interacts with the "inline body processing into dispatch" item (see
`todo/inline_body_in_dispatch.md`) — once we know a predicate is hot,
both optimisations become worth applying.

Open design questions:

- Where does the counter live? On the `PredicateMeta` class? In a
  shared thread-local? Atomicity under free-threaded Python?
- Can recompilation happen mid-search, or does it wait for all root
  generators to exhaust?
- How to handle tabled predicates (where the table's state is
  meaningful across calls)?
- Interaction with `-shallow([...])` directive — JIT only makes
  sense in trampoline mode.

## References

- `clausal/logic/compiler/arg_index.py` — current static indexing.
- `implementation_plans/COMPILER_OPTIMIZATION.md` — historic indexing
  design notes.
- `clausal/logic/compiler/README.md` §6 — optimisation overview.
