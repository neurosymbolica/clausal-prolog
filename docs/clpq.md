# CLP(Q) — Rational-domain Constraints

CLP(Q) provides constraint logic programming over the rationals using **exact arithmetic**. Linear equalities are solved by **Gaussian elimination**; linear inequalities by **Holzbaur's simplex over bounded variables**. The result is an exact solver: no rounding, no approximation, no epsilon comparisons. Every answer is a ratio of two integers.

The solver is a port of Christian Holzbaur's clp(q,r) 1.3.3, the CLP(Q) of SICStus Prolog, in `clausal/logic/clpq/` (`holzbaur.py` and the modules around it; `PROVENANCE.md` there says where it comes from and `DEVIATIONS.md` lists every difference from 1.3.3). It is the only CLP(Q) solver: the solver Clausal shipped before it was retired by operator ruling 2026-11-05, and `CLAUSAL_CLPQ=legacy`, which selected it, now raises an error.

!!! note
    For CLP(Z) (integer constraints), see [Constraints](constraints.md). For CLP(R) (real constraints via interval arithmetic), see [CLP(R)](clpr.md). For CLP(B) (Boolean constraints), see [CLP(B)](clpb.md).

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`):
ISO Prolog syntax, without cut, with `:- use_module(library(clpq)).` loading
the solver. The [seam](syntax.md), Clausal's Python-syntax surface, writes
the same constraints with Python's comparison operators; the page notes the
seam spelling where it differs.

---

## Why CLP(Q)?

CLP(R) uses IEEE 754 doubles with outward-rounded intervals. This is sound (the true value is always inside the interval) but **approximate**: repeated operations widen intervals, and some constraints that are satisfiable cannot be solved to a point. CLP(Z) is exact but restricted to integers. CLP(Q) fills the gap — exact arithmetic over all rationals, with LP optimization.

**When to use CLP(Q) instead of CLP(R):**

- Financial calculations where `1/3 + 1/3 + 1/3` must equal exactly `1`
- Linear programming where the optimal vertex has rational coordinates
- Scheduling with fractional time units
- Any domain where you need to distinguish `1/3` from `0.333...`
- Systems of linear equations with exact rational solutions

**When to prefer CLP(R):**

- Non-linear constraints (CLP(Q) rejects `X * Y` where both are variables)
- Problems where approximate answers suffice
- Very large iterative computations where coefficient growth (see below) is a concern

---

## The constraint set in goal position

A **`{C}` goal** posts CLP(Q) constraints, as in Prolog's `library(clpq)`. `C` is
one comparison over rational arithmetic (`=`, `=\=`, `<`, `=<`, `>`, `>=`) or several
joined by commas; they are posted together, and `/` inside them is exact division.

```clausal
:- use_module(library(clpq)).

two(N, Q) :-
    {Q = N * 2}.

within(X) :-
    {0 =< X, X =< 10}.

% X = 3 rdiv 4, Y = 1 rdiv 4
box(X, Y) :-
    {X + Y = 1, X - Y = 1/2}.

% X = 3 rdiv 2
half(X) :-
    {2 * X = 3}.

test("two, forwards and backwards") :-
    two(3, Q),
    Q == 6,
    two(N, 8),
    N == 4.

test("two, bound later") :-
    two(N, Q),
    N = 5,
    Q == 10.

test("within") :-
    within(5),
    \+ within(11).

test("box and half") :-
    box(X, Y),
    X =:= 3 rdiv 4,
    Y =:= 1 rdiv 4,
    half(H),
    H =:= 3 rdiv 2.

test("a brace goal held in a variable") :-
    G = {Y >= 2, Y =< 2},
    findall(Y, G, Ys),
    Ys == [2].
```

`two(3, Q)` gives `Q = 6`; `two(N, 8)` solves `N = 4`; `two(N, Q)` with both unbound leaves
the constraint in the store and binds `Q` the moment `N` is known. A rational answer prints
as `3 rdiv 4`; compare it with `=:=`, or with `==` against an `rdiv` value you evaluated
(`Q is rdiv(3, 4)`). Unifying it with the written term `3 rdiv 4` fails: that is a compound
term, not the number.

`{}/1` is a predicate too: a brace goal built at run time and meta-called
(`G = {X > 1}, call(G)`, `findall(X, G, Xs)`, `call({}, C)`, a `-g` goal
at the toplevel) posts its block as the written goal does. Like the
written form, it exists in a file that imports `library(clpq)`.

A unit-carrying operand is welcome: a `constant_number_units/3` constant folded in with
`constant(Name)` keeps its unit through the solver (the units side channel), so
`{Q = 100 * constant(one_euro)}` gives `100 euro` and `{F >= constant(max_fine)}` compares
against the declared `5000 euro`, throwing `system_error(units_mismatch)` if `F` is
dimensionless (see [Units](#units)).

In the seam the same goal is a **set literal in goal position**, written with the seam's
comparisons (`{Q == N * 2}`, `{0 <= X <= 10}` with a chained comparison), and it lowers to
the module predicate `clpq.rational((C1, C2))`. A set in seam **data** position is still a
set, and `{}` there is an empty dict, never a constraint set; an element that is not a
comparison (`{X + 1, X > 1}`) is a load-time error. The seam's bare comparison goals outside
a set (`X == N * 2` on its own) are the CLP(Z)-style constraints described next.

---

## Unified syntax

The CLP comparison operators of `library(clpz)` (`#=`, `#\=`, `#<`, `#>`, `#=<`, `#>=`) are shared across CLP(Z), CLP(R), and CLP(Q). The domain is determined at runtime by what types are involved:

| Operator | CLP(Z) | CLP(R) | CLP(Q) |
|---|---|---|---|
| `#=` | integer equality | real equality | rational equality |
| `#\=` | integer disequality | real disequality | rational disequality |
| `#<` `#>` `#=<` `#>=` | integer comparisons | real comparisons | rational comparisons |

(The seam spells these `==`, `!=`, `<`, `>`, `<=`, `>=`.)

**Dispatch rule:** if either operand is a rational (an `rdiv` value, a Python `Fraction`) or a variable declared with `rational` (or `in_q`), the constraint goes to CLP(Q). If either operand is a `float` or declared with `in_real`, it goes to CLP(R). Otherwise it goes to CLP(Z). So `in_q(X, 0, 10), X #= 3` is a CLP(Q) constraint, and `X #= 7 rdiv 2` binds `X = 7 rdiv 2`.

Mixing a rational (CLP(Q)) and a `float` (CLP(R)) operand in the same constraint throws the Python `TypeError` `cannot mix CLP(Q) rational and CLP(R) float in the same constraint` (caught by `catch/3` as `'TypeError'(Message)`). Convert explicitly if you need to cross domains.

### `/` inside a constraint is exact

Inside `{...}`, `/` is **exact rational division**, as in Scryer's `library(clpq)`. A quotient that IS an integer is that integer: `{X = 6/2}` gives `3`, not `3 rdiv 1`. Only non-integral results are rationals.

