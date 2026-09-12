# CLP constraints carry units via a side channel — design

**Date:** 2026-09-12. **Source todo:** `todo/clp-units-side-channel-2026-09-12.md`.
**Measured on:** clone main `64f04898` (the todo's own commit). Re-derive, do
not quote.

## 1. Problem, as measured

Every `Quantity` inside a CLP comparison raises today. Probe (infix spellings;
`#=` opens a comment on the surface, and infix `==`/`<`/`!=` reach the same
`fd_eq`/`fd_lt`/`fd_ne` functions):

    X == 1550.00(euro) - 50.00(euro)              type_error(integer, Quantity(...))
    X == 1550.00(euro) - Y, Y == 50.00(euro)      type_error(integer, Quantity(...))
    X < 1550.00(euro), X == 3.00(euro)            type_error(orderable, Quantity(...))
    X == 2 * 3(metre)                             type_error(integer, Quantity(...))
    has_units(X, metre), X == 3(metre) + 1(metre) type_error(integer, Quantity(...))
    X != 3(metre), X == 4(metre)                  type_error(evaluable, Quantity(...))

Two sites produce these: the operand guards `_reject_nonnumeric_eq` /
`_reject_nonnumeric_order` (bare Quantity against a Var) and the expression
leaf guard `_unknown_expr_leaf_error` (Quantity inside a tree). Both are
correct refusals for what they were written against — a broken FD var — and
neither is widened by this design.

The workaround in `tests/fixtures/units_clpfd.clausal` is the shape the todo
objects to: constrain bare integers, label, then wrap with unit predicates
afterwards. A value used both to decide and to compute is written twice.

## 2. Goals and non-goals

Goals:

* A quantity, or a variable carrying a `units` attribute, may appear anywhere
  in either side of `== != < =< > >=` (and their `#` spellings).
* Dimensional analysis happens FIRST, in a side channel, on the expression
  trees. Unit mismatch raises before any solver sees anything.
* The solvers receive bare numbers and bare variables only. No solver module
  (`clpfd.py`, `clpq.py`, `clpr.py`, the C cores) changes.
* Units are reattached when the solver binds, so the user's variable ends up
  bound to a `Quantity` with the computed dimensions.
* Money takes the exact route: `Decimal -> Fraction -> CLP(Q) -> Fraction`. No
  float on any money path.

Non-goals (parked, see §9):

* `is/2` with an unbound operand (that is the eval_/is-chain redesign).
* Unit *inference across constraints* posted before any quantity appeared.
* Converting the ground arithmetic path's raw `UnitsMismatch` to the ISO
  term (§3.6) — a separate change with the same target spelling.

## 3. Architecture

```
comparator entry (fd_eq / fd_ne / fd_lt / fd_le, Python and C wrappers)
   │
   ├─ side channel: units_clp.strip_for_solver(l, r, op, trail)
   │     1. scan: any Quantity leaf or units-attributed Var?  no → return None
   │     2. dimension pass: infer dims of every leaf, apply the rule table,
   │        throw system_error(units_mismatch) on disagreement
   │     3. numeric pass: Quantity value → solver number (Decimal → Fraction)
   │     4. shadow pass: united Var → its shadow Var (created on first use)
   │     → returns (l', r') with no Quantity and no units-attributed Var
   │
   ├─ existing guards (_reject_nonnumeric_*), unchanged, on (l', r')
   └─ existing dispatch (CLP(FD) / CLP(Q) / CLP(R)), unchanged, on (l', r')

binding time
   shadow S bound to number n  ──link hook──▶  user var V := Quantity(back(n), dims)
   user var V bound to Quantity q ──units hook──▶ shadow S := to_solver(q.value)
```

One new module, `clausal/logic/units_clp.py`, owns steps 1–4 and the link
hook. `clausal/logic/units_constraint.py` gains the shadow slot and the
reverse direction of the coupling. `clausal/logic/clpfd.py` gains one call
at each of the eight comparator entry points (four Python, four C wrappers;
`fd_gt`/`fd_ge` delegate and need nothing).

### 3.1 Engagement and cost

`strip_for_solver` is called before `_reject_nonnumeric_*`. Its first step is
a walk that returns `None` unless a `Quantity` leaf or a Var with a `units`
attribute is found. That walk is the same cost class as `_is_rational_arg`,
which already walks both trees at every post; plain `int == int` keeps its
existing fast path ahead of everything. When the result is `None` nothing
downstream changes — every existing constraint takes exactly its old path.

### 3.2 Dimension pass

Each leaf gets a dimension:

| leaf | dimension |
|---|---|
| `Quantity` | its `dims` |
| plain number (int/float/Fraction/Decimal) | dimensionless `{}` |
| Var with `units` attribute | the attribute's dims |
| Var with solver attributes (`fd`/`clpq`/`real`) and no `units` attribute | dimensionless — it is already a bare number |
| fresh Var (no attributes) | unknown, to be inferred |

Rule table, one entry per expression node. It is written by hand and
cross-checked against `Quantity`'s own arithmetic (§6, positive control):

| node | rule |
|---|---|
| `Add`, `Sub` | operands equal; result = operand dims |
| `Mult` | result = left + right (exponent-wise) |
| `Div` | result = left − right |
| `Negate` | result = operand |
| `Pow` | exponent ground, dimensionless, int; result = base × n |
| `FloorDiv` | operands equal; result dimensionless (as `divmod/4`) |
| `Mod` | operands equal; result = operand dims (as `divmod/4`) |
| comparator (all six) | sides equal |

Inference runs to a fixpoint: the comparator equates the two sides; `Add`,
`Sub`, `Mod`, `Negate` equate result and operands; `Mult`/`Div` derive any
one of the three from the other two; `Pow` derives base from result when the
exponent is a ground int. Whatever is still unknown after the fixpoint is
**dimensionless** (decision D1). The tree is then checked bottom-up with the
table, and any disagreement throws `error(system_error(units_mismatch), Context)` (§3.6) with the same message
family `Quantity._require_same_dims` uses, so `X == 1.00(euro) +
1.00(usd)` reads exactly like `1.00(euro) + 1.00(usd)` does in `is`.

A fresh Var whose inferred dims are non-empty becomes a **united var**: it
receives a `units` attribute (a `UnitState`) and a shadow. A fresh Var
inferred dimensionless stays a plain Var and goes to the solver as itself.

### 3.3 Numeric pass

`Quantity.value` is replaced by a number the solvers accept:

| value type | solver number | solver |
|---|---|---|
| `int` | itself | CLP(FD) |
| `float` | itself | CLP(R) |
| `Fraction` | itself | CLP(Q) |
| `Decimal` (every currency) | `Fraction(value)` — exact at every scale | CLP(Q) |

The existing `_any_rational` dispatch then routes a `Fraction` leaf to CLP(Q)
under both the Python and the C `fd_eq` (the C implementation calls back into
`_any_rational`). Mixed rational/real inside one constraint keeps raising the
existing `TypeError` from `_check_no_mixed_rational_real`.

### 3.4 Shadow variables and the link

A united var `V` with dims `D` has a shadow Var `S`:

* `V`'s `units` attribute is `UnitState(D, shadow=S)` (new slot, default
  `None`; `__eq__` still compares dims only).
