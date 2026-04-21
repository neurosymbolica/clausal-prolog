# Phase 1 — Array Core

The foundation. Pure array creation, properties, math, shape operations,
and bidirectional conversions. All predicates in this phase are Tier 1
(pure, no state).

**File to create:** `clausal/modules/py/jax.py`

**Depends on:** `clausal/modules/py/_helpers.py` (already in place —
provides `_pred`, `_pure`, `_deep_deref`).

---

## Predicates

### Creation

| Name | Arity | Modes | Description |
|---|---|---|---|
| `array` | `/2, /3` | `(+DATA, -A)`, `(+DATA, +OPTS, -A)` | Create array from list/nested list; OPTS for dtype |
| `zeros` | `/2, /3` | `(+SHAPE, -A)`, `(+SHAPE, +OPTS, -A)` | Zero array |
| `ones` | `/2, /3` | `(+SHAPE, -A)`, `(+SHAPE, +OPTS, -A)` | Ones array |
| `full` | `/3, /4` | `(+SHAPE, +VALUE, -A)`, `(+SHAPE, +VALUE, +OPTS, -A)` | Filled array |
| `arange` | `/2, /3, /4, /5` | `(+END, -A)`, `(+START, +END, -A)`, `(+START, +END, +STEP, -A)`, `(+START, +END, +STEP, +OPTS, -A)` | Range |
| `linspace` | `/4, /5` | `(+START, +END, +STEPS, -A)` | Linearly spaced |
| `eye` | `/2, /3, /4` | `(+N, -A)`, `(+N, +M, -A)`, `(+N, +M, +OPTS, -A)` | Identity matrix |

### Properties (multi-mode)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `shape` | `/2` | `(+A, -S)` query, `(+A, +S)` check | Shape as a Python tuple |
| `dtype` | `/2` | `(+A, -D)` query, `(+A, +D)` check | Dtype |
| `device` | `/2` | `(+A, -D)` query, `(+A, +D)` check | Device (string) |
| `dim` | `/2` | `(+A, -N)` | `ndim` |
| `element_count` | `/2` | `(+A, -N)` | `size` |

Note: `sharding/2` is deferred to Phase 13.

### Math

| Name | Arity | Modes | Description |
|---|---|---|---|
| `matmul` | `/3` | `(+A, +B, -C)` | Matrix multiply |
| `dot` | `/3` | `(+A, +B, -C)` | Dot product |
| `add` | `/3` | `(+A, +B, -C)` | Element-wise add |
| `mul` | `/3` | `(+A, +B, -C)` | Element-wise multiply |
| `sum` | `/2, /3` | `(+A, -S)`, `(+A, +AXIS, -S)` | Sum |
| `mean` | `/2, /3` | | Mean |
| `max` | `/2, /3` | | Max |
| `min` | `/2, /3` | | Min |
| `clip` | `/4` | `(+A, +MIN, +MAX, -A2)` | Clip values |
| `abs` | `/2` | `(+A, -A2)` | Absolute value |

### Shape operations

| Name | Arity | Modes | Description |
|---|---|---|---|
| `reshape` | `/3` | `(+A, +SHAPE, -A2)` | Reshape |
| `squeeze` | `/2, /3` | `(+A, -A2)`, `(+A, +AXIS, -A2)` | Remove size-1 dims |
| `expand_dims` | `/3` | `(+A, +AXIS, -A2)` | Add size-1 dim |
| `transpose` | `/2, /3` | `(+A, -A2)`, `(+A, +AXES, -A2)` | Transpose |
| `swapaxes` | `/4` | `(+A, +A0, +A1, -A2)` | Swap two axes |
| `moveaxis` | `/4` | `(+A, +SRC, +DEST, -A2)` | Move an axis |
| `concatenate` | `/3` | `(+ARRS, +AXIS, -A)` | Concatenate |
| `stack` | `/3` | `(+ARRS, +AXIS, -A)` | Stack along new axis |
| `broadcast_to` | `/3` | `(+A, +SHAPE, -A2)` | Broadcast |
| `astype` | `/3` | `(+A, +DTYPE, -A2)` | Cast to dtype |

