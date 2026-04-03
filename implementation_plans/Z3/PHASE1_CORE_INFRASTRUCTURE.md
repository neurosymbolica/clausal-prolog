# Phase 1 — Core Infrastructure (`clpz3.py`)

The foundation layer that everything else builds on. Gets the Var↔Z3 mapping,
expression translation, and trail synchronization right.

---

## Files to Create

| File | Purpose |
|------|---------|
| `clausal/logic/clpz3.py` | Core module: state, var registry, expression translation |
| `clausal/logic/builtins/z3_constraints.py` | Builtin registration for Z3 predicates |
| `tests/test_clpz3.py` | Unit tests |
| `tests/fixtures/z3_basic.clausal` | Integration test fixtures |

## Dependencies

```
pip install z3-solver
```

The `z3-solver` package provides the `z3` Python module. It bundles the Z3
shared library — no system install needed.

**Import guard:** All Z3 imports must be conditional so Clausal works without
Z3 installed:

```python
try:
    import z3 as _z3
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

def _require_z3():
    if not _HAS_Z3:
        raise ImportError(
            "Z3 backend requires the z3-solver package: pip install z3-solver"
        )
```

---

## 1. Z3State — Per-Query Solver State

### Design

Each query (call to `solve()`) gets its own `Z3State`. The state is **not**
stored as a global — it is attached to the trail so that concurrent queries
(in different threads) each have their own solver.

The state is stored as an attribute on a sentinel variable that lives for the
duration of the query. Alternatively, it can be stored in a thread-local and
keyed by trail identity.

**Option A: Trail-attached via sentinel Var**

```python
_Z3_STATE_KEY = "z3_state"
_z3_sentinel = {}  # id(trail) → sentinel Var

def get_z3_state(trail: Trail) -> Z3State:
    tid = id(trail)
    if tid in _z3_sentinel:
        sentinel = _z3_sentinel[tid]
        state = get_attr(sentinel, _Z3_STATE_KEY)
        if state is not None:
            return state
    # Create new state
    sentinel = Var()
    state = Z3State()
    put_attr(sentinel, _Z3_STATE_KEY, state, trail)
    _z3_sentinel[tid] = sentinel
    return state
```

**Problem:** `id(trail)` can be reused after GC. Also, `_z3_sentinel` leaks.

**Option B: Thread-local with explicit init/cleanup**

```python
import threading
_local = threading.local()

def get_z3_state(trail: Trail) -> Z3State:
    state = getattr(_local, 'z3_state', None)
    if state is not None and state.trail is trail:
        return state
    state = Z3State(trail)
    _local.z3_state = state
    return state
```

**Problem:** Only one active Z3State per thread. But this matches how Clausal
already works (one Trail per thread).

**Option C: Attribute on the Trail object itself (simplest)**

Clausal's Trail is a C object, but we can use a Python-side dict keyed by
`id(trail)` with weak cleanup, or (better) add a Python-level `extras` dict
to Trail that survives for the trail's lifetime. Since we can't modify the C
struct easily, use a weak-ref approach:

```python
import weakref
_z3_states: dict[int, Z3State] = {}

def get_z3_state(trail: Trail) -> Z3State:
    tid = id(trail)
    state = _z3_states.get(tid)
    if state is not None:
        return state
    state = Z3State()
    _z3_states[tid] = state
    # Clean up when trail is GC'd
    weakref.finalize(trail, _z3_states.pop, tid, None)
    return state
```

**Recommendation: Option C.** Simplest, no global mutation of Trail, weak-ref
cleanup prevents leaks.

### Z3State Class

```python
class Z3State:
    """Per-query Z3 solver state."""
    __slots__ = ('solver', 'var_map', 'rev_map', '_counter')

    def __init__(self):
        _require_z3()
        self.solver = _z3.Solver()
        self.var_map: dict[int, _z3.ExprRef] = {}    # id(Var) → Z3 const
        self.rev_map: dict[int, Var] = {}             # z3.get_id() → Var
        self._counter: int = 0                        # unique name counter
```

