# CLP(R) — Real-domain Constraints

CLP(R) provides constraint logic programming over the reals using **interval arithmetic over IEEE doubles with outward rounding**. Every variable has a closed interval `[lo, hi]`; constraints narrow these intervals toward a fixpoint. Non-linear constraints are propagated actively, not deferred.

The implementation lives in `clausal/logic/clpr.py`.

!!! note
    For CLP(FD) (finite-domain integer constraints), see [Constraints](constraints.md). For CLP(B) (Boolean constraints), see [CLP(B)](clpb.md).

---

## Unified syntax

Clausal's comparison operators are shared between CLP(FD) and CLP(R). The domain is determined by how variables are declared (or inferred from float literals), not by which operator is used:

| Operator | CLP(FD) meaning | CLP(R) meaning |
|---|---|---|
| `==` | integer equality | real equality |
| `!=` | integer disequality | real disequality |
| `<` `>` `<=` `>=` | integer comparisons | real comparisons |

**Dispatch rule:** if either operand is a `float` literal or a variable declared with `InReal`, the constraint goes to CLP(R). Otherwise it goes to CLP(FD).

This means `X * X == 2.0` (with undeclared `X`) automatically enters CLP(R) because `2.0` is a float. No special operators or brace syntax needed.

---

## Builtins

| Builtin | Arity | Description |
|---|---|---|
| `InReal` | 1 | `InReal(Var_or_list)` — declare real variable(s) with domain `[-∞, +∞]` |
| `InReal` | 3 | `InReal(Var_or_list, Lo, Hi)` — declare real variable(s) with domain `[Lo, Hi]` |
| `LabelReal` | 1 | `LabelReal(Vars)` — bisect intervals to IEEE float precision |
| `LabelReal` | 2 | `LabelReal(Vars, Eps)` — bisect until interval width ≤ Eps |

### InReal/1 and InReal/3

Declares one or more real variables. If the variable already has a real domain, intersects with the new bounds. Fails if the intersection is empty.

```clausal
# skip
InReal(X)                    % X ∈ [-∞, +∞]
InReal(X, 0.0, 1.0)          % X ∈ [0, 1]
InReal([X, Y, Z], -5.0, 5.0)   % all three ∈ [-5, 5]
```

### LabelReal/1 and LabelReal/2

Bisects intervals using a **widest-first** strategy (the variable with the largest interval is bisected first, analogous to largest-domain-first in CLP(FD)).

```clausal
# skip
LabelReal([X, Y])            % bisect to IEEE float precision
LabelReal([X, Y], 1.0e-9)   % bisect until width ≤ 1e-9
```

Without an `Eps`, bisection continues until the midpoint equals an endpoint in IEEE arithmetic — the interval is indistinguishable from a point. With `Eps`, it stops when `hi - lo ≤ Eps`.

Each branch of the bisection is a separate solution. Use `LabelReal` after posting all constraints to enumerate solutions.

---

## Constraint examples

### Linear constraints

```clausal
# skip
% Two-variable linear system: 2x + 3y = 12, x - y = 1
linear_system(X, Y) <- (
    InReal(X, -100.0, 100.0),
    InReal(Y, -100.0, 100.0),
    2.0 * X + 3.0 * Y == 12.0,
    X - Y == 1.0,
    LabelReal([X, Y], 1.0e-9)
)
% → X ≈ 3.0, Y ≈ 2.0
```

### Non-linear constraints

```clausal
# skip
% Unit circle (first quadrant)
unit_circle(X, Y) <- (
    InReal(X, 0.0, 1.0),
    InReal(Y, 0.0, 1.0),
    X * X + Y * Y == 1.0,
    LabelReal([X, Y], 1.0e-9)
)
% → X ≈ 0.7071..., Y ≈ 0.7071...  (and other points)
```

```clausal
# skip
% Square root: find x where x^2 = 2
sqrt2(X) <- (
    InReal(X, 0.0, 2.0),
    X * X == 2.0,
    LabelReal([X], 1.0e-12)
)
% → X ≈ 1.4142135623730951
```

### Mixed FD and real

Integer and real variables can appear together. When an FD variable is involved in a real constraint, a real interval is added alongside the existing FD domain — both attributes coexist on the same variable:

```clausal
# skip
% Worker schedule: integer hours, real cost
task(HOURS, COST) <- (
    InDomain(HOURS, 1, 8),         % integer hours (CLP(FD))
    InReal(COST, 10.0, 100.0),     % real cost (CLP(R))
    COST >= HOURS * 12.5,          % mixes FD + real
    HOURS <= 6,
    Label([HOURS]),
    LabelReal([COST], 1.0e-6)
)
```

In this example, `HOURS` keeps its FD domain `{1..8}` even after participating in the real constraint `COST >= HOURS * 12.5`. The FD domain enforces integrality and holes, while the real interval handles continuous narrowing. Both hooks fire independently on unification — the variable is only valid if both agree.

You can also add an FD domain to a variable that already has a real interval:

```clausal
# skip
% Start with a real constraint, then restrict to integers
mixed(X) <- (
    InReal(X, 0.0, 100.0),
    X * X <= 50.0,
    InDomain(X, 1, 10),    % adds FD domain alongside real
    Label([X])
)
```

The FD domain is automatically narrowed against the real interval (and vice versa), so the tightest bounds from either domain are always used.

### Float literals trigger CLP(R) automatically

```clausal
# skip
% No InReal needed — the float literal 9.0 triggers CLP(R)
pythagorean_real(X, Y) <- (
    InReal(X, 0.0, 10.0),
    InReal(Y, 0.0, 10.0),
    X * X + Y * Y == 25.0,
    LabelReal([X, Y], 1.0e-6)
)
```

---

## Comparison with other systems

| Feature | SWI CLP(R) | CLP(BNR) | ECLiPSe IC | **Clausal CLP(R)** |
|---|---|---|---|---|
| Non-linear propagation | Deferred | Active | Active | **Active** |
| Arithmetic engine | Simplex | Intervals | Intervals | **Intervals** |
| FD/real unification | — | Separate | `#`/`$` operators | **Same operators** |
| Domain declaration | Implicit | `X::real(lo,hi)` | `X :: lo..hi` | **`InReal(X, lo, hi)`** |
| Labeling | `bb_inf/4` (opt only) | `solve/1` | `locate/2` | **`LabelReal/1,2`** |

---

??? abstract "Soundness and rounding"

    Every arithmetic operation rounds **outward**: lower bounds round toward `−∞`, upper bounds toward `+∞`, using `math.nextafter`. This guarantees that the true mathematical result is always contained inside the computed float interval, even when intermediate IEEE operations introduce rounding error.

    Example: `0.1 + 0.2` is not exactly `0.3` in IEEE 754. After outward rounding, the computed interval for `[0.1, 0.1] + [0.2, 0.2]` contains `0.3`.

    The consequence: intervals can only widen due to rounding, never silently exclude the true value.

??? abstract "RealVar — per-variable state"

    Each constrained variable stores a `RealVar` as an attributed-variable attribute under the key `"real"`:

    ```python
    class RealVar:
        __slots__ = ('lo', 'hi', 'constraints')
        lo: float                    # lower bound, rounded toward -inf
        hi: float                    # upper bound, rounded toward +inf
        constraints: tuple           # tuple[RealConstraint, ...]
    ```

    **Trail safety**: every narrowing creates a new `RealVar` and calls `put_attr(var, "real", new_state, trail)`. The old state is automatically restored on `trail.undo()`. Never mutate in place.

    An empty interval (`lo > hi`) signals wipeout and causes backtracking. A point interval (`lo == hi`) means the variable is fully determined.

