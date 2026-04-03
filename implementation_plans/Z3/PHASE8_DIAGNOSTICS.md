# Phase 8 — Diagnostics (Unsat Cores, Explanations)

Expose Z3's diagnostic capabilities for debugging and explaining constraint
programs: unsat cores, named constraints, entailment checking, model
inspection, and solver statistics.

**Depends on:** Phase 1 (core infrastructure), at least one of Phases 2/3/4

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `z3_named`, `z3_unsat_core`, `z3_model`, `z3_stats`, `z3_simplify`, `z3_entailed` |
| `clausal/logic/builtins/z3_constraints.py` | Register diagnostic builtins |
| `tests/test_clpz3_diag.py` | Diagnostic tests |

---

## 1. Named Constraints: `z3_named(Constraint, Name)`

Z3's unsat core requires "assumption literals" — named Boolean constants
that track which constraints are active. We provide a user-friendly API
that names constraints:

```python
def z3_named(constraint_expr, name, trail: Trail) -> bool:
    """Add a constraint with a name, trackable via unsat core.

    Creates a Boolean indicator variable for the constraint:
        indicator <=> constraint
    The indicator is used as an assumption in check().
    """
    state = get_z3_state(trail)
    name = deref(name)
    if not isinstance(name, str):
        name = str(name)

    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())

    # Create a named Boolean indicator
    indicator = _z3.Bool(f"_named_{name}")
    state.solver.add(_z3.Implies(indicator, z3_expr))

    # Track the indicator
    if not hasattr(state, '_named_constraints'):
        state._named_constraints = {}
    state._named_constraints[name] = indicator

    # Record undo
    trail.record(lambda: state._named_constraints.pop(name, None))

    return True
```

### How Unsat Core Works with Named Constraints

Z3's `solver.check(*assumptions)` takes assumption literals. If the result
is `unsat`, `solver.unsat_core()` returns a subset of the assumptions that
are sufficient to cause unsatisfiability:

```python
# Internal flow:
indicators = list(state._named_constraints.values())
result = state.solver.check(*indicators)
if result == unsat:
    core = state.solver.unsat_core()
    # core is a list of indicator BoolRefs
    # map back to names
    core_names = [name for name, ind in state._named_constraints.items()
                  if ind in core_set]
```

---

## 2. Unsat Core: `z3_unsat_core(Core)`

```python
def z3_unsat_core(core_var, trail: Trail) -> bool:
    """Get the unsat core as a list of constraint names.

    Checks satisfiability using all named constraints as assumptions.
    If unsatisfiable, Core is unified with a list of names from the
    minimal unsatisfiable subset.

    Fails if the constraints are satisfiable.
    """
    state = get_z3_state(trail)

    named = getattr(state, '_named_constraints', {})
    if not named:
        # No named constraints — can't compute core
        # Check plain satisfiability
        if state.solver.check() == _z3.unsat:
            return unify(core_var, [], trail)  # unsat but no names to report
        return False  # sat — no core

    indicators = list(named.values())
    ind_to_name = {ind.get_id(): name for name, ind in named.items()}

    result = state.solver.check(*indicators)

    if result == _z3.unsat:
        core = state.solver.unsat_core()
        core_set = {c.get_id() for c in core}
        core_names = [ind_to_name[cid] for cid in core_set if cid in ind_to_name]
        return unify(core_var, sorted(core_names), trail)

    return False  # sat — no core


def z3_is_sat(result_var, trail: Trail) -> bool:
    """Check satisfiability, unifying result with "sat", "unsat", or "unknown"."""
    state = get_z3_state(trail)
    r = state.solver.check()
    if r == _z3.sat:
        return unify(result_var, "sat", trail)
    elif r == _z3.unsat:
        return unify(result_var, "unsat", trail)
    else:
        return unify(result_var, "unknown", trail)
```

### Minimal Unsat Core

Z3's unsat core is not necessarily minimal — it may include redundant
constraints. For truly minimal cores, use an iterative deletion algorithm:

```python
def z3_minimal_unsat_core(core_var, trail: Trail) -> bool:
    """Get a minimal unsat core (no redundant constraints).

    Uses iterative deletion: remove each constraint and check if still unsat.
    More expensive than z3_unsat_core but guaranteed minimal.
    """
    state = get_z3_state(trail)
    named = getattr(state, '_named_constraints', {})
    if not named:
        return False

    indicators = list(named.values())
    ind_to_name = {ind.get_id(): name for name, ind in named.items()}

    # First, check if unsat at all
    result = state.solver.check(*indicators)
    if result != _z3.unsat:
        return False

    # Get initial core
    core = list(state.solver.unsat_core())

    # Iteratively try to remove each constraint
    minimal = list(core)
    for c in core:
        candidate = [x for x in minimal if x.get_id() != c.get_id()]
        if state.solver.check(*candidate) == _z3.unsat:
            minimal = candidate  # c was redundant

    core_set = {c.get_id() for c in minimal}
    core_names = [ind_to_name[cid] for cid in core_set if cid in ind_to_name]
    return unify(core_var, sorted(core_names), trail)
```

---

## 3. Model Inspection: `z3_model(Vars, Values)`

```python
def z3_model(vars_list, values_var, trail: Trail) -> bool:
    """Get the current model (satisfying assignment) without binding variables.

    Vars: list of Clausal Vars registered with Z3
    Values: unified with a list of (VarName, Value) pairs

    Unlike label_z3, this does NOT bind the Clausal variables — it just
    returns the model as data.
    """
    state = get_z3_state(trail)
    vars_list = _to_var_list(deref(vars_list))

    if state.solver.check() != _z3.sat:
        return False

    m = state.solver.model()
    pairs = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is not None:
                val = z3_to_python(m.eval(z3_v, model_completion=True))
                pairs.append([str(z3_v), val])

    return unify(values_var, pairs, trail)
```

---

## 4. Entailment: `z3_entailed(Constraint)`

Already partially implemented in Phase 4 for CLP(Q) compatibility. Here we
provide a general version that works with any constraint type:

```python
def z3_entailed_general(constraint_expr, trail: Trail) -> bool:
    """Check if a constraint is entailed (necessarily true) given the store.

    Works by checking if the negation is unsatisfiable.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())

    state.solver.push()
    state.solver.add(_z3.Not(z3_expr))
    result = state.solver.check()
    state.solver.pop()

    return result == _z3.unsat


def z3_disentailed(constraint_expr, trail: Trail) -> bool:
    """Check if a constraint is disentailed (necessarily false) given the store.

    Works by checking if the constraint itself is unsatisfiable.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())

    state.solver.push()
    state.solver.add(z3_expr)
    result = state.solver.check()
    state.solver.pop()

    return result == _z3.unsat
```

---

## 5. Expression Simplification: `z3_simplify(Expr, Simplified)`

Z3 can simplify expressions symbolically:

```python
def z3_simplify(expr, result_var, trail: Trail) -> bool:
    """Simplify a Z3 expression and return the result.

    Uses Z3's built-in simplifier. The result is a simplified Z3 expression
    converted back to a Clausal-friendly form (string for now).
    """
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.IntSort())
    simplified = _z3.simplify(z3_expr)

    # Try to convert back to Python value
    try:
        val = z3_to_python(simplified)
    except (TypeError, ValueError):
        val = str(simplified)

    return unify(result_var, val, trail)
```

---

## 6. Solver Statistics: `z3_stats(Stats)`

```python
def z3_stats(stats_var, trail: Trail) -> bool:
    """Get solver statistics as a list of (Key, Value) pairs.

    Useful for debugging performance issues.
    """
    state = get_z3_state(trail)

    # Run a check first to populate stats
    state.solver.check()
    stats = state.solver.statistics()

    pairs = []
    for i in range(len(stats)):
        key = stats[i][0]
        val = stats[i][1]
        pairs.append([key, val])

    return unify(stats_var, pairs, trail)
```

