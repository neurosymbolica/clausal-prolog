# CLP(Q) — Constraint Logic Programming over Rationals

Implementation plan for CLP(Q) in Clausal: exact rational constraint solving via
Gaussian elimination and the revised simplex method, integrated with the existing
CLP(Z)/CLP(R) dispatch infrastructure, with `int/int` defaulting to `Fraction`.

---

## Background: The CLP(Q) landscape

### Historical roots

**CLP(R) / CLP(Q) (1987)** — Jaffar, Lassez, and Michaylov at IBM/Monash. The
original constraint logic programming systems over reals and rationals. CLP(Q)
used exact rational arithmetic with the simplex method for linear inequality
solving. Non-linear constraints were deferred.

**Prolog III (1989)** — Alain Colmerauer's system at Aix-Marseille. Had a
complete solver for linear arithmetic over rationals using Gaussian elimination.
Also integrated Boolean constraints and tree constraints. **Guy Narboni**
worked on the infinite-precision Gaussian elimination and documented the
**coefficient growth problem**: iterative rational computations can cause
numerator/denominator sizes to grow exponentially (see "About Gaussian
elimination and infinite precision", 1992).

**Prolog IV (1996)** — Extended Prolog III with interval narrowing for non-linear
constraints. Documented in Colmerauer & Narboni, "From Prolog III to Prolog IV:
the Logic of Constraint Programming Revisited" (Constraints journal, 1999).

**Holzbaur CLP(Q,R) (1992-1995)** — Christian Holzbaur at OFAI Vienna. This
became the definitive implementation, used by SICStus Prolog. Three key papers:

1. **Holzbaur 1992** — "An algorithm for linear constraint solving" (Journal of
   Logic Programming). Combines Gaussian elimination (equalities) with simplex
   (inequalities), with detection of *fixed variables* whose values become
   determined during elimination.
2. **Holzbaur 1994** — "A specialized incremental solved form algorithm for
   systems of linear inequalities" (OFAI TR-94-07). The incremental simplex
   adapted for CLP's constraint-at-a-time posting and Prolog backtracking.
3. **Holzbaur 1995** — "OFAI CLP(Q,R) Manual" (OFAI TR-95-09). Reference
   implementation manual.

**Robert Bagnara** created the **Parma Polyhedra Library (PPL)** — an open-source
C++ library that includes an exact-arithmetic simplex algorithm for convex
polyhedra operations over GMP rationals. Well-tested and formally sound; useful
as a correctness oracle.

**Refalo 1998** — "Approaches to the Incremental Detection of Implicit Equalities
with the Revised Simplex Method". Compares three approaches (CLP(R) style,
Prolog III Gaussian, quasi-dual revised simplex) and confirms that the revised
simplex is superior for CLP's incremental nature.

### The SICStus question

**SICStus Prolog is the only system with a fully correct CLP(Q)** (per Markus
Triska). SWI-Prolog's CLP(Q) is a port of Holzbaur's code by Leslie De Koninck,
but it is **orphaned** (no maintainer) and has known bugs:

- **Projection failure**: `{X < Y}` returns `{Y=X+_2220, _2220>0}` instead of
  projecting away internal variables to give `{X-Y<0}`. (Issue reported by
  Triska himself.)
- **Fourier-Motzkin projection** for variable elimination is broken.
- **Disequations not projected** properly.

SICStus is proprietary (binary-only, anti-reverse-engineering license clause).
We **cannot** look at SICStus source code.

**Our approach: clean-room implementation from published papers.** Copyright
protects expression (code), not ideas (algorithms). The Holzbaur papers describe
the algorithm in sufficient detail. SICStus documentation provides the expected
API and behavior. SWI-Prolog's open-source test cases provide correctness targets.
SWI-Prolog's CLP(Q,R) source (GPL-2) can be studied for understanding but we
must not create derivative code.

### The coefficient growth problem

This is inherent to exact rational arithmetic and is the concern Triska raised.
Demonstrated by Newton's method for sqrt(2):

| Iterations | Approximation      | Digit count (num/denom) |
|:----------:|:------------------:|:-----------------------:|
| 3          | 577/408            | 3 / 3                  |
| 4          | 665857/470832      | 6 / 6                  |
| 5          | 886731088897/627013566048 | 12 / 12           |
| 6          | ~25-digit / ~25-digit | 25 / 25              |
| 15         | ~12543-digit each  | 12543 / 12543           |

Each step multiplies/divides existing rationals, and GCD reduction doesn't
always shrink them enough. **There is no general mitigation** — SICStus's own
documentation says "switch to CLP(R) if this becomes a problem."

