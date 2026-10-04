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
    swapaxes, moveaxis, concatenate, stacked, broadcast_to, astype,
    at_set, at_add, at_mul, at_min, at_max, at_get,
    jax_numpy, array_list,
    det, slogdet, inv, solve, svd,
    eig, eigh, eigvals, eigvalsh,
    cholesky, qr, lstsq,
    norm, matrix_rank, pinv, matrix_power, cross,
    fft_transform, real_fft,
    fft_transform_2d, fft_transform_nd, fft_shift,
    fft_frequencies, real_fft_frequencies,
    eq, ne, gt, lt, ge, le, equal, array_equal, allclose,
    logical_and, logical_or, logical_not, logical_xor,
    any, all,
    where, masked_select, take, put_along_axis,
    einsum, logarithm, sine, cosine, tangent,
    sqrt, pow, atan2, sinh, cosh, tanh,
    sigmoid, softmax, log_softmax, logsumexp,
    floor, ceil, round, sign, cumsum, cumprod,
    partition, array_split, hsplit, vsplit, dsplit,
    tile, repeat, flip, roll, pad,
    zeros_like, ones_like, full_like, empty,
    logspace, geomspace, meshgrid, diag, identity,
    sub, div, floor_div, mod, neg, reciprocal,
    median, std, var, percentile, quantile, cov, corrcoef,
    argmin, argmax, sort, argsort, topk, nonzero, unique, argpartition,
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

## Gotcha — bidirectional check mode is bit-exact

Every bidirectional predicate in the wrapper (`logarithm`, `sine`,
`cosine`, `tangent`, `fft_transform`, `real_fft`, `fft_transform_2d`,
`fft_transform_nd`, `fft_shift`, `jax_numpy`, `array_list`, `stacked`,
`partition`, `flip`, …) supports a check mode: bind both sides and the
predicate runs the forward direction, then compares the computed output
to the supplied argument.

The comparison is **bit-exact**. For floating-point round-trips that's
almost never what you want — `arcsin(sin(0.5))` differs from `0.5` at
the last-ULP level, `ifft(fft(x))` picks up imaginary float noise, etc.
So `sine(0.5, 0.479426)` or `fft_transform(X, Y)` with a numerically
correct `Y` will *fail* the check.

Use `allclose/2` or `allclose/4` when you want a tolerant check:

```clausal
# Instead of relying on check mode —
array(0.5, ANGLE), sine(ANGLE, 0.479426)   # FAILS: last-ULP drift

# Compute forward, then compare with tolerance —
array(0.5, ANGLE), sine(ANGLE, VALUE),
array(0.479426, EXPECTED),
allclose(VALUE, EXPECTED, 0.0001, 0.0)
```

Exact check mode still works for integer or zero-exact round-trips
(`logarithm(1.0, 0.0)` passes — `log(1) == 0` exactly).

---

## Gotcha — predicates that shadow Python builtins

`-import_from(py.jax, [...])` brings predicate objects into the
importing clause's namespace *by name*. Eight of them have the same
name as a Python builtin:

| Imported | Shadows | Semantics |
|---|---|---|
| `abs` | `builtins.abs` | Element-wise `jnp.abs` |
| `all` | `builtins.all` | Reduce-to-bool (`jnp.all`) — a **check** predicate, not a value producer |
| `any` | `builtins.any` | Reduce-to-bool (`jnp.any`) — same |
| `max` | `builtins.max` | Reduction `jnp.max(a)` / `jnp.max(a, axis=…)` |
| `min` | `builtins.min` | Reduction `jnp.min(a)` / `jnp.min(a, axis=…)` |
| `pow` | `builtins.pow` | Element-wise `jnp.power` |
| `round` | `builtins.round` | Element-wise rounding (half-to-even — NumPy spec) |
| `sum` | `builtins.sum` | Reduction `jnp.sum(a)` / `jnp.sum(a, axis=…)` |

Only names you **import explicitly** are shadowed — Python code using
`py.jax` as a module (e.g. `from clausal.modules.py import jax;
jax.sum(...)`) is unaffected, and clauses that don't `-import_from`
these names keep the Python builtin.

### Where the trap bites