### Gotchas

- **Z3 Context:** By default, Z3 uses a global context. This is fine for
  single-threaded use. For multi-threaded, each thread needs its own `Context`.
  Defer this to Phase 5 (UserPropagateBase needs `fresh()` with new context).
- **Solver choice:** `Solver()` is the generic solver. For specific theories,
  `SolverFor("QF_LIA")` (quantifier-free linear integer arithmetic) can be
  much faster. Consider making this configurable later.
- **Memory:** Z3 expressions are reference-counted in C++. Python refs keep
  them alive. The `var_map` dict holds refs — they're cleaned up when the
  Z3State is GC'd.

---

## 2. Variable Registration

### z3_var_for()

```python
def z3_var_for(var: Var, sort: _z3.SortRef, trail: Trail) -> _z3.ExprRef:
    """Get or create a Z3 constant for a Clausal Var.

    The Z3 constant is cached in var_map by id(Var). The Var also gets
    an attribute 'z3' storing Z3VarInfo so constraint hooks can find it.
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"z3_var_for: expected unbound Var, got {type(var).__name__}")

    state = get_z3_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        # Check sort compatibility
        if existing.sort() != sort:
            raise TypeError(
                f"Z3 variable sort mismatch: already registered as "
                f"{existing.sort()}, now requesting {sort}"
            )
        return existing

    # Create new Z3 constant with a unique name
    state._counter += 1
    name = f"v_{state._counter}"
    z3_const = _z3.Const(name, sort)

    # Register in both maps
    state.var_map[vid] = z3_const
    state.rev_map[z3_const.get_id()] = var

    # Store on the Var as an attribute (trail-safe)
    put_attr(var, Z3_KEY, Z3VarInfo(z3_const, sort), trail)

    return z3_const
```

### Z3VarInfo

```python
Z3_KEY = "z3"

class Z3VarInfo:
    """Attribute value stored on a Clausal Var under key 'z3'."""
    __slots__ = ('z3_const', 'sort')

    def __init__(self, z3_const: _z3.ExprRef, sort: _z3.SortRef):
        self.z3_const = z3_const
        self.sort = sort
```

### Edge Cases

1. **Ground variable:** If `deref(var)` returns a concrete value (int, bool),
   it's already bound — don't create a Z3 constant. Return a Z3 literal:
   ```python
   if not is_var(var):
       if isinstance(var, int):
           return _z3.IntVal(var)
       if isinstance(var, bool):
           return _z3.BoolVal(var)
       if isinstance(var, float):
           return _z3.RealVal(var)
       raise TypeError(f"Cannot convert {type(var)} to Z3")
   ```
   Actually, `z3_var_for` should only handle Vars. Ground values should be
   handled in `clausal_to_z3()`. **Decision: keep z3_var_for strict (Var only),
   handle ground values in the expression translator.**

2. **Variable reuse across backtracks:** When `trail.undo()` unbinds a Var,
   the `put_attr` for `Z3_KEY` is also undone. But the `var_map` entry in
   Z3State persists (it's not trailed). This is fine — the Z3 constant is
   still valid, and re-posting constraints will re-register the attribute.
   
   **Actually, this is a subtle issue:** if the Var gets unbound and then
   re-constrained with a *different* sort, `z3_var_for` would detect the
   sort mismatch. **Solution:** On undo, the `var_map` entry should also be
   removed. Use `trail.record()`:
   
   ```python
   # After registering:
   trail.record(lambda: state.var_map.pop(vid, None))
   trail.record(lambda: state.rev_map.pop(z3_const.get_id(), None))
   ```
   
   **But wait:** This means every backtrack would deregister vars. In most
   cases, the var is re-registered with the same sort immediately. The Z3
   constant is already in the solver's assertion stack — removing it from
   var_map doesn't remove it from Z3. **Better approach:** Don't trail the
   var_map at all. Once a Var is mapped to a Z3 constant, it stays mapped
   for the entire query lifetime. Sort conflicts would be a programming
   error, not a backtracking issue.
   
   **Decision: var_map is not trailed. Sort is fixed at first registration.**

3. **Var identity:** `id(Var)` is stable for the Var's lifetime (it's a C
   object, not relocated by GC). Safe to use as dict key.

