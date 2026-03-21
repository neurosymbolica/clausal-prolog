# CLP(R) — Constraint Logic Programming over Reals

Implementation plan for CLP(R) in clausal: interval arithmetic over IEEE doubles, unified
syntax with the existing CLP(FD) solver, non-linear constraints via interval inversion,
and IEEE-terminating bisection labeling.

---

## Background: The CLP(R) landscape

Constraint Logic Programming over Reals has been part of Prolog systems since the late
1980s. Several distinct approaches have emerged, each with different tradeoffs.

### Historical roots

**CLP(R) (1987)** — Jaffar and Lassez at IBM Research. The original CLP(R) used a
simplex-based linear arithmetic solver. Non-linear constraints were deferred: posted as
residual goals that are re-checked when variables become ground, but not actively
propagated. Rational arithmetic was handled by a sibling system CLP(Q).

**BNR Prolog (1988–1992)** — Bell-Northern Research. John Cleary and colleagues built a
constraint solver based on *interval arithmetic* rather than simplex. Every variable has
a real-valued interval `[lo, hi]`. Constraints narrow these intervals toward a fixpoint.
This approach handles non-linear constraints actively and is the intellectual ancestor of
CLP(BNR).

**SICStus CLP(R/Q) (1990s)** — Holzbaur's implementation in SICStus became the reference
implementation, later ported to SWI-Prolog by Leslie De Koninck.

### Current major systems

#### SWI-Prolog `library(clpr)` and `library(clpq)`

The Holzbaur/De Koninck implementation. Uses Gaussian elimination and the simplex method
for linear arithmetic. Available in SWI-Prolog but officially **orphaned** (no active
maintainer as of 2024).

- `clpr` uses IEEE 64-bit floats
- `clpq` uses exact rational arithmetic (Python `fractions.Fraction` equivalent)
- **Non-linear constraints are deferred** — posted as passive residuals, only checked when
  ground. This means `{X * Y >= 0}` does nothing until both X and Y have values.
- Syntax: constraints wrapped in `{}` braces; standard Prolog arithmetic operators inside

```prolog
:- use_module(library(clpr)).

?- {X + Y =< 10, X - Y >= 2, X >= 0, Y >= 0}.
% X in [1.0, inf], Y in [-inf, 4.0], with constraint store

?- {X + Y =< 10}, {2*X = Y + 1}.
% X = 3.666..., Y = 6.333...  (solved exactly via simplex)
```

#### CLP(BNR) — `pack(clpBNR)` for SWI-Prolog

Maintained by Bill Older (ridgeworks), actively developed. Uses **interval arithmetic
with outward rounding**: every variable is represented as a closed interval `[lo, hi]`
where the true value is guaranteed to lie. Constraints are narrowing operations applied to
these intervals until a fixpoint is reached.

- Handles **non-linear constraints actively** — `{X*X + Y*Y == 1}` propagates
- Sound by construction: `lo` is rounded toward `-inf`, `hi` toward `+inf` after every
  floating-point operation, so the true real value is always inside the interval
- Variables declared via `::` with type `real`, `integer`, or `boolean`
- Constraints in `{}`; labeling via `solve/1` or `splitsolve/1`

```prolog
:- use_module(library(clpBNR)).

?- [X, Y]::real(0, 1), {X + Y == 1}.
% X::real(0.0, 1.0), Y::real(0.0, 1.0) with X+Y=1

?- X::real, {X*X == 2}, solve(X).
% X = 1.4142135623730951  (via bisection)

?- [X, Y]::real, {X*X + Y*Y == 1}, splitsolve([X, Y]).
% Enumerates points on the unit circle
```

#### ECLiPSe `library(ic)`

The IC (Interval Constraint) library in ECLiPSe is the most sophisticated unified system.
It handles integers and reals within a single framework using interval propagation.

- Integer variables and real variables share the same constraint machinery
- `#` operators enforce integrality (the variable must be integer-valued)
- `$` operators work for any numeric type (real or integer)
- "An integer variable is just a real variable with an additional integrality constraint"

```prolog
:- lib(ic).

?- X :: 1.0..10.0,  Y :: 1.0..10.0,  X $= Y + 1.5.
% X in [2.5, 10.0], Y in [1.0, 8.5]

?- X :: 1..10, Y :: 1..10, X #= Y + 2.
% X in [3, 10], Y in [1, 8]

?- X :: 1.0..10.0, Y :: 1..10,  X $= Y.
% promotes Y to real; X and Y share interval
```

#### SICStus Prolog CLP(R)

Similar to SWI's Holzbaur port. Linear arithmetic via simplex, non-linear deferred.
Maintained as a commercial product.

---

## The syntax problem

Every mainstream system suffers from an awkward syntax split between its integer and real
solvers. The root cause is that each solver was built independently and exposed different
operator sets.