```clausal
-import_from(py.jax, [sum])

test("fragile") <- (
    sum([1, 2, 3], S)        # py.jax.sum: treats [1,2,3] as a 1-D
                             # array literal and reduces. S is a JAX
                             # scalar array (6), *not* the Python int 6.
    S == 6                   # fails: JAX scalar != Python int
)
```

Two distinct surprises:

1. **Input coercion.** JAX will happily arrays-ify a Python list, so
   the call doesn't error — it just goes through a different code path
   than you intended.
2. **Result type.** Reductions return JAX *arrays* (even if 0-D), not
   Python scalars. Unify with `array_list(S, 6)` or compare via
   `allclose/2`, not direct `==`.

### Mixing with the Python builtin

If you genuinely need Python's `sum` / `max` / etc. in the same clause:

- Don't import the JAX name: `-import_from(py.jax, [mean, std])` and
  call `++(sum(list))` when you want Python's reduction.
- Or escape explicitly: `S is ++(sum([1, 2, 3]))`.

The shadowing is the whole point of `-import_from` — not a bug — but
worth knowing about when you write a clause that thinks it's acting on
a Python list but ends up in JAX.

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

### zeros_like, ones_like, full_like

```clausal
zeros_like(A, R)
zeros_like(A, OPTS, R)
ones_like(A, R)
ones_like(A, OPTS, R)
full_like(A, VALUE, R)
full_like(A, VALUE, OPTS, R)
```

Construct a new array matching the shape *and* dtype of `A`. `full_like`
takes a scalar fill value. The `OPTS` arity passes kwargs through to
`jnp.*_like` — use `{"dtype": …}` to keep `A`'s shape but override the
dtype, or `{"shape": …}` to keep `A`'s dtype with a different shape.

```clausal
ones([3, 4], A), zeros_like(A, Z)        # Z has shape [3, 4], dtype float32
ones([2], {"dtype": int32}, A),
  zeros_like(A, Z), dtype(Z, int32)      # dtype is preserved
ones([2], A),
  zeros_like(A, {"dtype": int32}, Z),
  dtype(Z, int32)                        # dtype overridden
```

### empty

```clausal
empty(SHAPE, A)
empty(SHAPE, OPTS, A)
```

Allocate an array of the given shape. **Caveat:** JAX cannot expose
uninitialised accelerator memory, so `empty` returns zeros. The
predicate exists for API symmetry with NumPy and PyTorch — prefer
`zeros` when the zero-fill matters semantically.

### logspace, geomspace

```clausal
logspace(START, END, STEPS, A)
logspace(START, END, STEPS, OPTS, A)
geomspace(START, END, STEPS, A)
geomspace(START, END, STEPS, OPTS, A)
```

`logspace` returns values evenly spaced on a **log scale** between
`base**START` and `base**END` (default base = 10). `geomspace` returns
`STEPS` values in a **geometric progression** from `START` to `END`.

```clausal
logspace(0.0, 2.0, 3, A)                 # [1.0, 10.0, 100.0]
logspace(0.0, 3.0, 4, {"base": 2.0}, A)  # [1.0, 2.0, 4.0, 8.0]
geomspace(1.0, 1000.0, 4, A)             # [1.0, 10.0, 100.0, 1000.0]
```

### meshgrid

```clausal
meshgrid(ARRS, MESH)
meshgrid(ARRS, OPTS, MESH)
```

Build coordinate arrays from 1-D input vectors. `ARRS` is a list of
input arrays, `MESH` is a list of output coordinate arrays (one per
input). Pass `{"indexing": "ij"}` for matrix-layout axes (default is
`"xy"`).

```clausal
array([1.0, 2.0, 3.0], X),
array([4.0, 5.0], Y),
meshgrid([X, Y], [XX, YY]),
shape(XX, [2, 3])                        # xy default: Y broadcast first

meshgrid([X, Y], {"indexing": "ij"}, [XX, YY]),
shape(XX, [3, 2])                        # ij: X broadcast first
```

### diag

```clausal
diag(A, R)
diag(A, K, R)
```

Input-polymorphic — **not** bijective:

- 1-D `A` → 2-D diagonal matrix with `A` on the main diagonal.
- 2-D `A` → 1-D vector of the main diagonal of `A`.

