# Phase 4: CP-SAT Advanced Constraints + Optimization

Circuit, table, automaton, inverse, reservoir constraints, and objective
optimization (minimize/maximize) with hints and search strategies.

---

## 1. Circuit Constraint

```python
def or_circuit(arcs: list, trail: Trail) -> bool:
    """Post a Hamiltonian circuit constraint.

    arcs: list of (tail, head, literal) triples where:
    - tail, head are node indices (0-based integers)
    - literal is a Clausal BoolVar — True iff this arc is in the circuit

    The circuit visits every node exactly once and returns to the start.
    Self-loops (tail == head) mean "skip this node" (for sub-tours).
    """
    state = get_cpsat_state(trail)
    cpsat_arcs = []
    for arc in arcs:
        arc = deref(arc)
        if isinstance(arc, (list, tuple)) and len(arc) == 3:
            tail, head, lit = arc
            tail = int(deref(tail))
            head = int(deref(head))
            lit_cp = _to_cpsat_bool(lit, trail)
            cpsat_arcs.append((tail, head, lit_cp))
        elif isinstance(arc, Compound) and arc.functor == 'arc' and len(arc.args) == 3:
            tail, head, lit = arc.args
            tail = int(deref(tail))
            head = int(deref(head))
            lit_cp = _to_cpsat_bool(lit, trail)
            cpsat_arcs.append((tail, head, lit_cp))
        else:
            raise TypeError(f"Expected arc(Tail, Head, Lit), got {arc}")

    state.model.AddCircuit(cpsat_arcs)
    # Note: AddCircuit does NOT support OnlyEnforceIf
    return True
```

### Gotcha: AddCircuit is Not Reifiable

`AddCircuit` cannot be guarded by `OnlyEnforceIf`.  For backtracking, use
self-loop arcs (`(i, i, skip_i)`) with activation-literal control over the
skip variables to effectively enable/disable nodes.

---

## 2. Table Constraint (Allowed Assignments)

```python
def or_table(vars_list: Any, tuples_list: Any, trail: Trail) -> bool:
    """Post a table (extensional) constraint.

    The combination of variable values must be one of the given tuples.

    vars_list: list of Clausal Vars (registered with CP-SAT)
    tuples_list: list of lists/tuples of integers
    """
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]

    tuples = []
    for t in tuples_list:
        t = deref(t)
        row = [int(deref(v)) for v in (t if isinstance(t, (list, tuple)) else [t])]
        tuples.append(row)

    ct = state.model.AddAllowedAssignments(cpsat_vars, tuples)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True
```

---

## 3. Forbidden Assignments

```python
def or_forbidden(vars_list: Any, tuples_list: Any, trail: Trail) -> bool:
    """Post a forbidden-assignments constraint (negated table).

    The combination of variable values must NOT be any of the given tuples.
    """
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]

    tuples = []
    for t in tuples_list:
        t = deref(t)
        row = [int(deref(v)) for v in (t if isinstance(t, (list, tuple)) else [t])]
        tuples.append(row)

    ct = state.model.AddForbiddenAssignments(cpsat_vars, tuples)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True
```

---

## 4. Inverse Constraint

```python
def or_inverse(vars1: Any, vars2: Any, trail: Trail) -> bool:
    """Post inverse constraint: vars1[vars2[i]] == i for all i.

    Both lists must have the same length n, and all variables must have
    domains within [0, n-1].
    """
    state = get_cpsat_state(trail)
    cpsat_v1 = [_to_cpsat(v, trail) for v in _as_list(vars1)]
    cpsat_v2 = [_to_cpsat(v, trail) for v in _as_list(vars2)]
    ct = state.model.AddInverse(cpsat_v1, cpsat_v2)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True
```

---

## 5. Automaton Constraint

