# Tabling leftovers: a test-only simple wrapper, and NAF scanning the whole table store (A04 minor items)

**Status: open, low priority.** The "minor hardening items" of the
2026-07-05 audit's A04 design file, split out of
todo/done/investigate-A04-parked-design-decisions.md on 2026-10-20 (the
items that still hold; see that file's status line for the closed ones).

## 1. Dead code: the simple tabled wrapper

`make_tabled_wrapper_simple` (`clausal/logic/tabling.py:1675`) and
`_trampoline_to_simple_adapter` (:2199) are referenced only by
tests/test_tabling.py and tests/test_wfs.py. Decide: delete them with their
tests, or mark them as reference implementations.

## 2. `_naf_tabled` scans the whole table store

`_naf_tabled` (`clausal/logic/tabling.py:1325`) still falls back to a loop
over every `table_store` entry (`for (f, a, k), e in table_store.items()`,
about :1399) to find a subsuming complete table. Index by
`(functor, arity)` if a NAF-heavy workload shows it.
