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


# ══════════════════════════════════════════════════════════════════════════
# CP-SAT builtins
# ══════════════════════════════════════════════════════════════════════════

@_builtin("ortools.cpsat", 1)
def _ortools_cpsat(constraints, trail, k):
    """ortools.cpsat(Constraints) — post integer/Boolean constraints."""
    from clausal.logic.clportools import or_constraint_block
    if or_constraint_block(constraints, trail):
        yield None


@_builtin("ortools.cpsat.in", 3)
def _ortools_cpsat_in_3(var, lo, hi, trail, k):
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, int(deref(lo)), int(deref(hi)), trail):
        yield None


@_builtin("ortools.cpsat.in_", 3)
def _ortools_cpsat_in__3(var, lo, hi, trail, k):
    """Alias for ortools.cpsat.in/3 — 'in' is a Python keyword."""
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, int(deref(lo)), int(deref(hi)), trail):
        yield None


@_builtin("ortools.cpsat.in", 2)
def _ortools_cpsat_in_2(var, values, trail, k):
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, deref(values), trail=trail):
        yield None


@_builtin("ortools.cpsat.in_", 2)
def _ortools_cpsat_in__2(var, values, trail, k):
    """Alias for ortools.cpsat.in/2 — 'in' is a Python keyword."""
    from clausal.logic.clportools import or_in
    from clausal.logic.variables import deref
    if or_in(var, deref(values), trail=trail):
        yield None


@_builtin("ortools.cpsat.bool", 1)
def _ortools_cpsat_bool(var, trail, k):
    from clausal.logic.clportools import or_bool
    if or_bool(var, trail):
        yield None


# ── Labeling and query ─────────────────────────────────────────────────────

@_builtin("ortools.cpsat.solve", 1)
def _ortools_cpsat_solve(vars_list, trail, k):
    from clausal.logic.clportools import label_or
    yield from label_or(vars_list, trail)


@_builtin("ortools.cpsat.check", 0)
def _ortools_cpsat_check(trail, k):
    from clausal.logic.clportools import or_check
    if or_check(trail):
        yield None


@_builtin("ortools.cpsat.count", 2)
def _ortools_cpsat_count(vars_list, n, trail, k):
    from clausal.logic.clportools import or_count
    from clausal.logic.variables import unify, deref
    count = or_count(deref(vars_list), trail)
    if unify(n, count, trail):
        yield None


@_builtin("ortools.cpsat.model", 2)
def _ortools_cpsat_model(vars_list, model_out, trail, k):
    from clausal.logic.clportools import label_or
    from clausal.logic.variables import deref, unify
    items = deref(vars_list)
    for _ in label_or(items, trail):
        vals = [deref(v) for v in (items if isinstance(items, list) else [items])]
        if unify(model_out, vals, trail):
            yield None
        return


# ── Global constraints ─────────────────────────────────────────────────────

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


# ── Boolean constraints ────────────────────────────────────────────────────

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


# ── Scheduling ─────────────────────────────────────────────────────────────

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


# ── Optimization ───────────────────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════
# LP/MIP builtins
# ══════════════════════════════════════════════════════════════════════════

def _make_lp_solver_builtin(solver_name: str, builtin_name: str):
    """Factory: create a builtin that posts constraints via a named LP/MIP solver."""

    @_builtin(builtin_name, 1)
    def _lp_constraint_block(constraints, trail, k):
        from clausal.logic.clportools_lp import lp_constraint_block
        if lp_constraint_block(constraints, solver_name, trail):
            yield None

    return _lp_constraint_block


_make_lp_solver_builtin('glop', 'ortools.glop')
_make_lp_solver_builtin('scip', 'ortools.scip')
_make_lp_solver_builtin('cbc', 'ortools.cbc')
_make_lp_solver_builtin('highs', 'ortools.highs')
_make_lp_solver_builtin('gurobi', 'ortools.gurobi')
_make_lp_solver_builtin('cplex', 'ortools.cplex')
_make_lp_solver_builtin('bop', 'ortools.bop')
_make_lp_solver_builtin('pdlp', 'ortools.pdlp')
_make_lp_solver_builtin('glpk', 'ortools.glpk')


@_builtin("ortools.lp.var", 3)
def _ortools_lp_var(var, lo, hi, trail, k):
    from clausal.logic.clportools_lp import lp_var
    from clausal.logic.variables import deref
    lp_var(var, float(deref(lo)), float(deref(hi)), trail)
    yield None


@_builtin("ortools.lp.int_var", 3)
def _ortools_lp_int_var(var, lo, hi, trail, k):
    from clausal.logic.clportools_lp import lp_int_var
    from clausal.logic.variables import deref
    lp_int_var(var, int(deref(lo)), int(deref(hi)), trail)
    yield None


@_builtin("ortools.lp.bool_var", 1)
def _ortools_lp_bool_var(var, trail, k):
    from clausal.logic.clportools_lp import lp_bool_var
    lp_bool_var(var, trail)
    yield None


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


# ══════════════════════════════════════════════════════════════════════════
# Graph algorithm builtins
# ══════════════════════════════════════════════════════════════════════════

@_builtin("ortools.graph.max_flow", 4)
def _ortools_max_flow(arcs, source, sink, flow, trail, k):
    from clausal.logic.clportools_graph import or_max_flow_builtin
    yield from or_max_flow_builtin(arcs, source, sink, flow, trail)


@_builtin("ortools.graph.min_cost_flow", 3)
def _ortools_min_cost_flow(arcs, supplies, cost, trail, k):
    from clausal.logic.clportools_graph import or_min_cost_flow_builtin
    yield from or_min_cost_flow_builtin(arcs, supplies, cost, trail)


@_builtin("ortools.graph.assignment", 3)
def _ortools_assignment(costs, assignment_out, cost, trail, k):
    from clausal.logic.clportools_graph import or_assignment_builtin
    yield from or_assignment_builtin(costs, assignment_out, cost, trail)


# ══════════════════════════════════════════════════════════════════════════
# Knapsack builtin
# ══════════════════════════════════════════════════════════════════════════

@_builtin("ortools.knapsack", 5)
def _ortools_knapsack(values, weights, capacities, selection, total, trail, k):
    from clausal.logic.clportools_graph import or_knapsack_builtin
    yield from or_knapsack_builtin(values, weights, capacities,
                                   selection, total, trail)


# ══════════════════════════════════════════════════════════════════════════
# Routing builtins
# ══════════════════════════════════════════════════════════════════════════

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
