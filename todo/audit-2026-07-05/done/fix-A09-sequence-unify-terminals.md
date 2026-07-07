# fix(A09-F009): sequence//1 Mode A compares terminals with == instead of unify

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F009
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F009_sequence_var_terminal (xfail — flip to pass), ::test_F009_regression_sequence_ground_modes

## Bug

`_sequence__3` Mode A (dcg.py:131-141) normalizes both sides to lists and
checks `s0_pref_norm == lst_pref_norm` with Python `==`. A Var terminal never
equals a char: `sequence([X], "a", S)` fails where it should bind X="a", S="".

## Fix direction

Unify element-wise (mark/undo on failure) instead of `==` — or unify the
whole prefix list (`unify(lst_as_list, s0_pref_norm, trail)`) before unifying
S with the remainder. Keep the str/bytes no-cross-unification guard (list('a')
vs list(b'a') never unify — unify already guarantees that).

## Acceptance

- xfail passes; ground modes A-D regression stays green; bytes/str divide
  preserved.
