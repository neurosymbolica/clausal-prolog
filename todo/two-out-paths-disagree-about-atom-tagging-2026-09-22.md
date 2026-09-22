# Two Python out-paths disagree about what an atom looks like

Filed 2026-09-22 by engine-lane from the downstream lane's finding; behaviour
is AS DESIGNED on each path, the question is whether the pair is.

* `--` / `clausal.logic.seam.export()` is THE out boundary (spec 2026-09-21):
  an atom leaves as `atoms.atom` (a `str` subclass), a string as plain `str`.
* `solve(goal, module=m)` yields a Trail; a caller that `deref`s a Var gets
  TERM-SPACE values: an atom is a plain `str`, a string is the carrier tuple.

A Python body that uses both (17 downstream bodies did) cannot write one
local "is this an atom" test that is right on both: `type(v) is str` is right
for solve+deref and wrong for export; `isinstance(v, atom)` the reverse. The
downstream checks resolved it by ruling ALL-SOLVE and dropping the `--` form (119 sites).

Open question for the operator, parked: should the Python-facing `solve`
path ALSO tag (i.e. is the out boundary "wherever a value reaches Python", as
`export()`'s docstring argues, or "only through `--`")? If the former, `deref`
at the Python API needs an exporting twin and the seam docstring's "this is
the one place" is the contract to keep. If the latter, document that a
`solve` caller is in term space and must not mix with `--` values. Nothing to
build until ruled; the downstream checks no longer depends on the answer.
