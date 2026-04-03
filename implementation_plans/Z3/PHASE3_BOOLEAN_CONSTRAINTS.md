# Phase 3 — CLP(Z3) Boolean Constraints

Boolean constraint predicates backed by Z3's SAT/CDCL solver, replacing
CLP(B)'s BDD-based approach.

**Depends on:** Phase 1 (core infrastructure)  
**Independent of:** Phases 2, 4

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `sat_z3`, `taut_z3`, `sat_count_z3`, `label_z3_bool`, `at_most_z3`, `at_least_z3` |
| `clausal/logic/builtins/z3_constraints.py` | Register boolean constraint builtins |
| `tests/test_clpz3_bool.py` | Boolean constraint tests |
| `tests/fixtures/z3_bool.clausal` | Integration test fixtures |

---

## 1. Boolean Expression Translation

CLP(B) uses Python bitwise operators (`&`, `|`, `^`, `~`) and special terms
(`BoolEq`, `BoolImpl`). Z3 uses `And()`, `Or()`, `Not()`, `Xor()`, `Implies()`.

### Mapping

| CLP(B) expression | Z3 translation |
|--------------------|----------------|
| `X & Y` | `z3.And(x, y)` |
| `X \| Y` | `z3.Or(x, y)` |
| `X ^ Y` | `z3.Xor(x, y)` |
| `~X` | `z3.Not(x)` |
| `BoolEq(X, Y)` | `x == y` |
| `BoolImpl(X, Y)` | `z3.Implies(x, y)` |
| `0` | `z3.BoolVal(False)` |
| `1` | `z3.BoolVal(True)` |

### Implementation: `clausal_bool_to_z3()`

CLP(B) expressions use Python bitwise operators which produce AST nodes at
parse time. At runtime, the expression tree consists of:

- `int` (0 or 1) — boolean constants
- `Var` — boolean variables
- Bitwise op nodes from `clausal.terms`: `BitAnd`, `BitOr`, `BitXor`
- Unary not from `clausal.terms`: `Invert` (for `~X`)
- Special terms: `BoolEq(left, right)`, `BoolImpl(left, right)`

```python
def clausal_bool_to_z3(expr, trail: Trail) -> _z3.BoolRef:
    """Translate a CLP(B)-style Boolean expression to Z3."""
    expr = deref(expr)

    # Constants
    if isinstance(expr, int):
        return _z3.BoolVal(bool(expr))
    if isinstance(expr, bool):
        return _z3.BoolVal(expr)

    # Logic variable → BoolSort
    if is_var(expr):
        return z3_var_for(expr, _z3.BoolSort(), trail)

    # Bitwise operators (from CLP(B) syntax)
    if isinstance(expr, _BitAnd):
        return _z3.And(clausal_bool_to_z3(expr.left, trail),
                       clausal_bool_to_z3(expr.right, trail))
    if isinstance(expr, _BitOr):
        return _z3.Or(clausal_bool_to_z3(expr.left, trail),
                      clausal_bool_to_z3(expr.right, trail))
    if isinstance(expr, _BitXor):
        return _z3.Xor(clausal_bool_to_z3(expr.left, trail),
                       clausal_bool_to_z3(expr.right, trail))
    if isinstance(expr, _Invert):
        return _z3.Not(clausal_bool_to_z3(expr.operand, trail))

    # Special CLP(B) terms
    from clausal.logic.clpb import BoolEq, BoolImpl
    if isinstance(expr, type) and False:
        pass  # guard
    if is_term_instance(expr):
        cls = type(expr)
        if cls is BoolEq:
            return clausal_bool_to_z3(expr.left, trail) == \
                   clausal_bool_to_z3(expr.right, trail)
        if cls is BoolImpl:
            return _z3.Implies(clausal_bool_to_z3(expr.left, trail),
                               clausal_bool_to_z3(expr.right, trail))

    raise TypeError(f"Cannot translate {type(expr).__name__} to Z3 Boolean: {expr}")
```

### Gotcha: Import the Right Node Types

CLP(B) expressions are built at runtime via Python operator overloading on
terms. The actual node types may come from `clausal.terms` or from
`clausal.pythonic_ast.nodes`. Check which:

```python
from clausal.terms import BitAnd as _BitAnd, BitOr as _BitOr, BitXor as _BitXor
```

If these don't exist as separate types, the bitwise operations may produce
generic `Compound` terms. In that case, check `Compound.functor`:

```python
if isinstance(expr, Compound):
    if expr.functor == '&':
        return _z3.And(...)
    if expr.functor == '|':
        return _z3.Or(...)
    # etc.
```

**Action: Verify the actual runtime types produced by `X & Y` where X, Y are
Var instances.** The CLP(B) module in `clpb.py` builds expressions — check
how it represents them.

---

## 2. `sat_z3(Expr)` — Post Boolean Constraint

```python
def sat_z3(expr, trail: Trail) -> bool:
    """Post a Boolean constraint via Z3.

    Translates Clausal Boolean expression to Z3 BoolRef and adds to solver.
    Does NOT check satisfiability eagerly (lazy, like CLP(B)).
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    state.solver.add(z3_expr)
    return True  # lazy — don't check now
```

### Design Decision: Eager vs. Lazy Check

CLP(B) checks satisfiability after every `sat()` call (BDD reduction detects
contradictions immediately). Z3 could do the same:

```python
# Eager variant:
state.solver.add(z3_expr)
return state.solver.check() != _z3.unsat
```

**Trade-off:**
- **Eager:** Catches contradictions immediately, matches CLP(B) semantics.
  But `check()` is expensive — O(SAT solve) per constraint posting.
- **Lazy:** Fast posting, defer checking to labeling. May accumulate
  contradictory constraints without noticing until labeling fails.

**Recommendation:** Start **lazy** (just `add()`). Add an optional `eager=True`
parameter for cases where early detection matters. CLP(B)'s BDD check is
O(polynomial) per constraint; Z3's check is O(NP). Different cost model.

### Alternative: `sat_z3` with Optional Check

```python
def sat_z3(expr, trail: Trail, *, check: bool = False) -> bool:
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    state.solver.add(z3_expr)
    if check:
        return state.solver.check() != _z3.unsat
    return True
```

---

## 3. `taut_z3(Expr, T)` — Tautology Check

```python
def taut_z3(expr, t_var, trail: Trail) -> bool:
    """Tautology check: T=1 if tautology, T=0 if contradiction, else fail.

    Checks if the expression is necessarily true (tautology) or necessarily
    false (contradiction) given current constraints.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)

    # Check if negation is unsatisfiable → tautology
    state.solver.push()
    state.solver.add(_z3.Not(z3_expr))
    neg_result = state.solver.check()
    state.solver.pop()

    if neg_result == _z3.unsat:
        # Expression is a tautology given constraints
        return unify(t_var, 1, trail)

    # Check if expression is unsatisfiable → contradiction
    state.solver.push()
    state.solver.add(z3_expr)
    pos_result = state.solver.check()
    state.solver.pop()

    if pos_result == _z3.unsat:
        # Expression is a contradiction given constraints
        return unify(t_var, 0, trail)

    # Neither tautology nor contradiction — fail (indeterminate)
    return False
```

### Edge Cases

- **No constraints:** `taut_z3(X | ~X, T)` → T = 1 (always true)
- **With constraints:** If `sat_z3(X)` was posted, then `taut_z3(X, T)` → T = 1
- **Contradiction:** `taut_z3(X & ~X, T)` → T = 0
- **Indeterminate:** `taut_z3(X, T)` with no constraints on X → fails
- **T already bound:** If `t_var` is already bound to 1 but expression is not
  a tautology → `unify` fails → `taut_z3` fails. Correct.

---

## 4. `sat_count_z3(Expr, N)` — Count Satisfying Assignments