### SWI-Prolog: two incompatible syntaxes

```prolog
% CLP(FD) — hash prefix operators:
X in 1..10,
X #= Y + 1,
X #< 5,
X #>= 0,
label([X, Y])

% CLP(R) — braces around standard arithmetic:
{X + Y =< 10},
{X - Y >= 2},
{X =:= 3.0},
{X =\= 0.0}
```

Users must learn completely different idioms. Mixing the two solvers in one program
requires careful bookkeeping about which variables live in which world.

### CLP(BNR): declaration syntax + braces

```prolog
% Declaration and constraints are separate concerns:
[X, Y]::real(0.0, 1.0),   % declare type and bounds
{X + Y == 1},              % post constraint (active, both linear and non-linear)
{X * X + Y * Y =< 1},
solve([X, Y])              % label via bisection
```

Better than the SWI split, but `::` for declaration and `{}` for constraints is still two
distinct syntactic forms with no counterpart in CLP(FD).

### ECLiPSe IC: unified but two operator prefixes

```prolog
% Integer constraints use #:
X #= Y + 2,  X #< 10

% Real constraints use $:
X $= Y + 2.5,  X $< 10.0

% Mixed (IC promotes):
X :: 1..10, Y :: 1.0..5.0, X $= Y
```

This is the most principled design, but users must still remember two operator families
and their exact applicability rules.

---

## The clausal opportunity

Clausal is in a better position than all of the above. The existing CLP(FD) implementation
already uses **plain Python comparison operators** without any prefix:

```
% Clausal CLP(FD) — already uses natural operators:
InDomain(X_, 1, 10),
X_ == Y_ + 1,
X_ < 5,
X_ >= 0,
Label([X_, Y_])
```

There is no `#` prefix. The sole thing that identifies a variable as belonging to CLP(FD)
is that it has an `"fd"` attribute (attached by `InDomain`). The comparison operators
inspect variables at runtime and post the right kind of constraint.

This means we can achieve **fully unified syntax** between CLP(FD) and CLP(R): the same
`==`, `<`, `<=`, `>`, `>=`, `!=` operators work for both domains. The domain type is
determined by how the variable was declared, not by which operator was used.

---

## Proposed syntax

### Side-by-side: prior art vs clausal

#### Variable declaration

| System | Integer domain | Real domain |
|---|---|---|
| SWI CLP(FD) | `X in 1..10` | — |
| SWI CLP(R) | — | `{X >= 0, X =< 10}` (implicit) |
| CLP(BNR) | `X::integer(1, 10)` | `X::real(0.0, 1.0)` |
| ECLiPSe IC | `X :: 1..10` | `X :: 1.0..10.0` |
| **clausal (existing FD)** | `InDomain(X_, 1, 10)` | — |
| **clausal (proposed R)** | `InDomain(X_, 1, 10)` | `InReal(X_, 0.0, 1.0)` |

#### Linear constraints

| System | Integer | Real |
|---|---|---|
| SWI CLP(FD) | `X #= Y + 1` | — |
| SWI CLP(R) | — | `{X =:= Y + 1}` |
| CLP(BNR) | `{X == Y + 1}` | `{X == Y + 1.0}` |
| ECLiPSe IC | `X #= Y + 1` | `X $= Y + 1.0` |
| **clausal (existing FD)** | `X_ == Y_ + 1` | — |
| **clausal (proposed R)** | `X_ == Y_ + 1` | `X_ == Y_ + 1.0` |

#### Non-linear constraints

| System | Behavior |
|---|---|
| SWI CLP(R) | `{X * Y >= 0}` — deferred, not actively propagated |
| CLP(BNR) | `{X * Y >= 0}` — active interval propagation |
| ECLiPSe IC | `X $>= 0 * Y` — active |
| **clausal (proposed R)** | `X_ * Y_ >= 0.0` — active interval propagation |

#### Labeling / search

| System | Integer | Real |
|---|---|---|
| SWI CLP(FD) | `label([X, Y])` | — |
| SWI CLP(R) | — | `bb_inf/4` (optimization only) |
| CLP(BNR) | `solve([X, Y])` | `solve([X, Y])` (bisection) |
| ECLiPSe IC | `labeling([X, Y])` | `locate([X, Y], 1.0e-6)` |
| **clausal (existing FD)** | `Label([X_, Y_])` | — |
| **clausal (proposed R)** | `Label([X_, Y_])` | `LabelReal([X_, Y_])` |

### Complete worked examples

#### Pythagorean triple (FD only, existing)

```
% Find integer Pythagorean triples up to 20
pythagorean(A_, B_, C_) <- (
    InDomain([A_, B_, C_], 1, 20),
    A_ * A_ + B_ * B_ == C_ * C_,
    A_ <= B_,
    Label([A_, B_, C_])
)
% → (3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (9, 12, 15), ...
```

