# scipy.stats — Statistics

The `scipy_stats` module wraps [`scipy.stats`](https://docs.scipy.org/doc/scipy/reference/stats.html) as Clausal predicates. It covers descriptive statistics, correlation and regression, parametric and nonparametric hypothesis tests, distribution evaluation, and frozen distribution handles.

---

## Import

```clausal
# skip
-import_from(scipy_stats, [StatsMean, StatsPearsonCorrelation, ResultGet, ...])
```

Or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_stats, [StatsMean, ...])
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
# skip
StatsDescribe(A, RESULT)
    Compute several descriptive statistics of the data in A.
    RESULT: dict {nobs, minmax, mean, variance, skewness, kurtosis}

StatsMean(A, RESULT)
    Arithmetic mean of A (trimmed mean with no trim).
    RESULT: float

StatsGeometricMean(A, RESULT)
    Geometric mean of A.
    RESULT: float

StatsHarmonicMean(A, RESULT)
    Harmonic mean of A.
    RESULT: float

StatsMode(A, RESULT)
    Modal (most common) value of A.
    RESULT: dict {mode, count}

StatsSkew(A, RESULT)
    Skewness of A.
    RESULT: float

StatsKurtosis(A, RESULT)
    Excess kurtosis of A (Fisher's definition, normal = 0).
    RESULT: float

StatsInterquartileRange(X, RESULT)
    Interquartile range of X (Q3 - Q1).
    RESULT: float

StatsZScore(A, RESULT)
    Z-scores of all elements in A.
    RESULT: list of floats

StatsMedianAbsoluteDeviation(X, RESULT)
    Median absolute deviation of X.
    RESULT: float
```

Example:

```clausal
-import_from(scipy_stats, [StatsMean, StatsDescribe, ResultGet])

Summarise(DATA, MEAN) <- (
    StatsMean(DATA, MEAN),
    StatsDescribe(DATA, DESC),
    ResultGet(DESC, 'variance', VAR),
    ++print(f"mean={float(MEAN):.3f}, var={float(VAR):.3f}")
)
```

---

### Correlation and regression (Tier 2)

```clausal
# skip
StatsPearsonCorrelation(X, Y, RESULT)
    Pearson correlation coefficient and p-value.
    RESULT: dict {statistic, pvalue}

StatsSpearmanCorrelation(A, RESULT)
    Spearman rank-order correlation of a 2-D array A.
    RESULT: dict {statistic, pvalue}

StatsSpearmanCorrelation(A, B, RESULT)
    Spearman correlation between two 1-D arrays.

StatsKendallTau(X, Y, RESULT)
    Kendall's tau statistic and p-value.
    RESULT: dict {statistic, pvalue}

StatsLinearRegression(X, Y, RESULT)
    Linear regression of Y on X.
    RESULT: dict {slope, intercept, rvalue, pvalue, stderr, intercept_stderr}

StatsTheilSlopes(Y, RESULT)
    Theil–Sen estimator for a set of points.
    RESULT: dict {slope, intercept, low_slope, high_slope}

StatsTheilSlopes(Y, X, RESULT)
    Theil–Sen estimator using explicit X values.
```

Example:

```clausal
-import_from(scipy_stats, [StatsLinearRegression, ResultGet])

LinearFit(X, Y, SLOPE, INTERCEPT) <- (
    StatsLinearRegression(X, Y, RESULT),
    ResultGet(RESULT, 'slope', SLOPE),
    ResultGet(RESULT, 'intercept', INTERCEPT)
)
```

---

### Parametric hypothesis tests (Tier 2)

```clausal
# skip
StatsTTest1Sample(A, POPMEAN, RESULT)
    One-sample t-test: is the mean of A different from POPMEAN?
    RESULT: dict {statistic, pvalue, df}

StatsTTestIndependent(A, B, RESULT)
    Independent two-sample t-test (equal variance assumed).
    RESULT: dict {statistic, pvalue, df}

StatsTTestIndependent(A, B, EQUAL_VAR, RESULT)
    EQUAL_VAR: True for Student's t-test, False for Welch's t-test.

StatsTTestRelated(A, B, RESULT)
    Related (paired) samples t-test.
    RESULT: dict {statistic, pvalue, df}

StatsChiSquare(F_OBS, RESULT)
    Chi-square goodness-of-fit test against uniform expected.
    RESULT: dict {statistic, pvalue}

StatsChiSquare(F_OBS, F_EXP, RESULT)
    F_EXP: expected frequencies (same length as F_OBS)

StatsChiSquareContingency(OBSERVED, RESULT)
    Chi-square test of independence from a contingency table.
    RESULT: dict {statistic, pvalue, dof, expected_freq}

StatsFisherExact(TABLE, RESULT)
    Fisher's exact test for a 2×2 contingency table.
    RESULT: dict {statistic, pvalue}
```

Example:

```clausal
-import_from(scipy_stats, [StatsTTestIndependent, ResultGet])

TwoGroupTest(GROUP_A, GROUP_B, PVAL) <- (
    StatsTTestIndependent(GROUP_A, GROUP_B, False, RESULT),
    ResultGet(RESULT, 'pvalue', PVAL)
)
```

---

### Nonparametric tests (Tier 2)

```clausal
# skip
StatsMannWhitneyU(X, Y, RESULT)
    Mann-Whitney U rank test.
    RESULT: dict {statistic, pvalue}

StatsWilcoxon(X, RESULT)
    Wilcoxon signed-rank test for one sample.
    RESULT: dict {statistic, pvalue}

StatsWilcoxon(X, Y, RESULT)
    Wilcoxon signed-rank test for paired samples X and Y.

StatsKruskal(GROUPS, RESULT)
    Kruskal–Wallis H-test. GROUPS is a Python list of arrays.
    RESULT: dict {statistic, pvalue}

StatsKs2samp(DATA1, DATA2, RESULT)
    Two-sample Kolmogorov–Smirnov test.
    RESULT: dict {statistic, pvalue}

StatsNormalityTest(A, RESULT)
    D'Agostino–Pearson omnibus test of normality.
    RESULT: dict {statistic, pvalue}

StatsShapiro(X, RESULT)
    Shapiro–Wilk test for normality.
    RESULT: dict {statistic, pvalue}
```

Example:

```clausal
-import_from(scipy_stats, [StatsKruskal, ResultGet])

GroupDifference(GROUPS, PVAL) <- (
    StatsKruskal(GROUPS, RESULT),
    ResultGet(RESULT, 'pvalue', PVAL)
)
```

---

### Distribution evaluation (Tier 1 functional)

```clausal
# skip
StatsDist(DIST, METHOD, X, RESULT)
    Call scipy.stats.<DIST>.<METHOD>(X) for any distribution and method.
    DIST:   string name of a scipy.stats distribution (e.g. 'norm', 'expon')
    METHOD: string method name (e.g. 'pdf', 'cdf', 'ppf', 'sf', 'isf')
    X:      point at which to evaluate
    RESULT: float

StatsDist(DIST, METHOD, RESULT)
    Call scipy.stats.<DIST>.<METHOD>() for zero-argument methods like 'entropy'.

StatsNormalPdf(X, RESULT)
    Standard normal PDF at X.

StatsNormalPdf(X, LOC, SCALE, RESULT)
    Normal PDF with given LOC (mean) and SCALE (std dev).

StatsNormalCdf(X, RESULT)
    Standard normal CDF at X.

StatsNormalCdf(X, LOC, SCALE, RESULT)

StatsNormalPpf(Q, RESULT)
    Standard normal quantile (inverse CDF) at probability Q.

StatsNormalPpf(Q, LOC, SCALE, RESULT)

StatsNormalRvs(RESULT)
    Single random variate from the standard normal.

StatsNormalRvs(LOC, SCALE, RESULT)
    Single random variate from Normal(LOC, SCALE).

StatsNormalRvs(LOC, SCALE, SIZE, RESULT)
    Array of SIZE random variates from Normal(LOC, SCALE).
```

Example:

```clausal
# skip
-import_from(scipy_stats, [StatsNormalPdf, StatsNormalCdf, StatsDist])

% Probability that X ~ N(0,1) falls in [-1, 1]
NormalInterval(P) <- (
    StatsNormalCdf(1.0, HIGH),
    StatsNormalCdf(-1.0, LOW),
    P is ++(float(HIGH) - float(LOW))
)

% Generic: exponential distribution entropy
ExponEntropy(H) <- (
    StatsDist('expon', 'entropy', H)
)
```

---

### Frozen distribution handles (Tier 3)

Freeze a distribution with fixed parameters, then evaluate it repeatedly without re-creating the distribution object each time.

```clausal
# skip
StatsFreezeDist(DIST, PARAMS_DICT, RESULT)
    Create a frozen scipy.stats distribution.
    DIST:        string name of a scipy.stats distribution (e.g. 'norm', 'beta')
    PARAMS_DICT: Python dict of keyword arguments for the distribution constructor
                 (e.g. {'loc': 1.0, 'scale': 2.0})
    RESULT:      integer handle into the frozen-distribution registry

StatsFrozenPdf(HANDLE, X, RESULT)
    PDF of the frozen distribution at point X.

StatsFrozenCdf(HANDLE, X, P)          # bidirectional
    X ground, P unbound → P = dist.cdf(x)   # forward: evaluate CDF
    P ground, X unbound → X = dist.ppf(p)   # backward: compute quantile (inverse CDF)
    Both ground         → consistency check: succeeds iff dist.cdf(x) ≈ p

StatsFrozenRvs(HANDLE, RESULT)
    Single random variate from the frozen distribution.

StatsFrozenRvs(HANDLE, SIZE, RESULT)
    Array of SIZE random variates.

StatsFrozenStats(HANDLE, RESULT)
    Mean and variance of the frozen distribution.
    RESULT: dict {mean, var}

StatsFrozenFree(HANDLE)
    Release the frozen distribution from the registry.
    Always succeeds. Call when the handle is no longer needed.
```

Example — reuse a frozen beta distribution:

```clausal
-import_from(scipy_stats, [StatsFreezeDist, StatsFrozenPdf, StatsFrozenCdf,
                            StatsFrozenStats, StatsFrozenFree])

BetaAnalysis(HANDLE) <- (
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
BetaCdf(P) <- (
    StatsFreezeDist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    StatsFrozenCdf(H, 0.3, P),
    StatsFrozenFree(H)
)

# Backward: X = quantile at P=0.5 (median) for Beta(2, 5)
BetaMedian(X) <- (
    StatsFreezeDist('beta', ++({'a': 2.0, 'b': 5.0}), H),
    StatsFrozenCdf(H, X, 0.5),
    StatsFrozenFree(H)
)
```

---

### ResultGet

```clausal
# skip
ResultGet(RESULT, FIELD, VALUE)
    Extract a named field from any Tier 2 result dict.
    RESULT: a dict returned by a Tier 2 predicate (or an object with an attribute)
    FIELD:  a ground string key
    VALUE:  unified with RESULT[FIELD] (or getattr(RESULT, FIELD))
    Fails if RESULT is not subscriptable, FIELD is absent, or VALUE does not unify.
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

- **Arrays**: pass Python lists or NumPy arrays via `++()` — e.g. `StatsMean(++([1.0, 2.0, 3.0]), RESULT)`.
- **`StatsKruskal`**: takes a single list of arrays as input — e.g. `StatsKruskal(++([[1,2,3],[4,5,6]]), RESULT)`. Scipy's `kruskal(*samples)` is called internally.
- **`StatsMode`**: scipy ≥ 1.11 returns scalar mode/count; older versions return arrays. The predicate normalises both cases to plain `float` / `int`.
- **`StatsNormalRvs` 1-arity**: the RESULT argument is the sole argument before `trail` — omit LOC, SCALE, and SIZE for a single standard-normal variate.
- **Frozen distributions**: integer handles are module-global. Always call `StatsFrozenFree` when done to avoid memory leaks in long-running programmes.
- **Exceptions**: predicates fail (no solution) when scipy raises an exception. This includes invalid input (e.g. non-square contingency tables for `StatsFisherExact`) and degenerate data.

---

*See also: [scipy.special](scipy_special.md) — special functions used by statistical distributions.*
