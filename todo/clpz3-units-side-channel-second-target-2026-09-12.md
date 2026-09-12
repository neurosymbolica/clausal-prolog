# CLP(Z3): second target for the units side channel

**Filed 2026-09-12.** Operator's suggestion: the Z3 wrapper is an opaque solver
and the test of whether the side channel is solver-independent.
clausal/logic/clpz3.py routes z3_eq … z3_ge through `_z3_arith_binary(l, r,
trail, op)`; one `strip_for_solver(l, r, ctx, trail)` call before
`clausal_to_z3` is the whole change — `label_z3` binds vars by `unify`, so the
`units_link` hook reattaches units without Z3 knowing. `in_z3` gets the
`in_domain_units` treatment (its bounds are floats/ints; use a Z3 Real sort for
money). `units_clp.py` deliberately imports nothing from clpfd at module level
for this reason. Acceptance: the SI and money clauses of
tests/fixtures/units_clp_side_channel.clausal re-spelled with z3 predicates,
skipped when z3-solver is not installed.

Also on the safety net, not routed: `cumulative/2` (task tuples of
start/duration/resource — two dimensions, time and resource) and
`tuples_in/2` (one var per column; strip per COLUMN, and the relation's
column with it). Both need their own rule rather than `strip_list_for_solver`.
`tuples_in/2` and `cumulative/2` both refuse dimensioned material up front
with `system_error(units_unsupported)` (dimensionless quantities pass as plain
numbers). Expression trees as ELEMENTS of a list builtin
(`sum_([A, 3(metre) + B], ...)`) are not stripped either (old type_error).

The direct CLP(Q)/CLP(R) front ends are not routed either: `clpq.rational/1`,
`clpq.maximize/2`, `clpq.minimize/2`, `clpr.real/1`, `clpr.label/1` … in
clausal/logic/builtins/constraints.py reach `q_eq`/`real_eq` without the side
channel, and `_linearize` answers a Quantity leaf with a raw Python
`TypeError("CLP(Q) requires linear constraints")`. They take the same
`(l, r, trail)` shape as `_z3_arith_binary`; the same one-line
`strip_for_solver` call applies.

**Design question parked 2026-09-12 (user thinking aloud: FD is not the ideal
first target for units, since multiplication, division and conversion factors
turn integers into rationals):** should `sum_/3` and `scalar_product/4` with
rational (sub-unit money) operands post the equivalent LINEAR equation to
CLP(Q) instead of throwing `units_unsupported`? Today `T == A + B` already
takes CLP(Q) exactly, so the refusal only bites the list spellings. Products
of two unknowns are nonlinear and belong to Z3 either way.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.

## Unfinished low-priority review findings (rounds 12–21), parked here 2026-09-12

- The units flag (`clausal/logic/_units_flag.py`) is per PROCESS and one-way:
  importing any unit module turns the side channel on for every later
  comparison post. Measured indistinguishable from baseline, but a per-query
  or per-module gate would make the "pays nothing" claim exact.
- `_units_hook`'s var–var branch: when the BARE solver variable is the side
  the unifier binds, its own (C) hook fires instead of the units hook, so the
  refusal for "dimensioned var unified with a bare solver var" arrives at the
  next channel use (`units_unsupported`) rather than at the unification.
  Direction-independent refusal needs the FD hook (C) to consult UNITS_KEY.
- Expression trees as ELEMENTS of a list builtin throw `units_unsupported`;
  supporting them means `analyse`/`strip` per element against the shared
  dimension.
- `ground_dims` is the positive-control oracle only; it rejects every
  variable by design.
- Corpus side: exact quotients now print as rationals (`10/3 euro`) and the
  comparators accept quantities they used to refuse. The sealed
  eu/procurement scorers (harness-batch-lane) must be re-run before this is
  promoted to canonical; that is a claim this repo cannot make.
- Round 22 (lows, unfixed): `Quantity._all_finite` checks Decimals only, so a
  non-finite FLOAT reaching `//`, `%` or the Fraction↔float bridge in
  `_num_pair` raises a Python `ValueError`/`OverflowError` (widen the test with
  `math.isfinite`); `reify_fd` skips the side channel when a side is not
  ground, so a dimensional DISAGREEMENT in a reified comparison stays
  undiagnosed (run `analyse` unconditionally, gate only `strip`); an UNBOUND
  bound to `in_domain/3` with a declared target reports a units mismatch
  instead of `instantiation_error`.
