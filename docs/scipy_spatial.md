# scipy.spatial — Spatial Algorithms

Provides spatial distance functions and spatial data-structure predicates from
`scipy.spatial` as importable clausal predicates.

## Import

```clausal
# skip
-import_from(scipy_spatial, [CrossDistance, PairwiseDistance, MakeKdTree, ...])
```

or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_spatial, [CrossDistance, ...])
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
# skip
CrossDistance(XA, XB, RESULT)
CrossDistance(XA, XB, METRIC, RESULT)
CrossDistance(XA, XB, METRIC, KWARGS, RESULT)
```

Compute the distance between each pair of rows from `XA` and `XB`.
Wraps `scipy.spatial.distance.cdist`.

- `XA`, `XB`: arrays of shape `(m, d)` and `(n, d)`
- `METRIC`: distance metric string (default `'minkowski'`)
- `KWARGS`: Python dict of extra metric-specific keyword arguments, or `None`
- `RESULT`: `(m × n)` distance matrix

```clausal
# skip
CrossDistance(++([[0.0, 0.0]]), ++([[3.0, 4.0]]), 'euclidean', D),
V is ++(float(D[0, 0]))   % V = 5.0
```

### PairwiseDistance

```clausal
# skip
PairwiseDistance(X, RESULT)
PairwiseDistance(X, METRIC, RESULT)
PairwiseDistance(X, METRIC, KWARGS, RESULT)
```

Compute pairwise distances between all rows within a single array `X`.
Wraps `scipy.spatial.distance.pdist`.

- `X`: array of shape `(n, d)`
- `RESULT`: condensed distance vector of length `n*(n-1)/2`

```clausal
# skip
PairwiseDistance(++([[0.0,0.0],[3.0,4.0]]), 'euclidean', D),
V is ++(float(D[0]))   % V = 5.0
```

### SquareForm

```clausal
# skip
SquareForm(X, RESULT)
```

Convert between a condensed distance vector and a square distance matrix.
Wraps `scipy.spatial.distance.squareform`.

```clausal
# skip
PairwiseDistance(PTS, CONDENSED),
SquareForm(CONDENSED, SQUARE)   % SQUARE is the full n×n matrix
```

### PointDistance

```clausal
# skip
PointDistance(METRIC, X, Y, RESULT)
```

Compute the scalar distance between two individual points using the named
metric.

- `METRIC`: e.g. `'euclidean'`, `'cityblock'`, `'cosine'`, `'mahalanobis'`
- `X`, `Y`: 1-D arrays or lists
- `RESULT`: float scalar

```clausal
# skip
PointDistance('euclidean', ++([0.0, 0.0]), ++([3.0, 4.0]), D)  % D = 5.0
```

---

## Tier 3 — KD-Tree

### MakeKdTree

```clausal
# skip
MakeKdTree(DATA, RESULT)
MakeKdTree(DATA, LEAFSIZE, RESULT)
```

Build a KD-tree for fast nearest-neighbour queries.
Wraps `scipy.spatial.KDTree`.

- `DATA`: `(n, d)` array of points
- `LEAFSIZE`: leaf-size threshold (default 10)
- `RESULT`: integer handle

### KdTreeQuery

```clausal
# skip
KdTreeQuery(HANDLE, X, RESULT)
KdTreeQuery(HANDLE, X, K, RESULT)
```

Query the KD-tree for the `K` nearest neighbours of each point in `X`.

- `X`: query point(s) — `(d,)` for a single point, `(m, d)` for multiple
- `K`: number of neighbours (default 1)
- `RESULT`: dict with keys `'distances'` and `'indices'`

```clausal
# skip
MakeKdTree(DATA, KD),
KdTreeQuery(KD, QUERY, 3, R),
NEAREST is ++(R['indices'])
```

### KdTreeQueryBall

```clausal
# skip
KdTreeQueryBall(HANDLE, X, RADIUS, RESULT)
```

Find all points within `RADIUS` of each query point.

- `RESULT`: list of index lists (or a flat list if `X` is a single point)

### KdTreeQueryPairs

```clausal
# skip
KdTreeQueryPairs(HANDLE, RADIUS, RESULT)
```

Find all pairs of points in the tree within `RADIUS` of each other.

- `RESULT`: set of `(i, j)` index pairs

---

## Tier 3 — ConvexHull

### MakeConvexHull

```clausal
# skip
MakeConvexHull(POINTS, RESULT)
```

Compute the convex hull of a set of points.
Wraps `scipy.spatial.ConvexHull`.

- `POINTS`: `(n, d)` array
- `RESULT`: integer handle

### ConvexHullAttr

```clausal
# skip
ConvexHullAttr(HANDLE, ATTR, RESULT)
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
# skip
MakeConvexHull(PTS, H),
ConvexHullAttr(H, 'volume', VOL),
Free(H)
```

---

## Tier 3 — Delaunay Triangulation

### MakeDelaunay

```clausal
# skip
MakeDelaunay(POINTS, RESULT)
```

Compute the Delaunay triangulation.
Wraps `scipy.spatial.Delaunay`.

- `RESULT`: integer handle

### DelaunayFindSimplex

```clausal
# skip
DelaunayFindSimplex(HANDLE, XI, RESULT)
DelaunayFindSimplex(HANDLE, XI, BRUTEFORCE, RESULT)
```

Find the simplex containing each point in `XI`.

- `XI`: `(m, d)` query points
- `BRUTEFORCE`: if `True`, bypass spatial index (default `False`)
- `RESULT`: int array; `-1` for points outside the triangulation

```clausal
# skip
MakeDelaunay(PTS, H),
DelaunayFindSimplex(H, ++([[0.5, 0.3]]), IDX),
++(int(IDX[0]) >= 0)   % point is inside
```

---

## Tier 3 — Rotation

Wraps `scipy.spatial.transform.Rotation`.

### MakeRotation

```clausal
# skip
MakeRotation(METHOD, DATA, RESULT)
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
# skip
RotationApply(HANDLE, VECTORS, RESULT)
RotationApply(HANDLE, VECTORS, INVERSE, RESULT)
```

Apply the rotation to an array of 3-D vectors.

- `INVERSE`: if `True`, apply the inverse rotation
- `RESULT`: rotated vectors array

### RotationAs

```clausal
# skip
RotationAs(HANDLE, FORM, RESULT)
RotationAs(HANDLE, FORM, SEQ, RESULT)
```

Export the rotation to a different representation.

- `FORM`: `'quat'`, `'matrix'`, `'rotvec'`, `'mrp'`, or `'euler'`
- `SEQ`: required when `FORM='euler'` (e.g. `'xyz'`)

### RotationCompose

```clausal
# skip
RotationCompose(HANDLE_A, HANDLE_B, RESULT)
```

Compose two rotations: `HANDLE_B` is applied first, then `HANDLE_A`.
Returns a new handle.

### RotationInverse

```clausal
# skip
RotationInverse(HANDLE, RESULT)
```

Return the inverse of the rotation as a new handle.

---

## Lifecycle — Free

```clausal
# skip
Free(HANDLE)
```

Release the object registered under `HANDLE`. Always succeeds, even if the
handle is unknown or already freed.

---

## Complete Example

```clausal
# skip
-import_from(scipy_spatial, [CrossDistance, MakeKdTree, KdTreeQuery,
                              MakeRotation, RotationApply, RotationAs, Free])

# Find the two nearest neighbours of each point
nearest_two(POINTS, INDICES) <- (
    MakeKdTree(POINTS, KD),
    KdTreeQuery(KD, POINTS, 2, R),
    INDICES is ++(R['indices'][:, 1]),
    Free(KD))

# Rotate a batch of vectors by 90 degrees around Z
rotate_z90(VECTORS, ROTATED) <- (
    MakeRotation('rotvec', ++([0.0, 0.0, 1.5707963267948966]), ROT),
    RotationApply(ROT, VECTORS, ROTATED),
    Free(ROT))
```

---

*See also: [scipy.cluster](scipy_cluster.md) — clustering algorithms that use spatial distances · [scipy.sparse](scipy_sparse.md) — sparse distance matrices.*