```python
def sat_count_z3(expr, count_var, trail: Trail) -> bool:
    """Count the number of satisfying assignments for a Boolean expression.

    Uses AllSMT enumeration: check() + block + check() until unsat.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)

    # Collect all Boolean variables in the expression
    bool_vars = _collect_z3_bools(z3_expr)
    if not bool_vars:
        # No variables — expression is constant
        state.solver.push()
        state.solver.add(z3_expr)
        r = state.solver.check()
        state.solver.pop()
        count = 1 if r == _z3.sat else 0
        return unify(count_var, count, trail)

    # Enumerate all satisfying assignments
    state.solver.push()
    state.solver.add(z3_expr)
    count = 0
    while state.solver.check() == _z3.sat:
        count += 1
        m = state.solver.model()
        block = _z3.Or([v != m.eval(v, model_completion=True) for v in bool_vars])
        state.solver.add(block)
    state.solver.pop()

    return unify(count_var, count, trail)


def _collect_z3_bools(expr: _z3.ExprRef) -> list[_z3.ExprRef]:
    """Collect all uninterpreted Boolean constants from a Z3 expression."""
    result = []
    seen = set()

    def _walk(e):
        eid = e.get_id()
        if eid in seen:
            return
        seen.add(eid)
        if _z3.is_const(e) and e.sort() == _z3.BoolSort() and e.decl().arity() == 0:
            # It's a Boolean variable (0-arity function)
            if str(e.decl().kind()) == 'Z3_OP_UNINTERPRETED':
                result.append(e)
        for i in range(e.num_args()):
            _walk(e.arg(i))

    _walk(expr)
    return result
```

### Performance

`sat_count` via enumeration is O(2^n) in the worst case. For large numbers
of variables, this is slow. Z3 doesn't have a native `#SAT` counter.

**Alternative:** Use a dedicated `#SAT` solver like SharpSAT or ApproxMC.
Defer to a later phase.

**Gotcha:** The `model_completion=True` is essential — without it, Z3 may
omit variables, causing the blocking clause to be too weak.

---

## 5. `label_z3_bool(Vars)` — Boolean Labeling

```python
def label_z3_bool(vars_list, trail: Trail):
    """Enumerate 0/1 assignments for Boolean variables via Z3.

    Generator: yields None for each satisfying assignment.
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = []
    clausal_vars = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = z3_var_for(v, _z3.BoolSort(), trail)
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, int) and v in (0, 1):
            pass  # already ground
        else:
            raise TypeError(f"label_z3_bool: expected 0, 1, or Var, got {v}")

    if not z3_vars:
        yield None
        return

    enum_mark = trail.mark()
    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = []
        for z3v in z3_vars:
            val = m.eval(z3v, model_completion=True)
            values.append(1 if _z3.is_true(val) else 0)

        mark = trail.mark()
        ok = True
        for cv, val in zip(clausal_vars, values):
            if not unify(cv, val, trail):
                ok = False
                break

        if ok:
            yield None

        trail.undo(mark)
        block = _z3.Or([z3v != m.eval(z3v, model_completion=True)
                        for z3v in z3_vars])
        state.solver.add(block)
```

---

## 6. Cardinality Constraints (New — Z3 Only)

Z3 provides native cardinality constraints that CLP(B) doesn't have:

```python
def at_most_z3(vars_list, k, trail: Trail) -> bool:
    """At most k of the Boolean vars are true."""
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    k = deref(k)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = [z3_var_for(deref(v), _z3.BoolSort(), trail)
               if is_var(deref(v)) else _z3.BoolVal(bool(deref(v)))
               for v in vars_list]
    state.solver.add(_z3.AtMost(*z3_vars, k))
    return True


def at_least_z3(vars_list, k, trail: Trail) -> bool:
    """At least k of the Boolean vars are true."""
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    k = deref(k)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = [z3_var_for(deref(v), _z3.BoolSort(), trail)
               if is_var(deref(v)) else _z3.BoolVal(bool(deref(v)))
               for v in vars_list]
    state.solver.add(_z3.AtLeast(*z3_vars, k))
    return True


def exactly_z3(vars_list, k, trail: Trail) -> bool:
    """Exactly k of the Boolean vars are true."""
    return at_most_z3(vars_list, k, trail) and at_least_z3(vars_list, k, trail)
```

### Pseudo-Boolean Constraints

Z3 also supports weighted pseudo-Boolean constraints:

```python
def pb_le_z3(weighted_vars, k, trail: Trail) -> bool:
    """Σ weight_i * var_i <= k (pseudo-Boolean less-equal).

    weighted_vars is a list of (Var, Weight) pairs.
    """
    state = get_z3_state(trail)
    pairs = []
    for v, w in weighted_vars:
        v = deref(v)
        w = deref(w)
        z3_v = z3_var_for(v, _z3.BoolSort(), trail) if is_var(v) else _z3.BoolVal(bool(v))
        pairs.append((z3_v, w))
    state.solver.add(_z3.PbLe(pairs, k))
    return True
```

---

## 7. Builtin Registration

```python
# Phase 3 additions to z3_constraints.py

@_builtin("sat_z3", 1)
def _sat_z3__1(expr, trail, k):
    """sat_z3(Expr) — post Boolean constraint via Z3."""
    from clausal.logic.clpz3 import sat_z3
    if sat_z3(expr, trail):
        yield None

@_builtin("taut_z3", 2)
def _taut_z3__2(expr, t, trail, k):
    """taut_z3(Expr, T) — T=1 if tautology, T=0 if contradiction, else fail."""
    from clausal.logic.clpz3 import taut_z3
    if taut_z3(expr, t, trail):
        yield None

@_builtin("sat_count_z3", 2)
def _sat_count_z3__2(expr, count, trail, k):
    """sat_count_z3(Expr, N) — count satisfying assignments via Z3."""
    from clausal.logic.clpz3 import sat_count_z3
    if sat_count_z3(expr, count, trail):
        yield None

@_builtin("label_z3_bool", 1)
def _label_z3_bool__1(vars_list, trail, k):
    """label_z3_bool(Vars) — enumerate 0/1 assignments via Z3."""
    from clausal.logic.clpz3 import label_z3_bool
    yield from label_z3_bool(vars_list, trail)

@_builtin("at_most_z3", 2)
def _at_most_z3__2(vars_list, k, trail, k_unused):
    """at_most_z3(Vars, K) — at most K of Vars are true."""
    from clausal.logic.clpz3 import at_most_z3
    if at_most_z3(vars_list, k, trail):
        yield None

@_builtin("at_least_z3", 2)
def _at_least_z3__2(vars_list, k, trail, k_unused):
    """at_least_z3(Vars, K) — at least K of Vars are true."""
    from clausal.logic.clpz3 import at_least_z3
    if at_least_z3(vars_list, k, trail):
        yield None

@_builtin("exactly_z3", 2)
def _exactly_z3__2(vars_list, k, trail, k_unused):
    """exactly_z3(Vars, K) — exactly K of Vars are true."""
    from clausal.logic.clpz3 import exactly_z3
    if exactly_z3(vars_list, k, trail):
        yield None
```

---

## 8. Tests

### Unit Tests: `tests/test_clpz3_bool.py`