* `S` carries a new attribute `units_link` → `Link(user=V, dims=D)`.
* Both are set with `put_attr`, so creation is trailed and undone on
  backtracking.

The solver only ever sees `S`. Hooks couple the two:

* **`units_link` hook on `S`**, bound to a number `n`: `unify(V,
  Quantity(back(n, D), D), trail)`. Bound to a Var `W`: if `W` has its own
  link to a different user var `U`, `unify(V, U)`; otherwise transfer the
  link to `W`.
* **`units` hook on `V`** (extended), bound to a `Quantity q`: check dims as
  today, then `unify(S, to_solver(q.value), trail)` when `V` has a shadow.
  Bound to a Var `W`: today's transfer/merge, plus: both have shadows →
  `unify(S_V, S_W)`; one has → the other inherits the whole `UnitState`.
  Bound to a plain number: unchanged (dimensionless only).

Re-entrancy is benign: `S` bound to `n` binds `V` to a `Quantity`, whose
hook unifies `S` with `to_solver(n)` — `S` is already `n`, and `unify(n, n)`
is true. The hook order inside `fire_wakeups` is per attribute key and every
hook must succeed, which is what makes the coupling safe: a dims mismatch on
`V` fails the whole unification including the solver's binding of `S`.

### 3.5 Reattachment, `back(n, D)`