### Conversions (bijective)

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `jax_numpy` | `/2` | `(+A, -N)`, `(-A, +N)` | yes | `jax.Array` <-> `numpy.ndarray` |
| `array_list` | `/2` | `(+A, -L)`, `(-A, +L)` | yes | `jax.Array` <-> nested Python list |

### Exported constants (via `__getattr__`)

- Dtypes: `float16`, `float32`, `float64`, `bfloat16`, `int8`, `int16`,
  `int32`, `int64`, `uint8`, `uint16`, `uint32`, `uint64`, `bool_`,
  `complex64`, `complex128`
- Math constants: `pi`, `e`, `inf`, `nan`
- Indexing: `newaxis`

---

## Context and Reference Patterns

### File structure — follow `torch.py`

`clausal/modules/py/torch.py` (1,317 lines) is the direct blueprint.
Copy its overall structure:

- **Lazy import guard** — `_ensure_jax()` and `_jx()` at the top (see
  `torch.py` lines 225-243 for `_ensure_torch`/`_th`). Thread-safe lazy
  import of `jax` and `jax.numpy`.
- **`_pure()` dispatch helper** — from `clausal/modules/py/_helpers.py`.
  Wrap every Tier 1 predicate the same way:

  ```python
  zeros = _pred("zeros",
      (2, _pure(lambda shape: _jnp().zeros(shape))),
      (3, _pure(lambda shape, opts: _jnp().zeros(shape, **opts))),
  )
  ```

- **`_property_2()` helper** — adapt from `torch.py` lines 245-264.
  Same multi-mode dispatch: `(+A, -V)` queries, `(+A, +V)` checks.

- **`_bidir_2()` helper** — already exists in `torch.py` lines 267-302.
  Re-use (import from `torch.py`) or copy into `jax.py` if we prefer to
  keep the modules independent. The conservative choice is to copy into
  `_helpers.py` so both wrappers share the same implementation — track
  as Issue 1 if duplication arises.

- **`_pred()` factory** — from `_helpers.py`. Same use as in `torch.py`.

- **Exported constants via `__getattr__`** — see `torch.py` for the
  pattern. Expose JAX dtypes, `pi`, `inf`, `nan`, `newaxis`.

### Lazy import — two sub-imports needed

JAX has two namespaces we lean on heavily:

```python
_jax = None
_jnp = None
_jax_lock = _threading.Lock()

def _ensure_jax():
    global _jax, _jnp
    if _jax is not None:
        return
    with _jax_lock:
        if _jax is not None:
            return
        from clausal.modules.py import _import_stdlib
        _jax = _import_stdlib("jax")
        _jnp = _import_stdlib("jax.numpy")

def _jx():
    _ensure_jax()
    return _jax

def _jnp_mod():
    _ensure_jax()
    return _jnp
```

### Creation with opts dict

JAX takes keyword arguments like `dtype=` directly. The opts dict gets
`**`-unpacked:

```python
zeros = _pred("zeros",
    (2, _pure(lambda shape: _jnp_mod().zeros(shape))),
    (3, _pure(lambda shape, opts: _jnp_mod().zeros(shape, **opts))),
)
```

Test uses exported dtype constants:

```clausal
-import_from(py.jax, [zeros, shape, dtype, float64])
zeros([3, 4], {"dtype": float64}, A)
dtype(A, float64)
```

### Shape as tuple vs list

`arr.shape` returns a Python `tuple` in JAX (same as NumPy). The wrapper
should convert to a list for Clausal, matching how `torch.py` does
`list(t.shape)` (line 397):

```python
shape = _pred("shape",
    (2, _property_2(lambda a: list(a.shape))),
)
```

Tests pass `[3, 4]` not `(3, 4)` to avoid tuple/list unification surprises.

### `dtype/2` equality

JAX's `dtype` comparison works with `==`, so the `_property_2()` helper
works as-is. If JAX returns numpy dtype objects, they compare equal to
`jnp.float32` etc. Validate during implementation.

### Device as string

Follow `torch.py` line 405:

```python
device = _pred("device",
    (2, _property_2(lambda a: str(a.device))),
)
```