```python
"""Tests for Z3 Boolean constraints (Phase 3)."""

import pytest
z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.clpz3 import (
    sat_z3, taut_z3, sat_count_z3, label_z3_bool,
    at_most_z3, at_least_z3, exactly_z3,
)


class TestSatZ3:
    def test_simple_and(self):
        trail = Trail()
        x, y = Var(), Var()
        # Build X & Y expression
        from clausal.terms import BitAnd
        assert sat_z3(BitAnd(x, y), trail)

    def test_contradiction(self):
        """sat_z3(X & ~X) — lazy, so returns True. Fails at check time."""
        trail = Trail()
        x = Var()
        from clausal.terms import BitAnd, Invert
        sat_z3(BitAnd(x, Invert(x)), trail)
        from clausal.logic.clpz3 import get_z3_state
        state = get_z3_state(trail)
        assert state.solver.check() == z3.unsat

    def test_bool_eq(self):
        trail = Trail()
        x, y = Var(), Var()
        from clausal.logic.clpb import BoolEq
        sat_z3(BoolEq(x, y), trail)
        # X == Y: labeling should give (0,0) and (1,1)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(0, 0), (1, 1)]

    def test_bool_impl(self):
        trail = Trail()
        x, y = Var(), Var()
        from clausal.logic.clpb import BoolImpl
        sat_z3(BoolImpl(x, y), trail)
        # X → Y: (0,0), (0,1), (1,1) but not (1,0)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert (1, 0) not in solutions
        assert len(solutions) == 3

    def test_ground_expression(self):
        trail = Trail()
        # sat_z3(1 & 0) — always false
        from clausal.terms import BitAnd
        sat_z3(BitAnd(1, 0), trail)
        from clausal.logic.clpz3 import get_z3_state
        assert get_z3_state(trail).solver.check() == z3.unsat


class TestTautZ3:
    def test_tautology(self):
        trail = Trail()
        x = Var()
        t = Var()
        from clausal.terms import BitOr, Invert
        # X | ~X is always true
        assert taut_z3(BitOr(x, Invert(x)), t, trail)
        assert deref(t) == 1

    def test_contradiction(self):
        trail = Trail()
        x = Var()
        t = Var()
        from clausal.terms import BitAnd, Invert
        # X & ~X is always false
        assert taut_z3(BitAnd(x, Invert(x)), t, trail)
        assert deref(t) == 0

    def test_indeterminate(self):
        trail = Trail()
        x = Var()
        t = Var()
        # X alone is neither tautology nor contradiction
        assert not taut_z3(x, t, trail)

    def test_with_constraints(self):
        trail = Trail()
        x = Var()
        t = Var()
        # Post X = 1, then check taut(X, T)
        sat_z3(x, trail)  # forces X to true
        assert taut_z3(x, t, trail)
        assert deref(t) == 1


class TestSatCountZ3:
    def test_two_vars_no_constraints(self):
        trail = Trail()
        x, y = Var(), Var()
        from clausal.terms import BitOr
        n = Var()
        # X | Y: 3 satisfying assignments out of 4
        assert sat_count_z3(BitOr(x, y), n, trail)
        assert deref(n) == 3

    def test_tautology_count(self):
        trail = Trail()
        x = Var()
        n = Var()
        from clausal.terms import BitOr, Invert
        assert sat_count_z3(BitOr(x, Invert(x)), n, trail)
        assert deref(n) == 2  # both assignments satisfy

    def test_contradiction_count(self):
        trail = Trail()
        x = Var()
        n = Var()
        from clausal.terms import BitAnd, Invert
        assert sat_count_z3(BitAnd(x, Invert(x)), n, trail)
        assert deref(n) == 0


class TestLabelZ3Bool:
    def test_single_var(self):
        trail = Trail()
        x = Var()
        solutions = []
        for _ in label_z3_bool([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [0, 1]

    def test_two_vars(self):
        trail = Trail()
        x, y = Var(), Var()
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 4
        assert sorted(solutions) == [(0,0), (0,1), (1,0), (1,1)]

    def test_with_constraint(self):
        trail = Trail()
        x, y = Var(), Var()
        from clausal.terms import BitAnd
        sat_z3(BitAnd(x, y), trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(1, 1)]

    def test_empty(self):
        trail = Trail()
        solutions = list(label_z3_bool([], trail))
        assert len(solutions) == 1

    def test_ground(self):
        trail = Trail()
        solutions = list(label_z3_bool([1, 0], trail))
        assert len(solutions) == 1


class TestCardinalityConstraints:
    def test_at_most(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_most_z3(xs, 1, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        # At most 1 true: (0,0,0), (1,0,0), (0,1,0), (0,0,1)
        assert len(solutions) == 4
        assert all(sum(s) <= 1 for s in solutions)

    def test_at_least(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_least_z3(xs, 2, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert all(sum(s) >= 2 for s in solutions)
        assert len(solutions) == 4  # (1,1,0), (1,0,1), (0,1,1), (1,1,1)

    def test_exactly(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        exactly_z3(xs, 2, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert all(sum(s) == 2 for s in solutions)
        assert len(solutions) == 3

    def test_at_most_zero(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_most_z3(xs, 0, trail)
        solutions = list(label_z3_bool(xs, trail))
        assert len(solutions) == 1  # all false
```

### Integration Tests: `tests/fixtures/z3_bool.clausal`

