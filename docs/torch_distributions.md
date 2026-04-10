# torch_distributions — Probability Distributions

Wraps `torch.distributions` — probability distributions with sampling,
log-probability, and property queries.

## Import

```clausal
# skip
-import_from(py.torch_distributions, [distribution, make_distribution,
    sample, log_prob, entropy, mean, variance, stddev, cdf, icdf])
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
# skip
distribution(NAME, CLASS)
```

Enumerate available distribution types. Names use original PyTorch class
names (`"Normal"`, `"Bernoulli"`, `"Categorical"`, etc.).

**Modes:** `(+name, -class)` lookup, `(-name, -class)` enumerate all.

```clausal
# skip
findall(N, distribution(N, _), NS),
in_("Normal", NS)
```

---

## Construction

### make_distribution

```clausal
# skip
make_distribution(NAME, PARAMS, DIST)
```

Construct a distribution from a name string and a params dict. List
values in the params dict are automatically converted to tensors.

```clausal
# skip
make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D)
```

```clausal
# skip
make_distribution("Categorical", {"probs": [0.25, 0.25, 0.25, 0.25]}, D)
```

---

## Properties

### mean, variance, stddev

```clausal
# skip
mean(DIST, M)
variance(DIST, V)
stddev(DIST, S)
```

Query distribution properties. Returns tensors.

```clausal
# skip
make_distribution("Normal", {"loc": 2.0, "scale": 1.0}, D),
mean(D, M),
tensor_list(M, 2.0)
```

### entropy

```clausal
# skip
entropy(DIST, H)
```

Distribution entropy (scalar tensor).

---

## Sampling

### sample

```clausal
# skip
sample(DIST, S)
sample(DIST, SHAPE, S)
```

Draw sample(s) from a distribution. Without a shape argument, draws a
single sample matching the distribution's batch/event shape. With a
shape list, draws that many samples.

```clausal
# skip
make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
sample(D, [100], S),
shape(S, [100])
```

---

## Log Probability

### log_prob

```clausal
# skip
log_prob(DIST, VALUE, LP)
```

Compute the log probability of a value under the distribution.

```clausal
# skip
make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
tensor(0.0, V),
log_prob(D, V, LP)
```

---

## CDF / Inverse CDF

### cdf

```clausal
# skip
cdf(DIST, VALUE, PROB)
```

Cumulative distribution function — probability that a random variable
is less than or equal to `VALUE`.

### icdf

```clausal
# skip
icdf(DIST, PROB, VALUE)
```

Inverse CDF (quantile function) — the value at which the CDF equals
`PROB`.

`cdf` and `icdf` are inverses: `icdf(D, cdf(D, X)) ≈ X`.

```clausal
# skip
make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
tensor(0.5, V),
cdf(D, V, P),
icdf(D, P, V2),
allclose(V, V2)
```