The solver's number comes back **as it is**, through `present_number` (an
integral `Fraction` presents as `int`, as everywhere). There is no
conversion to `Decimal` on the way out and nothing raises here:

| unit kind | `back(n, D)` |
|---|---|
| any, incl. currency | `present_number(n)` — `int`, `Fraction`, or the solver's `float` on the CLP(R) path |

A currency `Decimal` on the way in is a notation for an exact rational; the
way out is the exact rational. `1/3` of a euro comes back as
`Quantity(Fraction(1, 3), {euro: 1})` and the caller rounds explicitly with
`money_round/3` at the point it chooses, which is where rounding errors
belong. This needs one widening in `Quantity`: a currency value may be any
**exact number** — `int`, `Fraction`, or `Decimal` — and a `Fraction` is kept
rather than coerced (today `Quantity(Fraction(3, 2), {usd: 1})` raises
`TypeError: cannot coerce`). `float` keeps its `Decimal(str(f))` coercion.
`money_round/3` and the other money builtins accept the exact-number set;
`Decimal == Fraction` and their hashes already agree in Python for equal
values, so `Quantity` equality and dict keys are unaffected.

`Quantity(value, dims_dict)` is constructed with the dims dict, never the
currency predicate, so the constructor's precision check does not fire on an
arithmetic result — the same exemption ground arithmetic has.

### 3.6 Errors — ISO 13211 form

A units mismatch is thrown as a catchable `LogicException` whose term is
the ISO `system_error` shape with the mismatch as its code:

    error(system_error(units_mismatch), Context)

`system_error` is the ISO 13211-1 §7.12.2 category for errors outside the
standard's own list; the implementation-defined second argument carries what
a reader needs: the operator and the two dimension spellings, e.g.
`'(==)/2'` with `metre` vs `second`, or `euro` vs `usd`, using the same
qualified rendering `Quantity._require_same_dims` already produces for
same-named currencies. A new helper `system_error(code, context)` joins
`type_error` / `domain_error` in `clausal/logic/exceptions.py`. The Python
class `UnitsMismatch` is not the surface spelling of anything.

| condition | thrown |
|---|---|
| operands disagree (incl. mixed currencies) | `error(system_error(units_mismatch), Context)` |
| plain number beside a dimensioned operand in `Add`/`Sub` | same (matches `Quantity.__add__`) |
| `Pow` with non-ground / non-int / dimensioned exponent | same (matches `Quantity.__pow__`) |
| genuinely non-numeric ground operand (atom, string, date, …) | unchanged: the existing guards, existing messages, existing tests |

The ground arithmetic path (`is/2` over quantities) still raises the raw
Python `UnitsMismatch` today. Bringing it to the same ISO term is the
obvious follow-up and gets its own todo; it is not folded in here because it
touches every arithmetic builtin's error surface.

### 3.7 What does not change

* `_reject_nonnumeric_eq` / `_reject_nonnumeric_order`: same code, same
  tests. They now see `(l', r')`, which never contains a Quantity, so the
  A12-F002 property (no broken FD var is ever posted) holds by construction.
* `has_units/2`, `strip_units/2`, ground `Quantity` arithmetic, `is/2`.
* Every constraint with no quantity and no united var.

### 3.8 `in_domain/3` and `label/1` on united variables

Both work by the same shadow mechanism and each is one call site:

* `in_domain([X], 1.00(euro), 20.00(euro))`: the bounds go through the
  dimension pass (both sides must agree, and a plain-number bound beside a
  quantity bound disagrees); `X` becomes a united var; the stripped bounds
  are posted on the shadow. CLP(FD)'s `in_domain` keeps its integer-only
  bounds rule, so money bounds route to `in_q` on the shadow and `int`
  quantities to `in_domain`, chosen by the same numeric pass as §3.3.
* `label([X])`: labels the shadow; every solver binding of the shadow fires
  the `units_link` hook and `X` is bound to a `Quantity`. `label` itself
  never learns about units.