```text
--8<-- "tests/fixtures/docs/clpq_sigs.txt:int_int_produces_fraction_ex2"
```

Under `#=`, `/` is not rational division: `X #= 6/2` gives `3`, but `X #= 7/2` and `X #= 1/3` fail. Write `rdiv` there (`X #= 7 rdiv 2`), or use `{...}`. (In the seam, `/` inside any constraint, `X == 1/3` included, is exact.)

In **evaluation** (`is/2`, the ISO comparisons) `/` is float division. Use `rdiv/2` when you want the exact quotient outside a constraint:

```text
--8<-- "tests/fixtures/docs/clpq_sigs.txt:int_int_produces_fraction"
```

In evaluation a zero divisor raises `evaluation_error(zero_divisor)`. Inside `{...}` a zero divisor makes the constraint fail: `{X = 1/0}` fails, as `X #= 1/0` does. The full operator table is in [Operators](operators.md); evaluation is in [Arithmetic](arithmetic.md).

Integral rationals are presented as integers by every binder — the arithmetic comparisons, `between/3`, CLP(Q) equalities and optima — because `2` and `2 rdiv 1` compare equal arithmetically but are different terms in the standard order (`'=='/2`, `compare/3`).

---

## Builtins

| Builtin | Arity | Description |
|---|---|---|
| `rational` | 1 | `rational(X)` — declare X as a rational variable |
| `in_q` | 3 | `in_q(X, Lo, Hi)` — declare rational variable with bounds `[Lo, Hi]` |
| `maximize` | 1, 2 | `maximize(Expr, Result)` — find maximum; constrains `Expr` to its maximum, which binds the variables when the optimum is a single point. `maximize(Expr)` is clp(Q,R)'s form, without `Result` |
| `minimize` | 1, 2 | `minimize(Expr, Result)` — find minimum; constrains `Expr` to its minimum, which binds the variables when the optimum is a single point. `minimize(Expr)` is clp(Q,R)'s form |
| `sup` | 2 | `sup(Expr, Sup)` — compute upper bound without committing (variables stay unbound) |
| `inf` | 2 | `inf(Expr, Inf)` — compute lower bound without committing (variables stay unbound) |
| `entailed` | 1 | `entailed(C)` — test if constraint `C` is implied by current store |
| `int_minimize` | 3 | `int_minimize(IntVars, Expr, Min)` — minimize with integrality constraints; binds `IntVars` to the optimum (Clausal's own) |
| `bb_inf` | 3, 5 | `bb_inf(IntVars, Expr, Inf)`: the same search, binding `Inf` alone; `bb_inf(IntVars, Expr, Inf, Vertex, Eps)` also gives the integral values of `IntVars` at the infimum |
| `dump_q` | 2 | `dump_q(Vars, Constraints)` — project constraint store onto Vars (Fourier-Motzkin) |
| `dump` | 3 | `dump(Vars, NewVars, Constraints)` — clp(Q,R)'s dump/3: the projection as terms over `NewVars` (fresh variables, or atoms to name them) |
| `ordering` | 1 | `ordering(Spec)` — clp(Q,R)'s ordering/1: which variables an answer defines in terms of which (a list, or `A < B`) |

`in_q/1` is also accepted as an alias for `rational/1`.

### Module API

`:- use_module(library(clpq)).` brings the `{...}` goal and the builtins above. CLP(Q)
constraints are posted with a [constraint set in goal position](#the-constraint-set-in-goal-position),
then optimised or projected:

```clausal
:- use_module(library(clpq)).

% -> X = 3 rdiv 4, Y = 0, COST = 3 rdiv 4
optimal(X, Y, COST) :-
    {0 =< X, X =< 1, 0 =< Y, Y =< 1, X + Y = 3/4},
    maximize(X, COST).

test("optimal") :-
    optimal(X, Y, COST),
    X =:= 3 rdiv 4,
    Y == 0,
    COST =:= 3 rdiv 4.
```

In the seam the optimisation and projection predicates also live in the `clpq` module
namespace, and `clpq.rational((constraints))` is the long spelling of a constraint set —
what the set lowers to:

```seam
optimal(X, Y, COST) <- (
    clpq.rational((
        0 <= X <= 1,
        0 <= Y <= 1,
        X + Y == 3/4,
    )),
    clpq.maximize(X, COST),
)
```

| Seam module predicate | Arity | Description |
|---|---|---|
| `clpq.rational` | 1 | `clpq.rational((constraints))` — post rational constraints; the long spelling of `{constraints}` in goal position |
| `clpq.maximize` | 2 | `clpq.maximize(Expr, Result)` — maximize over rationals |
| `clpq.minimize` | 2 | `clpq.minimize(Expr, Result)` — minimize over rationals |
| `clpq.supremum` | 2 | `clpq.supremum(Expr, Result)` — compute upper bound without committing |
| `clpq.infimum` | 2 | `clpq.infimum(Expr, Result)` — compute lower bound without committing |
| `clpq.entailed` | 1 | `clpq.entailed(X <= 5)` — test if constraint is implied |
| `clpq.dump` | 2 | `clpq.dump(Vars, Constraints)` — project constraint store |

Inside `{...}`, the arithmetic operators (`+`, `-`, `*`, `/`) and the comparisons (`=`, `=\=`, `<`, `=<`, `>`, `>=`) are interpreted as rational constraints, and variables are auto-declared as rational. A chained comparison is not ISO syntax: write `{0 =< X, X =< 1}`. (In the seam the block uses Python's operators, and `0 <= X <= 1` chains.)

### rational/1

Declares a variable as rational-domain (unbounded). This is the type declaration — it says "X is rational", nothing more.

```text
--8<-- "tests/fixtures/docs/clpq_sigs.txt:rational_1"
```

### in_q/3

Declares a rational variable with explicit bounds. Equivalent to `rational(X), Lo <= X <= Hi`. If the variable already has bounds, intersects with the new ones. Fails if the intersection is empty.

```text
--8<-- "tests/fixtures/docs/clpq_sigs.txt:in_q_3"
```

When the bounds collapse to a point (`Lo = Hi`), the variable is automatically unified with that value.

### maximize/2 and minimize/2

Finds the optimum of a linear expression subject to all currently posted constraints. Unifies `Result` with the optimal objective value and posts `Expr = Result`, as clp(Q,R)'s `maximize/1` does (`sup/2`, then the equation). Where the optimum is a single point, as in the example below, that binds every variable; where it is a face, the answer keeps the face as constraints (`{X >= 0, Y >= 0, X + Y =< 4, X =< 3}, maximize(X + Y, M)` gives `M = 4, {Y = 4 - X}, {X >= 0}, {X =< 3}`). Fails if the problem is unbounded.

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:maximize_2_and_minimize_2"
```

### sup/2 and inf/2

Compute the upper or lower bound of a linear expression **without binding variables**. Useful for inspecting the feasible range or for implementing `entailed`.

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:sup_2_and_inf_2"
```

### entailed/1

Tests whether a constraint is logically implied by the current store — i.e., whether it holds for **all** feasible points. Does not modify the store.

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:entailed_1"
```

Supported relations: `=<`, `>=`, `<`, `>`, `=:=` (or `=`), `=\=`. The relation
may also be built at run time (`C = (X =< 5), entailed(C)`). In the seam they
are `<=`, `>=`, `<`, `>`, `==`, `!=`: `entailed(X <= 5)`.

A strict relation or a disequality in the store counts: after `{X < 5}`, both
`entailed(X < 5)` and `entailed(X =\= 5)` hold, and after `{X < Y, Y =< Z}`,
`entailed(X < Z)` holds.

As in SICStus, an unbound argument raises `instantiation_error` and a term that
is no relation (`entailed(foo)`, or `entailed(X \= 2)` in Clausal Prolog) raises
`type_error(constraint, T)`. A non-linear relation (`entailed(A*A =\= 5)`) is
not entailed: the call fails. A conjunction or disjunction of relations
(`entailed((X =< 2, X =< 3))`), which SICStus reads, is not read yet: it fails.

### int_minimize/3

Minimize a linear expression subject to the current constraints **and** the requirement that specified variables take integer values. Uses LP relaxation with branch-and-bound internally. `Min` is bound to the optimum, and each variable of `IntVars` to its value at the integral point found.

`int_minimize/3` is Clausal's own predicate; clp(q,r) 1.3.3 has none, so this is no deviation from it. It runs 1.3.3's `bb_inf/3` search and then binds the variables to the vertex `bb_inf/5` gives (operator ruling 2026-11-06). Its errors name `bb_inf/3`. The vertex holds 1.3.3's rounded values, so where the optimum is integral only within `Eps` (below) the binding can fail.

`bb_inf/3` itself is SICStus's: it binds `Min` alone and leaves the variables unbound, as in SICStus and Scryer. `bb_inf/5`
(`bb_inf(IntVars, Expr, Inf, Vertex, Eps)`) unifies `Vertex` with the values
of `IntVars` at the infimum; `bb_inf/3` is `bb_inf/5` with `Eps = 0.001`,
the distance from an integer within which the search takes a value
as integral, as in 1.3.3. An `Eps` that is no constant fails, as in SICStus.

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:int_minimize_3"
```

### dump_q/2

Projects the constraint store onto a list of variables, eliminating all internal (slack) variables via Fourier-Motzkin elimination. Returns a list of constraints, each an atom.

The projection is clp(q,r) 1.3.3's `dump/3`, which drops redundant bounds (four constraints in the example below).

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:dump_q_2"
```

This is the feature that SWI-Prolog's CLP(Q) gets wrong — internal variables leak into answers. Clausal Prolog eliminates them correctly via Fourier-Motzkin.

### dump/3 and ordering/1

`dump(Vars, NewVars, Constraints)` is clp(Q,R)'s form of the projection:
`Constraints` is a list of constraint terms (`a>=4`, `a+b=<10`) over
`NewVars`, which is unified with fresh variables, or with the atoms a
program names them with (`dump([A, B], [a, b], Cs)`); the store is left
as it was. `Vars` is a proper list of unbound variables. Each term holds
1.3.3's projection.

`ordering(Spec)` says which variables an answer defines in terms of which
(`Spec` a list, the first defined by the rest, or `A < B` / `A > B`); the
projection honours it, and an unbound `Spec` fails. dump/3 reads its `Vars` as an
ordering too, so an `ordering/1` that contradicts their order raises
`system_error(unsatisfiable_ordering)` on the port. The residual a `-g`
goal prints is not dump/3: on the port it is the projection clp(Q,R)'s
toplevel prints, which imposes no order of its own, so
`ordering(Y < X), {X + Y = 10}` prints `{Y = 10 - X}` whatever order the
goal names X and Y in.

## Units

A quantity (a number with units, see [units.md](units.md)) may stand
anywhere in a constraint, on either front end:

```clausal
:- use_module(library(clpq)).
:- use_module(european_union, [euro]).
:- constant_number_units(one_euro, 1, euro).
:- constant_number_units(max_fine, 5000, euro).

price(Q)  :- {Q = 100 * constant(one_euro)}.        % Q = 100 euro
fine(Q)   :- {Q >= constant(max_fine)}.             % posts; a later binding decides
split(N)  :-                                          % N = 300
    {Q = N * constant(one_euro)},
    Q is 300 * constant(one_euro).
half(Q)   :- {2 * Q = 3 * constant(one_euro)}.      % Q = 3/2 euro

test("price is 100 euro") :-
    price(Q),
    P is 100 * constant(one_euro),
    Q == P.

test("split is 300") :-
    split(N),
    N == 300.

test("half is 3/2 euro") :-
    half(Q),
    H is 3 rdiv 2 * constant(one_euro),
    Q == H.
```

`#(Name)` is the short spelling of `constant(Name)` (ruled 2026-11-04,
[directives](directives.md#name-the-short-spelling)): `{Q = 100 * #(one_euro)}`
is the same constraint, and any undeclared name is refused at load.

Loading `library(clpq)` also declares clp(q,r) 1.3.3's named constants
(ruled 2026-11-04: "#(pi) undeclared, etc: error is ok for now. let CLPQ
declare them too."): `#(p)` and `#(pi)` are `3.141592653589793`, `#(e)` is
`2.718281828459045` and `#(zero)` is `0` (Q's arithmetic epsilon), and
`constant(pi)` ... reads the same; a module's own declaration of the name
wins. The float meets the solver as a float literal does: the solver
reads a float as its exact binary value, as Scryer does, so
`{X = #(pi)}` gives `X = 884279719003555/281474976710656`, exactly what
its own `#(pi)` gave. The
atoms `pi`, `e` ... as data are unchanged.

```clausal
:- use_module(library(clpq)).

turns(X) :- {X = 2 * #(pi)}.

test("#(pi) is clpq's declared constant") :-
    turns(X),
    X > 6.28,
    X < 6.29,
    Y is #(e),
    Y =:= 2.718281828459045,
    Z = pi,
    atom(Z).
```

```clausal
:- use_module(library(clpq)).
:- use_module(european_union, [euro]).
:- constant_number_units(one_euro, 1, euro).

price(Q) :- {Q = 100 * #(one_euro)}.

test("# is constant/1 in a constraint") :-
    price(Q),
    P is 100 * constant(one_euro),
    Q == P.
```

The seam spelling:

```seam
-import_from(european_union, [euro])
-constant_number_units(one_euro, 1, euro)

price(Q) <- clpq.rational(Q == 100 * constant(one_euro))

test("price is 100 euro") <- (price(Q), Q == 100 * constant(one_euro))
```

The solver never sees a unit. Every post goes through the same units side
channel the CLP(FD) comparators use (`clausal.logic.units_clp`): the
dimension of every operand is inferred first — a variable multiplied by a
quantity takes the product's dimension, a bare multiplier defaults to
dimensionless — and a disagreement raises the ISO term
`error(system_error(units_mismatch), Ctx)` before anything is posted. Then
each quantity becomes its exact magnitude (a `Decimal` is an exact
rational) and each dimensioned variable its bare *shadow*; the constraint is
solved on those. When the solver binds a shadow, the variable the program
wrote is bound to a quantity with the inferred dimension.

The magnitude is always in the dimension's **base unit**, on the way in and
on the way out: `5000 cent` is `50 euro` at construction (a scaled unit,
exactly as `1 kilometre` is `1000 metre`), so `{Q = constant(small_fine)}`
answers `50.00 euro`. The answer's magnitude is presented as everywhere in
the engine: an integral rational is an int (a currency shows it as a
`Decimal`), a non-integral one an exact `Fraction` — `3/2 euro`, never a
float.

`in_q/3` takes quantity bounds (`in_q(X, 0(euro), 10.50(euro))` declares
`X` in euro; a plain number beside a quantity bound is a mismatch), the
objectives of `maximize/2`, `minimize/2`, `sup/2`, `inf/2` and `bb_inf/3`
answer a quantity of the objective's dimension (a plain number when the
units cancel, `Q / constant(one_euro)`), `entailed/1` reads through the
same channel, and `dump_q/2` projects a dimensioned variable's constraints
(they live on its shadow) under the variable's own name, with magnitudes in
the base unit and no unit shown (`{Q >= 5000}` for a euro variable).

CLP(R) runs the same channel for physical quantities (a float magnitude
comes back as a quantity), and refuses money (`units_unsupported`): a
currency amount is exact and must not be computed in floats.

---

## Constraint examples

### Linear equalities

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:linear_equalities"
```

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:linear_equalities_ex2"
```

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:linear_equalities_ex3"
```

### Linear inequalities

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:linear_inequalities"
```

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:linear_inequalities_ex2"
```

### Optimization

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:optimization"
```

---

## How it works: algorithm overview

CLP(Q) uses a fundamentally different solver from CLP(R). Where CLP(R) narrows intervals via the HC4 algorithm, CLP(Q) solves systems of linear constraints exactly: equations by substitution (Gaussian elimination), inequalities by a simplex method over variables that carry their own bounds. This is Christian Holzbaur's design for clp(q,r), and the solver is clp(q,r) 1.3.3 translated file by file. Each module of `clausal/logic/clpq/` names the 1.3.3 file it ports, `NAMES.md` there maps every 1.3.3 predicate to the function that ports it, and `DEVIATIONS.md` lists every place the port differs.

| 1.3.3 file | Module | What it does |
|---|---|---|
| `nf.pl`, `nfq.pl` | `normal_form.py` | reads a constraint into a normal form and posts it (`{}/1`); delays a non-linear one |
| `store.pl` | `linear_forms.py` | linear forms: add, scale, substitute |
| `bv.pl` | `bounded_simplex.py` | equations, the bounded-variable simplex, `sup`/`inf`, `maximize`/`minimize` |
| `ineq.pl` | `inequalities.py` | posting an inequality |
| `class.pl` | `components.py` | components: the sets of variables that constraints link |
| `itf3.pl` | `attribute_hooks.py` | the unification hook, and the goals a residual is written as |
| `project.pl`, `fourmotz.pl`, `redund.pl`, `dump.pl`, `ordering.pl` | `projection.py`, `fourier_motzkin.py`, `redundancy.py`, `residual_constraints.py`, `variable_ordering.py` | projecting the store onto the variables an answer shows |
| `bb.pl` | `branch_and_bound.py` | `bb_inf/3,5`: optimisation over integers |
| `geler.pl` | `delayed_goals.py` | goals that wait until a constraint becomes linear |
| `arith.pl`, `arith_q.pl` | `arithmetic.py` | exact rationals, as (numerator, denominator) pairs of ints |

`holzbaur.py` is the API the rest of Clausal calls (`q_eq`, `q_le`, `sup`, `dump_q`, ...); `boundary.py` turns an arithmetic cell into an operator node and runs the [units](#units) side channel before a constraint reaches the port, and `limits.py` holds the resource caps (the `clpq_max_*` [flags](flags.md)).

### The kinds of constraint

| Constraint | How it is posted | Example |
|---|---|---|
| **Equation** `Σ aᵢXᵢ + c = 0` | solved for one variable, which is substituted everywhere | `{X + Y = 10}` |
| **Bound** `aX + c =< 0` (one variable) | narrows that variable's bounds | `{X =< 10}` |
| **Inequality** over several variables | a new variable, the slack, stands for the left side and takes the bound | `{2*X + Y =< 16}` |
| **Strict** `<`, `>` | the same, the bound marked strict | `{X < Y}` |
| **Disequation** `=\=` | a new variable stands for the difference and is marked nonzero | `{X =\= 5}` |

A constraint is first read into a normal form (nf.pl): a sum of monomials, each a coefficient times a product of powers. A constraint whose normal form is linear (each monomial a constant, or a coefficient times one variable) is posted. `{3*X + 5*Y =< 10}` is linear. `{X * Y = 10}` over two rational variables is not: it is delayed until it becomes linear (until X or Y is known), as SICStus does. The functions clp(Q,R) knows inside `{}` are delayed the same way — `abs/1`, `sin/1`, `cos/1`, `tan/1`, `min/2`, `max/2`, `pow/2`, `exp/2` and `^/2` — which the `.pl` front end passes through (`{sin(cos(X)) = 1/2}` answers; `pow/2` and `exp/2` are read as `^`). `entailed/1` of a non-linear relation answers false.

### Why not interval arithmetic?

CLP(R) uses interval arithmetic: each variable has a range `[lo, hi]`, and constraints narrow these ranges. This works for non-linear constraints but has limitations for linear systems:

**Problem 1: Weak propagation.** Consider `X + Y = 10` with `X in [0, 10]` and `Y in [0, 10]`. Interval arithmetic narrows both to `[0, 10]` — no progress. It cannot deduce that if `X = 3` then `Y = 7` without labeling.

**Problem 2: No optimization.** Interval arithmetic has no native concept of "maximize this expression." You'd need to encode it as a constraint and binary-search, which is slow and approximate.

**Problem 3: Accumulating imprecision.** IEEE floats round every operation. After many constraints, the intervals may widen beyond usefulness.

Substitution and the simplex solve all three: an equation is solved exactly and substituted away, an inequality is decided by pivoting, and optimization is a direct extension of the simplex.

### Why not just simplex for everything?

The simplex method handles inequalities. You could turn every equation `a = b` into `a =< b` and `a >= b` and use the simplex for everything, but each equation would become two rows, and pivoting would have more to do. In Holzbaur's design an equation removes a variable instead: the variable it is solved for is defined by the others and is gone from every other constraint. A bound on a single variable needs no row at all: it is stored on the variable itself. Only an inequality over several variables adds a row, the definition of its slack.

---

## How it works: linear forms and the store

Every variable the solver knows carries one record, its state (`attributes.py`, 1.3.3's attributes in full words): its **linear form**, its **bounds** and their strictness, its **component**, and a few marks (nonzero, target, keep) the projection reads.

A linear form (store.pl) is 1.3.3's `[I, R | Terms]`: a constant `I`, a constant `R`, and a list of `(variable, coefficient)` terms in the variables' order (creation order, DEVIATIONS.md D4). A variable is either

- **independent**: its linear form is itself (`Terms = [X*1]`, `I = R = 0`); or
- **dependent**: its linear form is its definition in terms of independent variables. A dependent variable is a *basic* variable of the simplex, and its linear form is its row.

`R` is the part of a row's value that comes from independent variables sitting at an active bound, so `I + R` is the dependent variable's value at the current vertex (1.3.3's `rhs_value`).

The bounds are 1.3.3's type: none, lower `L`, upper `U`, or both, and a bound is *active* when the variable sits at it (1.3.3's `t_L`, `t_U`, `t_Lu`, `t_lU`). An independent variable with an active bound is non-basic at that bound. A strict bound is the same bound with a strictness bit set (one bit for the lower, one for the upper).

A **component** (class.pl) is the set of variables that constraints link; its record lists its members and its basis (the dependent variables whose rows are in it). An equation over two components merges them; a substitution rewrites only the rows of one component.

---

## How it works: equations

When an equation is posted, its normal form is **dereferenced**: each dependent variable in it is replaced by its linear form, so what is left mentions only independent variables (bv.pl's `solve/1`). Then:

- no variable is left: the constant must be zero, or the post fails;
- a variable is left: one of them is selected and the equation solved for it. The selection (bv.pl's `select_dependent/7`) prefers a variable new to the store over one already in a component, and a variable without bounds over one with bounds; on a tie the later variable in the order wins. The selected variable becomes dependent, its definition is **back-substituted** into every row of its component, and the components of the equation's variables become one;
- the selected variable had bounds: they are now the bounds of its row, and the simplex restores feasibility (below) before the post succeeds;
- a variable whose linear form becomes a constant is bound to that number, and the binding wakes the [unification hook](#how-it-works-the-unification-hook) in turn (bv.pl's `export_binding/1`).

### Worked example

**System:** `X + Y + Z = 6`, `X - Y = 2`, `Y - Z = 1`, three new variables, created in that order.

**Post `X + Y + Z = 6`.** All three are new and unbounded: a tie, so the last one, Z, is selected. `Z = 6 - X - Y`; X and Y stay independent.

**Post `X - Y = 2`.** Neither X nor Y is dependent, so nothing is substituted. Both are in Z's component and unbounded: Y, the later, is selected. `Y = X - 2`, and back substitution rewrites Z's row: `Z = 6 - X - (X - 2) = 8 - 2X`.

**Post `Y - Z = 1`.** Dereferenced: `(X - 2) - (8 - 2X) = 1`, that is `3X - 10 = 1`. Only X is left: `X = 11/3`. X is bound; substitution makes Y's and Z's linear forms constants, and they are bound too.

**Final answer:** `X = 11/3`, `Y = 5/3`, `Z = 2/3`. All exact.

---

## How it works: inequalities and the bounded-variable simplex

### Posting an inequality

An inequality is normalised to `Lin =< 0` or `Lin < 0` and dereferenced, so it mentions only independent variables (ineq.pl's `ineq/4`):

- **No variable**: the constant decides; the post succeeds or fails.
- **One variable** (`K*X + I =< 0`): a bound on X, `X =< -I/K` for a positive K, `X >= -I/K` for a negative one. It is stored on X only if it is tighter than X's bound of that side, and is checked against the other side.
- **One variable, X dependent**: the same bound goes on X's row: X is the basic variable of that row, so the bound is a bound on the row's value. Where the current value `I + R` breaks it, the simplex moves.
- **Several variables**: a new variable S, the slack, is defined by the form (`S = Lin`) and takes the bound `S =< 0` (`S < 0` for a strict one), so S is a basic variable with a row. Where the form has a variable U without bounds, U absorbs the slack instead: U is defined over a slack `S >= 0` (`S > 0` for a strict one), which stays independent (ineq.pl's `ineq_more/2`).

After the posts of the classic LP below (`in_q([X, Y], 0, 1000)` and three inequalities), the store holds two independent variables at their active lower bound and three slack rows:

```
X                 independent, 0 =< X =< 1000, at its lower bound
Y                 independent, 0 =< Y =< 1000, at its lower bound
S1 = X + 3Y - 15  dependent, S1 =< 0, value I + R = -15
S2 = X + 2Y - 11  dependent, S2 =< 0, value -11
S3 = 2X + Y - 16  dependent, S3 =< 0, value -16
```

### Restoring feasibility

A dependent variable whose value `I + R` is at or outside a bound of its row is **reconsidered** (bv.pl's `reconsider/1`). The solver takes one step towards the inside: it looks for an independent variable in the row whose move improves the value, and the tightest other row that move runs into (a ratio test over the component, `upper_bound_tightest`, `lower_bound_tightest`). Then either the independent variable moves to its own other bound (a *bound swap*) or it **pivots**: it and the limiting dependent variable exchange places, and every row of the component is rewritten by back substitution. The bound the dependent variable met becomes active. Each step leaves the store feasible or proves it infeasible: no move improves the value and the post fails.

Geometrically, a pivot moves along an edge of the feasible polyhedron from one vertex to an adjacent vertex.

### Optimisation: sup, inf, maximize, minimize

`inf(Expr, Inf)` reads `Expr` into a linear form over independent variables and iterates **decrease steps** (bv.pl's `iterate_decrease/2`): pick an independent variable whose coefficient lets the objective fall and whose bounds let it move, find the row that limits the move, and pivot or swap. When no variable can decrease the objective, its value is the infimum; when a variable can decrease it without limit, the problem is unbounded and `inf/2` fails. `sup/2` is `inf` of `-Expr`. The steps run between a trail mark and the undo to it, so the store is as it was afterwards; 1.3.3 does the same by failing back after recording the optimum.

`minimize(Expr)` and `maximize(Expr)` are `inf`/`sup`, then the constraint `{Expr =:= Optimum}` posted, as in 1.3.3: what that implies is bound, and an optimal face stays as constraints.

For the classic LP (maximize `30X + 50Y` subject to `2X + Y =< 16`, `X + 2Y =< 11`, `X + 3Y =< 15`, `X, Y >= 0`) the steps end at the vertex `X = 7, Y = 2`, objective **310**; the posted `{30*X + 50*Y =:= 310}` meets only that vertex, so X and Y are bound.

`bb_inf/3,5` (bb.pl) runs `inf` and, where an integer variable takes a value that is not integral (further than `Eps` from an integer), branches: `{X =< Floor}` first, then `{X >= Ceiling}`, keeping the best integral optimum found (the incumbent) and pruning a branch whose relaxed infimum is no better.

### Strict bounds and disequations

A strict bound is a bound with its strictness bit. The inequality code compares a new bound with the old one bit and all (`X < 3` after `X =< 3` tightens it; `X >= 3` after `X < 3` fails), the simplex steps carry the bits when a bound moves onto a row, and a projection prints them (`{X < Y, Y =< 3}` onto X is `X < 3`). The port adds one check 1.3.3 lacks: a binding fails when a strict bound of its component can no longer hold (DEVIATIONS.md D19).

A disequation `{Lin =\= 0}` defines a new variable by the form and marks it **nonzero**. It is passive: it fails when that variable is bound to 0, so the projection shows it through the variable (`{X =\= 2}` dumps as `{X = 2 + _Q1}, {_Q1 =\= 0}`).

---

## How it works: backtracking

A variable's state is a record that is never changed in place: each change puts a new record with `put_attr`, and the engine's trail undoes it on backtracking, as it undoes a binding. A component's record lives the same way, on a hidden variable of its own. So there is no store to copy: a post costs the changes it makes, and backtracking undoes exactly those. An operation that must leave the store as it was (an optimum, a projection, a redundancy test) takes a trail mark and undoes to it.

---

## How it works: the unification hook

When a variable with CLP(Q) state is unified, its attribute hook runs (itf3.pl's `verify_attributes/3`, `attribute_hooks.py`):

| Unified with | Action |
|---|---|
| a number | the equation `X = N` is solved: X's linear form, dereferenced, equals N; a nonzero variable must not be 0; the bindings that implies are exported in turn |
| another constrained variable | the equation `X = Y`, and their components merge |
| a variable without CLP(Q) state | that variable takes the state |
| anything else (a float, an atom, a compound) | `type_error(rational, T)`, from 1.3.3's arith_normalize test (DEVIATIONS.md D3) |

Bindings implied by a binding are queued and run by one loop, not nested, so a long chain of implied bindings needs no recursion (`export_bindings`). A goal delayed on a non-linear constraint (geler.pl) wakes when a variable in it is bound, and posts the constraint once it is linear. DEVIATIONS.md D3 lists how the hook meets the engine: bindings made in one unification, PlainVars, and hooks of other libraries running at the same time.

---

## How it works: projection

An answer shows constraints on the variables the query names, not on slacks and other internal variables. `dump/3`, `dump_q/2` and the `-g` answer printer project the store onto the answer's variables (project.pl), between a trail mark and the undo to it:

1. the targets are marked, and each dependent target is made independent by pivoting it with a non-target of its row;
2. dependent variables that are no target and are needed by nothing are dropped;
3. the non-target independent variables that occur in inequalities are eliminated by **Fourier-Motzkin elimination** (fourmotz.pl): each pair of an upper and a lower bound on the eliminated variable gives their combination, and a combination that is implied is not kept;
4. **redundant** bounds are dropped (redund.pl): a bound is redundant where posting its negation fails;
5. the variables are ordered (ordering.pl, as `ordering/1` asks) and each row is written as a constraint over the targets (dump.pl), a slack kept for a disequation named `_Q1`, `_Q2`, ...

The `-g` printer projects as the SICStus toplevel does (DEVIATIONS.md D28). Projection can be exponential in the number of variables eliminated; the `clpq_max_projection` [flag](flags.md) caps its work.

---

## How it works: dispatch from fd_eq, fd_le, etc.

The dispatch chain in `clpfd.py` (and the C extension `_clpfd_propagate.c`):

```
fd_eq(l, r, trail):
    1. Fast path: type(l) is int and type(r) is int → Python ==
    2. _resolve expression trees
    3. _check_no_mixed_rational_real(l, r) → TypeError if mixed
    4. integer-linear, every variable with FD state and one with Q
       state → CLP(Q) via q_eq, then CLP(FD) (_post_shared_fd_q)
    5. _any_rational(l, r) → CLP(Q) via q_eq
    6. _any_real(l, r)     → CLP(R) via real_eq
    7. Expression linearization → ScalarProductConstraint
    8. _both_ground(l, r)  → Python ==
    9. At least one Var    → CLP(Z) EqConstraint
```

`_any_rational` checks: is either operand a `Fraction` instance, or a `Var` with CLP(Q) state (the `Q_KEY` attribute)? Before dispatching, `_check_no_mixed_rational_real` raises `TypeError` if one operand is rational and the other is a float or CLP(R) variable.

Step 4 runs in the Python wrappers around the C entry points, ahead of them. The C extension mirrors the other checks. During module initialization, it imports `_check_no_mixed_rational_real`, `_any_rational` from the Python `clpfd` module and `q_eq`, `q_ne`, `q_lt`, `q_le` from `clpq`. The dispatch in C calls the Python functions through the C-API.

---

## The coefficient growth problem

This is the fundamental trade-off of exact rational arithmetic, raised by Markus Triska in discussions about this implementation.

When rational numbers are combined through arithmetic operations, the numerators and denominators can grow exponentially. Newton's method for `sqrt(2)` illustrates this:

| Iteration | Approximation | Digits (num/denom) |
|:---------:|:-------------:|:-------------------:|
| 0 | 1/1 | 1 / 1 |
| 1 | 3/2 | 1 / 1 |
| 2 | 17/12 | 2 / 2 |
| 3 | 577/408 | 3 / 3 |
| 4 | 665857/470832 | 6 / 6 |
| 5 | 886731088897/627013566048 | 12 / 12 |
| 15 | (12543-digit number) | 12543 / 12543 |

Each iteration roughly **doubles** the digit count. After 15 iterations, Python can still handle the number (arbitrary precision), but arithmetic becomes slow — GCD reduction on every operation is `O(n log n)` in digit count.

**In CLP(Q) specifically,** coefficient growth arises in two scenarios:

1. **Ill-conditioned systems** where the coefficient matrix determinant is close to zero. Substitution amplifies small differences.
2. **Many pivot steps** in the simplex method. Each pivot divides by the pivot coefficient, potentially increasing denominators.

**Mitigation strategies:**

- Every rational is kept in lowest terms (a GCD on every operation)
- For most CLP(Q) usage (systems of 5-20 variables), coefficient growth is manageable
- If growth becomes a problem, consider CLP(R) for the approximate part and CLP(Q) only where exactness is required
- The solver does not limit precision — it computes correct answers at the cost of speed. What it caps is work: the `clpq_max_*` [flags](flags.md) bound the nodes and pivots of a `bb_inf` search, the work of a projection, and the size of the powers and products one constraint expands, and raise `resource_error` past them (DEVIATIONS.md D24)

This is exactly the trade-off SICStus Prolog documents: "you may be out of space particularly soon" for iterative rational computations. The SICStus documentation recommends switching to CLP(R) when precision is not critical.

---

## Comparison with other systems

| Feature | SICStus CLP(Q) | SWI CLP(Q) | ECLiPSe | **Clausal Prolog CLP(Q)** |
|---|---|---|---|---|
| Correctness | Reference impl | Orphaned, bugs | No CLP(Q) | **Port of clp(q,r) 1.3.3, deviations listed** |
| Algorithm | Holzbaur Gaussian+simplex | Port of SICStus | — | **Holzbaur Gaussian+simplex** |
| Arithmetic | GMP rationals | SWI rationals | — | **Python ints (numerator, denominator)** |
| Optimization | `maximize/1`, `minimize/1` | Same (buggy) | — | **`maximize/2`, `minimize/2`**, and the `/1` forms |
| Bounds query | `sup/1`, `inf/1` | Same | — | **`sup/2`, `inf/2`** |
| Entailment | `entailed/1` | Same | — | **`entailed/1`** |
| MIP | `bb_inf/3`, `bb_inf/5` | Same | — | **`int_minimize/3`**, `bb_inf/3`, `bb_inf/5` |
| Projection | Fourier-Motzkin | Broken | — | **`dump_q/2` (Fourier-Motzkin)**, `dump/3`, `ordering/1` |
| Non-linear | Deferred | Deferred | — | **Deferred** |
| Syntax | `{X + Y =< 8}` | Same | — | **`{X + Y =< 8}`**, or `X + Y #=< 8` (unified; seam `X + Y <= 8`) |
| `/` inside a constraint | Exact rational | Exact rational | — | **Exact rational inside `{...}`; an integer when integral** |

### Historical context

**Holzbaur (1992, 1994, 1995)** at OFAI Vienna created the definitive CLP(Q,R) implementation for SICStus Prolog. His algorithm combines Gaussian elimination for equalities with a simplex method over bounded variables for inequalities, with incremental constraint addition and detection of fixed (determined) variables. Clausal's solver is a translation of his clp(q,r) 1.3.3 (below).

**SWI-Prolog's CLP(Q)** is a port of Holzbaur's code by Leslie De Koninck. It is officially "orphaned" (no maintainer) and has known bugs, including a projection failure reported by Markus Triska where internal variables leak into answers.

**Prolog III** (Colmerauer, 1989) had a complete solver for linear arithmetic over rationals using Gaussian elimination. Guy Narboni documented the coefficient growth problem in "About Gaussian elimination and infinite precision" (1992). Prolog IV (1996) extended this with interval narrowing for non-linear constraints.

**The Parma Polyhedra Library** (Bagnara et al.) provides an open-source exact-arithmetic simplex in C++ using GMP rationals. It serves as a correctness oracle for exact LP solvers.

The solver is a translation of the clp(q,r) 1.3.3 sources as SICStus distributes them (`clausal/logic/clpq/PROVENANCE.md`); SWI-Prolog's CLP(Q) is not used in any form. The solver Clausal shipped before it, retired on 2026-11-05, was a clean-room design from the published papers (Holzbaur 1992, 1994).

---

## Interaction with CLP(Z) and CLP(R)

### Type promotion lattice

```
int ──→ Fraction  (exact, via Fraction(n))
int ──→ float     (lossy for large ints, via float(n))
float ──✗──→ Fraction  (BLOCKED — lossy, raises type_error(rational, F))
Fraction ──✗──→ float   (BLOCKED — loses exactness)
```

Integer promotion to `Fraction` is always exact. This mirrors how CLP(Z)→CLP(R) promotion works (via `_promote_fd_to_real`), but without any precision loss.

### FD↔Q coexistence

A variable can have **both** FD and Q attributes simultaneously, just like FD and R can coexist. When a CLP(Z) variable enters a CLP(Q) context:

1. `_promote_fd_to_q` extracts the FD bounds as exact `Fraction` values and creates Q state
2. The FD attribute is **kept** — both hooks fire independently on unification
3. FD enforces integrality and domain holes; Q handles rational constraint propagation
4. When FD narrows (via `_narrow`), Q bounds are tightened to match
5. Integer-valued `Fraction` results (like `Fraction(3)`) are accepted by the FD hook
6. A `#` comparison whose variables all have FD state, one of them Q state
   too, and which is linear with integer coefficients, is posted to **both**
   stores: CLP(Q) gets the relaxation, CLP(FD) narrows the domains, and a
   domain that becomes a single value binds the variable, which CLP(Q) then
   sees. `X #>= 0, X #=< 5, {X + Y = 7}, X #> 4` gives `X = 5, Y = 2`, as in
   Scryer (it left X unbound when the post went to CLP(Q) alone). A `#`
   comparison with a variable that has Q state and no FD state (a rational
   variable, or a fresh one) stays CLP(Q)'s alone.

CLP(Q)'s own posts do not narrow an FD domain: `X in 1..5, {X > 4}` leaves
X unbound (`label([X])` gives 5), as Scryer, whose clpz and clpq are
separate, leaves it.

A CLP(Z) variable enters a CLP(Q) context through a comparison (`{X =< 7}`),
`in_q/1,3`, or the objective of `sup/2`, `inf/2`, `maximize`, `minimize` and
`bb_inf`: with `X in 1..5`, `sup(X, S)` gives `S = 5`. Only finite ends come
along: `X #\= 3` has none, so `sup(X, S)` fails, as it does for a variable
the store does not know.

Only the domain's hull comes along, a rational relaxation: no holes and no
integrality. `sup/2` and `inf/2` answer on the relaxation: with
`X in 1..3 \/ 7..9` and `{X >= 4}`, `inf(X, I)` gives 4, not 7. An optimum
that binds, or must be integral, cannot be read off the relaxation, so
`maximize`, `minimize` and `bb_inf` never give its answer, nor fail where
the FD side refuses it (operator ruling 2026-11-03):

- They raise `representation_error(fd_domain_with_holes)` when an FD
  variable whose domain has a hole is in the objective's component of the
  store: in the objective (or `bb_inf`'s integer list), or linked to it by
  constraints. `X in 0..2 \/ 8..10, {Y = X, Y =< 7}, maximize(Y)` raises
  it. An FD variable with holes that no constraint links to the objective
  does not count.
- `maximize` and `minimize` raise
  `representation_error(fd_relaxation_not_integral)` when the relaxed
  optimum gives an FD variable a value that is not an integer:
  `X in 1..5, {2*X >= 3}, minimize(X)` raises it (the relaxation's
  optimum is 3/2). Where the optimum is integral they answer as before.
- `bb_inf` makes integral only the variables of its integer list. It
  binds nothing, so `X in 1..5, {2*X >= 3},
  bb_inf([], X, I)` gives `I = 3/2`, the relaxation, as asked; list `X` for
  `I = 2`.
- An FD constraint posted between FD variables before they had CLP(Q)
  state (`X #= Y + 3` ahead of `{D = X - Y}`) is not in the CLP(Q) store.
  When clpfd refuses the relaxation's optimum through such a constraint
  (one posted before promotion, a non-linear or global one such as
  `all_different/1`, or a domain narrowed after promotion), while the
  store alone takes it, `maximize`, `minimize` and `bb_inf` raise
  `representation_error(fd_constraint_not_in_relaxation)` (operator
  ruling 2026-11-03): `X in 1..5, Y in 1..5, X #= Y + 3, {D = X - Y},
  maximize(D)` failed, since the relaxation's `D = 4` binds `X = 5, Y = 1`,
  and `bb_inf([X, Y], -D, I)` gave `I = -4` under `holzbaur`. For
  `bb_inf` the check is a trial binding of the FD variables of its
  integer list to the integral point; the store is left as it was. An
  optimum the FD constraints allow answers as before (`X #=< Y,
  {D = X + Y}, maximize(D)` gives `D = 20`). The check does not search:
  where the program has no integer solution at all, it raises too, as the
  integrality refusal does. Posted after promotion (`{D = X - Y},
  X #= Y + 3`), the constraint reaches both stores, and `D = 3`. (Scryer
  fails both orders: its clpq does not see clpz's bounds.) Constraints
  that are not CLP(FD)'s, such as `dif/2`, are not checked: an optimum
  they refuse fails.

```clausal
--8<-- "tests/fixtures/docs/clpq_sigs.txt:fd_q_coexistence"
```

### Dispatch table

| Situation | Behaviour |
|---|---|
| `in_q(X, 0, 10)` then `X #= 3` | CLP(Q): X has CLP(Q) state, `3` is treated as `Fraction(3)` |
| `in_domain(X, 0, 5)`, `{X + Y = 7}` then `X #> 4` | Both stores: FD narrows X to 5 and binds it, CLP(Q) gives `Y = 2` |
| `in_domain(X, 1, 10)` then `X #= 1 rdiv 3` | **Fails**: the rational triggers Q dispatch, the FD var is promoted to Q with bounds `[1, 10]`, and `1/3` is outside them |
| `in_domain(X, 1, 10)` then `X #= 1 rdiv 2` | **Fails**: `1/2` is not an integer, FD hook rejects |
| `X #= 1/0` | **Fails** |
| `{X = 1/0}` | **Fails** |
| `in_real(X, 0.0, 10.0)` then `X #= 1 rdiv 3` | **TypeError**: cannot mix CLP(Q) rational and CLP(R) float |
| `in_real(X, 0.0, 10.0)` then `in_q(X, 0, 1)` | Accepted: no `TypeError` is raised |
| `X #= 5` (no declaration) | CLP(Z): both sides are integers |
| `X #= 5.0` (no declaration) | CLP(R): float literal triggers R dispatch |
| `X #= 1 rdiv 3` (no declaration) | CLP(Q): the rational operand triggers Q dispatch |
| `X #= 1/3` (no declaration) | **Fails**: `/` under `#=` is not rational division; write `rdiv` or `{X = 1/3}` |

(The seam spells these with `==`; there `/` inside a constraint is exact, so seam
`X == 1/3` is the CLP(Q) row, and seam `X == 1/0` fails.)

---

??? abstract "Per-variable state"

    Each constrained variable stores its state as an attributed-variable
    attribute under the key `Q_KEY` (`"clpq_holzbaur"`): an immutable
    `SolverState` record (`clausal/logic/clpq/attributes.py`) with its
    linear form, its bounds and their strictness, its component and the
    marks the projection reads ([linear forms and the store](#how-it-works-linear-forms-and-the-store)).
    A change puts a new record with `put_attr`, which `trail.undo()`
    restores; there is no global store ([backtracking](#how-it-works-backtracking)).

??? example "Usage examples"

    **LP optimization:**

    ```clausal
    --8<-- "tests/fixtures/docs/clpq_sigs.txt:dispatch_table"
    ```

    **Backtracking (constraints are undone when a branch fails):**

    ```clausal
    --8<-- "tests/fixtures/docs/clpq_sigs.txt:dispatch_table_ex2"
    ```

    **Inspecting variable state (Python runtime API):**

    ```python
    # This is specific to the Python runtime — not Clausal syntax.
    from clausal.logic.clpq import Q_KEY
    from clausal.logic.variables import get_attr

    state = get_attr(var, Q_KEY)
    if state is not None:
        print(state.bounds)        # bounds_lower_upper((0, 1), (10, 1)), ...
        print(state.linear_form)   # the row of a dependent variable
    ```

---

??? info "Test coverage"

    Tests are in `tests/test_clpq.py`; the port's own, one file per ported 1.3.3 file plus the oracle, fuzz and differential tests, are in `tests/clpq_port/`.

    - **Dispatch**: Fraction triggers CLP(Q), int stays CLP(Z), float stays CLP(R)
    - **Domain declaration**: `in_q` basic, narrowing, infeasible, point binding, list form, unbounded, ground check
    - **Ground constraints**: all six comparison operators on ground rationals
    - **Variable binding**: `q_eq(X, Fraction)` binds X
    - **Linear equalities**: two-var, three-var (exact fractions), contradictory, redundant, rational coefficients, scaled (`2*X = 1 -> X = 1/2`), large coefficients (`999999*X = 1`)
    - **Linear inequalities**: simple le, infeasible system, two-var feasibility, redundant, zero coefficients
    - **Backtracking**: undo restores unbound, undo restores bounds, undo restores the whole store; maximize/minimize backtrack correctly
    - **Optimization**: maximize simple, minimize simple, classic LP (30X + 50Y, answer 310), variables bound to optimal point
    - **sup/inf**: simple bounds, LP bounds, does not bind variables
    - **entailed**: `=<`, `>=`, `=`, `\=` entailment; does not modify store; does not add Q attributes to bare variables
    - **Disequality**: `q_ne` prevents binding to excluded value, allows other values; strict `q_lt` rejects equal; two-var disequality; backtrack restores
    - **Pivot/simplex**: upper-bound inequality feasibility, infeasible upper-bound detection, degenerate vertex, contradictory multi-var inequalities
    - **Projection**: `dump_q` simple bounds, inequality projection (no internal var leakage), equality projection, empty store
    - **Integer optimization**: `int_minimize` (bb_inf) simple integer, LP integer, no integer constraint, infeasible, already integer, mixed integer, multi-level branching, variable binding
    - **Coefficient growth**: Newton sqrt(2) to 12-digit fractions, large coefficient constraints
    - **Float type safety**: `type_error(rational, F)` raised when Q-variable unified with float
    - **Undo**: a multi-step operation undoable as a single unit
    - **End-to-end seam**: all doc examples compiled and run through full pipeline (7 integration tests)

---

## References

- Holzbaur, C. (1992). "An algorithm for linear constraint solving: its incorporation in a Prolog meta-interpreter for CLP." *Journal of Logic Programming*.
- Holzbaur, C. (1994). "A specialized incremental solved form algorithm for systems of linear inequalities." OFAI TR-94-07, Vienna.
- Holzbaur, C. (1995). "OFAI CLP(Q,R) Manual, Edition 1.3.3." OFAI TR-95-09, Vienna.
- Refalo, P. (1998). "Approaches to the incremental detection of implicit equalities with the revised simplex method." *Lecture Notes in Computer Science*.
- Narboni, G.A. (1992). "About Gaussian elimination and infinite precision." 2nd International Workshop on Constraint Logic Programming, Marseille.
- Narboni, G.A. (1999). "From Prolog III to Prolog IV: the Logic of Constraint Programming Revisited." *Constraints* journal.
