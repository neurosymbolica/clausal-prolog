# Phase 2 — PRNG Keys and Randomness

JAX's most Clausal-friendly corner. Every sample requires a key; every
consumed key produces a new one. This is state threading the library
does itself — no adaptation required.

**File to create:** `clausal/modules/py/jax_random.py`

**Depends on:** Phase 1 — `clausal/modules/py/jax.py` with
`_ensure_jax()`, `_jnp_mod()`, `_pure()`, `_property_2()`, `_bidir_2()`,
and exported dtype constants.

---

## Predicates

### Key primitives

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `key` | `/2` | `(+SEED, -K)` | no | Create a typed-key `PRNGKey` from an integer seed |
| `split_key` | `/2` | `(+K, -KEYS)` | no | Split into 2 subkeys (list of length 2) |
| `split_key` | `/3` | `(+K, +N, -KEYS)` | no | Split into N subkeys |
| `fold_in` | `/3` | `(+K, +DATA, -K2)` | no | Fold an integer into a key |
| `key_bytes` | `/2` | `(+K, -BYTES)`, `(-K, +BYTES)` | yes | Key ↔ raw bytes (`jr.key_data` / `jr.wrap_key_data`) |

### Samplers (state-threaded, all Tier 1 pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `normal` | `/3, /4` | `(+K, +SHAPE, -A)`, `(+K, +SHAPE, +OPTS, -A)` | Standard normal |
| `uniform` | `/3, /4, /5` | `(+K, +SHAPE, -A)`, `(+K, +SHAPE, +OPTS, -A)`, `(+K, +SHAPE, +MIN, +MAX, -A)` | Uniform |
| `bernoulli` | `/3, /4` | `(+K, +P, -A)`, `(+K, +P, +SHAPE, -A)` | Bernoulli |
| `categorical` | `/3, /4` | `(+K, +LOGITS, -A)`, `(+K, +LOGITS, +AXIS, -A)` | Categorical |
| `poisson` | `/3, /4` | `(+K, +LAM, -A)`, `(+K, +LAM, +SHAPE, -A)` | Poisson |
| `gamma` | `/3, /4` | | Gamma |
| `beta` | `/4, /5` | `(+K, +A, +B, -A)`, `(+K, +A, +B, +SHAPE, -A)` | Beta |
| `exponential` | `/3, /4` | | Exponential |
| `dirichlet` | `/3, /4` | `(+K, +ALPHA, -A)` | Dirichlet |
| `multivariate_normal` | `/4, /5` | `(+K, +MEAN, +COV, -A)` | Multivariate normal |
| `permutation` | `/3` | `(+K, +X, -A2)` | Random permutation of an array or integer range |
| `choice` | `/4, /5` | `(+K, +X, +SHAPE, -A)`, `(+K, +X, +SHAPE, +OPTS, -A)` | Random choice |
| `randint` | `/5` | `(+K, +SHAPE, +MIN, +MAX, -A)` | Random integers |
| `truncated_normal` | `/5` | `(+K, +LOWER, +UPPER, +SHAPE, -A)` | Truncated normal |

### Sampler registry

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `sampler` | `/2` | `(+NAME, -FN)`, `(-NAME, -FN)`, `(-NAME, +FN)` | pure | yes | Enumerate samplers in `jax.random` |

Use the names JAX uses (`"normal"`, `"uniform"`, `"bernoulli"`). The
registry is introspected at first use.

---

## Context and Reference Patterns

### File structure — follow `torch_nn.py` minus the enumeration part

`torch_nn.py` is the closest precedent for a small focused wrapper
module that imports helpers from a sibling wrapper (`torch.py`).

```python
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _deep_deref, _pure, _fact_table_2
from clausal.modules.py.jax import _ensure_jax, _jx, _jnp_mod
```

### Key creation

```python
def _jr():
    _ensure_jax()
    import jax.random as jr
    return jr

key = _pred("key",
    (2, _pure(lambda seed: _jr().key(int(seed)))),
)
```

### Split — mind the N argument

`jr.split(k, n)` returns a `PRNGKeyArray` of shape `(n,)`. Clausal users
want a Python list of keys, not a key-array. Convert:

```python
def _split_2(k):
    sub = _jr().split(k, 2)
    return [sub[0], sub[1]]

def _split_3(k, n):
    sub = _jr().split(k, int(n))
    return [sub[i] for i in range(int(n))]

split_key = _pred("split_key",
    (2, _pure(_split_2)),
    (3, _pure(_split_3)),
)
```

The list form is crucial — it lets users pattern-match
`[K1, K2] = ...` in a Clausal clause body.

### `fold_in`

Straightforward:

```python
fold_in = _pred("fold_in",
    (3, _pure(lambda k, data: _jr().fold_in(k, int(data)))),
)
```

### Key ↔ bytes — bidirectional

`jr.key_data(k)` returns a `uint32[2]` array; `jr.wrap_key_data(bytes)`
reconstructs a typed key. The round-trip is strict:

```python
key_bytes = _pred("key_bytes",
    (2, _bidir_2(
        forward=lambda k: _jr().key_data(k),
        backward=lambda b: _jr().wrap_key_data(b),
    )),
)
```

Tests validate `key -> bytes -> key` roundtrip.

### Samplers

All follow `_pure()`:

```python
normal = _pred("normal",
    (3, _pure(lambda k, shape: _jr().normal(k, shape))),
    (4, _pure(lambda k, shape, opts: _jr().normal(k, shape, **opts))),
)

uniform = _pred("uniform",
    (3, _pure(lambda k, shape: _jr().uniform(k, shape))),
    (4, _pure(lambda k, shape, opts: _jr().uniform(k, shape, **opts))),
    (5, _pure(lambda k, shape, minval, maxval:
              _jr().uniform(k, shape, minval=minval, maxval=maxval))),
)
```

Note `jr.uniform` accepts `minval`/`maxval` keyword args. The 5-arity
variant is a convenience.

### Sampler registry

Same pattern as `activation/2` in `torch_nn.py`. Introspect `jax.random`
for top-level callable samplers:

```python
def _build_sampler_facts():
    jr = _jr()
    # Curated list — jax.random has many names, we only want samplers
    wanted = [
        "normal", "uniform", "bernoulli", "beta", "binomial",
        "categorical", "cauchy", "chisquare", "choice", "dirichlet",
        "exponential", "gamma", "geometric", "gumbel", "laplace",
        "logistic", "multivariate_normal", "normal", "pareto",
        "permutation", "poisson", "rademacher", "randint", "rayleigh",
        "t", "triangular", "truncated_normal", "uniform", "weibull_min",
    ]
    facts = []
    for name in wanted:
        fn = getattr(jr, name, None)
        if fn is not None and callable(fn):
            facts.append((name, fn))
    return facts

sampler = _pred("sampler",
    (2, _fact_table_2(_build_sampler_facts)),
)
```

Introspecting via whitelist is safer than scanning `dir(jr)` — JAX's
module has many internals (`PRNGKey`, `fold_in`, private helpers).

---

## Example Usage

```clausal
-import_from(py.jax, [shape, array_list, sum, mean, element_count])
-import_from(py.jax_random, [key, split_key, fold_in, key_bytes,
                              normal, uniform, bernoulli, categorical,
                              permutation, choice, randint, sampler])

Test("create key") <- (
    key(42, K),
    # Keys have shape () and dtype key<fry>
    shape(K, [])
)

Test("split into 2") <- (
    key(0, K0),
    split_key(K0, [K1, K2]),
    # K1 and K2 are new keys
    not(K1 == K2)
)

Test("split into N") <- (
    key(0, K0),
    split_key(K0, 3, KS),
    length(KS, 3)
)

Test("sample normal") <- (
    key(0, K),
    normal(K, [100], A),
    shape(A, [100])
)

Test("sample uniform with range") <- (
    key(1, K),
    uniform(K, [1000], 0.0, 10.0, A),
    # All values should be in [0, 10)
    max(A, MAX),
    array_list(MAX, MV),
    MV < 10.0,
    min(A, MIN),
    array_list(MIN, MN),
    MN >= 0.0
)

Test("fold_in produces new key") <- (
    key(0, K0),
    fold_in(K0, 5, K1),
    not(K0 == K1)
)

Test("key_bytes roundtrip") <- (
    key(42, K),
    key_bytes(K, B),
    key_bytes(K2, B),
    # K and K2 should produce the same samples
    normal(K, [3], A1),
    normal(K2, [3], A2),
    array_list(A1, L1),
    array_list(A2, L2),
    L1 == L2
)

Test("bernoulli") <- (
    key(0, K),
    bernoulli(K, 0.5, [100], A),
    shape(A, [100]),
    dtype(A, bool_)
)

Test("sampler registry: lookup by name") <- (
    sampler("normal", FN),
    NAME is ++(FN.__name__),
    NAME == "normal"
)

Test("sampler registry: enumerate") <- (
    findall(N, sampler(N, _), NS),
    in_("normal", NS),
    in_("uniform", NS),
    in_("bernoulli", NS)
)

# Showcase: state-threaded key splitting
init_two_layers(SEED, W1, W2) <- (
    key(SEED, K0),
    split_key(K0, 2, [K1, K2]),
    normal(K1, [784, 256], W1),
    normal(K2, [256, 10], W2)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_random_tests.clausal`):