#### Unit circle (proposed CLP(R))

```
% Find a point on the unit circle in the first quadrant
unit_circle(X_, Y_) <- (
    InReal(X_, 0.0, 1.0),
    InReal(Y_, 0.0, 1.0),
    X_ * X_ + Y_ * Y_ == 1.0,
    LabelReal([X_, Y_])
)
% → X ≈ 0.7071067811865476, Y ≈ 0.7071067811865476  (among others)
```

#### Comparing FD and R side by side — "between two values"

```
% Integer version (CLP(FD))
between_int(X_) <- (
    InDomain(X_, 3, 7),
    X_ != 5,
    Label([X_])
)
% → X = 3, 4, 6, 7

% Real version (proposed CLP(R))
between_real(X_) <- (
    InReal(X_, 3.0, 7.0),
    LabelReal([X_])
)
% → interval narrowed to [3.0, 7.0], bisection yields points within
```

#### Mixed FD + real: solving a scheduling problem

```
% Worker takes at most 8 hours; rate is a real multiplier
task(Hours_, Cost_) <- (
    InDomain(Hours_, 1, 8),           % integer hours (FD)
    InReal(Cost_, 10.0, 100.0),       % real cost per hour (R)
    Cost_ >= Hours_ * 12.5,           % constraint mixes FD var + real constant
    Hours_ <= 6,
    Label([Hours_]),
    LabelReal([Cost_])
)
% Promotes Hours_ to real interval when mixed constraint is posted
```

#### Trigonometric constraint (proposed, using transcendental interval extension)

```
% Find angle X (in radians) where sin(X) = 0.5, in [0, π]
half_sine(X_) <- (
    InReal(X_, 0.0, 3.141592653589793),
    Sin(X_) == 0.5,
    LabelReal([X_])
)
% → X ≈ 0.5235987755982988  (π/6)
%   X ≈ 2.617993877991494   (5π/6)
```

#### Linear system (proposed)

```
% Solve  2x + 3y = 12,  x - y = 1
linear_system(X_, Y_) <- (
    InReal(X_),
    InReal(Y_),
    2.0 * X_ + 3.0 * Y_ == 12.0,
    X_ - Y_ == 1.0,
    LabelReal([X_, Y_])
)
% → X ≈ 3.0, Y ≈ 2.0
```

---

## Implementation plan

### Phase 1 — `clausal/logic/clpr.py`

New module, mirroring the structure of `clpfd.py`.

#### 1.1 State representation

```python
REAL_KEY = "real"

class RealVar:
    """Real-domain state for one variable.

    Immutable for trail safety — narrowing creates a new instance.
    lo and hi are IEEE doubles; lo is rounded toward -inf, hi toward +inf
    after every arithmetic operation, so the true value is always inside.
    """
    __slots__ = ('lo', 'hi', 'constraints')
    lo: float
    hi: float
    constraints: tuple   # tuple[RealConstraint, ...]
```

The invariant `lo <= hi` always holds. A point value has `lo == hi`. An empty interval
(wipeout) is represented by `lo > hi` and signals failure.

#### 1.2 Interval arithmetic with outward rounding

Use `math.nextafter(x, math.inf)` to round up and `math.nextafter(x, -math.inf)` to
round down. This ensures the true mathematical result is always contained in the computed
float interval, giving soundness despite using IEEE doubles.

```python
import math

def _dn(x: float) -> float:
    """Round x toward -inf by one ULP (for lower bounds)."""
    return math.nextafter(x, -math.inf)

def _up(x: float) -> float:
    """Round x toward +inf by one ULP (for upper bounds)."""
    return math.nextafter(x, math.inf)

def _iadd(alo, ahi, blo, bhi):
    return _dn(alo + blo), _up(ahi + bhi)

def _isub(alo, ahi, blo, bhi):
    return _dn(alo - bhi), _up(ahi - blo)

def _imul(alo, ahi, blo, bhi):
    corners = [alo*blo, alo*bhi, ahi*blo, ahi*bhi]
    return _dn(min(corners)), _up(max(corners))

def _idiv(alo, ahi, blo, bhi):
    # If zero is in denominator, result is [-inf, inf] (or split, for tighter bounds)
    if blo <= 0.0 <= bhi:
        return -math.inf, math.inf
    corners = [alo/blo, alo/bhi, ahi/blo, ahi/bhi]
    return _dn(min(corners)), _up(max(corners))

def _ipow_int(alo, ahi, n: int):
    # Integer exponent — handles negative exponent and even/odd separately
    ...

def _isqrt(alo, ahi):
    # Requires alo >= 0 (propagate lower bound to 0 if negative before calling)
    return _dn(math.sqrt(max(0.0, alo))), _up(math.sqrt(ahi))

def _iabs(alo, ahi):
    if alo >= 0:
        return alo, ahi
    if ahi <= 0:
        return -ahi, -alo
    return 0.0, max(-alo, ahi)

def _imin(alo, ahi, blo, bhi):
    return min(alo, blo), min(ahi, bhi)

def _imax(alo, ahi, blo, bhi):
    return max(alo, blo), max(ahi, bhi)

# Transcendentals (monotone functions: just apply and round)
def _iexp(alo, ahi):
    return _dn(math.exp(alo)), _up(math.exp(ahi))

def _ilog(alo, ahi):
    # Requires alo > 0
    return _dn(math.log(max(1e-308, alo))), _up(math.log(ahi))

# Non-monotone transcendentals require splitting at extrema
def _isin(alo, ahi):
    # Split interval at multiples of π/2 where sin has extrema ±1
    # For large intervals just return [-1, 1]
    ...

def _icos(alo, ahi):
    # Split at multiples of π
    ...

def _iatan(alo, ahi):
    # Monotone increasing on all of ℝ
    return _dn(math.atan(alo)), _up(math.atan(ahi))

def _iasin(alo, ahi):
    # Domain: [-1, 1]; monotone increasing
    return _dn(math.asin(max(-1.0, alo))), _up(math.asin(min(1.0, ahi)))

def _iacos(alo, ahi):
    # Domain: [-1, 1]; monotone decreasing
    return _dn(math.acos(min(1.0, ahi))), _up(math.acos(max(-1.0, alo)))
```