### 3.8a The other FD builtins, and the safety net (review round 1)

The branch review found that every FD builtin outside the comparators
posted on the user's variable directly: `all_different/1` then put FD state
on a united var, `label/1` enumerated the shadow, and the reattachment was
refused by the FD hook — zero answers, no error. Two things fix that:

* **`strip_list_for_solver(items, ctx, trail)`** — the list form of the
  side channel, for builtins whose operands share ONE dimension: every
  known dimension must agree, a plain number or bare solver var is
  dimensionless, a fresh var takes the shared dimension, quantities become
  solver numbers and united vars their shadows. Applied in `all_different`,
  `sum_/3` (summands and value), `scalar_product/4` (coefficients must be
  plain; vars and value share), `element/3` (list and value; index is a
  plain position), `chain/2`, `circuit/1`, `global_cardinality/2` (vars
  and pair keys share); `reify` and `zcompare/3` use the pair form, after
  zcompare's Order validation. List elements must be leaves: an expression
  tree inside a list builtin is a recorded gap (the old type_error, loud).
* **The safety net** — `_link_hook` throws
  `error(system_error(units_unsupported), Ctx)` when the user's variable
  already carries solver state, i.e. some builtin bypassed the side channel.
  `cumulative/2` (task tuples) and `tuples_in/2` (one var per COLUMN, so
  columns carry different dimensions and the shared-dimension list form does
  not fit) are the two FD builtins left on the net; both are loud, not
  silent, and are recorded in the CLP(Z3) follow-up todo as the next call
  sites to route. Dimensionless quantity bounds to `in_domain/3` take the
  plain path; non-integral bounds throw `system_error(units_unsupported)`.

Also from that review: `>`/`>=` strip before delegating so the error names
the operator the user wrote; exponent errors carry their own ISO codes
(`instantiation_error`, `type_error(integer, E)`), not `units_mismatch`;
quantity bounds to `in_domain/3` must be whole units (the plain path's
integer rule), since a CLP(Q)-only domain is not labellable; `Quantity`
gains `//` and `%` with `divmod_/4`'s rule so the positive control covers
those nodes; and `_num_pair` bridges `Fraction`/`Decimal` so a CLP(Q)
money result adds to a Decimal literal exactly.

### 3.8b Rounds 2–4 of the review, in one place

* `circuit/1` refuses united vars (node indices are positions, not
  measurements) and accepts dimensionless quantities as positions.
* `sum_/3` and `scalar_product/4` require whole-unit quantities and throw
  `units_unsupported` otherwise — a finite domain is integers, and the
  builtin's own integer guard would have skipped a `10.50(euro)` silently.
* A declared units var cannot take plain `in_domain/3` bounds (a mismatch),
  and `label/1` throws `units_unsupported` for a declared var that was given
  solver state directly and never shadowed. Together with the `_link_hook`
  net, no bypass fails silently.
* The base of a power is a multiplicative position: a fresh var there
  defaults to dimensionless, and `X ** 0` is dimensionless whatever `X` is.
* `Quantity` accepts a bare `Fraction` in every scalar fast path and has
  `//`, `%` and their reflected forms; `_num_pair` bridges
  `Fraction`/`Decimal`/`float` exactly; the units hook accepts every
  exact/real number for a dimensionless declaration.
* Operator/relation arguments are validated before the side channel runs
  (`sum_`, `scalar_product`, `chain`, `zcompare`), so a bad operator wins.