```prolog
# Half adder
HalfAdder(X, Y, SUM, CARRY) <- (
    sat_z3(BoolEq(SUM, X ^ Y)),
    sat_z3(BoolEq(CARRY, X & Y))
)

Test("half adder 1+1") <- HalfAdder(1, 1, SUM, CARRY), SUM == 0, CARRY == 1
Test("half adder 1+0") <- HalfAdder(1, 0, SUM, CARRY), SUM == 1, CARRY == 0
Test("half adder 0+0") <- HalfAdder(0, 0, SUM, CARRY), SUM == 0, CARRY == 0

# Full adder
FullAdder(X, Y, CIN, SUM, COUT) <- (
    sat_z3(BoolEq(S1, X ^ Y)),
    sat_z3(BoolEq(C1, X & Y)),
    sat_z3(BoolEq(SUM, S1 ^ CIN)),
    sat_z3(BoolEq(C2, S1 & CIN)),
    sat_z3(BoolEq(COUT, C1 | C2))
)

Test("full adder 1+1+1") <- FullAdder(1, 1, 1, SUM, COUT), SUM == 1, COUT == 1

# Pigeonhole (2 pigeons, 1 hole → unsat)
Test("pigeonhole 2,1 unsat") <- (
    sat_z3(P1),
    sat_z3(P2),
    at_most_z3([P1, P2], 1),
    \+ label_z3_bool([P1, P2])  # should fail (unsat after constraints)
)

# Exactly-one constraint
Test("exactly one of three") <- (
    exactly_z3([X, Y, Z], 1),
    findall([A, B, C],
        (label_z3_bool([X, Y, Z]), A = X, B = Y, C = Z),
        SOLUTIONS),
    length(SOLUTIONS, 3)
)
```

---

## 9. Gotchas & Edge Cases

1. **CLP(B) expression types:** Verify the exact Python types produced by
   `X & Y`, `~X`, etc. when X is a Var. CLP(B) may wrap them in its own
   BDD-related types. The translator needs to handle the actual runtime types.

2. **Boolean vs Integer sort:** CLP(B) uses 0/1 integers. Z3 has a separate
   `BoolSort`. The `z3_to_python` converter maps `True → 1`, `False → 0`.
   But a Z3 BoolRef cannot be used in integer arithmetic directly. If the
   user mixes Bool and Int Z3 vars, we need coercion:
   ```python
   z3.If(bool_var, z3.IntVal(1), z3.IntVal(0))
   ```

3. **Shared Z3 solver:** If the user mixes `in_z3` (Int) and `sat_z3` (Bool)
   in the same query, both use the same `Z3State.solver`. This is fine — Z3
   handles theory combination natively.

4. **Variable sort conflict:** If a Var is used in both `in_z3(X, 1, 9)` and
   `sat_z3(X & Y)`, the first registers it as IntSort, the second tries
   BoolSort. The sort mismatch will be caught by `z3_var_for`. **Solution:**
   Use `z3.If(x > 0, True, False)` for coercion, or require the user to use
   separate variables. Document this limitation.

5. **`sat_count_z3` performance:** Exponential in the number of variables.
   For > 20 variables, warn or timeout.

6. **Nested Boolean expressions:** `sat_z3(BoolEq(X, BoolImpl(Y, Z & W)))` —
   the translator must handle arbitrary nesting. Test deeply nested expressions.

---

## Implementation Order

1. `clausal_bool_to_z3()` — Boolean expression translation
2. `sat_z3()` — post constraint
3. `label_z3_bool()` — enumerate assignments
4. `taut_z3()` — tautology check
5. `sat_count_z3()` — solution counting
6. `at_most_z3`, `at_least_z3`, `exactly_z3` — cardinality
7. Builtin registration
8. Unit tests
9. Integration tests (half adder, full adder, pigeonhole)
10. Cross-validation: same problems with CLP(B) and Z3, compare results

---

## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — `BoolEq`/`BoolImpl` are not `isinstance`-checkable

**Problem:** The plan showed `isinstance(expr, BoolEq)` but `BoolEq` and `BoolImpl` are created
via `make_predicate`, which produces instances whose type has no importable Python class. There is
no stable class to `isinstance`-check against.

**Fix:** Detect via `type(expr)._functor`:
```python
functor = getattr(type(expr), '_functor', None)
if functor == 'BoolEq': ...
if functor == 'BoolImpl': ...
```
This is how `clpb.py` itself detects them at line 317.

---

### Issue 2 — `clausal_bool_to_z3` delegates to `clausal_to_z3` for most cases