These are the primitives that all constraint propagation and expression evaluation builds
on. Adding a new transcendental later (e.g., `sinh`, `cosh`, `tanh`) is just one new
function here plus registering it in the expression evaluator and compiler term-node list.

#### 1.3 Expression interval evaluator

Mirrors `_expr_domain` in `clpfd.py` but returns `(lo, hi)` float pairs:

```python
def _expr_interval(expr, trail) -> tuple[float, float]:
    """Compute the interval [lo, hi] containing all possible values of expr."""
    expr = deref(expr)
    if isinstance(expr, (int, float)):
        v = float(expr)
        return v, v
    if is_var(expr):
        state = get_attr(expr, REAL_KEY)
        if state is not None:
            return state.lo, state.hi
        # Check if it's an FD var — use its bounds
        fd_state = get_attr(expr, FD_KEY)
        if fd_state is not None:
            return float(domain_min(fd_state.domain)), float(domain_max(fd_state.domain))
        return -math.inf, math.inf
    # Arithmetic term nodes (Add, Sub, Mult, Div, Pow, Negate, Sin, Cos, ...)
    if isinstance(expr, Add):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _iadd(alo, ahi, blo, bhi)
    if isinstance(expr, Sub):
        ...
    if isinstance(expr, Mult):
        ...
    # etc. for all node types including transcendentals
```

#### 1.4 Constraint types

```python
class RealConstraint:
    """Base class for all CLP(R) constraints."""
    __slots__ = ('lhs', 'rhs', 'vars')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        self.vars = _collect_constraint_vars(lhs, rhs)  # reuse from clpfd

    def propagate(self, trail: Trail, queue: deque) -> bool:
        raise NotImplementedError


class RealLeConstraint(RealConstraint):   # lhs <= rhs
class RealLtConstraint(RealConstraint):   # lhs <  rhs (strict)
class RealEqConstraint(RealConstraint):   # lhs == rhs
class RealNeConstraint(RealConstraint):   # lhs != rhs
```

**Propagation for `RealEqConstraint`** — the core narrowing algorithm:

For `lhs == rhs`, compute the interval of each side, intersect them, then narrow each
variable in the expression to be consistent with the intersection:

```
lhs_interval ∩ rhs_interval → common interval C
For each variable V in lhs:  narrow V to be consistent with C given the rest of lhs
For each variable V in rhs:  narrow V to be consistent with C given the rest of rhs
```

For simple cases like `V == expr` (one variable on the left), the narrowing is direct:
`V`'s interval is intersected with the interval of `expr`. For expressions like
`X + Y == C`, we narrow `X` to `C - Y_interval` and `Y` to `C - X_interval`.

Non-linear cases like `X * X == C` on `[4, 9]` yield `X ∈ [-3, -2] ∪ [2, 3]` — split
into two intervals. Since `RealVar` uses a single interval (unlike `FDVar`'s multi-
interval domain), we widen to the hull: `X ∈ [-3, 3]`. Completeness can be recovered via
bisection labeling, which will eventually separate the two solutions.

**Propagation for `RealLeConstraint`** (`lhs <= rhs`):

```
lhs_interval = [alo, ahi],  rhs_interval = [blo, bhi]
narrow lhs above: ahi = min(ahi, bhi)       (lhs can't exceed rhs's max)
narrow rhs below: blo = max(blo, alo)       (rhs must be at least lhs's min)
```

**Propagation for `RealNeConstraint`** (`lhs != rhs`):