---

## 7. Constraint Store Dump: `z3_assertions(Assertions)`

```python
def z3_assertions(assertions_var, trail: Trail) -> bool:
    """Get all current Z3 assertions as a list of strings.

    Useful for debugging: see exactly what constraints are posted.
    """
    state = get_z3_state(trail)
    assertions = [str(a) for a in state.solver.assertions()]
    return unify(assertions_var, assertions, trail)
```

---

## 8. Solver Configuration: `z3_set_option(Key, Value)`

```python
def z3_set_option(key, value, trail: Trail) -> bool:
    """Set a Z3 solver option.

    Common options:
    - ("timeout", 30000)  — timeout in milliseconds
    - ("model", True)     — enable model generation
    - ("unsat_core", True) — enable unsat core generation
    """
    state = get_z3_state(trail)
    key = deref(key)
    value = deref(value)
    state.solver.set(key, value)
    return True


def z3_set_logic(logic, trail: Trail) -> bool:
    """Set the SMT-LIB logic for the solver.

    Switches to a logic-specific solver that may be much faster.

    Common logics:
    - "QF_LIA"  — quantifier-free linear integer arithmetic
    - "QF_LRA"  — quantifier-free linear real arithmetic
    - "QF_BV"   — quantifier-free bitvectors
    - "QF_NIA"  — quantifier-free nonlinear integer arithmetic
    - "QF_UFLIA" — QF_LIA + uninterpreted functions
    - "HORN"    — Horn clauses (Datalog, CHC solving)
    """
    state = get_z3_state(trail)
    logic = deref(logic)
    # Replace solver with logic-specific one
    old_assertions = list(state.solver.assertions())
    state.solver = _z3.SolverFor(logic)
    for a in old_assertions:
        state.solver.add(a)
    return True
```

---

## 9. Builtin Registration

```python
@_builtin("z3_named", 2)
def _z3_named__2(constraint_expr, name, trail, k):
    """z3_named(Constraint, Name) — add named constraint for unsat core tracking."""
    from clausal.logic.clpz3 import z3_named
    if z3_named(constraint_expr, name, trail):
        yield None

@_builtin("z3_unsat_core", 1)
def _z3_unsat_core__1(core, trail, k):
    """z3_unsat_core(Core) — get unsat core as list of constraint names."""
    from clausal.logic.clpz3 import z3_unsat_core
    if z3_unsat_core(core, trail):
        yield None

@_builtin("z3_minimal_unsat_core", 1)
def _z3_minimal_unsat_core__1(core, trail, k):
    """z3_minimal_unsat_core(Core) — get minimal unsat core."""
    from clausal.logic.clpz3 import z3_minimal_unsat_core
    if z3_minimal_unsat_core(core, trail):
        yield None

@_builtin("z3_is_sat", 1)
def _z3_is_sat__1(result, trail, k):
    """z3_is_sat(Result) — Result is 'sat', 'unsat', or 'unknown'."""
    from clausal.logic.clpz3 import z3_is_sat
    if z3_is_sat(result, trail):
        yield None

@_builtin("z3_model", 2)
def _z3_model__2(vars_list, values, trail, k):
    """z3_model(Vars, Values) — get model without binding variables."""
    from clausal.logic.clpz3 import z3_model
    if z3_model(vars_list, values, trail):
        yield None

@_builtin("z3_entailed", 1)
def _z3_entailed__1(constraint_expr, trail, k):
    """z3_entailed(Constraint) — succeed if constraint is implied by store."""
    from clausal.logic.clpz3 import z3_entailed_general
    from clausal.logic.variables import deref as _deref
    from clausal.pythonic_ast.nodes import LtE, Lt, GtE, Gt, ArithEq, ArithNeq
    expr = _deref(constraint_expr)
    # Handle comparison nodes
    cmp_types = (LtE, Lt, GtE, Gt, ArithEq, ArithNeq)
    if isinstance(expr, cmp_types):
        if z3_entailed_general(expr, trail):
            yield None
    else:
        # Try as boolean expression
        if z3_entailed_general(expr, trail):
            yield None

@_builtin("z3_disentailed", 1)
def _z3_disentailed__1(constraint_expr, trail, k):
    """z3_disentailed(Constraint) — succeed if constraint is impossible."""
    from clausal.logic.clpz3 import z3_disentailed
    if z3_disentailed(constraint_expr, trail):
        yield None

@_builtin("z3_simplify", 2)
def _z3_simplify__2(expr, result, trail, k):
    """z3_simplify(Expr, Result) — simplify expression via Z3."""
    from clausal.logic.clpz3 import z3_simplify
    if z3_simplify(expr, result, trail):
        yield None

@_builtin("z3_assertions", 1)
def _z3_assertions__1(assertions, trail, k):
    """z3_assertions(List) — get all Z3 assertions as strings."""
    from clausal.logic.clpz3 import z3_assertions
    if z3_assertions(assertions, trail):
        yield None

@_builtin("z3_stats", 1)
def _z3_stats__1(stats, trail, k):
    """z3_stats(Stats) — get solver statistics."""
    from clausal.logic.clpz3 import z3_stats
    if z3_stats(stats, trail):
        yield None

@_builtin("z3_set_option", 2)
def _z3_set_option__2(key, value, trail, k):
    """z3_set_option(Key, Value) — set Z3 solver option."""
    from clausal.logic.clpz3 import z3_set_option
    if z3_set_option(key, value, trail):
        yield None

@_builtin("z3_set_logic", 1)
def _z3_set_logic__1(logic, trail, k):
    """z3_set_logic(Logic) — switch to logic-specific solver."""
    from clausal.logic.clpz3 import z3_set_logic
    if z3_set_logic(logic, trail):
        yield None
```