JAX's `arr.device` returns a `Device` object whose `str(...)` is
`"TFRT_CPU_0"` or similar. We may want a more useful string — check what
the property looks like during implementation and normalise to something
like `"cpu:0"` if the raw form is ugly. If the raw form is fine, keep it.

### Math ops are uniform

All pure math is the same pattern:

```python
matmul = _pred("matmul",
    (3, _pure(lambda a, b: _jnp_mod().matmul(a, b))),
)
add = _pred("add",
    (3, _pure(lambda a, b: _jnp_mod().add(a, b))),
)
# etc.
```

### Reductions with optional axis

Two arities, both `_pure()`:

```python
sum = _pred("sum",
    (2, _pure(lambda a: _jnp_mod().sum(a))),
    (3, _pure(lambda a, axis: _jnp_mod().sum(a, axis=int(axis)))),
)
```

### Conversions — `_bidir_2()`

`jax_numpy/2` and `array_list/2` use the same helper PyTorch uses:

```python
jax_numpy = _pred("jax_numpy",
    (2, _bidir_2(
        forward=lambda a: _np_module().asarray(a),
        backward=lambda n: _jnp_mod().asarray(n),
    )),
)

array_list = _pred("array_list",
    (2, _bidir_2(
        forward=lambda a: a.tolist(),
        backward=lambda l: _jnp_mod().array(l),
    )),
)
```

### Exported constants via `__getattr__`

See the PyTorch wrapper's approach for exporting `float32`, `float64`,
etc. Follow the same module-level `__getattr__`:

```python
def __getattr__(name):
    if name in _EXPORTED_DTYPES:
        _ensure_jax()
        return getattr(_jnp, name)
    if name in _EXPORTED_CONSTS:
        _ensure_jax()
        return getattr(_jnp, name)
    raise AttributeError(name)

_EXPORTED_DTYPES = frozenset({
    "float16", "float32", "float64", "bfloat16",
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "bool_", "complex64", "complex128",
})
_EXPORTED_CONSTS = frozenset({"pi", "e", "inf", "nan", "newaxis"})
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, zeros, ones, arange, linspace,
                      shape, dtype, device, dim, element_count,
                      matmul, add, mul, sum, mean, abs, clip,
                      reshape, squeeze, expand_dims, transpose,
                      concatenate, stack, broadcast_to, astype,
                      jax_numpy, array_list,
                      float32, float64, int32])
-import_module(numpy)

Test("create zeros and query shape") <- (
    zeros([3, 4], A),
    shape(A, [3, 4])
)

Test("create with dtype option") <- (
    zeros([2, 3], {"dtype": float64}, A),
    dtype(A, float64)
)

Test("arange") <- (
    arange(0, 6, A),
    array_list(A, [0, 1, 2, 3, 4, 5])
)

Test("linspace") <- (
    linspace(0.0, 1.0, 5, A),
    shape(A, [5])
)

Test("reshape") <- (
    zeros([2, 6], A),
    reshape(A, [3, 4], A2),
    shape(A2, [3, 4])
)

Test("matmul shape") <- (
    zeros([2, 3], A),
    zeros([3, 4], B),
    matmul(A, B, C),
    shape(C, [2, 4])
)

Test("squeeze removes size-1") <- (
    zeros([1, 3, 1, 4], A),
    squeeze(A, A2),
    shape(A2, [3, 4])
)

Test("expand_dims adds") <- (
    zeros([3, 4], A),
    expand_dims(A, 0, A2),
    shape(A2, [1, 3, 4])
)

Test("squeeze and expand_dims are inverses at a dim") <- (
    zeros([3, 1, 4], A),
    squeeze(A, 1, A2),
    shape(A2, [3, 4]),
    expand_dims(A2, 1, A3),
    shape(A3, [3, 1, 4])
)

Test("concatenate along axis") <- (
    zeros([2, 3], A),
    ones([2, 3], B),
    concatenate([A, B], 0, C),
    shape(C, [4, 3])
)

Test("sum reduction") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    sum(A, S),
    array_list(S, 10.0)
)

Test("clip") <- (
    array([-1.0, 0.0, 2.0], A),
    clip(A, 0.0, 1.0, A2),
    array_list(A2, [0.0, 0.0, 1.0])
)

Test("shape check mode succeeds") <- (
    zeros([3, 4], A),
    shape(A, [3, 4])
)

Test("shape check mode fails") <- (
    zeros([3, 4], A),
    not(shape(A, [5, 6]))
)

Test("jax_numpy forward") <- (
    array([1.0, 2.0, 3.0], A),
    jax_numpy(A, N),
    array_list(A, [1.0, 2.0, 3.0])
)

Test("jax_numpy reverse") <- (
    N is ++(numpy.array([1.0, 2.0, 3.0])),
    jax_numpy(A, N),
    array_list(A, [1.0, 2.0, 3.0])
)

Test("array_list roundtrip") <- (
    array_list(A, [[1.0, 2.0], [3.0, 4.0]]),
    shape(A, [2, 2]),
    array_list(A, L),
    L == [[1.0, 2.0], [3.0, 4.0]]
)

Test("astype") <- (
    zeros([3], A),
    astype(A, int32, A2),
    dtype(A2, int32)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_array_tests.clausal`):
