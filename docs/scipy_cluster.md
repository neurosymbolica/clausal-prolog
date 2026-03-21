# scipy.cluster — Clustering

The `scipy_cluster` module wraps [`scipy.cluster.hierarchy`](https://docs.scipy.org/doc/scipy/reference/cluster.hierarchy.html) and [`scipy.cluster.vq`](https://docs.scipy.org/doc/scipy/reference/cluster.vq.html) as Clausal predicates. It covers hierarchical clustering (linkage, flat cluster assignment, dendrogram, cophenetic analysis) and vector quantisation (k-means).

---

## Import

```clausal
-import_from(scipy_cluster, [Linkage, FlatCluster, Dendrogram,
                              Cophenet, Inconsistent,
                              KMeans2, KMeans, VectorQuantize, Whiten,
                              ResultGet])
```

Or via the canonical `py.*` path:

```clausal
-import_from(py.scipy_cluster, [Linkage, FlatCluster, ...])
```

---

## Tier

All predicates are **Tier 2** — they return result dicts or NumPy arrays. Use `ResultGet` to access named fields from dict results.

---

## Naming conventions

The `Cluster` prefix is dropped since these predicates live in the cluster module. Abbreviations that are not the universal name are expanded:

| scipy function | Clausal predicate |
|---|---|
| `hierarchy.linkage` | `Linkage` |
| `hierarchy.fcluster` | `FlatCluster` |
| `hierarchy.dendrogram` | `Dendrogram` |
| `hierarchy.cophenet` | `Cophenet` |
| `hierarchy.inconsistent` | `Inconsistent` |
| `vq.kmeans2` | `KMeans2` |
| `vq.kmeans` | `KMeans` |
| `vq.vq` | `VectorQuantize` |
| `vq.whiten` | `Whiten` |

---

## Predicate catalogue

### Hierarchical clustering

#### `Linkage(Y, RESULT)`
#### `Linkage(Y, METHOD, RESULT)`
#### `Linkage(Y, METHOD, METRIC, RESULT)`
#### `Linkage(Y, METHOD, METRIC, OPTIMAL_ORDERING, RESULT)`

Compute a hierarchical clustering linkage matrix from observation matrix or condensed distance matrix `Y`.

- `METHOD`: `'single'`, `'complete'`, `'average'`, `'weighted'`, `'centroid'`, `'median'`, `'ward'` (default `'single'`)
- `METRIC`: distance metric string (default `'euclidean'`)
- `OPTIMAL_ORDERING`: reorder leaves to minimise distance (default `False`)
- `RESULT`: ndarray of shape `(n-1, 4)` — the linkage matrix `Z`

```clausal
Linkage(DATA, 'ward', Z),
% Z is the linkage matrix for ward hierarchical clustering
```

---

#### `FlatCluster(Z, T, RESULT)`
#### `FlatCluster(Z, T, CRITERION, RESULT)`
#### `FlatCluster(Z, T, CRITERION, DEPTH, RESULT)`

Form flat clusters from a hierarchical clustering linkage matrix `Z`.

- `T`: threshold or number of clusters (depending on `CRITERION`)
- `CRITERION`: `'inconsistent'`, `'distance'`, `'maxclust'`, `'monocrit'`, `'maxclust_monocrit'` (default `'inconsistent'`)
- `DEPTH`: depth for inconsistency calculation (default `2`)
- `RESULT`: ndarray of shape `(n,)` — integer cluster assignment for each observation

```clausal
Linkage(DATA, 'ward', Z),
FlatCluster(Z, 3, 'maxclust', LABELS),
% LABELS[i] is the cluster number for observation i
```

---

#### `Dendrogram(Z, RESULT)`
#### `Dendrogram(Z, TRUNCATE_MODE, RESULT)`

Compute dendrogram layout data from linkage matrix `Z`. Always uses `no_plot=True` to avoid matplotlib dependency.

- `TRUNCATE_MODE`: `None`, `'lastp'`, or `'level'`
- `RESULT`: dict with keys `icoord`, `dcoord`, `ivl`, `leaves`, `color_list`

```clausal
Linkage(DATA, 'ward', Z),
Dendrogram(Z, D),
ResultGet(D, 'leaves', LEAVES),
% LEAVES is the list of leaf node indices
```

---

#### `Cophenet(Z, RESULT)`
#### `Cophenet(Z, Y, RESULT)`

Compute cophenetic distances from linkage matrix `Z`.

- Without `Y`: `RESULT` is the condensed cophenetic distance array (ndarray of length `n*(n-1)/2`)
- With `Y` (condensed pairwise distances): `RESULT` is `dict {'c': float, 'd': ndarray}` where `c` is the cophenetic correlation coefficient and `d` is the cophenetic distance array

```clausal
Linkage(DATA, 'ward', Z),
Y is ++(pdist(DATA)),
Cophenet(Z, Y, RESULT),
ResultGet(RESULT, 'c', C),
% C is the cophenetic correlation coefficient (1.0 = perfect)
```

---

#### `Inconsistent(Z, RESULT)`
#### `Inconsistent(Z, DEPTH, RESULT)`

Compute inconsistency statistics for each non-singleton cluster in linkage matrix `Z`.

- `DEPTH`: number of levels to consider (default `2`)
- `RESULT`: ndarray of shape `(n-1, 4)` — each row is `[mean, std, count, inconsistency_coefficient]`

```clausal
Linkage(DATA, 'ward', Z),
Inconsistent(Z, STATS),
% STATS[i, 3] is the inconsistency coefficient for merge i
```

---

### Vector quantisation

#### `KMeans2(DATA, K, RESULT)`
#### `KMeans2(DATA, K, ITERATIONS, RESULT)`
#### `KMeans2(DATA, K, ITERATIONS, SEED, RESULT)`

k-means clustering with explicit re-initialisation (`scipy.cluster.vq.kmeans2`).

- `K`: number of clusters (integer)
- `ITERATIONS`: number of iterations (default `10`)
- `SEED`: random seed for reproducibility
- `RESULT`: dict `{'centroid': ndarray shape (K, D), 'label': ndarray shape (N,)}`

```clausal
KMeans2(DATA, 3, RESULT),
ResultGet(RESULT, 'centroid', CENTROIDS),
ResultGet(RESULT, 'label', LABELS),
```

---

#### `KMeans(OBS, K, RESULT)`
#### `KMeans(OBS, K, ITERATIONS, RESULT)`

Classic k-means (`scipy.cluster.vq.kmeans`). Runs until convergence or the iteration limit.

- `K`: number of clusters (integer) or initial codebook (ndarray)
- `ITERATIONS`: maximum iterations (default `10`)
- `RESULT`: dict `{'codebook': ndarray shape (K, D), 'distortion': float}`

```clausal
KMeans(DATA, 2, RESULT),
ResultGet(RESULT, 'codebook', CODEBOOK),
ResultGet(RESULT, 'distortion', D),
% D is the mean Euclidean distance to the nearest centroid
```

---

#### `VectorQuantize(OBS, CODE_BOOK, RESULT)`

Assign each observation in `OBS` to the nearest code in `CODE_BOOK`.

- `OBS`: ndarray of shape `(N, D)`
- `CODE_BOOK`: ndarray of shape `(K, D)`
- `RESULT`: dict `{'code': ndarray shape (N,), 'dist': ndarray shape (N,)}`
  - `code[i]` — index of nearest centroid for observation `i`
  - `dist[i]` — Euclidean distance to that centroid

```clausal
KMeans(DATA, 2, KR),
ResultGet(KR, 'codebook', CODEBOOK),
VectorQuantize(DATA, CODEBOOK, VQR),
ResultGet(VQR, 'code', CODE),
```

---

#### `Whiten(OBS, RESULT)`

Normalise observations by dividing each feature by its standard deviation.

- `OBS`: ndarray of shape `(N, D)`
- `RESULT`: ndarray of shape `(N, D)` with each column standardised to unit variance

```clausal
Whiten(RAW_DATA, NORMALISED),
KMeans2(NORMALISED, 3, RESULT),
```

---

### Helper

#### `ResultGet(RESULT, FIELD, VALUE)`

Extract a named field from a Tier 2 result dict.

- `RESULT`: dict returned by `KMeans2`, `KMeans`, `VectorQuantize`, `Cophenet` (with Y), or `Dendrogram`
- `FIELD`: string key
- `VALUE`: unified with `RESULT[FIELD]`

```clausal
KMeans(DATA, 2, R),
ResultGet(R, 'codebook', CODEBOOK),
ResultGet(R, 'distortion', D),
```

---

## Typical pipeline

```clausal
% 1. Load and whiten data
Whiten(RAW_DATA, DATA),

% 2. Hierarchical clustering to explore structure
Linkage(DATA, 'ward', Z),
FlatCluster(Z, 3, 'maxclust', LABELS),

% 3. k-means for production assignment
KMeans(DATA, 3, KR),
ResultGet(KR, 'codebook', CODEBOOK),
VectorQuantize(DATA, CODEBOOK, VQR),
ResultGet(VQR, 'code', ASSIGNMENTS).
```

---

## Notes

- `KMeans2` uses random initialisation by default; results are non-deterministic unless `SEED` is fixed.
- `KMeans` and `KMeans2` may warn about empty clusters on small or degenerate data.
- `Dendrogram` always passes `no_plot=True` internally — it returns the layout dict but never calls matplotlib. If you need a plot, access the raw data via `ResultGet` and draw it yourself.
- All predicates fail silently (yield no solutions) on exceptions such as singular matrices or incompatible array shapes.
