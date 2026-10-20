# A tabled predicate over a dynamic, untabled predicate goes stale after assertz (A04-D002)

**Status: open, needs a ruling.** Design decision A04-D002 of the
2026-07-05 audit, split out of
todo/done/investigate-A04-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/design-questions.md.

## Repro (seam, probed 2026-10-20)

```
-table(t/1)
-dynamic(d/1)

d(1),
t(X) <- d(X)
```

`t(X)` gives `[1]`; after `assertz(d(2))`, `t(X)` still gives `[1]`
(a fresh evaluation gives `[1, 2]`). Invalidation is per predicate: an
`assertz`/`retract` on a tabled dynamic predicate abolishes its own table
(pinned in tests/audit_2026_07_05/test_04_runtime_tabling.py::TestTablingGuards::test_dynamic_tabled_assertz_retract_invalidation),
but not the tables that depend on it. docs/tabling.md documents
`abolish_table/2` but does not warn about this case.

## Options (from the audit)

(a) document it loudly and recommend `abolish_table` after changing a
dependency (recommended now); (b) an opt-in conservative mode: any
assertz/retract abolishes every table in the module; (c) invalidate along
the dependency graph (the compiler has the call graph).
