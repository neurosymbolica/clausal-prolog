# CLP(Q) — Rational-domain Constraints

CLP(Q) provides constraint logic programming over the rationals using **exact arithmetic** via Python's `fractions.Fraction`. Linear equalities are solved by **Gaussian elimination**; linear inequalities by the **revised simplex method** with Bland's anti-cycling rule. The result is an exact solver: no rounding, no approximation, no epsilon comparisons. Every answer is a ratio of two integers.

The implementation lives in `clausal/logic/clpq.py`.

!!! note
    For CLP(Z) (integer constraints), see [Constraints](constraints.md). For CLP(R) (real constraints via interval arithmetic), see [CLP(R)](clpr.md). For CLP(B) (Boolean constraints), see [CLP(B)](clpb.md).

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

## Unified syntax

Clausal's comparison operators are shared across CLP(Z), CLP(R), and CLP(Q). The domain is determined at runtime by what types are involved:

| Operator | CLP(Z) | CLP(R) | CLP(Q) |
|---|---|---|---|
| `==` | integer equality | real equality | rational equality |
| `!=` | integer disequality | real disequality | rational disequality |
| `<` `>` `<=` `>=` | integer comparisons | real comparisons | rational comparisons |

**Dispatch rule:** if either operand is a `Fraction` or a variable declared with `in_q`, the constraint goes to CLP(Q). If either operand is a `float` or declared with `in_real`, it goes to CLP(R). Otherwise it goes to CLP(Z).

CLP(Q) has the highest dispatch priority: if both `Fraction` and `float` appear, exact rational arithmetic wins.

### `int/int` produces `Fraction`

In Clausal, **integer division always produces an exact rational**:

```clausal
# skip
X := 1/3            % Fraction(1, 3) — exact, not 0.333...
X := 7/2            % Fraction(7, 2) — exact, not 3.5
X := 22/7           % Fraction(22, 7) — exact
```

This is a deliberate language design choice. In a logic programming language, exactness is the natural default. If you want IEEE float division, use a float literal on either side: `1.0/3` or `7/2.0`.

Because `int/int` produces `Fraction`, rational constraints arise naturally:

```clausal
# skip
X == 1/3            % CLP(Q) constraint: X = Fraction(1, 3)
X + Y == 1/2        % CLP(Q) constraint: X + Y = Fraction(1, 2)
```

---

## Builtins

| Builtin | Arity | Description |
|---|---|---|
| `in_q` | 1 | `in_q(Var_or_list)` — declare rational variable(s) with unbounded domain |
| `in_q` | 3 | `in_q(Var_or_list, Lo, Hi)` — declare rational variable(s) with domain `[Lo, Hi]` |
| `maximize` | 2 | `maximize(Expr, Result)` — find maximum; binds all variables to optimal point |
| `minimize` | 2 | `minimize(Expr, Result)` — find minimum; binds all variables to optimal point |
| `sup` | 2 | `sup(Expr, Sup)` — compute upper bound without committing (variables stay unbound) |
| `inf` | 2 | `inf(Expr, Inf)` — compute lower bound without committing (variables stay unbound) |
| `entailed` | 3 | `entailed(Op, L, R)` — test if `L Op R` is implied by current constraints |
| `bb_inf` | 3 | `bb_inf(IntVars, Expr, Inf)` — mixed-integer optimization via branch-and-bound |
| `dump_q` | 2 | `dump_q(Vars, Constraints)` — project constraint store onto Vars (Fourier-Motzkin) |

### in_q/1 and in_q/3

Declares one or more variables as rational-domain. If the variable already has a rational domain, intersects with the new bounds. Fails if the intersection is empty.

```clausal
# skip
in_q(X)                       % X in (-inf, +inf)
in_q(X, 0, 10)                % X in [0, 10]
in_q([X, Y, Z], 0, 100)       % all three in [0, 100]
```

When the bounds collapse to a point (`lo == hi`), the variable is automatically unified with that value.

### maximize/2 and minimize/2

Finds the optimum of a linear expression subject to all currently posted constraints. Unifies `Result` with the optimal objective value **and binds all constrained variables to their optimal assignments**. Fails if the problem is unbounded.

```clausal
# skip
% Classic linear program:
% maximize 30*X + 50*Y subject to:
%   2*X + Y <= 16
%   X + 2*Y <= 11
%   X + 3*Y <= 15
%   X, Y >= 0

lp(X, Y, OBJ) <- (
    in_q([X, Y], 0, 1000),
    2*X + Y <= 16,
    X + 2*Y <= 11,
    X + 3*Y <= 15,
    maximize(30*X + 50*Y, OBJ)
)
% -> X = 7, Y = 2, OBJ = 310  (all exact rationals, all bound)
```

