"""clausal.modules.graphs — Graph predicates for Clausal.

Provides graph creation, pathfinding, cycle detection, connectivity checks,
degree analysis, MST, and more.  Import via::

    -import_from(graphs, [vertices, shortest_path, find_path])

Or via module import::

    -import_module(graphs)
    # then use graphs.vertices(...), graphs.shortest_path(...), etc.

Edge representation
-------------------
- **Unweighted**: ``[[u, v], [v, w], ...]`` — list of 2-element lists
- **Weighted**:   ``[[u, v, weight], ...]`` — list of 3-element lists
- **vertices**:   extracted automatically from edges
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, type_error)
from clausal.modules.py import ModulePredicate


# ── Dispatch adapter ─────────────────────────────────────────────────────────
#
# Graph predicates use the shared ModulePredicate base rather than a bespoke
# adapter: the old `_GraphPredicate._multi_dispatch` forwarded only
# `this_generator, _proceed, *args`, dropping `_fail`/`_catcher` — latent while
# every predicate registered a single arity (so `_get_dispatch` returned the fn
# directly), but a TypeError the moment a second arity was registered (F053).
# The base also gives catchable errors and consistent wrong-arity handling.
_GraphPredicate = ModulePredicate


# ── Argument checks (operator rulings 2026-10-02) ───────────────────────────
#
# An EDGE LIST that is unbound or not a list is a caller error, not a graph
# with no answer: it used to fail silently (every predicate gated on
# ``isinstance(edges_val, list)``), so a typo'd argument made the rule quietly
# not fire. Likewise a node argument the computation needs (a traversal
# source, a path endpoint, the node whose neighbours/degree is asked).
# "No path", "not connected", "has a cycle" etc. stay legitimate FAILURES.


def _edges_arg(value, context):
    """The deref'd edge list *value*, or raise the ISO error for it."""
    v = deref(value)
    if is_var(v):
        raise LogicException(instantiation_error(context))
    if not isinstance(v, list):
        raise LogicException(type_error("list", v, context))
    return v


def _needed_node(value, context):
    """The deref'd node *value*; instantiation_error if it is unbound."""
    v = deref(value)
    if is_var(v):
        raise LogicException(instantiation_error(context))
    return v


# ── Helpers ──────────────────────────────────────────────────────────────────


def _vertex_key(node):
    """A hashable key for *node*, falling back to identity when unhashable."""
    try:
        hash(node)
        return node
    except TypeError:
        return id(node)


def _extract_vertices(edges):
    """Extract unique vertices from an edge list, preserving first-seen order."""
    seen = set()
    result = []
    for edge in edges:
        e = deref(edge)
        if not isinstance(e, list) or len(e) < 1:
            continue
        # A 1-element entry [v] names a lone vertex with no incident edge,
        # making single-vertex graphs representable and the documented
        # is_isolated ?Node enumerate mode reachable (F046).
        nodes = (deref(e[0]), deref(e[1])) if len(e) >= 2 else (deref(e[0]),)
        for node in nodes:
            # Fall back to object identity for any unhashable vertex
            # (list, dict, set) so it doesn't crash with a raw TypeError (F052).
            h = _vertex_key(node)
            if h not in seen:
                seen.add(h)
                result.append(node)
    return result


def _adj_append(adj, key, value, seen):
    """Append *value* to ``adj[key]`` unless it is already present.

    Order-preserving dedup so parallel edges don't produce duplicate neighbor
    entries (and hence duplicate find_path solutions / neighbor lists) — F051.
    *seen* is a per-key set of ``_vertex_key`` values maintained alongside the
    ordered list so membership is O(1) instead of a linear scan per insert
    (which made adjacency builds O(E·deg) — seconds on a 40k-edge star).
    """
    keys = seen.setdefault(key, set())
    vk = _vertex_key(value)
    if vk not in keys:
        keys.add(vk)
        adj.setdefault(key, []).append(value)


def _build_adj(edges):
    """Build undirected adjacency dict from edge list."""
    adj: dict = {}
    seen: dict = {}
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 2:
            u, v = deref(e[0]), deref(e[1])
            _adj_append(adj, u, v, seen)
            _adj_append(adj, v, u, seen)
    return adj