```python
def or_automaton(vars_list: Any, start: int, accepting: list,
                  transitions: list, trail: Trail) -> bool:
    """Post an automaton (regular language) constraint.

    The sequence of variable values must be accepted by the given DFA.

    vars_list: list of Clausal Vars
    start: starting state (int)
    accepting: list of accepting states (ints)
    transitions: list of (state, value, next_state) triples
    """
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]
    start = int(start)
    acc = [int(a) for a in accepting]

    trans = []
    for t in transitions:
        t = deref(t)
        if isinstance(t, (list, tuple)) and len(t) == 3:
            s, v, ns = t
            trans.append((int(deref(s)), int(deref(v)), int(deref(ns))))
        elif isinstance(t, Compound) and len(t.args) == 3:
            s, v, ns = t.args
            trans.append((int(deref(s)), int(deref(v)), int(deref(ns))))
        else:
            raise TypeError(f"Expected transition(State, Value, NextState), got {t}")

    state.model.AddAutomaton(cpsat_vars, start, acc, trans)
    # Note: AddAutomaton does NOT support OnlyEnforceIf
    return True
```

---

## 6. Reservoir Constraint

```python
def or_reservoir(times: list, level_changes: list,
                  min_level: int, max_level: int, trail: Trail) -> bool:
    """Post a reservoir constraint.

    Events happen at given times, each changing the reservoir level.
    The level must stay within [min_level, max_level] at all times.

    times: list of IntVar or int (event times)
    level_changes: list of int (positive = inflow, negative = outflow)
    """
    state = get_cpsat_state(trail)
    times_cp = [_to_cpsat(t, trail) if is_var(deref(t)) else int(deref(t))
                for t in times]
    changes = [int(deref(c)) for c in level_changes]

    state.model.AddReservoirConstraint(
        times_cp, changes, min_level, max_level
    )
    return True
```

---

## 7. Minimize / Maximize

```python
def or_minimize(expr: Any, val: Any, trail: Trail):
    """Minimize a CP-SAT expression and unify val with the optimal value.

    Generator: yields once with the optimal solution bound to variables.
    Fails if infeasible.
    """
    state = get_cpsat_state(trail)
    cpsat_expr = clausal_to_cpsat(expr, trail)
    state.model.Minimize(cpsat_expr)

    _apply_assumptions(state)
    status = state.solver.Solve(state.model)

    if status == _OPTIMAL:
        obj_val = int(state.solver.ObjectiveValue())
        # Bind all registered variables to their optimal values
        mark = trail.mark()
        for idx, clausal_var in state.rev_map.items():
            cpsat_var = state.var_map[id(clausal_var)]
            value = state.solver.Value(cpsat_var)
            unify(clausal_var, value, trail)
        if unify(val, obj_val, trail):
            yield None
        trail.undo(mark)
    elif status == _FEASIBLE:
        # Feasible but possibly not optimal (solver timeout, etc.)
        obj_val = int(state.solver.ObjectiveValue())
        mark = trail.mark()
        for idx, clausal_var in state.rev_map.items():
            cpsat_var = state.var_map[id(clausal_var)]
            value = state.solver.Value(cpsat_var)
            unify(clausal_var, value, trail)
        if unify(val, obj_val, trail):
            yield None
        trail.undo(mark)
    # else: INFEASIBLE — fail (generator returns without yielding)


def or_maximize(expr: Any, val: Any, trail: Trail):
    """Maximize a CP-SAT expression and unify val with the optimal value."""
    state = get_cpsat_state(trail)
    cpsat_expr = clausal_to_cpsat(expr, trail)
    state.model.Maximize(cpsat_expr)

    _apply_assumptions(state)
    status = state.solver.Solve(state.model)

    if status in (_OPTIMAL, _FEASIBLE):
        obj_val = int(state.solver.ObjectiveValue())
        mark = trail.mark()
        for idx, clausal_var in state.rev_map.items():
            cpsat_var = state.var_map[id(clausal_var)]
            value = state.solver.Value(cpsat_var)
            unify(clausal_var, value, trail)
        if unify(val, obj_val, trail):
            yield None
        trail.undo(mark)
```

### Gotcha: Objective is Model-Wide

