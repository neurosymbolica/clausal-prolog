# Clausal — Graphs (`graphs` module)

## Overview

The `graphs` module provides predicates for graph creation, traversal, pathfinding, cycle detection, connectivity, and minimum spanning trees. Graphs are represented as edge lists — plain Python [lists](lists.md) matching the [pairs](pairs.md) convention.

```clausal
# skip
-import_from(graphs, [Vertices, ShortestPath, IsConnected])

Main <- (
    G = [["a", "b"], ["b", "c"], ["a", "c"]],
    Vertices(G, V),
    ++print(f"Vertices: {V}"),
    ShortestPath(G, "a", "c", P),
    ++print(f"Shortest path: {P}")
)
```

Or via [module import](import.md):

```clausal
# skip
-import_module(graphs)

Main <- (
    G = [["a", "b"], ["b", "c"]],
    graphs.Vertices(G, V),
    graphs.IsConnected(G)
)
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
# skip
Vertices([["a", "b"], ["b", "c"]], V)    % V = ["a", "b", "c"]
Neighbors([["a", "b"], ["b", "c"]], "b", N)  % N = ["a", "c"]
Degree([["a", "b"], ["b", "c"]], "b", D)     % D = 2
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
# skip
BreadthFirstNodes([["a", "b"], ["b", "c"], ["c", "d"]], "a", N)
# N = ["a", "b", "c", "d"]
```

---

## Pathfinding predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `FindPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Enumerate all simple paths via [backtracking](control.md) |
| `ShortestPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Shortest path (BFS for unweighted, Dijkstra for weighted) |
| `PathCost(Edges, Path, Cost)` | `+Edges, +Path, -Cost` | Sum of edge weights along a path |

```clausal
# skip
# Enumerate all paths
FindPath([["a", "b"], ["b", "c"], ["a", "c"]], "a", "c", P)
# P = ["a", "b", "c"]  then  P = ["a", "c"]

# Shortest path in a weighted graph
ShortestPath([["a", "b", 1], ["b", "c", 2], ["a", "c", 10]], "a", "c", P)
# P = ["a", "b", "c"]

# Cost of a path
PathCost([["a", "b", 3], ["b", "c", 5]], ["a", "b", "c"], C)
# C = 8
```

---

## Components and ordering predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ConnectedComponents(Edges, Components)` | `+Edges, -Components` | List of components (each a vertex list) |
| `TopologicalSort(Edges, Order)` | `+Edges, -Order` | Topological ordering of a DAG; fails if cyclic |
| `HasCycle(Edges)` | `+Edges` | Succeeds if the directed graph contains a cycle |

```clausal
# skip
ConnectedComponents([["a", "b"], ["c", "d"]], C)
# C = [["a", "b"], ["c", "d"]]

TopologicalSort([["a", "b"], ["b", "c"], ["a", "c"]], O)
# O = ["a", "b", "c"]
```

---

## Tree predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `SpanningTree(Edges, Tree)` | `+Edges, -Tree` | A spanning tree (edge subset) via BFS |
| `MinSpanningTree(Edges, Tree, Cost)` | `+Edges, -Tree, -Cost` | Minimum spanning tree via Prim's algorithm |

```clausal
# skip
MinSpanningTree([["a", "b", 1], ["b", "c", 2], ["a", "c", 4]], T, C)
# T = [["a", "b", 1], ["b", "c", 2]]   C = 3
```

---

## Transformation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ReverseEdges(Edges, Reversed)` | `+Edges, -Reversed` | Reverse all edge directions |
| `MergeGraphs(Edges1, Edges2, Merged)` | `+Edges1, +Edges2, -Merged` | Union of two edge lists |

```clausal
# skip
ReverseEdges([["a", "b"], ["c", "d"]], R)
# R = [["b", "a"], ["d", "c"]]
```

---

*See also: [Tabling](tabling.md) — memoised search for cycle-free results on cyclic graphs · [Lists](lists.md) — list predicates used by graph algorithms.*