---

## 10. Clausal Syntax Examples

```prolog
# Debugging: find conflicting constraints
Debug(CORE) <- (
    in_z3([X, Y], 1, 5),
    z3_named(X > 3, "x_big"),
    z3_named(X < 2, "x_small"),
    z3_named(Y == X, "y_eq_x"),
    z3_unsat_core(CORE)
    # CORE should include "x_big" and "x_small"
)

Test("unsat core detects conflict") <- (
    Debug(CORE),
    member("x_big", CORE),
    member("x_small", CORE)
)

# Check entailment
TestEntailed() <- (
    in_z3(X, 1, 5),
    z3_entailed(X >= 1),           # entailed by bounds
    \+ z3_entailed(X == 3)         # not entailed (X could be anything in [1,5])
)

Test("entailment check") <- TestEntailed()

# Solver configuration
Fast(X) <- (
    z3_set_logic("QF_LIA"),        # fast linear integer solver
    z3_set_option("timeout", 5000),
    in_z3(X, 1, 1000000),
    X * 2 == 500000,
    label_z3([X])
)

Test("configured solver") <- Fast(250000)

# Inspect constraint store
Inspect(ASSERTIONS) <- (
    in_z3([X, Y], 0, 10),
    X + Y == 10,
    z3_assertions(ASSERTIONS)
    # ASSERTIONS is a list of Z3 assertion strings
)
```

---

## 11. Tests

### `tests/test_clpz3_diag.py`

