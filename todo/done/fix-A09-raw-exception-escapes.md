# fix(A09-F012): raw Python exceptions escape builtins (IndexError/TypeError/ValueError)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F012
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F012_* (xfail — flip to pass), ::test_F012_regression_sort_by_incomparable_keys
**Gated by:** A09-D002. Cross-refs: pairs half also in fix-A09-pairs-malformed-pairs.md.

## Bug

Sites that raise raw Python exceptions through the engine (uncatchable by
catch/3, kill the whole query):

- pairs.py:16-17, 39, 52 — `deref(p)[1]` on a 1-element pair → IndexError.
- dict_set.py:140-160 (`dict_pairs` construct), 356-363 (`set_list`),
  set_add/set_remove — unhashable key/element → TypeError.
- arithmetic.py:337 — `pow(base, -1, mod)` non-invertible → ValueError.
- higher_order.py:404, 441 — max_by/min_by `k > best_key` on incomparable
  keys → TypeError, while sort_by (369-371) catches it and falls back —
  pick ONE behaviour.

Model: sum_list/max_list/min_list (lists.py:602-683, F052) — catch and
re-raise as typed `LogicException(type_error(...))`.

## Fix direction

Wrap each site per the F052 pattern (type_error("pair",...),
type_error("hashable",...)/domain_error, evaluation_error("undefined") for
exp_mod, type_error("orderable",...) for max_by/min_by — and make sort_by
consistent with the decision).

## Acceptance

- All F012 xfails pass; catch/3 can intercept each error; happy paths
  unchanged.