**Observation:** `clausal_to_z3` already handles `BitAnd`/`BitOr`/`BitXor`/`Invert`/`And`/`Or`/
`Not` correctly when called with `default_sort=BoolSort()`. So `clausal_bool_to_z3` only needs
to add three things on top: `int → BoolVal` override, `BoolEq`, and `BoolImpl`. Everything else
falls through to `clausal_to_z3`. Implementation is clean; the plan's description of a "fully
separate translator" was an overstatement.

---

### Issue 3 — `Var & Var` raises `TypeError` — no operator overloading on Var

**Problem:** The plan's test examples showed `X & Y` syntax but `Var` objects don't support
bitwise operators. `x & y` raises `TypeError: unsupported operand type(s) for &: 'AttVar' and
'AttVar'`. Users must construct `BitAnd(left=x, right=y)` explicitly. This is consistent with
the explicit naming convention (Phase 2 Issue 7), but the plan's examples need correcting.

**Resolution:** All tests use `BitAnd(left=x, right=y)` etc. consistently. Not a code bug.

---

### Issue 4 — `_collect_z3_bool_vars` used safer boolean check

**Plan:** Used `str(e.decl().kind()) == 'Z3_OP_UNINTERPRETED'` (fragile string comparison).

**Fix:** Used `z3.is_bool(e) and z3.is_const(e) and not z3.is_true(e) and not z3.is_false(e)`
which is API-stable and does not depend on Z3 internal enum string names.

---

### Issue 5 — Constraint-posting functions lacked trail scoping (latent Phase 2 bug, fixed here)

**Problem:** All constraint-posting functions in Phases 2 and 3 (`in_z3`, `all_different_z3`,
`z3_eq`/`ne`/`lt` etc., `sat_z3`, `at_most_z3`, `at_least_z3`) called `state.solver.add()`
directly without a `z3_push` scope. This means Clausal backtracking did NOT retract the
constraints. A goal that posts a Z3 constraint and then fails would leave the constraint in
the solver permanently for that trail level — incorrect Prolog semantics.

**Fix:** Every constraint-posting function now calls `z3_push(trail)` before `solver.add()`,
wrapping the posted constraints in a trail-linked scope. All 170 tests pass unchanged, confirming
the fix is behaviorally correct.

The two exceptions that remain unscoped (intentionally):
- `sat_count_z3`: uses `solver.push()/pop()` directly for a temporary probe; never commits
- `taut_z3`: same — temporary probe, never commits to trail

---

### Issue 6 — Added `z3_try/1` for non-committing satisfiability probe

**Problem:** After Issue 5's fix, there is no way to test a constraint without posting it. The
"probe without commit" pattern is needed for search strategies, constraint propagation tests, etc.

**Fix:** Added `z3_try(expr, trail)` — translates expr as a Boolean constraint, probes using
`solver.push()/pop()`, returns True if sat, False if unsat. Never modifies the trail or solver
state. Registered as `@_builtin("z3_try", 1)`.

Note: `z3_try` only accepts Boolean expressions (goes through `clausal_bool_to_z3`). A separate
`z3_try_int/2` or similar may be needed for probing integer constraints — deferred.

---

### Issue 7 — `taut_z3` uses two `solver.push()/pop()` pairs (not trail-linked)

**Observation:** `taut_z3` calls `solver.push()/pop()` twice directly (not via `z3_push(trail)`)
because its probes must not persist. This temporarily increases `solver.num_scopes()` by 1 during
each probe. This is correct and intentional. Tested in `test_does_not_modify_solver`.

---

### Issue 8 — `sat_count_z3` counts within existing constraint context

**Observation:** If there are prior constraints in the solver (e.g., from `sat_z3`), `sat_count_z3`
counts assignments satisfying both `expr` AND the prior constraints. This is semantically correct
(count within the current constraint context) but not explicitly tested or documented.

**Resolution:** Added note to `sat_count_z3` docstring and added
`test_counts_within_existing_constraint_context` to `TestSatCountZ3` in `test_clpz3_bool.py`.
The test verifies that with `x` forced true, `sat_count_z3(X | Y)` returns 2, not the
unconstrained 3.
