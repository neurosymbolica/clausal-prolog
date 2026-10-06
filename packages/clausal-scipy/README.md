# clausal-scipy

[SciPy](https://scipy.org) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps SciPy's subpackages as Clausal Prolog predicates, one module
each: `scipy_linalg`, `scipy_optimize`, `scipy_stats`,
`scipy_integrate`, `scipy_interpolate`, `scipy_fft`, `scipy_ndimage`,
`scipy_spatial`, `scipy_signal`, `scipy_sparse`, `scipy_cluster`,
`scipy_special`, `scipy_constants` and `scipy_differentiate`.

## Install

```
pip install clausal-scipy
```

`scipy` is pulled in as a dependency. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/scipy_cluster_tests.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/tests/fixtures/scipy_cluster_tests.seam),
shows the shape of a call:

```seam
-import_from(scipy_cluster, [linkage])

sample_points(DATA) <- (DATA is [[1.0,1.0],[1.2,0.9],[0.8,1.1],[5.0,5.0],[5.1,4.9],[4.9,5.1]])

test("linkage ward produces matrix") <- (
    sample_points(DATA),
    linkage(DATA, 'ward', Z),
    ROWS is ++(len(Z)),
    ROWS == 5)
```

## Documentation

- [scipy.cluster — Clustering](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_cluster.md)
- [scipy.constants — Physical Constants](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_constants.md)
- [scipy.differentiate — Numerical Differentiation](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_differentiate.md)
- [scipy.fft — Fast Fourier Transforms](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_fft.md)
- [scipy.integrate — Numerical Integration](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_integrate.md)
- [scipy.interpolate — Interpolation](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_interpolate.md)
- [scipy.linalg — Linear Algebra](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_linalg.md)
- [scipy.ndimage — N-dimensional Image Processing](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_ndimage.md)
- [scipy.optimize — Optimisation](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_optimize.md)
- [scipy.signal — Signal Processing](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_signal.md)
- [scipy.sparse — Sparse Matrices and Sparse Linear Algebra](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_sparse.md)
- [scipy.spatial — Spatial Algorithms](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_spatial.md)
- [scipy.special — Mathematical Special Functions](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_special.md)
- [scipy.stats — statistics](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_stats.md)
- [Predicate renames (2026-10-02)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/RENAMES.md)

## License

MIT
