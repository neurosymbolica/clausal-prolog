# torch_distributions — Probability Distributions

Wraps `torch.distributions` — probability distributions with sampling,
log-probability, and property queries.

## Import

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:import"
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 2 — fact table | `distribution` | Registry of available distribution types |
| 1 — pure | `make_distribution`, `sample`, `log_prob`, `cdf`, `icdf` | Construct and query |
| 1 — pure (property) | `mean`, `variance`, `stddev`, `entropy` | Distribution properties |

---

## Distribution Registry

### distribution

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:distribution"
```

Enumerate available distribution types. Names use original PyTorch class
names (`"Normal"`, `"Bernoulli"`, `"Categorical"`, etc.).

**Modes:** `(+name, -class)` lookup, `(-name, -class)` enumerate all.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:distribution_ex2"
```

---

## Construction

### make_distribution

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:make_distribution"
```

Construct a distribution from a name string and a params dict. List
values in the params dict are automatically converted to tensors.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:make_distribution_ex2"
```

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:make_distribution_ex3"
```

---

## Properties

### mean, variance, stddev

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:mean_variance_stddev"
```

Query distribution properties. Returns tensors.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:mean_variance_stddev_ex2"
```

### entropy

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:entropy"
```

Distribution entropy (scalar tensor).

---

## Sampling

### sample

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:sample"
```

Draw sample(s) from a distribution. Without a shape argument, draws a
single sample matching the distribution's batch/event shape. With a
shape list, draws that many samples.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:sample_ex2"
```

---

## Log Probability

### log_prob

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:log_prob"
```

Compute the log probability of a value under the distribution.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:log_prob_ex2"
```

---

## CDF / Inverse CDF

### cdf

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:cdf"
```

Cumulative distribution function — probability that a random variable
is less than or equal to `VALUE`.

### icdf

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:icdf"
```

Inverse CDF (quantile function) — the value at which the CDF equals
`PROB`.

`cdf` and `icdf` are inverses: `icdf(D, cdf(D, X)) ≈ X`.

```clausal
--8<-- "tests/fixtures/docs/torch_distributions_sigs.txt:cdf_icdf_roundtrip"
```