* Round 5: the whole-units guard lives in the shared list wrapper, so
  `all_different`, `element` and `global_cardinality` are as loud as `sum_`
  for a sub-unit amount; `//` and `%` floor and take the divisor's sign
  whatever the storage type (Decimal's own operators truncate), computed
  exactly through `Fraction`; the C comparator wrappers keep the integer
  fast path ahead of the side channel.
* Round 6: ground `Quantity` division with a Decimal or Fraction operand is
  EXACT — a terminating quotient presents as Decimal, a non-terminating one
  stays the rational — so `1000(yen) / 3` agrees between `is/2` and CLP(Q)
  (int/int and anything with a float keep Python's semantics). The side
  channel is gated on `clausal/logic/_units_flag.active`, set the first time
  a Quantity is built or a units var declared, so a program without units
  never walks a tree; a foreign leaf is a return value of the scan, not an
  exception. `scalar_product` coefficients and `circuit` positions get the
  whole-units guard. The direct CLP(Q)/CLP(R) front ends (`clpq.rational/1`
  and friends) are recorded in the gap todo with the CLP(Z3) call site.

### 3.9 Where units and values meet inside a solver: nowhere

The question is whether a solver ever needs the unit next to the value. It
does not, for two reasons that are both already true of the engine:

* **Every quantity is normalised to its dimension's standard scale at
  construction**, by the unit predicate, before the side channel sees it.
  Measured: `5000(usd_cent)` arrives as `Decimal('50.00')` dollar, and
  `1(kilometre)` arrives as `1000` metre. Minor currency units are scaled
  units of the major unit, exactly as `kilometre` is of `metre`, so the
  major unit is the currency's standard and the side channel never sees a
  penny or a satang. There are no offset units (no celsius) in the vocabulary.
* **The unit systems are coherent.** SI derived units carry factor 1 against
  their base expansion (`newton = kg·m/s²`), and each currency is its own
  single-unit dimension. So a non-linear product of two stripped values in
  standard scale is the standard-scale value of the product dimension, with
  no factor to apply. Propagation, labelling and the simplex all operate on
  standard-scale numbers and stay correct.

Scaling therefore lives only at the two boundaries it already lives at: the
unit predicates scale in when a quantity is built, and scale out when a
value is asked for in a named unit. Reattachment binds the standard-scale
value with the dimension, which is exactly what a `Quantity` is today.

## 4. Behaviour rules worth stating

* **Goal order matters, as it does for every attribute.** `X == Y * Z, Y ==
  3(metre)`: the first goal has no quantity, so `X`, `Y`, `Z` become bare FD
  vars; the second then meets a bare var against a dimensioned quantity and
  throws the units_mismatch term. Declaring `has_units(Y, metre)` first, or posting
  the quantity-bearing goal first, gives the intended reading. This is the
  same rule the ground arithmetic already applies (`2 - 3(metre)` raises).
* **A dimensionless result is a bare number.** `X == D1 / D2` with both
  metre leaves `X` a plain Var bound to a plain number, matching
  `has_units(RATIO, dimensionless)` in the existing fixture.
* **Ground on both sides** goes through the same strip: `1550.00(euro) -
  50.00(euro) == 1500.00(euro)` checks dims, strips, and compares numbers.
* **Scaled units** are already stored in SI base by the unit predicates, so
  `1(kilometre)` arrives as a float metre quantity and takes CLP(R); nothing
  here needs to know about scaling.

## 5. Files touched

| file | change |
|---|---|
| `clausal/logic/units_clp.py` (new) | scan, dimension pass + rule table, numeric pass, shadow creation, `units_link` hook, `back`/`to_solver` |
| `clausal/logic/units_constraint.py` | `UnitState.shadow`; `_units_hook` forwards Quantity bindings and merges shadows |
| `clausal/logic/clpfd.py` | one `strip_for_solver` call at each of the 8 comparator entry points, before the guards; one each in `in_domain` and `label` |
| `clausal/logic/exceptions.py` | `system_error(code, context)` helper |
| `clausal/terms.py` | currency `Quantity` keeps an exact `Fraction` value |
| `clausal/modules/currency.py` | money builtins accept the exact-number set (`int`, `Fraction`, `Decimal`) |
| `clausal/logic/builtins/__init__.py` | import the new module for its hook registration, as `units_constraint` is |
| `tests/test_units_clp.py` (new) | §6 |
| `tests/fixtures/units_clp_side_channel.clausal` (new) | acceptance cases in the surface language |
| `tests/audit_2026_07_05/test_12_seams.py:276`, `tests/test_date_time_ordering.py:201` | the two tests that pin "Quantity against a Var raises" flip to the new behaviour (decision D6) |
| `todo/clp-units-side-channel-2026-09-12.md` | `git mv` to `todo/done/` at the end |

## 6. Testing

* **Rule table positive control.** For a generated set of ground expression
  trees over quantities and plain numbers, the side channel's dims must equal
  the dims of evaluating the same tree with `Quantity` arithmetic, and it
  must raise exactly when that evaluation raises. This is the "extraction"
  the todo asked for, done as a check instead of a derivation.
* **Exactness pinned.** `Fraction(Decimal('0.01'))`,
  `Fraction(Decimal('123456789012345.67'))` round-trip through `back` to the
  same `Decimal`; a float never appears on the money path (assert the type
  at the shadow and at the reattached value).
* **Acceptance (surface language).** Money comparison; money subtraction
  with a fresh result carrying euro; `X < 1550.00(euro)` then binding; mixed
  currencies raise; `!=`; metre/second mismatch raises; inferred units on a
  fresh var; dimensionless result is bare; backtracking undoes the shadow.
* **`in_domain`/`label` on money and metre vars** bind Quantities; a plain bound beside a quantity bound throws the ISO term; `1/3` euro comes back as an exact `Fraction` and `money_round/3` rounds it.
* **Error term pinned** as `error(system_error(units_mismatch), Context)` and caught by `catch/3`.
* **Guard tests stay green** unchanged, plus one new test that a units var
  compared against an atom still raises the existing `type_error`.
* **Suite gate.** Failure SET diff against a baseline regenerated in the same
  tree, per `running-tests-in-bug-fix-clone`.
* **Downstream acceptance.** The todo says one exists on the consuming side
  with a byte-identical reference output. It is not in this repo. **Ask the
  operator for it; do not invent one.**

## 7. Implementation order

1. `units_clp.py` dimension pass + rule table, with the positive-control test
   (pure functions, no engine wiring).
2. Numeric pass and `back`/`to_solver`, with the exactness tests.
3. Shadow + link hook + `units_constraint` extension, unit-tested through
   `unify` directly.
4. Wire the 8 entry points; surface-language acceptance fixture; flip the
   two pinned tests.
5. Baseline diff, roborev review, `git mv` the todo.

## 8. Second target: CLP(Z3), the opaque-solver test of the idea

`clausal/logic/clpz3.py` is a genuinely opaque target: Z3 sees only its own
symbolic constants, and `z3_eq` … `z3_ge` all go through one helper,
`_z3_arith_binary(l, r, trail, op)`. The side channel needs exactly one call
there — `strip_for_solver` before `clausal_to_z3` — and nothing else:
`label_z3` binds Clausal vars by ordinary `unify`, so the `units_link` hook
reattaches units without Z3 knowing they exist. `z3_to_python` already
returns `int | float | Fraction`, which `back` accepts.

This is the check that the design is solver-independent rather than
clpfd-shaped, and it is the natural follow-up once the native path lands.
Not in this task's scope; recorded here so the strip function is written
with a second caller in mind (no clpfd imports inside `units_clp.py`).

## 9. Decisions taken — override any of these (D3–D5 ruled 2026-09-12)

| # | decision | alternative not taken |
|---|---|---|
| D1 | After inference, unknown dims default to dimensionless. Consistent with ground arithmetic, where a bare number beside a quantity in `*`/`/` is fine and in `+`/`-` raises. | Raise "cannot infer units of Y; declare with has_units/2". Stricter, and would make `Total == Price * Qty` need a declaration for `Qty`. |
| D2 | A var that already carries solver attributes is a bare number (dimensionless). | Adopt inferred dims onto it. Would silently change the meaning of an already-posted bare constraint. |
| D3 | RULED by the operator 2026-09-12: the solver's number comes back exact and unconverted; the caller converts to Decimal and rounds explicitly. `Decimal` in, rational out, both members of one exact-number set. | Convert to Decimal / raise on a non-terminating fraction. Overstepping. |
| D4 | RULED by the operator 2026-09-12 (after discussion with Markus Triska): ISO 13211 form `error(system_error(units_mismatch), Context)`, catchable. The ground `is/2` path follows in its own todo. | Raw Python `UnitsMismatch`. A Python programmer's spelling. |
| D5 | `in_domain/3` and `label/1` on united vars are IN scope (§3.8): one call site each, same shadow mechanism. | Defer them. They are what makes the FD path usable end to end. |
| D6 | The two tests pinning "Quantity vs Var raises" flip. A Quantity is numeric to the comparators now. | Keep them, which would mean keeping the todo's problem. |