---

## 3. Expression Translation

### clausal_to_z3()

Translates Clausal expression trees (simple_ast nodes) and runtime values
to Z3 expressions.

```python
def clausal_to_z3(expr, trail: Trail, default_sort=None) -> _z3.ExprRef:
    """Translate a Clausal expression to Z3.

    Handles:
    - Var → look up in var_map (or create with default_sort)
    - int → IntVal
    - float → RealVal
    - bool → BoolVal
    - Fraction → RealVal(num) / RealVal(den)
    - Add/Sub/Mult/... → Z3 operator application
    - ArithEq/Lt/... → Z3 comparison (returns BoolRef)
    - And/Or/Not → Z3 boolean combinators
    """
    expr = deref(expr)

    # ── Leaf: concrete value ──
    if isinstance(expr, bool):
        return _z3.BoolVal(expr)
    if isinstance(expr, int):
        return _z3.IntVal(expr)
    if isinstance(expr, float):
        return _z3.RealVal(expr)
    if isinstance(expr, Fraction):
        return _z3.RealVal(expr.numerator) / _z3.RealVal(expr.denominator)

    # ── Leaf: logic variable ──
    if is_var(expr):
        # Check if already registered
        state = get_z3_state(trail)
        z3_c = state.var_map.get(id(expr))
        if z3_c is not None:
            return z3_c
        # Not yet registered — use default_sort or error
        if default_sort is None:
            raise ValueError(
                "Unregistered Z3 variable with no default sort. "
                "Use in_z3() or in_z3_real() to declare variables first."
            )
        return z3_var_for(expr, default_sort, trail)

    # ── Arithmetic operators ──
    if isinstance(expr, _Add):
        return clausal_to_z3(expr.left, trail, default_sort) + \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Sub):
        return clausal_to_z3(expr.left, trail, default_sort) - \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Mult):
        return clausal_to_z3(expr.left, trail, default_sort) * \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _FloorDiv):
        return clausal_to_z3(expr.left, trail, default_sort) / \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Mod):
        return clausal_to_z3(expr.left, trail, default_sort) % \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Negate):
        return -clausal_to_z3(expr.operand, trail, default_sort)

    # ── Comparison operators ──
    if isinstance(expr, ArithEq):
        return clausal_to_z3(expr.left, trail, default_sort) == \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, ArithNeq):
        return clausal_to_z3(expr.left, trail, default_sort) != \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Lt):
        return clausal_to_z3(expr.left, trail, default_sort) < \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _LtE):
        return clausal_to_z3(expr.left, trail, default_sort) <= \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _Gt):
        return clausal_to_z3(expr.left, trail, default_sort) > \
               clausal_to_z3(expr.right, trail, default_sort)
    if isinstance(expr, _GtE):
        return clausal_to_z3(expr.left, trail, default_sort) >= \
               clausal_to_z3(expr.right, trail, default_sort)

    # ── Boolean operators ──
    if isinstance(expr, _And):
        return _z3.And(clausal_to_z3(expr.left, trail, _z3.BoolSort()),
                       clausal_to_z3(expr.right, trail, _z3.BoolSort()))
    if isinstance(expr, _Or):
        return _z3.Or(clausal_to_z3(expr.left, trail, _z3.BoolSort()),
                      clausal_to_z3(expr.right, trail, _z3.BoolSort()))
    if isinstance(expr, _Not):
        return _z3.Not(clausal_to_z3(expr.operand, trail, _z3.BoolSort()))

    raise TypeError(f"Cannot translate {type(expr).__name__} to Z3: {expr}")
```

