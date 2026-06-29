# Phase 8: Builtins & Module API

Register all OR-Tools operations as Clausal builtins so they can be called
from `.clausal` files using the `ortools.*` module-prefixed predicate syntax.

---

## 1. Builtin Registration File

**File**: `clausal/logic/builtins/ortools_constraints.py`

```python
"""OR-Tools constraint, optimization, and algorithm builtins.

Provides:
  CP-SAT:    ortools.cpsat/1, ortools.cpsat.in/3, ortools.cpsat.solve/1, etc.
  LP/MIP:    ortools.glop/1, ortools.scip/1, ortools.cbc/1, etc.
  Graph:     ortools.graph.max_flow/4, ortools.graph.min_cost_flow/3, etc.
  Knapsack:  ortools.knapsack/5
  Routing:   ortools.routing.tsp/4, ortools.routing.vrp/6, etc.
"""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin
```

---

## 2. CP-SAT Builtins

### Constraint Block

```python
@_builtin("ortools.cpsat", 1)
def _ortools_cpsat(constraints, trail, k):
    """ortools.cpsat(Constraints) — post integer/Boolean constraints."""
    from clausal.logic.clportools import or_constraint_block
    if or_constraint_block(constraints, trail):
        yield None
```

### Domain Declaration

```python
@_builtin("ortools.cpsat.in", 3)
def _ortools_cpsat_in_3(var, lo, hi, trail, k):
    """ortools.cpsat.in(Var, Lo, Hi) — declare integer domain [Lo, Hi]."""
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, int(deref(lo)), int(deref(hi)), trail):
        yield None


@_builtin("ortools.cpsat.in", 2)
def _ortools_cpsat_in_2(var, values, trail, k):
    """ortools.cpsat.in(Var, Values) — declare sparse integer domain."""
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, deref(values), trail=trail):
        yield None


@_builtin("ortools.cpsat.bool", 1)
def _ortools_cpsat_bool(var, trail, k):
    """ortools.cpsat.bool(Var) — declare Boolean variable."""
    from clausal.logic.clportools import or_bool
    if or_bool(var, trail):
        yield None
```

### Labeling and Query

```python
@_builtin("ortools.cpsat.solve", 1)
def _ortools_cpsat_solve(vars_list, trail, k):
    """ortools.cpsat.solve(Vars) — enumerate satisfying assignments."""
    from clausal.logic.clportools import label_or
    yield from label_or(vars_list, trail)


@_builtin("ortools.cpsat.check", 0)
def _ortools_cpsat_check(trail, k):
    """ortools.cpsat.check — succeed iff CP-SAT constraints are satisfiable."""
    from clausal.logic.clportools import or_check
    if or_check(trail):
        yield None


@_builtin("ortools.cpsat.count", 2)
def _ortools_cpsat_count(vars_list, n, trail, k):
    """ortools.cpsat.count(Vars, N) — N = number of solutions."""
    from clausal.logic.clportools import or_count
    from clausal.logic.variables import unify, deref
    count = or_count(deref(vars_list), trail)
    if unify(n, count, trail):
        yield None


@_builtin("ortools.cpsat.model", 2)
def _ortools_cpsat_model(vars_list, model_out, trail, k):
    """ortools.cpsat.model(Vars, Model) — Model = list of values (first soln)."""
    from clausal.logic.clportools import label_or
    from clausal.logic.variables import deref, unify
    items = deref(vars_list)
    for _ in label_or(items, trail):
        vals = [deref(v) for v in (items if isinstance(items, list) else [items])]
        if unify(model_out, vals, trail):
            yield None
        return  # first solution only
```

### Global Constraints

