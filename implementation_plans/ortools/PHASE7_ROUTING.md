# Phase 7: Routing (VRP / TSP)

Vehicle routing predicates using OR-Tools' `RoutingIndexManager` and
`RoutingModel`.  These are one-shot solvers: each call builds a routing model
from Clausal data, solves it, and unifies the result.

---

## 1. Import Guard

```python
try:
    from ortools.constraint_solver import routing_enums_pb2 as _routing_enums
    from ortools.constraint_solver import pywrapcp as _pywrapcp
    _HAS_ROUTING = True
except ImportError:
    _HAS_ROUTING = False

def _require_routing() -> None:
    if not _HAS_ROUTING:
        raise ImportError(
            "OR-Tools routing requires ortools: pip install ortools"
        )
```

---

## 2. TSP (Traveling Salesman Problem)

```python
def or_tsp(distances: Any, depot: Any, trail: Trail) -> tuple:
    """Solve the Traveling Salesman Problem.

    distances: N x N list of lists (distance matrix)
    depot: int (starting/ending node index)

    Returns (tour, total_distance) where tour is a list of node indices
    in visit order (starting and ending at depot).
    Returns None if no solution found.
    """
    _require_routing()

    dist_matrix = []
    for row in _as_list(distances):
        row = deref(row)
        dist_matrix.append([int(deref(d)) for d in _as_list(row)])

    n = len(dist_matrix)
    depot = int(deref(depot))

    manager = _pywrapcp.RoutingIndexManager(n, 1, depot)  # 1 vehicle
    routing = _pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return dist_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_params = _pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        _routing_enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        _routing_enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.FromSeconds(30)

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return None

    # Extract tour
    tour = []
    index = routing.Start(0)  # vehicle 0
    total_distance = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        tour.append(node)
        prev_index = index
        index = solution.Value(routing.NextVar(index))
        total_distance += routing.GetArcCostForVehicle(prev_index, index, 0)
    tour.append(manager.IndexToNode(index))  # return to depot

    return tour, total_distance
```

### Clausal Builtin Wrapper

```python
def or_tsp_builtin(distances: Any, depot: Any, tour: Any,
                    total_dist: Any, trail: Trail):
    """ortools.routing.tsp(Distances, Depot, Tour, TotalDistance)."""
    result = or_tsp(distances, depot, trail)
    if result is None:
        return
    tour_val, dist_val = result
    if unify(tour, tour_val, trail) and unify(total_dist, dist_val, trail):
        yield None
```

---

## 3. VRP with Capacity Constraints

```python
def or_vrp(distances: Any, demands: Any, vehicle_capacities: Any,
            depot: Any, trail: Trail) -> tuple:
    """Solve a Capacitated Vehicle Routing Problem (CVRP).

    distances: N x N distance matrix
    demands: list of N demands (demand[depot] should be 0)
    vehicle_capacities: list of capacities (one per vehicle)
    depot: int (depot node index)

    Returns (routes, total_distance) where routes is a list of lists,
    one route per vehicle.  Each route is a list of node indices.
    Returns None if no solution.
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

    # Distance callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return dist_matrix[from_node][to_node]

    transit_cb = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # Demand callback
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demand_list[from_node]

    demand_cb = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb,
        0,              # no slack
        cap_list,       # vehicle capacities
        True,           # start cumul to zero
        'Capacity'
    )

    search_params = _pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        _routing_enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        _routing_enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.FromSeconds(30)

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return None

    # Extract routes
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
        route.append(manager.IndexToNode(index))  # back to depot
        routes.append(route)
        total_distance += route_distance

    return routes, total_distance
```

### Clausal Builtin Wrapper

```python
def or_vrp_builtin(distances: Any, demands: Any, capacities: Any,
                    depot: Any, routes: Any, total_dist: Any, trail: Trail):
    """ortools.routing.vrp(Distances, Demands, Capacities, Depot, Routes, TotalDist)."""
    result = or_vrp(distances, demands, capacities, depot, trail)
    if result is None:
        return
    routes_val, dist_val = result
    if unify(routes, routes_val, trail) and unify(total_dist, dist_val, trail):
        yield None
```