CP-SAT supports only one objective per model.  Calling `model.Minimize()`
or `model.Maximize()` overwrites any previous objective.  For multi-objective
optimization, use weighted sum:

```python
ortools.cpsat.minimize(3*X + 5*Y, Cost)
```

Or use successive optimization (solve, fix one objective, optimize the other).

---

## 8. Solution Hints

```python
def or_hint(vars_list: Any, values_list: Any, trail: Trail) -> bool:
    """Provide solution hints to warm-start the solver.

    hints guide the solver toward a feasible solution, potentially
    reducing solve time.  Hints are not constraints — the solver may
    ignore them.
    """
    state = get_cpsat_state(trail)
    vars_ = _as_list(vars_list)
    vals = _as_list(values_list)
    if len(vars_) != len(vals):
        raise ValueError("or_hint: vars and values must have same length")
    for v, val in zip(vars_, vals):
        cpsat_var = _to_cpsat(v, trail)
        state.model.AddHint(cpsat_var, int(deref(val)))
    return True
```

---

## 9. Decision Strategy

```python
def or_decision_strategy(vars_list: Any, var_strategy: str,
                          domain_strategy: str, trail: Trail) -> bool:
    """Set the search strategy for variable/value selection.

    var_strategy: 'choose_first', 'choose_lowest_min', 'choose_highest_max',
                  'choose_min_domain_size', 'choose_max_domain_size'
    domain_strategy: 'select_min_value', 'select_max_value',
                     'select_lower_half', 'select_upper_half'
    """
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]

    var_strats = {
        'choose_first': _cp_model.CHOOSE_FIRST,
        'choose_lowest_min': _cp_model.CHOOSE_LOWEST_MIN,
        'choose_highest_max': _cp_model.CHOOSE_HIGHEST_MAX,
        'choose_min_domain_size': _cp_model.CHOOSE_MIN_DOMAIN_SIZE,
        'choose_max_domain_size': _cp_model.CHOOSE_MAX_DOMAIN_SIZE,
    }
    dom_strats = {
        'select_min_value': _cp_model.SELECT_MIN_VALUE,
        'select_max_value': _cp_model.SELECT_MAX_VALUE,
        'select_lower_half': _cp_model.SELECT_LOWER_HALF,
        'select_upper_half': _cp_model.SELECT_UPPER_HALF,
    }

    vs = var_strats.get(var_strategy)
    ds = dom_strats.get(domain_strategy)
    if vs is None:
        raise ValueError(f"Unknown var_strategy: {var_strategy}")
    if ds is None:
        raise ValueError(f"Unknown domain_strategy: {domain_strategy}")

    state.model.AddDecisionStrategy(cpsat_vars, vs, ds)
    return True
```

---

## 10. Tests (Phase 4)

