# Clausal — Graphs (`graphs` module)

## Overview

The `graphs` module provides predicates for graph creation, traversal, pathfinding, cycle detection, connectivity, and minimum spanning trees. Graphs are represented as edge lists — plain Python [lists](lists.md) matching the [pairs](pairs.md) convention.

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:overview_import"
```

Or via [module import](import.md):

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:overview_module"
```

---

## Import

```clausal
-import_from(graphs, [
    Vertices, Neighbors, HasEdge, Degree,
    IsConnected, IsIsolated,
    BreadthFirstNodes, DepthFirstNodes,
    FindPath, ShortestPath, PathCost,
    ConnectedComponents, TopologicalSort, HasCycle,
    SpanningTree, MinSpanningTree,
    ReverseEdges, MergeGraphs
])
```

---

## Edge representation

- **Unweighted**: `[["a", "b"], ["b", "c"], ...]` — list of 2-element lists
- **Weighted**: `[["a", "b", 3], ["b", "c", 5], ...]` — list of 3-element lists
- **Vertices** are extracted automatically from edges

---

## Graph query predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Vertices(Edges, Verts)` | `+Edges, -Verts` | Extract unique vertex list from edges |
| `Neighbors(Edges, Node, Nbrs)` | `+Edges, +Node, -Nbrs` | List of adjacent nodes |
| `HasEdge(Edges, U, V)` | `+Edges, ?U, ?V` | Succeeds if edge `[U, V]` exists; enumerates on backtrack |
| `Degree(Edges, Node, Deg)` | `+Edges, +Node, -Deg` | Count of incident edges |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:query_examples"
```

---

## Graph property predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `IsConnected(Edges)` | `+Edges` | Succeeds if graph is connected |
| `IsIsolated(Edges, Node)` | `+Edges, ?Node` | Check or enumerate isolated nodes (degree 0) |

---

## Traversal predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `BreadthFirstNodes(Edges, Source, Nodes)` | `+Edges, +Source, -Nodes` | BFS node ordering from source |
| `DepthFirstNodes(Edges, Source, Nodes)` | `+Edges, +Source, -Nodes` | DFS preorder node ordering from source |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:traversal_example"
```

---

## Pathfinding predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `FindPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Enumerate all simple paths via [backtracking](control.md) |
| `ShortestPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Shortest path (BFS for unweighted, Dijkstra for weighted) |
| `PathCost(Edges, Path, Cost)` | `+Edges, +Path, -Cost` | sum_ of edge weights along a path |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:pathfinding_examples"
```

---

## Components and ordering predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ConnectedComponents(Edges, Components)` | `+Edges, -Components` | List of components (each a vertex list) |
| `TopologicalSort(Edges, Order)` | `+Edges, -Order` | Topological ordering of a DAG; fails if cyclic |
| `HasCycle(Edges)` | `+Edges` | Succeeds if the directed graph contains a cycle |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:component_examples"
```

---

## Tree predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `SpanningTree(Edges, Tree)` | `+Edges, -Tree` | A spanning tree (edge subset) via BFS |
| `MinSpanningTree(Edges, Tree, Cost)` | `+Edges, -Tree, -Cost` | Minimum spanning tree via Prim's algorithm |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:tree_example"
```

---

## Transformation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ReverseEdges(Edges, Reversed)` | `+Edges, -Reversed` | reverse all edge directions |
| `MergeGraphs(Edges1, Edges2, Merged)` | `+Edges1, +Edges2, -Merged` | union of two edge lists |

```clausal
--8<-- "tests/fixtures/docs/graphs_sigs.txt:transform_example"
```

---

*See also: [Tabling](tabling.md) — memoised search for cycle-free results on cyclic graphs · [Lists](lists.md) — list predicates used by graph algorithms.*