```python
class TestNamedConstraints:
    def test_named_and_unsat_core(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(ArithNode(x, '>', 5), "x_big", trail)
        z3_named(ArithNode(x, '<', 3), "x_small", trail)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert "x_big" in names
        assert "x_small" in names

    def test_satisfiable_no_core(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(ArithNode(x, '>', 5), "x_big", trail)
        core = Var()
        assert not z3_unsat_core(core, trail)  # sat → fails

    def test_named_backtrack(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)

        mark = trail.mark()
        z3_named(ArithNode(x, '>', 5), "x_big", trail)
        trail.undo(mark)

        state = get_z3_state(trail)
        named = getattr(state, '_named_constraints', {})
        assert "x_big" not in named

    def test_minimal_core(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(ArithNode(x, '>', 5), "a", trail)
        z3_named(ArithNode(x, '<', 3), "b", trail)
        z3_named(ArithNode(x, '>', 0), "c", trail)  # redundant
        core = Var()
        assert z3_minimal_unsat_core(core, trail)
        names = deref(core)
        assert "a" in names
        assert "b" in names
        # "c" should NOT be in the minimal core


class TestEntailment:
    def test_entailed_by_bounds(self):
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert z3_entailed_general(GtE(x, 5), trail)
        assert z3_entailed_general(LtE(x, 10), trail)

    def test_not_entailed(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert not z3_entailed_general(GtE(x, 5), trail)

    def test_disentailed(self):
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert z3_disentailed(Lt(x, 5), trail)  # x < 5 impossible

    def test_entailed_after_constraint(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, y, trail)
        z3_eq(x, 5, trail)
        assert z3_entailed_general(ArithEq(y, 5), trail)


class TestModel:
    def test_model_without_binding(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        # x should still be unbound
        assert is_var(deref(x))
        # vals should contain the model
        model_data = deref(vals)
        assert len(model_data) == 1
        assert model_data[0][1] in [1, 2, 3]


class TestAssertions:
    def test_dump_assertions(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assertions = Var()
        assert z3_assertions(assertions, trail)
        a_list = deref(assertions)
        assert len(a_list) >= 2  # at least x >= 1 and x <= 10
        assert all(isinstance(s, str) for s in a_list)


class TestSolverConfig:
    def test_set_timeout(self):
        trail = Trail()
        z3_set_option("timeout", 1000, trail)
        state = get_z3_state(trail)
        # Verify option was set (no crash)

    def test_set_logic(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_set_logic("QF_LIA", trail)
        # Existing constraints should be preserved
        state = get_z3_state(trail)
        assert state.solver.check() == z3.sat

    def test_set_logic_preserves_assertions(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 5, trail)
        z3_set_logic("QF_LIA", trail)
        for _ in label_z3([x], trail):
            assert deref(x) == 5


class TestIsSat:
    def test_sat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == "sat"

    def test_unsat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == "unsat"
```

---

## 12. Gotchas

1. **Unsat core requires named constraints.** Without `z3_named`, there's
   nothing to report in the core. `z3_unsat_core` with no named constraints
   returns `[]` if unsat, fails if sat.

2. **Unsat core is not minimal.** Z3's `unsat_core()` returns a subset of
   assumptions but not necessarily the smallest. Use `z3_minimal_unsat_core`
   for truly minimal cores (more expensive).

3. **`z3_set_logic` replaces the solver.** All assertions are copied to the
   new solver, but Z3 internal state (learned clauses, etc.) is lost. Call
   this early, before posting many constraints.

4. **Statistics are only populated after `check()`.** Call `z3_stats` after
   `label_z3` or `z3_check`, not before.

5. **`z3_entailed` calls `check()` twice** (once with negation, once pop).
   For performance-sensitive code, batch entailment checks.

6. **Model inspection without binding:** `z3_model` is useful for debugging
   but doesn't integrate with Clausal's variable binding. The user sees
   string names, not Clausal Var objects.

7. **Timeout handling:** If Z3 times out, `check()` returns `unknown`.
   `z3_is_sat` reports this. `label_z3` treats `unknown` as no solution.
   `z3_unsat_core` fails (can't determine core).

---

## Implementation Order

1. `z3_named()` — named constraint posting
2. `z3_unsat_core()` — basic unsat core
3. `z3_is_sat()` — satisfiability check with result binding
4. `z3_entailed_general()` / `z3_disentailed()` — entailment
5. `z3_assertions()` — constraint store dump
6. `z3_model()` — model inspection
7. `z3_simplify()` — expression simplification
8. `z3_set_option()` / `z3_set_logic()` — solver configuration
9. `z3_stats()` — solver statistics
10. `z3_minimal_unsat_core()` — minimal core (iterative deletion)
11. Builtin registration
12. Tests
