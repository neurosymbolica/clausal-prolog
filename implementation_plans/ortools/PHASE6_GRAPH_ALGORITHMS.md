# Phase 6: Graph Algorithms (Max Flow, Min Cost Flow, Assignment)

One-shot graph algorithm predicates using OR-Tools' `ortools.graph.python`
module.  These are non-incremental: each call builds a model from Clausal
data, solves it, and unifies the result.  Also includes the knapsack solver.

---

## 1. Import Guards

```python
try:
    from ortools.graph.python import max_flow as _max_flow_mod
    from ortools.graph.python import min_cost_flow as _min_cost_flow_mod
    from ortools.graph.python import linear_sum_assignment as _assignment_mod
    _SimpleMaxFlow = _max_flow_mod.SimpleMaxFlow
    _SimpleMinCostFlow = _min_cost_flow_mod.SimpleMinCostFlow
    _SimpleLinearSumAssignment = _assignment_mod.SimpleLinearSumAssignment
    _HAS_GRAPH = True
except ImportError:
    _HAS_GRAPH = False

try:
    from ortools.algorithms.python import knapsack_solver as _knapsack_mod
    _KnapsackSolver = _knapsack_mod.KnapsackSolver
    _HAS_KNAPSACK = True
except ImportError:
    _HAS_KNAPSACK = False

def _require_graph() -> None:
    if not _HAS_GRAPH:
        raise ImportError(
            "OR-Tools graph algorithms require ortools: pip install ortools"
        )

def _require_knapsack() -> None:
    if not _HAS_KNAPSACK:
        raise ImportError(
            "OR-Tools knapsack solver requires ortools: pip install ortools"
        )
```

---

## 2. Max Flow

```python
def or_max_flow(arcs: Any, source: Any, sink: Any, trail: Trail) -> tuple:
    """Compute maximum flow in a directed network.

    arcs: list of arc(From, To, Capacity) terms or [From, To, Capacity] lists
    source: int (source node)
    sink: int (sink node)

    Returns (max_flow_value, flow_per_arc) where flow_per_arc is a list
    of (from, to, flow) triples.
    """
    _require_graph()
    smf = _SimpleMaxFlow()

    arc_list = _as_list(arcs)
    arc_indices = []
    for arc in arc_list:
        arc = deref(arc)
        if isinstance(arc, (list, tuple)) and len(arc) == 3:
            f, t, c = int(deref(arc[0])), int(deref(arc[1])), int(deref(arc[2]))
        elif isinstance(arc, Compound) and arc.functor == 'arc' and len(arc.args) == 3:
            f, t, c = int(deref(arc.args[0])), int(deref(arc.args[1])), int(deref(arc.args[2]))
        else:
            raise TypeError(f"Expected arc(From, To, Capacity), got {arc}")
        idx = smf.AddArcWithCapacity(f, t, c)
        arc_indices.append((f, t, idx))

    source = int(deref(source))
    sink = int(deref(sink))

    status = smf.Solve(source, sink)
    if status != smf.OPTIMAL:
        return None  # infeasible or error

    flow_value = smf.OptimalFlow()
    flow_per_arc = []
    for f, t, idx in arc_indices:
        flow_per_arc.append((f, t, smf.Flow(idx)))

    return flow_value, flow_per_arc
```

### Clausal Builtin Wrapper

```python
def or_max_flow_builtin(arcs: Any, source: Any, sink: Any, flow: Any,
                         trail: Trail):
    """Builtin: ortools.graph.max_flow(Arcs, Source, Sink, Flow).

    Unifies Flow with the maximum flow value.
    """
    result = or_max_flow(arcs, source, sink, trail)
    if result is None:
        return  # fail
    flow_value, _ = result
    if unify(flow, flow_value, trail):
        yield None


def or_max_flow_full(arcs: Any, source: Any, sink: Any,
                      flow: Any, flow_arcs: Any, trail: Trail):
    """Builtin: ortools.graph.max_flow(Arcs, Source, Sink, Flow, FlowArcs).

    Unifies Flow with max flow value and FlowArcs with per-arc flows.
    """
    result = or_max_flow(arcs, source, sink, trail)
    if result is None:
        return
    flow_value, per_arc = result
    if unify(flow, flow_value, trail) and unify(flow_arcs, per_arc, trail):
        yield None
```

---

## 3. Min Cost Flow