```python
@_builtin("ortools.cpsat.all_different", 1)
def _ortools_cpsat_all_different(vars_list, trail, k):
    from clausal.logic.clportools import or_all_different
    if or_all_different(vars_list, trail):
        yield None


@_builtin("ortools.cpsat.element", 3)
def _ortools_cpsat_element(index, array, target, trail, k):
    from clausal.logic.clportools import or_element
    if or_element(index, array, target, trail):
        yield None


@_builtin("ortools.cpsat.table", 2)
def _ortools_cpsat_table(vars_list, tuples_list, trail, k):
    from clausal.logic.clportools import or_table
    from clausal.logic.variables import deref
    if or_table(vars_list, deref(tuples_list), trail):
        yield None


@_builtin("ortools.cpsat.circuit", 1)
def _ortools_cpsat_circuit(arcs, trail, k):
    from clausal.logic.clportools import or_circuit
    from clausal.logic.variables import deref
    if or_circuit(deref(arcs), trail):
        yield None


@_builtin("ortools.cpsat.inverse", 2)
def _ortools_cpsat_inverse(vars1, vars2, trail, k):
    from clausal.logic.clportools import or_inverse
    if or_inverse(vars1, vars2, trail):
        yield None


@_builtin("ortools.cpsat.automaton", 4)
def _ortools_cpsat_automaton(vars_list, start, accepting, transitions, trail, k):
    from clausal.logic.clportools import or_automaton
    from clausal.logic.variables import deref
    if or_automaton(vars_list, int(deref(start)), deref(accepting),
                    deref(transitions), trail):
        yield None
```

### Boolean Constraints

```python
@_builtin("ortools.cpsat.bool_or", 1)
def _ortools_cpsat_bool_or(literals, trail, k):
    from clausal.logic.clportools import or_bool_or
    if or_bool_or(literals, trail):
        yield None


@_builtin("ortools.cpsat.bool_and", 1)
def _ortools_cpsat_bool_and(literals, trail, k):
    from clausal.logic.clportools import or_bool_and
    if or_bool_and(literals, trail):
        yield None


@_builtin("ortools.cpsat.implication", 2)
def _ortools_cpsat_implication(a, b, trail, k):
    from clausal.logic.clportools import or_implication
    if or_implication(a, b, trail):
        yield None


@_builtin("ortools.cpsat.exactly_one", 1)
def _ortools_cpsat_exactly_one(literals, trail, k):
    from clausal.logic.clportools import or_exactly_one
    if or_exactly_one(literals, trail):
        yield None


@_builtin("ortools.cpsat.at_most_one", 1)
def _ortools_cpsat_at_most_one(literals, trail, k):
    from clausal.logic.clportools import or_at_most_one
    if or_at_most_one(literals, trail):
        yield None


@_builtin("ortools.cpsat.at_least_one", 1)
def _ortools_cpsat_at_least_one(literals, trail, k):
    from clausal.logic.clportools import or_at_least_one
    if or_at_least_one(literals, trail):
        yield None
```

### Scheduling

```python
@_builtin("ortools.cpsat.interval", 3)
def _ortools_cpsat_interval(start, size, end, trail, k):
    from clausal.logic.clportools import or_interval_scoped
    or_interval_scoped(start, size, end, trail)
    yield None


@_builtin("ortools.cpsat.optional_interval", 4)
def _ortools_cpsat_optional_interval(start, size, end, presence, trail, k):
    from clausal.logic.clportools import or_optional_interval
    or_optional_interval(start, size, end, presence, trail)
    yield None


@_builtin("ortools.cpsat.no_overlap", 1)
def _ortools_cpsat_no_overlap(intervals, trail, k):
    from clausal.logic.clportools import or_no_overlap, _intervals_from_clausal
    from clausal.logic.variables import deref
    ivs = _intervals_from_clausal(deref(intervals), trail)
    if or_no_overlap(ivs, trail):
        yield None


@_builtin("ortools.cpsat.no_overlap_2d", 2)
def _ortools_cpsat_no_overlap_2d(x_intervals, y_intervals, trail, k):
    from clausal.logic.clportools import or_no_overlap_2d, _intervals_from_clausal
    from clausal.logic.variables import deref
    xivs = _intervals_from_clausal(deref(x_intervals), trail)
    yivs = _intervals_from_clausal(deref(y_intervals), trail)
    if or_no_overlap_2d(xivs, yivs, trail):
        yield None


@_builtin("ortools.cpsat.cumulative", 3)
def _ortools_cpsat_cumulative(intervals, demands, capacity, trail, k):
    from clausal.logic.clportools import or_cumulative, _intervals_from_clausal
    from clausal.logic.variables import deref
    ivs = _intervals_from_clausal(deref(intervals), trail)
    if or_cumulative(ivs, deref(demands), capacity, trail):
        yield None
```

### Optimization