### sup/2 and inf/2

Compute the upper or lower bound of a linear expression **without binding variables**. Useful for inspecting the feasible range or for implementing `entailed`.

```clausal
# skip
bounds(X, Lo, Hi) <- (
    in_q(X, 0, 100),
    X <= 10,
    X >= 3,
    inf(X, Lo),           % Lo = 3
    sup(X, Hi)            % Hi = 10
)
% X remains unbound — only Lo and Hi are set
```

### entailed/3

Tests whether a constraint is logically implied by the current store — i.e., whether it holds for **all** feasible points. Does not modify the store.

The first argument is the operator as a string: `"=<"`, `">="`, `"<"`, `">"`, `"="`, `"\\="`.

```clausal
# skip
test_entailed(X) <- (
    in_q(X, 0, 100),
    X <= 4,
    entailed("=<", X, 5),     % true: X <= 4 implies X <= 5
    \+ entailed("=<", X, 3)   % false: X could be 4, which is > 3
)
```

### bb_inf/3

Mixed-integer optimization: finds the minimum of a linear expression subject to the current constraints **and** the requirement that specified variables take integer values. Uses LP relaxation with branch-and-bound. Binds all constrained variables to their optimal integer assignments.

```clausal
# skip
% Minimum integer X such that X >= 3/2
int_min(X, Cost) <- (
    in_q(X, 0, 10),
    X >= 3/2,
    bb_inf([X], X, Cost)
)
% -> X = 2, Cost = 2

% SICStus example: min(X) with X >= Y + Z, Y > 1, Z > 1, all integer
sicstus_bb(X, Y, Z, Cost) <- (
    in_q([X, Y, Z], 0, 100),
    X >= Y + Z,
    Y >= 2,
    Z >= 2,
    bb_inf([X, Y, Z], X, Cost)
)
% -> X = 4, Y = 2, Z = 2, Cost = 4
```

### dump_q/2

Projects the constraint store onto a list of variables, eliminating all internal (slack) variables via Fourier-Motzkin elimination. Returns a list of constraint strings.

```clausal
# skip
show_constraints(X, Y, CS) <- (
    in_q([X, Y], 0, 100),
    2*X + Y <= 16,
    X + 2*Y <= 11,
    dump_q([X, Y], CS)
)
% CS = ["{2*X + Y =< 16}", "{X + 2*Y =< 11}", ...]
```

This is the feature that SWI-Prolog's CLP(Q) gets wrong — internal variables leak into answers. Clausal eliminates them correctly via Fourier-Motzkin.

---

## Constraint examples

### Linear equalities

```clausal
# skip
% Two-variable system: X + Y = 10, X = 3 -> Y = 7
two_var(X, Y) <- (
    in_q([X, Y], 0, 10),
    X + Y == 10,
    X == 3
)
% -> X = 3, Y = 7  (exact)
```

```clausal
# skip
% Three equations in three unknowns:
% X + Y + Z = 6, X - Y = 2, Y - Z = 1
three_var(X, Y, Z) <- (
    in_q([X, Y, Z], -100, 100),
    X + Y + Z == 6,
    X - Y == 2,
    Y - Z == 1
)
% -> X = 11/3, Y = 5/3, Z = 2/3  (exact fractions)
```

```clausal
# skip
% Rational coefficients: (1/2)*X + (1/3)*Y = 1, Y = 0
rational_coeffs(X, Y) <- (
    in_q([X, Y], -10, 10),
    1/2 * X + 1/3 * Y == 1,
    Y == 0
)
% -> X = 2, Y = 0
```

### Linear inequalities

```clausal
# skip
% Feasibility: X + Y <= 8, X <= 5, Y <= 6
feasible(X, Y) <- (
    in_q([X, Y], 0, 100),
    X + Y <= 8,
    X <= 5,
    Y <= 6
)
% Succeeds — the feasible region is non-empty
```

```clausal
# skip
% Infeasible: X >= 6 and X <= 4 is impossible
infeasible(X) <- (
    in_q(X, 0, 10),
    X >= 6,
    X <= 4
)
% Fails — no solution exists
```

### Optimization

```clausal
# skip
% Minimize cost subject to resource constraints
scheduling(X, Y, COST) <- (
    in_q([X, Y], 0, 100),
    X + Y >= 10,          % need at least 10 total
    2*X + Y <= 30,        % resource constraint 1
    X + 3*Y <= 40,        % resource constraint 2
    minimize(5*X + 3*Y, COST)
)
```

