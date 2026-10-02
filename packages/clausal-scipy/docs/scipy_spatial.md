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
| 1 — pure | `cross_distance`, `pairwise_distance`, `square_form`, `point_distance` | Array in, array/scalar out |
| 3 — handle | `make_kd_tree`, `kd_tree_query`, `kd_tree_query_ball`, `kd_tree_query_pairs` | KD-tree |
| 3 — handle | `make_convex_hull`, `convex_hull_attr` | Convex hull |
| 3 — handle | `make_delaunay`, `delaunay_find_simplex` | Delaunay triangulation |
| 3 — handle | `make_rotation`, `rotation_apply`, `rotation_as`, `rotation_compose`, `rotation_inverse` | 3-D rotation |
| lifecycle | `free` | Release any handle |

---

## Tier 1 — Distance Functions

### cross_distance

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

### pairwise_distance

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

### square_form

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:squareform"
```

Convert between a condensed distance vector and a square distance matrix.
Wraps `scipy.spatial.distance.squareform`.

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:squareform_ex2"
```

### point_distance

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

### make_kd_tree

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makekdtree"
```

Build a KD-tree for fast nearest-neighbour queries.
Wraps `scipy.spatial.KDTree`.

- `DATA`: `(n, d)` array of points
- `LEAFSIZE`: leaf-size threshold (default 10)
- `RESULT`: integer handle

### kd_tree_query

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

### kd_tree_query_ball

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequeryball"
```

Find all points within `RADIUS` of each query point.

- `RESULT`: list of index lists (or a flat list if `X` is a single point)

### kd_tree_query_pairs

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:kdtreequerypairs"
```

Find all pairs of points in the tree within `RADIUS` of each other.

- `RESULT`: set of `(i, j)` index pairs

---

## Tier 3 — ConvexHull

### make_convex_hull

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makeconvexhull"
```

Compute the convex hull of a set of points.
Wraps `scipy.spatial.ConvexHull`.

- `POINTS`: `(n, d)` array
- `RESULT`: integer handle

### convex_hull_attr

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

### make_delaunay

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:makedelaunay"
```

Compute the Delaunay triangulation.
Wraps `scipy.spatial.Delaunay`.

- `RESULT`: integer handle

### delaunay_find_simplex

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

### make_rotation

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

### rotation_apply

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationapply"
```

Apply the rotation to an array of 3-D vectors.

- `INVERSE`: if `True`, apply the inverse rotation
- `RESULT`: rotated vectors array

### rotation_as

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationas"
```

Export the rotation to a different representation.

- `FORM`: `'quat'`, `'matrix'`, `'rotvec'`, `'mrp'`, or `'euler'`
- `SEQ`: required when `FORM='euler'` (e.g. `'xyz'`)

### rotation_compose

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationcompose"
```

Compose two rotations: `HANDLE_B` is applied first, then `HANDLE_A`.
Returns a new handle.

### rotation_inverse

```clausal
--8<-- "tests/fixtures/docs/scipy_spatial_sigs.txt:rotationinverse"
```

Return the inverse of the rotation as a new handle.

---

## Lifecycle — free

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