Interval arithmetic cannot represent exclusion of a single point from an interval —
`X != 3.0` with `X ∈ [1.0, 5.0]` gives no narrowing. The constraint is stored and
re-checked when variables become ground. If both sides evaluate to the same float value,
fail. This is the one place where CLP(R) is weaker than CLP(FD)'s `!=`.

#### 1.5 Narrowing helper

```python
def _narrow_var(var: Var, new_lo: float, new_hi: float,
                trail: Trail, queue: deque) -> bool:
    """Narrow variable var's interval to [new_lo, new_hi].

    Returns False (wipeout) if new_lo > new_hi.
    Schedules affected constraints for re-propagation via queue.
    Trail-safe: creates new RealVar if bounds change.
    """
    state = get_attr(var, REAL_KEY)
    if state is None:
        return False
    lo = max(state.lo, new_lo)
    hi = min(state.hi, new_hi)
    if lo > hi:
        return False                           # wipeout
    if lo == state.lo and hi == state.hi:
        return True                            # no change, no work
    new_state = RealVar(lo, hi, state.constraints)
    put_attr(var, REAL_KEY, new_state, trail)  # trailed
    queue.extend(state.constraints)            # re-propagate
    return True
```

#### 1.6 Propagation engine

```python
def propagate(queue: deque, trail: Trail) -> bool:
    """Fixpoint narrowing loop. Mirrors clpfd.propagate."""
    seen: set[int] = set()
    while queue:
        constraint = queue.popleft()
        cid = id(constraint)
        if cid in seen:
            continue
        seen.add(cid)
        if not constraint.propagate(trail, queue):
            return False
    return True
```

#### 1.7 Attribute hook

```python
def _real_hook(attr_value, bound_to, trail: Trail) -> bool:
    """Called when a real-constrained var is unified."""
    state = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, (int, float)):
        v = float(bound_to)
        if not (state.lo <= v <= state.hi):
            return False
        # Check ne-constraints (can now test ground equality)
        for c in state.constraints:
            if isinstance(c, RealNeConstraint):
                lo2, hi2 = _expr_interval(c.rhs if c.lhs is ... else c.lhs, trail)
                if lo2 == hi2 == v:
                    return False
        queue: deque = deque(state.constraints)
        return propagate(queue, trail)

    if is_var(bound_to):
        # Merge real state
        other_state = get_attr(bound_to, REAL_KEY)
        if other_state is None:
            # Check if it's an FD var — promote to real
            fd_state = get_attr(bound_to, "fd")
            if fd_state is not None:
                _promote_fd_to_real(bound_to, fd_state, trail)
                other_state = get_attr(bound_to, REAL_KEY)
        if other_state is None:
            put_attr(bound_to, REAL_KEY, state, trail)
            return True
        # Both have real state — intersect intervals, merge constraints
        new_lo = max(state.lo, other_state.lo)
        new_hi = min(state.hi, other_state.hi)
        if new_lo > new_hi:
            return False
        seen_ids: set[int] = set()
        merged: list = []
        for c in state.constraints + other_state.constraints:
            if id(c) not in seen_ids:
                seen_ids.add(id(c))
                merged.append(c)
        new_state = RealVar(new_lo, new_hi, tuple(merged))
        put_attr(bound_to, REAL_KEY, new_state, trail)
        queue: deque = deque(merged)
        return propagate(queue, trail)

    return False  # bound to non-numeric non-var
```

#### 1.8 FD promotion

```python
def _promote_fd_to_real(var: Var, fd_state: FDVar, trail: Trail) -> None:
    """Replace a variable's FD attribute with a real interval [fd_min, fd_max].

    Called when a real constraint is posted on an FD variable, or when a real
    variable unifies with an FD variable. The integrality constraint is relaxed:
    we use the FD domain's outer bounds as the real interval.

    Note: this loses the FD domain's internal holes. If X was {1,3,5} (FD), after
    promotion it becomes [1.0, 5.0] (real). The holes are dropped — real interval
    arithmetic cannot represent them. For most mixed use cases this is acceptable.
    If integrality must be preserved, keep the FD attribute alongside the real one
    (future enhancement: dual-attributed variables).
    """
    lo = float(domain_min(fd_state.domain))
    hi = float(domain_max(fd_state.domain))
    real_state = RealVar(lo, hi, ())
    put_attr(var, REAL_KEY, real_state, trail)
    # Remove the FD attribute to avoid double-constraint
    del_attr(var, FD_KEY, trail)
```

#### 1.9 Top-level API