def _build_directed_adj(edges):
    """Build directed adjacency dict from edge list."""
    adj: dict = {}
    seen: dict = {}
    for edge in edges:
        e = deref(edge)
        if isinstance(e, list) and len(e) >= 2:
            u, v = deref(e[0]), deref(e[1])
            _adj_append(adj, u, v, seen)
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
    """vertices(Edges, Verts) — extract unique vertex list from edges."""
    edges_val = _edges_arg(edges, "vertices/2")
    if isinstance(edges_val, list):
        result = _extract_vertices(edges_val)
        mark = trail.mark()
        if unify(verts, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _neighbors__3(this_generator, _proceed, _fail, _catcher, edges, node, nbrs, trail):
    """neighbors(Edges, Node, Nbrs) — list of adjacent nodes for Node."""
    edges_val = _edges_arg(edges, "neighbors/3")
    node_val = _needed_node(node, "neighbors/3")
    if isinstance(edges_val, list) and not is_var(node_val):
        adj = _build_adj(edges_val)
        result = adj.get(node_val, [])
        mark = trail.mark()
        if unify(nbrs, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _has_edge__3(this_generator, _proceed, _fail, _catcher, edges, u, v, trail):
    """has_edge(Edges, U, V) — succeeds if edge [U,V] exists."""
    edges_val = _edges_arg(edges, "has_edge/3")
    if isinstance(edges_val, list):
        seen = set()
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 2:
                eu, ev = deref(e[0]), deref(e[1])
                # Don't re-yield a parallel edge's identical (U,V) pair (F051).
                key = (_vertex_key(eu), _vertex_key(ev))
                if key in seen:
                    continue
                seen.add(key)
                mark = trail.mark()
                if unify(u, eu, trail) and unify(v, ev, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


def _degree__3(this_generator, _proceed, _fail, _catcher, edges, node, deg, trail):
    """degree(Edges, Node, Deg) — degree of Node (count of incident edges)."""
    edges_val = _edges_arg(edges, "degree/3")
    node_val = _needed_node(node, "degree/3")
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
    """is_connected(Edges) — succeeds if graph is connected."""
    edges_val = _edges_arg(edges, "is_connected/1")
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
    """is_isolated(Edges, Node) — check/enumerate isolated nodes (degree 0)."""
    edges_val = _edges_arg(edges, "is_isolated/2")
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
    """breadth_first_nodes(Edges, Source, Nodes) — BFS node ordering from Source."""
    edges_val = _edges_arg(edges, "breadth_first_nodes/3")
    source_val = _needed_node(source, "breadth_first_nodes/3")
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
    """depth_first_nodes(Edges, Source, Nodes) — DFS preorder node ordering from Source."""
    edges_val = _edges_arg(edges, "depth_first_nodes/3")
    source_val = _needed_node(source, "depth_first_nodes/3")
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
    """find_path(Edges, Start, End, Path) — enumerate simple paths via backtracking."""
    edges_val = _edges_arg(edges, "find_path/4")
    start_val = _needed_node(start, "find_path/4")
    end_val = _needed_node(end, "find_path/4")
    if isinstance(edges_val, list) and not is_var(start_val) and not is_var(end_val):
        adj = _build_adj(edges_val)

        def _dfs(start_node, target):
            # Iterative simple-path enumeration (explicit node/iterator stack)
            # so a long path does not overflow the recursion limit — the
            # trampoline would eat the RecursionError and answer "no path"
            # (F044). Yields the same paths, in the same order, as the former
            # recursion.
            if start_node == target:
                yield [start_node]
                return
            path = [start_node]
            inpath = {_vertex_key(start_node)}
            stack = [(start_node, iter(adj.get(start_node, [])))]
            while stack:
                _node, it = stack[-1]
                advanced = False
                for neighbor in it:
                    nk = _vertex_key(neighbor)
                    if nk in inpath:
                        continue
                    if neighbor == target:
                        yield path + [neighbor]
                        continue
                    path.append(neighbor)
                    inpath.add(nk)
                    stack.append((neighbor, iter(adj.get(neighbor, []))))
                    advanced = True
                    break
                if not advanced:
                    stack.pop()
                    if stack:
                        inpath.discard(_vertex_key(path.pop()))

        for p in _dfs(start_val, end_val):
            mark = trail.mark()
            if unify(path, p, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


def _shortest_path__4(this_generator, _proceed, _fail, _catcher, edges, start, end, path, trail):
    """shortest_path(Edges, Start, End, Path) — shortest path.

    Uses BFS for unweighted graphs (2-element edges),
    Dijkstra for weighted graphs (3-element edges).
    """
    edges_val = _edges_arg(edges, "shortest_path/4")
    start_val = _needed_node(start, "shortest_path/4")
    end_val = _needed_node(end, "shortest_path/4")
    if isinstance(edges_val, list) and not is_var(start_val) and not is_var(end_val):
        has_weights = any(
            isinstance(deref(e), list) and len(deref(e)) >= 3
            for e in edges_val
        )
        if has_weights:
            # Dijkstra is unsound with negative weights and would silently
            # return a non-shortest path (F045). A Bellman-Ford fallback
            # could be added later if needed.
            # Ruling 2026-10-02: a negative weight is a right-typed value
            # outside what the predicate admits -> domain_error, where it
            # used to fail and read as "no path".
            for e in edges_val:
                e = deref(e)
                if isinstance(e, list) and len(e) >= 3:
                    w = deref(e[2])
                    if isinstance(w, (int, float)) and w < 0:
                        raise LogicException(domain_error(
                            "not_less_than_zero", w, "shortest_path/4"))
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
    """path_cost(Edges, Path, Cost) — cost of a path in a weighted graph."""
    edges_val = _edges_arg(edges, "path_cost/3")
    path_val = deref(path)
    if is_var(path_val):
        raise LogicException(instantiation_error("path_cost/3"))
    if not isinstance(path_val, list):
        raise LogicException(type_error("list", path_val, "path_cost/3"))
    if isinstance(edges_val, list) and isinstance(path_val, list) and len(path_val) >= 2:
        weight_map: dict = {}
        for edge in edges_val:
            e = deref(edge)
            if isinstance(e, list) and len(e) >= 3:
                u, v, w = deref(e[0]), deref(e[1]), deref(e[2])
                # Keep the minimum weight across parallel edges so path_cost
                # agrees with shortest_path (which keeps all parallel edges and
                # takes the cheapest), rather than the last one seen (F049).
                weight_map[(u, v)] = min(weight_map.get((u, v), w), w)
                weight_map[(v, u)] = min(weight_map.get((v, u), w), w)
            elif isinstance(e, list) and len(e) == 2:
                u, v = deref(e[0]), deref(e[1])
                weight_map[(u, v)] = min(weight_map.get((u, v), 1), 1)
                weight_map[(v, u)] = min(weight_map.get((v, u), 1), 1)

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
    """connected_components(Edges, Components) — list of components (each a vertex list)."""
    edges_val = _edges_arg(edges, "connected_components/2")
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
    """topological_sort(Edges, Order) — topological ordering of DAG (Kahn's algorithm).

    Fails if graph has a cycle.
    """
    edges_val = _edges_arg(edges, "topological_sort/2")
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
    """has_cycle(Edges) — succeeds if graph contains a cycle."""
    edges_val = _edges_arg(edges, "has_cycle/1")
    if isinstance(edges_val, list):
        adj = _build_directed_adj(edges_val)
        all_nodes = list(adj.keys())
        # 0 = white (unseen), 1 = grey (on the current DFS stack), 2 = black
        # (finished). A grey neighbour is a back-edge, i.e. a cycle. Iterative
        # so deep graphs don't overflow the recursion limit (the trampoline
        # would eat the RecursionError and answer "no cycle") — F043.
        color: dict = {n: 0 for n in all_nodes}
        found = False

        for root in all_nodes:
            if found:
                break
            if color.get(root, 0) != 0:
                continue
            color[root] = 1
            stack = [(root, iter(adj.get(root, [])))]
            while stack and not found:
                node, it = stack[-1]
                advanced = False
                for neighbor in it:
                    c = color.get(neighbor, 0)
                    if c == 1:
                        found = True
                        break
                    if c == 0:
                        color[neighbor] = 1
                        stack.append((neighbor, iter(adj.get(neighbor, []))))
                        advanced = True
                        break
                if not advanced and not found:
                    color[node] = 2
                    stack.pop()

        if found:
            yield (_proceed, None)
    yield (_fail, DONE)


# ── Tree Operations ──────────────────────────────────────────────────────────


def _spanning_tree__2(this_generator, _proceed, _fail, _catcher, edges, tree, trail):
    """spanning_tree(Edges, Tree) — a spanning tree (edge subset) via BFS."""
    edges_val = _edges_arg(edges, "spanning_tree/2")
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
        if len(visited) < len(verts):
            # No spanning tree exists for a disconnected graph (F050).
            yield (_fail, DONE)
            return
        mark = trail.mark()
        if unify(tree, tree_edges, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _min_spanning_tree__3(this_generator, _proceed, _fail, _catcher, edges, tree, total_cost, trail):
    """min_spanning_tree(Edges, Tree, TotalCost) — MST via Prim's algorithm."""
    edges_val = _edges_arg(edges, "min_spanning_tree/3")
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
        # A monotone insertion counter breaks weight ties before the heap ever
        # compares the vertices themselves, which may be of mixed, unorderable
        # types (int vs str) — F052. It also makes tie-breaks deterministic
        # (insertion order) rather than id()-dependent.
        counter = itertools.count()
        heap = []
        for neighbor, w in wadj.get(verts[0], []):
            heapq.heappush(heap, (w, next(counter), verts[0], neighbor))
        while heap and len(visited) < len(verts):
            w, _, u, v = heapq.heappop(heap)
            if v in visited:
                continue
            visited.add(v)
            tree_edges.append([u, v, w])
            cost += w
            for neighbor, nw in wadj.get(v, []):
                if neighbor not in visited:
                    heapq.heappush(heap, (nw, next(counter), v, neighbor))
        if len(visited) < len(verts):
            # No spanning TREE exists for a disconnected graph (symmetric with
            # topological_sort failing on a cycle) — F050.
            yield (_fail, DONE)
            return
        mark = trail.mark()
        if unify(tree, tree_edges, trail) and unify(total_cost, cost, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Graph Transformation ─────────────────────────────────────────────────────


def _reverse_edges__2(this_generator, _proceed, _fail, _catcher, edges, reversed_edges, trail):
    """reverse_edges(Edges, Reversed) — reverse all edge directions."""
    edges_val = _edges_arg(edges, "reverse_edges/2")
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
    """merge_graphs(Edges1, Edges2, Merged) — union of two edge lists."""
    e1 = _edges_arg(edges1, "merge_graphs/3: argument 1")
    e2 = _edges_arg(edges2, "merge_graphs/3: argument 2")
    if isinstance(e1, list) and isinstance(e2, list):
        result = list(e1) + list(e2)
        mark = trail.mark()
        if unify(merged, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Build and export predicate objects ───────────────────────────────────────

vertices = _GraphPredicate("vertices")
vertices._register(2, _vertices__2)

neighbors = _GraphPredicate("neighbors")
neighbors._register(3, _neighbors__3)

has_edge = _GraphPredicate("has_edge")
has_edge._register(3, _has_edge__3)

degree = _GraphPredicate("degree")
degree._register(3, _degree__3)

is_connected = _GraphPredicate("is_connected")
is_connected._register(1, _is_connected__1)

is_isolated = _GraphPredicate("is_isolated")
is_isolated._register(2, _is_isolated__2)

breadth_first_nodes = _GraphPredicate("breadth_first_nodes")
breadth_first_nodes._register(3, _breadth_first_nodes__3)

depth_first_nodes = _GraphPredicate("depth_first_nodes")
depth_first_nodes._register(3, _depth_first_nodes__3)

find_path = _GraphPredicate("find_path")
find_path._register(4, _find_path__4)

shortest_path = _GraphPredicate("shortest_path")
shortest_path._register(4, _shortest_path__4)

path_cost = _GraphPredicate("path_cost")
path_cost._register(3, _path_cost__3)

connected_components = _GraphPredicate("connected_components")
connected_components._register(2, _connected_components__2)

topological_sort = _GraphPredicate("topological_sort")
topological_sort._register(2, _topological_sort__2)

has_cycle = _GraphPredicate("has_cycle")
has_cycle._register(1, _has_cycle__1)

spanning_tree = _GraphPredicate("spanning_tree")
spanning_tree._register(2, _spanning_tree__2)

min_spanning_tree = _GraphPredicate("min_spanning_tree")
min_spanning_tree._register(3, _min_spanning_tree__3)

reverse_edges = _GraphPredicate("reverse_edges")
reverse_edges._register(2, _reverse_edges__2)

merge_graphs = _GraphPredicate("merge_graphs")
merge_graphs._register(3, _merge_graphs__3)
