# jax_random — JAX PRNG and Sampling

JAX refuses to hide randomness in a global. Every sample takes an
explicit `PRNGKey`; splitting a key produces new keys; a key that has
been used has no lingering effect on the one it was split from. That
is *exactly* the discipline Clausal Prolog expects from stateful operations —
state-threaded, backtracking-safe, no hidden side effects.

If backtracking abandons a sample, the subkey that produced it is
abandoned too — the pre-split key is still valid and can be re-used.

## Import

```seam
-import_from(py.jax_random, [
    key, split_key, fold_in, key_bytes,
    normal, uniform, bernoulli, categorical,
    poisson, gamma, beta, exponential, dirichlet,
    multivariate_normal, permutation, choice,
    randint, truncated_normal,
    sampler
])
```

---

## Key primitives

### key

```seam
key(SEED, K)
```

Create a typed PRNG key from an integer seed. Uses `jax.random.key`
(the modern typed-key API — *not* the deprecated `PRNGKey`).

```seam
key(42, K)
```

### split_key

```seam
split_key(K, KEYS)          # KEYS is a 2-element list
split_key(K, N, KEYS)       # KEYS is an N-element list
```

Split a key. `split_key/2` produces a Python list of two subkeys —
pattern-match them directly:

```seam
key(0, K0),
split_key(K0, [K1, K2])
```

For N subkeys:

```seam
key(0, K0),
split_key(K0, 3, KS),
length(KS, 3)
```

### fold_in

```seam
fold_in(K, DATA, K2)
```

Fold an integer into a key, producing a new key. Useful for deriving
per-example subkeys inside a loop without repeated splitting.

### key_bytes

```seam
key_bytes(K, BYTES)
```

Bijective: typed key ↔ `uint32[2]` byte array.

- `(+K, -B)` — extract the raw bytes via `jr.key_data`.
- `(-K, +B)` — reconstruct the key via `jr.wrap_key_data`.

The roundtrip preserves sampling behaviour — not necessarily
byte-for-byte equality of the key objects, but sampling from the
roundtripped key produces the same sequence as sampling from the
original.

---

## Samplers

Every sampler takes a key as its first argument. The key is consumed —
re-use the same key only if you want the same sample. Typical pattern:
split once, pass each subkey to one consumer.

| Predicate | Signature |
|---|---|
| `normal` | `(K, SHAPE, A)` or `(K, SHAPE, OPTS, A)` |
| `uniform` | `(K, SHAPE, A)`, `(K, SHAPE, OPTS, A)`, or `(K, SHAPE, MIN, MAX, A)` |
| `bernoulli` | `(K, P, A)` or `(K, P, SHAPE, A)` — result dtype is `bool_` |
| `categorical` | `(K, LOGITS, A)` or `(K, LOGITS, AXIS, A)` |
| `poisson` | `(K, LAM, A)` or `(K, LAM, SHAPE, A)` |
| `gamma` | `(K, A_PARAM, A)` or `(K, A_PARAM, SHAPE, A)` |
| `beta` | `(K, A_PARAM, B_PARAM, A)` or `(K, A_PARAM, B_PARAM, SHAPE, A)` |
| `exponential` | `(K, A)` or `(K, SHAPE, A)` |
| `dirichlet` | `(K, ALPHA, A)` or `(K, ALPHA, SHAPE, A)` |
| `multivariate_normal` | `(K, MEAN, COV, A)` or `(K, MEAN, COV, SHAPE, A)` |
| `permutation` | `(K, X, A)` — X is an integer (range) or array |
| `choice` | `(K, X, SHAPE, A)` or `(K, X, SHAPE, OPTS, A)` |
| `randint` | `(K, SHAPE, MIN, MAX, A)` — integers in `[MIN, MAX)` |
| `truncated_normal` | `(K, LOWER, UPPER, SHAPE, A)` |

```seam
key(0, K),
uniform(K, [1000], 0.0, 10.0, A)
```

```seam
key(0, K),
bernoulli(K, 0.5, [100], A),
dtype(A, bool_)
```

---

## Sampler registry

```seam
sampler(NAME, FN)
```

Fact table over `jax.random` samplers. Modes:

- `(+NAME, -FN)` — look up a sampler function by its JAX name
- `(-NAME, -FN)` — enumerate every available sampler
- `(-NAME, +FN)` — reverse lookup

```seam
# Enumerate every sampler JAX exposes
findall(N, sampler(N, _), NAMES)
```

Built from a curated whitelist of JAX sampler names — avoids catching
internals like `PRNGKey` or `key_data`.

---

## State-threading example

A parameter-initialisation helper that splits one key into two and
draws independent weight matrices:

```seam
init_two_layers(SEED, W1, W2) <- (
    key(SEED, K0),
    split_key(K0, 2, [K1, K2]),
    normal(K1, [784, 256], W1),
    normal(K2, [256, 10], W2)
)
```

`K1` and `K2` are independent — abandoning `W2` via backtracking
doesn't affect `W1` because nothing was mutated.

---

## Gotchas

- **Same seed → same samples.** JAX is deterministic given a key. If
  you want different samples in two branches, you must split or fold
  first. Re-using a key is a bug, not a feature.
- **Keys are first-class `jax.Array`s**, with shape `()` and dtype
  `key<fry>`. They have all the properties of any JAX array — `shape`,
  `dtype`, `device` all work on them.
- **Comparing two keys directly with `==`** goes through JAX's
  element-wise comparison. To check key distinctness, compare the
  samples they produce (or their bytes via `key_bytes`).
- **`PRNGKey` vs `key`.** JAX's older `jr.PRNGKey(seed)` API returns a
  `uint32[2]` array instead of a typed key. The wrapper uses the
  modern `jr.key(seed)` exclusively.
- **`float64` PRNG samples** require enabling x64 (see
  [jax.md](jax.md#gotcha-float64-is-silently-truncated-by-default)).

See [the Phase 2 implementation plan](../implementation_plans/jax/phase2_random.md)
for design notes.