```python
def in_real(var_or_list, lo: float, hi: float, trail: Trail) -> bool:
    """Post real domain [lo, hi] on Var or list of Vars."""

def real_eq(l, r, trail: Trail) -> bool:
def real_ne(l, r, trail: Trail) -> bool:
def real_lt(l, r, trail: Trail) -> bool:
def real_le(l, r, trail: Trail) -> bool:
def real_gt(l, r, trail: Trail) -> bool:
def real_ge(l, r, trail: Trail) -> bool:

def label_real(vars_list, trail: Trail, eps: float | None = None):
    """Generator: bisect real intervals until IEEE-point or eps width.

    Default (eps=None): bisect until (lo + hi) / 2.0 == lo or == hi in IEEE
    arithmetic — i.e., the interval is indistinguishable from a point at the
    current float precision. This terminates in at most ~53 steps per variable.

    With eps: stop when hi - lo <= eps.

    Strategy: pick the variable with the widest interval (widest-first, analogous
    to first-fail in CLP(FD)), bisect at midpoint, recurse on each half.
    """
```

#### 1.10 Module-level hook registration

```python
register_attr_hook(REAL_KEY, _real_hook)
```

---

### Phase 2 — Unified dispatch in `clpfd.py`

Add a small helper that detects whether any argument is a real variable, and if so
delegates to the CLP(R) functions. The existing FD logic becomes `_fd_eq_core` etc.

```python
def _has_real_attr(x, trail) -> bool:
    x = deref(x)
    if is_var(x):
        return get_attr(x, "real") is not None
    return isinstance(x, float)

def _any_real(l, r, trail) -> bool:
    return _has_real_attr(l, trail) or _has_real_attr(r, trail)

def fd_eq(l, r, trail: Trail) -> bool:
    l, r = deref(l), deref(r)
    l, r = _resolve(l), _resolve(r)
    if _any_real(l, r, trail):
        from clausal.logic.clpr import real_eq
        return real_eq(l, r, trail)
    return _fd_eq_core(l, r, trail)

# fd_ne, fd_lt, fd_le, fd_gt, fd_ge — same pattern
```

Because `float` literals also trigger real dispatch, a constraint like
`X_ * X_ == 2.0` (with `X_` undeclared) will automatically enter CLP(R) without
requiring `InReal(X_)`. For full control, declare the variable explicitly.

**No compiler changes are needed.** The compiler already emits calls to `fd_eq`, `fd_lt`,
etc. After this change they become smart dispatchers.

---

### Phase 3 — New builtins in `clausal/logic/builtins/constraints.py`

```python
@_builtin("InReal", 1)
def _in_real__1(var_or_list, trail, k):
    """InReal(Var) — declare real variable with unbounded domain [-inf, +inf]."""
    from clausal.logic.clpr import in_real
    if in_real(var_or_list, -math.inf, math.inf, trail):
        yield None

@_builtin("InReal", 3)
def _in_real__3(var_or_list, lo, hi, trail, k):
    """InReal(Var, Lo, Hi) — declare real variable with domain [Lo, Hi]."""
    from clausal.logic.clpr import in_real
    if in_real(var_or_list, float(lo), float(hi), trail):
        yield None

@_builtin("LabelReal", 1)
def _label_real__1(vars_list, trail, k):
    """LabelReal(Vars) — bisect real intervals to IEEE float precision."""
    from clausal.logic.clpr import label_real
    yield from label_real(vars_list, trail)

@_builtin("LabelReal", 2)
def _label_real__2(vars_list, eps, trail, k):
    """LabelReal(Vars, Eps) — bisect until interval width <= Eps."""
    from clausal.logic.clpr import label_real
    yield from label_real(vars_list, trail, eps=float(eps))
```

**Transcendental builtins** (posted as constraints, not evaluated eagerly):

```python
@_builtin("Sin", 2)    # Sin(X_, Y_)  —  Y == sin(X)
@_builtin("Cos", 2)    # Cos(X_, Y_)  —  Y == cos(X)
@_builtin("Exp", 2)    # Exp(X_, Y_)  —  Y == exp(X)
@_builtin("Log", 2)    # Log(X_, Y_)  —  Y == log(X)
@_builtin("Sqrt", 2)   # Sqrt(X_, Y_) —  Y == sqrt(X)
@_builtin("Abs", 2)    # Abs(X_, Y_)  —  Y == abs(X)
```

Alternatively, transcendental constraints can be expressed via expression syntax if we
add `Sin`, `Cos` etc. as recognised term-node types in the compiler. The two-argument
builtin form is simpler to implement first; expression syntax is a follow-on.

---

### Phase 4 — `docs/clpr.md`

Following the style of `docs/constraints.md` and `docs/clpb.md`.

---

### Phase 5 — `tests/test_clpr.py`

#### Interval arithmetic unit tests