### Import Mapping

The expression translator needs to import Clausal's AST node types. These
come from `clausal.terms` and `clausal.pythonic_ast.nodes`:

```python
from clausal.terms import (
    Add as _Add, Sub as _Sub, Mult as _Mult,
    FloorDiv as _FloorDiv, Mod as _Mod,
    Negate as _Negate,
)
from clausal.pythonic_ast.nodes import (
    ArithEq, ArithNeq,
    Lt as _Lt, LtE as _LtE, Gt as _Gt, GtE as _GtE,
    And as _And, Or as _Or, Not as _Not,
)
```

**Gotcha:** `clausal.terms` re-exports some node types from `pythonic_ast.nodes`.
Verify which module owns each name. The compiler uses imports from both.

### z3_to_python()

```python
def z3_to_python(z3_val: _z3.ExprRef):
    """Convert a Z3 model value to a Python value."""
    if _z3.is_int_value(z3_val):
        return z3_val.as_long()
    if _z3.is_rational_value(z3_val):
        return Fraction(z3_val.numerator_as_long(), z3_val.denominator_as_long())
    if _z3.is_true(z3_val):
        return 1   # Clausal uses 1/0 for booleans, not True/False
    if _z3.is_false(z3_val):
        return 0
    if _z3.is_algebraic_value(z3_val):
        # Approximate as float
        return float(z3_val.approx(20))
    # Fallback: string representation
    return str(z3_val)
```

**Gotcha: Boolean representation.** Clausal's CLP(B) uses `0` and `1` (integers),
not Python `True`/`False`. Z3's `BoolSort` uses `BoolVal(True)` / `BoolVal(False)`.
The converter must map `is_true → 1`, `is_false → 0` to match Clausal semantics.

**Gotcha: Large integers.** Z3's `as_long()` returns a Python int (arbitrary
precision). Safe for Clausal. But `as_long()` raises on non-integer values —
always check `is_int_value()` first.

**Gotcha: Rational values.** Z3 returns rational values for `RealSort()`.
Use `numerator_as_long()` / `denominator_as_long()` → `Fraction`. This matches
CLP(Q) semantics exactly.

---

## 4. Trail ↔ Solver Synchronization

### z3_push()

```python
def z3_push(trail: Trail):
    """Push a Z3 solver scope, recording the undo callback on trail.

    When trail.undo() reaches this point, solver.pop() is called
    automatically, retracting all Z3 constraints added since this push.
    """
    state = get_z3_state(trail)
    state.solver.push()
    trail.record(lambda: state.solver.pop())
```

### z3_add()

```python
def z3_add(constraint: _z3.BoolRef, trail: Trail) -> bool:
    """Add a Z3 constraint in the current scope.

    Returns True on success, False if the constraint store becomes
    immediately inconsistent (optional fast check).
    """
    state = get_z3_state(trail)
    state.solver.add(constraint)
    # Don't call check() here — it's expensive. Let it batch.
    return True
```

**Design decision: eager vs. lazy consistency checking.**

- **Eager:** Call `solver.check()` after every `add()`. Detects failure early
  but is extremely expensive (each check is a full SAT solve).
- **Lazy:** Just `add()` and defer checking to labeling/explicit check. Matches
  how CLP(FD) works — constraints are posted, propagation happens, but full
  consistency isn't checked until labeling.
- **Recommendation: Lazy.** Only check at labeling time or when explicitly
  requested. This matches Clausal's semantics and avoids O(n²) solver calls
  during constraint posting.

### Scope Lifecycle

```
solve(goal, module, trail)
  ├─ constraints are posted → solver.add(...)
  ├─ choice point:
  │   trail.mark() + z3_push(trail)
  │   ├─ branch A: more constraints, label → check()
  │   └─ trail.undo(mark) → solver.pop() via callback
  ├─ choice point:
  │   trail.mark() + z3_push(trail)
  │   └─ branch B: ...
  └─ query ends → Z3State GC'd → solver freed
```