```python
@_builtin("ortools.cpsat.minimize", 2)
def _ortools_cpsat_minimize(expr, val, trail, k):
    from clausal.logic.clportools import or_minimize
    yield from or_minimize(expr, val, trail)


@_builtin("ortools.cpsat.maximize", 2)
def _ortools_cpsat_maximize(expr, val, trail, k):
    from clausal.logic.clportools import or_maximize
    yield from or_maximize(expr, val, trail)


@_builtin("ortools.cpsat.hint", 2)
def _ortools_cpsat_hint(vars_list, values, trail, k):
    from clausal.logic.clportools import or_hint
    if or_hint(vars_list, values, trail):
        yield None
```

---

## 3. LP/MIP Builtins

### Constraint Block Builtins (one per solver backend)

```python
def _make_lp_solver_builtin(solver_name: str, builtin_name: str):
    """Factory: create a builtin that posts constraints via the named LP/MIP solver."""

    @_builtin(builtin_name, 1)
    def _lp_constraint_block(constraints, trail, k):
        from clausal.logic.clportools_lp import lp_constraint_block
        if lp_constraint_block(constraints, solver_name, trail):
            yield None

    return _lp_constraint_block


# Register all LP/MIP solver backends
_make_lp_solver_builtin('glop', 'ortools.glop')
_make_lp_solver_builtin('scip', 'ortools.scip')
_make_lp_solver_builtin('cbc', 'ortools.cbc')
_make_lp_solver_builtin('highs', 'ortools.highs')
_make_lp_solver_builtin('gurobi', 'ortools.gurobi')
_make_lp_solver_builtin('cplex', 'ortools.cplex')
_make_lp_solver_builtin('bop', 'ortools.bop')
_make_lp_solver_builtin('pdlp', 'ortools.pdlp')
_make_lp_solver_builtin('glpk', 'ortools.glpk')
```

### Variable Declaration

```python
@_builtin("ortools.lp.var", 3)
def _ortools_lp_var(var, lo, hi, trail, k):
    """ortools.lp.var(Var, Lo, Hi) — declare continuous variable."""
    from clausal.logic.clportools_lp import lp_var
    from clausal.logic.variables import deref
    lp_var(var, float(deref(lo)), float(deref(hi)), trail)
    yield None


@_builtin("ortools.lp.int_var", 3)
def _ortools_lp_int_var(var, lo, hi, trail, k):
    """ortools.lp.int_var(Var, Lo, Hi) — declare integer variable (MIP)."""
    from clausal.logic.clportools_lp import lp_int_var
    from clausal.logic.variables import deref
    lp_int_var(var, int(deref(lo)), int(deref(hi)), trail)
    yield None


@_builtin("ortools.lp.bool_var", 1)
def _ortools_lp_bool_var(var, trail, k):
    """ortools.lp.bool_var(Var) — declare Boolean variable (MIP)."""
    from clausal.logic.clportools_lp import lp_bool_var
    lp_bool_var(var, trail)
    yield None
```

### LP Solve and Query

```python
@_builtin("ortools.lp.solve", 1)
def _ortools_lp_solve(vars_list, trail, k):
    from clausal.logic.clportools_lp import lp_solve
    yield from lp_solve(vars_list, trail)


@_builtin("ortools.lp.check", 0)
def _ortools_lp_check(trail, k):
    from clausal.logic.clportools_lp import lp_check
    if lp_check(trail):
        yield None


@_builtin("ortools.lp.minimize", 2)
def _ortools_lp_minimize(expr, val, trail, k):
    from clausal.logic.clportools_lp import lp_minimize
    yield from lp_minimize(expr, val, trail)


@_builtin("ortools.lp.maximize", 2)
def _ortools_lp_maximize(expr, val, trail, k):
    from clausal.logic.clportools_lp import lp_maximize
    yield from lp_maximize(expr, val, trail)
```

---

## 4. Graph Algorithm Builtins