---

## How it works: algorithm overview

CLP(Q) uses a fundamentally different solver from CLP(R). Where CLP(R) narrows intervals via the HC4 algorithm, CLP(Q) solves systems of linear constraints exactly using two classical algorithms working in tandem.

### The three constraint types

| Constraint type | Algorithm | Example |
|---|---|---|
| **Equality** `Σ aᵢXᵢ = c` | Gaussian elimination | `X + Y == 10` |
| **Inequality** `Σ aᵢXᵢ <= c` | Revised simplex with slack variables | `2*X + Y <= 16` |
| **Disequality** `X != Y` | Passive check (fires when both ground) | `X != 5` |

All constraints must be **linear** — each term is a constant times a variable, with no products of variables. `3*X + 5*Y <= 10` is linear. `X * Y <= 10` is not, and will raise a `TypeError`.

### Why not interval arithmetic?

CLP(R) uses interval arithmetic: each variable has a range `[lo, hi]`, and constraints narrow these ranges. This works for non-linear constraints but has limitations for linear systems:

**Problem 1: Weak propagation.** Consider `X + Y = 10` with `X in [0, 10]` and `Y in [0, 10]`. Interval arithmetic narrows both to `[0, 10]` — no progress. It cannot deduce that if `X = 3` then `Y = 7` without labeling.

**Problem 2: No optimization.** Interval arithmetic has no native concept of "maximize this expression." You'd need to encode it as a constraint and binary-search, which is slow and approximate.

**Problem 3: Accumulating imprecision.** IEEE floats round every operation. After many constraints, the intervals may widen beyond usefulness.

Gaussian elimination + simplex solves all three problems: equalities are solved exactly by elimination, inequalities are decided by pivoting, and optimization is a direct extension of the simplex algorithm.

### Why not just simplex for everything?

The simplex method handles inequalities. You could convert every equality `a = b` into `a <= b` and `a >= b`, then use simplex for everything. But this is wasteful — each equality becomes two rows in the tableau, doubling the problem size and slowing pivoting.

The Holzbaur approach (which we implement) is more efficient: equalities are eliminated by Gaussian elimination first, reducing the number of free variables. The simplex only handles the remaining inequalities over the reduced system.

---

## How it works: Gaussian elimination

When an equality constraint `a₁X₁ + a₂X₂ + ... + aₙXₙ = c` is posted:

1. **Substitute** — replace any variables that were already eliminated by previous equalities
2. **Pick a pivot** — choose a variable to eliminate (prefer user variables over slacks, smallest coefficient for numerical stability)
3. **Solve** — express the pivot variable in terms of the others: `Xᵢ = (c - Σ aⱼXⱼ) / aᵢ`
4. **Substitute forward** — replace `Xᵢ` in all existing rows and other parametric definitions

The eliminated variable is now **parametric** — its value is determined by the remaining free variables.

### Worked example

**System:** `X + Y + Z = 6`, `X - Y = 2`, `Y - Z = 1`

**Step 1: Post `X + Y + Z = 6`.**

Coefficients: `{X: 1, Y: 1, Z: 1}`, constant: `6`.

Pick pivot: X (smallest ID). Solve: `X = 6 - Y - Z`.

X is now parametric: `X = -Y - Z + 6`.

**Step 2: Post `X - Y = 2`.**

Coefficients: `{X: 1, Y: -1}`, constant: `2`.

Substitute X (parametric): `X = -Y - Z + 6`, so:

`1·(-Y - Z + 6) + (-1)·Y = ?` after substituting the LHS constant moves to the RHS.

Result: `{Y: -2, Z: -1}`, constant: `2 - 6 = -4` (the parametric constant `6` is subtracted from the RHS because it appeared on the LHS).

Pick pivot: Z. Solve: `Z = (-4 - (-2)·Y) / (-1) = 4 - 2Y`.

Wait — let's be precise. The equation is `-2Y - Z = -4`. Solving for Z: `-Z = -4 + 2Y`, so `Z = 4 - 2Y`. In parametric form: `Z = {Y: -2} + 4`.

Also update X's parametric definition: substitute `Z = -2Y + 4`:

`X = -Y - (-2Y + 4) + 6 = -Y + 2Y - 4 + 6 = Y + 2`.

So now: `X = {Y: 1} + 2`, `Z = {Y: -2} + 4`.

**Step 3: Post `Y - Z = 1`.**

Coefficients: `{Y: 1, Z: -1}`, constant: `1`.

Substitute Z (parametric): `Z = -2Y + 4`:

`Y - (-2Y + 4) = 1` (the constant `4` from Z's definition moves to RHS).

`Y + 2Y = 1 + 4 = 5`, so `3Y = 5`.

Pick pivot: Y. Solve: `Y = 5/3`.

Y is now parametric with no free variables: `Y = {} + 5/3`. Its bounds are set to `[5/3, 5/3]` — a point. This triggers **implied binding**: `unify(Y, 5/3)`.

The hook then propagates: X depends on Y, so `X = 5/3 + 2 = 11/3`. Z depends on Y: `Z = -2·(5/3) + 4 = -10/3 + 12/3 = 2/3`. Both are bound.

**Final answer:** `X = 11/3`, `Y = 5/3`, `Z = 2/3`. All exact.

---

## How it works: the revised simplex method

### Setting up an inequality

When `Σ aᵢXᵢ <= c` is posted:

**Single-variable case** (`aX <= c`): simply tighten the upper bound of X to `c/a` (or lower bound if `a < 0`). No tableau row needed. This handles the very common case of simple bounds like `X <= 10`.

**Multi-variable case**: introduce a **slack variable** `s >= 0` such that:

`Σ aᵢXᵢ + s = c`

The slack `s` measures how much "room" remains before the inequality becomes tight. `s = 0` means the constraint is active (binding); `s > 0` means there's slack.

The slack becomes a new **basic variable** with a row in the tableau:

`s = c - Σ aᵢXᵢ`

### Feasibility check

After adding the slack, we check: is the slack non-negative under the current assignment? If yes, the new constraint is compatible — we're done. If no (the current point violates the inequality), we need to **restore feasibility** by pivoting.

### Pivoting

A **pivot** swaps a basic variable (one with a row) and a non-basic variable (one sitting at a bound). The swap preserves all equations but changes which variables are "free" (non-basic) and which are "determined" (basic).

Geometrically, a pivot moves along an edge of the feasible polyhedron from one vertex to an adjacent vertex.

### Restoring feasibility (dual simplex)

When a newly added constraint makes the current point infeasible:

1. Find the most infeasible basic variable (the one whose assignment is furthest below its lower bound)
2. Find an entering non-basic variable that, when increased via pivoting, would reduce the infeasibility
3. Pivot — the infeasible variable leaves the basis, the entering variable joins
4. Repeat until all basic variables are feasible, or detect infeasibility (no valid pivot exists)

**Bland's rule** prevents cycling: always choose the lowest-indexed eligible variable as the entering variable. This guarantees termination even on degenerate systems where pivots don't change the objective value.

### Worked example: LP optimization

**Problem:** maximize `30X + 50Y` subject to `2X + Y <= 16`, `X + 2Y <= 11`, `X + 3Y <= 15`, `X,Y >= 0`.

**Setup.** After posting `in_q([X, Y], 0, 1000)` and the three inequalities, the tableau has:

| Basic var | Row | RHS | Current value |
|---|---|---|---|
| s₁ | `s₁ = -2X - Y + 16` | 16 | 16 (feasible) |
| s₂ | `s₂ = -X - 2Y + 11` | 11 | 11 (feasible) |
| s₃ | `s₃ = -X - 3Y + 15` | 15 | 15 (feasible) |

Non-basic: X = 0 (at lower bound), Y = 0 (at lower bound).

Current objective: `30·0 + 50·0 = 0`. Not optimal — both X and Y have positive objective coefficients.

**Iteration 1.** Entering = X (first non-basic with positive obj coeff, Bland's rule with sorted IDs).

Ratio test — which basic variable first hits its lower bound (0) as X increases?

| Slack | Coeff of X | Current value | Ratio (value / |coeff|) |
|---|---|---|---|
| s₁ | -2 | 16 | 16/2 = 8 |
| s₂ | -1 | 11 | 11/1 = 11 |
| s₃ | -1 | 15 | 15/1 = 15 |

Minimum ratio = 8, leaving = s₁. **Pivot X ↔ s₁.**

After pivot, X is basic: `X = -s₁/2 - Y/2 + 8`. Non-basic: s₁ = 0, Y = 0.

New assignment: X = 8, Y = 0. Objective = 240.

Objective coefficients update: substitute X's new expression into `30X + 50Y`:

`30(-s₁/2 - Y/2 + 8) + 50Y = -15s₁ - 15Y + 240 + 50Y = -15s₁ + 35Y + 240`

Reduced costs: s₁ = -15 (non-positive, stay at bound), Y = 35 (positive, can improve).

**Iteration 2.** Entering = Y.

After substituting X into the other rows and computing ratios (details omitted), the minimum ratio determines which slack leaves. After pivoting, we reach:

**Optimal:** X = 7, Y = 2, s₁ = 0, s₂ = 0, s₃ = 2. Objective = 30·7 + 50·2 = **310**.

All reduced costs are non-positive — no non-basic variable can improve the objective. This is the optimum.

---

## How it works: linearization

Before a constraint reaches the Gaussian elimination or simplex, the expression tree (built from Clausal's `Add`, `Sub`, `Mult`, `Div`, `Negate` nodes) must be flattened to a linear form `{var_id: coefficient, ...} + constant`.

The `_linearize` function walks the expression tree:

| Node | Result |
|---|---|
| `int n` | `{}, Fraction(n)` |
| `Fraction f` | `{}, f` |
| `Var v` (unbound) | `{v._id: 1}, 0` |
| `Add(L, R)` | merge coefficients, add constants |
| `Sub(L, R)` | merge with negated R coefficients |
| `Mult(const, expr)` | scale all coefficients by const |
| `Mult(expr, const)` | scale all coefficients by const |
| `Mult(var, var)` | **rejected** — non-linear |
| `Div(expr, const)` | divide all coefficients by const |
| `Div(expr, var)` | **rejected** — non-linear |
| `Negate(expr)` | negate all coefficients and constant |

If linearization fails (non-linear expression), a `TypeError` is raised with a clear message.

---

## How it works: the Tableau data structure

The `Tableau` class is the core of the solver. It maintains the state of the entire constraint system as a single, shared, mutable object per trail.

```
Tableau
├── rows:        {basic_var_id: {non_basic_var_id: coeff, ...}}
├── rhs:         {basic_var_id: constant}
├── lo, hi:      {var_id: Fraction | None}  (bounds)
├── assign:      {var_id: Fraction}         (current assignment)
├── parametric:  {var_id: ({var_id: coeff}, constant)}  (Gaussian-eliminated vars)
├── diseqs:      [(var_id, var_id), ...]    (passive disequalities)
└── _var_map:    {var_id: Var}              (back-reference to logic variables)
```

**Invariants:**

- Basic variables have a row in `rows`. Their value is determined by `rhs - Σ row[v]·assign[v]`.
- Non-basic variables have no row. They sit at one of their bounds.
- Parametric variables were eliminated by equalities. They have an entry in `parametric` and no row.
- `assign[v]` always reflects the current solution point. For basic vars it's computed from the row; for non-basic vars it equals their current bound value.

---

## How it works: backtracking

CLP(Q) must integrate with Prolog's backtracking. When a choice point is explored and later abandoned, all constraints posted during that branch must be undone.

The Tableau is **mutable shared state** — there's one per trail, not one per variable. This makes backtracking non-trivial: you can't just undo per-variable attributes (as CLP(R) does with its per-variable `RealVar`).

**Copy-on-write via `trail.record()`:**

Before each constraint modification, the entire Tableau is deep-copied. The copy is captured in a closure and pushed onto the trail:

```python
def _snapshot_tableau(trail):
    tid = id(trail)
    old = _tableaux[tid].copy()
    trail.record(lambda: _tableaux.__setitem__(tid, old))
```

When `trail.undo(mark)` is called, the closure fires, replacing the current Tableau with the snapshot. All subsequent operations see the pre-modification state.

**Cost:** `O(n)` per snapshot where `n` is the total number of variables and constraints. For typical CLP(Q) problems (tens of variables), this is negligible. For very large systems (hundreds of variables), the copy dominates — but such systems rarely arise in logic programming.

---

## How it works: the attribute hook

Each CLP(Q) variable carries a `QVar` attribute under the key `"clpq"`:

```python
class QVar:
    __slots__ = ('lo', 'hi', 'tab_id')
    lo: Fraction | None    # lower bound (None = unbounded)
    hi: Fraction | None    # upper bound (None = unbounded)
    tab_id: int            # variable's ID in the Tableau
```

When a Q-constrained variable is unified (bound to a value or another variable), the **attribute hook** `_q_hook` fires:

| Unified with | Action |
|---|---|
| `int` or `Fraction` | Check bounds, then substitute the value into the Tableau via `fix_variable`. Propagate implied bindings. |
| Another Q-variable | Intersect bounds, then add equality `X = Y` to the Tableau. Propagate implied bindings. |
| Q-variable without attribute | Transfer the `QVar` attribute to the other variable. |
| `bool` or non-numeric | **Fail.** |

### Implied bindings (chain propagation)

After a Gaussian elimination step, some variables may become fully determined — their parametric definition reduces to a constant (all dependencies are themselves resolved). The `_propagate_determined` method detects these and sets their bounds to `[val, val]`. Then `check_implied_bindings` scans for any variable whose bounds have collapsed to a point and calls `unify` on it, which fires the hook again. This chain continues until no more variables are determined.

---

## How it works: dispatch from fd_eq, fd_le, etc.

The dispatch chain in `clpfd.py` (and the C extension `_clpfd_propagate.c`):

```
fd_eq(l, r, trail):
    1. Fast path: type(l) is int and type(r) is int → Python ==
    2. _resolve expression trees
    3. _any_rational(l, r) → CLP(Q) via q_eq        [NEW]
    4. _any_real(l, r)     → CLP(R) via real_eq
    5. Expression linearization → ScalarProductConstraint
    6. _both_ground(l, r)  → Python ==
    7. At least one Var    → CLP(Z) EqConstraint
```

`_any_rational` checks: is either operand a `Fraction` instance, or a `Var` with a `"clpq"` attribute?

The C extension mirrors this check. During module initialization, it imports `_any_rational` from the Python `clpfd` module and `q_eq`, `q_ne`, `q_lt`, `q_le` from `clpq`. The dispatch in C calls the Python functions through the C-API.

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

1. **Ill-conditioned systems** where the coefficient matrix determinant is close to zero. Gaussian elimination amplifies small differences.
2. **Many pivot steps** in the simplex method. Each pivot divides by the pivot coefficient, potentially increasing denominators.

**Mitigation strategies:**

- Python's `Fraction` normalizes automatically (GCD reduction on every operation)
- For most CLP(Q) usage (systems of 5-20 variables), coefficient growth is manageable
- If growth becomes a problem, consider CLP(R) for the approximate part and CLP(Q) only where exactness is required
- The solver does not artificially limit precision — it will compute correct answers at the cost of speed

This is exactly the trade-off SICStus Prolog documents: "you may be out of space particularly soon" for iterative rational computations. The SICStus documentation recommends switching to CLP(R) when precision is not critical.

---

## Comparison with other systems

| Feature | SICStus CLP(Q) | SWI CLP(Q) | ECLiPSe | **Clausal CLP(Q)** |
|---|---|---|---|---|
| Correctness | Reference impl | Orphaned, bugs | No CLP(Q) | **Clean-room from papers** |
| Algorithm | Holzbaur Gaussian+simplex | Port of SICStus | — | **Holzbaur Gaussian+simplex** |
| Arithmetic | GMP rationals | SWI rationals | — | **Python `Fraction`** |
| Optimization | `maximize/1`, `minimize/1` | Same (buggy) | — | **`maximize/2`, `minimize/2`** |
| Bounds query | `sup/1`, `inf/1` | Same | — | **`sup/2`, `inf/2`** |
| Entailment | `entailed/1` | Same | — | **`entailed/3`** |
| MIP | `bb_inf/3`, `bb_inf/5` | Same | — | **`bb_inf/3`** |
| Projection | Fourier-Motzkin | Broken | — | **`dump_q/2` (Fourier-Motzkin)** |
| Non-linear | Deferred | Deferred | — | **Rejected (TypeError)** |
| Syntax | `{X + Y =< 8}` | Same | — | **`X + Y <= 8`** (unified) |
| int/int | Stays integer | Stays integer | — | **Produces Fraction** |

### Historical context

**Holzbaur (1992, 1994, 1995)** at OFAI Vienna created the definitive CLP(Q,R) implementation for SICStus Prolog. His algorithm combines Gaussian elimination for equalities with the revised simplex method for inequalities, with incremental constraint addition and detection of fixed (determined) variables. Our implementation is based on these published papers.

**SWI-Prolog's CLP(Q)** is a port of Holzbaur's code by Leslie De Koninck. It is officially "orphaned" (no maintainer) and has known bugs, including a projection failure reported by Markus Triska where internal variables leak into answers.

**Prolog III** (Colmerauer, 1989) had a complete solver for linear arithmetic over rationals using Gaussian elimination. Guy Narboni documented the coefficient growth problem in "About Gaussian elimination and infinite precision" (1992). Prolog IV (1996) extended this with interval narrowing for non-linear constraints.

**The Parma Polyhedra Library** (Bagnara et al.) provides an open-source exact-arithmetic simplex in C++ using GMP rationals. It serves as a correctness oracle for exact LP solvers.

Our implementation is a **clean-room** design based on the published papers (Holzbaur 1992, 1994), not derived from any existing source code. SICStus is proprietary; SWI's CLP(Q) is GPL-2.

---

## Interaction with CLP(Z) and CLP(R)

### Type promotion lattice

```
int ──→ Fraction  (exact, via Fraction(n))
int ──→ float     (lossy for large ints, via float(n))
float ──✗──→ Fraction  (BLOCKED — lossy, raises TypeError)
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

```clausal
# skip
% X is integer-constrained AND participates in a rational equation
mixed(X, Y) <- (
    in_domain(X, 1, 10),        % CLP(Z): X in {1..10}
    in_q(Y, 0, 10),             % CLP(Q): Y in [0, 10]
    X + Y == 10,                % Q dispatch (Y has Q attr)
    Y == 7                      % → X = 3 (integer, accepted by both FD and Q)
)
```

### Dispatch table

| Situation | Behaviour |
|---|---|
| `in_q(X, 0, 10)` then `X == 3` | CLP(Q): X has `"clpq"` attribute, `3` is treated as `Fraction(3)` |
| `in_domain(X, 1, 10)` then `X == 1/3` | CLP(Q): `1/3` triggers Q dispatch; FD var promoted to Q with bounds `[1, 10]` |
| `in_domain(X, 1, 10)` then `X == 1/2` | **Fails**: `Fraction(1,2)` is not integer, FD hook rejects |
| `in_real(X, 0.0, 10.0)` then `X == 1/3` | CLP(Q): Fraction takes priority over float |
| `in_real(X, 0.0, 10.0)` then `in_q(X, ...)` | **TypeError**: cannot mix float and Fraction domains |
| `X == 5` (no declaration) | CLP(Z): both sides are `int` |
| `X == 5.0` (no declaration) | CLP(R): float literal triggers R dispatch |
| `X == 1/3` (no declaration) | CLP(Q): Fraction literal triggers Q dispatch |

---

??? abstract "QVar — per-variable state"

    Each constrained variable stores a `QVar` as an attributed-variable attribute under the key `"clpq"`:

    ```python
    class QVar:
        __slots__ = ('lo', 'hi', 'tab_id')
        lo: Fraction | None    # None means unbounded below
        hi: Fraction | None    # None means unbounded above
        tab_id: int            # this variable's ID in the global Tableau
    ```

    Unlike CLP(R)'s `RealVar` which stores constraints per-variable, CLP(Q) stores all constraints in the **global Tableau**. The `QVar` just holds bounds and a reference into the tableau.

    **Trail safety:** `QVar` is immutable. Narrowing creates a new `QVar` via `put_attr(var, "clpq", new_state, trail)`. The old state is restored on `trail.undo()`. The Tableau itself is snapshot-restored separately via `trail.record()`.

??? abstract "Tableau invariants"

    The Tableau maintains these invariants:

    1. **Basic variables** have a row. Their assignment is `rhs[bv] - Σ row[bv][v] * assign[v]`.
    2. **Non-basic variables** sit at one of their bounds. Their assignment equals that bound value.
    3. **Parametric variables** were eliminated by Gaussian. Their value is `pk + Σ pc[v] * assign[v]`.
    4. **Slack variables** use negative IDs to avoid collisions with user variable IDs (which are positive).
    5. **All assignments are consistent.** After every operation, `assign[v]` matches the value computed from the rows/parametric definitions.
    6. **Feasibility.** After successful constraint addition, all basic variables satisfy their bounds.

??? abstract "Substitution direction"

    A subtle point in the implementation: when substituting a parametric variable `X = Σ aⱼYⱼ + k` into an equation `Σ cᵢZᵢ = d`, the parametric constant `k` is on the **left-hand side** (it's part of X's expansion). It must be moved to the right by **subtracting** it from the equation's constant:

    ```
    Original:  cₓ·X + ... = d
    Substitute X = Σ aⱼYⱼ + k:
               cₓ·(Σ aⱼYⱼ + k) + ... = d
               cₓ·Σ aⱼYⱼ + cₓ·k + ... = d
               cₓ·Σ aⱼYⱼ + ... = d - cₓ·k
    ```

    Getting this sign wrong is a classic implementation bug (SWI-Prolog's CLP(Q) has related issues). Our implementation explicitly subtracts: `new_k -= coeff * pk`.

??? abstract "Pivot mechanics"

    The pivot operation swaps a basic variable (leaving) and a non-basic variable (entering):

    ```
    Before: leaving = Σ row[v]·v + rhs     (entering is one of v)
    Solve:  entering = (leaving - Σ other·v - rhs) / row[entering]
    ```

    Note the sign: `new_rhs = -rhs / pivot_coeff`, not `+rhs / pivot_coeff`. The leaving variable's constant is on the left side of the equation, so dividing it out negates it.

    After the pivot:
    1. The leaving variable becomes non-basic at its lower bound
    2. The entering variable gets a new row
    3. All other rows that contained the entering variable are updated by substitution
    4. All basic variable assignments are recomputed from their rows

??? example "Usage examples"

    **LP optimization:**

    ```clausal
    # skip
    LP(X, Y, OBJ) <- (
        in_q([X, Y], 0, 1000),
        2*X + Y <= 16,
        X + 2*Y <= 11,
        X + 3*Y <= 15,
        maximize(30*X + 50*Y, OBJ)
    )
    % -> X = 7, Y = 2, OBJ = 310
    ```

    **Backtracking (constraints are undone when a branch fails):**

    ```clausal
    # skip
    % First branch: X = 5.  Second branch: X = 3.
    % Each branch sees only its own constraints.
    choice(X) <- (
        in_q(X, 0, 10),
        X == 5
    )
    choice(X) <- (
        in_q(X, 0, 10),
        X == 3
    )
    ```

    **Inspecting variable state (Python runtime API):**

    ```python
    # This is specific to the Python runtime — not Clausal syntax.
    from clausal.logic.clpq import Q_KEY
    from clausal.logic.variables import get_attr

    state = get_attr(var, Q_KEY)
    if state is not None:
        print(f"[{state.lo}, {state.hi}]")  # current bounds
        print(f"tableau ID: {state.tab_id}")
    ```

---

??? info "Test coverage"

    Tests are in `tests/test_clpq.py` (105 tests).

    - **Dispatch**: Fraction triggers CLP(Q), int stays CLP(Z), float stays CLP(R)
    - **Domain declaration**: `in_q` basic, narrowing, infeasible, point binding, list form, unbounded, ground check
    - **Ground constraints**: all six comparison operators on ground rationals
    - **Variable binding**: `q_eq(X, Fraction)` binds X
    - **Linear equalities**: two-var, three-var (exact fractions), contradictory, redundant, rational coefficients, scaled (`2*X = 1 -> X = 1/2`), large coefficients (`999999*X = 1`)
    - **Linear inequalities**: simple le, infeasible system, two-var feasibility, redundant, zero coefficients
    - **Backtracking**: undo restores unbound, undo restores bounds, undo restores full tableau state; maximize/minimize backtrack correctly
    - **Optimization**: maximize simple, minimize simple, classic LP (30X + 50Y, answer 310), variables bound to optimal point
    - **sup/inf**: simple bounds, LP bounds, does not bind variables
    - **entailed**: `=<`, `>=`, `=`, `\=` entailment; does not modify store; does not add Q attributes to bare variables
    - **Disequality**: `q_ne` prevents binding to excluded value, allows other values; strict `q_lt` rejects equal; two-var disequality; backtrack restores
    - **Pivot/simplex**: upper-bound inequality feasibility, infeasible upper-bound detection, degenerate vertex, contradictory multi-var inequalities
    - **Projection**: `dump_q` simple bounds, inequality projection (no internal var leakage), equality projection, empty store
    - **Branch-and-bound**: `bb_inf` simple integer, LP integer, no integer constraint, infeasible, already integer, mixed integer, multi-level branching, variable binding
    - **Linearization**: constants, ints, vars, add, scalar mult, non-linear rejection, negate
    - **Coefficient growth**: Newton sqrt(2) to 12-digit fractions, large coefficient constraints
    - **Float type safety**: `TypeError` raised when Q-variable unified with float
    - **Snapshot dedup**: multi-step operation undoable as single unit
    - **End-to-end Clausal**: all doc examples compiled and run through full pipeline (7 integration tests)

---

## References

- Holzbaur, C. (1992). "An algorithm for linear constraint solving: its incorporation in a Prolog meta-interpreter for CLP." *Journal of Logic Programming*.
- Holzbaur, C. (1994). "A specialized incremental solved form algorithm for systems of linear inequalities." OFAI TR-94-07, Vienna.
- Holzbaur, C. (1995). "OFAI CLP(Q,R) Manual, Edition 1.3.3." OFAI TR-95-09, Vienna.
- Refalo, P. (1998). "Approaches to the incremental detection of implicit equalities with the revised simplex method." *Lecture Notes in Computer Science*.
- Narboni, G.A. (1992). "About Gaussian elimination and infinite precision." 2nd International Workshop on Constraint Logic Programming, Marseille.
- Narboni, G.A. (1999). "From Prolog III to Prolog IV: the Logic of Constraint Programming Revisited." *Constraints* journal.