```python
def or_min_cost_flow(arcs: Any, supplies: Any, trail: Trail) -> tuple:
    """Compute minimum cost flow in a directed network.

    arcs: list of arc(From, To, Capacity, UnitCost) terms
    supplies: list of supply(Node, Supply) terms
        (positive = supply, negative = demand)

    Returns (total_cost, flow_per_arc) or None if infeasible.
    """
    _require_graph()
    smcf = _SimpleMinCostFlow()

    arc_list = _as_list(arcs)
    arc_indices = []
    for arc in arc_list:
        arc = deref(arc)
        if isinstance(arc, (list, tuple)) and len(arc) == 4:
            f, t, c, cost = [int(deref(x)) for x in arc]
        elif isinstance(arc, Compound) and arc.functor == 'arc' and len(arc.args) == 4:
            f, t, c, cost = [int(deref(x)) for x in arc.args]
        else:
            raise TypeError(f"Expected arc(From, To, Capacity, UnitCost), got {arc}")
        idx = smcf.AddArcWithCapacityAndUnitCost(f, t, c, cost)
        arc_indices.append((f, t, idx))

    supply_list = _as_list(supplies)
    for s in supply_list:
        s = deref(s)
        if isinstance(s, (list, tuple)) and len(s) == 2:
            node, supply = int(deref(s[0])), int(deref(s[1]))
        elif isinstance(s, Compound) and s.functor == 'supply' and len(s.args) == 2:
            node, supply = int(deref(s.args[0])), int(deref(s.args[1]))
        else:
            raise TypeError(f"Expected supply(Node, Supply), got {s}")
        smcf.SetNodeSupply(node, supply)

    status = smcf.Solve()
    if status != smcf.OPTIMAL:
        return None

    total_cost = smcf.OptimalCost()
    flow_per_arc = []
    for f, t, idx in arc_indices:
        flow_per_arc.append((f, t, smcf.Flow(idx), smcf.UnitCost(idx)))

    return total_cost, flow_per_arc
```

### Clausal Builtin Wrappers

```python
def or_min_cost_flow_builtin(arcs: Any, supplies: Any, cost: Any,
                              trail: Trail):
    """ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost)."""
    result = or_min_cost_flow(arcs, supplies, trail)
    if result is None:
        return
    total_cost, _ = result
    if unify(cost, total_cost, trail):
        yield None


def or_min_cost_flow_full(arcs: Any, supplies: Any, cost: Any,
                           flow_arcs: Any, trail: Trail):
    """ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost, FlowArcs)."""
    result = or_min_cost_flow(arcs, supplies, trail)
    if result is None:
        return
    total_cost, per_arc = result
    if unify(cost, total_cost, trail) and unify(flow_arcs, per_arc, trail):
        yield None
```

---

## 4. Linear Sum Assignment

```python
def or_assignment(costs: Any, trail: Trail) -> tuple:
    """Solve the linear sum assignment problem.

    costs: list of lists (cost matrix, agents x tasks)
    costs[i][j] = cost of assigning agent i to task j

    Returns (total_cost, assignment) where assignment[i] = task for agent i.
    Returns None if infeasible.
    """
    _require_graph()
    assignment = _SimpleLinearSumAssignment()

    cost_matrix = []
    for row in _as_list(costs):
        row = deref(row)
        cost_row = [int(deref(c)) for c in _as_list(row)]
        cost_matrix.append(cost_row)

    n_agents = len(cost_matrix)
    if n_agents == 0:
        return 0, []

    n_tasks = len(cost_matrix[0])
    for i in range(n_agents):
        for j in range(n_tasks):
            assignment.AddArcWithCost(i, j, cost_matrix[i][j])

    status = assignment.Solve()
    if status != assignment.OPTIMAL:
        return None

    total_cost = assignment.OptimalCost()
    result = [assignment.RightMate(i) for i in range(n_agents)]

    return total_cost, result
```

### Clausal Builtin Wrapper

```python
def or_assignment_builtin(costs: Any, assignment_out: Any, cost: Any,
                           trail: Trail):
    """ortools.graph.assignment(Costs, Assignment, TotalCost)."""
    result = or_assignment(costs, trail)
    if result is None:
        return
    total_cost, assign = result
    if unify(cost, total_cost, trail) and unify(assignment_out, assign, trail):
        yield None
```

---

## 5. Knapsack Solver

```python
def or_knapsack(values: Any, weights: Any, capacities: Any,
                 trail: Trail) -> tuple:
    """Solve a multi-dimensional 0-1 knapsack problem.

    values: list of int (value per item)
    weights: list of lists of int (weight per item per dimension)
    capacities: list of int (capacity per dimension)

    Returns (total_value, selection) where selection is a list of 0/1.
    """
    _require_knapsack()

    vals = [int(deref(v)) for v in _as_list(values)]
    n_items = len(vals)

    weight_matrix = []
    for row in _as_list(weights):
        row = deref(row)
        weight_matrix.append([int(deref(w)) for w in _as_list(row)])

    caps = [int(deref(c)) for c in _as_list(capacities)]

    solver = _KnapsackSolver(
        _KnapsackSolver.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
        'knapsack'
    )
    solver.Init(vals, weight_matrix, caps)
    total_value = solver.Solve()

    selection = [1 if solver.BestSolutionContains(i) else 0
                 for i in range(n_items)]

    return total_value, selection
```