```python
class TestIntervalArithmetic:
    def test_iadd_basic(self):
        assert _iadd(1.0, 2.0, 3.0, 4.0) == (4.0, 6.0)

    def test_iadd_outward_rounding(self):
        lo, hi = _iadd(0.1, 0.1, 0.2, 0.2)
        # 0.1 + 0.2 is not exactly 0.3 in IEEE; interval must contain 0.3
        assert lo <= 0.3 <= hi

    def test_imul_negative(self):
        lo, hi = _imul(-2.0, -1.0, 3.0, 4.0)
        assert lo <= -8.0 and hi >= -3.0

    def test_idiv_zero_in_denominator(self):
        lo, hi = _idiv(1.0, 2.0, -1.0, 1.0)
        assert lo == -math.inf and hi == math.inf

    def test_isqrt(self):
        lo, hi = _isqrt(4.0, 9.0)
        assert lo <= 2.0 and hi >= 3.0

    def test_iexp_ilog_roundtrip(self):
        lo, hi = _iexp(1.0, 2.0)
        lo2, hi2 = _ilog(lo, hi)
        assert lo2 <= 1.0 <= 2.0 <= hi2
```

#### RealVar state tests

```python
class TestRealVar:
    def test_in_real_bounds(self):
        trail = Trail()
        x = Var()
        assert in_real(x, 0.0, 1.0, trail)
        state = get_attr(x, REAL_KEY)
        assert state.lo == 0.0 and state.hi == 1.0

    def test_in_real_list(self):
        trail = Trail()
        x, y = Var(), Var()
        assert in_real([x, y], -5.0, 5.0, trail)
        for v in [x, y]:
            s = get_attr(v, REAL_KEY)
            assert s.lo == -5.0 and s.hi == 5.0

    def test_unify_in_bounds(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        assert unify(x, 0.5, trail)

    def test_unify_out_of_bounds_fails(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        assert not unify(x, 2.0, trail)

    def test_backtrack_restores_domain(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        mark = trail.mark()
        in_real(x, 0.0, 5.0, trail)
        assert get_attr(x, REAL_KEY).hi == 5.0
        trail.undo(mark)
        assert get_attr(x, REAL_KEY).hi == 10.0
```

#### Linear constraint tests

```python
class TestLinearConstraints:
    def test_eq_narrows_both(self):
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 10.0, trail)
        in_real(y, 0.0, 10.0, trail)
        # X == 3.0: x should be pinned to 3.0
        assert real_eq(x, 3.0, trail)
        s = get_attr(x, REAL_KEY)
        assert s.lo == 3.0 and s.hi == 3.0

    def test_le_narrows_upper(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_le(x, 5.0, trail)
        assert get_attr(x, REAL_KEY).hi <= 5.0

    def test_linear_system(self):
        # 2x + 3y = 12, x - y = 1 → x=3, y=2
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, -100.0, 100.0, trail)
        in_real(y, -100.0, 100.0, trail)
        # 2*x + 3*y == 12  and  x - y == 1
        # After labeling, should converge to x≈3, y≈2
        solutions = list(label_real([x, y], trail))
        assert len(solutions) >= 1

    def test_unsatisfiable_fails(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        assert not real_ge(x, 2.0, trail)
```

#### Non-linear constraint tests

```python
class TestNonLinearConstraints:
    def test_square_narrows(self):
        # X*X <= 4.0, X in [0, 10] → X in [0, 2]
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        # Post X*X <= 4
        xx = Mult(x, x)
        assert real_le(xx, 4.0, trail)
        s = get_attr(x, REAL_KEY)
        assert s.hi <= 2.0 + 1e-12

    def test_unit_circle_labeling(self):
        # X^2 + Y^2 == 1, X,Y in [0,1] → near (0.707, 0.707)
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 1.0, trail)
        in_real(y, 0.0, 1.0, trail)
        xx_yy = Add(Mult(x, x), Mult(y, y))
        assert real_eq(xx_yy, 1.0, trail)
        solutions = list(label_real([x, y], trail, eps=1e-9))
        assert len(solutions) >= 1
        for sol_trail in solutions:
            sx = get_attr(deref(x), REAL_KEY)
            sy = get_attr(deref(y), REAL_KEY)
            mid_x = (sx.lo + sx.hi) / 2
            mid_y = (sy.lo + sy.hi) / 2
            assert abs(mid_x**2 + mid_y**2 - 1.0) < 1e-8

    def test_product_constraint(self):
        # X * Y == 6.0, X in [1,3], Y in [1,3] → X≈2.449, Y≈2.449 or other
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 1.0, 3.0, trail)
        in_real(y, 1.0, 3.0, trail)
        assert real_eq(Mult(x, y), 6.0, trail)
        solutions = list(label_real([x, y], trail, eps=1e-9))
        assert len(solutions) >= 1
```

#### Labeling tests