Strategies we can employ:
- Python's `Fraction` is arbitrary precision — no overflow, just slowness
- Optional `max_denominator` safety valve (non-default, user opt-in)
- Periodic GCD normalization (Python's Fraction does this automatically)
- Document the trade-off clearly in user-facing docs

---

## Design overview

### Architecture

CLP(Q) uses a fundamentally different solver from CLP(R). Where CLP(R) uses
**interval narrowing** (HC4), CLP(Q) uses **Gaussian elimination** for equalities
and the **revised simplex method** for inequalities. This is correct because:

- Intervals over rationals would be exact but would not propagate equalities
  across multi-variable systems (e.g., `X + Y = 10, X - Y = 2` → `X = 6, Y = 4`)
- The simplex method gives us optimization (maximize/minimize) for free
- Holzbaur's algorithm is proven correct for incremental constraint addition

### Data flow

```
User writes in .clausal:
    in_q([X, Y], 0, 10),
    X + 2*Y <= 14,
    3*X + Y <= 14,
    X + Y <= 8,
    maximize(X + Y, OBJ)

Compiled to Python (via compiler.py):
    _in_q([X, Y], Fraction(0), Fraction(10), trail)
    _fd_le(Add(X, Mult(Fraction(2), Y)), Fraction(14), trail)
    ...
    _maximize(Add(X, Y), OBJ, trail)

Runtime dispatch (clpfd.py fd_le):
    detects Fraction → dispatches to q_le(...)

CLP(Q) solver (clpq.py):
    linearize expression → {X: 1, Y: 2} <= 14
    add to global Tableau
    check feasibility via simplex
    on maximize: Phase II simplex → X = 2, Y = 6, OBJ = 8
```

### The Holzbaur algorithm in detail

The solver maintains two structures simultaneously:

**1. Equality subsystem (Gaussian elimination)**

When an equality `a₁X₁ + a₂X₂ + ... + aₙXₙ = c` is posted:
- Pick the variable with the smallest coefficient (pivot variable)
- Solve for it: `Xᵢ = (c - Σ aⱼXⱼ) / aᵢ`  (j ≠ i)
- Substitute this expression for `Xᵢ` into ALL other equalities and
  inequalities in the system
- `Xᵢ` is now "parametric" — defined in terms of other variables

This is standard Gaussian elimination done incrementally, one equation at a
time. After each elimination step:
- Check if any variable has become **fixed** (appears in zero remaining
  constraints and has a determined value) → bind it via `unify`
- Check for contradiction (0 = nonzero constant) → fail

**2. Inequality subsystem (revised simplex)**

When an inequality `a₁X₁ + a₂X₂ + ... + aₙXₙ ≤ c` is posted:
- Introduce a slack variable `s ≥ 0`: `a₁X₁ + ... + aₙXₙ + s = c`
- The slack becomes a new basic variable; the original vars are non-basic
- Check if this is immediately feasible (does the current assignment satisfy
  the new constraint?)
- If not: use the **dual simplex method** to restore feasibility — pivot to
  find a feasible basis, or detect infeasibility (→ fail)

The **revised simplex** (vs. tableau simplex) stores the basis inverse
implicitly, which is more memory-efficient and better suited to incremental
constraint addition.

**Anti-cycling: Bland's rule.** Always choose the lowest-indexed eligible
variable to enter/leave the basis. This guarantees termination even with
degenerate systems (where a pivot doesn't change the objective value).

**3. Disequalities (passive)**

`X ≠ Y` constraints are stored passively. They are only checked when both
sides become ground. If they become equal → fail. This matches SICStus
behavior.

**4. Optimization (Phase II simplex)**

`maximize(Expr)` / `minimize(Expr)`:
- Linearize `Expr` to get objective coefficients
- Run Phase II simplex on the current tableau with this objective
- The optimal value and variable assignments are extracted from the final basis

### Trail integration (backtracking)

The tableau is a **global object shared across all Q-constrained variables**
on a given trail. This is necessary because the simplex needs the full system.

**Copy-on-write strategy:**
- Before each constraint addition that modifies the tableau, take a snapshot
  (deep copy of the relevant dicts)
- Store the snapshot on the trail via `put_attr` on a sentinel variable
- On `trail.undo()`, the old snapshot is restored

The cost of copying is proportional to the number of variables/constraints in
the current system. For typical CLP(Q) usage (10s of variables), this is cheap.
For very large systems (100s+), we may later optimize to incremental undo.

---

## Syntax and dispatch

### `int/int` → `Fraction` (the key syntax change)

**All integer-divided-by-integer expressions produce `Fraction` in Clausal.**

This is implemented at compile time in `arith_to_ast_expr` (`compiler.py:1538`).
When we see a `Div` node where both operands are integer constants, we emit
`Fraction(n, d)` instead of `n / d`.

This applies everywhere — constraints (`==`, `<`, etc.) AND eager evaluation
(`:=`). Users write `7.0 / 2` if they want float division.

```clausal
# These all produce Fraction:
X := 1/3           # Fraction(1, 3)
X := 7/2           # Fraction(7, 2)
X == 1/3           # constraint with Fraction(1, 3)

# These produce float (unchanged):
X := 1.0/3         # 0.333...
X := 7/2.0         # 3.5
```

**Implementation in `compiler.py`:**

```python
# In arith_to_ast_expr, BEFORE the _ARITH_BINOP_MAP loop (around line 1555):

if isinstance(term, Div):
    # int/int → Fraction(n, d) for exact rational arithmetic
    if isinstance(term.left, int) and not isinstance(term.left, bool) \
       and isinstance(term.right, int) and not isinstance(term.right, bool):
        return ast.Call(
            func=ast.Name(id='_Fraction', ctx=ast.Load()),
            args=[ast.Constant(value=term.left),
                  ast.Constant(value=term.right)],
            keywords=[],
        )
```

And in `base_globals` (around line 5593):
```python
from fractions import Fraction as _Fraction_cls
base_globals["_Fraction"] = _Fraction_cls
```

Also handle `Fraction` as a literal type:
```python
# In arith_to_ast_expr, line 1552:
if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
    return ast.Constant(value=term)
```

### Dispatch chain

The existing dispatch in `clpfd.py` follows this priority:

```
fd_eq(l, r, trail):
    1. Fast path: both int → Python ==
    2. _resolve expression trees
    3. _any_real → CLP(R)
    4. Linearize → ScalarProductConstraint
    5. _both_ground → Python ==
    6. At least one Var → CLP(Z) EqConstraint
```

We insert **CLP(Q) dispatch before CLP(R)** (rational takes precedence over
approximate). The rationale: if a user mixes Fraction and float, exactness
should win.

```python
# In clpfd.py, new functions around line 1149:

from fractions import Fraction

def _is_rational_arg(x) -> bool:
    """True if x is a Fraction or a Var with a rational-domain attribute."""
    x = deref(x)
    if isinstance(x, Fraction):
        return True
    if is_var(x):
        from clausal.logic.clpq import Q_KEY
        return get_attr(x, Q_KEY) is not None
    return False

def _any_rational(l, r) -> bool:
    """True if either argument should use CLP(Q) dispatch."""
    return _is_rational_arg(l) or _is_rational_arg(r)
```

Then in each `fd_*` function:

```python
def fd_eq(l, r, trail):
    # ... existing fast path and _resolve ...
    if _any_rational(l, r):                    # NEW: before _any_real
        from clausal.logic.clpq import q_eq
        return q_eq(l, r, trail)
    if _any_real(l, r):                        # existing
        from clausal.logic.clpr import real_eq
        return real_eq(l, r, trail)
    # ... rest unchanged ...
```

Same pattern for `fd_ne`, `fd_lt`, `fd_le`, `fd_gt`, `fd_ge`.

### `_resolve` must handle Fraction

The `_resolve` function (`clpfd.py:1165`) evaluates ground expression trees.
Currently it only handles int results. When `int/int` produces `Fraction`,
`_eval_ground` needs to handle `Fraction` values in expression trees.

```python
# In _resolve and _eval_ground: handle Fraction alongside int
# A Div(3, 2) node will have left=3, right=2 as ints, but after
# the compiler change, a ground Div where both are int will already
# be compiled as Fraction(3,2) at the AST level.
# However, expression trees like Add(x, Fraction(1,2)) where x
# is bound to Fraction(3,2) at runtime need _resolve to compute
# Fraction(3,2) + Fraction(1,2) = Fraction(2,1).
```

### Builtins registration

CLP(Q) builtins are registered via the `@_builtin` decorator in
`clausal/logic/builtins/constraints.py` — the same file that registers
`in_real`, `label_real`, `in_domain`, etc. This is **not** done via
`base_globals` in `compiler.py` (that's for constraint dispatch functions
like `_fd_eq`).

**File:** `clausal/logic/builtins/constraints.py`

```python
# ── CLP(Q) builtins ─────────────────────────────────────────────────────────

@_builtin("in_q", 1)
def _in_q__1(var_or_list, trail, k):
    """in_q(Var) — declare rational variable with unbounded domain."""
    from clausal.logic.clpq import in_q as _in_q_fn
    if _in_q_fn(var_or_list, None, None, trail):
        yield None

@_builtin("in_q", 3)
def _in_q__3(var_or_list, lo, hi, trail, k):
    """in_q(Var, Lo, Hi) — declare rational variable with domain [Lo, Hi]."""
    from clausal.logic.clpq import in_q as _in_q_fn
    if _in_q_fn(var_or_list, lo, hi, trail):
        yield None

@_builtin("maximize", 2)
def _maximize__2(expr, result, trail, k):
    """maximize(Expr, Result) — find maximum of linear expression."""
    from clausal.logic.clpq import maximize as _maximize_fn
    if _maximize_fn(expr, result, trail):
        yield None

@_builtin("minimize", 2)
def _minimize__2(expr, result, trail, k):
    """minimize(Expr, Result) — find minimum of linear expression."""
    from clausal.logic.clpq import minimize as _minimize_fn
    if _minimize_fn(expr, result, trail):
        yield None
```

**How `@_builtin` works:** The decorator registers a Python generator function
in a global registry keyed by `(name, arity)`. When the compiler encounters a
call like `in_q(X, 0, 10)`, it looks up `("in_q", 3)` in the registry and
emits a trampoline call to the registered generator. The `trail` and `k`
(continuation) arguments are injected by the compiler.

**Expression passing:** For `maximize(3*X + 5*Y, Result)`, the first argument
is an **unevaluated expression tree** (`Add(Mult(Fraction(3), X), Mult(Fraction(5), Y))`),
not a computed value. This is because the compiler passes constraint arguments
with `eval_arith=False` (see `compiler.py:2188`). The `maximize` function
receives the tree and calls `_linearize` on it.

**Gotcha:** `maximize` and `minimize` are common names. We should check for
conflicts with any existing builtins. Currently there are none in the codebase.

---

## Module structure: `clausal/logic/clpq.py`

### Constants and state

```python
"""clausal.logic.clpq — CLP(Q) rational-domain constraint solver.

Exact arithmetic over Python Fraction via Gaussian elimination (equalities)
and the revised simplex method (inequalities). Unified syntax with CLP(Z)
and CLP(R): the same ==, <, <=, >, >=, != operators dispatch to CLP(Q)
when a Fraction literal or in_q-declared variable is detected.

Trail safety: The Tableau is snapshot-copied before each modification.
Snapshots are restored on backtrack via the trail's attribute mechanism.
"""

from fractions import Fraction
from collections import deque
from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify,
    put_attr, get_attr, del_attr, register_attr_hook,
)

Q_KEY = "clpq"
ZERO = Fraction(0)
ONE = Fraction(1)
```

### QVar: per-variable rational-domain state

```python
class QVar:
    """Rational-domain state for one variable.

    Immutable for trail safety. Stores optional bounds [lo, hi] and the
    variable's ID in the global tableau. A QVar with lo == hi is "fixed"
    and should be bound.
    """
    __slots__ = ('lo', 'hi', 'tableau_id')

    def __init__(self, lo: Fraction | None, hi: Fraction | None,
                 tableau_id: int | None = None):
        self.lo = lo    # None means -inf
        self.hi = hi    # None means +inf
        self.tableau_id = tableau_id
```

Note: unlike CLP(R)'s `RealVar` which stores constraints per-variable, CLP(Q)
stores constraints in the **global Tableau**. The `QVar` just holds bounds and
a reference into the tableau.

### Tableau: the simplex solver

```python
class Tableau:
    """Incremental solver for linear constraints over exact rationals.

    Combines Gaussian elimination (equalities) with the revised simplex
    method (inequalities).

    Terminology:
    - "basic variable": currently expressed in terms of non-basic variables
    - "non-basic variable": currently at their bound (lower or upper)
    - "parametric": eliminated by Gaussian elimination, defined by an equation

    Data structures:
    - rows: dict[int, dict[int, Fraction]]
        For each basic variable (by ID): its expression as a linear
        combination of non-basic variables. row[i][j] = coefficient of
        var j in the equation defining basic var i.
    - rhs: dict[int, Fraction]
        The constant term for each basic variable's equation.
    - lo, hi: dict[int, Fraction | None]
        Lower and upper bounds for all variables (basic and non-basic).
    - assign: dict[int, Fraction]
        Current assignment for all variables. For non-basic: their current
        value (at one of their bounds). For basic: computed from the row.
    - parametric: dict[int, tuple[dict[int, Fraction], Fraction]]
        Eliminated (equality) variables: var_id → ({coeffs}, constant)
        meaning var = sum(coeffs[j] * var_j) + constant
    - diseqs: list[tuple[int, int]]
        Passive disequality pairs (checked when both become ground).
    """

    def __init__(self):
        self.rows: dict[int, dict[int, Fraction]] = {}
        self.rhs: dict[int, Fraction] = {}
        self.lo: dict[int, Fraction | None] = {}
        self.hi: dict[int, Fraction | None] = {}
        self.assign: dict[int, Fraction] = {}
        self.parametric: dict[int, tuple[dict[int, Fraction], Fraction]] = {}
        self.diseqs: list[tuple[int, int]] = []
        self._next_slack: int = 0
        self._var_map: dict[int, Var] = {}  # id → Var object

    def copy(self) -> 'Tableau':
        """Deep copy for trail snapshots."""
        t = Tableau()
        t.rows = {k: dict(v) for k, v in self.rows.items()}
        t.rhs = dict(self.rhs)
        t.lo = dict(self.lo)
        t.hi = dict(self.hi)
        t.assign = dict(self.assign)
        t.parametric = {k: (dict(c), v) for k, (c, v) in self.parametric.items()}
        t.diseqs = list(self.diseqs)
        t._next_slack = self._next_slack
        t._var_map = dict(self._var_map)
        return t

    def fresh_slack(self) -> int:
        """Allocate a fresh slack variable ID (negative to avoid clash)."""
        self._next_slack += 1
        return -self._next_slack  # negative IDs for slack vars
```

### Tableau internal helpers

These are the internal methods referenced by the main operations:

```python
    def _substitute_parametric(self, coeffs: dict[int, Fraction],
                               constant: Fraction) -> tuple[dict[int, Fraction], Fraction]:
        """Replace parametric (equality-eliminated) variables in a linear expression.

        If var X was eliminated by an equality and defined as
            X = a₁Y₁ + a₂Y₂ + c
        then any occurrence of X in coeffs is replaced by expanding its definition.

        Returns: (new_coeffs, new_constant) with no parametric vars remaining.
        """
        new_coeffs = {}
        new_const = constant
        for var_id, coeff in coeffs.items():
            if var_id in self.parametric:
                param_coeffs, param_const = self.parametric[var_id]
                # X appears with coefficient `coeff`, expand:
                # coeff * X = coeff * (sum(param_coeffs[j] * Xj) + param_const)
                for pv, pc in param_coeffs.items():
                    new_coeffs[pv] = new_coeffs.get(pv, ZERO) + coeff * pc
                new_const += coeff * param_const
            else:
                new_coeffs[var_id] = new_coeffs.get(var_id, ZERO) + coeff
        # Clean zeros
        return {v: c for v, c in new_coeffs.items() if c != ZERO}, new_const

    def _substitute_basic(self, coeffs: dict[int, Fraction],
                          constant: Fraction) -> tuple[dict[int, Fraction], Fraction]:
        """Replace basic variables by their row definitions.

        A basic variable B has a row: B = sum(row[B][j] * Xj) + rhs[B]
        So: coeff * B = coeff * (sum(row[B][j] * Xj) + rhs[B])

        After this, coeffs contains only non-basic variables.
        """
        new_coeffs = {}
        new_const = constant
        for var_id, coeff in coeffs.items():
            if var_id in self.rows:
                row = self.rows[var_id]
                row_rhs = self.rhs[var_id]
                for rv, rc in row.items():
                    new_coeffs[rv] = new_coeffs.get(rv, ZERO) + coeff * rc
                new_const += coeff * row_rhs
            else:
                new_coeffs[var_id] = new_coeffs.get(var_id, ZERO) + coeff
        return {v: c for v, c in new_coeffs.items() if c != ZERO}, new_const

    def _update_nonbasic(self, var_id: int) -> bool:
        """After tightening bounds on a non-basic variable, update its assignment.

        Non-basic vars sit at one of their bounds. If the current assignment
        violates the new bounds, snap to the nearest bound and update all
        basic variables that depend on it.
        """
        val = self.assign.get(var_id, ZERO)
        lo = self.lo.get(var_id)
        hi = self.hi.get(var_id)
        new_val = val
        if lo is not None and val < lo:
            new_val = lo
        elif hi is not None and val > hi:
            new_val = hi
        if new_val != val:
            delta = new_val - val
            self.assign[var_id] = new_val
            # Update all basic variables that have var_id in their row
            for basic_var, row in self.rows.items():
                if var_id in row:
                    self.assign[basic_var] += row[var_id] * delta
            # Now check if any basic variable became infeasible
            for basic_var in list(self.rows):
                bval = self.assign[basic_var]
                blo = self.lo.get(basic_var)
                bhi = self.hi.get(basic_var)
                if (blo is not None and bval < blo) or (bhi is not None and bval > bhi):
                    if not self._restore_feasibility(basic_var):
                        return False
        return True

    def _check_basic_feasible(self, var_id: int) -> bool:
        """Check if a basic variable's current assignment satisfies its bounds.

        If not, attempt to restore feasibility via dual simplex.
        """
        val = self.assign.get(var_id, ZERO)
        lo = self.lo.get(var_id)
        hi = self.hi.get(var_id)
        if lo is not None and val < lo:
            return self._restore_feasibility(var_id)
        if hi is not None and val > hi:
            return self._restore_feasibility(var_id)
        return True

    def fix_variable(self, var_id: int, value: Fraction) -> bool:
        """Fix a variable to a specific value (called when unified to ground).

        Substitutes the value into all rows and parametric definitions.
        Checks feasibility of affected constraints.
        Returns False if fixing causes infeasibility.
        """
        # Set both bounds to the value
        self.lo[var_id] = value
        self.hi[var_id] = value
        self.assign[var_id] = value

        if var_id in self.parametric:
            # Variable was already eliminated; just update its value
            # Check consistency: does the parametric definition agree?
            param_coeffs, param_const = self.parametric[var_id]
            computed = param_const
            for v, c in param_coeffs.items():
                computed += c * self.assign.get(v, ZERO)
            if computed != value:
                # The parametric definition doesn't match — add as equality
                # value = sum(param_coeffs[v] * v) + param_const
                # → 0 = sum(param_coeffs[v] * v) + param_const - value
                return False  # contradiction
            return True

        if var_id in self.rows:
            # Basic variable: substitute and remove from basis
            # All other rows referencing var_id need updating
            row = self.rows.pop(var_id)
            rhs = self.rhs.pop(var_id)
            # Check: does the row agree with the value?
            computed = rhs
            for v, c in row.items():
                computed -= c * self.assign.get(v, ZERO)
            # The row says var_id = computed, we want var_id = value
            # The discrepancy must be absorbed by adjusting non-basic vars
            # This is complex — simplify by adding as an equality constraint
            return self.add_equality({var_id: ONE}, value)

        # Non-basic variable: snap to value, update dependents
        old_val = self.assign.get(var_id, ZERO)
        if old_val != value:
            delta = value - old_val
            self.assign[var_id] = value
            for basic_var, row in self.rows.items():
                if var_id in row:
                    self.assign[basic_var] += row[var_id] * delta
        # Check feasibility of affected basic vars
        for basic_var in list(self.rows):
            if var_id in self.rows.get(basic_var, {}):
                if not self._check_basic_feasible(basic_var):
                    return False
        # Check disequalities
        return self._check_diseqs()

    def _check_diseqs(self) -> bool:
        """Check all passive disequalities. Fail if any ground pair is equal."""
        for (a, b) in self.diseqs:
            a_val = self.assign.get(a)
            b_val = self.assign.get(b)
            a_fixed = self.lo.get(a) is not None and self.lo[a] == self.hi.get(a)
            b_fixed = self.lo.get(b) is not None and self.lo[b] == self.hi.get(b)
            if a_fixed and b_fixed and a_val == b_val:
                return False
        return True

    def register_var(self, var: Var, lo: Fraction | None, hi: Fraction | None) -> int:
        """Register a Var in the tableau. Returns the tableau variable ID.

        Uses the Var's _id as the tableau variable ID (they're unique ints).
        Sets initial bounds and assignment.
        """
        vid = var._id
        self._var_map[vid] = var
        old_lo = self.lo.get(vid)
        old_hi = self.hi.get(vid)
        new_lo = lo if old_lo is None else (max(old_lo, lo) if lo is not None else old_lo)
        new_hi = hi if old_hi is None else (min(old_hi, hi) if hi is not None else old_hi)
        self.lo[vid] = new_lo
        self.hi[vid] = new_hi
        # Initial assignment: at lower bound if available, else 0, else upper bound
        if vid not in self.assign:
            if new_lo is not None:
                self.assign[vid] = new_lo
            elif new_hi is not None:
                self.assign[vid] = min(ZERO, new_hi)
            else:
                self.assign[vid] = ZERO
        return vid
```

### Tableau operations

#### Adding a bound

```python
    def set_bound(self, var_id: int, bound_lo: Fraction | None,
                  bound_hi: Fraction | None) -> bool:
        """Tighten bounds on a variable. Returns False if infeasible."""
        old_lo = self.lo.get(var_id)
        old_hi = self.hi.get(var_id)
        new_lo = bound_lo if old_lo is None else (
            max(old_lo, bound_lo) if bound_lo is not None else old_lo)
        new_hi = bound_hi if old_hi is None else (
            min(old_hi, bound_hi) if bound_hi is not None else old_hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        self.lo[var_id] = new_lo
        self.hi[var_id] = new_hi
        # If variable is non-basic, may need to update assignment + restore feasibility
        if var_id not in self.rows:
            return self._update_nonbasic(var_id)
        return self._check_basic_feasible(var_id)
```

#### Adding an equality constraint

```python
    def add_equality(self, coeffs: dict[int, Fraction], constant: Fraction) -> bool:
        """Add: sum(coeffs[i] * Xi) = constant.

        Uses Gaussian elimination: pick a pivot variable, solve for it,
        substitute into all other rows.
        Returns False if contradiction detected.
        """
        # Substitute already-parametric vars
        coeffs, constant = self._substitute_parametric(coeffs, constant)

        # Substitute basic vars (expand their rows)
        coeffs, constant = self._substitute_basic(coeffs, constant)

        # Now coeffs only contains non-basic variables
        if not coeffs:
            # Pure constant: check 0 = constant
            return constant == ZERO

        # Pick pivot: variable with smallest absolute coefficient (stability)
        pivot_var = min(coeffs, key=lambda v: abs(coeffs[v]))
        pivot_coeff = coeffs.pop(pivot_var)

        # Solve: pivot_var = (constant - sum(other_coeffs * vars)) / pivot_coeff
        param_coeffs = {v: -c / pivot_coeff for v, c in coeffs.items()}
        param_const = constant / pivot_coeff

        # Record as parametric
        self.parametric[pivot_var] = (param_coeffs, param_const)

        # Substitute into all remaining rows
        for row_var, row_coeffs in self.rows.items():
            if pivot_var in row_coeffs:
                factor = row_coeffs.pop(pivot_var)
                for v, c in param_coeffs.items():
                    row_coeffs[v] = row_coeffs.get(v, ZERO) + factor * c
                self.rhs[row_var] = self.rhs[row_var] + factor * param_const
                # Clean zeros
                row_coeffs = {v: c for v, c in row_coeffs.items() if c != ZERO}
                self.rows[row_var] = row_coeffs

        # Compute assignment for pivot_var
        val = param_const
        for v, c in param_coeffs.items():
            val += c * self.assign.get(v, ZERO)
        self.assign[pivot_var] = val

        # Check bounds on pivot_var
        lo = self.lo.get(pivot_var)
        hi = self.hi.get(pivot_var)
        if lo is not None and val < lo:
            return False
        if hi is not None and val > hi:
            return False

        # Remove pivot_var from basic/non_basic tracking if present
        self.rows.pop(pivot_var, None)
        return True
```

#### Adding an inequality constraint

```python
    def add_inequality(self, coeffs: dict[int, Fraction], constant: Fraction,
                       relation: str) -> bool:
        """Add: sum(coeffs[i] * Xi) {<=, >=} constant.

        Introduces a slack variable and checks feasibility via dual simplex.
        Returns False if infeasible.
        """
        # Substitute parametric variables
        coeffs, constant = self._substitute_parametric(coeffs, constant)
        # Substitute basic variables
        coeffs, constant = self._substitute_basic(coeffs, constant)

        if relation == '<=':
            # sum(coeffs) + slack = constant, slack >= 0
            slack = self.fresh_slack()
            self.rows[slack] = dict(coeffs)
            self.rhs[slack] = constant
            self.lo[slack] = ZERO
            self.hi[slack] = None
            # Compute current value of slack
            val = constant
            for v, c in coeffs.items():
                val -= c * self.assign.get(v, ZERO)
            self.assign[slack] = val
            # Check feasibility
            if val < ZERO:
                return self._restore_feasibility(slack)

        elif relation == '>=':
            # Negate: -sum(coeffs) <= -constant
            neg_coeffs = {v: -c for v, c in coeffs.items()}
            return self.add_inequality(neg_coeffs, -constant, '<=')

        return True
```

#### Simplex pivot

```python
    def _pivot(self, leaving: int, entering: int) -> None:
        """Standard simplex pivot: swap leaving (basic) and entering (non-basic).

        After pivot:
        - entering becomes basic (gets a row)
        - leaving becomes non-basic (removed from rows)
        """
        row = self.rows[leaving]
        pivot_coeff = row[entering]

        # Express entering in terms of the rest
        new_row = {}
        for v, c in row.items():
            if v != entering:
                new_row[v] = -c / pivot_coeff
        new_row[leaving] = Fraction(1) / pivot_coeff
        new_rhs = self.rhs[leaving] / pivot_coeff

        # Update all other rows
        for other_var in list(self.rows):
            if other_var == leaving:
                continue
            other_row = self.rows[other_var]
            if entering in other_row:
                factor = other_row.pop(entering)
                for v, c in new_row.items():
                    other_row[v] = other_row.get(v, ZERO) + factor * c
                self.rhs[other_var] += factor * new_rhs
                # Clean zeros
                self.rows[other_var] = {v: c for v, c in other_row.items() if c != ZERO}

        # Install new row
        del self.rows[leaving]
        self.rows[entering] = new_row
        self.rhs[entering] = new_rhs

        # Update assignments
        self.assign[entering] = new_rhs
        for v, c in new_row.items():
            self.assign[entering] -= c * self.assign.get(v, ZERO)
        # Leaving var gets its bound value
        # (set by caller based on direction of infeasibility)
```

#### Restore feasibility (dual simplex)

```python
    def _restore_feasibility(self, infeasible_var: int) -> bool:
        """Dual simplex: pivot to make infeasible_var feasible.

        Uses Bland's rule for anti-cycling: always choose lowest-indexed
        eligible entering variable.

        Returns False if infeasible (no valid pivot exists).
        """
        max_iters = len(self.rows) * len(self.lo) + 100  # safety bound
        for _ in range(max_iters):
            # Find most infeasible basic variable (or specific one)
            leaving = None
            worst = ZERO
            for var_id, row in self.rows.items():
                val = self.assign[var_id]
                lo = self.lo.get(var_id)
                hi = self.hi.get(var_id)
                if lo is not None and val < lo:
                    violation = lo - val
                    if violation > worst:
                        worst = violation
                        leaving = var_id
                elif hi is not None and val > hi:
                    violation = val - hi
                    if violation > worst:
                        worst = violation
                        leaving = var_id

            if leaving is None:
                return True  # all feasible

            # Find entering variable (Bland's rule: smallest index)
            row = self.rows[leaving]
            val = self.assign[leaving]
            lo = self.lo.get(leaving)
            entering = None

            if lo is not None and val < lo:
                # Need to increase leaving's value
                # entering must have negative coeff (to increase via pivot)
                for v in sorted(row.keys()):  # Bland's rule: sorted
                    c = row[v]
                    if c < ZERO:
                        entering = v
                        break
            else:
                # Need to decrease leaving's value
                for v in sorted(row.keys()):
                    c = row[v]
                    if c > ZERO:
                        entering = v
                        break

            if entering is None:
                return False  # infeasible — no valid pivot

            self._pivot(leaving, entering)

        return False  # exceeded iteration limit — treat as infeasible
```

#### Optimization

```python
    def optimize(self, objective: dict[int, Fraction], direction: str) -> Fraction | None:
        """Phase II simplex: maximize or minimize objective.

        objective: {var_id: coefficient} (linear expression)
        direction: 'max' or 'min'

        Returns optimal value, or None if unbounded.
        Updates self.assign to the optimal solution.

        Algorithm:
        1. Express objective in terms of non-basic variables only
           (substitute parametric and basic vars)
        2. Repeat:
           a. Find non-basic var with positive objective coefficient (entering)
              - Bland's rule: pick smallest-indexed such var
           b. If none found → current solution is optimal
           c. Find basic var that limits how much entering can increase (leaving)
              - Minimum ratio test
           d. If none found → objective is unbounded
           e. Pivot (swap entering/leaving) and update objective coefficients
        """
        # Substitute parametric vars in objective
        obj, obj_const = self._substitute_parametric(dict(objective), ZERO)
        # Substitute basic vars in objective
        obj, obj_const = self._substitute_basic(obj, obj_const)

        # Now obj contains only non-basic variables
        if direction == 'min':
            obj = {v: -c for v, c in obj.items()}
            obj_const = -obj_const

        max_iters = 10 * (len(self.rows) + len(self.lo) + 1)  # safety
        for _ in range(max_iters):
            # Find entering variable: first non-basic with positive obj coefficient
            # Bland's rule: sorted by index
            entering = None
            for v in sorted(obj.keys()):
                if v in self.rows:
                    continue  # basic var — skip
                if obj.get(v, ZERO) > ZERO:
                    entering = v
                    break

            if entering is None:
                # Optimal: compute objective value from current assignment
                val = obj_const
                for v, c in obj.items():
                    val += c * self.assign.get(v, ZERO)
                if direction == 'min':
                    val = -val
                return val

            # Find leaving variable: minimum ratio test
            # We want to increase `entering`. For each basic var whose row
            # contains `entering`, compute how much `entering` can increase
            # before that basic var hits its bound.
            leaving = None
            min_ratio = None
            for basic_var, row in self.rows.items():
                if entering not in row:
                    continue
                coeff = row[entering]
                if coeff <= ZERO:
                    continue  # entering increase doesn't push basic_var down
                # How much can entering increase?
                # basic_var = ... + coeff * entering + ... = rhs
                # basic_var currently at self.assign[basic_var]
                # When entering increases by delta: basic_var decreases by coeff * delta
                # basic_var must stay >= lo[basic_var]
                bval = self.assign[basic_var]
                blo = self.lo.get(basic_var)
                if blo is not None:
                    ratio = (bval - blo) / coeff
                    if leaving is None or ratio < min_ratio:
                        min_ratio = ratio
                        leaving = basic_var

            if leaving is None:
                return None  # unbounded — entering can increase without limit

            # Pivot and update objective
            # Before pivot: obj has entering with coefficient c_e
            # After pivot: entering becomes basic, leaving becomes non-basic
            # Must update obj to express in terms of new non-basic set
            entering_coeff = obj.pop(entering, ZERO)
            row = self.rows[leaving]
            pivot_coeff = row[entering]

            # After pivot, entering's row expresses entering in terms of
            # {leaving, other non-basics}. Substitute into obj:
            # obj was: ... + c_e * entering + ...
            # entering = (1/pivot_coeff) * leaving - sum(row[v]/pivot_coeff * v) + rhs/pivot_coeff
            factor = entering_coeff / pivot_coeff
            for v, c in row.items():
                if v != entering:
                    obj[v] = obj.get(v, ZERO) - factor * c
            obj[leaving] = obj.get(leaving, ZERO) + factor
            obj_const += factor * self.rhs[leaving]
            # Clean zeros
            obj = {v: c for v, c in obj.items() if c != ZERO}

            self._pivot(leaving, entering)

        return None  # exceeded iterations — shouldn't happen with Bland's
```

### Linearization

```python
def _linearize(expr, trail: Trail) -> tuple[dict[int, Fraction], Fraction] | None:
    """Flatten an expression tree into {var_id: coefficient} + constant.

    Returns None if the expression is non-linear (e.g., Var * Var).
    Handles: Add, Sub, Mult(const, expr), Mult(expr, const), Negate, Div.
    """
    # Lazy imports to avoid circular deps
    _ensure_term_imports()

    expr = deref(expr)

    if isinstance(expr, (int, float)):
        return {}, Fraction(expr)
    if isinstance(expr, Fraction):
        return {}, expr
    if is_var(expr):
        # IMPORTANT: expr is already deref'd. If a Var is bound to a value,
        # deref returns the value, not the Var. So if we reach here, the Var
        # is truly unbound. Its _id is used as the tableau variable key.
        return {expr._id: ONE}, ZERO

    if isinstance(expr, _Add):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        merged = dict(l_coeffs)
        for v, c in r_coeffs.items():
            merged[v] = merged.get(v, ZERO) + c
        return {v: c for v, c in merged.items() if c != ZERO}, l_const + r_const

    if isinstance(expr, _Sub):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        merged = dict(l_coeffs)
        for v, c in r_coeffs.items():
            merged[v] = merged.get(v, ZERO) - c
        return {v: c for v, c in merged.items() if c != ZERO}, l_const - r_const

    if isinstance(expr, _Mult):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        # One side must be constant for linearity
        if not l_coeffs:
            # left is constant, multiply right by it
            return {v: l_const * c for v, c in r_coeffs.items()}, l_const * r_const
        if not r_coeffs:
            # right is constant, multiply left by it
            return {v: r_const * c for v, c in l_coeffs.items()}, l_const * r_const
        return None  # non-linear: Var * Var

    if isinstance(expr, _Negate):
        inner = _linearize(expr.operand, trail)
        if inner is None:
            return None
        coeffs, const = inner
        return {v: -c for v, c in coeffs.items()}, -const

    if isinstance(expr, _Div):
        # Division by constant only
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        r_coeffs, r_const = rc
        if r_coeffs:
            return None  # division by variable: non-linear
        if r_const == ZERO:
            return None  # division by zero
        l_coeffs, l_const = lc
        return {v: c / r_const for v, c in l_coeffs.items()}, l_const / r_const

    return None  # unknown node type
```

### Helper functions

```python
def _is_ground_q(x) -> bool:
    """True if x is a concrete rational-compatible value (not a Var or expr tree)."""
    if isinstance(x, (int, Fraction)) and not isinstance(x, bool):
        return True
    return False

def _ensure_q_for_expr(expr, trail: Trail) -> None:
    """Ensure all Vars in an expression have Q-domain attributes.

    Walks the expression tree and auto-declares any unconstrained Var
    as in_q with unbounded range [-inf, +inf].
    """
    expr = deref(expr)
    if is_var(expr):
        if get_attr(expr, Q_KEY) is None:
            _post_q_domain(expr, None, None, trail)
        return
    _ensure_term_imports()
    if isinstance(expr, (_Add, _Sub, _Mult, _Div)):
        _ensure_q_for_expr(expr.left, trail)
        _ensure_q_for_expr(expr.right, trail)
    elif isinstance(expr, _Negate):
        _ensure_q_for_expr(expr.operand, trail)

def _post_q_domain(target, lo: Fraction | None, hi: Fraction | None,
                   trail: Trail) -> bool:
    """Post rational domain on a single target (var or numeric).

    If the var already has Q state, tighten bounds. If bounds collapse
    to a point, bind the variable.
    """
    target = deref(target)
    if isinstance(target, bool):
        return False
    if isinstance(target, (int, Fraction)):
        val = Fraction(target)
        if lo is not None and val < lo:
            return False
        if hi is not None and val > hi:
            return False
        return True
    if not is_var(target):
        return False

    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)

    state = get_attr(target, Q_KEY)
    if state is None:
        # New Q variable: register in tableau
        tab_id = tableau.register_var(target, lo, hi)
        new_state = QVar(lo, hi, tab_id)
        put_attr(target, Q_KEY, new_state, trail)
    else:
        # Tighten existing bounds
        new_lo = _max_none(state.lo, lo)
        new_hi = _min_none(state.hi, hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        # Update tableau bounds
        if not tableau.set_bound(state.tableau_id, new_lo, new_hi):
            return False
        new_state = QVar(new_lo, new_hi, state.tableau_id)
        put_attr(target, Q_KEY, new_state, trail)

    # Bind if point domain
    final_lo = new_state.lo
    final_hi = new_state.hi
    if final_lo is not None and final_hi is not None and final_lo == final_hi:
        if not unify(target, final_lo, trail):
            return False
    return True

def _max_none(a: Fraction | None, b: Fraction | None) -> Fraction | None:
    """max() that treats None as -infinity."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)

def _min_none(a: Fraction | None, b: Fraction | None) -> Fraction | None:
    """min() that treats None as +infinity."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)

# Lazy term imports (same pattern as clpr.py)
_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = None

def _ensure_term_imports():
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate
        _Add, _Sub, _Mult, _Div = Add, Sub, Mult, Div
        _FloorDiv, _Mod, _Pow, _Negate = FloorDiv, Mod, Pow, Negate
```

### Tableau storage and trail integration

The trail C implementation provides `trail.record(callable)` — pushes a no-arg
undo callback that fires on `trail.undo(mark)`. This is the mechanism for
restoring tableau state.

```python
# Module-level storage: one Tableau per trail identity.
# WeakKeyDictionary would be ideal but Trail may not be hashable/weakrefable.
# Use id(trail) with cleanup on access.
_tableaux: dict[int, Tableau] = {}

def _get_tableau(trail: Trail) -> Tableau:
    """Get or create the global Tableau for this trail."""
    tid = id(trail)
    tab = _tableaux.get(tid)
    if tab is None:
        tab = Tableau()
        _tableaux[tid] = tab
    return tab

def _snapshot_tableau(trail: Trail) -> None:
    """Save a copy of the current tableau so trail.undo() restores it.

    Uses trail.record() to push an undo callback that replaces the
    current tableau with the snapshot.
    """
    tid = id(trail)
    old_copy = _tableaux[tid].copy()

    def _undo():
        _tableaux[tid] = old_copy

    trail.record(_undo)
```

**How it works step by step:**

1. Before modifying the tableau, `_snapshot_tableau(trail)` is called
2. This deep-copies the current tableau and captures it in a closure
3. The closure is pushed onto the trail via `trail.record()`
4. If `trail.undo(mark)` is called later, the closure fires and replaces
   the module-level `_tableaux[tid]` entry with the snapshot
5. All subsequent `_get_tableau(trail)` calls see the restored state

**Important:** `_snapshot_tableau` must be called **before** every mutation,
not after. And it must be called at most once per "logical step" — if `q_eq`
calls both `add_equality` and then `fix_variable`, only one snapshot at the
beginning is needed (both mutations are undone together).

**Cleanup concern:** `id(trail)` can theoretically be reused after GC. In
practice, trails are long-lived (one per search context). If this becomes an
issue, we can use `weakref.ref(trail, cleanup_callback)` to remove stale
entries — but only if `Trail` objects support weakrefs (check at implementation
time).

### Attribute hook

```python
def _q_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when a Q-constrained variable is unified.

    attr_value: the QVar instance
    bound_to: the value the variable was bound to
    """
    state = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, bool):
        return False

    if isinstance(bound_to, (int, Fraction)):
        val = Fraction(bound_to)
        # Check bounds
        if state.lo is not None and val < state.lo:
            return False
        if state.hi is not None and val > state.hi:
            return False
        # Substitute into tableau: this variable is now fixed
        tableau = _get_tableau(trail)
        _snapshot_tableau(trail)
        return tableau.fix_variable(state.tableau_id, val)

    if isinstance(bound_to, float):
        # Float in Q context: convert to Fraction
        val = Fraction(bound_to).limit_denominator(10**15)
        # ... same as above ...

    if is_var(bound_to):
        other_state = get_attr(bound_to, Q_KEY)
        if other_state is None:
            # Transfer Q state to the other var
            put_attr(bound_to, Q_KEY, state, trail)
            return True
        # Both have Q state: merge bounds, update tableau
        new_lo = _max_none(state.lo, other_state.lo)
        new_hi = _min_none(state.hi, other_state.hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        # Add equality constraint: this_var = other_var in tableau
        tableau = _get_tableau(trail)
        _snapshot_tableau(trail)
        return tableau.add_equality(
            {state.tableau_id: ONE, other_state.tableau_id: -ONE}, ZERO
        )

    return False

register_attr_hook(Q_KEY, _q_hook)
```

### Public API

```python
def in_q(var_or_list, lo=None, hi=None, trail: Trail = None) -> bool:
    """Declare variable(s) as rational with optional bounds [lo, hi].

    Usage in Clausal:
        in_q(X, 0, 10)           # X in [0, 10]
        in_q([X, Y, Z], 0, 10)  # all in [0, 10]
        in_q(X)                   # X in (-inf, +inf)
    """
    targets = deref(var_or_list)
    lo_val = Fraction(deref(lo)) if lo is not None else None
    hi_val = Fraction(deref(hi)) if hi is not None else None
    if isinstance(targets, list):
        return all(_post_q_domain(deref(v), lo_val, hi_val, trail) for v in targets)
    return _post_q_domain(targets, lo_val, hi_val, trail)


def q_eq(l, r, trail: Trail) -> bool:
    """Post l == r as a rational equality constraint."""
    l, r = deref(l), deref(r)
    # Ground check
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) == Fraction(r)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    # Linearize: l - r = 0
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("CLP(Q) requires linear constraints")
    l_coeffs, l_const = lc
    r_coeffs, r_const = rc
    merged = dict(l_coeffs)
    for v, c in r_coeffs.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    constant = r_const - l_const
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    return tableau.add_equality(coeffs, constant)


def q_le(l, r, trail: Trail) -> bool:
    """Post l <= r as a rational inequality constraint."""
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) <= Fraction(r)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    # Linearize: l - r <= 0  →  coeffs <= constant
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("CLP(Q) requires linear constraints")
    l_coeffs, l_const = lc
    r_coeffs, r_const = rc
    merged = dict(l_coeffs)
    for v, c in r_coeffs.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    constant = r_const - l_const
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    return tableau.add_inequality(coeffs, constant, '<=')


def q_lt(l, r, trail: Trail) -> bool:
    """Post l < r (strict less-than).

    In rational arithmetic, l < r ⟺ l <= r ∧ l ≠ r.
    We post the non-strict inequality and record the disequality passively.

    SUBTLETY: Over the rationals, strict < is NOT the same as adding an
    epsilon. There is no smallest positive rational. Instead:
    - We post l <= r (which the simplex handles)
    - We record l ≠ r as a passive disequality
    - If both become ground and equal, the disequality fails

    This is how SICStus handles it. The alternative — adding a symbolic
    epsilon — would complicate the entire simplex.

    EDGE CASE: If posting l <= r immediately makes them equal (e.g.,
    l and r are already constrained to be the same), then q_ne should
    catch it and fail right away.
    """
    if not q_le(l, r, trail):
        return False
    return q_ne(l, r, trail)


def q_ne(l, r, trail: Trail) -> bool:
    """Post l != r as a passive disequality.

    Only fails when both sides become ground and equal.
    """
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) != Fraction(r)
    # Record passively in tableau
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    # ... store (l_id, r_id) in tableau.diseqs ...
    return True


def q_gt(l, r, trail: Trail) -> bool:
    return q_lt(r, l, trail)

def q_ge(l, r, trail: Trail) -> bool:
    return q_le(r, l, trail)


def maximize(expr, result_var, trail: Trail):
    """Maximize expr subject to current constraints. Bind result_var to optimal value.

    Usage in Clausal:
        maximize(3*X + 5*Y, OBJ)
    """
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("maximize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    opt = tableau.optimize(coeffs, 'max')
    if opt is None:
        return False  # unbounded
    return unify(result_var, opt + const, trail)


def minimize(expr, result_var, trail: Trail):
    """Minimize expr subject to current constraints."""
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("minimize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    opt = tableau.optimize(coeffs, 'min')
    if opt is None:
        return False  # unbounded
    return unify(result_var, opt + const, trail)
```

---

## Detailed walkthrough: a complete CLP(Q) example

To make the architecture concrete, let's trace this Clausal program end-to-end:

```clausal
LP(X, Y, OBJ) <- (
    in_q([X, Y], 0, 100),
    2*X + Y <= 16,
    X + 2*Y <= 11,
    X + 3*Y <= 15,
    maximize(30*X + 50*Y, OBJ)
)
```

### Step 1: Parsing and compilation

The Clausal source is parsed by `ast.parse()`, then transformed by
`EmbedTransformer`. The compiler sees:

- `in_q([X, Y], 0, 100)` → builtin call, emits trampoline to `_in_q__3`
- `2*X + Y <= 16` → `LtE(Add(Mult(2, X), Y), 16)` goal node
  - The `2` and `16` are ints, but `Mult(2, X)` stays as an expression tree
    because `eval_arith=False` (line 2210)
  - Compiled to: `_fd_le(Add(Mult(2, X), Y), 16, trail)`
- `maximize(30*X + 50*Y, OBJ)` → builtin call to `_maximize__2`

**Note:** The `int/int → Fraction` change only fires in `arith_to_ast_expr`
(which is used by `:=` and explicit arithmetic). Constraint arguments use
`term_to_ast_expr` with `eval_arith=False`, so `2*X` stays as `Mult(2, X)`.
The `2` is an int, not Fraction. This is fine — `_linearize` handles ints
by converting `Fraction(2)`.

### Step 2: Runtime execution of `in_q([X, Y], 0, 100)`

1. `_in_q__3` calls `in_q([X, Y], 0, 100, trail)`
2. `in_q` iterates over `[X, Y]`, calling `_post_q_domain` for each
3. For X: creates `QVar(lo=Fraction(0), hi=Fraction(100), tableau_id=X._id)`
   - Calls `tableau.register_var(X, Fraction(0), Fraction(100))`
   - This sets `tableau.lo[X._id] = 0`, `tableau.hi[X._id] = 100`,
     `tableau.assign[X._id] = 0` (initial at lower bound)
   - Calls `put_attr(X, Q_KEY, qvar, trail)` to record the attribute
4. Same for Y

**Tableau state after `in_q`:**
```
rows: {}  (no constraints yet)
lo: {X: 0, Y: 0}
hi: {X: 100, Y: 100}
assign: {X: 0, Y: 0}
parametric: {}
```

### Step 3: Runtime execution of `2*X + Y <= 16`

1. `fd_le(Add(Mult(2, X), Y), 16, trail)` is called
2. `_any_rational` checks: X has Q_KEY attribute → True
3. Dispatches to `q_le(Add(Mult(2, X), Y), 16, trail)`
4. `_ensure_q_for_expr` walks the expression — X and Y already have Q attrs
5. `_linearize(Add(Mult(2, X), Y))`:
   - `_linearize(Mult(2, X))` → left=2 (constant), right=X (var)
     → `{X: Fraction(2)}, Fraction(0)`
   - `_linearize(Y)` → `{Y: Fraction(1)}, Fraction(0)`
   - Merged: `{X: 2, Y: 1}, 0`
6. `_linearize(16)` → `{}, Fraction(16)`
7. Merged coeffs: `{X: 2, Y: 1}`, constant = `16 - 0 = 16`
8. `_snapshot_tableau(trail)` — copies the tableau, registers undo callback
9. `tableau.add_inequality({X: 2, Y: 1}, Fraction(16), '<=')`
   - Creates slack variable s₁ ≥ 0
   - Row: s₁ = 16 - 2X - Y
   - With X=0, Y=0: s₁ = 16 ≥ 0 → feasible

**Tableau state after first inequality:**
```
rows: {s₁: {X: -2, Y: -1}}
rhs:  {s₁: 16}
lo:   {X: 0, Y: 0, s₁: 0}
hi:   {X: 100, Y: 100, s₁: None}
assign: {X: 0, Y: 0, s₁: 16}
```

### Step 4: Two more inequalities added similarly

After all three inequalities:
```
rows: {s₁: {X: -2, Y: -1},  s₂: {X: -1, Y: -2},  s₃: {X: -1, Y: -3}}
rhs:  {s₁: 16,               s₂: 11,                s₃: 15}
assign: {X: 0, Y: 0, s₁: 16, s₂: 11, s₃: 15}
```

All slack variables are non-negative → system is feasible at origin.

### Step 5: `maximize(30*X + 50*Y, OBJ)`

1. `_linearize(Add(Mult(30, X), Mult(50, Y)))` → `{X: 30, Y: 50}, 0`
2. `tableau.optimize({X: 30, Y: 50}, 'max')`
3. Substitute basic vars in objective: X and Y are non-basic, so no substitution
4. Objective over non-basic vars: `{X: 30, Y: 50}`

**Iteration 1:** Entering = X (first positive, Bland's rule, but Y has larger coeff
— Bland's picks smallest index, so depends on IDs. Let's say Y enters first.)
- Entering = Y (coeff 50 > 0)
- Ratio test:
  - s₁: coeff of Y = -1, but we need positive → skip (wait, sign depends on convention)

Actually, let me reconsider. The row `s₁ = 16 - 2X - Y` means:
in the row dict, `s₁.row = {X: -2, Y: -1}` and `rhs = 16`.

For the ratio test when Y enters: we look at basic vars where Y has a
**negative** coefficient in their row (because increasing Y decreases the
basic var, which is bounded below by 0).
- s₁: Y coeff = -1 (negative), ratio = (16 - 0) / 1 = 16
- s₂: Y coeff = -2, ratio = 11/2 = 5.5
- s₃: Y coeff = -3, ratio = 15/3 = 5

Minimum ratio = 5 → leaving = s₃.

**Pivot s₃ ↔ Y:** Y becomes basic, s₃ becomes non-basic.
After pivot: Y = 5 - (1/3)X - (1/3)s₃
Assignments: X=0, Y=5, s₃=0

Objective update: obj was 50Y + 30X. Substitute Y = 5 - (1/3)X - (1/3)s₃:
= 50(5 - X/3 - s₃/3) + 30X = 250 - 50X/3 - 50s₃/3 + 30X
= 250 + (30 - 50/3)X - (50/3)s₃ = 250 + (40/3)X - (50/3)s₃
Non-basic obj: {X: 40/3, s₃: -50/3}

**Iteration 2:** Entering = X (40/3 > 0)
Ratio test on basic vars containing X:
- s₁: row updated after pivot. s₁ = 16 - 2X - Y = 16 - 2X - (5 - X/3 - s₃/3)
  = 11 - (5/3)X + (1/3)s₃. Coeff of X = -5/3, ratio = 11 / (5/3) = 33/5
- s₂: similarly updated. Coeff of X in s₂ depends on pivot.
- Y: Y is now basic. Y = 5 - (1/3)X - (1/3)s₃. Coeff of X = -1/3, ratio = 5 / (1/3) = 15

Minimum ratio = 33/5 = 6.6 → leaving = s₁.

**Pivot s₁ ↔ X:** X = (33/5) - ... After pivot: X = 33/5 - ...

Let me skip the arithmetic and state the known result:
**Optimal:** X = 7, Y = 2, objective = 30(7) + 50(2) = 210 + 100 = **310** ✓

3. `maximize` returns `Fraction(310)`
4. `unify(OBJ, Fraction(310), trail)` binds OBJ

---

## `_resolve` and `_eval_ground` updates

**File:** `clausal/logic/clpfd.py:1165-1180`

The `_resolve` function evaluates ground expression trees to concrete values.
Currently it uses `_eval_ground` which only expects `int` results. With `int/int`
producing `Fraction`, ground expression trees can now contain `Fraction` values.

```python
# Current _eval_ground evaluates Add(3, Mult(2, 5)) → 13.
# Now it may encounter Fraction values: Add(Fraction(1,2), Fraction(1,3)) → Fraction(5,6).
# The fix: _eval_ground already uses Python arithmetic operators (+, -, *, /),
# and Fraction supports all of these. The only issue is type checks:
# if the function checks `isinstance(result, int)`, it should also accept Fraction.
```

**What needs changing:**
1. `_eval_ground` should accept `Fraction` as a valid leaf type
2. `_resolve` should accept `Fraction` results (currently it may only expect `int`)
3. `_is_fd_compatible` should NOT treat `Fraction` as FD-compatible (Fractions
   go to CLP(Q), not CLP(Z))
4. `_both_ground` should recognize `Fraction` as ground

Let me check the actual `_eval_ground`:

The function at `clpfd.py` recursively evaluates `Add`, `Sub`, `Mult`, `Negate`
on ground terms using Python `+`, `-`, `*` operators. Since `Fraction` supports
all these operators, the function should work out of the box — **provided** it
accepts `Fraction` as a valid leaf alongside `int`.

**Specific change needed:** In `_eval_ground`, the base case likely checks
`isinstance(x, int)`. Add `Fraction`:

```python
if isinstance(x, (int, Fraction)) and not isinstance(x, bool):
    return x
```

---

## Edge cases and gotchas

### 1. Division by zero in Fraction

```python
Fraction(1, 0)  # → raises ZeroDivisionError
```

We must catch this in `_linearize` when dividing by a zero constant, and in the
compiler's `int/int` folding (reject `1/0` at compile time or let Python raise
at runtime — prefer the latter, consistent with current behavior).

### 2. int/Fraction mixing

```python
Fraction(3) + 1  # works — Python auto-converts int to Fraction
Fraction(3) + 1.5  # works — Python converts Fraction to float (LOSSY!)
```

In CLP(Q) we must ensure we **never** accidentally convert to float. All
arithmetic within the tableau must stay as `Fraction`. When a user writes
`X == 1`, the `1` is an `int`, and `Fraction(1)` is exact. No problem.

When a user writes `X == 1.5`, the `1.5` is a `float` and should trigger
CLP(R), not CLP(Q). The dispatch order ensures this: `_any_rational` checks
for `Fraction` or `Q_KEY`; floats are handled by `_any_real`.

**But:** what if a variable is declared `in_q` and then compared to a float?
```clausal
in_q(X, 0, 10),
X == 1.5        # Fraction or float?
```

Decision: **error.** Mixing rational and float domains is a type error, matching
SICStus behavior. The `_q_hook` should reject `float` bound_to values (or
convert via `Fraction.from_float()` with a warning).

### 3. Negative zero in Fraction

Not an issue — `Fraction` has no negative zero. `Fraction(0) == Fraction(-0)`.

### 4. Very large coefficients

```python
Fraction(886731088897, 627013566048) * Fraction(886731088897, 627013566048)
# → exact but huge numerator/denominator
```

Python handles this fine (arbitrary precision) but operations become O(n^2) in
digit count. The Tableau.copy() cost grows with coefficient size.

### 5. Degenerate pivots (cycling)

Bland's rule prevents infinite cycling but may cause many degenerate pivots
(pivots that don't change the objective value). Each pivot is exact, so we
won't accumulate errors — we'll just be slow.

### 6. Trail undo and tableau restoration

The hardest part of the implementation. If we undo past a constraint addition,
we must restore the entire tableau to its pre-constraint state. Copy-on-write
is the safest approach. The alternative — incremental undo (reverse the
Gaussian elimination step) — is more efficient but much harder to get right.

**Start with copy-on-write.** Optimize later if profiling shows it's a
bottleneck.

### 7. Variable elimination via unification

When `unify(X, 3, trail)` is called on a Q-constrained variable, the hook
fires and must:
1. Substitute X = 3 into the tableau (all rows containing X)
2. Check feasibility of affected constraints
3. Detect any newly fixed variables → bind them too (chain reaction)

This chain reaction must terminate. It will, because each step reduces the
number of free variables by at least one.

### 8. Empty tableau

When no Q constraints have been posted, `_get_tableau(trail)` returns an empty
Tableau. All operations on an empty tableau should be trivially correct.

### 9. Interaction with CLP(Z) and CLP(R)

A variable should belong to at most one domain: Q, R, or Z. If a variable has
both `Q_KEY` and `FD_KEY` attributes, we need a clear policy:
- **Q + Z:** Rational and integer. The variable is effectively integer-constrained
  (CLP(Z) is more restrictive). Let both hooks fire independently.
- **Q + R:** Type error — mixing exact and approximate. The dispatch order
  prevents this (Q checks first), but the hook should reject it.

### 10. Projection (printing constraints)

SWI-Prolog's biggest bug is broken projection. We should implement clean
projection from the start:

```python
def dump_q(vars_list, trail) -> list[str]:
    """Project the constraint store onto the given variables.

    Returns a list of constraint strings with internal variables eliminated.
    Uses Fourier-Motzkin elimination for inequality projection.
    """
```

This is complex but critical for debugging. Defer to Phase 5.

---

## Test plan

### Phase 1: Compiler + Dispatch (no solver yet)

```python
# test_fraction_literal.py

def test_int_div_int_produces_fraction():
    """1/3 in Clausal source → Fraction(1, 3) at runtime."""
    # Compile a clause: test(X) <- X := 1/3
    # Assert X is Fraction(1, 3), not 0.333...

def test_float_div_still_float():
    """1.0/3 → float, not Fraction."""

def test_int_div_int_in_constraint():
    """X == 1/3 dispatches to CLP(Q)."""

def test_fraction_in_base_globals():
    """_Fraction is available in compiled code."""

def test_dispatch_fraction_to_q_eq():
    """fd_eq with Fraction argument dispatches to q_eq."""

def test_dispatch_fraction_to_q_le():
    """fd_le with Fraction argument dispatches to q_le."""

def test_dispatch_int_still_fd():
    """fd_eq with int arguments still goes to CLP(Z)."""

def test_dispatch_float_still_real():
    """fd_eq with float arguments still goes to CLP(R)."""
```

### Phase 2: Basic QVar + bounds

```python
# test_clpq.py

class TestInQ:
    def test_in_q_basic(self):
        """in_q(X, 0, 10) creates QVar with bounds [0, 10]."""
        trail = Trail()
        x = Var()
        assert in_q(x, 0, 10, trail)
        state = get_attr(x, Q_KEY)
        assert state.lo == Fraction(0)
        assert state.hi == Fraction(10)

    def test_in_q_narrows(self):
        """Second in_q tightens bounds."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        in_q(x, 2, 8, trail)
        state = get_attr(x, Q_KEY)
        assert state.lo == Fraction(2)
        assert state.hi == Fraction(8)

    def test_in_q_infeasible(self):
        """in_q with contradictory bounds fails."""
        trail = Trail()
        x = Var()
        in_q(x, 5, 10, trail)
        assert not in_q(x, 0, 3, trail)  # [5,10] ∩ [0,3] = empty

    def test_in_q_point_binds(self):
        """in_q(X, 5, 5) binds X to Fraction(5)."""
        trail = Trail()
        x = Var()
        in_q(x, 5, 5, trail)
        assert deref(x) == Fraction(5)

    def test_in_q_list(self):
        """in_q([X,Y,Z], 0, 10) constrains all three."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        assert in_q([x, y, z], 0, 10, trail)
        for v in [x, y, z]:
            assert get_attr(v, Q_KEY) is not None

    def test_in_q_ground_fraction_check(self):
        """in_q on a ground Fraction checks bounds."""
        trail = Trail()
        assert in_q(Fraction(5), 0, 10, trail)
        assert not in_q(Fraction(15), 0, 10, trail)
```

### Phase 3: Linear equalities (Gaussian elimination)

```python
class TestLinearEqualities:
    def test_simple_eq_binds(self):
        """X == 5 in Q context → X bound to Fraction(5)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_eq(x, Fraction(5), trail)
        assert deref(x) == Fraction(5)

    def test_two_var_eq(self):
        """X + Y == 10, X == 3 → Y == 7."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_eq(Add(x, y), Fraction(10), trail)
        assert q_eq(x, Fraction(3), trail)
        assert deref(y) == Fraction(7)

    def test_three_var_system(self):
        """X + Y + Z = 6, X - Y = 2, Y - Z = 1 → X=3, Y=1, Z=2 (wrong)
        Actually: X-Y=2 → X=Y+2; Y-Z=1 → Z=Y-1
        X+Y+Z=6 → (Y+2)+Y+(Y-1)=6 → 3Y+1=6 → Y=5/3
        X = 5/3 + 2 = 11/3, Z = 5/3 - 1 = 2/3"""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        in_q([x, y, z], -100, 100, trail)
        assert q_eq(Add(Add(x, y), z), Fraction(6), trail)
        assert q_eq(Sub(x, y), Fraction(2), trail)
        assert q_eq(Sub(y, z), Fraction(1), trail)
        assert deref(x) == Fraction(11, 3)
        assert deref(y) == Fraction(5, 3)
        assert deref(z) == Fraction(2, 3)

    def test_contradictory_equalities(self):
        """X == 3, X == 5 → fail."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_eq(x, Fraction(3), trail)
        assert not q_eq(x, Fraction(5), trail)

    def test_redundant_equality(self):
        """X + Y == 10, X + Y == 10 → succeeds (redundant)."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_eq(Add(x, y), Fraction(10), trail)
        assert q_eq(Add(x, y), Fraction(10), trail)

    def test_rational_coefficients(self):
        """(1/2)*X + (1/3)*Y == 1 → exact solution."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        half_x = Mult(Fraction(1, 2), x)
        third_y = Mult(Fraction(1, 3), y)
        assert q_eq(Add(half_x, third_y), Fraction(1), trail)
        # X = 2 - (2/3)Y; if Y=0 then X=2
        assert q_eq(y, Fraction(0), trail)
        assert deref(x) == Fraction(2)
```

### Phase 4: Linear inequalities (simplex)

```python
class TestLinearInequalities:
    def test_simple_le(self):
        """X <= 5, in_q(X, 0, 10) → feasible."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_le(x, Fraction(5), trail)

    def test_le_infeasible(self):
        """X >= 6, X <= 4 → infeasible."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_ge(x, Fraction(6), trail)
        assert not q_le(x, Fraction(4), trail)

    def test_two_var_inequality_system(self):
        """Classic LP feasibility:
        X + Y <= 8, X <= 5, Y <= 6, X >= 0, Y >= 0
        → feasible (e.g., X=2, Y=3)"""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_le(Add(x, y), Fraction(8), trail)
        assert q_le(x, Fraction(5), trail)
        assert q_le(y, Fraction(6), trail)
        # System is feasible, variables not yet determined

    def test_strict_lt(self):
        """X < 5 (strict) → X <= 5 ∧ X ≠ 5."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_lt(x, Fraction(5), trail)
        # X = 5 should now fail
        assert not q_eq(x, Fraction(5), trail)

    def test_sicstus_example_supremum(self):
        """From SICStus docs:
        2*X + Y <= 16, X + 2*Y <= 11, X + 3*Y <= 15, Z = 30*X + 50*Y
        sup(Z) = 310"""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        in_q([x, y, z], 0, 1000, trail)
        assert q_le(Add(Mult(Fraction(2), x), y), Fraction(16), trail)
        assert q_le(Add(x, Mult(Fraction(2), y)), Fraction(11), trail)
        assert q_le(Add(x, Mult(Fraction(3), y)), Fraction(15), trail)
        assert q_eq(z, Add(Mult(Fraction(30), x), Mult(Fraction(50), y)), trail)
        # maximize Z → 310
        result = Var()
        assert maximize(z, result, trail)
        assert deref(result) == Fraction(310)
```

### Phase 5: Backtracking

```python
class TestBacktracking:
    def test_undo_restores_bounds(self):
        """trail.undo() restores QVar bounds."""
        trail = Trail()
        x = Var()
        mark = trail.mark()
        in_q(x, 0, 10, trail)
        trail.undo(mark)
        assert get_attr(x, Q_KEY) is None

    def test_undo_restores_tableau(self):
        """trail.undo() restores the tableau to pre-constraint state."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        mark = trail.mark()
        q_eq(Add(x, y), Fraction(10), trail)
        q_eq(x, Fraction(3), trail)
        assert deref(y) == Fraction(7)
        trail.undo(mark)
        # y should be unbound again
        assert is_var(y)

    def test_undo_after_infeasible(self):
        """After a failed constraint, undo should restore feasible state."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_le(x, Fraction(5), trail)
        mark = trail.mark()
        result = q_ge(x, Fraction(8), trail)  # may or may not fail
        trail.undo(mark)
        # Tableau should be back to just X <= 5
```

### Phase 6: Optimization

```python
class TestOptimization:
    def test_maximize_simple(self):
        """maximize X subject to X <= 10 → 10."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, Fraction(10), trail)
        result = Var()
        assert maximize(x, result, trail)
        assert deref(result) == Fraction(10)

    def test_minimize_simple(self):
        """minimize X subject to X >= 3 → 3."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, Fraction(3), trail)
        result = Var()
        assert minimize(x, result, trail)
        assert deref(result) == Fraction(3)

    def test_maximize_lp(self):
        """Classic LP from SICStus docs:
        maximize 30X + 50Y subject to
            2X + Y <= 16, X + 2Y <= 11, X + 3Y <= 15
        → optimal at X=7, Y=2, objective=310"""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 1000, trail)
        q_le(Add(Mult(Fraction(2), x), y), Fraction(16), trail)
        q_le(Add(x, Mult(Fraction(2), y)), Fraction(11), trail)
        q_le(Add(x, Mult(Fraction(3), y)), Fraction(15), trail)
        obj_expr = Add(Mult(Fraction(30), x), Mult(Fraction(50), y))
        result = Var()
        assert maximize(obj_expr, result, trail)
        assert deref(result) == Fraction(310)

    def test_unbounded(self):
        """maximize X with no upper bound → None (unbounded)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, None, trail)
        result = Var()
        assert not maximize(x, result, trail)  # unbounded → fail

    def test_infeasible_optimize(self):
        """maximize over empty feasible region → fail."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_le(x, Fraction(3), trail)
        q_ge(x, Fraction(5), trail)  # fails — empty region
        # Should have already failed at q_ge
```

### Phase 7: Coefficient growth stress test

```python
class TestCoefficientGrowth:
    def test_newton_sqrt2(self):
        """Newton's method for sqrt(2), 5 iterations.
        s₀ = 1
        sₙ₊₁ = sₙ/2 + 1/sₙ
        After 5 iterations: 886731088897/627013566048"""
        trail = Trail()
        # Build iteratively
        s = Fraction(1)
        for _ in range(5):
            s = s / 2 + 1 / s
        assert s == Fraction(886731088897, 627013566048)
        # Verify it's close to sqrt(2)
        assert abs(float(s) - 2**0.5) < 1e-20

    def test_large_coefficient_constraint(self):
        """Constraints with large rational coefficients should work."""
        trail = Trail()
        x = Var()
        big = Fraction(886731088897, 627013566048)
        in_q(x, 0, big * 2, trail)
        assert q_eq(x, big, trail)
        assert deref(x) == big
```

### Phase 8: SICStus compatibility tests

```python
class TestSICStusExamples:
    def test_entailed_le(self):
        """SICStus: {A =< 4}, entailed(A ≠ 5) → yes."""
        # entailed is a higher-level check — test bounds implication

    def test_mortgage(self):
        """Mortgage calculation from SICStus docs.
        mg(P,T,I,B,MP): T=1 → B+MP = P*(1+I)
        mg(P,12,1/100,B,MP) → rational relationship between P, B, MP"""
        # This exercises recursive constraint posting

    def test_convex_hull(self):
        """Convex hull from SICStus docs.
        conv_hull([[1,1],[2,0],[3,0],[1,2],[2,2]], [X,Y])
        → 5 non-redundant constraints defining the hull"""

    def test_filled_rectangle(self):
        """Square tiling: find A such that a rectangle A × 1 can be
        tiled with squares of distinct sizes.
        Solution 1: A = 1, squares = [1]
        Solution 2: A = 33/32, squares = [15/32, 9/16, 1/4, ...]"""
```

---

## Implementation phases

### Phase 1: Compiler change (`int/int` → `Fraction`)

**Files:** `clausal/logic/compiler.py`

1. Modify `arith_to_ast_expr` (line 1538) to intercept `Div(int, int)` → `Fraction`
2. Add `Fraction` to the literal type check (line 1552)
3. Add `_Fraction` to `base_globals` (line 5593)
4. Run full test suite — check for regressions from the `int/int` change

**Risk:** This is the highest-risk change because it affects all Clausal programs.
Run the full test suite immediately after this change. If specific tests break
because they relied on `int/int → float`, fix them to use `float/int` or
`int/float` instead.

### Phase 2: Core CLP(Q) scaffolding

**Files:** `clausal/logic/clpq.py` (new), `clausal/logic/clpfd.py`

1. Create `clpq.py` with `Q_KEY`, `QVar`, `in_q`, `_q_hook`, `register_attr_hook`
2. Add `_is_rational_arg`, `_any_rational` to `clpfd.py`
3. Add rational dispatch to all `fd_*` functions (before `_any_real`)
4. Implement basic `q_eq`, `q_ne`, `q_lt`, `q_le`, `q_gt`, `q_ge` with
   **ground-only handling** (no tableau yet — just Fraction comparison)

**Tests:** Phase 1 + Phase 2 tests (ground comparisons, dispatch, `in_q` bounds)

### Phase 3: Gaussian elimination (equalities)

**Files:** `clausal/logic/clpq.py`

1. Implement `Tableau` class with `add_equality`, `_substitute_parametric`,
   `_substitute_basic`
2. Implement `_linearize` for expression trees
3. Wire `q_eq` to linearize → add to tableau
4. Implement variable fixing (detected after elimination → `unify`)
5. Implement `_snapshot_tableau` for trail integration

**Tests:** Phase 3 tests (two-var, three-var, contradictory, redundant)

### Phase 4: Simplex (inequalities)

**Files:** `clausal/logic/clpq.py`

1. Implement `add_inequality`, `fresh_slack`, `_pivot`
2. Implement `_restore_feasibility` (dual simplex) with Bland's rule
3. Wire `q_le`, `q_ge` to linearize → add_inequality
4. Implement `q_lt` as `q_le` + `q_ne`

**Tests:** Phase 4 tests (feasibility, infeasibility, SICStus supremum example)

### Phase 5: Trail integration

**Files:** `clausal/logic/clpq.py`

1. Implement `Tableau.copy()` for deep-copy snapshots
2. Wire `_snapshot_tableau` to use `trail.record(lambda: restore_snapshot)` —
   this is the C-level trail callback mechanism (see `_variables.c:795`)
3. Ensure `_snapshot_tableau` is called exactly once per logical constraint step
4. Test backtracking exhaustively — especially undo after infeasible constraint

**Tests:** Phase 5 tests (undo bounds, undo tableau, undo after failure)

### Phase 6: Optimization

**Files:** `clausal/logic/clpq.py`, `clausal/logic/builtins/constraints.py`

1. Implement `Tableau.optimize` (Phase II simplex with Bland's rule)
2. Implement `maximize`, `minimize` public API in `clpq.py`
3. Register `@_builtin("maximize", 2)` and `@_builtin("minimize", 2)` in
   `clausal/logic/builtins/constraints.py`

**Tests:** Phase 6 tests (simple max/min, LP, unbounded, infeasible)

### Phase 7: Polish and advanced features

**Files:** `clausal/logic/clpq.py`, `tests/test_clpq.py`

1. Coefficient growth stress tests
2. SICStus compatibility tests
3. Projection (`dump_q`) — Fourier-Motzkin elimination
4. Error messages for non-linear constraints
5. Documentation

---

## References

### Papers (implement from these)
- Holzbaur 1992 — "An algorithm for linear constraint solving" (JLP)
- Holzbaur 1994 — "Specialized incremental solved form" (OFAI TR-94-07)
- Holzbaur 1995 — "OFAI CLP(Q,R) Manual" (OFAI TR-95-09)
- Refalo 1998 — "Approaches to incremental detection of implicit equalities"
- Narboni 1992 — "About Gaussian elimination and infinite precision"

### Reference implementations (study, don't copy)
- SWI-Prolog CLP(Q,R): https://github.com/SWI-Prolog/packages-clpqr (GPL-2)
- Parma Polyhedra Library: https://www.bugseng.com/ppl/ (GPL-3, exact simplex)
- QSopt-Exact: https://www.math.uwaterloo.ca/~bico/qsopt/ex/ (exact LP)

### Documentation (expected behavior)
- SICStus CLP(Q,R) docs: https://sicstus.sics.se/sicstus/docs/3.7.1/html/sicstus_32.html
- SWI-Prolog CLP(Q,R) status: https://www.swi-prolog.org/pldoc/man?section=clpqr-status

### Clausal code locations
- Dispatch: `clausal/logic/clpfd.py:1149-1344` (`_is_real_arg`, `fd_eq` etc.)
- Compiler arith: `clausal/logic/compiler.py:1527-1570` (`arith_to_ast_expr`)
- Compiler goals: `clausal/logic/compiler.py:2186-2228` (ArithEq, Lt, etc.)
- Compiler globals: `clausal/logic/compiler.py:5575-5630` (`base_globals`)
- Builtins registry: `clausal/logic/builtins/constraints.py` (`@_builtin` decorator)
- Builtin decorator: `clausal/logic/builtins/_registry.py` (defines `@_builtin`)
- CLP(R) pattern: `clausal/logic/clpr.py` (mirror this architecture)
- Variables API: `clausal/logic/variables/__init__.py` (put_attr, get_attr, etc.)
- Trail C impl: `clausal/logic/variables/_variables.c:795` (`trail.record()`)
- AST nodes: `clausal/pythonic_ast/nodes.py:515` (Div, Add, etc.)
- AST conversion: `clausal/pythonic_ast/conversion_from_python_ast.py:135` (BINOP_CLASS)