```python
@_builtin("ortools.graph.max_flow", 4)
def _ortools_max_flow(arcs, source, sink, flow, trail, k):
    from clausal.logic.clportools_graph import or_max_flow_builtin
    yield from or_max_flow_builtin(arcs, source, sink, flow, trail)


@_builtin("ortools.graph.max_flow", 5)
def _ortools_max_flow_full(arcs, source, sink, flow, flow_arcs, trail, k):
    from clausal.logic.clportools_graph import or_max_flow_full
    yield from or_max_flow_full(arcs, source, sink, flow, flow_arcs, trail)


@_builtin("ortools.graph.min_cost_flow", 3)
def _ortools_min_cost_flow(arcs, supplies, cost, trail, k):
    from clausal.logic.clportools_graph import or_min_cost_flow_builtin
    yield from or_min_cost_flow_builtin(arcs, supplies, cost, trail)


@_builtin("ortools.graph.min_cost_flow", 4)
def _ortools_min_cost_flow_full(arcs, supplies, cost, flow_arcs, trail, k):
    from clausal.logic.clportools_graph import or_min_cost_flow_full
    yield from or_min_cost_flow_full(arcs, supplies, cost, flow_arcs, trail)


@_builtin("ortools.graph.assignment", 3)
def _ortools_assignment(costs, assignment_out, cost, trail, k):
    from clausal.logic.clportools_graph import or_assignment_builtin
    yield from or_assignment_builtin(costs, assignment_out, cost, trail)
```

---

## 5. Knapsack Builtin

```python
@_builtin("ortools.knapsack", 5)
def _ortools_knapsack(values, weights, capacities, selection, total, trail, k):
    from clausal.logic.clportools_graph import or_knapsack_builtin
    yield from or_knapsack_builtin(values, weights, capacities,
                                    selection, total, trail)
```

---

## 6. Routing Builtins

```python
@_builtin("ortools.routing.tsp", 4)
def _ortools_tsp(distances, depot, tour, total_dist, trail, k):
    from clausal.logic.clportools_routing import or_tsp_builtin
    yield from or_tsp_builtin(distances, depot, tour, total_dist, trail)


@_builtin("ortools.routing.vrp", 6)
def _ortools_vrp(distances, demands, capacities, depot, routes, total_dist, trail, k):
    from clausal.logic.clportools_routing import or_vrp_builtin
    yield from or_vrp_builtin(distances, demands, capacities, depot,
                               routes, total_dist, trail)


@_builtin("ortools.routing.vrptw", 5)
def _ortools_vrptw(distances, time_windows, depot, n_vehicles, routes, trail, k):
    from clausal.logic.clportools_routing import or_vrptw_builtin
    yield from or_vrptw_builtin(distances, time_windows, depot,
                                 n_vehicles, routes, trail)
```

---

## 7. Registration in constraints.py

**File**: `clausal/logic/builtins/constraints.py`

Add at the end:

```python
# ── OR-Tools builtins ───────────────────────────────────────────────────────
# Import to register ortools.* builtins
import clausal.logic.builtins.ortools_constraints  # noqa: F401
```

---

## 8. Integration Tests

### Python API Tests

```python
class TestORToolsBuiltinRegistration:

    def test_cpsat_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.cpsat", 1) is not None

    def test_cpsat_in_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.cpsat.in", 3) is not None

    def test_cpsat_solve_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.cpsat.solve", 1) is not None

    def test_glop_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.glop", 1) is not None

    def test_scip_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.scip", 1) is not None

    def test_max_flow_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.graph.max_flow", 4) is not None

    def test_tsp_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.routing.tsp", 4) is not None

    def test_knapsack_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("ortools.knapsack", 5) is not None
```

### .clausal File Integration Tests

```python
# tests/data/ortools_queens.clausal:
#
# -use_module(ortools).
#
# queens(N, Qs) :-
#     length(Qs, N),
#     maplist(ortools.cpsat.in_(1, N), Qs),
#     ortools.cpsat.all_different(Qs),
#     diag(Qs),
#     ortools.cpsat.solve(Qs).
#
# ortools.cpsat.in_(Lo, Hi, X) :- ortools.cpsat.in(X, Lo, Hi).
#
# diag([]).
# diag([Q|Qs]) :- diag_check(Q, Qs, 1), diag(Qs).
# diag_check(_, [], _).
# diag_check(Q, [Q2|Qs], D) :-
#     ortools.cpsat((Q - Q2 =\= D, Q2 - Q =\= D)),
#     D1 is D + 1,
#     diag_check(Q, Qs, D1).

class TestClausalFile:

    def test_queens_4(self):
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, Trail, deref
        trail = Trail()
        qs = Var()
        count = sum(1 for _ in call("queens", 4, qs, module=..., trail=trail))
        assert count == 2  # 4-queens has 2 solutions
```