- Every creation function with default and custom opts
- Every property predicate in query mode; `shape/dtype` in check mode (success + failure via `not(...)`)
- Every math operation with shape verification
- Every shape operation with shape verification
- Bijective roundtrips: `squeeze`/`expand_dims`, `jax_numpy`, `array_list`
- Edge cases: scalar arrays, 0-d arrays, empty arrays

**Python unit tests** (`tests/test_jax_infra.py`):
- Lazy import doesn't crash when JAX is missing (graceful ModuleNotFoundError or explicit error)
- Opts dict unpacking edge cases (empty dict, unknown keys)
- `__getattr__` returns the right dtype objects

---

## Docs

Create `docs/jax.md`:
- Overview and import example
- Array creation predicates with examples
- Property predicates with mode descriptions
- Math predicates
- Shape operations with bijective pair notes
- Conversions
- All code examples must appear verbatim in the `.clausal` test file

---

## Issues

### Resolved during Phase 1 implementation

1. **`device` string format — clean enough, kept raw.**
   On CPU, `str(arr.device)` prints `"cpu:0"` (not `"TFRT_CPU_0"` as the
   original plan speculated). No normalisation applied. The integration
   test was relaxed to re-use the queried value rather than hard-coding
   `"cpu:0"`, so running the suite on GPU would still pass.

2. **Shape return type — list conversion works.** `arr.shape` is a
   `tuple`; `list(arr.shape)` unifies cleanly with Clausal list literals
   like `[3, 4]`. Tests use list form throughout.

3. **Mixed-type `jnp.array` — no issue in practice.** Phase 1 tests use
   consistent types per array, so no promotion surprises arose.

4. **`_bidir_2` / `_property_2` / `_bidir_3_mid` — promoted to
   `_helpers.py`.** Both `torch.py` and `jax.py` now import the shared
   implementations; three previous duplicates (torch.py + jax.py)
   reduced to one source of truth. `torch_nn.py`, `torch_distributions.py`,
   and `torch_data.py` still hold their own `_property_2` copies — worth
   consolidating in a follow-up.

5. **`jax.Array` equality in check modes — safe for Phase 1.**
   `_property_2` is only called on shape (list of ints) and dtype (numpy
   dtype objects); neither triggers element-wise array comparison.

### New issue surfaced during implementation

6. **`float64` option silently downcast to `float32` (`jax_enable_x64`).**
   JAX's default disables 64-bit floats, so
   `zeros([2, 3], {"dtype": float64}, A)` emits a `UserWarning` and
   returns a `float32` array. The wrapper intentionally does **not**
   auto-enable x64 on import, because that globally flips the default
   dtype to `float64` and would surprise any other JAX user in the same
   process. Documented in the module docstring; users who need float64
   must set `jax.config.update("jax_enable_x64", True)` (or the
   `JAX_ENABLE_X64=1` env var) before any JAX computation. The Phase 1
   integration test for "dtype option" was switched from `float64` to
   `int32` to avoid triggering the truncation.
