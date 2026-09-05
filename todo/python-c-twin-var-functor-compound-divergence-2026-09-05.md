# C twins visit a `Compound`'s Var functor slot; Python twins don't — pre-existing, needs an owner

Found during P3-2 Task 2C (2026-09-05), while building the corpus that pins
`c_copy_term`/`c_collect_vars`/`c_is_ground` against their Python twins.
Pre-existing (predates cells and this phase entirely — A01-F003), not a cell
question, and deliberately NOT fixed as part of Task 2C (fixing it would be a
non-cell answer change, exactly what this phase's parity invariant forbids).
Ledger: "Needs an owner — surface at close-out (todo)."

## The divergence

`Compound(functor, args)` can have an UNBOUND `Var` as its functor (a
higher-order construction the class representation happens to allow, even
though ISO forbids it as a functor in general). `term_variables`/`copy_term`
disagree on whether that functor Var counts as "a variable of the term":

```python
f = Var()
term = Compound(f, (1, 2))

_collect_vars_py(term, result)   # -> []      (walks term.args only)
_c_collect_raw(term, result)     # -> [f]     (also visits the functor slot,
                                  #             per A01-F003)
```

`c_is_ground` and `_is_ground_py` DO agree here (both correctly reject a
non-str functor as non-ground), so only the copy_term/collect_vars pair
diverges — `is_ground` was fixed for this case at some point in the past
(A01-F003), `copy_term`/`term_variables` were not.

**The cell analogue has no such split**: both twins walk slot 0 uniformly —
`_collect_vars_py((f, 1, 2), ...)` and `_c_collect_raw((f, 1, 2), ...)` both
return `[f]`. This divergence is specific to the `Compound` class
representation's separate functor/args fields; a cell has no separate functor
slot to disagree about.

## Why it's parked, not fixed

- Fixing either twin to agree with the other changes the answer of
  `term_variables(Compound(Var(), 1, 2))` / `copy_term` over a `Compound` with
  an unbound functor — a real behavior change, unrelated to cells, outside
  every P3-2 task's authorized scope (Task 2C's C changes were scoped
  narrowly to giving the three walkers a TUPLE branch, not to auditing their
  existing `Compound` branches).
- It is pinned, not silently left: `test_a_var_functor_compound_is_a_known_twin_divergence`
  (`tests/test_python_fallbacks.py:750`) asserts both sides of the divergence
  explicitly, plus the cell-analogue's agreement, so any future fix (in either
  direction) has to touch this test consciously rather than by accident.
  `_KNOWN_COMPOUND_FUNCTOR_DIVERGENCE = {"compound_var_functor"}`
  (`tests/test_python_fallbacks.py:535`) excludes the shape from the
  corpus-wide "twins must agree" parametrized check for the same reason.

## Extend the pin: the copy-side divergence is invisible to the corpus (2026-09-05 addition)

A related note recorded during Task 2C's own fix rounds (ledger: "copy-side
functor divergence of the pinned Compound-Var-functor twin split is invisible
to both corpus assertions"): the existing pin above exercises `collect_vars`
only. The equivalent question for `copy_term` — does `c_copy_term` rebuild a
`Compound`'s functor slot when it's an unbound Var (producing a FRESH copy of
that Var), while `_copy_term_py` leaves the original functor Var shared? — is
not asserted anywhere. Extending
`test_a_var_functor_compound_is_a_known_twin_divergence` by two lines (call
`inspection._c_copy_term_impl`/`_copy_term_py` on the same `Compound(f, (1, 2))`
term and assert whatever the two actually do, matching or diverging) would
close that blind spot without deciding the underlying design question — it
only makes the CURRENT behavior visible, the same way the existing two
assertions do for `collect_vars`.

## Where to look

- `clausal/logic/variables/_variables.c` — `c_collect_vars`'s `Compound`
  functor-visiting branch (search "A01-F003").
- `clausal/logic/builtins/inspection.py` — `_collect_vars_py`/`_copy_term_py`
  (imported by the test as shown above) — the Python twins that only walk
  `term.args`.
- `tests/test_python_fallbacks.py:520-535` (corpus exclusion),
  `tests/test_python_fallbacks.py:750` (the pin) — extend per the section
  above when this is picked up.
- `.superpowers/sdd/p32-cell-default-flip/task-2c-report.md` — Task 2C's own
  record of finding this while building the corpus.
