# `-dynamic(f/N)` beside `f/M` clauses moves the class onto the wrong row

Found while measuring the P1 reroute sites (2026-09-17). **Pre-existing** —
reproduced identically against the commit before that work, so nothing in P1
caused it.

## Reproduce

```
-dynamic(d/2)
d(1),
```

```python
m = _load_module("z", "z.clausal")
cls = m.__dict__["d"]          # <Predicate d/1 ...>
cls._row.key                   # ('d', 2)   <- the class moved onto d/2's row
call("d", Var(), module=m.__dict__["$module"])
# TypeError: d__2() missing 1 required positional argument: 'trail'
```

The name's class has ONE field, its clauses are `d/1`, and `db._clauses` holds
them under `('d', 1)` — but the class ends up bound to the `('d', 2)` row and
therefore answers with `d/2`'s dispatch, so **every call to `d/1` raises**.
`-dynamic(d/1)` alone is healthy (`answers == [1]`); adding a declaration at
any other arity breaks it, in either order.

## Where it is NOT

`compiler_v2` step 4a (the `-dynamic` seeding loop) declines correctly: its
membership test is arity-checked against the class's own arity, so it sets
`pending[('d', 2)] = None` and binds nothing. The move happens later, and the
suspect is `compiler/predicate.py`'s "resolve `pred_cls` by name if not
passed" — the arity-blind `module_dict` lookup that is P4's row 900/1025/1734/
1849 in `tools/predmeta_census/P1_SITES.tsv`. Confirm before fixing.

## Why it matters to P4

This is the defect P4's reroute is supposed to make impossible: one class per
NAME, resolved without an arity, handed to `_bind_row(db, functor, arity)`.
A fix landed on the P4 site would close it structurally; a spot fix here would
not.

## Exit criterion

`-dynamic(d/2)` beside `d(1),` loads and `d/1` answers `[1]`, with `d/2`
declared-and-empty. Test lives beside
`tests/predmeta_p1/test_p1_sites_rerouted.py::test_the_ordinary_dynamic_predicate_still_answers`,
which is the positive control for the healthy shape.

## Resolved (2026-09-24, branch fix/small-todos-batch-2026-09-24)

Confirmed the suspect: the arity-blind resolve-by-name in
`compiler/predicate.py` (four sites) handed d/1's class to d/2's `_install`,
whose unauthorized `_bind_row` moved it (same database, so not policed). Fixed
at `_install`, not at the P4 sites: a class already on this database's row at
another arity is not re-bound and gets no dispatch written onto it. Exit
criterion met: `d/1` answers `[1]`, `d/2` is declared and empty. See
`todo/done/zero-field-class-bound-to-another-aritys-row-crashes-call-2026-09-24.md`
for tests.
