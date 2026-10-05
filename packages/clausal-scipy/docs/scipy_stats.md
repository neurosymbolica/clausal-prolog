# scipy.stats — statistics

The `scipy_stats` module wraps [`scipy.stats`](https://docs.scipy.org/doc/scipy/reference/stats.html) as Clausal Prolog predicates. It covers descriptive statistics, correlation and regression, parametric and nonparametric hypothesis tests, distribution evaluation, and frozen distribution handles.

---

## Import

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:import"
```

Or via the canonical `py.*` path:

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:import_ex2"
```

---

## Tiers

- **Tier 1** — descriptive statistics: RESULT is unified with a plain Python float, list, or dict.
- **Tier 2** — result-dict predicates: RESULT is a Python dict. Use `result_get(RESULT, FIELD, VALUE)` to extract fields.
- **Tier 1 functional** — distribution evaluation: plain float output.
- **Tier 3** — frozen distribution handles: `stats_freeze_dist` creates a frozen distribution and returns an opaque integer handle. Pass the handle to `stats_frozen_pdf`, `stats_frozen_cdf`, etc. Release with `stats_frozen_free`.

---

## Naming conventions

Predicate names use full English words; scipy's abbreviations are expanded:

| scipy function | Clausal Prolog predicate |
|---|---|
| `describe` | `stats_describe` |
| `tmean` | `stats_mean` |
| `gmean` | `stats_geometric_mean` |
| `hmean` | `stats_harmonic_mean` |
| `mode` | `stats_mode` |
| `skew` | `stats_skew` |
| `kurtosis` | `stats_kurtosis` |
| `iqr` | `stats_interquartile_range` |
| `zscore` | `stats_z_score` |
| `median_abs_deviation` | `stats_median_absolute_deviation` |
| `pearsonr` | `stats_pearson_correlation` |
| `spearmanr` | `stats_spearman_correlation` |
| `kendalltau` | `stats_kendall_tau` |
| `linregress` | `stats_linear_regression` |
| `theilslopes` | `stats_theil_slopes` |
| `ttest_1samp` | `stats_t_test1_sample` |
| `ttest_ind` | `stats_t_test_independent` |
| `ttest_rel` | `stats_t_test_related` |
| `chisquare` | `stats_chi_square` |
| `chi2_contingency` | `stats_chi_square_contingency` |
| `fisher_exact` | `stats_fisher_exact` |
| `mannwhitneyu` | `stats_mann_whitney_u` |
| `wilcoxon` | `stats_wilcoxon` |
| `kruskal` | `stats_kruskal` |
| `ks_2samp` | `stats_ks2samp` |
| `normaltest` | `stats_normality_test` |
| `shapiro` | `stats_shapiro` |
| `norm.pdf` | `stats_normal_pdf` |
| `norm.cdf` | `stats_normal_cdf` |
| `norm.ppf` | `stats_normal_ppf` |
| `norm.rvs` | `stats_normal_rvs` |

---

## Predicate catalogue

### Descriptive statistics (Tier 1)

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:descriptive_statistics"
```

Example:

```seam
-import_from(scipy_stats, [stats_mean, stats_describe, result_get])

summarise(DATA, MEAN) <- (
    stats_mean(DATA, MEAN),
    stats_describe(DATA, DESC),
    result_get(DESC, 'variance', VAR),
    ++print(f"mean={float(MEAN):.3f}, var={float(VAR):.3f}")
)
```

---

### Correlation and regression (Tier 2)

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:correlation_and_regression"
```

Example:

```seam
-import_from(scipy_stats, [stats_linear_regression, result_get])

linear_fit(X, Y, SLOPE, INTERCEPT) <- (
    stats_linear_regression(X, Y, RESULT),
    result_get(RESULT, 'slope', SLOPE),
    result_get(RESULT, 'intercept', INTERCEPT)
)
```

---

### Parametric hypothesis tests (Tier 2)

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:parametric_hypothesis_tests"
```

Example:

```seam
-import_from(scipy_stats, [stats_t_test_independent, result_get])

two_group_test(GROUP_A, GROUP_B, PVAL) <- (
    stats_t_test_independent(GROUP_A, GROUP_B, False, RESULT),
    result_get(RESULT, 'pvalue', PVAL)
)
```

---

### Nonparametric tests (Tier 2)

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:nonparametric_tests"
```

Example:

```seam
-import_from(scipy_stats, [stats_kruskal, result_get])

group_difference(GROUPS, PVAL) <- (
    stats_kruskal(GROUPS, RESULT),
    result_get(RESULT, 'pvalue', PVAL)
)
```

---

### Distribution evaluation (Tier 1 functional)

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:distribution_evaluation"
```

Example:

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:distribution_evaluation_ex2"
```

---

### Frozen distribution handles (Tier 3)

freeze a distribution with fixed parameters, then evaluate it repeatedly without re-creating the distribution object each time.

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:frozen_distribution_handles"
```

Example — reuse a frozen beta distribution:

```seam
-import_from(scipy_stats, [stats_freeze_dist, stats_frozen_pdf, stats_frozen_cdf,
                            stats_frozen_stats, stats_frozen_free])

beta_analysis(HANDLE) <- (
    stats_freeze_dist('beta', ++({'a': 2.0, 'b': 5.0}), HANDLE),
    stats_frozen_pdf(HANDLE, 0.3, PDF),
    stats_frozen_cdf(HANDLE, 0.3, CDF),
    stats_frozen_stats(HANDLE, STATS),
    ++print(f"pdf={float(PDF):.4f}, cdf={float(CDF):.4f}"),
    stats_frozen_free(HANDLE)
)
```

Example — bidirectional `stats_frozen_cdf` as CDF and quantile function:

```seam
-import_from(scipy_stats, [stats_freeze_dist, stats_frozen_cdf, stats_frozen_free])

# Forward: P = CDF(0.3) for Beta(2, 5)
beta_cdf(P) <- (
    stats_freeze_dist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    stats_frozen_cdf(H, 0.3, P),
    stats_frozen_free(H)
)

# Backward: X = quantile at P=0.5 (median) for Beta(2, 5)
beta_median(X) <- (
    stats_freeze_dist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    stats_frozen_cdf(H, X, 0.5),
    stats_frozen_free(H)
)
```

---

### result_get

```seam
--8<-- "tests/fixtures/docs/scipy_stats_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `stats_pearson_correlation`, `stats_kendall_tau`, `stats_spearman_correlation` | `'statistic'`, `'pvalue'` |
| `stats_linear_regression` | `'slope'`, `'intercept'`, `'rvalue'`, `'pvalue'`, `'stderr'` |
| `stats_theil_slopes` | `'slope'`, `'intercept'`, `'low_slope'`, `'high_slope'` |
| `stats_t_test1_sample`, `stats_t_test_independent`, `stats_t_test_related` | `'statistic'`, `'pvalue'`, `'df'` |
| `stats_chi_square`, `stats_fisher_exact` | `'statistic'`, `'pvalue'` |
| `stats_chi_square_contingency` | `'statistic'`, `'pvalue'`, `'dof'`, `'expected_freq'` |
| `stats_mann_whitney_u`, `stats_wilcoxon`, `stats_kruskal` | `'statistic'`, `'pvalue'` |
| `stats_ks2samp`, `stats_normality_test`, `stats_shapiro` | `'statistic'`, `'pvalue'` |
| `stats_describe` | `'nobs'`, `'minmax'`, `'mean'`, `'variance'`, `'skewness'`, `'kurtosis'` |
| `stats_mode` | `'mode'`, `'count'` |
| `stats_frozen_stats` | `'mean'`, `'var'` |

---

## Notes

- **Arrays**: pass Python lists or NumPy arrays via [`++()`](python_integration.md) — e.g. `stats_mean(++([1.0, 2.0, 3.0]), RESULT)`.
- **`stats_kruskal`**: takes a single list of arrays as input — e.g. `stats_kruskal(++([[1,2,3],[4,5,6]]), RESULT)`. Scipy's `kruskal(*samples)` is called internally.
- **`stats_mode`**: scipy ≥ 1.11 returns scalar mode/count; older versions return arrays. The predicate normalises both cases to plain `float` / `int`.
- **`stats_normal_rvs` 1-arity**: the RESULT argument is the sole argument before `trail` — omit LOC, SCALE, and SIZE for a single standard-normal variate.
- **Frozen distributions**: integer handles are module-global. Always call `stats_frozen_free` when done to avoid memory leaks in long-running programmes.
- **Exceptions**: predicates fail (no solution) when scipy raises an exception. This includes invalid input (e.g. non-square contingency tables for `stats_fisher_exact`) and degenerate data.

---

*See also: [scipy.special](scipy_special.md) — special functions used by statistical distributions.*