- Key creation with various seeds (0, 42, large integer)
- `split_key/2` and `split_key/3` with different N
- `fold_in/3` produces a new key
- `key_bytes/2` roundtrip: `key -> bytes -> key` reproduces samples
- Every sampler with shape verification
- `sampler/2` registry: specific lookup, findall, reverse lookup
- Determinism: same key produces same samples (compare via `array_list`)

**Python unit tests** (if needed):
- `_build_sampler_facts` returns non-empty list with expected names
- `split_key` returns a Python list (not a key-array) so pattern
  matching works

---

## Docs

Create `docs/jax_random.md`:
- Overview: why JAX uses explicit keys, how this maps to state threading
- Key primitives with examples
- Samplers with argument explanations
- Registry usage
- Note: `PRNGKey` is immutable — backtracking is safe
- All examples backed by `.clausal` tests

---

## Issues

### Resolved during Phase 2 implementation

1. **Key dtype (`key<fry>`) — works in shape checks, skipped in tests.**
   Keys have `shape == ()` and a typed extended dtype. `shape(K, [])`
   works correctly. The wrapper does not attempt to expose a dtype
   constant for `key<fry>`; tests exercise keys behaviourally
   (sampling determinism) rather than asserting dtype equality.

2. **`jr.split` return type — subkeys are usable keys.**
   `jr.split(k, N)` returns a `PRNGKeyArray` of shape `(N,)`. Indexing
   with `sub[i]` yields a scalar key (shape `()`, dtype `key<fry>`)
   that samplers accept directly. `_split_2` / `_split_3` extract the
   subkeys into a Python list so `[K1, K2]` pattern matching in clause
   bodies works.

3. **`key_bytes` bijection — roundtrip verified behaviourally.**
   Tests sample from a key, bytes-roundtrip the key, sample again,
   and compare sample lists for equality. This avoids depending on
   JAX's internal byte layout.

4. **Deprecated `PRNGKey` constructor — not exposed.** The wrapper
   uses `jr.key` exclusively; the docs call out the distinction.

5. **`split_key/2` vs `/3` arity — no conflict.** Multi-arity
   predicates dispatch on argument count (confirmed against `torch.py`
   patterns).

6. **Comparing keys directly via Clausal `==` — avoided.**
   `K1 == K2` on two JAX arrays goes through element-wise equality; the
   semantics in Clausal's unification operator is not what most users
   would expect for "are these the same key?". Tests that need to
   establish distinctness do so by comparing *samples* drawn from the
   keys (robust and what a user actually cares about).

### New issues surfaced during implementation

7. **`_jr()` lazy-import lock.** The initial implementation of
   `_jr()` checked and set a module global without a lock — inconsistent
   with `_ensure_jax()` in `jax.py`. On free-threaded Python 3.13 two
   threads could race to import `jax.random`. Fixed in follow-up:
   `_jr()` now uses the same `threading.Lock` pattern as `_ensure_jax()`.

8. **Backtracking-safety was asserted but not tested.** The central
   Clausal-friendliness claim for Phase 2 — *"if a sampler branch
   fails, the pre-split key and sibling subkeys stay valid"* — was
   documented but not exercised. Added an integration test
   (`"backtracking leaves sibling keys valid"`) that consumes one
   subkey inside a deliberately-failing goal and confirms the sibling
   still produces expected samples.
