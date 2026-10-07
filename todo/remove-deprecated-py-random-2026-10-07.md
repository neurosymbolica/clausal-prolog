# Remove the deprecated `py.random` adapter

**Status: OPEN (removal parked; deprecation landed with `library(pure_random)`).**

Filed 2026-10-07, with the pure random library.

Operator, 2026-10-07: "py.random (the existing adapter: global generator,
OS-entropy seeded, set_seed/1) is DEPRECATED: it warns once per process on
first use, pointing at the pure library. It keeps working; removal is a later
todo (file one)."

## What is deprecated

`clausal/modules/py/random.py` (`py.random`, `random_mod`,
`library(py_random)`): `float_0_to_1/1`, `float_between/3`,
`integer_between/3`, `choice/2`, `permutation/2`, `sample/3`, `set_seed/1`,
`maybe/0`, `maybe/1`. Its first call in a process warns with
`clausal.lint_warnings.ClausalPyRandomDeprecationWarning`. The replacement is
`clausal/modules/pure_random.py` (`library(pure_random)`, docs
`docs/pure_random.md`).

## To remove it

- Delete `clausal/modules/py/random.py`, regenerate the facades (that drops
  `clausal/library/py_random.seam` and its `_py_facades.py` entry), drop the
  `random_mod` alias in `clausal/templating/term_rewriting.py`.
- Delete `docs/random.md` and its nav and index rows; update
  `docs/importing_prolog.md` (the `py/random` row and the list of six `py_`
  facades).
- Tests that use it: `tests/test_random_module.py`,
  `tests/test_py_adapters_domain_error.py`,
  `tests/test_call_runs_special_form_cells.py` (+
  `tests/fixtures/call_special_forms_re.seam`), and the warning test in
  `tests/test_pure_random.py`.
- Keep `ClausalPyRandomDeprecationWarning` (a public 1.x class per
  `docs/public-api.md` §1.6) until a major release.

## Open questions

- When? The CHANGELOG's other 1.0 deprecations are "removed in 2.0". Whether
  a `py.*` adapter is inside the semver surface needs a ruling.
- `maybe/0,1` and `float_between/3` have no pure counterpart yet. Add
  `maybe(S0, S)`, `maybe(P, S0, S)` and `random_float(L, H, X, S0, S)` before
  removal, or drop them?
