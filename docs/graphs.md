# Clausal — Graphs (`graphs` module)

## Overview

The `graphs` module provides predicates for graph creation, traversal, pathfinding, cycle detection, connectivity, and minimum spanning trees. Graphs are represented as edge lists — plain Python lists matching the `pairs.py` convention.

```clausal
-import_from(graphs, [Vertices, ShortestPath, IsConnected])

Main <- (
    G_ = [["a", "b"], ["b", "c"], ["a", "c"]] and
    Vertices(G_, V_) and
    ++print(f"Vertices: {V_}") and
    ShortestPath(G_, "a", "c", P_) and
    ++print(f"Shortest path: {P_}")
)
```

Or via module import:

```clausal
-import_module(graphs)

Main <- (
    G_ = [["a", "b"], ["b", "c"]] and
    graphs.Vertices(G_, V_) and
    graphs.IsConnected(G_)
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
Vertices([["a", "b"], ["b", "c"]], V_)    % V_ = ["a", "b", "c"]
Neighbors([["a", "b"], ["b", "c"]], "b", N_)  % N_ = ["a", "c"]
Degree([["a", "b"], ["b", "c"]], "b", D_)     % D_ = 2
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
BreadthFirstNodes([["a", "b"], ["b", "c"], ["c", "d"]], "a", N_)
% N_ = ["a", "b", "c", "d"]
```

---

## Pathfinding predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `FindPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Enumerate all simple paths via backtracking |
| `ShortestPath(Edges, Start, End, Path)` | `+Edges, +Start, +End, -Path` | Shortest path (BFS for unweighted, Dijkstra for weighted) |
| `PathCost(Edges, Path, Cost)` | `+Edges, +Path, -Cost` | Sum of edge weights along a path |

```clausal
% Enumerate all paths
FindPath([["a", "b"], ["b", "c"], ["a", "c"]], "a", "c", P_)
% P_ = ["a", "b", "c"]  then  P_ = ["a", "c"]

% Shortest path in a weighted graph
ShortestPath([["a", "b", 1], ["b", "c", 2], ["a", "c", 10]], "a", "c", P_)
% P_ = ["a", "b", "c"]

% Cost of a path
PathCost([["a", "b", 3], ["b", "c", 5]], ["a", "b", "c"], C_)
% C_ = 8
```

---

## Components and ordering predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ConnectedComponents(Edges, Components)` | `+Edges, -Components` | List of components (each a vertex list) |
| `TopologicalSort(Edges, Order)` | `+Edges, -Order` | Topological ordering of a DAG; fails if cyclic |
| `HasCycle(Edges)` | `+Edges` | Succeeds if the directed graph contains a cycle |

```clausal
ConnectedComponents([["a", "b"], ["c", "d"]], C_)
% C_ = [["a", "b"], ["c", "d"]]

TopologicalSort([["a", "b"], ["b", "c"], ["a", "c"]], O_)
% O_ = ["a", "b", "c"]
```

---

## Tree predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `SpanningTree(Edges, Tree)` | `+Edges, -Tree` | A spanning tree (edge subset) via BFS |
| `MinSpanningTree(Edges, Tree, Cost)` | `+Edges, -Tree, -Cost` | Minimum spanning tree via Prim's algorithm |

```clausal
MinSpanningTree([["a", "b", 1], ["b", "c", 2], ["a", "c", 4]], T_, C_)
% T_ = [["a", "b", 1], ["b", "c", 2]]   C_ = 3
```

---

## Transformation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `ReverseEdges(Edges, Reversed)` | `+Edges, -Reversed` | Reverse all edge directions |
| `MergeGraphs(Edges1, Edges2, Merged)` | `+Edges1, +Edges2, -Merged` | Union of two edge lists |

```clausal
ReverseEdges([["a", "b"], ["c", "d"]], R_)
% R_ = [["b", "a"], ["d", "c"]]
```