### When to Push

Z3 push/pop should happen at **choice points** (before branching), not at
every constraint posting. The labeling generator handles this:

```python
def label_z3(vars_list, trail):
    state = get_z3_state(trail)
    z3_vars = [...]

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        mark = trail.mark()
        # Bind Clausal vars
        for cv, z3v in zip(clausal_vars, z3_vars):
            val = z3_to_python(m.eval(z3v, model_completion=True))
            unify(cv, val, trail)
        yield None          # solution
        trail.undo(mark)    # unbind Clausal vars
        # Block this solution (permanent — not pushed)
        state.solver.add(_z3.Or([z3v != m.eval(z3v, model_completion=True)
                                 for z3v in z3_vars]))
```

**Note:** Blocking clauses are added **without** push/pop. They persist across
iterations. This is correct — we don't want to revisit already-found solutions.

**Gotcha: trail.undo unbinds Clausal vars but doesn't undo solver.add.**
This is intentional. The blocking clause is not a backtrackable constraint —
it's a permanent assertion for the enumeration loop. The solver's scope doesn't
change during enumeration. Push/pop is only used when Clausal backtracks over
the labeling generator itself (e.g., the caller's choice point fails).

For that outer backtracking, the caller would have done `trail.mark()` before
entering the predicate that calls `label_z3`. When the caller does
`trail.undo(mark)`, any `z3_push` callbacks recorded after that mark fire,
popping the solver scope and removing all constraints (including blocking
clauses) added since.

---

## 5. Builtin Registration

### File: `clausal/logic/builtins/z3_constraints.py`

```python
"""Z3-backed constraint builtins.

These predicates use Z3 as the constraint solver backend instead of
Clausal's native CLP(FD)/CLP(B)/CLP(Q) solvers. They follow the same
Clausal syntax and semantics.
"""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


# Phase 2: Integer constraints
@_builtin("in_z3", 3)
def _in_z3__3(var_or_list, lo, hi, trail, k):
    """in_z3(Var, Lo, Hi) — post integer domain [Lo, Hi] via Z3."""
    from clausal.logic.clpz3 import in_z3 as _fn
    if _fn(var_or_list, lo, hi, trail):
        yield None

@_builtin("label_z3", 1)
def _label_z3__1(vars_list, trail, k):
    """label_z3(Vars) — enumerate integer solutions via Z3."""
    from clausal.logic.clpz3 import label_z3 as _fn
    yield from _fn(vars_list, trail)

@_builtin("all_different_z3", 1)
def _all_different_z3__1(vars_list, trail, k):
    """all_different_z3(Vars) — Z3 Distinct constraint."""
    from clausal.logic.clpz3 import all_different_z3 as _fn
    if _fn(vars_list, trail):
        yield None

# ... more builtins added in later phases ...
```

**The `_builtin` decorator** (from `_registry.py`) takes `(functor, arity)`,
wraps the generator function to trampoline protocol, and stores in `_BUILTINS`.

**The builtin signature** is `fn(*args, trail, k)` where `k` is an unused
continuation parameter. The function is a generator:
- `yield None` = one solution (like Prolog success)
- `yield from generator` = delegate to a multi-solution generator
- Falling off the end = failure (no solutions)

---

## 6. Tests

### Unit Tests: `tests/test_clpz3.py`

```python
"""Tests for Z3 integration: core infrastructure (Phase 1)."""

import pytest

# Skip all tests if z3-solver not installed
z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    get_z3_state, z3_var_for, z3_push, z3_add,
    clausal_to_z3, z3_to_python,
    Z3State, Z3VarInfo, Z3_KEY,
)


class TestZ3State:
    def test_create_state(self):
        trail = Trail()
        state = get_z3_state(trail)
        assert isinstance(state, Z3State)
        assert state.solver is not None

    def test_same_state_same_trail(self):
        trail = Trail()
        s1 = get_z3_state(trail)
        s2 = get_z3_state(trail)
        assert s1 is s2

    def test_different_trails_different_states(self):
        t1, t2 = Trail(), Trail()
        s1, s2 = get_z3_state(t1), get_z3_state(t2)
        assert s1 is not s2


class TestVarRegistration:
    def test_register_int_var(self):
        trail = Trail()
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        assert z3_x.sort() == z3.IntSort()

    def test_same_var_same_constant(self):
        trail = Trail()
        x = Var()
        z3_x1 = z3_var_for(x, z3.IntSort(), trail)
        z3_x2 = z3_var_for(x, z3.IntSort(), trail)
        assert z3_x1 is z3_x2

    def test_different_vars_different_constants(self):
        trail = Trail()
        x, y = Var(), Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        z3_y = z3_var_for(y, z3.IntSort(), trail)
        assert z3_x is not z3_y

    def test_sort_mismatch_raises(self):
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        with pytest.raises(TypeError, match="sort mismatch"):
            z3_var_for(x, z3.BoolSort(), trail)

    def test_ground_var_raises(self):
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        with pytest.raises(TypeError, match="expected unbound Var"):
            z3_var_for(x, z3.IntSort(), trail)

    def test_attvar_info_stored(self):
        trail = Trail()
        from clausal.logic.variables import get_attr
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        info = get_attr(x, Z3_KEY)
        assert info is not None
        assert info.z3_const is z3_x
        assert info.sort == z3.IntSort()

    def test_bool_var(self):
        trail = Trail()
        b = Var()
        z3_b = z3_var_for(b, z3.BoolSort(), trail)
        assert z3_b.sort() == z3.BoolSort()

    def test_real_var(self):
        trail = Trail()
        r = Var()
        z3_r = z3_var_for(r, z3.RealSort(), trail)
        assert z3_r.sort() == z3.RealSort()


class TestExpressionTranslation:
    def test_int_literal(self):
        trail = Trail()
        result = clausal_to_z3(42, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == 42

    def test_bool_literal(self):
        trail = Trail()
        assert z3.is_true(clausal_to_z3(True, trail))
        assert z3.is_false(clausal_to_z3(False, trail))

    def test_float_literal(self):
        trail = Trail()
        result = clausal_to_z3(3.14, trail)
        # Z3 RealVal

    def test_var_lookup(self):
        trail = Trail()
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(x, trail)
        assert result is z3_x

    def test_unregistered_var_with_default_sort(self):
        trail = Trail()
        x = Var()
        result = clausal_to_z3(x, trail, default_sort=z3.IntSort())
        assert result.sort() == z3.IntSort()

    def test_unregistered_var_no_sort_raises(self):
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="Unregistered"):
            clausal_to_z3(x, trail)

    def test_addition(self):
        from clausal.terms import Add
        trail = Trail()
        x, y = Var(), Var()
        z3_var_for(x, z3.IntSort(), trail)
        z3_var_for(y, z3.IntSort(), trail)
        result = clausal_to_z3(Add(x, y), trail)
        assert result.num_args() == 2

    def test_nested_arithmetic(self):
        from clausal.terms import Add, Mult
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        # 2 * x + 3
        expr = Add(Mult(2, x), 3)
        result = clausal_to_z3(expr, trail)
        # Should be a valid Z3 expression
        assert result.sort() == z3.IntSort()

    def test_comparison_to_bool(self):
        from clausal.pythonic_ast.nodes import ArithEq
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(ArithEq(left=x, right=5), trail)
        assert result.sort() == z3.BoolSort()


class TestZ3ToPython:
    def test_int_value(self):
        assert z3_to_python(z3.IntVal(42)) == 42
        assert isinstance(z3_to_python(z3.IntVal(42)), int)

    def test_negative_int(self):
        assert z3_to_python(z3.IntVal(-7)) == -7

    def test_large_int(self):
        big = 10**100
        assert z3_to_python(z3.IntVal(big)) == big

    def test_bool_true(self):
        assert z3_to_python(z3.BoolVal(True)) == 1

    def test_bool_false(self):
        assert z3_to_python(z3.BoolVal(False)) == 0

    def test_rational(self):
        from fractions import Fraction
        result = z3_to_python(z3.RealVal("3/7"))
        assert result == Fraction(3, 7)


class TestTrailSync:
    def test_push_pop_via_trail(self):
        trail = Trail()
        state = get_z3_state(trail)
        x = z3.Int('x')
        state.solver.add(x > 0)

        mark = trail.mark()
        z3_push(trail)
        state.solver.add(x < 0)  # contradictory in this scope
        assert state.solver.num_scopes() == 1

        trail.undo(mark)
        assert state.solver.num_scopes() == 0
        # x > 0 still there, x < 0 retracted
        assert state.solver.check() == z3.sat

    def test_nested_push_pop(self):
        trail = Trail()
        state = get_z3_state(trail)

        mark1 = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int('x') > 0)

        mark2 = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int('x') > 10)

        assert state.solver.num_scopes() == 2
        trail.undo(mark2)
        assert state.solver.num_scopes() == 1
        trail.undo(mark1)
        assert state.solver.num_scopes() == 0

    def test_push_with_other_trail_entries(self):
        """Trail undo interleaves Z3 pop with Clausal var unbinding."""
        trail = Trail()
        state = get_z3_state(trail)
        x = Var()

        mark = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int('x') > 0)
        unify(x, 42, trail)  # Clausal binding

        assert deref(x) == 42
        assert state.solver.num_scopes() == 1

        trail.undo(mark)
        assert is_var(deref(x))  # Clausal binding undone
        assert state.solver.num_scopes() == 0  # Z3 scope popped
```

### Edge Cases to Test

1. **Empty solver:** `check()` on solver with no constraints → `sat`
2. **Contradictory constraints:** `add(x > 0)` + `add(x < 0)` → `check()` returns `unsat`
3. **Multiple push/pop with interleaved Clausal bindings**
4. **Z3State garbage collection:** Create state, drop trail reference, verify no crash
5. **Large expressions:** Deeply nested arithmetic trees
6. **Mixed sorts in expression:** `Int + Real` (Z3 auto-promotes Int to Real)
7. **Fraction translation:** `Fraction(1, 3)` → `RealVal(1) / RealVal(3)`
8. **Zero and negative values:** `IntVal(0)`, `IntVal(-1000000)`

---

## Implementation Order

1. `Z3State` class and `get_z3_state()` with weak-ref cleanup
2. `Z3VarInfo` and `z3_var_for()` — variable registration
3. `z3_to_python()` — value conversion (needed for tests)
4. `clausal_to_z3()` — expression translation
5. `z3_push()` and `z3_add()` — trail synchronization
6. `z3_constraints.py` — stub builtin file (real builtins in Phase 2)
7. Tests for all of the above

**Estimated complexity:** ~400 lines of code + ~300 lines of tests.

---

## Implementation Issues (Post-Implementation Addendum)

Issues discovered during Phase 1 implementation and their resolutions.

### Issue 1 — `Trail` C extension doesn't support weak references

**Problem:** The plan specified `weakref.finalize(trail, _z3_states.pop, tid, None)` for automatic
cleanup of `_z3_states` when a Trail is GC'd. But `Trail` is a C extension type without a
`tp_weaklistoffset` in its `PyTypeObject`, so `weakref.ref(trail)` raises `TypeError`.

**Initial workaround:** Replaced `weakref.finalize` with explicit `release_z3_state(trail)`, but
this requires callers to manually clean up and is error-prone.

**Fix:** Added `tp_weaklistoffset` support directly to `Trail`:
- Added `PyObject *weakrefs` field to `TrailObject` struct in `_variables.c` and `_variables_capi.h`
- Initialize to `NULL` in `Trail_new`
- Call `PyObject_ClearWeakRefs` at the top of `Trail_dealloc`
- Set `.tp_weaklistoffset = offsetof(TrailObject, weakrefs)` in `TrailType`
- Added `#include <stddef.h>` for `offsetof`

The original `weakref.finalize` design is now fully realized. `_z3_states` cleans up automatically
when the Trail is GC'd. No callers need to do anything.

**Side effect discovered:** Without weakref cleanup, `id(trail)` reuse between tests was causing
test isolation failures (`test_counter_increments`, `test_push_then_constraint_then_backtrack_and_re_add`
failed in suite but passed in isolation). These are now also fixed.

---

### Issue 2 — `z3_add` naming could cause confusion in later phases

**Problem:** `z3_add(constraint, trail)` adds a `BoolRef` to the solver. When Phase 2 arrives with
`z3_eq`, `z3_ne`, etc., `z3_add` looks like it might mean "add (arithmetic)" but it's a low-level
solver primitive.

**Resolution:** Not changed. `z3_add` is never directly exposed as a user predicate — it's an
internal helper used inside `z3_push`, labeling, and future constraint functions. Phase 2 arithmetic
constraints use `z3_eq`/`z3_ne`/etc. which are clearly different. If confusion arises, rename to
`_z3_solver_add` in a future cleanup pass.

---

### Issue 3 — `_to_python_list` silent fallback swallows errors

**Problem:** On `cons_to_list` failure, the original code did `return [val]` — silently treating
an unconvertible value as a 1-element list rather than reporting the error.

**Fix:** Changed the `except` clause to re-raise as `TypeError`:
```python
except (ValueError, TypeError):
    raise TypeError(
        f"Expected a list, got {type(val).__name__!r}: {val!r}"
    )
```

---

### Issue 4 — `clausal_to_z3` with mixed-sort subexpressions

**Problem:** `default_sort` is propagated uniformly to all unregistered vars in an expression tree.
An `Add(int_var, bool_var)` with `default_sort=IntSort()` would try to create `bool_var` as IntSort,
which might silently produce a wrong-sort Z3 variable.

**Resolution:** Already handled by `z3_var_for`'s sort-mismatch check. If `bool_var` was previously
registered as `BoolSort` and is now translated with `default_sort=IntSort()`, `z3_var_for` raises
`TypeError("Z3 variable sort mismatch: ...")` immediately. If the var is unregistered, it gets
`IntSort` — which is only wrong if the programmer mixed sorts intentionally (a usage error). No
code change needed; document that expression trees should be homogeneous in sort.

---

### Issue 5 — `in_z3` singleton domain fast-path not yet implemented

**Problem:** The plan specified that `in_z3(X, 3, 3)` should call `unify(X, lo, trail)` immediately
(matching CLP(FD) behavior where a singleton domain triggers binding). This was not implemented in
Phase 1 because `in_z3` is a Phase 2 function.

**Resolution:** Will be implemented in Phase 2 when `in_z3` is written. The test
`test_singleton_domain` in `test_clpz3_int.py` verifies this behavior:
```python
def test_singleton_domain(self):
    trail = Trail()
    x = Var()
    assert in_z3(x, 3, 3, trail)
    assert deref(x) == 3
```

---

### Issue 6 — `rev_map` correctness not fully tested

**Problem:** `rev_map` (mapping `ExprRef.get_id() → Var`) is populated but unused until Phase 5
(UserPropagateBase callbacks). Tests only verify it's populated, not that lookups work correctly
in edge cases (e.g., after Z3 simplification creates new ExprRefs).

**Resolution:** Deferred to Phase 5. The `get_id()` key is stable for a given `ExprRef` object
within a Z3 context, which is sufficient for Phase 5's callback use case. If issues arise when
implementing Phase 5, revisit.