??? abstract "HC4 inversion — constraint propagation"

    Equality and inequality constraints are propagated using the **HC4 algorithm**: each constraint narrows the variables in its expression by computing the interval of the expression and inverting it through the expression tree.

    For `lhs == rhs`:

    1. Compute `[llo, lhi]` = interval of `lhs`
    2. Compute `[rlo, rhi]` = interval of `rhs`
    3. Intersect: `C = [max(llo, rlo), min(lhi, rhi)]`
    4. Invert: narrow each variable `V` in `lhs` so that `lhs ∈ C`, and similarly for `rhs`

    **Inversion rules** for each operator:

    | Expression | Constraint | Inversion |
    |---|---|---|
    | `L + R ∈ C` | L | `L ∈ [clo − R_hi, chi − R_lo]` |
    | `L + R ∈ C` | R | `R ∈ [clo − L_hi, chi − L_lo]` |
    | `L − R ∈ C` | L | `L ∈ [clo + R_lo, chi + R_hi]` |
    | `L − R ∈ C` | R | `R ∈ [L_lo − chi, L_hi − clo]` |
    | `L * R ∈ C` | L | `L ∈ C / R_interval` (no narrowing if 0 ∈ R) |
    | `L * R ∈ C` | R | `R ∈ C / L_interval` (no narrowing if 0 ∈ L) |
    | `V * V ∈ C` | V | `V ∈ [−√chi, √chi]` (same-var special case) |
    | `L / R ∈ C` | L | `L ∈ C * R_interval` |
    | `L / R ∈ C` | R | `R ∈ L_interval / C` |
    | `V^n ∈ C`, n even | V | `V ∈ [−chi^(1/n), chi^(1/n)]` (hull) |
    | `V^n ∈ C`, n odd | V | `V ∈ [clo^(1/n), chi^(1/n)]` (monotone) |
    | `−V ∈ C` | V | `V ∈ [−chi, −clo]` |

    **Inequality constraints** (`<=`, `<`) use a simpler scheme:

    - `lhs <= rhs`: narrow `lhs` above `rhs_hi`, narrow `rhs` below `lhs_lo`
    - `lhs < rhs`: same but with one ULP gap (strict)

    **Disequality** (`!=`) is passive: it only fires when both sides evaluate to the same point interval, in which case it fails immediately.

??? abstract "Propagation engine"

    After each narrowing, all constraints attached to the narrowed variable are re-queued. The propagation loop drains the queue until stable (fixpoint) or until a wipeout is detected.

    The queue contains `RealConstraint` objects. Because bounds can only narrow monotonically (never widen), the fixpoint is reached in a finite number of steps — bounded by the number of variable-constraint pairs times the number of distinguishable float intervals (~2^53 per variable).

??? abstract "Bisection labeling"

    `LabelReal` uses an explicit stack-based bisection (not Python recursion) to avoid hitting Python's call stack limit for intervals spanning subnormal floats.

    At each step:

    1. Pick the variable with the widest interval (**widest-first** heuristic).
    2. Compute `mid = (lo + hi) / 2.0`.
    3. If `mid == lo` or `mid == hi` (IEEE termination, or `hi − lo ≤ eps`): this variable is resolved — proceed to label the remaining variables.
    4. Otherwise: push intervals `[lo, mid]` and `[mid, hi]` onto the stack and try each.

    Each leaf of the bisection tree that survives constraint propagation is yielded as a solution. After yielding, the trail is restored so that the next branch can be explored.

??? abstract "FD/Real coexistence"

    When a real constraint is posted on a variable that already has a CLP(FD) domain, a real interval `[float(fd_min), float(fd_max)]` is added **alongside** the existing FD attribute. Both attributes coexist:

    - The **FD hook** enforces integrality and domain holes (e.g., `{1, 2, 5, 6}` excludes 3 and 4).
    - The **Real hook** enforces continuous interval bounds and propagates through real constraints.
    - Both hooks fire independently on unification — the variable is only valid if **both** agree.

    This also works in reverse: posting `InDomain` on a variable that already has a real interval adds an FD attribute narrowed against the real bounds.

    When FD propagation narrows the domain, the real interval is tightened to match. When computing intervals for real constraints, the tightest bounds from both attributes are used.

    Promotion is also triggered when a real variable is unified with an FD variable.

??? abstract "Attribute hook"

    `_real_hook` fires when a real-constrained variable is unified:

    - **Bound to a number**: check that the value lies within `[lo, hi]`, then propagate all attached constraints.
    - **Bound to another Var with real state**: intersect intervals, merge constraint lists, propagate.
    - **Bound to another Var without real state**: transfer real state to the other var (promoting FD state first if present).
    - **Bound to non-numeric, non-Var**: fail.

??? abstract "Interaction with CLP(FD) and dif/2"

    CLP(R) uses the attribute key `"real"`, CLP(FD) uses `"fd"`, and dif/2 uses `"dif"`. All hooks fire independently. A variable can have both `"fd"` and `"real"` attributes simultaneously — the FD domain enforces integrality and holes while the real interval handles continuous narrowing. When both are present, bounds are kept in sync: FD narrowing tightens the real interval, and interval queries return the intersection of both.

    A variable can also have dif constraints under `"dif"` alongside either or both numeric domains.

    The `fd_eq`, `fd_ne`, `fd_lt`, `fd_le`, `fd_gt`, `fd_ge` dispatch functions check for float literals and `"real"` attributes before deciding which solver to invoke.

