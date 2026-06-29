# OR-Tools Integration for Clausal

A plan to integrate Google's OR-Tools solver suite as a constraint-solving and
optimization backend for Clausal, providing access to CP-SAT (constraint
programming), LP/MIP solvers (GLOP, SCIP, CBC, HiGHS, Gurobi, CPLEX), vehicle
routing, graph algorithms (max flow, min cost flow, assignment), and knapsack
solving through a per-solver module-prefixed predicate API that follows the
established CLP module pattern.

---

## Sub-Plans (Detailed)

| Phase | Sub-Plan | Focus |
|-------|----------|-------|
| 0 | [PHASE0_PREREQUISITES.md](PHASE0_PREREQUISITES.md) | Imports, AST nodes, Trail API, `_builtin` decorator, conventions |
| 1 | [PHASE1_CORE_INFRASTRUCTURE.md](PHASE1_CORE_INFRASTRUCTURE.md) | Shared state patterns, ORState, trail sync, OnlyEnforceIf |
| 2 | [PHASE2_CPSAT_CONSTRAINTS.md](PHASE2_CPSAT_CONSTRAINTS.md) | CP-SAT integer + Boolean, arithmetic, all_different, labeling |
| 3 | [PHASE3_CPSAT_SCHEDULING.md](PHASE3_CPSAT_SCHEDULING.md) | IntervalVar, no_overlap, cumulative, no_overlap_2d |
| 4 | [PHASE4_CPSAT_ADVANCED_OPTIMIZATION.md](PHASE4_CPSAT_ADVANCED_OPTIMIZATION.md) | Circuit, table, automaton, reservoir, minimize/maximize |
| 5 | [PHASE5_LP_MIP.md](PHASE5_LP_MIP.md) | GLOP, SCIP, CBC, HiGHS, Gurobi, CPLEX — linear/MIP solving |
| 6 | [PHASE6_GRAPH_ALGORITHMS.md](PHASE6_GRAPH_ALGORITHMS.md) | Max flow, min cost flow, linear sum assignment |
| 7 | [PHASE7_ROUTING.md](PHASE7_ROUTING.md) | Vehicle routing, TSP, dimensions, time windows |
| 8 | [PHASE8_BUILTINS_API.md](PHASE8_BUILTINS_API.md) | Builtin registration, .clausal integration, docs |

---

## Table of Contents (this document)