`K` offsets the diagonal (`K > 0` picks a super-diagonal; `K < 0` a
sub-diagonal). You bind the input; the output direction follows the
input's dimensionality. Use `array_list` in tests rather than trying
to round-trip through a bound output.

```clausal
array([1, 2, 3], V), diag(V, M), shape(M, [3, 3])   # create
array([[1, 2], [3, 4]], M), diag(M, V)              # extract → [1, 4]
array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], M),
  diag(M, 1, V)                                      # → [2, 6]
```

### identity

```clausal
identity(N, A)
identity(N, OPTS, A)
```

Square identity matrix of side `N`. Equivalent to `eye(N, A)`; exposed
for NumPy/JAX naming symmetry.

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

`D` is the device name (cpu:0, gpu:0) as an ATOM, a symbolic name; a bound `D`
may be the atom or the string. Not a `Device` object, so unification works.

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
| `sub(A, B, C)` | Element-wise subtract |
| `mul(A, B, C)` | Element-wise multiply |
| `div(A, B, C)` | Element-wise true divide (integer operands promote to float) |
| `floor_div(A, B, C)` | Element-wise floor divide |
| `mod(A, B, C)` | Element-wise remainder |
| `neg(A, R)` | Negate |
| `reciprocal(A, R)` | `1 / A` |
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
| `stacked(LS, AXIS, A)` | Bidirectional: `A` is `LS` stacked along `AXIS`. Forward `jnp.stack`; backward `jnp.unstack` (requires JAX ≥ 0.4.28) |
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

## Shape Extras

Additional shape-manipulating predicates beyond the core set. All are
pure. `partition`, `array_split`, and the `hsplit`/`vsplit`/`dsplit`
trio return a **list** of arrays (JAX's `jnp.split` returns a tuple;
the wrapper unwraps it so `length/2` and list-pattern matching work
directly).

| Predicate | Semantics |
|---|---|
| `partition(A, N_OR_IDX, LS)` / `(A, N_OR_IDX, AXIS, LS)` | Bidirectional: forward `jnp.split`, backward `jnp.concatenate`. "LS is the partition of A at N_OR_IDX along AXIS" |
| `array_split(A, N_OR_IDX, LS)` / `(A, N_OR_IDX, AXIS, LS)` | Like `partition` forward but tolerates uneven division (forward-only) |
| `hsplit(A, N, LS)` | Column-wise split (axis 1) |
| `vsplit(A, N, LS)` | Row-wise split (axis 0) |
| `dsplit(A, N, LS)` | Depth-wise split (axis 2) |
| `tile(A, REPS, R)` | Replicate `A` across axes |
| `repeat(A, REPS, AXIS, R)` | Repeat elements along `AXIS` |
| `flip(A, R)` / `flip(A, AXIS, R)` | Bidirectional self-inverse reversal along `AXIS` (int or tuple); no-axis form reverses every axis |
| `roll(A, SHIFTS, R)` / `roll(A, SHIFTS, AXIS, R)` | Cyclic shift |
| `pad(A, PAD_WIDTH, R)` / `pad(A, PAD_WIDTH, MODE, R)` | Pad an array; `MODE` is a JAX/NumPy mode string |

`partition` collapses the `split` + `concatenate` pair into a single
bidirectional noun predicate. Forward mode splits, backward mode
concatenates:

```clausal
test("partition forward") <- (
    arange(0, 6, A),
    partition(A, 3, [P0, P1, P2]),          # LS bound by forward
    array_list(P0, [0, 1])
)

test("partition backward") <- (
    array([0, 1], P0), array([2, 3], P1), array([4, 5], P2),
    partition(A, 3, [P0, P1, P2]),          # A bound by backward
    array_list(A, [0, 1, 2, 3, 4, 5])
)
```

`concatenate/3` is still available as a separate forward-only predicate
for joining arbitrary-sized pieces — `partition`'s backward direction
only covers the narrower case where LS is a valid split of A.

`stacked/3` is the declarative form of `stack` + `unstack`. It reads
"A is LS stacked along AXIS" and runs in either direction depending on
which side is bound:

```clausal
test("stacked forward") <- (
    zeros([3], Z), ones([3], O),
    stacked([Z, O], 0, A),             # A has shape [2, 3]
    shape(A, [2, 3])
)

test("stacked backward") <- (
    array([[1, 2], [3, 4], [5, 6]], A),
    stacked([R0, R1, R2], 0, A),
    array_list(R0, [1, 2])             # R1 = [3,4], R2 = [5,6]
)
```

This subsumes the older forward-only `stack/3` and `unstack/3`
predicates; neither is exported any more.

### `partition` vs `array_split`

`partition(A, N, LS)` forward mode raises (and therefore fails the
predicate) when `A`'s length along the axis doesn't divide evenly by
`N`. `array_split` accepts uneven divisions — earlier pieces get one
extra element:

```clausal
test("array_split uneven") <- (
    arange(0, 7, A),
    array_split(A, 3, LS),
    length(LS, 3)                       # pieces are [0,1,2], [3,4], [5,6]
)
```

Both forms also accept a list of indices in place of `N`:

```clausal
test("partition by indices") <- (
    arange(0, 10, A),
    partition(A, [3, 7], [P0, P1, P2])  # [0..2], [3..6], [7..9]
)
```

### `flip` and `roll` axis arguments

`flip` and `roll` accept either a single int axis or a tuple of axes.
A plain Clausal list works too — `_deep_deref` passes it through to JAX,
which treats it as an iterable of axes:

```clausal
test("flip with tuple axes") <- (
    array([[1, 2], [3, 4]], A),
    flip(A, (0, 1), R)                  # reverse both rows and columns
)
```

`flip` is self-inverse and wired bidirectionally — either A or R may
be bound. `flip/2` (no axis) reverses **every** axis; same shorthand
as passing a tuple of all axes:

```clausal
test("flip/2 bidirectional") <- (
    array([[1, 2, 3], [4, 5, 6]], A),
    flip(A, R),                         # forward: R = [[6,5,4], [3,2,1]]
    flip(A2, R)                         # backward: A2 equals A
)
```

`roll/3` (no axis) has a surprise: on multi-dim arrays it **flattens**,
rolls the flat sequence, then reshapes back. This is `jnp.roll`'s own
behaviour, not an artefact of the wrapper. Use `roll/4` with an
explicit axis when you want per-axis rolling:

```clausal
test("roll/3 vs roll/4 on 2d") <- (
    array([[0, 1, 2], [3, 4, 5]], A),
    roll(A, 1, R),                      # R = [[5,0,1], [2,3,4]] — flat
    roll(A, 1, 0, R2)                   # R2 = [[3,4,5], [0,1,2]] — axis 0
)
```

### `repeat` requires an explicit axis

`repeat/4` takes the axis as a mandatory int. `jnp.repeat` without an
axis flattens first — a different operation that would need its own
predicate. In practice, compose with `reshape/3` or `ravel` when you
want that:

```clausal
test("flatten-then-repeat via reshape") <- (
    array([[1, 2], [3, 4]], A),
    reshape(A, [4], A1),                # [1, 2, 3, 4]
    repeat(A1, 2, 0, R)                 # [1,1,2,2,3,3,4,4]
)
```

### Minimum JAX version for `stacked` backward mode

`jnp.unstack` — the function that implements `stacked/3`'s backward
direction — was added in JAX 0.4.28. Older installs will fail with
`AttributeError` the first time `stacked(LS, AXIS, A)` is run with `A`
bound. The forward direction (`jnp.stack`) works on any modern JAX.

### `pad` modes

`MODE` is a string matching NumPy / JAX's `numpy.pad` modes:
`"constant"` (zeros — the default when `MODE` is omitted), `"edge"`,
`"reflect"`, `"symmetric"`, `"wrap"`, `"maximum"`, `"minimum"`,
`"mean"`, `"median"`. `PAD_WIDTH` may be an int, a `(before, after)`
pair, or a per-axis list/tuple of pairs:

```clausal
test("pad modes") <- (
    array([1, 2, 3], A),
    pad(A, [1, 2], R),                  # [0,1,2,3,0,0] (constant is default)
    pad(A, [1, 2], "edge", R2),         # [1,1,2,3,3,3]
    pad(A, [2, 2], "reflect", R3)       # reflect uses interior as mirror
)
```

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
test("solve diagonal system") <- (
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
test("roundtrip") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    fft_transform(T, F),            # forward
    fft_transform(T2, F)            # backward — T2 ≈ T
)

