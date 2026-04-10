# Phase 9 — Probability Distributions

Wraps `torch.distributions` — probability distributions with sampling,
log-probability, and property queries. Natural fit for relational
enumeration and multi-mode property queries.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.
Phase 3 — `clausal/modules/py/torch_nn.py` for `_fact_table_2()` pattern.

**File to create:** `clausal/modules/py/torch_distributions.py`

**Overlap with scipy:** `scipy_stats.py` covers similar ground
(`StatsDist`, `StatsFreezeDist`, `StatsFrozenPdf`, `StatsFrozenCdf`,
`StatsFrozenRvs`). The PyTorch versions are tensor-native and
GPU-accelerated, and integrate with autograd for variational inference.

---

## Predicates

### Distribution registry

| Name | Arity | Modes | Nondet? | Description |
|---|---|---|---|---|
| `distribution` | `/2` | `(+name, -class)`, `(-name, -class)` | yes | Available distribution types |

### Distribution operations

| Name | Arity | Modes | Description |
|---|---|---|---|
| `make_distribution` | `/3` | `(+name, +params, -dist)` | Construct a distribution |
| `sample` | `/2, /3` | `(+dist, -S)`, `(+dist, +shape, -S)` | Draw sample(s) |
| `log_prob` | `/3` | `(+dist, +value, -LP)` | Log probability of value |
| `entropy` | `/2` | `(+dist, -H)` | Distribution entropy |
| `mean` | `/2` | `(+dist, -M)` | Distribution mean |
| `variance` | `/2` | `(+dist, -V)` | Distribution variance |
| `stddev` | `/2` | `(+dist, -S)` | Distribution standard deviation |
| `cdf` | `/3` | `(+dist, +value, -P)` | Cumulative distribution function |
| `icdf` | `/3` | `(+dist, +prob, -V)` | Inverse CDF (quantile function) |

### Bijective pair

`cdf`/`icdf` are inverses: `icdf(dist, cdf(dist, x)) == x`.

---

## Context and Reference Patterns

`distribution/2` follows the `_fact_table_2()` pattern from Phase 3
(`torch_nn.py`). Introspect `torch.distributions` to build the registry:

```python
def _build_distribution_facts():
    dists = _ensure_torch().distributions
    facts = []
    for name in dir(dists):
        cls = getattr(dists, name)
        if isinstance(cls, type) and issubclass(cls, dists.Distribution):
            if name[0].isupper() and not name.startswith('_'):
                facts.append((name, cls))
    return facts
```

Uses original PyTorch names (`"Normal"`, `"Bernoulli"`, `"Categorical"`).

`make_distribution/3` constructs a distribution object from name + params dict:

```python
# make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, DIST)
def _make_dist(name, params):
    cls = _lookup_dist(name)
    return cls(**params)
```

Property predicates (`mean/2`, `variance/2`, etc.) follow the `_property_2()`
pattern from Phase 1.

---

## Example Usage

```clausal
-import_from(py.torch_distributions, [distribution, make_distribution,
    sample, log_prob, entropy, mean, variance, cdf, icdf])
-import_from(py.torch, [tensor, shape, tensor_list])

# List all available distributions
Test("enumerate distributions") <- (
    findall(N, distribution(N, _), NS),
    in_("Normal", NS),
    in_("Bernoulli", NS),
    in_("Categorical", NS)
)

# Create and query a normal distribution
Test("normal distribution mean") <- (
    make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
    mean(D, M),
    tensor_list(M, 0.0)
)

# Sample from distribution
Test("sample shape") <- (
    make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
    sample(D, [100], S),
    shape(S, [100])
)

# cdf/icdf are inverses
Test("cdf icdf roundtrip") <- (
    make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
    tensor([0.5], V),
    cdf(D, V, P),
    icdf(D, P, V2),
    allclose(V, V2)
)

# Log probability
Test("log_prob") <- (
    make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D),
    tensor([0.0], V),
    log_prob(D, V, LP),
    # log(1/sqrt(2*pi)) ≈ -0.9189
    tensor_list(LP, LPV),
    LPV < -0.9,
    LPV > -0.95
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_distributions_tests.clausal`):
- Distribution registry enumeration
- Construction of Normal, Bernoulli, Categorical, Uniform, Poisson
- Property queries: mean, variance, stddev, entropy
- Sampling with shape verification
- `log_prob` with known values
- `cdf`/`icdf` bijective roundtrip
- Invalid params fail gracefully

---

## Docs

Create `docs/torch_distributions.md` — registry, construction, properties,
sampling, `cdf`/`icdf` bijection.

---

## Issues

### 1. List-to-tensor conversion in `make_distribution` params

Distribution constructors (e.g. `Categorical`) require tensor arguments,
but Clausal dict literals produce plain Python lists for array-like values.
`_make_distribution` now auto-converts list values in the params dict to
tensors via `torch.tensor(v)`.

### 2. Separate module file — no `_pure()` reuse

`torch_distributions.py` is a new file (`clausal/modules/py/torch_distributions.py`)
rather than being added to `torch.py`. The `_pure()`, `_property_2()`,
`_deep_deref()`, and `_fact_table_2()` helpers were duplicated locally
(small, self-contained closures). Imports `_ensure_torch`, `_th`, and
`_deep_deref` from `torch.py`; duplicates the others to keep the module
self-contained like `torch_nn.py`.

### 3. No handle/freeze pattern needed

Unlike `scipy_stats.py` which uses a handle registry for frozen
distributions, `torch.distributions` objects are lightweight and
stateless (no file handles, no accumulated state). Distribution objects
are passed directly as Clausal terms — no handle allocation needed.
