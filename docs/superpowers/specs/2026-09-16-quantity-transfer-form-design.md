# The quantity transfer form — design

Date: 2026-09-16. Approach approved by the operator in session ("approach 1, go ahead").
Scope ruled the same day: **core only**, built **on `feat/iso-l3-lowering-2026-09-14`**.

This document builds what `2026-09-14-retire-predicatemeta-section4-answer.md` §§2–5 RULED.
It restates nothing that document settles; it says where the ruled shape lives in code, what
mechanism keeps the seam ruling true, and what is deliberately not built.

---

## 1. What is being built, in one paragraph

A quantity is a Python object at runtime (ruled 2026-09-15). For the boundaries that cannot
carry an object — subinterpreters, process boundaries, `.pyc` bytecode caches — it has a
functor-first **transfer form**, `quantity(Magnitude, unit(Ratio, Dimensions))`. This design
adds (a) the conversion both ways, marshal-clean, in `clausal/logic/python_terms.py`; (b) a
`Fraction` transfer form, `rdiv(N, D)`, because a divided money quantity has a `Fraction`
magnitude and the magnitude must convert too; and (c) the explicit relation
`quantity_number/2` in `clausal/modules/units.py`. None of those boundaries has a consumer in
the tree today; **this builds the encoding, not the plumbing.**

## 2. The mechanism: a transfer layer BESIDE the seam registry, not inside it

### 2.1 The constraint

The ruling is that a same-interpreter seam **passes the object**. The existing registry
(`TO_TERM` / `FROM_TERM`) is the seam's registry: `clausal/modules/py/datetime.py` reads it
through a scope-narrowed wrapper, and harness-batch-lane has measured a `++` hook that would
convert every non-tuple entry in it (their handoff of 2026-09-16, §6 — kept for engine-lane's
use). Registering `Quantity` there would make that hook, or the next widening of the date
wrapper, convert quantities at the seam and break the ruling silently. A `Fraction` entry is
worse: the engine has no arithmetic on an `rdiv` term yet (§ "rdiv/decimal" of the section-4
answer: sequenced with the CLP(Q) C port), so money divided by three crossing a seam as a term
would stop computing and the goal would just stop holding.

### 2.2 The shape

Two more tables and two entry points in `python_terms.py`:

    TO_TRANSFER:   dict[type, fn]      Quantity, Fraction
    FROM_TRANSFER: dict[str, fn]       'quantity', 'rdiv'

    to_transfer(value)   consult TO_TRANSFER by exact type; otherwise to_term(value, strict=True)
    from_transfer(term)  consult FROM_TRANSFER by functor;  otherwise from_term(term)

    register_transfer(cls, functor, to_fn, from_fn)   same no-override rule as register()

The fall-through is what makes dates and decimals INSIDE a quantity free: a `Decimal`
magnitude converts through the seam registry's existing `('decimal', M, S)` entry, and
`to_transfer` is what the quantity converter calls on its own components, so a quantity holding
a `Fraction` gets `rdiv` and one holding a `Decimal` gets `decimal`, from one dispatcher.

`to_transfer` does NOT apply the engine-owned-type guard that `to_term` applies — that guard is
exactly what makes the seam pass a `Quantity` through, and a transfer is the one place the
object must NOT pass through. `to_transfer` still refuses a logic variable: converting a `Var`
is destructive on every path.

**The seam functions are not edited.** Two tests pin the ruling from the seam's side:
`to_term(q)` returns the same object, `from_term(('quantity', …))` returns the tuple unchanged.

### 2.3 Why not the alternatives

* *Reorder `to_term` so the registry beats the engine-owned guard, and register there.* Fewer
  lines; but the seam would then convert quantities the moment anything consults the registry,
  and the ruling would be held only by the accident that nothing does today.
* *A transfer-only flag on `register()`.* Same effect as this design, but every lookup site has
  to remember the flag — the per-site branch the section-4 answer §4 warns against.

## 3. The encoding, as code will emit and read it

All from the section-4 answer §2–§4; repeated here only so the plan's tests can be checked
against one table.

