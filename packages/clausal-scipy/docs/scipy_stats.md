# scipy.stats — statistics

The `scipy_stats` module wraps [`scipy.stats`](https://docs.scipy.org/doc/scipy/reference/stats.html) as Clausal predicates. It covers descriptive statistics, correlation and regression, parametric and nonparametric hypothesis tests, distribution evaluation, and frozen distribution handles.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:import_ex2"
```

---

## Tiers

- **Tier 1** — descriptive statistics: RESULT is unified with a plain Python float, list, or dict.
- **Tier 2** — result-dict predicates: RESULT is a Python dict. Use `ResultGet(RESULT, FIELD, VALUE)` to extract fields.
- **Tier 1 functional** — distribution evaluation: plain float output.
- **Tier 3** — frozen distribution handles: `StatsFreezeDist` creates a frozen distribution and returns an opaque integer handle. Pass the handle to `StatsFrozenPdf`, `StatsFrozenCdf`, etc. Release with `StatsFrozenFree`.

---

## Naming conventions

Predicate names use full English words; scipy's abbreviations are expanded:

| scipy function | Clausal predicate |
|---|---|
| `describe` | `StatsDescribe` |
| `tmean` | `StatsMean` |
| `gmean` | `StatsGeometricMean` |
| `hmean` | `StatsHarmonicMean` |
| `mode` | `StatsMode` |
| `skew` | `StatsSkew` |
| `kurtosis` | `StatsKurtosis` |
| `iqr` | `StatsInterquartileRange` |
| `zscore` | `StatsZScore` |
| `median_abs_deviation` | `StatsMedianAbsoluteDeviation` |
| `pearsonr` | `StatsPearsonCorrelation` |
| `spearmanr` | `StatsSpearmanCorrelation` |
| `kendalltau` | `StatsKendallTau` |
| `linregress` | `StatsLinearRegression` |
| `theilslopes` | `StatsTheilSlopes` |
| `ttest_1samp` | `StatsTTest1Sample` |
| `ttest_ind` | `StatsTTestIndependent` |
| `ttest_rel` | `StatsTTestRelated` |
| `chisquare` | `StatsChiSquare` |
| `chi2_contingency` | `StatsChiSquareContingency` |
| `fisher_exact` | `StatsFisherExact` |
| `mannwhitneyu` | `StatsMannWhitneyU` |
| `wilcoxon` | `StatsWilcoxon` |
| `kruskal` | `StatsKruskal` |
| `ks_2samp` | `StatsKs2samp` |
| `normaltest` | `StatsNormalityTest` |
| `shapiro` | `StatsShapiro` |
| `norm.pdf` | `StatsNormalPdf` |
| `norm.cdf` | `StatsNormalCdf` |
| `norm.ppf` | `StatsNormalPpf` |
| `norm.rvs` | `StatsNormalRvs` |

---

## Predicate catalogue

### Descriptive statistics (Tier 1)

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:descriptive_statistics"
```

Example:

```clausal
-import_from(scipy_stats, [StatsMean, StatsDescribe, ResultGet])

summarise(DATA, MEAN) <- (
    StatsMean(DATA, MEAN),
    StatsDescribe(DATA, DESC),
    ResultGet(DESC, 'variance', VAR),
    ++print(f"mean={float(MEAN):.3f}, var={float(VAR):.3f}")
)
```

---

### Correlation and regression (Tier 2)

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:correlation_and_regression"
```

Example:

```clausal
-import_from(scipy_stats, [StatsLinearRegression, ResultGet])

linear_fit(X, Y, SLOPE, INTERCEPT) <- (
    StatsLinearRegression(X, Y, RESULT),
    ResultGet(RESULT, 'slope', SLOPE),
    ResultGet(RESULT, 'intercept', INTERCEPT)
)
```

---

### Parametric hypothesis tests (Tier 2)

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:parametric_hypothesis_tests"
```

Example:

```clausal
-import_from(scipy_stats, [StatsTTestIndependent, ResultGet])

two_group_test(GROUP_A, GROUP_B, PVAL) <- (
    StatsTTestIndependent(GROUP_A, GROUP_B, False, RESULT),
    ResultGet(RESULT, 'pvalue', PVAL)
)
```

---

### Nonparametric tests (Tier 2)

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:nonparametric_tests"
```

Example:

```clausal
-import_from(scipy_stats, [StatsKruskal, ResultGet])

group_difference(GROUPS, PVAL) <- (
    StatsKruskal(GROUPS, RESULT),
    ResultGet(RESULT, 'pvalue', PVAL)
)
```

---

### Distribution evaluation (Tier 1 functional)

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:distribution_evaluation"
```

Example:

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:distribution_evaluation_ex2"
```

---

### Frozen distribution handles (Tier 3)

freeze a distribution with fixed parameters, then evaluate it repeatedly without re-creating the distribution object each time.

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:frozen_distribution_handles"
```

Example — reuse a frozen beta distribution:

```clausal
-import_from(scipy_stats, [StatsFreezeDist, StatsFrozenPdf, StatsFrozenCdf,
                            StatsFrozenStats, StatsFrozenFree])

beta_analysis(HANDLE) <- (
    StatsFreezeDist('beta', ++({'a': 2.0, 'b': 5.0}), HANDLE),
    StatsFrozenPdf(HANDLE, 0.3, PDF),
    StatsFrozenCdf(HANDLE, 0.3, CDF),
    StatsFrozenStats(HANDLE, STATS),
    ++print(f"pdf={float(PDF):.4f}, cdf={float(CDF):.4f}"),
    StatsFrozenFree(HANDLE)
)
```

Example — bidirectional `StatsFrozenCdf` as CDF and quantile function:

```clausal
-import_from(scipy_stats, [StatsFreezeDist, StatsFrozenCdf, StatsFrozenFree])

# Forward: P = CDF(0.3) for Beta(2, 5)
beta_cdf(P) <- (
    StatsFreezeDist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    StatsFrozenCdf(H, 0.3, P),
    StatsFrozenFree(H)
)

# Backward: X = quantile at P=0.5 (median) for Beta(2, 5)
beta_median(X) <- (
    StatsFreezeDist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    StatsFrozenCdf(H, X, 0.5),
    StatsFrozenFree(H)
)
```

---

### ResultGet

```clausal
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `StatsPearsonCorrelation`, `StatsKendallTau`, `StatsSpearmanCorrelation` | `'statistic'`, `'pvalue'` |
| `StatsLinearRegression` | `'slope'`, `'intercept'`, `'rvalue'`, `'pvalue'`, `'stderr'` |
| `StatsTheilSlopes` | `'slope'`, `'intercept'`, `'low_slope'`, `'high_slope'` |
| `StatsTTest1Sample`, `StatsTTestIndependent`, `StatsTTestRelated` | `'statistic'`, `'pvalue'`, `'df'` |
| `StatsChiSquare`, `StatsFisherExact` | `'statistic'`, `'pvalue'` |
| `StatsChiSquareContingency` | `'statistic'`, `'pvalue'`, `'dof'`, `'expected_freq'` |
| `StatsMannWhitneyU`, `StatsWilcoxon`, `StatsKruskal` | `'statistic'`, `'pvalue'` |
| `StatsKs2samp`, `StatsNormalityTest`, `StatsShapiro` | `'statistic'`, `'pvalue'` |
| `StatsDescribe` | `'nobs'`, `'minmax'`, `'mean'`, `'variance'`, `'skewness'`, `'kurtosis'` |
| `StatsMode` | `'mode'`, `'count'` |
| `StatsFrozenStats` | `'mean'`, `'var'` |

---

## Notes

- **Arrays**: pass Python lists or NumPy arrays via [`++()`](python_integration.md) — e.g. `StatsMean(++([1.0, 2.0, 3.0]), RESULT)`.
- **`StatsKruskal`**: takes a single list of arrays as input — e.g. `StatsKruskal(++([[1,2,3],[4,5,6]]), RESULT)`. Scipy's `kruskal(*samples)` is called internally.
- **`StatsMode`**: scipy ≥ 1.11 returns scalar mode/count; older versions return arrays. The predicate normalises both cases to plain `float` / `int`.
- **`StatsNormalRvs` 1-arity**: the RESULT argument is the sole argument before `trail` — omit LOC, SCALE, and SIZE for a single standard-normal variate.
- **Frozen distributions**: integer handles are module-global. Always call `StatsFrozenFree` when done to avoid memory leaks in long-running programmes.
- **Exceptions**: predicates fail (no solution) when scipy raises an exception. This includes invalid input (e.g. non-square contingency tables for `StatsFisherExact`) and degenerate data.

---

*See also: [scipy.special](scipy_special.md) — special functions used by statistical distributions.*
