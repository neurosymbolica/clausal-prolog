"""clausal.modules.graphs — Graph predicates for Clausal.

Provides graph creation, pathfinding, cycle detection, connectivity checks,
degree analysis, MST, and more.  Import via::

    -import_from(graphs, [Vertices, ShortestPath, FindPath])

Or via module import::

    -import_module(graphs)
    # then use graphs.Vertices(...), graphs.ShortestPath(...), etc.

Edge representation
-------------------
- **Unweighted**: ``[[u, v], [v, w], ...]`` — list of 2-element lists
- **Weighted**:   ``[[u, v, weight], ...]`` — list of 3-element lists
- **Vertices**:   extracted automatically from edges
"""

from __future__ import annotations

import heapq
from collections import deque
from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter (same pattern as py/re.py / py/uuid.py) ─────────────


class _GraphPredicate:
    """Adapter with ``_get_dispatch()`` for a graph predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (_fail, DONE)
            return
        yield from fn(this_generator, _proceed, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"graphs.{self._name}/{arities}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_vertices(edges):
    """Extract unique vertices from an edge list, preserving first-seen order."""
    seen = set()
    result = []
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 2:
            for node in (deref(e[0]), deref(e[1])):
                h = id(node) if isinstance(node, list) else node
                if h not in seen:
                    seen.add(h)
                    result.append(node)
    return result


def _build_adj(edges):
    """Build undirected adjacency dict from edge list."""
    adj: dict = {}
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 2:
            u, v = deref(e[0]), deref(e[1])
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
    return adj


def _build_directed_adj(edges):
    """Build directed adjacency dict from edge list."""
    adj: dict = {}
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 2:
            u, v = deref(e[0]), deref(e[1])
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, [])  # ensure v is in adj
    return adj


def _build_weighted_adj(edges):
    """Build undirected weighted adjacency dict from edge list."""
    adj: dict = {}
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 3:
            u, v, w = deref(e[0]), deref(e[1]), deref(e[2])
            adj.setdefault(u, []).append((v, w))
            adj.setdefault(v, []).append((u, w))
        elif isinstance(e, list) and len(e) == 2:
            u, v = deref(e[0]), deref(e[1])
            adj.setdefault(u, []).append((v, 1))
            adj.setdefault(v, []).append((u, 1))
    return adj


# ── Graph Query ──────────────────────────────────────────────────────────────


def _vertices__2(this_generator, _proceed, _fail, _catcher, edges, verts, trail):
    """Vertices(Edges, Verts) — extract unique vertex list from edges."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        result = _extract_vertices(edges_val)
        mark = trail.mark()
        if unify(verts, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _neighbors__3(this_generator, _proceed, _fail, _catcher, edges, node, nbrs, trail):
    """Neighbors(Edges, Node, Nbrs) — list of adjacent nodes for Node."""
    edges_val = deref(edges)
    node_val = deref(node)
    if isinstance(edges_val, list) and not is_var(node_val):
        adj = _build_adj(edges_val)
        result = adj.get(node_val, [])
        mark = trail.mark()
        if unify(nbrs, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _has_edge__3(this_generator, _proceed, _fail, _catcher, edges, u, v, trail):
    """HasEdge(Edges, U, V) — succeeds if edge [U,V] exists."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 2:
                eu, ev = deref(e[0]), deref(e[1])
                mark = trail.mark()
                if unify(u, eu, trail) and unify(v, ev, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


def _degree__3(this_generator, _proceed, _fail, _catcher, edges, node, deg, trail):
    """Degree(Edges, Node, Deg) — degree of Node (count of incident edges)."""
    edges_val = deref(edges)
    node_val = deref(node)
    if isinstance(edges_val, list) and not is_var(node_val):
        count = 0
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 2:
                if deref(e[0]) == node_val or deref(e[1]) == node_val:
                    count += 1
        mark = trail.mark()
        if unify(deg, count, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Graph Properties ─────────────────────────────────────────────────────────


def _is_connected__1(this_generator, _proceed, _fail, _catcher, edges, trail):
    """IsConnected(Edges) — succeeds if graph is connected."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        verts = _extract_vertices(edges_val)
        if len(verts) == 0:
            yield (_proceed, None)
            yield (_fail, DONE)
            return
        adj = _build_adj(edges_val)
        visited = set()
        queue = deque([verts[0]])
        visited.add(verts[0])
        while queue:
            current = queue.popleft()
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(visited) == len(verts):
            yield (_proceed, None)
    yield (_fail, DONE)


def _is_isolated__2(this_generator, _proceed, _fail, _catcher, edges, node, trail):
    """IsIsolated(Edges, Node) — check/enumerate isolated nodes (degree 0)."""
    edges_val = deref(edges)
    node_val = deref(node)
    if isinstance(edges_val, list):
        adj = _build_adj(edges_val)
        if not is_var(node_val):
            if node_val not in adj or len(adj[node_val]) == 0:
                yield (_proceed, None)
        else:
            verts = _extract_vertices(edges_val)
            for v in verts:
                if len(adj.get(v, [])) == 0:
                    mark = trail.mark()
                    if unify(node, v, trail):
                        yield (_proceed, None)
                    trail.undo(mark)
    yield (_fail, DONE)


# ── Traversal ────────────────────────────────────────────────────────────────


def _breadth_first_nodes__3(this_generator, _proceed, _fail, _catcher, edges, source, nodes, trail):
    """BreadthFirstNodes(Edges, Source, Nodes) — BFS node ordering from Source."""
    edges_val = deref(edges)
    source_val = deref(source)
    if isinstance(edges_val, list) and not is_var(source_val):
        adj = _build_adj(edges_val)
        visited_set = set()
        result = []
        queue = deque([source_val])
        visited_set.add(source_val)
        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in adj.get(current, []):
                if neighbor not in visited_set:
                    visited_set.add(neighbor)
                    queue.append(neighbor)
        mark = trail.mark()
        if unify(nodes, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _depth_first_nodes__3(this_generator, _proceed, _fail, _catcher, edges, source, nodes, trail):
    """DepthFirstNodes(Edges, Source, Nodes) — DFS preorder node ordering from Source."""
    edges_val = deref(edges)
    source_val = deref(source)
    if isinstance(edges_val, list) and not is_var(source_val):
        adj = _build_adj(edges_val)
        visited_set = set()
        result = []
        stack = [source_val]
        while stack:
            current = stack.pop()
            if current not in visited_set:
                visited_set.add(current)
                result.append(current)
                for neighbor in reversed(adj.get(current, [])):
                    if neighbor not in visited_set:
                        stack.append(neighbor)
        mark = trail.mark()
        if unify(nodes, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Pathfinding ──────────────────────────────────────────────────────────────


def _find_path__4(this_generator, _proceed, _fail, _catcher, edges, start, end, path, trail):
    """FindPath(Edges, Start, End, Path) — enumerate simple paths via backtracking."""
    edges_val = deref(edges)
    start_val = deref(start)
    end_val = deref(end)
    if isinstance(edges_val, list) and not is_var(start_val) and not is_var(end_val):
        adj = _build_adj(edges_val)

        def _dfs(current, target, visited):
            if current == target:
                yield list(visited)
                return
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.append(neighbor)
                    yield from _dfs(neighbor, target, visited)
                    visited.pop()

        for p in _dfs(start_val, end_val, [start_val]):
            mark = trail.mark()
            if unify(path, p, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


def _shortest_path__4(this_generator, _proceed, _fail, _catcher, edges, start, end, path, trail):
    """ShortestPath(Edges, Start, End, Path) — shortest path.

    Uses BFS for unweighted graphs (2-element edges),
    Dijkstra for weighted graphs (3-element edges).
    """
    edges_val = deref(edges)
    start_val = deref(start)
    end_val = deref(end)
    if isinstance(edges_val, list) and not is_var(start_val) and not is_var(end_val):
        has_weights = any(
            isinstance(deref(e), list) and len(deref(e)) >= 3
            for e in edges_val
        )
        if has_weights:
            wadj = _build_weighted_adj(edges_val)
            dist = {start_val: 0}
            prev: dict = {start_val: None}
            heap = [(0, id(start_val), start_val)]
            while heap:
                d, _, current = heapq.heappop(heap)
                if current == end_val:
                    break
                if d > dist.get(current, float('inf')):
                    continue
                for neighbor, weight in wadj.get(current, []):
                    nd = d + weight
                    if nd < dist.get(neighbor, float('inf')):
                        dist[neighbor] = nd
                        prev[neighbor] = current
                        heapq.heappush(heap, (nd, id(neighbor), neighbor))
            if end_val in prev:
                result = []
                node = end_val
                while node is not None:
                    result.append(node)
                    node = prev[node]
                result.reverse()
                mark = trail.mark()
                if unify(path, result, trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            adj = _build_adj(edges_val)
            prev_map: dict = {start_val: None}
            queue = deque([start_val])
            found = False
            while queue and not found:
                current = queue.popleft()
                if current == end_val:
                    found = True
                    break
                for neighbor in adj.get(current, []):
                    if neighbor not in prev_map:
                        prev_map[neighbor] = current
                        queue.append(neighbor)
            if found:
                result = []
                node = end_val
                while node is not None:
                    result.append(node)
                    node = prev_map[node]
                result.reverse()
                mark = trail.mark()
                if unify(path, result, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


def _path_cost__3(this_generator, _proceed, _fail, _catcher, edges, path, cost, trail):
    """PathCost(Edges, Path, Cost) — cost of a path in a weighted graph."""
    edges_val = deref(edges)
    path_val = deref(path)
    if isinstance(edges_val, list) and isinstance(path_val, list) and len(path_val) >= 2:
        weight_map: dict = {}
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 3:
                u, v, w = deref(e[0]), deref(e[1]), deref(e[2])
                weight_map[(u, v)] = w
                weight_map[(v, u)] = w
            elif isinstance(e, list) and len(e) == 2:
                u, v = deref(e[0]), deref(e[1])
                weight_map[(u, v)] = 1
                weight_map[(v, u)] = 1

        total = 0
        valid = True
        for i in range(len(path_val) - 1):
            key = (deref(path_val[i]), deref(path_val[i + 1]))
            if key in weight_map:
                total += weight_map[key]
            else:
                valid = False
                break
        if valid:
            mark = trail.mark()
            if unify(cost, total, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


# ── Components & Ordering ────────────────────────────────────────────────────


def _connected_components__2(this_generator, _proceed, _fail, _catcher, edges, components, trail):
    """ConnectedComponents(Edges, Components) — list of components (each a vertex list)."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        verts = _extract_vertices(edges_val)
        adj = _build_adj(edges_val)
        visited = set()
        result = []
        for v in verts:
            if v not in visited:
                component = []
                queue = deque([v])
                visited.add(v)
                while queue:
                    current = queue.popleft()
                    component.append(current)
                    for neighbor in adj.get(current, []):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                result.append(component)
        mark = trail.mark()
        if unify(components, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _topological_sort__2(this_generator, _proceed, _fail, _catcher, edges, order, trail):
    """TopologicalSort(Edges, Order) — topological ordering of DAG (Kahn's algorithm).

    Fails if graph has a cycle.
    """
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        adj = _build_directed_adj(edges_val)
        all_nodes = list(adj.keys())
        in_degree: dict = {n: 0 for n in all_nodes}
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 2:
                v = deref(e[1])
                in_degree[v] = in_degree.get(v, 0) + 1

        queue = deque([n for n in all_nodes if in_degree[n] == 0])
        result = []
        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) == len(all_nodes):
            mark = trail.mark()
            if unify(order, result, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


def _has_cycle__1(this_generator, _proceed, _fail, _catcher, edges, trail):
    """HasCycle(Edges) — succeeds if graph contains a cycle."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        adj = _build_directed_adj(edges_val)
        all_nodes = list(adj.keys())
        color: dict = {n: 0 for n in all_nodes}
        has_cycle = False

        def _dfs(node):
            nonlocal has_cycle
            color[node] = 1
            for neighbor in adj.get(node, []):
                if has_cycle:
                    return
                if color.get(neighbor, 0) == 1:
                    has_cycle = True
                    return
                if color.get(neighbor, 0) == 0:
                    _dfs(neighbor)
            color[node] = 2

        for n in all_nodes:
            if has_cycle:
                break
            if color[n] == 0:
                _dfs(n)

        if has_cycle:
            yield (_proceed, None)
    yield (_fail, DONE)


# ── Tree Operations ──────────────────────────────────────────────────────────


def _spanning_tree__2(this_generator, _proceed, _fail, _catcher, edges, tree, trail):
    """SpanningTree(Edges, Tree) — a spanning tree (edge subset) via BFS."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        verts = _extract_vertices(edges_val)
        if len(verts) == 0:
            mark = trail.mark()
            if unify(tree, [], trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)
            return
        adj = _build_adj(edges_val)
        visited = {verts[0]}
        tree_edges = []
        queue = deque([verts[0]])
        while queue:
            current = queue.popleft()
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    tree_edges.append([current, neighbor])
                    queue.append(neighbor)
        mark = trail.mark()
        if unify(tree, tree_edges, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _min_spanning_tree__3(this_generator, _proceed, _fail, _catcher, edges, tree, total_cost, trail):
    """MinSpanningTree(Edges, Tree, TotalCost) — MST via Prim's algorithm."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        verts = _extract_vertices(edges_val)
        if len(verts) == 0:
            mark = trail.mark()
            if unify(tree, [], trail) and unify(total_cost, 0, trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)
            return
        wadj = _build_weighted_adj(edges_val)
        visited = {verts[0]}
        tree_edges = []
        cost = 0
        heap = []
        for neighbor, w in wadj.get(verts[0], []):
            heapq.heappush(heap, (w, verts[0], neighbor))
        while heap and len(visited) < len(verts):
            w, u, v = heapq.heappop(heap)
            if v in visited:
                continue
            visited.add(v)
            tree_edges.append([u, v, w])
            cost += w
            for neighbor, nw in wadj.get(v, []):
                if neighbor not in visited:
                    heapq.heappush(heap, (nw, v, neighbor))
        mark = trail.mark()
        if unify(tree, tree_edges, trail) and unify(total_cost, cost, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Graph Transformation ─────────────────────────────────────────────────────


def _reverse_edges__2(this_generator, _proceed, _fail, _catcher, edges, reversed_edges, trail):
    """ReverseEdges(Edges, Reversed) — reverse all edge directions."""
    edges_val = deref(edges)
    if isinstance(edges_val, list):
        result = []
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 3:
                result.append([deref(e[1]), deref(e[0])] + [deref(x) for x in e[2:]])
            elif isinstance(e, list) and len(e) == 2:
                result.append([deref(e[1]), deref(e[0])])
        mark = trail.mark()
        if unify(reversed_edges, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _merge_graphs__3(this_generator, _proceed, _fail, _catcher, edges1, edges2, merged, trail):
    """MergeGraphs(Edges1, Edges2, Merged) — union of two edge lists."""
    e1 = deref(edges1)
    e2 = deref(edges2)
    if isinstance(e1, list) and isinstance(e2, list):
        result = list(e1) + list(e2)
        mark = trail.mark()
        if unify(merged, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Build and export predicate objects ───────────────────────────────────────

Vertices = _GraphPredicate("Vertices")
Vertices._register(2, _vertices__2)

Neighbors = _GraphPredicate("Neighbors")
Neighbors._register(3, _neighbors__3)

HasEdge = _GraphPredicate("HasEdge")
HasEdge._register(3, _has_edge__3)

Degree = _GraphPredicate("Degree")
Degree._register(3, _degree__3)

IsConnected = _GraphPredicate("IsConnected")
IsConnected._register(1, _is_connected__1)

IsIsolated = _GraphPredicate("IsIsolated")
IsIsolated._register(2, _is_isolated__2)

BreadthFirstNodes = _GraphPredicate("BreadthFirstNodes")
BreadthFirstNodes._register(3, _breadth_first_nodes__3)

DepthFirstNodes = _GraphPredicate("DepthFirstNodes")
DepthFirstNodes._register(3, _depth_first_nodes__3)

FindPath = _GraphPredicate("FindPath")
FindPath._register(4, _find_path__4)

ShortestPath = _GraphPredicate("ShortestPath")
ShortestPath._register(4, _shortest_path__4)

PathCost = _GraphPredicate("PathCost")
PathCost._register(3, _path_cost__3)

ConnectedComponents = _GraphPredicate("ConnectedComponents")
ConnectedComponents._register(2, _connected_components__2)

TopologicalSort = _GraphPredicate("TopologicalSort")
TopologicalSort._register(2, _topological_sort__2)

HasCycle = _GraphPredicate("HasCycle")
HasCycle._register(1, _has_cycle__1)

SpanningTree = _GraphPredicate("SpanningTree")
SpanningTree._register(2, _spanning_tree__2)

MinSpanningTree = _GraphPredicate("MinSpanningTree")
MinSpanningTree._register(3, _min_spanning_tree__3)

ReverseEdges = _GraphPredicate("ReverseEdges")
ReverseEdges._register(2, _reverse_edges__2)

MergeGraphs = _GraphPredicate("MergeGraphs")
MergeGraphs._register(3, _merge_graphs__3)
