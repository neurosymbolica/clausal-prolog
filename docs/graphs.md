# Clausal Prolog — Graphs (`graphs` module)

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax), which imports the `graphs` module
    through its facade `library(graphs)` (see
    [Importing Prolog](importing_prolog.md)). The [seam](syntax.md)
    imports it as `-import_from(graphs, [...])`.

## Overview

The `graphs` module provides predicates for graph creation, traversal, pathfinding, cycle detection, connectivity, and minimum spanning trees. Graphs are represented as edge lists — plain [lists](lists.md) matching the [pairs](pairs.md) convention.

```clausal
--8<-- "tests/fixtures/docs/graphs_examples.clausal:overview_import"
```

Or import the whole module and qualify the calls (see
[module import](import.md)):

```clausal
--8<-- "tests/fixtures/docs/graphs_examples.clausal:overview_module"
```

---

## Import

```clausal
:- use_module(library(graphs), [
    vertices/2, neighbors/3, has_edge/3, degree/3,
    is_connected/1, is_isolated/2,
    breadth_first_nodes/3, depth_first_nodes/3,
    find_path/4, shortest_path/4, path_cost/3,
    connected_components/2, topological_sort/2, has_cycle/1,
    spanning_tree/2, min_spanning_tree/3,
    reverse_edges/2, merge_graphs/3
]).
```

---

## Edge representation

- **Unweighted**: `[[a, b], [b, c], ...]` — list of 2-element lists
- **Weighted**: `[[a, b, 3], [b, c, 5], ...]` — list of 3-element lists
- **Lone vertex**: a 1-element `[[v]]` entry names a vertex with no incident
  edge (makes single-vertex graphs representable and `is_isolated` enumeration
  reachable)
- **vertices** are extracted automatically from edges. A vertex is any term;
  the examples use atoms (`a`). A `"a"` vertex is a string and is kept as
  one: `vertices([["a", "b"]], V)` gives two string vertices, which are not
  the atoms `a` and `b`
- **Malformed entries** (a non-list, or the empty list) are silently skipped

A list of one-character atoms is also a string, so the top level prints
`V = [a, b, c]` as `V = "abc"`; it is the same term.

---

## Directionality and conventions

Most predicates treat the edge list as **undirected** — `neighbors`, `degree`,
`find_path`, `shortest_path`, `path_cost`, `is_connected`,
`connected_components`, `spanning_tree`, and `min_spanning_tree` all follow an
edge in both directions. The exceptions are **directed**: `has_cycle`,
`topological_sort`, and `reverse_edges` respect edge direction, and `has_edge`
matches an edge only in the stored `[U, V]` order (so `has_edge([[a, b]],
b, a)` fails even though `a` and `b` are neighbors).

Other conventions worth noting:

- **`degree` counts a self-loop once** (`[[a, a]]` → degree 1), not twice.
- **`path_cost` requires at least two vertices**; a single-vertex path fails
  rather than reporting cost 0.
- **`breadth_first_nodes` from an absent source** yields just `[Source]` — the
  source is treated as a phantom isolated vertex. `find_path` from an absent
  source fails unless `Start == End` (in which case it yields the
  single-vertex path `[Start]`).
- **`is_isolated` in check mode treats any term that is not a vertex as
  isolated** — `is_isolated([[a, b]], zzz)` succeeds, since a non-vertex
  trivially has degree 0 (accepted behavior). Enumerate mode only
  yields actual vertices.
- **`shortest_path` requires non-negative weights** (Dijkstra); a negative
  weight `W` raises `domain_error(not_less_than_zero, W)`.
- **`min_spanning_tree`/`spanning_tree` require a connected graph**; a
  disconnected graph has no spanning tree and fails.
- **`merge_graphs` concatenates** the two edge lists (duplicates are kept); it
  is not a set union.
- **`is_connected([])`** is vacuously true (no vertices to disconnect).
- Parallel edges are de-duplicated in adjacency, so `neighbors` and `find_path`
  do not report a neighbor or path more than once per distinct edge.

---

## Graph query predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `vertices(Edges, Verts)` | `+Edges, -Verts` | Extract unique vertex list from edges |
| `neighbors(Edges, Node, Nbrs)` | `+Edges, +Node, -Nbrs` | List of adjacent nodes |
| `has_edge(Edges, U, V)` | `+Edges, ?U, ?V` | Succeeds if a **directed** edge `[U, V]` exists (order matters); enumerates on backtrack |
| `degree(Edges, Node, Deg)` | `+Edges, +Node, -Deg` | Count of incident edges |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:query_examples"
```

---

## Graph property predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `is_connected(Edges)` | `+Edges` | Succeeds if graph is connected |
| `is_isolated(Edges, Node)` | `+Edges, ?Node` | Check or enumerate isolated nodes (degree 0) |

---

## Traversal predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `breadth_first_nodes(Edges, Source, Nodes)` | `+Edges, +Source, -Nodes` | BFS node ordering from source |
| `depth_first_nodes(Edges, Source, Nodes)` | `+Edges, +Source, -Nodes` | DFS preorder node ordering from source |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:traversal_example"
```

---

## Pathfinding predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `find_path(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Enumerate all simple paths via [backtracking](control.md) |
| `shortest_path(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Shortest path (BFS for unweighted, Dijkstra for weighted). **Precondition:** weighted edges must be non-negative; a negative weight raises `domain_error(not_less_than_zero, W)` (Dijkstra is unsound with negative weights). |
| `path_cost(Edges, Path, Cost)` | `+Edges, +Path, -Cost` | Sum of edge weights along a path |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:pathfinding_examples"
```

---

## Components and ordering predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `connected_components(Edges, Components)` | `+Edges, -Components` | List of components (each a vertex list) |
| `topological_sort(Edges, Order)` | `+Edges, -Order` | Topological ordering of a DAG; fails if cyclic |
| `has_cycle(Edges)` | `+Edges` | Succeeds if the directed graph contains a cycle |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:component_examples"
```

---

## Tree predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `spanning_tree(Edges, Tree)` | `+Edges, -Tree` | A spanning tree (edge subset) via BFS |
| `min_spanning_tree(Edges, Tree, Cost)` | `+Edges, -Tree, -Cost` | Minimum spanning tree via Prim's algorithm |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:tree_example"
```

---

## Transformation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `reverse_edges(Edges, Reversed)` | `+Edges, -Reversed` | reverse all edge directions |
| `merge_graphs(Edges1, Edges2, Merged)` | `+Edges1, +Edges2, -Merged` | union of two edge lists |

```text
--8<-- "tests/fixtures/docs/graphs_sigs.txt:transform_example"
```

---

*See also: [Tabling](tabling.md) — memoised search for cycle-free results on cyclic graphs · [Lists](lists.md) — list predicates used by graph algorithms.*
