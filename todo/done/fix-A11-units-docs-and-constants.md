# fix(A11-F048/F055/F056/F059): units/imperial docs and constants batch

- F048: docs' and module docstring's own example `mebi * Byte(1)` raises
  TypeError — `Byte` is a Quantity (scaled unit), not callable
  (units.py:218-221, 269; docs/units.md:219, 332-333). Either fix the
  examples to `* Byte`, or (A11-D011 recommendation) give
  `Quantity.__call__(v)` scaling semantics (`Byte(4)` = `4*Byte`) so all
  published examples work and the predicate/constant asymmetry disappears.
- F055: `psi = 6_894.757` and `horsepower = 745.69987` (imperial.py:69,84)
  are rounded; every other constant is exact. Derive them
  (`psi = pound_force.value / 0.0254**2`; hp = 550 ft·lbf/s).
- F056: docs/units.md:47-51 deny `n(imperial_vector)` sugar but `5(inch)`
  works (guarded); the claimed-unsupported `5(kilo)` dies with a raw
  AttributeError from `Quantity.__init__` (terms.py:1536-1550, A01 seam) —
  raise a designed error ("SI prefixes cannot be used as units") and bless
  the imperial case in docs.
- F059: docs/units.md:12,144,150 import `has_units` from `py.units`, which
  does not export it (`has_units/2` is a builtin,
  logic/units_constraint.py:101) — the quick-start ImportErrors on
  copy-paste. Either add a re-export (one line, keeps snippets valid) or fix
  the three doc sites.

**Tests**: test_F048 (xfail + guard), test_F055 (xfail), test_F056 (guard +
xfail), test_F059 (xfail).