```python
class TestCPSATCircuit:

    def test_tsp_3_cities(self):
        """3-city TSP via circuit constraint."""
        trail = Trail()
        # Nodes: 0, 1, 2
        # BoolVars for each possible arc
        arcs_vars = {}
        for i in range(3):
            for j in range(3):
                if i != j:
                    arcs_vars[(i, j)] = Var()
                    or_bool(arcs_vars[(i, j)], trail)

        arcs = []
        for (i, j), v in arcs_vars.items():
            arcs.append((i, j, v))

        or_circuit(arcs, trail)
        assert or_check(trail)

    def test_circuit_2_nodes(self):
        """2-node circuit: must use both arcs 0->1 and 1->0."""
        trail = Trail()
        a01, a10 = Var(), Var()
        or_bool(a01, trail)
        or_bool(a10, trail)
        or_circuit([(0, 1, a01), (1, 0, a10)], trail)
        assert or_check(trail)


class TestCPSATTable:

    def test_allowed_assignments(self):
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 1, 3, trail)
        or_in(y, 1, 3, trail)
        or_table([x, y], [[1, 2], [2, 3], [3, 1]], trail)
        count = sum(1 for _ in label_or([x, y], trail))
        assert count == 3

    def test_forbidden_assignments(self):
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 1, 2, trail)
        or_in(y, 1, 2, trail)
        or_forbidden([x, y], [[1, 1], [2, 2]], trail)
        # Allowed: (1,2), (2,1)
        count = sum(1 for _ in label_or([x, y], trail))
        assert count == 2


class TestCPSATOptimization:

    def test_minimize(self):
        """Minimize x + y subject to x + y >= 10."""
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 0, 100, trail)
        or_in(y, 0, 100, trail)
        state = get_cpsat_state(trail)
        cx = state.var_map[id(x)]
        cy = state.var_map[id(y)]
        or_add_constraint(cx + cy >= 10, trail)
        val = Var()
        for _ in or_minimize(Add(x, y), val, trail):
            assert deref(val) == 10

    def test_maximize(self):
        """Maximize x + y subject to x + y <= 20, x <= 12, y <= 12."""
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 0, 12, trail)
        or_in(y, 0, 12, trail)
        state = get_cpsat_state(trail)
        cx = state.var_map[id(x)]
        cy = state.var_map[id(y)]
        or_add_constraint(cx + cy <= 20, trail)
        val = Var()
        for _ in or_maximize(Add(x, y), val, trail):
            assert deref(val) == 20

    def test_knapsack_via_cpsat(self):
        """0-1 knapsack via CP-SAT Boolean variables."""
        trail = Trail()
        values = [60, 100, 120]
        weights = [10, 20, 30]
        capacity = 50
        items = [Var() for _ in range(3)]
        for item in items:
            or_bool(item, trail)

        # Weight constraint
        state = get_cpsat_state(trail)
        item_cps = [state.var_map[id(v)] for v in items]
        weight_expr = sum(w * v for w, v in zip(weights, item_cps))
        or_add_constraint(weight_expr <= capacity, trail)

        # Maximize value
        value_expr = sum(val * v for val, v in zip(values, item_cps))
        opt = Var()
        for _ in or_maximize(value_expr, opt, trail):
            assert deref(opt) == 220  # items 1 and 2: 100 + 120


class TestCPSATHints:

    def test_hint_guides_solution(self):
        trail = Trail()
        x = Var()
        or_in(x, 1, 100, trail)
        or_hint([x], [42], trail)
        # Hint doesn't constrain, just guides
        assert or_check(trail)
```

---

## Implementation Order

1. `or_circuit()`
2. `or_table()`
3. `or_forbidden()`
4. `or_inverse()`
5. `or_automaton()`
6. `or_reservoir()`
7. `or_minimize()`
8. `or_maximize()`
9. `or_hint()`
10. `or_decision_strategy()`
11. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools.py -v -k "TestCPSATCircuit or TestCPSATTable or TestCPSATOptimization or TestCPSATHints"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] Every `trail.record(callback)` callback captures only simple values
      (ints, not Trail objects) to avoid preventing GC
- [ ] Every constraint addition is guarded by `OnlyEnforceIf` when
      `active_lits` is non-empty
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify non-reifiable constraints (`AddCircuit`, `AddAutomaton`)
      don't silently ignore the `OnlyEnforceIf` guard

### 3. Write Issues Into This File

If you discover any issues during implementation — bugs, design decisions
that needed to change, gotchas not covered in the plan, or things that
worked differently than expected — **append them to this file** under a new
section:

```markdown
## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — [short description]

**Problem:** ...
**Resolution:** ...
```

Number issues sequentially. Include enough detail that someone reading the
plan later understands what happened and why.

### 4. Ask Before Continuing If:

- A design decision in the plan seems wrong or suboptimal after seeing
  the real code
- A test requires infrastructure that doesn't exist yet (e.g., a missing
  `cons_to_list`, a Trail method that behaves differently than documented)
- You need to modify files outside the scope of this phase (e.g., changing
  the Trail C extension, modifying the compiler, editing another solver's
  code)
- The phase's approach is fundamentally incompatible with something you
  discovered in the codebase

**Do not silently work around these — surface them so the right decision
can be made.**
