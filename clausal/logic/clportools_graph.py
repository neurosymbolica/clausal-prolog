"""clausal.logic.clportools_graph — OR-Tools graph algorithms + knapsack.

One-shot solvers: max flow, min cost flow, linear sum assignment, and
multi-dimensional knapsack.  Each call builds a model, solves, and returns
the result.  No incremental state or backtracking.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify,
)

# ── Import guards ─────────────────────────────────────────────────────────

try:
    from ortools.graph.python import max_flow as _max_flow_mod
    from ortools.graph.python import min_cost_flow as _min_cost_flow_mod
    from ortools.graph.python import linear_sum_assignment as _assignment_mod
    _SimpleMaxFlow = _max_flow_mod.SimpleMaxFlow
    _SimpleMinCostFlow = _min_cost_flow_mod.SimpleMinCostFlow
    _SimpleLinearSumAssignment = _assignment_mod.SimpleLinearSumAssignment
    _HAS_GRAPH = True
except ImportError:  # pragma: no cover
    _HAS_GRAPH = False

try:
    from ortools.algorithms.python import knapsack_solver as _knapsack_mod
    _KnapsackSolver = _knapsack_mod.KnapsackSolver
    _HAS_KNAPSACK = True
except ImportError:  # pragma: no cover
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


# ── _as_list helper ────────────────────────────────────────────────────────

def _as_list(val: Any) -> list:
    """Coerce a Clausal term to a Python list."""
    val = deref(val)
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    if is_var(val) or isinstance(val, int):
        return [val]
    try:
        from clausal.terms import cons_to_list
        return cons_to_list(val)
    except (ValueError, TypeError, ImportError):
        raise TypeError(
            f"Expected a list, got {type(val).__name__!r}: {val!r}"
        )


# ── Max Flow ──────────────────────────────────────────────────────────────

def or_max_flow(arcs: Any, source: Any, sink: Any, trail: Trail) -> tuple:
    """Compute maximum flow in a directed network.

    arcs: list of [From, To, Capacity] or arc(From, To, Capacity) terms
    Returns (max_flow_value, flow_per_arc) or None if infeasible.
    """
    from clausal.terms import Compound
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
        idx = smf.add_arc_with_capacity(f, t, c)
        arc_indices.append((f, t, idx))

    source = int(deref(source))
    sink = int(deref(sink))

    status = smf.solve(source, sink)
    if status != smf.OPTIMAL:
        return None

    flow_value = smf.optimal_flow()
    flow_per_arc = []
    for f, t, idx in arc_indices:
        flow_per_arc.append((f, t, smf.flow(idx)))

    return flow_value, flow_per_arc


def or_max_flow_builtin(arcs: Any, source: Any, sink: Any, flow: Any,
                        trail: Trail):
    """Builtin: ortools.graph.max_flow(Arcs, Source, Sink, Flow)."""
    result = or_max_flow(arcs, source, sink, trail)
    if result is None:
        return
    flow_value, _ = result
    if unify(flow, flow_value, trail):
        yield None


# ── Min Cost Flow ─────────────────────────────────────────────────────────

def or_min_cost_flow(arcs: Any, supplies: Any, trail: Trail) -> tuple:
    """Compute minimum cost flow in a directed network.

    arcs: list of [From, To, Capacity, UnitCost]
    supplies: list of [Node, Supply] (negative = demand)
    Returns (total_cost, flow_per_arc) or None if infeasible.
    """
    from clausal.terms import Compound
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
        idx = smcf.add_arc_with_capacity_and_unit_cost(f, t, c, cost)
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
        smcf.set_node_supply(node, supply)

    status = smcf.solve()
    if status != smcf.OPTIMAL:
        return None

    total_cost = smcf.optimal_cost()
    flow_per_arc = []
    for f, t, idx in arc_indices:
        flow_per_arc.append((f, t, smcf.flow(idx), smcf.unit_cost(idx)))

    return total_cost, flow_per_arc


def or_min_cost_flow_builtin(arcs: Any, supplies: Any, cost: Any,
                             trail: Trail):
    """ortools.graph.min_cost_flow(Arcs, Supplies, TotalCost)."""
    result = or_min_cost_flow(arcs, supplies, trail)
    if result is None:
        return
    total_cost, _ = result
    if unify(cost, total_cost, trail):
        yield None


# ── Linear Sum Assignment ─────────────────────────────────────────────────

def or_assignment(costs: Any, trail: Trail) -> tuple:
    """Solve the linear sum assignment problem.

    costs: list of lists (cost matrix, agents x tasks)
    Returns (total_cost, assignment) or None if infeasible.
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
            assignment.add_arc_with_cost(i, j, cost_matrix[i][j])

    status = assignment.solve()
    if status != assignment.OPTIMAL:
        return None

    total_cost = assignment.optimal_cost()
    result = [assignment.right_mate(i) for i in range(n_agents)]

    return total_cost, result


def or_assignment_builtin(costs: Any, assignment_out: Any, cost: Any,
                          trail: Trail):
    """ortools.graph.assignment(Costs, Assignment, TotalCost)."""
    result = or_assignment(costs, trail)
    if result is None:
        return
    total_cost, assign = result
    if unify(cost, total_cost, trail) and unify(assignment_out, assign, trail):
        yield None


# ── Knapsack ──────────────────────────────────────────────────────────────

def or_knapsack(values: Any, weights: Any, capacities: Any,
                trail: Trail) -> tuple:
    """Solve a multi-dimensional 0-1 knapsack problem.

    values: list of int
    weights: list of lists of int (weight per item per dimension)
    capacities: list of int (capacity per dimension)
    Returns (total_value, selection) where selection is list of 0/1.
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
        _knapsack_mod.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
        'knapsack'
    )
    solver.init(vals, weight_matrix, caps)
    total_value = solver.solve()

    selection = [1 if solver.best_solution_contains(i) else 0
                 for i in range(n_items)]

    return total_value, selection


def or_knapsack_builtin(values: Any, weights: Any, capacities: Any,
                        selection: Any, total: Any, trail: Trail):
    """ortools.knapsack(Values, Weights, Capacities, Selection, TotalValue)."""
    result = or_knapsack(values, weights, capacities, trail)
    if result is None:
        return
    total_value, sel = result
    if unify(total, total_value, trail) and unify(selection, sel, trail):
        yield None
