# scipy.spatial — Spatial Algorithms

Provides spatial distance functions and spatial data-structure predicates from
`scipy.spatial` as [importable](import.md) clausal predicates.

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:import"
```

or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:import_ex2"
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 1 — pure | `CrossDistance`, `PairwiseDistance`, `SquareForm`, `PointDistance` | Array in, array/scalar out |
| 3 — handle | `MakeKdTree`, `KdTreeQuery`, `KdTreeQueryBall`, `KdTreeQueryPairs` | KD-tree |
| 3 — handle | `MakeConvexHull`, `ConvexHullAttr` | Convex hull |
| 3 — handle | `MakeDelaunay`, `DelaunayFindSimplex` | Delaunay triangulation |
| 3 — handle | `MakeRotation`, `RotationApply`, `RotationAs`, `RotationCompose`, `RotationInverse` | 3-D rotation |
| lifecycle | `Free` | Release any handle |

---

## Tier 1 — Distance Functions

### CrossDistance

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:crossdistance"
```

Compute the distance between each pair of rows from `XA` and `XB`.
Wraps `scipy.spatial.distance.cdist`.

- `XA`, `XB`: arrays of shape `(m, d)` and `(n, d)`
- `METRIC`: distance metric string (default `'minkowski'`)
- `KWARGS`: Python dict of extra metric-specific keyword arguments, or `None`
- `RESULT`: `(m × n)` distance matrix

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:crossdistance_ex2"
```

### PairwiseDistance

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:pairwisedistance"
```

Compute pairwise distances between all rows within a single array `X`.
Wraps `scipy.spatial.distance.pdist`.

- `X`: array of shape `(n, d)`
- `RESULT`: condensed distance vector of length `n*(n-1)/2`

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:pairwisedistance_ex2"
```

### SquareForm

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:squareform"
```

Convert between a condensed distance vector and a square distance matrix.
Wraps `scipy.spatial.distance.squareform`.

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:squareform_ex2"
```

### PointDistance

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:pointdistance"
```

Compute the scalar distance between two individual points using the named
metric.

- `METRIC`: e.g. `'euclidean'`, `'cityblock'`, `'cosine'`, `'mahalanobis'`
- `X`, `Y`: 1-D arrays or lists
- `RESULT`: float scalar

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:pointdistance_ex2"
```

---

## Tier 3 — KD-Tree

### MakeKdTree

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makekdtree"
```

Build a KD-tree for fast nearest-neighbour queries.
Wraps `scipy.spatial.KDTree`.

- `DATA`: `(n, d)` array of points
- `LEAFSIZE`: leaf-size threshold (default 10)
- `RESULT`: integer handle

### KdTreeQuery

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequery"
```

Query the KD-tree for the `K` nearest neighbours of each point in `X`.

- `X`: query point(s) — `(d,)` for a single point, `(m, d)` for multiple
- `K`: number of neighbours (default 1)
- `RESULT`: dict with keys `'distances'` and `'indices'`

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequery_ex2"
```

### KdTreeQueryBall

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequeryball"
```

Find all points within `RADIUS` of each query point.

- `RESULT`: list of index lists (or a flat list if `X` is a single point)

### KdTreeQueryPairs

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequerypairs"
```

Find all pairs of points in the tree within `RADIUS` of each other.

- `RESULT`: set of `(i, j)` index pairs

---

## Tier 3 — ConvexHull

### MakeConvexHull

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makeconvexhull"
```

Compute the convex hull of a set of points.
Wraps `scipy.spatial.ConvexHull`.

- `POINTS`: `(n, d)` array
- `RESULT`: integer handle

### ConvexHullAttr

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:convexhullattr"
```

Retrieve an attribute of the `ConvexHull` object.

| `ATTR` | Type | Description |
|--------|------|-------------|
| `'vertices'` | int array | Indices of hull vertices |
| `'simplices'` | int array | Facet index sets |
| `'equations'` | float array | Hyperplane equations (normals + offsets) |
| `'area'` | float | Surface area (perimeter in 2-D) |
| `'volume'` | float | Volume (area in 2-D) |
| `'neighbors'` | int array | Neighbour facet indices |
| `'coplanar'` | int array | Coplanar points not on hull |

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:convexhullattr_ex2"
```

---

## Tier 3 — Delaunay Triangulation

### MakeDelaunay

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makedelaunay"
```

Compute the Delaunay triangulation.
Wraps `scipy.spatial.Delaunay`.

- `RESULT`: integer handle

### DelaunayFindSimplex

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:delaunayfindsimplex"
```

Find the simplex containing each point in `XI`.

- `XI`: `(m, d)` query points
- `BRUTEFORCE`: if `True`, bypass spatial index (default `False`)
- `RESULT`: int array; `-1` for points outside the triangulation

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:delaunayfindsimplex_ex2"
```

---

## Tier 3 — Rotation

Wraps `scipy.spatial.transform.Rotation`.

### MakeRotation

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makerotation"
```

Construct a rotation from a given representation.

| `METHOD` | `DATA` |
|----------|--------|
| `'quat'` | quaternion array `[x, y, z, w]` |
| `'matrix'` | 3×3 rotation matrix |
| `'rotvec'` | rotation vector (axis × angle) |
| `'mrp'` | Modified Rodrigues Parameters |
| `'euler'` | tuple `(seq, angles)` e.g. `('xyz', [0.0, 0.0, 1.57])` |

- `RESULT`: integer handle

### RotationApply

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationapply"
```

Apply the rotation to an array of 3-D vectors.

- `INVERSE`: if `True`, apply the inverse rotation
- `RESULT`: rotated vectors array

### RotationAs

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationas"
```

Export the rotation to a different representation.

- `FORM`: `'quat'`, `'matrix'`, `'rotvec'`, `'mrp'`, or `'euler'`
- `SEQ`: required when `FORM='euler'` (e.g. `'xyz'`)

### RotationCompose

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationcompose"
```

Compose two rotations: `HANDLE_B` is applied first, then `HANDLE_A`.
Returns a new handle.

### RotationInverse

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationinverse"
```

Return the inverse of the rotation as a new handle.

---

## Lifecycle — Free

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:lifecycle"
```

Release the object registered under `HANDLE`. Always succeeds, even if the
handle is unknown or already freed.

---

## Complete Example

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:complete_example"
```

---

*See also: [scipy.cluster](scipy_cluster.md) — clustering algorithms that use spatial distances · [scipy.sparse](scipy_sparse.md) — sparse distance matrices.*