---

## 9. Documentation Examples

### Complete N-Queens

```prolog
% queens.clausal — N-Queens via OR-Tools CP-SAT
-use_module(ortools).

queens(N, Qs) :-
    length(Qs, N),
    maplist(ortools.cpsat.in_(1, N), Qs),
    ortools.cpsat.all_different(Qs),
    diagonal_constraints(Qs),
    ortools.cpsat.solve(Qs).

ortools.cpsat.in_(Lo, Hi, X) :- ortools.cpsat.in(X, Lo, Hi).

diagonal_constraints([]).
diagonal_constraints([Q|Qs]) :-
    check_diag(Q, Qs, 1),
    diagonal_constraints(Qs).

check_diag(_, [], _).
check_diag(Q, [Q2|Qs], D) :-
    ortools.cpsat((Q - Q2 =\= D, Q2 - Q =\= D)),
    D1 is D + 1,
    check_diag(Q, Qs, D1).
```

### Diet Problem (LP)

```prolog
% diet.clausal — Linear programming via GLOP
-use_module(ortools).

diet(Bread, Milk, Cheese, Cost) :-
    ortools.lp.var(Bread, 0.0, 10.0),
    ortools.lp.var(Milk, 0.0, 10.0),
    ortools.lp.var(Cheese, 0.0, 10.0),
    ortools.glop((
        2*Bread + 3.5*Milk + Cheese >= 6,
        Bread + 2*Milk + 3*Cheese >= 10
    )),
    ortools.lp.minimize(2*Bread + 3.5*Milk + 8*Cheese, Cost),
    ortools.lp.solve([Bread, Milk, Cheese]).
```

### Shipping Network (Min Cost Flow)

```prolog
% shipping.clausal — Min cost flow
-use_module(ortools).

shipping(TotalCost) :-
    Arcs = [
        arc(0, 1, 15, 4),    % warehouse -> store A, cap 15, cost 4
        arc(0, 2, 8, 4),     % warehouse -> store B, cap 8, cost 4
        arc(1, 2, 20, 2),    % store A -> store B, cap 20, cost 2
        arc(1, 3, 4, 2),     % store A -> customer, cap 4, cost 2
        arc(2, 3, 15, 6)     % store B -> customer, cap 15, cost 6
    ],
    Supplies = [supply(0, 20), supply(3, -20)],
    ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost).
```

### TSP (Routing)

```prolog
% tsp.clausal — Traveling salesman
-use_module(ortools).

solve_tsp(Tour, Distance) :-
    Distances = [
        [0, 2451, 713, 1018, 1631, 1374],
        [2451, 0, 1745, 1524, 831, 1240],
        [713, 1745, 0, 355, 920, 803],
        [1018, 1524, 355, 0, 700, 862],
        [1631, 831, 920, 700, 0, 663],
        [1374, 1240, 803, 862, 663, 0]
    ],
    ortools.routing.tsp(Distances, 0, Tour, Distance).
```

---

## Implementation Order

1. Create `clausal/logic/builtins/ortools_constraints.py`
2. CP-SAT builtins (constraint block, domains, globals, scheduling, optimization)
3. LP/MIP builtins (constraint blocks per solver, vars, solve, optimize)
4. Graph builtins (max_flow, min_cost_flow, assignment)
5. Knapsack builtin
6. Routing builtins (tsp, vrp, vrptw)
7. Add import to `clausal/logic/builtins/constraints.py`
8. Verify all builtins registered (unit tests)
9. Create `.clausal` test files
10. Run integration tests
11. Write documentation examples

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools.py -v -k "TestORToolsBuiltinRegistration or TestClausalFile"
```

Also run any `.clausal` integration test files created in this phase.

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] Every `trail.record(callback)` callback captures only simple values
      (ints, not Trail objects) to avoid preventing GC
- [ ] Every constraint addition is guarded by `OnlyEnforceIf` when
      `active_lits` is non-empty (CP-SAT phases) / tagged with scope ID
      (LP/MIP phase)
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify all builtins are discoverable via `find_builtin`

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