---

## 4. VRP with Time Windows

```python
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
        elif isinstance(tw, Compound) and len(tw.args) == 2:
            tw_list.append((int(deref(tw.args[0])), int(deref(tw.args[1]))))
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

    # Time dimension
    max_time = max(tw[1] for tw in tw_list) + max(max(row) for row in dist_matrix)
    routing.AddDimension(
        transit_cb,
        max_time,       # max waiting time
        max_time,       # max total time per vehicle
        False,          # don't force start cumul to zero
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')

    # Set time windows
    for loc_idx in range(n):
        if loc_idx == depot:
            continue
        index = manager.NodeToIndex(loc_idx)
        time_dimension.CumulVar(index).SetRange(
            tw_list[loc_idx][0], tw_list[loc_idx][1]
        )

    # Depot time windows
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
    search_params.time_limit.FromSeconds(30)

    solution = routing.SolveWithParameters(search_params)
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
```

### Clausal Builtin Wrapper

```python
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
```

---

## 5. Tests (Phase 7)

```python
class TestTSP:

    def test_4_city_tsp(self):
        """4-city TSP with known optimal tour."""
        trail = Trail()
        distances = [
            [0, 10, 15, 20],
            [10, 0, 35, 25],
            [15, 35, 0, 30],
            [20, 25, 30, 0],
        ]
        result = or_tsp(distances, 0, trail)
        assert result is not None
        tour, total = result
        assert tour[0] == 0           # starts at depot
        assert tour[-1] == 0          # ends at depot
        assert len(tour) == 5         # 4 cities + return
        assert total == 80            # optimal: 0->1->3->2->0

    def test_3_city_triangle(self):
        trail = Trail()
        distances = [
            [0, 1, 2],
            [1, 0, 3],
            [2, 3, 0],
        ]
        result = or_tsp(distances, 0, trail)
        assert result is not None
        assert result[1] == 6  # 0->1->2->0: 1+3+2=6


class TestVRP:

    def test_cvrp_2_vehicles(self):
        """CVRP: 4 customers, 2 vehicles, capacity 15."""
        trail = Trail()
        distances = [
            [0, 10, 15, 20, 25],   # depot + 4 customers
            [10, 0, 35, 25, 30],
            [15, 35, 0, 30, 20],
            [20, 25, 30, 0, 15],
            [25, 30, 20, 15, 0],
        ]
        demands = [0, 5, 8, 3, 6]   # depot has 0 demand
        capacities = [15, 15]
        result = or_vrp(distances, demands, capacities, 0, trail)
        assert result is not None
        routes, total = result
        assert len(routes) == 2
        # Each route should start and end at depot 0
        for route in routes:
            assert route[0] == 0
            assert route[-1] == 0


class TestVRPTW:

    def test_vrptw_simple(self):
        """VRPTW: 3 customers with time windows."""
        trail = Trail()
        distances = [
            [0, 10, 15, 20],
            [10, 0, 25, 30],
            [15, 25, 0, 10],
            [20, 30, 10, 0],
        ]
        time_windows = [
            (0, 100),    # depot
            (5, 30),     # customer 1
            (10, 50),    # customer 2
            (20, 70),    # customer 3
        ]
        result = or_vrptw(distances, time_windows, 0, 1, trail)
        assert result is not None
        routes, _ = result
        assert len(routes) == 1
```

---

## Implementation Order

1. Import guard
2. `or_tsp()` + builtin wrapper
3. `or_vrp()` + builtin wrapper
4. `or_vrptw()` + builtin wrapper
5. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools_routing.py -v -k "TestTSP or TestVRP or TestVRPTW"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify the routing solver is available (it requires the
      `constraint_solver` module from OR-Tools)

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
