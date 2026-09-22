# rdiv/decimal arithmetic — design session, 2026-09-17

Engine-lane, handoff NEXT item 4: "a design session, not a fix". Inputs: the section-4 answer's
"rdiv/decimal" section (2026-09-14/15), `todo/decimal-term-form-orders-as-a-term-in-compare-and-msort-2026-09-16.md`
(with iso-export-lane's two-engine measurement), the CLP(Q) C-port spec §3.3, and the state of the
engine on canonical `a0e9f0d1`, measured this session. Nothing here is built. The questions that
need the operator are parked in `todo/rdiv-decimal-arithmetic-design-questions-2026-09-17.md`
(clone), each with a recommendation.

## 0. What is ruled, and what the engine does today

Ruled, in date order:

| date | ruling |
| --- | --- |
| 2026-09-13 | arithmetic IS RATIONAL: `{...}` is the default export route, `#=` the narrow integer case |
| 2026-09-14 | dates and decimals are TERMS; a Python object put through raises, and that error stays |
| 2026-09-15 | rationals are `('rdiv', N, D)`, decimals `('decimal', M, S)` (mantissa, decimal places); `('decimal', M, S) == ('rdiv', M, 10**S)` |
| 2026-09-15 | `quantity` goes the OTHER way: a Python OBJECT in the engine (it stands in for a number and must be an operand of `#=/2`), a tuple TRANSFER form for subinterpreters/processes/bytecode only, never the seam |
| 2026-09-16 | the decimal term is first-class; the arithmetic half is sequenced WITH the CLP(Q) C port |

Measured today (canonical `a0e9f0d1`, the venv engine, `clausal.__file__` asserted):

| question | answer |
| --- | --- |
| standard-order band of `('decimal', 99, 1)` and `('rdiv', 1, 2)` | COMPOUND (3); `Decimal('9.9')` and `Fraction(1, 2)` objects are NUMBER (1), ranks 3 and 4 |
| `msort([('decimal',99,1), ('decimal',1000,3)])` | unchanged — mantissa order, silent (the todo's defect, reproduced) |
| `msort([('rdiv',1,2), ('rdiv',1,3)])` | unchanged — WRONG, silent |
| `_eval_ground(('decimal', 99, 1))`, `(('rdiv', 1, 2))` | `type_error` — loud |
| `_eval_ground(Decimal('1.5'))` | **`type_error` — loud, and NEW to this record**: the evaluator refuses a Python Decimal leaf too, so `'is'(X, D + 1)` with a declared-decimal constant raises today |
| `_eval_ground(Fraction(1, 3))` | `Fraction(1, 3)` — accepted |
| `Quantity(Decimal('10.01')) + 1` / `/ 3` | `Decimal('11.01')` / `Fraction(1001, 300)` — the quantity path already does exact division by going to Fraction |
| `Decimal('0.1') == Fraction(1, 10)` (Python) | True — value comparison across the two exact kinds is correct natively |
| `Decimal('1') / 3` (Python) | `0.3333333333333333333333333333` — Decimal division is INEXACT (context precision) |
| seam registry | `Decimal` is registered as a SEAM conversion (`to_term(Decimal('9.9'))` → `('decimal', 99, 1)`); `Fraction` is registered as a TRANSFER conversion only (`to_term(Fraction(1, 3), strict=False)` passes the object through) |
| where a Decimal object arises in the engine | declared decimal constants (`constants.py`), currency/units magnitudes (`units.py`, `currency.py`), never from a source literal (`10.01` compiles to a FLOAT) |
| the standard-order branch | `feat/iso-standard-order-2026-09-09` IS merged into main (memory said not landed); `compare/3`, `@<` and the number ranks live in `_helpers._standard_order_key` and `iso_compare._numeric_tag` |

**The asymmetry the rulings left.** `Fraction`/`rdiv` has the QUANTITY shape (object in the
engine, transfer form outside) and works: arithmetic, CLP(Q), `present_number`, standard order are
all consistent for it. `Decimal`/`decimal` has the DATE shape on paper (a term) and the quantity
shape in fact: every Decimal the engine holds is an object, the cell exists only in the seam
registry, and nothing converts at any crossing (the `++` hook that would have is reverted, then
narrowed to the date family and parked). The decimal ruling (09-14) predates the quantity ruling
(09-15), and the quantity ruling's argument — "it stands in for a NUMBER and must be an operand of
`#=/2`" — applies word for word to the number a quantity wraps.

## 1. The rule that bounds the fix

iso-export-lane measured it in both ladder engines (todo, 2026-09-17): **a term is mis-ordered
by `@<` exactly while it remains a COMPOUND; evaluation moves it into the number region, where
standard order is numeric.** `A is 1 rdiv 2, B is 1 rdiv 3, A @> B` is correct in Scryer and
Trealla; `rdiv(1,2) @> rdiv(1,3)` is wrong in both. Dates order correctly as compounds only because
their components are most-significant-first on one scale; that is a property of dates and does not
generalise.

So there are two honest ways to make the two cells order right: put the cells in the number band
(teach every numeric site to read them as numbers), or never let a cell survive as a compound
inside the engine (lower it to a number at every entry). The first is the "decimals are terms"
reading taken literally; the second is the quantity ruling's shape.

## 2. Options

### A. The cells are numbers everywhere

`('decimal', M, S)` and `('rdiv', N, D)` are the in-engine representation of a decimal and a
rational. Every site that asks "is this a number" must recognise the two cells. Sized this session:

    59 type tests naming int/float/Number/Fraction/Decimal in 14 files (clausal/logic, terms.py,
    modules/), 35 of them in terms.py (Quantity arithmetic);
    6 C files with PyLong/PyFloat checks (_arithmetic_core, _clpfd_core, _clpfd_propagate,
    _tabling_core's do_normalize twin, _list_unify, _variables — unify itself);
    plus: _eval_ground leaves, the compiled arith path (ast.BinOp over native values), number/1,
    sum_list/max_list/min_list/between, CLP(FD/Q/Z3) leaf dispatch, _num_pair, write/writeq/
    format rendering, tabling answer normalisation, iso_compare._numeric_tag, the order key.

Failure mode of a missed site: it reads the cell as a COMPOUND — silent wrong order, or a
`type_error` at best. This is "reading 2, the numeric surface" from the section-4 answer, and it
is also the option that collides with the C port: it changes what a rational IS while `arith_q`
is being rewritten over `mpq`.

### B. Numbers are Python number objects; the cells are transfer forms and source spellings

The engine's numbers are `int`, `float`, `Fraction` (exact rational), `Decimal` (exact rational
carrying a SCALE), `Quantity` (any of those with dimensions). The two cells appear in exactly three
places, and are lowered to numbers at each:

1. **Source.** `decimal(1001, 2)` and `rdiv(1, 3)` written in `.clausal`/`.seam` lower to
   `Decimal('10.01')` and `Fraction(1, 3)` literals at compile time — the same choke point that
   folds a literal `3/2` to `$exact_div(3, 2)`. Never a compound at run time.
2. **The seam (`++`, strict `to_term`).** `Decimal` MOVES from the seam registry to the transfer
   table, beside `Fraction`. The `++` hook then leaves a Decimal alone exactly as it leaves a
   Fraction alone; a Python caller who wants the term form asks the transfer layer.
3. **Transfer** (subinterpreters, processes, bytecode cache): `to_transfer`/`from_transfer` already
   carry both (`quantity/2` wraps them). Marshal-cleanness holds where it is needed.

Standard order needs NO change for objects: `Decimal` and `Fraction` are already in the number
band at ranks 3 and 4, with `compare(=) <=> ==` by construction. What IS missing is the
arithmetic half, and it is small and measured (§0): the evaluator refuses a Decimal leaf, and
native `/` on Decimals is inexact.

This is the quantity ruling applied to the number a quantity wraps; it is how `Fraction` already
works; the ordering defect becomes UNREACHABLE rather than fixed at 59 sites; and the C port's
interface (Fraction or int at the binder boundary, `arith_q` over `mpq`) does not move. What it
does not satisfy is the 2026-09-14 sentence "no Python object in term position" read literally —
but `Fraction(3, 2)` is in term position today by design, and `Quantity` was ruled so. **Parked
question 1** asks the operator to re-align the decimal ruling to the quantity ruling, with this
document as the case.

### C. The guard, regardless of A or B

Make the standard order NUMERIC for the two cells and let `_eval_ground` accept them as leaves —
one branch in `_standard_order_key` (a well-formed `('decimal', int, int)` / `('rdiv', int, int)`
cell keys as its value, rank 3 / 4, before the generic cell branch), the matching branch in
`iso_compare._numeric_tag`, and a leaf conversion in the evaluator. ~40 lines and tests. Under B it
is belt-and-braces (a cell that leaks through some unforeseen route still orders right); under A it
is the first slice. It closes the SILENT half of the todo today and has no dependency on the port.

**Recommendation: B, with C landed first as the guard.** A is priced above; nothing in the rulings
requires paying it, and the quantity ruling suggests the operator would not.

## 3. Arithmetic rules under B (the part that has to be written down exactly)

Kinds and their standard-order rank (existing): float 0 < int 1 < bool 2 < Decimal 3 < Fraction 4
< Quantity 5, at equal value.

* **`+`, `-`, `*`:** Decimal ⊕ Decimal → Decimal (Python semantics: scale of a sum is the larger
  scale, of a product the sum of scales — exact). Decimal ⊕ int → Decimal. Decimal ⊕ Fraction →
  Fraction, exact, scale dropped — the rule `_num_pair` already applies inside `Quantity`. Decimal
  ⊕ float → Decimal via `Decimal(str(f))` — also `_num_pair`'s existing bridge; **parked question
  5** is whether to keep that or raise (ISO mixes to float; the engine has chosen exactness once
  already, in `Quantity`).
* **`/`:** whenever either operand is exact and non-int-float (Decimal or Fraction), the result is
  a **Fraction**, never a Decimal — Decimal division is inexact (§0) and the 2026-09-13 ruling says
  arithmetic is rational. `int / int` → Fraction (exists, `$exact_div`). `Quantity` already does
  this (`Decimal('10.01') / 3` → `Fraction(1001, 300)`, measured). **The compiled path is the
  hazard:** `arith_to_ast_expr` emits a native `ast.Div`, and Python's `Decimal / int` is the
  inexact one, so once Decimal leaves are accepted the compiled `/` needs a `$div` runtime name
  beside `$exact_div` that routes any Decimal/Fraction operand through `Fraction`. Without it the
  interpreted and compiled evaluators would disagree — a fixture that evaluates `D / 3` both ways
  is the positive control.
* **Presentation at binders:** an integral Fraction presents as int (`present_number`, exists). A
  Decimal presents as itself — scale is information (`10.00` is not `10`), and the transfer form
  agrees (`_decimal_to_term` makes an int only when there are NO decimal places).
* **`=:=`, `<`, …:** by value across kinds; Python already compares Decimal against Fraction
  exactly (measured). No change.
* **`==`, `compare/3`:** kinds are distinct (ranks), value first. **Parked question 2:** two
  decimals of equal value and different scale (`10.0` vs `10.00`) — same term or not? The section-4
  answer wrote "distinct terms, same rational value", and ISO's `1` vs `1.0` is the analogue.
  Recommendation: distinct, which means the Decimal order key carries the scale as a third
  component `(value, rank, scale)` and `_numeric_tag` agrees; today `Decimal('1.0') ==
  Decimal('1.00')` is True in Python so the key would collapse them.
* **CLP(Q):** a Decimal entering `{...}` converts EXACTLY (`Fraction(d)` is exact for finite `d`);
  results come back as Fraction or int. A decimal's scale is NOT reconstructed on the way out — a
  CLP(Q) result is a rational; the exporter's "decimal scale lost under `decimal_repr=float`" is
  the same fact seen from outside and is inherent, not a defect. For the C port this is ONE entry
  conversion (numerator/denominator of `Fraction(d)` into `mpq`), a sentence in spec §3.3, and no
  change to its staging.
* **`number/1`, `sum_list/2` and friends:** already accept `numbers.Number` (Decimal and Fraction
  both) — no change; a positive control that the C arithmetic fast path (`_arithmetic_core.c`,
  two Long/Float checks) FALLS THROUGH to Python for a Decimal as it does for a Fraction.
* **Rendering:** `write(Decimal('10.01'))` prints `10.01`. `writeq` of a Decimal or a Fraction has
  no ISO form; the exporter already chooses (`decimal_repr`). **Parked question 3.**

## 4. Sequencing with the CLP(Q) C port

The section-4 answer sequenced the arithmetic half WITH the port because "a rational-representation
change written now would be written against a Python `arith_q` that a parked branch is midway
through replacing". That collision is specific to option A. Under B no rational representation
changes: `Fraction` stays the in-engine rational, the port's binder boundary stays `Fraction`-or-int,
and the only port-facing item is the Decimal entry conversion. So:

* **Independent of the port, can land now, in this order:** C (the ordering guard, closes the
  silent defect); the evaluator's Decimal leaf + the `/`→Fraction rule + the compiled `$div`; the
  registry move (Decimal to the transfer table) with the compile-route lowering of the two cell
  spellings.
* **Coupled to the port:** nothing structural. Add the entry-conversion sentence to the port spec
  when it resumes (its NEXT 1 is the 910-clause annotation commit; this does not touch it).

The port itself is parked at `feat/clpq-c-port-2026-09-13` (11 commits, `arith_q` in C, 20/20 on
the differential, nothing landed); its own resume list is in its handoff and is unchanged by this.

## 5. The `++` hook and the todo's "goes live" trigger

The todo's hazard — "the term appears the moment any `++` auto-conversion that includes Decimal
lands" — is removed by construction under B: with Decimal in the transfer table the hook never
produces the cell, the same way it never produces `rdiv`. the harness lane's narrowed date-only
hook stays correct as is. Under A the hook may convert only after the whole numeric surface is done.

## 6. Gates, before any of it is promoted

* Engine failure-set A/B on a CLEAN base (the branch baseline cannot see what it already
  contains), with a positive control per instrument.
* Anything that moves what `compare/3`, `msort/2` or the evaluator answers for a value the sealed
  bodies handle goes to the harness lane as a QUESTION first — the 82-scorer answer diff, sha
  frozen before asking; they have the reference. Money is live corpus vocabulary, so the evaluator
  change qualifies; the ordering guard for the two cells does not move any answer today (nothing
  emits a cell) but is cheap to include in the same run.
* The units-declaring canary domain (corpus-lane knows which) runs first after any change that
  touches number kinds.
* Tell iso-export-lane BEFORE a decimal term can reach an export. Under B one reaches an export
  only through the transfer form, which their `decimal_repr` dialect already handles, and their
  companion's `decimal/2`-magnitude refusal stays the guard until they lift it; the message is
  still owed when the registry moves.

## 7. Work list under B, sized

| step | what | size | gate |
| --- | --- | --- | --- |
| 1 | C: numeric order key + `_numeric_tag` for the two cells; evaluator leaf conversion; tests incl. the todo's four cases and a leak-control (a cell reaching `msort` still orders numerically) | ~1 day | engine A/B |
| 2 | evaluator accepts a Decimal leaf; `/` → Fraction when an exact non-int operand is present, interpreted AND compiled (`$div`); parity fixture | 1–2 days | engine A/B + harness question |
| 3 | Decimal: seam registry → transfer table; compile-route lowering of `decimal/2` and `rdiv/2` cells written in source; refuse malformed cells loudly | ~1 day | engine A/B; message iso-export-lane |
| 4 | port spec §3.3: the Decimal entry conversion sentence | minutes | none |
| 6 | RULED Q5: float beside Decimal/Fraction RAISES, in the evaluator and in `Quantity._num_pair` (remove the `Decimal(str(f))` bridge) | ~1 day | engine A/B + harness question (money paths) |
| 7 | RULED Q3: measure Scryer/Trealla `writeq` of a rational, then decide | hours | none |
| 5 | if parked question 2 rules "distinct": scale in the Decimal order key and tag | hours | engine A/B |

Not in this list, deliberately: turning `10.01` in source into a Decimal (reading 2 of the
section-4 answer) — that is the literal surface and a corpus migration, **parked question 4**.

## 8. Not established

* Whether the operator re-aligns the decimal ruling to the quantity ruling (Q1). Everything
  above the guard (C) waits on it; the guard does not.
* The population of `'is'(X, <decimal constant> ...)` sites in the corpus that raise today
  (§0's new fact) — corpus-lane's to count; if non-zero, step 2 is a live fix, not latent.
* What Scryer and Trealla print for a rational (`writeq`) — needed for Q3, not measured here.

---

# RULED 2026-09-17 (operator, on the five parked questions)

| Q | ruling | consequence for the design above |
| --- | --- | --- |
| Q1 | **re-align**: the decimal ruling takes the quantity ruling's shape — a Python number object in the engine, `('decimal', M, S)` a TRANSFER form and SOURCE spelling | option B is the design; option A is closed |
| Q2 | **distinct terms, equal value**. They do NOT unify: `=`/2 is syntactic identity on numbers (ISO `1 = 1.0` fails), so `10.0 = 10.00` fails, `10.0 =:= 10.00` succeeds, `10.0 == 10.00` fails, `compare/3` orders by value then scale | the Decimal order key and `_numeric_tag` carry the scale; unification of two Decimals is exact-type-and-scale, and does NOT inherit the engine's int/float conflation (the deferred divergence stays what it is) |
| Q3 | **measure first**, then decide `writeq`; `write` keeps `10.01` | step added: measure Scryer and Trealla's `writeq` of a rational |
| Q4 | **no**: `10.01` in source IS a float, that is ISO | the explicit spellings `decimal(M, S)` and `rdiv(N, D)` are the only way to write an exact non-integer; no literal flip, ever, on this ruling |
| Q5 | **no implicit coercion — raise**. Decimal beside a float is an error; it risks loss of precision | §3's "Decimal ⊕ float → Decimal(str(f))" is REVERSED, and so is the same rule inside `Quantity._num_pair` (it is the same pair): a float beside a Decimal or a Fraction raises a type error. This changes money-path behaviour and goes to the harness lane as a QUESTION before it lands |

---

# Step 1 BUILT and PROMOTED 2026-09-17 — the ordering guard (`e52a3171`)

`exact_cell_number` beside `present_number`; canonical cells key in the number band (marked as the
cell, after their object); `_number_key` carries (scale, cell) uniformly; Decimal left the
native-sort fast path; `'=='` objects to two Decimals of different scale (Q2); an `rdiv` cell
evaluates, a `decimal` cell stays LOUD until step 2. 20 tests, 5 mutation controls all firing (the
first Q2 assertion was vacuous — list `==` ignores Decimal scale — and control 5 caught it).

Gates: engine failure-set A/B on a clean base at `5d53aeea`: NEW 0 / GONE 0 (145 / 145 names,
+20 passed). Harness axis (the harness lane, base AND guard run, .so premise verified by their
own diff): **82/82 unchanged on both, ATTRIBUTABLE for the cell-ordering half; SILENT on
mixed-scale decimal comparison** — their population has 0 bodies mentioning Decimal and 1 rulebase
source of 849, so a clean result there is not coverage of the Q2 behaviour. Recorded as a CONDITION, not a
status (the harness lane's refinement, so it cannot rot into a standing property): **ruled (Q2)
and engine-tested; the closed corpus does not CURRENTLY exercise mixed-scale decimal comparison —
0 of 82 sealed answer-set scorers construct a Decimal — so the harness axis is silent on that half. RE-ASK
the harness lane when a domain compares or sorts money of differing scale** (their trigger: any
sealed body constructing a `Decimal`; one grep, zero today; nobody monitors it).

**Corrected 2026-09-18 (the harness lane, their own correction):** the reason above was
"unmeasured"; the true reason is stronger. The ONE Decimal money-arithmetic site in the closed
corpus is a pure-Python GOLD model that imports nothing from the engine — no engine change can reach
it. So the only Decimal arithmetic in the corpus is structurally unreachable from the engine, and
the 82 sealed answer-set scorers ARE the engine-reaching population, re-derived structurally (their roster tool
classifies every evaluation file outside the 82 by whether it reaches the engine: 92 outside, 5
reach it — unmigrated scorers of unformalised domains with nothing yet to score — 0 genuine gaps,
calibrated on a synthetic gap). The condition stands unchanged; "82 of 82" now means all of them.
Their general lesson, kept: classify a file by what it can REACH, not by what it CONTAINS. Unification of decimals of different scale
is still conflated (C unifier) and rides with the int/float todo.

---

# Step 2 BUILT — the evaluator (`9e30afa9`)

`clausal/logic/exact_arith.py` is the ONE spelling: `exact_add/sub/mul/div`, used by
`_eval_ground` and emitted by `arith_to_ast_expr` as `$add/$sub/$mul/$div` (`//`, `%`, `**` stay
native). A Decimal is a number in the evaluator (finite only); `+ - *` are exact on
`(mantissa, scale)` pairs (a 28-digit product that native Decimal rounds is pinned exact); `/` over
any exact operand is a Fraction, never a Decimal; Decimal ⊕ Fraction goes exact-to-exact as a
Fraction; **Decimal ⊕ float RAISES `type_error(exact_number, Float)` on both paths (Q5)**; a
Decimal enters CLP(Q) exactly; a scale-less Decimal presents as int at the binder (the transfer
form's choke point, applied at the binder). **Runtime `int / int` on the COMPILED path is now
rational** (`7 / 2` was the float `3.5` there and `Fraction(7, 2)` in `is/2` — the parked "eval_
variable-operand float", closed). Cost measured: ~30 ns per compiled operator, ~300 ns per exact
int/int division.

Two LATENT defects the rational compiled division made reachable, fixed and pinned: the four
comparison entries (`== != < =<`, Python twins and C-backed wrappers) refused a ground Fraction
beside a ground float as "cannot mix CLP(Q) and CLP(R)" — a value question, now compared by
exact value ahead of the refusal (`_ground_number_pair`) — in the C-backed wrappers a GROUND
EXPRESSION TREE is folded first (`_resolve`), which the first fix missed and the harness lane's
probe `X / Y == 3.5` caught (two paths, one symptom); and `_expr_tree_has_var` isinstance'd
against still-None lazy node classes on a ground non-var leaf.

Gates: 44 parity/pin tests (every case through `is/2` AND `eval_/2`, same value, TYPE, error), 6
mutation controls all firing; engine failure-set A/B on a clean base at `506596da`: **NEW 0 /
GONE 0** (145 / 145 names, +37 passed) at `df187e1f`. Harness axis (the harness lane, frozen corpus, compiled path asserted on every tree): **82/82
unchanged at 506596da (base), c9a7bfd1, f3c70951 and 9e30afa9**, with TWO positive controls on
the swept trees — runtime `7 / 2` is `Fraction(7, 2)` there against `3.5` on base (the change is
LIVE and moves no scorer answer), and the reported shape `X / Y == 3.5` red at 506596da and
f3c70951, green at 9e30afa9. The c9a7bfd1 run's zero no-score rows is the weak-but-real evidence
the corpus holds no `X / N == 0.5` shape. Limits, theirs, kept: harness axis only; "reproduces
canonical" is not "correct"; single replicate whose error mode is spurious MOVEMENT. The
mixed-scale decimal half stays corpus-unexercised — the CONDITION above, unchanged.

**Their diagnosis, worth keeping:** the defect lived in the GAP between two implementations of one
contract (Python twins fold a ground tree, the C-backed wrappers — the ones actually loaded — did
not), and the tests that pass are the Python ones. The question that finds it: "has the CHANGE
been measured, or the INTERACTION?" — filed as a todo to audit the remaining twin/wrapper pairs.

Not in step 2 (still open): Fraction ⊕ float (a float today; step 6 with the harness question),
`**` with a Decimal base (native), `writeq` of a rational (step 7, measure first), the registry
move of Decimal to the transfer table (step 3), unification of decimals of different scale (with
the int/float todo).

---

# Step 7 MEASURED (2026-09-18): `writeq` of a rational in the two ladder engines

    goal                     Scryer          Trealla
    X is 1 rdiv 3, write     1 rdiv 3        1 rdiv 3
    writeq                   1 rdiv 3        1 rdiv 3
    write_canonical          rdiv(1,3)       1 rdiv 3
    7 rdiv 2 / -1 rdiv 3     7 rdiv 2 / -1 rdiv 3   (both)
    4 rdiv 2                 2               2        (integral presents as int — the engine's rule too)
    rational(X), number(X)   true, true      true, true

Neither engine has a decimal type, so there is no reference for `writeq(Decimal)`.
**Recommendation for Q3 (parked, the operator's):** `write` and `writeq` of a Fraction print
`N rdiv D`, matching both engines; `write` of a Decimal prints its digits (`10.01`, ruled);
`writeq` of a Decimal prints the source spelling `decimal(M, S)`, because `writeq`'s contract is
"reads back as the same term" and the digits read back as a FLOAT (Q4) — the cell spelling reads
back exactly once step 3 lowers it. Nothing built.

# Twin/wrapper audit CLOSED (2026-09-18)

The twin population is exactly the four comparison entries (`propagate` hits are class methods).
`tests/test_comparison_twin_parity.py` runs one 84-case matrix through the C-backed wrappers
in-process and the pure-Python twins in a subprocess with the C propagate module blocked, and
asserts identical outcomes; 0 divergences after step 2's fixes; positive control: the pre-9e30afa9
wrapper (no ground fold) makes the tree case diverge and the matrix sees it.

# Cell operands in compiled arithmetic — FIXED and PROMOTED (2026-09-18, `8f8ab9dd`)

Found while scoping step 3: a spelling written in source (`decimal(1001, 2)`, `rdiv(1, 3)`, declared
`-private`) reaches the COMPILED tree as a cell tuple, and the exact helpers fell to Python's tuple
operators — `eval_(decimal(1001, 2) * 2, R)` answered the tuple REPEATED, `('yes',) * 2` the atom
DOUBLED: a value of the right shape to keep flowing (the harness lane's control, live on canonical
before the fix). The four helpers now normalise a tuple operand: a canonical cell evaluates as its
number (parity with `_eval_ground`'s leaf), any other tuple raises `type_error(evaluable)` on both
paths; the `--` seam maps that to the Python `TypeError` it always raised. Gates: engine A/B on the
canonical-engine baseline NEW 0 / GONE 0; harness 82/82 on base and fix with the control live on
the swept trees — the stronger reading, theirs: no sealed harness performs compiled exact
arithmetic on a tuple operand. This is what makes option (c) of Q7 the engine's current behaviour.

---

# RULED 2026-09-18: Q6 = option C, Q7 = option c

Q6 (the Q4/Q5 collision at the units bridge): **C** — a written float is exact at DECLARATION and
CONSTRUCTION (its digits are the user's), a float beside an exact number at RUN TIME raises. The
operator also floated a per-module `-float_literals(decimal | rational)` read-time directive,
ISO-shaped like `double_quotes`, which would dissolve the collision for modules that opt in; noted,
not ruled, not built. Q7 (lowering the written spellings): **c** — do not lower; `quantity_number/2`
is meant for constants internally, most Prologs ignore units and compute on bare numbers, and the
engine already orders and evaluates a written cell correctly.

# Steps 6 and 3 BUILT and PROMOTED (`42153362`, `fe60e174`, gate fixes `4f0af19b`)

Step 6: the shortest-repr bridge survives only in `Quantity.__init__` beside an exact factor
(`2.5(centimetre)`, `5.25 percent`) and for money; `_num_pair` refuses a float beside a Decimal
or a Fraction (`type_error(exact_number, Float)`); the exact helpers refuse a float beside a
Fraction on both paths; the 13 float-literal SI-fraction factors of the units vocabulary are exact
Decimals built from the literal text (measured physical constants stay floats). Consequence to
schedule: an inline `MONEY * 1.2` in a clause body now raises and migrates to `decimal(12, 1)` or
to a declared constant — corpus-lane's count decides how much.

Step 3 (c): Decimal leaves the seam registry (no engine consumer, measured) and joins the transfer
table beside `rdiv`; Decimal and Fraction are seam SCALARS, so the strict seam passes them as
numbers (it used to refuse a Fraction as unregistered); `to_transfer` consults its table before the
scalar pass-through. Nothing is lowered.

Also taken (`4f0af19b`): `Quantity`'s own `+ - *` go through the exact helpers (one spelling; Decimal
pairs exact beyond 28 digits); a non-finite Decimal keeps Decimal's NaN/Infinity semantics in
quantity arithmetic while the evaluator still refuses it at the leaf. The first A/B's 7 NEW were all
test pins following the rulings — the one that looked real was a test oracle dividing bare ints
with Python's `/` (a float the TEST made, not the engine).

Gates: 19 step-6 tests + 3 mutation controls; value-term tests follow the move; engine A/B on the
canonical-engine baseline at `4f0af19b`: **NEW 0** (GONE 1 = the load-marginal perf test). Harness axis
(the harness lane, sequential, base 053fbdbe and branch 4f0af19b, .so premise re-verified): **82/82
unchanged on both**, with a control behind each mechanism on the swept trees — `2.5(centimetre)`
0.025 → Decimal('0.025'); `5(centimetre)` 0.05 → Decimal('0.05'); compiled `eval_(Q * 1.5, R)`
`quantity(0.07500000000000001, …)` → `type_error(exact_number, 1.5)` (the float error the ruling exists
to remove, sitting in a quantity on the base); `eval_(2.5 * 2, R)` 5.0 both (negative control).
Their readings, kept verbatim: for the refusal, "no sealed harness performs compiled arithmetic
mixing a float with a quantity or other exact number" — a property of the population; for the two
spelling mechanisms, **a CONDITION, not a status**: the closed corpus does not CURRENTLY write a
unit-bearing quantity literal (0 rulebases), so re-ask the harness lane when any rulebase writes
one. Limits, theirs: harness axis only; "reproduces canonical" is not "correct"; single replicate
whose error mode is spurious movement.
