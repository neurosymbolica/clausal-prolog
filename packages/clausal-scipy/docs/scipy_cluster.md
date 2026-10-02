# scipy.cluster — Clustering

The `scipy_cluster` module wraps [`scipy.cluster.hierarchy`](https://docs.scipy.org/doc/scipy/reference/cluster.hierarchy.html) and [`scipy.cluster.vq`](https://docs.scipy.org/doc/scipy/reference/cluster.vq.html) as Clausal predicates. It covers hierarchical clustering (linkage, flat cluster assignment, dendrogram, cophenetic analysis) and vector quantisation (k-means).

---

## Import

```clausal
-import_from(scipy_cluster, [linkage, flat_cluster, dendrogram,
                              cophenet, inconsistent,
                              k_means2, k_means, vector_quantize, whiten,
                              result_get])
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:import"
```

---

## Tier

All predicates are **Tier 2** — they return result dicts or NumPy arrays. Use `result_get` to access named fields from dict results.

---

## Naming conventions

The `Cluster` prefix is dropped since these predicates live in the cluster [module](import.md). Abbreviations that are not the universal name are expanded:

| scipy function | Clausal predicate |
|---|---|
| `hierarchy.linkage` | `linkage` |
| `hierarchy.fcluster` | `flat_cluster` |
| `hierarchy.dendrogram` | `dendrogram` |
| `hierarchy.cophenet` | `cophenet` |
| `hierarchy.inconsistent` | `inconsistent` |
| `vq.kmeans2` | `k_means2` |
| `vq.kmeans` | `k_means` |
| `vq.vq` | `vector_quantize` |
| `vq.whiten` | `whiten` |

---

## Predicate catalogue

### Hierarchical clustering

#### `linkage(Y, RESULT)`
#### `linkage(Y, METHOD, RESULT)`
#### `linkage(Y, METHOD, METRIC, RESULT)`
#### `linkage(Y, METHOD, METRIC, OPTIMAL_ORDERING, RESULT)`

Compute a hierarchical clustering linkage matrix from observation matrix or condensed distance matrix `Y`.

- `METHOD`: `'single'`, `'complete'`, `'average'`, `'weighted'`, `'centroid'`, `'median'`, `'ward'` (default `'single'`)
- `METRIC`: distance metric string (default `'euclidean'`)
- `OPTIMAL_ORDERING`: reorder leaves to minimise distance (default `False`)
- `RESULT`: ndarray of shape `(n-1, 4)` — the linkage matrix `Z`

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:hierarchical_clustering"
```

---

#### `flat_cluster(Z, T, RESULT)`
#### `flat_cluster(Z, T, CRITERION, RESULT)`
#### `flat_cluster(Z, T, CRITERION, DEPTH, RESULT)`

Form flat clusters from a hierarchical clustering linkage matrix `Z`.

- `T`: threshold or number of clusters (depending on `CRITERION`)
- `CRITERION`: `'inconsistent'`, `'distance'`, `'maxclust'`, `'monocrit'`, `'maxclust_monocrit'` (default `'inconsistent'`)
- `DEPTH`: depth for inconsistency calculation (default `2`)
- `RESULT`: ndarray of shape `(n,)` — integer cluster assignment for each observation

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:hierarchical_clustering_ex2"
```

---

#### `dendrogram(Z, RESULT)`
#### `dendrogram(Z, TRUNCATE_MODE, RESULT)`

Compute dendrogram layout data from linkage matrix `Z`. Always uses `no_plot=True` to avoid matplotlib dependency.

- `TRUNCATE_MODE`: `None`, `'lastp'`, or `'level'`
- `RESULT`: dict with keys `icoord`, `dcoord`, `ivl`, `leaves`, `color_list`

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:hierarchical_clustering_ex3"
```

---

#### `cophenet(Z, RESULT)`
#### `cophenet(Z, Y, RESULT)`

Compute cophenetic distances from linkage matrix `Z`.

- Without `Y`: `RESULT` is the condensed cophenetic distance array (ndarray of length `n*(n-1)/2`)
- With `Y` (condensed pairwise distances): `RESULT` is `dict {'c': float, 'd': ndarray}` where `c` is the cophenetic correlation coefficient and `d` is the cophenetic distance array

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:hierarchical_clustering_ex4"
```

---

#### `inconsistent(Z, RESULT)`
#### `inconsistent(Z, DEPTH, RESULT)`

Compute inconsistency statistics for each non-singleton cluster in linkage matrix `Z`.

- `DEPTH`: number of levels to consider (default `2`)
- `RESULT`: ndarray of shape `(n-1, 4)` — each row is `[mean, std, count, inconsistency_coefficient]`

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:hierarchical_clustering_ex5"
```

---

### Vector quantisation

#### `k_means2(DATA, K, RESULT)`
#### `k_means2(DATA, K, ITERATIONS, RESULT)`
#### `k_means2(DATA, K, ITERATIONS, SEED, RESULT)`

k-means clustering with explicit re-initialisation (`scipy.cluster.vq.kmeans2`).

- `K`: number of clusters (integer)
- `ITERATIONS`: number of iterations (default `10`)
- `SEED`: random seed for reproducibility
- `RESULT`: dict `{'centroid': ndarray shape (K, D), 'label': ndarray shape (N,)}`

```clausal
k_means2(DATA, 3, RESULT),
result_get(RESULT, 'centroid', CENTROIDS),
result_get(RESULT, 'label', LABELS),
```

---

#### `k_means(OBS, K, RESULT)`
#### `k_means(OBS, K, ITERATIONS, RESULT)`

Classic k-means (`scipy.cluster.vq.kmeans`). Runs until convergence or the iteration limit.

- `K`: number of clusters (integer) or initial codebook (ndarray)
- `ITERATIONS`: maximum iterations (default `10`)
- `RESULT`: dict `{'codebook': ndarray shape (K, D), 'distortion': float}`

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:vector_quantisation"
```

---

#### `vector_quantize(OBS, CODE_BOOK, RESULT)`

Assign each observation in `OBS` to the nearest code in `CODE_BOOK`.

- `OBS`: ndarray of shape `(N, D)`
- `CODE_BOOK`: ndarray of shape `(K, D)`
- `RESULT`: dict `{'code': ndarray shape (N,), 'dist': ndarray shape (N,)}`
  - `code[i]` — index of nearest centroid for observation `i`
  - `dist[i]` — Euclidean distance to that centroid

```clausal
k_means(DATA, 2, KR),
result_get(KR, 'codebook', CODEBOOK),
vector_quantize(DATA, CODEBOOK, VQR),
result_get(VQR, 'code', CODE),
```

---

#### `whiten(OBS, RESULT)`

Normalise observations by dividing each feature by its standard deviation.

- `OBS`: ndarray of shape `(N, D)`
- `RESULT`: ndarray of shape `(N, D)` with each column standardised to unit variance

```clausal
whiten(RAW_DATA, NORMALISED),
k_means2(NORMALISED, 3, RESULT),
```

---

### Helper

#### `result_get(RESULT, FIELD, VALUE)`

Extract a named field from a Tier 2 result dict.

- `RESULT`: dict returned by `k_means2`, `k_means`, `vector_quantize`, `cophenet` (with Y), or `dendrogram`
- `FIELD`: string key
- `VALUE`: unified with `RESULT[FIELD]`

```clausal
k_means(DATA, 2, R),
result_get(R, 'codebook', CODEBOOK),
result_get(R, 'distortion', D),
```

---

## Typical pipeline

```clausal
--8<-- "tests/fixtures/docs/scipy_cluster_sigs.txt:typical_pipeline"
```

---

## Notes

- `k_means2` uses random initialisation by default; results are non-deterministic unless `SEED` is fixed.
- `k_means` and `k_means2` may warn about empty clusters on small or degenerate data.
- `dendrogram` always passes `no_plot=True` internally — it returns the layout dict but never calls matplotlib. If you need a plot, access the raw data via `result_get` and draw it yourself.
- All predicates fail silently (yield no solutions) on exceptions such as singular matrices or incompatible array shapes.

---

*See also: [scipy.spatial](scipy_spatial.md) — distance metrics and spatial structures · [scipy.stats](scipy_stats.md) — statistical distributions and tests.*