??? warning "Cross-domain pitfalls"

    **Booleans are not numbers.** Python's `True`/`False` are not valid in CLP(R) or CLP(FD) expressions. Booleans belong to CLP(B). Passing a boolean where a number is expected will cause the constraint to fail or be ignored. Use `0`/`1` explicitly if you need numeric values.

    **Labeling order matters.** If a variable has both FD and real attributes, use `Label` (FD) to enumerate integer values. `LabelReal` bisects the continuous interval and does not enforce integrality — it will find non-integer points within the interval. For mixed-domain variables, label with FD first to fix the integer value, then use `LabelReal` for any remaining real variables.

    **Large integers lose precision in float.** When an FD variable participates in a real constraint, its bounds are converted to IEEE doubles. Integers beyond 2^53 cannot be represented exactly as floats. For ground integer-integer comparisons (e.g., `X == Y` where both are bound to ints), the comparison is done exactly without float conversion. But during interval propagation, the float approximation is used.

---

??? example "Python API"

    ```python
    from clausal.logic.variables import Var, Trail, deref, is_var, get_attr
    from clausal.logic.clpr import (
        REAL_KEY, in_real, label_real,
        real_eq, real_le, real_ge,
    )
    from clausal.terms import Add, Mult

    trail = Trail()
    x, y = Var(), Var()

    # Declare domains
    in_real(x, 0.0, 1.0, trail)
    in_real(y, 0.0, 1.0, trail)

    # Post constraint: x^2 + y^2 == 1  (unit circle, first quadrant)
    real_eq(Add(left=Mult(left=x, right=x), right=Mult(left=y, right=y)),
            1.0, trail)

    # Label with 1e-9 precision, collect first few solutions
    for _ in label_real([x, y], trail, eps=1e-9):
        sx = get_attr(deref(x), REAL_KEY)
        sy = get_attr(deref(y), REAL_KEY)
        mx = (sx.lo + sx.hi) / 2.0
        my = (sy.lo + sy.hi) / 2.0
        print(f"x ≈ {mx:.10f}, y ≈ {my:.10f}")
        # x ≈ 0.7071067812, y ≈ 0.7071067812  (and others)
    ```

    **Inspecting variable state:**

    ```python
    from clausal.logic.clpr import REAL_KEY

    state = get_attr(var, REAL_KEY)
    if state is not None:
        print(f"[{state.lo}, {state.hi}]")   # current interval
        print(f"{len(state.constraints)} constraints attached")
    ```

    **Backtracking:**

    ```python
    trail = Trail()
    x = Var()
    in_real(x, 0.0, 10.0, trail)

    mark = trail.mark()
    real_le(x, 5.0, trail)          # narrows x to [0, 5]
    print(get_attr(x, REAL_KEY).hi)  # 5.0
    trail.undo(mark)
    print(get_attr(x, REAL_KEY).hi)  # 10.0  (restored)
    ```

---

??? info "Test coverage"

    Tests are in `tests/test_clpr.py` (80 tests).

    - **Outward rounding**: `_dn`/`_up` properties, `_iadd` containing 0.3, edge cases
    - **Interval arithmetic**: `_iadd`, `_isub`, `_imul`, `_idiv` (zero denominator), `_ipow_int` (even/odd/negative), `_isqrt`, `_iabs`, `_isin`, `_icos`, `_iexp`/`_ilog` roundtrip
    - **Expression intervals**: float literals, int literals, real vars, unbound vars, Add/Mult/Negate/Pow expressions
    - **RealVar state**: `in_real` bounds, list form, narrowing existing, empty intersection fails, unify succeeds/fails at bounds, backtracking restores, point domain binds, ground int checks, var-var merge, disjoint fails
    - **Linear constraints**: `real_eq` pins var, narrows from both sides; `real_le`/`real_lt`/`real_ge`/`real_gt` narrowing; unsatisfiable cases; `real_ne` ground-equal fails; Add and Sub constraint propagation
    - **Non-linear constraints**: `x^2 <= 4` narrows upper bound; `x^2 == 9` pins; `x^2 == -1` fails; product constraint; Negate; Pow node
    - **Labeling**: IEEE termination (first solution); eps stopping; already-ground; empty list; constrained (x^2=4); unit circle (1e-9 precision); backtrack restores state
    - **FD/real dispatch**: float literal triggers CLP(R), `real_le` dispatched from `fd_le`, real var triggers dispatch, pure FD unaffected
    - **Auto-promotion**: undeclared var + float eq; Mult expr + float rhs; ground float comparison