1. [Motivation](#1-motivation)
2. [OR-Tools Solver Inventory](#2-or-tools-solver-inventory)
3. [Architecture Overview](#3-architecture-overview)
4. [Backtracking Strategies Per Solver Family](#4-backtracking-strategies-per-solver-family)
5. [Operator Syntax](#5-operator-syntax)
6. [API Design](#6-api-design)
7. [Phase Summaries](#7-phase-summaries)
8. [Comparison with Existing Backends](#8-comparison-with-existing-backends)
9. [Appendix A: OR-Tools Feature Matrix](#appendix-a-or-tools-feature-matrix)
10. [Appendix B: Existing Prolog + CP/LP Projects](#appendix-b-existing-prolog--cplp-projects)

---

## 1. Motivation

Clausal currently has six constraint solvers:

| Module | Domain | Algorithm | Strengths | Weaknesses |
|--------|--------|-----------|-----------|------------|
| `clpfd.py` | Integers | Interval domains + propagation | Pure Prolog, no deps | No optimization, limited globals |
| `clpb.py` | Booleans | BDDs (Triska design) | Exact counting, tautology | Exponential blowup |
| `clpq.py` | Rationals | Gaussian elim + simplex | Exact arithmetic | Slow on large LP |
| `clpr.py` | Reals | Interval arithmetic | Real-valued labeling | Limited precision |
| `clpz3.py` | Mixed (SMT) | Z3 DPLL(T) | Theory combination | Heavy startup, no scheduling |
| `clpsat.py` | Booleans | PySAT CDCL | Fast pure SAT | Boolean only |

**What's missing:**

1. **Industrial-strength constraint programming** — CLP(FD) is propagation-based
   without lazy clause generation; it cannot compete with modern CP solvers on
   scheduling, routing, or combinatorial optimization problems.

2. **Fast linear/mixed-integer programming** — CLP(Q) is exact-arithmetic
   simplex, not a production LP/MIP solver.  Problems with thousands of
   variables and constraints need GLOP, SCIP, or Gurobi.

3. **Vehicle routing** — No existing solver handles TSP, VRP, VRPTW, or other
   routing problems.

4. **Network flow** — Max flow, min cost flow, and assignment are fundamental
   OR operations with no current support.

Google's OR-Tools is the dominant open-source operations research toolkit,
providing **all of the above** in a single `pip install ortools`:

- **CP-SAT**: SAT Competition / MiniZinc Challenge winner, lazy clause
  generation, scheduling-native, multi-threaded
- **GLOP**: Google's production LP solver (revised simplex)
- **SCIP / CBC / HiGHS**: Mixed-integer programming backends
- **Gurobi / CPLEX**: Commercial MIP solvers (if licensed)
- **Routing**: Specialized VRP/TSP solver with dimensions and constraints
- **Graph**: Max flow, min cost flow, linear sum assignment
- **Knapsack**: Multi-algorithm knapsack solver

Integrating OR-Tools gives Clausal users access to the full spectrum of
operations research solvers through the familiar Prolog-style relational
interface.

---

## 2. OR-Tools Solver Inventory

### Incremental Constraint Solvers

These support adding constraints over time and fit the constraint-block +
activation-literal pattern for Prolog backtracking integration:

| Solver | Module | Problem Type | Variables | Backtracking |
|--------|--------|-------------|-----------|--------------|
| **CP-SAT** | `ortools.sat.python.cp_model` | Integer/Boolean CP + optimization | IntVar, BoolVar, IntervalVar | OnlyEnforceIf |
| **GLOP** | `ortools.linear_solver.pywraplp` | Linear programming | Continuous | Model rebuild |
| **SCIP** | `ortools.linear_solver.pywraplp` | Mixed-integer programming | Continuous + Integer | Model rebuild |
| **CBC** | `ortools.linear_solver.pywraplp` | Mixed-integer programming | Continuous + Integer | Model rebuild |
| **HiGHS** | `ortools.linear_solver.pywraplp` | LP / MIP | Continuous + Integer | Model rebuild |
| **Gurobi** | `ortools.linear_solver.pywraplp` | LP / MIP (commercial) | Continuous + Integer | Model rebuild |
| **CPLEX** | `ortools.linear_solver.pywraplp` | LP / MIP (commercial) | Continuous + Integer | Model rebuild |
| **BOP** | `ortools.linear_solver.pywraplp` | Boolean optimization | Boolean | Model rebuild |
| **PDLP** | `ortools.linear_solver.pywraplp` | Large-scale LP | Continuous | Model rebuild |

### One-Shot Algorithmic Solvers

These take all inputs at once and return a solution.  They don't support
incremental constraint posting, so Clausal wraps them as predicates that take
structured input and unify the result:

| Solver | Module | Problem Type |
|--------|--------|-------------|
| **Max Flow** | `ortools.graph.python.max_flow` | Maximum flow in a network |
| **Min Cost Flow** | `ortools.graph.python.min_cost_flow` | Minimum cost flow |
| **Assignment** | `ortools.graph.python.linear_assignment` | Bipartite matching |
| **Knapsack** | `ortools.algorithms.pywrapknapsack_solver` | 0-1 knapsack |
| **Routing** | `ortools.constraint_solver.pywrapcp` | VRP / TSP |

---

## 3. Architecture Overview

OR-Tools integration uses **two architectural patterns**, depending on the
solver family:

### Pattern A: Incremental Constraint Solvers (CP-SAT, LP/MIP)

Same pattern as `clpsat.py` and `clpz3.py` — per-Trail state with activation
literal backtracking:

```
Clausal Var  <--->  CP-SAT IntVar/BoolVar  or  LP NumVar/IntVar
     |
SolverState (per Trail) {
  model/solver:     backend-specific model + solver
  var_map:          dict[int, SolverVar]     # id(Var) -> backend var
  rev_map:          dict[int, Var]           # solver var index -> Var
  active_lits:      list[...]               # activation literals
}
     |
Trail.record(callback) -> remove activation lit / mark constraint inactive
```

**CP-SAT** uses `OnlyEnforceIf(act_lit)` for reification — the native and
cleanest mechanism.

**LP/MIP** solvers (`pywraplp`) don't support reification.  Instead, we track
which constraints belong to which activation scope.  On solve, we rebuild the
solver with only the active constraints.  This is fast because LP/MIP model
building is cheap relative to solving.

### Pattern B: One-Shot Algorithmic Solvers (Routing, Graph, Knapsack)

These are wrapped as Clausal predicates that:

1. Accept structured input (lists, adjacency data, etc.)
2. Build the solver-specific model internally
3. Solve
4. Unify the result with output variables

No incremental state, no activation literals.  Each call is independent.

```
ortools.max_flow(Arcs, Source, Sink, Flow)
  → Build SimpleMaxFlow
  → Solve
  → Unify Flow with result
```

### File Organization

```
clausal/logic/
  clportools.py              # CP-SAT integration (Phases 1-4)
  clportools_lp.py           # LP/MIP integration (Phase 5)
  clportools_graph.py        # Graph algorithms (Phase 6)
  clportools_routing.py      # Routing (Phase 7)

clausal/logic/builtins/
  ortools_constraints.py     # All ortools.* builtin registrations (Phase 8)
```

---

## 4. Backtracking Strategies Per Solver Family

### CP-SAT: OnlyEnforceIf Activation Literals

CP-SAT natively supports **reification** via `OnlyEnforceIf`:

```python
model.Add(x + y <= 10).OnlyEnforceIf(act_lit)
```

The constraint is only active when `act_lit` is True.

```python
def or_push(trail: Trail) -> None:
    """Create a new activation-literal scope."""
    state = get_cpsat_state(trail)
    act = state.model.NewBoolVar(f'_act_{state._bool_counter}')
    state._bool_counter += 1
    state.active_lits.append(act)
    trail.record(lambda: state.active_lits.remove(act))
```

Before each solve, all active literals are assumed True:

```python
state.model.ClearAssumptions()
state.model.AddAssumptions(state.active_lits)
```

On backtrack, the callback removes the activation literal from the list.
Subsequent solves no longer assume it, so its guarded constraints become
dormant.  Same pattern as PySAT's activation literals.

### LP/MIP: Constraint Set Rebuild

`pywraplp.Solver` doesn't support `OnlyEnforceIf` or push/pop.  Instead:

```python
class LPConstraintEntry:
    """A constraint with its activation scope."""
    __slots__ = ('coeffs', 'bounds', 'scope_id')

class LPState:
    constraints: list[LPConstraintEntry]
    active_scopes: set[int]
```

On `lp_push(trail)`, a new scope ID is created and added to `active_scopes`.
Constraints added in this scope are tagged with that scope ID.  On backtrack,
the scope ID is removed from `active_scopes`.

Before each solve, the LP model is rebuilt from scratch using only constraints
whose `scope_id` is in `active_scopes`:

```python
def _rebuild_lp(state: LPState) -> None:
    state.solver.Clear()
    # Re-create variables
    for var_entry in state.variables:
        ...
    # Re-add only active constraints
    for ct in state.constraints:
        if ct.scope_id in state.active_scopes:
            ...
```

This is efficient because LP model building is O(constraints), while solving
is O(much more).  For problems with <100K constraints, rebuild time is
negligible.

### One-Shot Solvers: No Backtracking

Routing, graph, and knapsack solvers are deterministic functions: given input,
produce output.  They are called within Prolog goals but don't maintain
incremental state.  Backtracking simply re-invokes the solver (or fails if
there's only one solution).

---

## 5. Operator Syntax

Clausal's compiler transforms Python operators in `.clausal` files:

| Python syntax | AST node | CP-SAT / LP meaning |
|---|---|---|
| `X + Y` | `Add(left, right)` | Sum |
| `X - Y` | `Sub(left, right)` | Difference |
| `X * Y` | `Mult(left, right)` | Product (CP-SAT: integer; LP: linear) |
| `X // Y` | `FloorDiv(left, right)` | Integer division (CP-SAT only) |
| `X % Y` | `Mod(left, right)` | Modulo (CP-SAT only) |
| `X == Y` | `Eq(left, right)` | Equality |
| `X != Y` | `NotEq(left, right)` | Disequality |
| `X < Y` | `Lt(left, right)` | Less than |
| `X <= Y` | `LtE(left, right)` | Less or equal |
| `X > Y` | `Gt(left, right)` | Greater than |
| `X >= Y` | `GtE(left, right)` | Greater or equal |
| `X \| Y` | `BitOr(left, right)` | Boolean OR (CP-SAT Boolean constraints) |
| `X & Y` | `BitAnd(left, right)` | Boolean AND |
| `~X` | `Invert(operand)` | Boolean NOT |

These are the same AST nodes used by all existing CLP modules.

---

## 6. API Design

### CP-SAT Predicates (`ortools.cpsat.*`)

```python
# Domain declaration
ortools.cpsat.in(X, 1, 9)                      # IntVar [1, 9]
ortools.cpsat.in(X, [1, 3, 5, 7, 9])           # Sparse domain
ortools.cpsat.bool(X)                           # BoolVar

# Constraint block (arithmetic + comparison)
ortools.cpsat((
    X + Y > 10,
    X != Y,
    X * 2 <= Y + 3,
))

# Global constraints
ortools.cpsat.all_different(Vars)
ortools.cpsat.element(Index, Array, Target)
ortools.cpsat.table(Vars, Tuples)
ortools.cpsat.circuit(Arcs)
ortools.cpsat.inverse(Vars1, Vars2)
ortools.cpsat.automaton(Vars, Start, Accept, Transitions)

# Scheduling
ortools.cpsat.interval(Start, Size, End)
ortools.cpsat.optional_interval(Start, Size, End, Presence)
ortools.cpsat.no_overlap(Intervals)
ortools.cpsat.no_overlap_2d(XIntervals, YIntervals)
ortools.cpsat.cumulative(Intervals, Demands, Capacity)

# Optimization
ortools.cpsat.minimize(Expr, Val)
ortools.cpsat.maximize(Expr, Val)
ortools.cpsat.hint(Vars, Values)

# Labeling and query
ortools.cpsat.solve(Vars)                       # Enumerate solutions
ortools.cpsat.check                             # Succeed iff SAT
ortools.cpsat.count(Vars, N)                    # Count solutions
ortools.cpsat.model(Vars, Model)                # First solution
```

### LP/MIP Predicates (`ortools.glop.*`, `ortools.scip.*`, etc.)

```python
# Variable declaration (one per solver backend)
ortools.glop.var(X, 0.0, 100.0)                # Continuous [0, 100]
ortools.scip.var(X, 0.0, 100.0)                # Continuous
ortools.scip.int_var(X, 0, 100)                # Integer
ortools.cbc.var(X, 0.0, 100.0)                 # Continuous
ortools.cbc.int_var(X, 0, 100)                 # Integer
ortools.highs.var(X, 0.0, 100.0)               # Continuous
ortools.highs.int_var(X, 0, 100)               # Integer

# Constraint block (linear constraints — same syntax for all LP/MIP solvers)
ortools.glop((
    2*X + 3*Y =< 120,
    X + Y =< 50,
    X >= 0,
    Y >= 0,
))

ortools.scip((
    2*X + 3*Y =< 120,
    X + Y =< 50,
))

ortools.cbc((
    2*X + 3*Y =< 120,
    X + Y =< 50,
))

ortools.highs((
    2*X + 3*Y =< 120,
    X + Y =< 50,
))

# Optimization (works with any LP/MIP solver)
ortools.lp.minimize(3*X + 5*Y, Val)
ortools.lp.maximize(3*X + 5*Y, Val)

# Labeling / query
ortools.lp.solve(Vars)                          # Solve and bind values
ortools.lp.check                                # Succeed iff feasible
ortools.lp.objective(Val)                       # Val = objective value
```

### Graph Algorithm Predicates (`ortools.graph.*`)

```python
# Max flow: Arcs = [(From, To, Capacity), ...], Flow = max flow value
ortools.graph.max_flow(Arcs, Source, Sink, Flow)

# Min cost flow:
# Arcs = [(From, To, Capacity, UnitCost), ...]
# Supplies = [(Node, Supply), ...]   (negative = demand)
ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost)
ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost, FlowAssignment)

# Assignment:
# Costs = [[C_ij, ...], ...] (matrix of agent-to-task costs)
ortools.graph.assignment(Costs, Assignment, TotalCost)
```

### Knapsack Predicates (`ortools.knapsack.*`)

```python
# Values = [V1, V2, ...], Weights = [[W1, W2, ...], ...] (multi-dim),
# Capacities = [C1, ...]
ortools.knapsack(Values, Weights, Capacities, Selection, TotalValue)
```

### Routing Predicates (`ortools.routing.*`)

```python
# TSP: Distances = [[D_ij, ...], ...], Tour = solution ordering
ortools.routing.tsp(Distances, Depot, Tour, TotalDistance)

# VRP with capacity:
ortools.routing.vrp(Distances, Demands, VehicleCapacities, Depot, Routes, TotalDistance)

# VRP with time windows:
ortools.routing.vrptw(Distances, TimeWindows, Depot, Routes, TotalTime)

# General routing (advanced):
ortools.routing.solve(Config, Routes)
```

---

### Example: N-Queens (CP-SAT) in .clausal

```prolog
-use_module(ortools).

queens(N, Qs) :-
    length(Qs, N),
    maplist(ortools.cpsat.in_(1, N), Qs),
    ortools.cpsat.all_different(Qs),
    diag_constraints(Qs),
    ortools.cpsat.solve(Qs).

ortools.cpsat.in_(Lo, Hi, X) :- ortools.cpsat.in(X, Lo, Hi).

diag_constraints([]).
diag_constraints([Q|Qs]) :-
    diag_check(Q, Qs, 1),
    diag_constraints(Qs).

diag_check(_, [], _).
diag_check(Q, [Q2|Qs], D) :-
    ortools.cpsat((Q - Q2 =\= D, Q2 - Q =\= D)),
    D1 is D + 1,
    diag_check(Q, Qs, D1).
```

### Example: Diet Problem (LP via GLOP) in .clausal

```prolog
-use_module(ortools).

diet(Bread, Milk, Cheese, Cost) :-
    ortools.glop.var(Bread, 0.0, 10.0),
    ortools.glop.var(Milk, 0.0, 10.0),
    ortools.glop.var(Cheese, 0.0, 10.0),
    ortools.glop((
        2*Bread + 3.5*Milk + Cheese >= 6,    % protein
        Bread + 2*Milk + 3*Cheese >= 10,     % calcium
    )),
    ortools.lp.minimize(2*Bread + 3.5*Milk + 8*Cheese, Cost),
    ortools.lp.solve([Bread, Milk, Cheese]).
```

### Example: Max Flow (Graph) in .clausal

```prolog
-use_module(ortools).

max_flow_example(Flow) :-
    Arcs = [
        arc(0, 1, 20), arc(0, 2, 30), arc(0, 3, 10),
        arc(1, 2, 40), arc(1, 4, 30),
        arc(2, 3, 10), arc(2, 4, 20),
        arc(3, 2, 5),  arc(3, 4, 20)
    ],
    ortools.graph.max_flow(Arcs, 0, 4, Flow).
```

### Example: TSP (Routing) in .clausal

```prolog
-use_module(ortools).

tsp_example(Tour, Distance) :-
    Distances = [
        [0, 10, 15, 20],
        [10, 0, 35, 25],
        [15, 35, 0, 30],
        [20, 25, 30, 0]
    ],
    ortools.routing.tsp(Distances, 0, Tour, Distance).
```

---

## 7. Phase Summaries

### Phase 1: Core Infrastructure

**File**: `clausal/logic/clportools.py` (first ~350 lines)

- `ORVarInfo` — attribute stored on Var under key `"or"`
- `CPSATState` — per-Trail CP-SAT state (CpModel + CpSolver)
- `get_cpsat_state(trail)` — state registry with weakref cleanup
- `or_var_for(var, lo, hi, trail)` — IntVar creation + bidirectional mapping
- `or_bool_for(var, trail)` — BoolVar creation + bidirectional mapping
- `or_push(trail)` — activation literal scope via OnlyEnforceIf
- `or_add_constraint(constraint, trail)` — guarded constraint addition
- `or_check(trail)` — satisfiability test
- Shared `LPState` base for LP/MIP solvers (constraint-set rebuild pattern)
- Basic tests: variable mapping, constraint addition, backtracking, UNSAT

### Phase 2: CP-SAT Integer + Boolean Constraints

**File**: `clausal/logic/clportools.py` (next ~500 lines)

- `or_in(var, lo, hi, trail)` — integer domain declaration
- `or_in_sparse(var, values, trail)` — sparse domain
- `or_bool(var, trail)` — Boolean variable declaration
- `clausal_to_cpsat(expr, trail)` — translate Clausal arithmetic AST to
  CP-SAT `LinearExpr` / `IntVar` expressions
- `or_constraint_block(constraint_set, trail)` — walk tuple, translate,
  add with OnlyEnforceIf
- `or_all_different(vars, trail)` — all-different constraint
- `or_element(index, array, target, trail)` — element constraint
- `or_bool_or(literals, trail)` — Boolean OR clause
- `or_bool_and(literals, trail)` — Boolean AND
- `or_implication(a, b, trail)` — implication a => b
- `or_exactly_one(literals, trail)` — exactly one true
- `or_at_most_one(literals, trail)` — at most one true
- `label_or(vars, trail)` — enumerate solutions with blocking clauses
  (same pattern as `label_z3` and `label_sat`)
- `or_count(vars, trail)` — count solutions
- Tests: domains, arithmetic, all-different, Boolean, labeling

### Phase 3: CP-SAT Scheduling

**File**: `clausal/logic/clportools.py` (next ~300 lines)

- `or_interval(start, size, end, trail)` — create IntervalVar
- `or_optional_interval(start, size, end, presence, trail)` — optional interval
- `or_fixed_interval(start, size, trail)` — fixed-size interval
- `or_no_overlap(intervals, trail)` — no temporal overlap
- `or_no_overlap_2d(x_intervals, y_intervals, trail)` — 2D no-overlap
- `or_cumulative(intervals, demands, capacity, trail)` — cumulative resource
- Tests: job-shop scheduling, resource-constrained scheduling, 2D packing

### Phase 4: CP-SAT Advanced + Optimization

**File**: `clausal/logic/clportools.py` (next ~400 lines)

- `or_circuit(arcs, trail)` — Hamiltonian circuit
- `or_table(vars, tuples, trail)` — allowed assignments
- `or_forbidden(vars, tuples, trail)` — forbidden assignments
- `or_inverse(vars1, vars2, trail)` — inverse permutation
- `or_automaton(vars, start, accepting, transitions, trail)` — DFA
- `or_reservoir(times, changes, min_level, max_level, trail)` — reservoir
- `or_minimize(expr, val, trail)` — minimize objective
- `or_maximize(expr, val, trail)` — maximize objective
- `or_hint(vars, values, trail)` — solution hints
- `or_decision_strategy(vars, strategy, trail)` — search strategy
- Tests: TSP via circuit, extensional constraints, optimization, knapsack via CP

### Phase 5: LP/MIP Solver

**File**: `clausal/logic/clportools_lp.py` (~600 lines)

- `LPVarInfo` — attribute stored on Var under key `"lp"`
- `LPState` — per-Trail state (pywraplp.Solver)
- `LPConstraintEntry` — tagged constraint for scope tracking
- `get_lp_state(trail, solver_name)` — state registry (solver name selects backend)
- `lp_var(var, lo, hi, trail)` — continuous variable
- `lp_int_var(var, lo, hi, trail)` — integer variable
- `lp_bool_var(var, trail)` — Boolean variable
- `lp_push(trail)` — scope management (constraint tagging)
- `lp_add_constraint(coeffs, bounds, trail)` — add linear constraint
- `lp_constraint_block(constraint_set, solver_name, trail)` — translate and add
- `clausal_to_lp(expr, trail)` — translate arithmetic to LP coefficients
- `_rebuild_lp(state)` — rebuild solver from active constraints
- `lp_solve(vars, trail)` — solve and bind values
- `lp_minimize(expr, val, trail)` — minimize linear objective
- `lp_maximize(expr, val, trail)` — maximize linear objective
- `lp_check(trail)` — feasibility test

Supported backend names:

| Name | Backend | Type |
|------|---------|------|
| `'glop'` | GLOP | LP (continuous) |
| `'scip'` | SCIP | MIP |
| `'cbc'` | CBC | MIP |
| `'highs'` | HiGHS | LP / MIP |
| `'gurobi'` | Gurobi | LP / MIP (commercial) |
| `'cplex'` | CPLEX | LP / MIP (commercial) |
| `'bop'` | BOP | Boolean optimization |
| `'pdlp'` | PDLP | Large-scale LP |
| `'sat'` | CP-SAT (via LP interface) | MIP |

Tests: LP feasibility, MIP optimization, backtracking constraint retraction,
solver mismatch, diet problem, production planning

### Phase 6: Graph Algorithms

**File**: `clausal/logic/clportools_graph.py` (~300 lines)

- `or_max_flow(arcs, source, sink, trail)` — max flow computation
- `or_min_cost_flow(arcs, supplies, trail)` — min cost flow
- `or_assignment(costs, trail)` — linear sum assignment
- `or_knapsack(values, weights, capacities, trail)` — knapsack solving

All are **one-shot** predicates: build model from input, solve, unify result.
No incremental state.  Backtracking simply fails (one solution each).

Tests: textbook max flow, min cost flow, assignment, and knapsack examples

### Phase 7: Routing

**File**: `clausal/logic/clportools_routing.py` (~400 lines)

- `or_tsp(distances, depot, trail)` — TSP solving
- `or_vrp(distances, demands, capacities, depot, trail)` — capacitated VRP
- `or_vrptw(distances, time_windows, depot, trail)` — VRP with time windows
- `or_routing_solve(config, trail)` — general routing with full config

Routing uses OR-Tools' `RoutingIndexManager` + `RoutingModel`.  Each call
builds the model from Clausal data structures, solves, and returns the routes.

Tests: small TSP, VRP with 2 vehicles, VRPTW example

### Phase 8: Builtins & Module API

**Files**: `clausal/logic/builtins/ortools_constraints.py`, update to
`clausal/logic/builtins/constraints.py`

CP-SAT builtins:
- `ortools.cpsat/1` (constraint block)
- `ortools.cpsat.in/3`, `ortools.cpsat.in/2`, `ortools.cpsat.bool/1`
- `ortools.cpsat.solve/1`, `ortools.cpsat.check/0`, `ortools.cpsat.count/2`
- `ortools.cpsat.all_different/1`, `ortools.cpsat.element/3`, `ortools.cpsat.table/2`
- `ortools.cpsat.circuit/1`, `ortools.cpsat.inverse/2`, `ortools.cpsat.automaton/4`
- `ortools.cpsat.interval/3`, `ortools.cpsat.no_overlap/1`, `ortools.cpsat.cumulative/3`
- `ortools.cpsat.minimize/2`, `ortools.cpsat.maximize/2`, `ortools.cpsat.hint/2`

LP/MIP builtins (one constraint-block predicate per solver, shared utility predicates):
- `ortools.glop/1`, `ortools.scip/1`, `ortools.cbc/1`, `ortools.highs/1`
- `ortools.gurobi/1`, `ortools.cplex/1`, `ortools.bop/1`, `ortools.pdlp/1`
- `ortools.lp.var/3`, `ortools.lp.int_var/3`, `ortools.lp.bool_var/1`
- `ortools.lp.solve/1`, `ortools.lp.check/0`
- `ortools.lp.minimize/2`, `ortools.lp.maximize/2`, `ortools.lp.objective/1`

Graph builtins:
- `ortools.graph.max_flow/4`
- `ortools.graph.min_cost_flow/3`, `ortools.graph.min_cost_flow/4`
- `ortools.graph.assignment/3`

Knapsack builtins:
- `ortools.knapsack/5`

Routing builtins:
- `ortools.routing.tsp/4`
- `ortools.routing.vrp/6`
- `ortools.routing.vrptw/4`

Integration tests with `.clausal` files, documentation examples.

---

## 8. Comparison with Existing Backends

| Feature | CLP(FD) | CLP(Q) | Z3 | PySAT | OR-Tools |
|---------|---------|--------|-----|-------|----------|
| **Algorithm** | Arc consistency | Simplex | DPLL(T) | CDCL | LCG + Simplex + SAT |
| **Integer vars** | Yes | Via B&B | Yes (SMT Int) | No | **Yes (CP-SAT, MIP)** |
| **Continuous vars** | No | Yes (rational) | Yes (Real) | No | **Yes (LP/MIP)** |
| **Boolean vars** | Via 0/1 | No | Yes | Yes | **Yes (both CP-SAT and BOP)** |
| **Scheduling** | No | No | No | No | **Yes (native intervals)** |
| **Routing** | No | No | No | No | **Yes (native VRP/TSP)** |
| **Network flow** | No | No | No | No | **Yes (max/min cost flow)** |
| **All-different** | Yes | No | Distinct | No | **Yes (native)** |
| **Table/extensional** | No | No | No | No | **Yes (native)** |
| **Optimization** | No | Yes (LP) | Yes (Optimize) | No | **Yes (CP, LP, MIP)** |
| **Multi-threaded** | No | No | No | No | **Yes (8 threads default)** |
| **Scalability** | ~1K | ~10K | ~10K | ~1M (Bool) | **~100K+ (CP), ~1M (LP)** |
| **Commercial solvers** | No | No | No | No | **Yes (Gurobi, CPLEX)** |
| **Backtracking** | Trail domains | Trail simplex | push/pop | Act. lits | **OnlyEnforceIf / rebuild** |
| **Use case** | Small FD | Exact LP | Mixed theories | Large SAT | **Scheduling, routing, OR** |

---

## Appendix A: OR-Tools Feature Matrix

### CP-SAT Constraint Types

| Category | Constraints |
|----------|-------------|
| Linear | `Add(expr op val)` for `==`, `!=`, `<`, `<=`, `>`, `>=` |
| All-different | `AddAllDifferent(vars)` |
| Element | `AddElement(index, vars, target)` |
| Circuit | `AddCircuit(arcs)` — arcs = `[(tail, head, literal), ...]` |
| Table | `AddAllowedAssignments(vars, tuples)`, `AddForbiddenAssignments` |
| Inverse | `AddInverse(vars1, vars2)` |
| Automaton | `AddAutomaton(vars, start, finals, transitions)` |
| Reservoir | `AddReservoirConstraint(times, changes, min, max)` |
| Boolean | `AddBoolOr`, `AddBoolAnd`, `AddExactlyOne`, `AddAtMostOne`, `AddAtLeastOne`, `AddImplication` |
| Scheduling | `NewIntervalVar`, `NewOptionalIntervalVar`, `AddNoOverlap`, `AddNoOverlap2D`, `AddCumulative` |
| Optimization | `Minimize(expr)`, `Maximize(expr)` |
| Hints | `AddHint(var, value)` |
| Strategy | `AddDecisionStrategy(vars, var_strategy, domain_strategy)` |

### LP/MIP Solver Backends

| Backend | Type | License | Best For |
|---------|------|---------|----------|
| GLOP | LP | Free (OR-Tools) | Fast LP, Google production |
| PDLP | LP | Free (OR-Tools) | Very large-scale LP |
| CBC | MIP | Free (COIN-OR) | General MIP |
| SCIP | MIP | Apache 2.0 | Academic MIP, research |
| HiGHS | LP/MIP | MIT | Modern open-source LP/MIP |
| BOP | Boolean opt | Free (OR-Tools) | Boolean satisfaction/optimization |
| Gurobi | LP/MIP | Commercial | Fastest commercial MIP |
| CPLEX | LP/MIP | Commercial | Enterprise MIP |
| Xpress | LP/MIP | Commercial | Enterprise LP/MIP |

### Graph Algorithms

| Algorithm | Class | Complexity |
|-----------|-------|------------|
| Max Flow | `SimpleMaxFlow` | O(V^2 * E) |
| Min Cost Flow | `SimpleMinCostFlow` | O(V * E * log(V * C)) |
| Assignment | `SimpleLinearSumAssignment` | O(V * E * log(V * C)) |

### Knapsack Algorithms

| Algorithm | Type | Best For |
|-----------|------|----------|
| Dynamic programming | Exact | Single dimension, small capacity |
| 64-item solver | Exact | ≤64 items |
| Multi-dim B&B | Exact | Multiple dimensions |
| MIP formulation | Exact | Via LP/MIP backend |

---

## Appendix B: Existing Prolog + CP/LP Projects

### SICStus Prolog CLP(FD)

Mats Carlsson's CLP(FD) is a full finite-domain solver with global constraints
(all_different, cumulative, element, circuit).  Uses propagation with
indexicals.  No integration with external CP or LP solvers.

### ECLiPSe ic + eplex

ECLiPSe's `ic` library provides CP propagation, and `eplex` provides LP/MIP
solving via CPLEX or Xpress.  The two can be combined for hybrid CP/LP search.
This is the closest existing work to what Clausal's OR-Tools integration
provides, but requires explicit hybrid solver orchestration.

### SWI-Prolog CLP(FD) + R Integration

SWI-Prolog's CLP(FD) is Markus Triska's implementation.  The `rserve_client`
pack allows calling R from Prolog for optimization (via R's lpSolve, etc.),
but this is ad-hoc, not a first-class constraint interface.

### MiniZinc

MiniZinc is a constraint modeling language that targets multiple solvers
including OR-Tools CP-SAT, Gurobi, and others.  Models are compiled ahead of
time to FlatZinc.  Clausal's approach is fundamentally different: constraints
are posted **incrementally during Prolog search**, not compiled to a flat
representation.

### Picat + SAT/MIP

Picat provides `sat` and `mip` modules that can target SAT solvers and LP/MIP
solvers.  The tabling/planning integration is interesting, but Picat lacks
Prolog's full relational semantics.

### The Clausal approach

Clausal's OR-Tools integration is unique in combining:

1. **Full Prolog semantics** (unification, backtracking, meta-predicates)
2. **Multiple OR-Tools solver families** (CP-SAT, LP/MIP, routing, graph)
3. **Incremental constraint posting** with trail-synchronized backtracking
4. **Consistent module API** across all solvers (`ortools.cpsat.*`,
   `ortools.glop.*`, `ortools.graph.*`, etc.)

The `OnlyEnforceIf` technique for CP-SAT backtracking and the constraint-set
rebuild technique for LP/MIP are well-suited to OR-Tools' API design.  The
one-shot wrappers for routing and graph algorithms provide clean Prolog
interfaces to fundamentally non-incremental solvers.

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `clausal/logic/clportools.py` | Create | CP-SAT integration (~1500 lines) |
| `clausal/logic/clportools_lp.py` | Create | LP/MIP integration (~600 lines) |
| `clausal/logic/clportools_graph.py` | Create | Graph algorithms (~300 lines) |
| `clausal/logic/clportools_routing.py` | Create | Routing (~400 lines) |
| `clausal/logic/builtins/ortools_constraints.py` | Create | All builtin registrations (~300 lines) |
| `clausal/logic/builtins/constraints.py` | Modify | Import ortools_constraints module |
| `tests/test_clportools.py` | Create | CP-SAT tests (~400 lines) |
| `tests/test_clportools_lp.py` | Create | LP/MIP tests (~200 lines) |
| `tests/test_clportools_graph.py` | Create | Graph algorithm tests (~150 lines) |
| `tests/test_clportools_routing.py` | Create | Routing tests (~150 lines) |

---

## Verification

```bash
pip install ortools
pytest tests/test_clportools*.py -v
```

Quick smoke test (Python):

```python
# CP-SAT
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.clportools import or_in, or_all_different, label_or

trail = Trail()
x, y, z = Var(), Var(), Var()
or_in(x, 1, 3, trail)
or_in(y, 1, 3, trail)
or_in(z, 1, 3, trail)
or_all_different([x, y, z], trail)
solutions = []
for _ in label_or([x, y, z], trail):
    solutions.append((deref(x), deref(y), deref(z)))
print(len(solutions))  # 6

# LP (GLOP)
from clausal.logic.clportools_lp import lp_var, lp_constraint_block, lp_minimize, lp_solve
trail = Trail()
x, y = Var(), Var()
lp_var(x, 0.0, 100.0, trail, solver_name='glop')
lp_var(y, 0.0, 100.0, trail, solver_name='glop')
lp_constraint_block((...), 'glop', trail)

# Graph
from clausal.logic.clportools_graph import or_max_flow
trail = Trail()
flow = or_max_flow([(0,1,20), (0,2,30), (1,2,40), (2,3,20)], 0, 3, trail)
print(flow)  # 50
```