test("frequencies of length-4 signal") <- (
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

## Comparisons, Logic, and Selection

Element-wise comparisons produce bool arrays; check predicates reduce to a
single Python bool and succeed / fail accordingly. All predicates are
Tier 1 pure.

### Element-wise comparisons

| Predicate | JAX call | Output |
|---|---|---|
| `eq(A, B, C)` | `jnp.equal` | bool array |
| `ne(A, B, C)` | `jnp.not_equal` | bool array |
| `gt(A, B, C)` | `jnp.greater` | bool array |
| `lt(A, B, C)` | `jnp.less` | bool array |
| `ge(A, B, C)` | `jnp.greater_equal` | bool array |
| `le(A, B, C)` | `jnp.less_equal` | bool array |

```clausal
array([1, 2, 3], A),
array([1, 5, 3], B),
eq(A, B, C),
array_list(C, [True, False, True])
```

Both operands broadcast — a scalar vs. an array compares each element.

### Check predicates

These succeed iff the reduction is true; failure under `not(...)`.

| Predicate | Semantics |
|---|---|
| `equal(A, B)` | Same shape **and** every element equal |
| `array_equal(A, B)` | Alias for `equal/2` |
| `allclose(A, B)` | `jnp.allclose` with default tolerances |
| `allclose(A, B, ATOL, RTOL)` | Explicit absolute / relative tolerances |
| `any(A)` / `any(A, AXIS)` | Any element truthy (optionally reduced over `AXIS`) |
| `all(A)` / `all(A, AXIS)` | All elements truthy |

```clausal
test("allclose within tolerance") <- (
    array([1.0, 2.0], A),
    array([1.0000001, 2.0], B),
    allclose(A, B)
)
```

### Logical operations

| Predicate | JAX call |
|---|---|
| `logical_and(A, B, C)` | `jnp.logical_and` |
| `logical_or(A, B, C)` | `jnp.logical_or` |
| `logical_not(A, B)` | `jnp.logical_not` |
| `logical_xor(A, B, C)` | `jnp.logical_xor` |

### Selection

| Predicate | Semantics |
|---|---|
| `where(COND, X, Y, R)` | `jnp.where(cond, x, y)` — element-wise pick |
| `masked_select(A, MASK, R)` | Elements of `A` where `MASK` is true (1-D result) |
| `take(A, INDICES, AXIS, R)` | Gather along `AXIS` — `jnp.take(a, indices, axis=AXIS)` |
| `put_along_axis(A, IDX, VAL, AXIS, R)` | Scatter `VAL` into `A` at `IDX` along `AXIS` (returns a new array) |

```clausal
test("where selects") <- (
    array([True, False, True], COND),
    array([10, 20, 30], X),
    array([1, 2, 3], Y),
    where(COND, X, Y, R),
    array_list(R, [10, 2, 30])
)

test("take along axis 0") <- (
    array([[1, 2], [3, 4], [5, 6]], A),
    array([0, 2], IDX),
    take(A, IDX, 0, R),
    array_list(R, [[1, 2], [5, 6]])
)
```

### Caveats

- **`masked_select` is not `jit`-safe.** The output length depends on the
  mask values, so JAX's tracer can't fix it at trace time. For a
  `jit`-compatible alternative, use `where(MASK, A, 0, R)` to build a
  fixed-shape array where unwanted entries are zeroed out.

- **`put_along_axis` is a copy.** JAX's immutable arrays mean
  "in-place" isn't possible — the wrapper passes `inplace=False` for you
  (a JAX API requirement). The original `A` is untouched.

- **Broadcasting.** `where`, comparison, and logical predicates follow
  NumPy broadcasting. Shape mismatches surface as predicate failure via
  the underlying `_pure` wrapper.

- **Bool arrays via `array_list`.** JAX bool arrays round-trip to Python
  bools via `.tolist()`, so `array_list(C, [True, False, True])` works
  in both directions.

See the [Phase 6 implementation plan](../implementation_plans/jax/phase6_comparisons.md)
for the predicate catalogue and design notes.

---

## Advanced Math

Einstein summation, bijective exp/log and trig pairs, plus common
non-bijective math. All Tier 1 pure.

### einsum

```clausal
einsum(EQUATION, ARRAYS, R)
```

`ARRAYS` is a Clausal list of arrays. The equation is standard NumPy
einsum syntax.

```clausal
einsum("ij,jk->ik", [A, B], R)   # matmul
einsum("ii->",      [A],    R)   # trace
einsum("ii->i",     [A],    R)   # diagonal extract
einsum("i,i->",     [A, B], R)   # dot product
```

### Bijective exp/log and trig

Each pair collapses into a single multi-mode predicate. The **noun
name** describes the natural reading of the second argument:
`logarithm(X, Y)` means "Y is the log of X", so forward is `log` and
backward is `exp`.

| Predicate | Forward | Backward | Backward domain |
|---|---|---|---|
| `logarithm(X, Y)` | `jnp.log(X)` | `jnp.exp(Y)` | all reals |
| `sine(ANGLE, VALUE)` | `jnp.sin(ANGLE)` | `jnp.arcsin(VALUE)` | `VALUE ∈ [-1, 1]` |
| `cosine(ANGLE, VALUE)` | `jnp.cos(ANGLE)` | `jnp.arccos(VALUE)` | `VALUE ∈ [-1, 1]` |
| `tangent(ANGLE, VALUE)` | `jnp.tan(ANGLE)` | `jnp.arctan(VALUE)` | all reals, single branch |

Values outside the backward-mode domain return `NaN` — the JAX
functions don't raise. Guard with `allclose/4` or a range check if you
need strictness.

```clausal
test("logarithm forward") <- (
    array(1.0, X),
    logarithm(X, Y),
    array_list(Y, 0.0)
)

test("logarithm backward") <- (
    array(0.0, Y),
    logarithm(X, Y),
    array_list(X, 1.0)
)
```

Partial bijection: `sine(ANGLE, VALUE)` in backward mode only recovers
a principal-branch angle. Round-tripping `sin` then `arcsin` on
`ANGLE = π` yields `0`, not `π`.

### Non-bijective math

| Predicate | JAX call | Notes |
|---|---|---|
| `sqrt(A, R)` | `jnp.sqrt` | Element-wise |
| `pow(A, E, R)` | `jnp.power(A, E)` | Broadcasts exponent |
| `atan2(Y, X, R)` | `jnp.arctan2(Y, X)` | Two-arg arctan with correct quadrant |
| `sinh(A, R)` / `cosh` / `tanh` | `jnp.sinh` / `.cosh` / `.tanh` | Hyperbolic |
| `sigmoid(A, R)` | `jax.nn.sigmoid` | Logistic |
| `softmax(A, AXIS, R)` | `jax.nn.softmax` | Sums to 1 along `AXIS` |
| `log_softmax(A, AXIS, R)` | `jax.nn.log_softmax` | Numerically stable `log(softmax)` |
| `logsumexp(A, AXIS, R)` | `jax.scipy.special.logsumexp` | Numerically stable `log(sum(exp(A)))` |
| `floor(A, R)` / `ceil` / `round` / `sign` | `jnp.floor` / `ceil` / `round` / `sign` | |
| `cumsum(A, AXIS, R)` | `jnp.cumsum` | Along `AXIS` |
| `cumprod(A, AXIS, R)` | `jnp.cumprod` | |

`softmax`, `log_softmax`, and `sigmoid` live in `jax.nn`;
`logsumexp` lives in `jax.scipy.special`. The wrapper imports lazily
and the user doesn't see the submodule split.

```clausal
test("softmax sums to 1 along axis") <- (
    array([1.0, 2.0, 3.0, 4.0], A),
    softmax(A, 0, R),
    sum(R, S),
    array(1.0, ONE),
    allclose(S, ONE, 0.0001, 0.0)
)
```

### Caveats

- **Non-integer operands silently promote.** `softmax` on an int array
  produces a float result; `pow` with integer exponents returns floats
  when the base is float.
- **Out-of-domain NaN.** `sqrt(-1)`, `logarithm(-1, _)`, `arcsin(2)` and
  similar all return `nan` without raising. Use an explicit range check
  before calling, or `allclose(R, R)` to detect a NaN (NaN ≠ NaN) if you
  only need a detection signal.
- **`round` is half-to-even.** JAX follows NumPy's banker's rounding:
  `round(0.5) == 0`, `round(1.5) == 2`. Not a bug — a spec match.
- **`round`, `pow`, `sum`, `any`, `all`, `abs`, `max`, `min` shadow
  Python builtins.** See the [shadowed-builtin gotcha
  section](#gotcha--predicates-that-shadow-python-builtins) above —
  easy to write a clause that thinks it's reducing a Python list but
  is actually building a 0-D JAX array.
- **Check mode on `logarithm` / `sine` / `cosine` / `tangent` is
  bit-exact.** Don't rely on `sine(0.5, 0.479426)` succeeding — use
  forward-mode with `allclose/4` instead. See [Gotcha — bidirectional
  check mode is bit-exact](#gotcha--bidirectional-check-mode-is-bit-exact).

See the [Phase 7 implementation plan](../implementation_plans/jax/phase7_advanced_math.md)
for the predicate catalogue and design notes.

---

## Statistics and Selection

Axis-aware statistical reductions and sort/selection utilities. All
pure.

### Statistical reductions

| Predicate | Semantics |
|---|---|
| `median(A, R)` / `median(A, AXIS, R)` | Median |
| `std(A, R)` / `std(A, AXIS, R)` | Standard deviation |
| `var(A, R)` / `var(A, AXIS, R)` | Variance |
| `percentile(A, Q, R)` / `percentile(A, Q, AXIS, R)` | `Q` ∈ `[0, 100]` (NumPy convention) |
| `quantile(A, Q, R)` / `quantile(A, Q, AXIS, R)` | `Q` ∈ `[0, 1]` |
| `cov(A, R)` | Covariance matrix (rows as variables) |
| `corrcoef(A, R)` | Correlation coefficient matrix |

```clausal
array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], T),
median(T, 1, M)                              # M = [2.0, 5.0]
percentile(T, 25.0, 1, P)                    # P = [1.5, 4.5]
```

### Sorting and selection

| Predicate | Semantics |
|---|---|
| `argmin(A, I)` / `argmin(A, AXIS, I)` | Index of minimum |
| `argmax(A, I)` / `argmax(A, AXIS, I)` | Index of maximum |
| `sort(A, R)` / `sort(A, AXIS, R)` | Sorted **values** (no indices) |
| `argsort(A, I)` / `argsort(A, AXIS, I)` | Indices that would sort `A` |
| `topk(A, K, (VALUES, INDICES))` | `jax.lax.top_k` — last axis only |
| `nonzero(A, (I_1, ..., I_N))` | One index array per dim (always a tuple) |
| `unique(A, R)` | Sorted unique values |
| `argpartition(A, KTH, R)` | Indices such that `A[R[KTH]]` sits at its sorted position |

```clausal
array([3.0, 1.0, 4.0, 1.0, 5.0], A),
sort(A, SORTED),                             # SORTED = [1,1,3,4,5]
argsort(A, IDX),                             # IDX = [1,3,0,2,4]
take(A, IDX, 0, VIA_IDX)                     # VIA_IDX == SORTED
```

`topk` packs its output into a tuple so Clausal's `RES is (VS, IS)`
pattern extracts both values and indices:

```clausal
topk(A, 2, RES),
RES is (VS, IS)                              # VS = top-2 values, IS = their indices
```

### Caveats

- **`topk` is last-axis only.** `jax.lax.top_k` doesn't accept an axis
  argument. Transpose before/after if you need another axis.
- **`nonzero` output shape is data-dependent.** Not jit-safe. For a
  jit-safe alternative use `where(cond, a, 0)` to keep shape fixed.
- **`unique` output shape is data-dependent.** Same jit caveat.
- **`sort` returns values only.** Use `argsort` + `take` if you also
  need the permutation.
- **`argmin` / `argmax` on empty input raise.** JAX inherits NumPy's
  behaviour — wrap in a size check if input may be empty.

See the [Phase 15 implementation plan](../implementation_plans/jax/phase15_stats_selection.md)
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