### Clausal Builtin Wrapper

```python
def or_knapsack_builtin(values: Any, weights: Any, capacities: Any,
                         selection: Any, total: Any, trail: Trail):
    """ortools.knapsack(Values, Weights, Capacities, Selection, TotalValue)."""
    result = or_knapsack(values, weights, capacities, trail)
    if result is None:
        return
    total_value, sel = result
    if unify(total, total_value, trail) and unify(selection, sel, trail):
        yield None
```

---

## 6. Tests (Phase 6)

```python
class TestMaxFlow:

    def test_simple_network(self):
        """Simple 4-node network with known max flow."""
        trail = Trail()
        arcs = [
            [0, 1, 20],
            [0, 2, 30],
            [1, 2, 10],
            [1, 3, 30],
            [2, 3, 20],
        ]
        result = or_max_flow(arcs, 0, 3, trail)
        assert result is not None
        flow_value, _ = result
        assert flow_value == 50

    def test_single_arc(self):
        trail = Trail()
        arcs = [[0, 1, 42]]
        result = or_max_flow(arcs, 0, 1, trail)
        assert result is not None
        assert result[0] == 42

    def test_bottleneck(self):
        """Flow limited by bottleneck arc."""
        trail = Trail()
        arcs = [[0, 1, 100], [1, 2, 5], [2, 3, 100]]
        result = or_max_flow(arcs, 0, 3, trail)
        assert result[0] == 5


class TestMinCostFlow:

    def test_simple_supply_demand(self):
        """2-node supply/demand with single arc."""
        trail = Trail()
        arcs = [[0, 1, 10, 5]]         # capacity 10, cost 5/unit
        supplies = [[0, 7], [1, -7]]     # supply 7, demand 7
        result = or_min_cost_flow(arcs, supplies, trail)
        assert result is not None
        assert result[0] == 35           # 7 * 5 = 35

    def test_two_paths_different_costs(self):
        """Choose cheaper path."""
        trail = Trail()
        arcs = [
            [0, 1, 10, 1],   # cheap path
            [0, 2, 10, 5],   # expensive path
            [1, 3, 10, 0],
            [2, 3, 10, 0],
        ]
        supplies = [[0, 5], [3, -5]]
        result = or_min_cost_flow(arcs, supplies, trail)
        assert result is not None
        assert result[0] == 5  # 5 units via cheap path


class TestAssignment:

    def test_3x3_assignment(self):
        """3 agents, 3 tasks with known optimal assignment."""
        trail = Trail()
        costs = [
            [90, 80, 75],
            [35, 85, 55],
            [125, 45, 110],
        ]
        result = or_assignment(costs, trail)
        assert result is not None
        total_cost, assign = result
        # Optimal: agent 0->task 2 (75), agent 1->task 0 (35), agent 2->task 1 (45)
        assert total_cost == 155
        assert assign == [2, 0, 1]

    def test_2x2_trivial(self):
        trail = Trail()
        costs = [[1, 2], [3, 4]]
        result = or_assignment(costs, trail)
        assert result is not None
        # Optimal: 0->0 (1), 1->1 (4) = 5  or  0->1 (2), 1->0 (3) = 5
        assert result[0] == 5


class TestKnapsack:

    def test_simple_01_knapsack(self):
        trail = Trail()
        values = [60, 100, 120]
        weights = [[10, 20, 30]]
        capacities = [50]
        result = or_knapsack(values, weights, capacities, trail)
        assert result is not None
        total, selection = result
        assert total == 220  # items 1 and 2
        assert selection == [0, 1, 1]

    def test_single_item_fits(self):
        trail = Trail()
        values = [42]
        weights = [[10]]
        capacities = [10]
        result = or_knapsack(values, weights, capacities, trail)
        assert result[0] == 42
        assert result[1] == [1]

    def test_multidimensional(self):
        """Knapsack with 2 weight dimensions."""
        trail = Trail()
        values = [10, 20, 30]
        weights = [[5, 10, 15], [3, 6, 9]]  # 2 dimensions
        capacities = [20, 12]
        result = or_knapsack(values, weights, capacities, trail)
        assert result is not None
        assert result[0] > 0
```

---

## Implementation Order

1. Import guards
2. `or_max_flow()` + builtin wrapper
3. `or_min_cost_flow()` + builtin wrapper
4. `or_assignment()` + builtin wrapper
5. `or_knapsack()` + builtin wrapper
6. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools_graph.py -v -k "TestMaxFlow or TestMinCostFlow or TestAssignment or TestKnapsack"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports

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
