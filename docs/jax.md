# jax — JAX Array Operations

Provides pure array operations from [JAX](https://docs.jax.dev) as
[importable](import.md) clausal predicates. Phase 1 covers array
creation, properties, math, shape operations, and bijective conversions.

All Phase 1 predicates are **pure** — arrays in, arrays out, no hidden
state. JAX itself is functional, so the wrapper is a thin shim.

## Import

```clausal
-import_from(py.jax, [
    array, zeros, ones, full, arange, linspace, eye,
    shape, dtype, device, dim, element_count,
    matmul, dot, add, mul, sum, mean, max, min, clip, abs,
    reshape, squeeze, expand_dims, transpose,
    swapaxes, moveaxis, concatenate, stack, broadcast_to, astype,
    at_set, at_add, at_mul, at_min, at_max, at_get,
    jax_numpy, array_list,
    det, slogdet, inv, solve, svd,
    eig, eigh, eigvals, eigvalsh,
    cholesky, qr, lstsq,
    norm, matrix_rank, pinv, matrix_power, cross,
    fft_transform, real_fft,
    fft_transform_2d, fft_transform_nd, fft_shift,
    fft_frequencies, real_fft_frequencies,
    float32, float64, int32, newaxis
])
```

Dtype constants (`float32`, `int32`, …) and math/indexing constants
(`pi`, `inf`, `nan`, `newaxis`) are exported directly — no `++()`
escape needed.

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 1 — pure | Creation, math, shape ops, `.at` updates, linalg | Array in, array out |
| 1 — pure (multi-mode) | `shape`, `dtype`, `device` | Query or check |
| 1 — pure (bijective) | `jax_numpy`, `array_list`, FFT pairs | Bidirectional conversion |

---

## Gotcha — `float64` is silently truncated by default

JAX disables 64-bit floats unless you ask for them. With stock config:

```clausal
zeros([2, 3], {"dtype": float64}, A),
dtype(A, float64)   # FAILS — A was silently downcast to float32
```

The wrapper does **not** auto-enable x64 on import, because flipping it
also changes the *default* float dtype to `float64` globally and would
surprise other JAX users sharing the process. Enable it yourself before
any JAX work:

```python
import jax
jax.config.update("jax_enable_x64", True)
```

Or set `JAX_ENABLE_X64=1` in the environment before Python starts. See
[JAX's gotcha
docs](https://docs.jax.dev/en/latest/notebooks/Common_Gotchas_in_JAX.html#double-64bit-precision)
for the full story.

---

## Array Creation

### array

```clausal
array(DATA, A)
array(DATA, OPTS, A)
```

Create an array from a Python list or nested list. `OPTS` is a dict for
`dtype` kwargs.

```clausal
array([1.0, 2.0, 3.0], A)                    # 1-D
array([[1.0, 2.0], [3.0, 4.0]], A)           # 2-D
```

### zeros, ones

```clausal
zeros(SHAPE, A)
zeros(SHAPE, OPTS, A)
ones(SHAPE, A)
ones(SHAPE, OPTS, A)
```

Create zero/one-filled arrays. Pass `{"dtype": int32}` etc. via `OPTS`.

```clausal
zeros([3, 4], A)
zeros([2, 3], {"dtype": int32}, A)
```

### full

```clausal
full(SHAPE, VALUE, A)
full(SHAPE, VALUE, OPTS, A)
```

Create an array filled with a scalar value.

### arange

```clausal
arange(END, A)
arange(START, END, A)
arange(START, END, STEP, A)
arange(START, END, STEP, OPTS, A)
```

Integer-range array, like Python's `range`.

### linspace

```clausal
linspace(START, END, STEPS, A)
linspace(START, END, STEPS, OPTS, A)
```

`STEPS` evenly spaced values from `START` to `END` (both inclusive).

### eye

```clausal
eye(N, A)
eye(N, M, A)
eye(N, M, OPTS, A)
```

Identity matrix, square (`N` × `N`) or rectangular (`N` × `M`).

---

## Array Properties (Multi-Mode)

These support two modes:

- **Query** `(+A, -V)` — second arg unbound, returns the property.
- **Check** `(+A, +V)` — both bound, succeeds iff the property matches.

### shape

```clausal
shape(A, SHAPE)
```

Shape is a Python list of ints.

```clausal
zeros([3, 4], A), shape(A, S)           # S = [3, 4]
zeros([3, 4], A), shape(A, [3, 4])      # succeeds
zeros([3, 4], A), not shape(A, [5, 6])  # check mode fails
```

### dtype

```clausal
dtype(A, D)
```

Compare against exported dtype constants (`float32`, `int32`, etc.):

```clausal
zeros([2], A), dtype(A, float32)  # succeeds on default config
```

### device

```clausal
device(A, D)
```

`D` is a string like `"cpu:0"` or `"gpu:0"`. Strings — not `Device`
objects — so unification and pattern matching work naturally.

### dim, element_count

```clausal
dim(A, N)             # number of axes (ndim)
element_count(A, N)   # total number of elements (size)
```

---

## Array Math

| Predicate | Semantics |
|---|---|
| `matmul(A, B, C)` | Matrix multiply |
| `dot(A, B, C)` | Dot product |
| `add(A, B, C)` | Element-wise add |
| `mul(A, B, C)` | Element-wise multiply |
| `sum(A, S)` / `sum(A, AXIS, S)` | Sum, optionally along an axis |
| `mean(A, M)` / `mean(A, AXIS, M)` | Mean |
| `max(A, M)` / `max(A, AXIS, M)` | Max |
| `min(A, M)` / `min(A, AXIS, M)` | Min |
| `clip(A, MIN, MAX, A2)` | Clamp to `[MIN, MAX]` |
| `abs(A, A2)` | Absolute value |

```clausal
array([[1.0, 2.0], [3.0, 4.0]], T),
sum(T, 0, S)                        # S = [4.0, 6.0]
```

---

## Shape Operations

| Predicate | Semantics |
|---|---|
| `reshape(A, SHAPE, A2)` | Reshape |
| `squeeze(A, A2)` / `squeeze(A, AXIS, A2)` | Drop size-1 axes |
| `expand_dims(A, AXIS, A2)` | Insert a size-1 axis |
| `transpose(A, A2)` / `transpose(A, AXES, A2)` | Transpose (reverse or permute axes) |
| `swapaxes(A, I, J, A2)` | Swap two axes |
| `moveaxis(A, SRC, DEST, A2)` | Move one axis |
| `concatenate(ARRS, AXIS, A)` | Concat along existing axis |
| `stack(ARRS, AXIS, A)` | Stack along a new axis |
| `broadcast_to(A, SHAPE, A2)` | Broadcast to a target shape |
| `astype(A, DTYPE, A2)` | Cast to a new dtype |

`squeeze` and `expand_dims` are inverses at a given axis:

```clausal
zeros([3, 1, 4], A),
squeeze(A, 1, A2), shape(A2, [3, 4]),
expand_dims(A2, 1, A3), shape(A3, [3, 1, 4])
```

`transpose` is self-inverse on 2-D arrays (no-axes form).

---

## Functional Updates (`.at`)

JAX's `.at[idx].<op>(val)` idiom returns a **new array** — the original
is untouched. That purity is exactly what Clausal backtracking needs:
the PyTorch equivalent (`tensor[idx] = val`) mutates in place and so
can't survive a backtrack. Every `at_*` predicate below is Tier 1 pure.

```clausal
arange(0, 6, A),
at_set(A, 2, 99, A2)      # A2 = [0, 1, 99, 3, 4, 5], A is unchanged
```

| Predicate | Semantics |
|---|---|
| `at_set(A, IDX, VAL, A2)` | `A.at[IDX].set(VAL)` |
| `at_add(A, IDX, VAL, A2)` | `A.at[IDX].add(VAL)` |
| `at_mul(A, IDX, VAL, A2)` | `A.at[IDX].mul(VAL)` |
| `at_min(A, IDX, VAL, A2)` | `A.at[IDX].min(VAL)` (element-wise min against `VAL`) |
| `at_max(A, IDX, VAL, A2)` | `A.at[IDX].max(VAL)` |
| `at_get(A, IDX, VAL)` | `A.at[IDX].get()` — read the value at `IDX` |

### Index types

`IDX` can be:

- **A scalar integer** — `at_set(A, 2, 99, A2)`. For a 2-D array this
  targets a whole row (`a[0]`-style broadcast).
- **A tuple of integers** — multi-dim scalar indexing:
  `at_set(M, (1, 2), 99, M2)` addresses the single cell at row 1,
  column 2. Tuple literals in `.clausal` compile to Python tuples.
  Tuple elements may be bound Clausal variables — `_deep_deref` walks
  into tuples to resolve them.
- **A JAX array of indices** — fancy indexing. Build it with `array/2`:

  ```clausal
  array([10, 20, 30, 40, 50], A),
  array([0, 2, 4], IDX),
  at_set(A, IDX, 0, A2)           # A2 = [0, 20, 0, 40, 0]
  ```

**Plain Python lists are not valid indices.** Modern JAX (0.4+) raises
`TypeError` on `arr.at[[0, 2, 4]]` and tells you to wrap in
`jnp.array`. The `at_*` predicates surface this as predicate failure:

```clausal
array([10, 20, 30], A),
not at_set(A, [0, 2], 0, _A2)     # succeeds — list index is rejected
```

Slice indices (`a.at[1:3]`) aren't expressible as Clausal terms today —
use `lax.dynamic_update_slice` via `++()` if you need them.

### Out-of-bounds indices are silently clipped

JAX's default index mode is `promise_in_bounds`: out-of-range indices
are dropped for updates and clipped for reads, with no error. Make sure
your indices are valid or switch modes at the JAX level before calling
these predicates. See [JAX indexing docs](https://docs.jax.dev/en/latest/_autosummary/jax.numpy.ndarray.at.html)
for the full mode list.

### Contrast with PyTorch

| Library | Update idiom | Pure? |
|---|---|---|
| PyTorch | `tensor[idx] = val` | No — mutates, breaks backtracking |
| JAX     | `arr.at[idx].set(val)` | Yes — returns a new array |

The PyTorch wrapper works around its mutation by exposing `scatter` and
`gather`. JAX has `.at` built in, so the wrapper just passes it through.

---

## Conversions (Bijective)

Both directions of each conversion run through a single predicate — pass
the known side as the bound argument:

### jax_numpy

```clausal
jax_numpy(JAX_ARR, NUMPY_ARR)
```

- `(+A, -N)` — extract a `numpy.ndarray` view.
- `(-A, +N)` — build a `jax.Array` from a numpy array.

### array_list

```clausal
array_list(A, L)
```

- `(+A, -L)` — nested Python list via `.tolist()`.
- `(-A, +L)` — build a `jax.Array` from a nested list.

```clausal
array_list(A, [[1.0, 2.0], [3.0, 4.0]]),
shape(A, [2, 2])
```

---

## Linear Algebra

All from `jax.numpy.linalg`, exposed as pure predicates. Decompositions
that return a `NamedTuple` in JAX (`svd`, `qr`, `eigh`, `slogdet`, …)
are returned as plain tuples so they decompose in Clausal with `is`:

```clausal
svd(A, RESULT),
RESULT is (U, S, VH)
```

### Scalar and simple results

| Predicate | Returns | Semantics |
|---|---|---|
| `det(A, D)` | scalar array | Determinant |
| `slogdet(A, (SIGN, LOGDET))` | 2-tuple | Sign and `log(abs(det(A)))` |
| `inv(A, B)` | matrix | Matrix inverse |
| `solve(A, B, X)` | array | Solve `A @ X == B` |
| `matrix_rank(A, R)` | int | Rank (Python int, not array) |
| `pinv(A, B)` | matrix | Moore–Penrose pseudoinverse |
| `matrix_power(A, N, B)` | matrix | `A` to integer power `N` |
| `cross(A, B, C)` | vector | Cross product (3-vectors) |

### Decompositions

| Predicate | Tuple shape | Notes |
|---|---|---|
| `svd(A, (U, S, VH))` | `(M,M), (K,), (N,N)` for `full_matrices=True` (default) | `K = min(M, N)` |
| `eig(A, (VAL, VEC))` | complex arrays | Use for non-symmetric matrices |
| `eigh(A, (VAL, VEC))` | real arrays | Symmetric / Hermitian inputs |
| `eigvals(A, VAL)` | complex array | Values only |
| `eigvalsh(A, VAL)` | real array | Hermitian values only |
| `cholesky(A, L)` | lower-triangular | `A = L @ L.T`; `A` must be positive-definite |
| `qr(A, (Q, R))` | reduced by default | For `(M, N)` input with `M >= N`: `Q: (M, N)`, `R: (N, N)` |
| `lstsq(A, B, (X, RES, RANK, S))` | 4-tuple | Least-squares solution |

### Norm

```clausal
norm(A, N)
norm(A, ORD, N)
```

`ORD` accepts JAX's standard values: an integer (`1`, `2`, `-1`, …),
the string `'fro'` for the Frobenius norm, or `inf`/`-inf` for the
infinity norms. No arg = Frobenius for matrices, 2-norm for vectors.

### Example

```clausal
Test("solve diagonal system") <- (
    array([[2.0, 0.0], [0.0, 4.0]], A),
    array([6.0, 8.0], B),
    solve(A, B, X)            # X ≈ [3.0, 2.0]
)
```

### Numerical notes

- **JAX defaults to `float32`.** Round-trip equalities like
  `inv(inv(A)) == A` drift at the 1e-7 level. Tests use range checks
  (`V > 1.99, V < 2.01`) rather than exact equality.
- **Singular matrices.** `inv` of a singular matrix does **not** raise
  — JAX returns an array of `inf`/`nan` and the predicate succeeds.
  Guard with `matrix_rank/2` if you need a hard check.
- **`eig` / `eigvals` return complex arrays** (`complex64`), even when
  eigenvalues happen to be real. For symmetric / Hermitian matrices use
  `eigh` / `eigvalsh` — those return real arrays. To compare `eig`
  output against real expected values, pull out the real part in a
  `++()` escape:

  ```clausal
  eigvals(A, E),
  E_REAL is ++(E.real),
  at_get(E_REAL, 0, E0), array_list(E0, V0)
  ```

  Note too that `eig` / `eigvals` do not guarantee an order on the
  eigenvalues — tests that need determinism should compare sums /
  products rather than positional values.
- **`matrix_power` with negative `N`** requires invertibility. On a
  singular input it returns non-finite values rather than raising.
- **`lstsq` passes `rcond=None`** to silence JAX's future-default
  warning.

See the [Phase 4 implementation plan](../implementation_plans/jax/phase4_linalg.md)
for the predicate catalogue and design notes.

---

## FFT

`jax.numpy.fft` is all pure. Every forward / inverse pair collapses into
**one multi-mode predicate**: bind the signal to run the forward
transform, bind the frequencies to run the inverse.

```clausal
fft_transform(T, F)                 # if T bound, F = fft(T)
                                    # if F bound, T = ifft(F)
```

### Bijective pairs

| Predicate | Forward | Inverse | Notes |
|---|---|---|---|
| `fft_transform/2,/3` | `fft` | `ifft` | `/3` takes an `axis` (int) middle arg |
| `real_fft/2,/3` | `rfft` | `irfft` | Bijective for **even** N (see below); `/3` takes an `axis` |
| `fft_transform_2d/2,/3` | `fft2` | `ifft2` | `/3` takes an `axes` list; default `(-2, -1)` |
| `fft_transform_nd/2,/3` | `fftn` | `ifftn` | `/3` takes an `axes` list; default = all axes |
| `fft_shift/2,/3` | `fftshift` | `ifftshift` | `/3` takes an `axes` list; self-inverse for even N |

Axes for the `/3` forms are a Clausal list of ints, e.g.
`fft_shift(T, [1], S)` shifts only axis 1.

### Non-bijective helpers

| Predicate | JAX call | Notes |
|---|---|---|
| `fft_frequencies(N, F)` / `fft_frequencies(N, D, F)` | `fftfreq(N, d=D)` | Default `D=1` |
| `real_fft_frequencies(N, F)` / `/3` | `rfftfreq(N, d=D)` | `N // 2 + 1` values |

### Example

```clausal
Test("roundtrip") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    fft_transform(T, F),            # forward
    fft_transform(T2, F)            # backward — T2 ≈ T
)

Test("frequencies of length-4 signal") <- (
    fft_frequencies(4, F),
    array_list(F, [0.0, 0.25, -0.5, -0.25])
)
```

### Caveats

- **`fft_transform` output is complex.** `fft` of a real `float32` input
  returns `complex64`; on `float64` it returns `complex128`. Round-trip
  via `ifft` preserves complex dtype — the recovered signal has tiny
  imaginary parts due to float noise. Compare values via `.real`:

  ```clausal
  at_get(T2, 0, V), array_list(V, C), V_REAL is ++(C.real)
  ```

- **`real_fft` needs even N for strict bijection.** `rfft` of a
  length-N real signal produces `N // 2 + 1` complex values. `irfft`
  defaults to `2 * (K - 1)` — correct for even N, loses the trailing
  sample for odd N. If you need odd N round-trips, pass the original
  length explicitly via `lax`-level APIs with `++()`.

- **`fft_shift` is only self-inverse for even N.** For odd N,
  `fftshift` and `ifftshift` differ by one element — the `_bidir_2`
  helper still calls the correct inverse in each direction.

See the [Phase 5 implementation plan](../implementation_plans/jax/phase5_fft.md)
for the predicate catalogue and design notes.

---

## Why JAX wrapping is simple

Unlike PyTorch, JAX has no in-place operations, no `requires_grad`
attribute on arrays, and no hidden optimizer state. Every operation
takes arrays in and returns new arrays out — so every Phase 1 predicate
is Tier 1 (pure). State threading (PRNG keys, device placement) is
reserved for later phases.

See [the Phase 1 implementation plan](../implementation_plans/jax/phase1_array_core.md)
for the full predicate catalogue and design notes.