| thing | term | wire tuple |
|---|---|---|
| a dimension | `metre(1)` | `('metre', 1)` |
| dimensions, N ≥ 1 | `dimensions(metre(1), second(-2))` | `('dimensions', ('metre', 1), ('second', -2))` **sorted by atom on emit** |
| dimensionless | the atom `dimensionless` | `('dimensionless',)` |
| a unit | `unit(Ratio, Dimensions)` | `('unit', R, Dims)` — always `unit/2` |
| a quantity | `quantity(Magnitude, Unit)` | `('quantity', M, U)` — always `quantity/2` |
| a rational | `rdiv(N, D)` | `('rdiv', N, D)`, `D > 1`, lowest terms, sign on `N` (a `Fraction` with denominator 1 is already an `int` at construction) |

Magnitude and ratio are **number terms**: an `int` or `float` passes through, a `Decimal` is the
seam registry's `('decimal', M, S)` (or an `int` when it has no fractional digits — ruled
52ab6b30, and it changes nothing here because the object compares by value), a `Fraction` is
`('rdiv', N, D)`.

**Emit** (`Quantity` → term): magnitude `= q.value` converted; unit `= ('unit', 1, dims)`.
The ratio is ALWAYS 1 on emit — the object has no ratio slot (section-4 answer, "THE RATIO SLOT
IS ASYMMETRIC"). Dims: `('dimensionless',)` when empty, else `('dimensions', *sorted pairs)`.
Sorting is a boundary step, not an invariant: the stored dict is order-insensitive and the
sort exists so an emitted term is one term.

**Read** (term → `Quantity`): `Ratio` and `Magnitude` come back through `from_transfer`, the
product is taken through `Quantity._num_pair` so Decimal × int and Fraction × Decimal stay
exact, and the object is built as `Quantity(product, dims_dict)` with `dims_dict` keyed by atom
— which is what `atom_keyed_dims` and the currency path already accept. Read is
order-insensitive in the dims slot; `('dimensions', ('second', -2), ('metre', 1))` reads to the
same object as the sorted spelling.

**One helper owns the two-functor dims slot.** `_dims_to_term(d)` and `_dims_from_term(t)`
are the only places that know the slot carries `dimensions/N` OR the atom `dimensionless`. The
section-4 answer §4 records this as the cost of choosing the existing word, and asks that it be
said once, not branched per site.

**Marshal-clean is a test, not a claim.** Every emitted transfer term round-trips through
`marshal.dumps`/`loads` to an equal term, and the positive control is that `marshal.dumps` of
the OBJECT raises. The three spec examples — `5 kilometre`, `1550.00 euro`, `3 percent` — are
the fixture, plus a divided money value for `rdiv` and a two-dimension value for the sort.

## 4. `quantity_number/2`

    quantity_number(QuantityTerm, Number)

In Clausal, `Number` is the quantity OBJECT (ruled §5). A units predicate of arity 2 in
`clausal/modules/units.py`, registered beside `make_quantity/3` with the same
`_UnitsPredicate` + `_simple_to_trampoline` pattern, so it is reachable exactly where
`make_quantity` is.

| mode | behaviour |
|---|---|
| `(-Term, +Object)` | `Term` unifies with `to_transfer(Object)`. Ratio 1. |
| `(+Term, -Object)` | `Object` unifies with `from_transfer(Term)`. Ratio multiplied through. |
| `(+Term, +Object)` | build from `Term`, unify the two objects: value equality, so a written `5 kilometre` equals the `5000 metre` object, and `300 basis_point` equals `3 percent`. |
| `(-, -)` | `instantiation_error`, context `quantity_number/2`. |
| `Term` bound but not a well-formed quantity term | `type_error(quantity, Term, "quantity_number/2")`. Raised, never a quiet failure — a malformed term that failed silently would be the "goal just stops holding" shape. |
| `Term` bound to a `Quantity` OBJECT | treated as the object itself (`from_transfer` passes an engine-owned object through). Cheap, and the alternative is a trap. |
| `Object` bound to something that is not a `Quantity` | plain unification failure (no error): the relation does not hold. |

Errors use `clausal.logic.exceptions.type_error` / `instantiation_error` wrapped in
`LogicException`, the convention the list builtins already use.

**The other dialects' half is not here.** For a Prolog with no units, `Number` is the magnitude
scaled to the standard unit for those dimensions, i.e. `Magnitude × Ratio` with the unit
discarded. CORRECTED 2026-09-17 (iso-export-lane): the per-dialect preludes
(`clausal/tools/prolog_preludes/clausal_constants_{scryer,trealla}.pl`) are in THIS tree, and
the exporter stages COMPANIONS, so the definition's home is the `units` companion on the export
side — an exported domain reaches it through the module it already imports. Built there
2026-09-17 as ONE portable file (`Magnitude * Ratio`, never a division; `is/2` on purpose,
since `#=` would pull integer-only clpz into every unit-bearing domain), ten tests on both
engines. Known loud gap: a `decimal(M, S)` magnitude is not evaluable there and raises
`type_error(evaluable, decimal/2)` — right while nothing emits one. This design gave the
reference semantics; the plan did not touch the export side.

## 5. Where things live

| file | change |
|---|---|
| `clausal/logic/python_terms.py` | `TO_TRANSFER`, `FROM_TRANSFER`, `register_transfer`, `to_transfer`, `from_transfer`; the `Fraction` entry; the dims-slot helper pair; module docstring gains a TRANSFER section stating the seam ruling |
| `clausal/terms.py` | nothing structural. The `Quantity` converters are registered from `python_terms.py`, importing `Quantity` lazily inside the functions (`python_terms` must not import `clausal.terms` at module load — `terms.py` is imported by everything and a cycle here would be found by the first import of `python_terms`, i.e. by `py.datetime`). |
| `clausal/modules/units.py` | `quantity_number = _UnitsPredicate("quantity_number")`, arity 2, `_quantity_number_impl` |
| `tests/value_terms/test_quantity_transfer.py` | new: encoding table, round trips, marshal, sort, order-insensitive read, ratio-through-read, `rdiv`, the two seam-unchanged pins, no-override |
| `tests/test_units.py` (or a new `tests/test_quantity_number.py`) | the seven modes of §4 through the engine (`solve`), not through Python calls |

The `_unit_registry` is not touched: the transfer form carries dimensions and a ratio, never
unit metadata, by ruling §3.

## 6. Gate

Built on the feature branch, whose baseline is red (144–145 failures, per the branch's own
handoffs — regenerate, never trust the number). A failure-set diff is blind to what its baseline
already contains, so the gate is:

1. Before the first edit: the failure SET of the full suite on the branch tip, AND the list of
   already-red tests in every file this design touches (`tests/value_terms/*`,
   `tests/test_units*.py`, `tests/test_quantity*.py`, `tests/test_currency*.py`). That second
   list is the blind spot, enumerated. If a red test sits in a touched file, it is run alone and
   its reason recorded before the work starts.
2. After: failure-set diff, NEW must be 0; the new test files pass; pytest's own exit status is
   propagated and the run logs `TREE-SHA` / `IMPORTED` / test count (a run of zero tests is a
   failure).
3. `test_funnel_lint` runs alone, since an insertion in `terms.py` (none planned) or a new
   allowlisted site trips it.
4. No domain axis. Nothing on the seam changes, `quantity_number` has 0 corpus mentions
   (measured 2026-09-16), and no corpus site can reach the transfer layer.
5. roborev review of the branch range.

## 7. Not built, and why

* **Consumer plumbing** — no subinterpreter, process, or `.pyc` path exists; building one is a
  separate design with its own or-parallelism questions.
* **The compiler reading `quantity(…)` written in `.clausal` source into an object** (§6 of the
  section-4 answer says MAY). Ruled out of this plan's scope by the operator, 2026-09-16.
* **The exporter's Prolog-side `quantity_number/2`** — another lane, another repo.
* **A third object slot so a quantity round-trips the unit it was WRITTEN in** — not ruled; the
  section-4 answer records it as the only open item and this design does not pre-empt it.
* **Arithmetic on `rdiv`/`decimal` terms** — sequenced with the CLP(Q) C port by ruling.
* **Any change to `to_term`, `from_term`, the seam registry's entries, or `py/datetime.py`** —
  the date migration measures against those, and this design's whole point is that the seam is
  untouched.

## 8. Interaction with the date migration (harness-batch-lane)

Their work is corpus-side crossing sites in another repo; they never edit the engine, and their
harness reads the registry only through `date_term_to_python`. This design adds no entry to the
tables that function reads, changes no seam behaviour, and produces no term a harness can
receive (a quantity comes back from `solve` as an object, as today). The one shared file is
`python_terms.py`, which they cite by commit (`f74d0f61`, the `++` revert) but do not edit; the
edits here are additive and leave every existing line in place, so a later cherry-pick of their
`++` hook proposal applies cleanly and, because it converts only entries in `TO_TERM`, still
does not touch quantities.
