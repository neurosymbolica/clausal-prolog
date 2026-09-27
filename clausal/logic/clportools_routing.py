"""clausal.logic.clportools_routing — OR-Tools routing (TSP, VRP, VRPTW).

One-shot routing solvers: each call builds a RoutingModel, solves, and
returns the result.  No incremental state or backtracking.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify,
)

# ── Import guard ──────────────────────────────────────────────────────────

try:
    from ortools.constraint_solver import routing_enums_pb2 as _routing_enums
    from ortools.constraint_solver import pywrapcp as _pywrapcp
    _HAS_ROUTING = True
except ImportError:  # pragma: no cover
    _HAS_ROUTING = False


def _require_routing() -> None:
    if not _HAS_ROUTING:
        raise ImportError(
            "OR-Tools routing requires ortools: pip install ortools"
        )


# ── Adaptive solve ────────────────────────────────────────────────────────

import time as _time

_DEFAULT_TIMEOUT_MS = 50   # initial timeout: 50ms


def _solve_with_adaptive_timeout(routing, search_params):
    """Solve with GUIDED_LOCAL_SEARCH, doubling timeout until a solution is found.

    Starts at _DEFAULT_TIMEOUT_MS, doubles on failure, up to 10x the default.
    """
    timeout_ms = _DEFAULT_TIMEOUT_MS
    max_ms = _DEFAULT_TIMEOUT_MS * 10
    while timeout_ms <= max_ms:
        search_params.time_limit.FromMilliseconds(timeout_ms)
        solution = routing.SolveWithParameters(search_params)
        if solution is not None:
            return solution
        timeout_ms *= 2
    return None


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
    raise TypeError(
        f"Expected a list, got {type(val).__name__!r}: {val!r}"
    )


# ── TSP ───────────────────────────────────────────────────────────────────

def or_tsp(distances: Any, depot: Any, trail: Trail) -> tuple:
    """Solve the Traveling Salesman Problem.

    distances: N x N distance matrix
    depot: int (starting/ending node)
    Returns (tour, total_distance) or None.
    """
    _require_routing()

    dist_matrix = []
    for row in _as_list(distances):
        row = deref(row)
        dist_matrix.append([int(deref(d)) for d in _as_list(row)])

    n = len(dist_matrix)
    depot = int(deref(depot))

    manager = _pywrapcp.RoutingIndexManager(n, 1, depot)
    routing = _pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return dist_matrix[from_node][to_node]

    transit_cb = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    search_params = _pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        _routing_enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        _routing_enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    solution = _solve_with_adaptive_timeout(routing, search_params)
    if solution is None:
        return None

    tour = []
    index = routing.Start(0)
    total_distance = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        tour.append(node)
        prev_index = index
        index = solution.Value(routing.NextVar(index))
        total_distance += routing.GetArcCostForVehicle(prev_index, index, 0)
    tour.append(manager.IndexToNode(index))

    return tour, total_distance


def or_tsp_builtin(distances: Any, depot: Any, tour: Any,
                   total_dist: Any, trail: Trail):
    """ortools.routing.tsp(Distances, Depot, Tour, TotalDistance)."""
    result = or_tsp(distances, depot, trail)
    if result is None:
        return
    tour_val, dist_val = result
    if unify(tour, tour_val, trail) and unify(total_dist, dist_val, trail):
        yield None


# ── VRP with Capacity ─────────────────────────────────────────────────────

def or_vrp(distances: Any, demands: Any, vehicle_capacities: Any,
           depot: Any, trail: Trail) -> tuple:
    """Solve a Capacitated Vehicle Routing Problem.

    distances: N x N distance matrix
    demands: list of N demands (depot demand = 0)
    vehicle_capacities: list of capacities (one per vehicle)
    depot: int
    Returns (routes, total_distance) or None.
    """
    _require_routing()

    dist_matrix = []
    for row in _as_list(distances):
        row = deref(row)
        dist_matrix.append([int(deref(d)) for d in _as_list(row)])

    demand_list = [int(deref(d)) for d in _as_list(demands)]
    cap_list = [int(deref(c)) for c in _as_list(vehicle_capacities)]
    n_vehicles = len(cap_list)
    n = len(dist_matrix)
    depot = int(deref(depot))

    manager = _pywrapcp.RoutingIndexManager(n, n_vehicles, depot)
    routing = _pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return dist_matrix[from_node][to_node]

    transit_cb = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demand_list[from_node]

    demand_cb = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb, 0, cap_list, True, 'Capacity'
    )

    search_params = _pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        _routing_enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        _routing_enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    solution = _solve_with_adaptive_timeout(routing, search_params)
    if solution is None:
        return None

    routes = []
    total_distance = 0
    for v in range(n_vehicles):
        route = []
        index = routing.Start(v)
        route_distance = 0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(node)
            prev_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(prev_index, index, v)
        route.append(manager.IndexToNode(index))
        routes.append(route)
        total_distance += route_distance

    return routes, total_distance


def or_vrp_builtin(distances: Any, demands: Any, capacities: Any,
                   depot: Any, routes: Any, total_dist: Any, trail: Trail):
    """ortools.routing.vrp(Distances, Demands, Capacities, Depot, Routes, TotalDist)."""
    result = or_vrp(distances, demands, capacities, depot, trail)
    if result is None:
        return
    routes_val, dist_val = result
    if unify(routes, routes_val, trail) and unify(total_dist, dist_val, trail):
        yield None


# ── VRP with Time Windows ─────────────────────────────────────────────────

def or_vrptw(distances: Any, time_windows: Any, depot: Any,
             n_vehicles: int, trail: Trail) -> tuple:
    """Solve a VRP with time window constraints.

    distances: N x N distance/time matrix
    time_windows: list of (earliest, latest) pairs per node
    depot: int
    n_vehicles: int
    Returns (routes, total_time) or None.
    """
    _require_routing()

    dist_matrix = []
    for row in _as_list(distances):
        row = deref(row)
        dist_matrix.append([int(deref(d)) for d in _as_list(row)])

    tw_list = []
    for tw in _as_list(time_windows):
        tw = deref(tw)
        if isinstance(tw, (list, tuple)) and len(tw) == 2:
            tw_list.append((int(deref(tw[0])), int(deref(tw[1]))))
        elif type(tw) is tuple and len(tw) == 3 and type(tw[0]) is str:
            tw_list.append((int(deref(tw[1])), int(deref(tw[2]))))
        else:
            raise TypeError(f"Expected time window (Earliest, Latest), got {tw}")

    n = len(dist_matrix)
    depot = int(deref(depot))
    n_vehicles = int(n_vehicles)

    manager = _pywrapcp.RoutingIndexManager(n, n_vehicles, depot)
    routing = _pywrapcp.RoutingModel(manager)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return dist_matrix[from_node][to_node]

    transit_cb = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    max_time = max(tw[1] for tw in tw_list) + max(max(row) for row in dist_matrix)
    routing.AddDimension(transit_cb, max_time, max_time, False, 'Time')
    time_dimension = routing.GetDimensionOrDie('Time')

    for loc_idx in range(n):
        if loc_idx == depot:
            continue
        index = manager.NodeToIndex(loc_idx)
        time_dimension.CumulVar(index).SetRange(
            tw_list[loc_idx][0], tw_list[loc_idx][1]
        )

    for v in range(n_vehicles):
        index = routing.Start(v)
        time_dimension.CumulVar(index).SetRange(
            tw_list[depot][0], tw_list[depot][1]
        )

    search_params = _pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        _routing_enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        _routing_enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    solution = _solve_with_adaptive_timeout(routing, search_params)
    if solution is None:
        return None

    routes = []
    total_time = 0
    for v in range(n_vehicles):
        route = []
        index = routing.Start(v)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            arrival = solution.Value(time_var)
            route.append((node, arrival))
            index = solution.Value(routing.NextVar(index))
        node = manager.IndexToNode(index)
        time_var = time_dimension.CumulVar(index)
        arrival = solution.Value(time_var)
        route.append((node, arrival))
        total_time += arrival
        routes.append(route)

    return routes, total_time


def or_vrptw_builtin(distances: Any, time_windows: Any, depot: Any,
                     n_vehicles: Any, routes: Any, trail: Trail):
    """ortools.routing.vrptw(Distances, TimeWindows, Depot, NVehicles, Routes)."""
    result = or_vrptw(distances, time_windows, depot,
                      int(deref(n_vehicles)), trail)
    if result is None:
        return
    routes_val, _ = result
    if unify(routes, routes_val, trail):
        yield None