```python
class TestLabelReal:
    def test_ieee_termination(self):
        # With eps=None, bisection must terminate
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        solutions = list(label_real([x], trail))
        assert len(solutions) >= 1
        # Each solution should be a point interval
        for _ in solutions:
            s = get_attr(deref(x), REAL_KEY)
            assert s.lo == s.hi or s.hi - s.lo < 1e-15

    def test_eps_stopping(self):
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        real_le(x, 0.5, trail)   # narrow to [0, 0.5]
        solutions = list(label_real([x], trail, eps=0.1))
        for _ in solutions:
            s = get_attr(deref(x), REAL_KEY)
            assert s.hi - s.lo <= 0.1 + 1e-15

    def test_backtracking(self):
        # Multiple solutions: X in [0,1], X^2 == [0,1] → many points
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        solutions = list(label_real([x], trail, eps=0.25))
        assert len(solutions) >= 4   # at least one solution per quarter-interval
```

#### Mixed FD + real tests

```python
class TestMixedFDReal:
    def test_fd_promoted_when_real_constraint_posted(self):
        trail = Trail()
        x = Var()
        in_domain(x, 1, 5, trail)          # FD: {1,2,3,4,5}
        assert real_le(x, 3.5, trail)       # mixed: promote x to real [1.0, 3.5]
        assert get_attr(x, REAL_KEY) is not None
        s = get_attr(x, REAL_KEY)
        assert s.lo == 1.0
        assert s.hi <= 3.5

    def test_float_literal_triggers_real(self):
        # X_ == 2.0  with undeclared X_ should auto-enter CLP(R)
        trail = Trail()
        x = Var()
        assert fd_eq(x, 2.0, trail)         # dispatches to real_eq
        s = get_attr(x, REAL_KEY)
        assert s is not None
        assert s.lo == 2.0 and s.hi == 2.0

    def test_compiler_integration_real(self):
        # Integration test via .clausal source
        # InReal(X_, 0.0, 1.0), X_ == 0.5  → succeeds with X=0.5
        ...
```

#### Compiler integration tests (`.clausal` source)

```
% tests/fixtures/clpr_basic.clausal
test_linear(X_, Y_) <- (
    InReal(X_, 0.0, 10.0),
    InReal(Y_, 0.0, 10.0),
    X_ + Y_ == 5.0,
    X_ == 2.0,
    LabelReal([X_, Y_])
)

test_unit_circle(X_, Y_) <- (
    InReal(X_, 0.0, 1.0),
    InReal(Y_, 0.0, 1.0),
    X_ * X_ + Y_ * Y_ == 1.0,
    LabelReal([X_, Y_], 1.0e-9)
)

test_unbounded(X_) <- (
    InReal(X_),
    X_ >= 3.0,
    X_ <= 7.0,
    LabelReal([X_], 1.0e-6)
)
```

---

### Future work: `RealMinimize` / `RealMaximize`

The Phase 1 interval infrastructure is sufficient to implement optimization. The approach:

```
RealMinimize(Expr_, Var_)
```

1. Compute `_expr_interval(Expr)` → `[lo, hi]`
2. `Var_` is unified with `lo` (the minimum of the interval)
3. For non-linear expressions, use bisection: repeatedly post `Expr <= midpoint` and
   narrow until the lower bound stabilizes

This is a bisection-based branch-and-bound. It gives the minimum value to IEEE float
precision. Full global optimisation (finding the unique global minimum of a non-convex
function) is not guaranteed — the interval solver gives a region containing all solutions,
and labeling enumerates them.

---

### Notes on completeness and soundness

**Soundness**: guaranteed. Every interval contains the true real value. If the solver
says `X ∈ [2.0, 3.0]`, there genuinely exists no solution outside that range.

**Completeness**: not guaranteed for non-linear problems. The interval solver may
over-approximate: `X ∈ [1.0, 5.0]` after propagation does not mean every value in
`[1.0, 5.0]` is a solution. Bisection labeling makes this precise in the limit.

**vs SWI CLP(R)**: clausal's CLP(R) is *more* powerful for non-linear problems (active
propagation vs deferred), but *less* precise for linear problems (interval narrowing vs
exact simplex). For pure linear systems with exact rational solutions, interval arithmetic
may leave a very tight but non-point interval.

**vs CLP(BNR)**: essentially the same approach. CLP(BNR) is more mature and has more
optimised narrowing operators; clausal's version is architecturally simpler and integrated
with the existing CLP(FD)/CLP(B) infrastructure.

---

### Files to create / modify

| Action | File | Notes |
|---|---|---|
| Create | `clausal/logic/clpr.py` | Core CLP(R) solver (~600 lines) |
| Modify | `clausal/logic/clpfd.py` | Add `_any_real` + dispatch shim (~30 lines) |
| Modify | `clausal/logic/builtins/constraints.py` | `InReal`, `LabelReal`, transcendental builtins |
| Create | `tests/test_clpr.py` | Full test suite |
| Create | `tests/fixtures/clpr_basic.clausal` | Compiler integration fixtures |
| Create | `docs/clpr.md` | User documentation |
