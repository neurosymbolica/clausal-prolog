# Phase 1 — Tensor Core

The foundation. Pure tensor creation, properties, math, and shape
operations. All predicates in this phase are Tier 1 (pure, no state).

**File to create:** `clausal/modules/py/torch.py`

---

## Predicates

### Creation

| Name | Arity | Modes | Description |
|---|---|---|---|
| `tensor` | `/2` | `(+data, -T)` | Create tensor from list/nested list |
| `zeros` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | Zero tensor; opts dict for dtype/device |
| `ones` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | Ones tensor |
| `randn` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | Normal random tensor |
| `arange` | `/2, /3, /4` | `(+end, -T)`, `(+start, +end, -T)`, `(+start, +end, +step, -T)` | Range tensor |
| `linspace` | `/4, /5` | `(+start, +end, +steps, -T)`, `(+start, +end, +steps, +opts, -T)` | Linearly spaced |
| `full` | `/3, /4` | `(+shape, +value, -T)`, `(+shape, +value, +opts, -T)` | Filled tensor |
| `eye` | `/2, /3` | `(+n, -T)`, `(+n, +m, -T)` | Identity matrix |

### Properties (multi-mode)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `shape` | `/2` | `(+T,-S)` query, `(+T,+S)` check | Shape of tensor. Check-only when both bound. |
| `dtype` | `/2` | `(+T,-D)` query, `(+T,+D)` check | Dtype. Check-only when both bound. |
| `device` | `/2` | `(+T,-D)` query, `(+T,+D)` check | Device. Check-only when both bound. |
| `dim` | `/2` | `(+T,-N)` | Number of dimensions |
| `element_count` | `/2` | `(+T,-N)` | Number of elements |
| `requires_gradient` | `/2` | `(+T,-B)` | Gradient tracking flag |

### Math

| Name | Arity | Modes | Description |
|---|---|---|---|
| `matmul` | `/3` | `(+A,+B,-C)` | Matrix multiply |
| `add` | `/3` | `(+A,+B,-C)` | Element-wise add |
| `mul` | `/3` | `(+A,+B,-C)` | Element-wise multiply |
| `cat` | `/3` | `(+tensors,+dim,-T)` | Concatenate along dim |
| `stack` | `/3` | `(+tensors,+dim,-T)` | Stack along new dim |
| `sum` | `/2, /3` | `(+T,-S)`, `(+T,+dim,-S)` | Sum reduction |
| `mean` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | Mean reduction |
| `max` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | Max reduction |
| `min` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | Min reduction |
| `clamp` | `/4` | `(+T,+min,+max,-T2)` | Clamp values |
| `abs` | `/2` | `(+T,-T2)` | Absolute value |
| `softmax` | `/3` | `(+T,+dim,-T2)` | Softmax |
| `relu` | `/2` | `(+T,-T2)` | ReLU activation |

### Shape operations

| Name | Arity | Modes | Description |
|---|---|---|---|
| `reshape` | `/3` | `(+T,+shape,-T2)` | Reshape tensor |
| `squeeze` | `/2, /3` | `(+T,-T2)`, `(+T,+dim,-T2)` | Remove size-1 dims |
| `unsqueeze` | `/3` | `(+T,+dim,-T2)` | Add size-1 dim |
| `flatten` | `/2, /4` | `(+T,-T2)`, `(+T,+start,+end,-T2)` | Flatten dims |
| `unflatten` | `/4` | `(+T,+dim,+shape,-T2)` | Unflatten dim |
| `transpose` | `/4` | `(+T,+d0,+d1,-T2)` | Swap two dims |
| `permute` | `/3` | `(+T,+dims,-T2)` | Reorder all dims |
| `contiguous` | `/2` | `(+T,-T2)` | Make memory contiguous |

---

## Context and Reference Patterns

### File structure

Follow `clausal/modules/py/scipy_spatial.py` for the overall file layout:

- **Lazy import guard:** See `_sp()` at line 18 — a function that does a
  thread-safe lazy `import scipy.spatial` on first call. Do the same for
  `import torch`.
- **`_pure()` dispatch helper:** See line 30 — wraps a pure function as a
  trampoline dispatch. Use this for all Tier 1 predicates: tensor creation,
  math, shape ops.
- **`_pred()` factory:** See line 50 — creates a `ModulePredicate` and
  registers arity variants. Use this for every predicate.

All tensor creation and math predicates are the same pattern as
`CrossDistance` and `PairwiseDistance` in that file — pure functions
wrapped with `_pure()`.

### Multi-mode property predicates

`shape/2`, `dtype/2`, `device/2` need custom dispatch (not `_pure()`)
because they have two modes:

- **Query mode** (`(+T, -S)`): second arg is unbound. Call `T.shape` /
  `T.dtype` / `T.device` and unify with the result.
- **Check mode** (`(+T, +S)`): both bound. Check equality and succeed/fail.

Implement mode dispatch by checking `isinstance(deref(var), Var)` — see
`clausal/logic/util.py` for `Var` and `deref`. Example pattern:

```python
def _shape_2(this_generator, parent, tensor_var, shape_var, trail):
    t = deref(tensor_var)
    s = deref(shape_var)
    actual_shape = list(t.shape)
    if isinstance(s, Var):
        # Query mode: unify shape_var with actual shape
        if unify(shape_var, actual_shape, trail):
            yield (parent, None)
    else:
        # Check mode: succeed if shapes match
        if list(s) == actual_shape:
            yield (parent, None)
    yield (parent, DONE)
```

### Opts dict handling

Creation functions (`zeros/3`, `ones/3`, etc.) take an optional dict for
`dtype` and `device` kwargs. See how `clausal/modules/py/scipy_optimize.py`
handles kwargs: the last positional arg before the result is a dict that
gets `**`-unpacked into the Python function call:

```python
# zeros/3: zeros(SHAPE, OPTS, T) where OPTS is e.g. {dtype: torch.float64}
(3, _pure(lambda shape, opts: _torch().zeros(shape, **opts))),
```

### Bijective pairs

`squeeze`/`unsqueeze` and `flatten`/`unflatten` are separate predicates
(not collapsed into one) because the operations aren't symmetric — they
take different arguments.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, zeros, ones, randn, shape, dtype, device,
                         reshape, squeeze, unsqueeze, matmul, add, mul,
                         relu, softmax, sum, cat, abs, clamp])

Test("create zeros and query shape") <- (
    zeros([3, 4], T),
    shape(T, [3, 4])
)

Test("create with dtype option") <- (
    zeros([2, 3], {dtype: ++(torch.float64)}, T),
    dtype(T, ++(torch.float64))
)

Test("reshape") <- (
    zeros([2, 6], T),
    reshape(T, [3, 4], T2),
    shape(T2, [3, 4])
)

Test("matmul shapes") <- (
    zeros([2, 3], A),
    zeros([3, 4], B),
    matmul(A, B, C),
    shape(C, [2, 4])
)

Test("relu zeroes negatives") <- (
    tensor([-1.0, 0.0, 1.0], T),
    relu(T, T2),
    tensor_list(T2, [0.0, 0.0, 1.0])
)

Test("squeeze removes size-1 dims") <- (
    zeros([1, 3, 1, 4], T),
    squeeze(T, T2),
    shape(T2, [3, 4])
)

Test("unsqueeze adds dim") <- (
    zeros([3, 4], T),
    unsqueeze(T, 0, T2),
    shape(T2, [1, 3, 4])
)

Test("squeeze and unsqueeze are inverses") <- (
    zeros([3, 1, 4], T),
    squeeze(T, 1, T2),
    shape(T2, [3, 4]),
    unsqueeze(T2, 1, T3),
    shape(T3, [3, 1, 4])
)

Test("cat along dim") <- (
    zeros([2, 3], A),
    ones([2, 3], B),
    cat([A, B], 0, C),
    shape(C, [4, 3])
)

Test("sum reduction") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], T),
    sum(T, S),
    % S is a scalar tensor with value 10.0
    tensor_list(S, 10.0)
)

Test("shape check mode succeeds") <- (
    zeros([3, 4], T),
    shape(T, [3, 4])
)

Test("shape check mode fails") <- (
    zeros([3, 4], T),
    \+ shape(T, [5, 6])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/clausal_files/torch_tensor.clausal`):
- Every creation function with default and custom opts
- Every property predicate in query mode
- `shape/2`, `dtype/2`, `device/2` in check mode (both success and failure with `\+`)
- Every math operation with shape verification
- Every shape operation with shape verification
- Bijective roundtrips: squeeze/unsqueeze, flatten/unflatten
- Edge cases: scalar tensors, empty tensors, 0-dim tensors

**Python unit tests** (`tests/test_torch_infra.py`):
- Lazy import guard doesn't fail when torch is missing (graceful error)
- Opts dict unpacking edge cases (empty dict, unknown keys)

---

## Docs

Create `docs/torch.md`:
- Overview and import example
- Tensor creation predicates with examples
- Property predicates with mode descriptions
- Math predicates
- Shape operations with bijective pair notes
- All code examples must appear verbatim in the `.clausal` test file

---

## Issues

### 1. `deref` does not deep-deref container contents — FIXED

`deref()` on a list or dict returns the container with Var objects still
inside. This affects all predicates that take list or dict arguments:
shape lists like `[N, M]`, tensor lists like `[A, B]`, and opts dicts
like `{"dtype": DT}`. Fixed by introducing `_deep_deref()` which
recursively unwraps Vars inside lists and dicts, and using it in the
`_pure()` helper so all predicates benefit.

### 2. `.clausal` files use Python syntax, not Prolog syntax — FIXED

- Comments must use `#`, not `%` (files go through `ast.parse`)
- Negation-as-failure is `not(...)`, not `\+`
- Unicode characters in comments cause `SyntaxError`

### 3. Avoiding `++()` escapes — FIXED

Dtype constants (`float32`, `float64`, etc.) are exported directly from
`py.torch` so users can import them by name. The `device/2` predicate
returns a string (`"cpu"`) rather than a `torch.device` object. An
`is_contiguous/1` predicate was added to avoid `++(T.is_contiguous())`
escapes. Use `-import_module(torch)` or `-import_module(numpy)` for
direct access to Python module attributes.

### 4. `import_from(py.torch, ...)` shadows `import_module(torch)` — NOTED

Importing from `py.torch` registers the Clausal module under the name
`torch`, which shadows any `-import_module(torch)`. Dtype constants are
exported from `py.torch` to avoid needing both. If users need both the
Python `torch` module and `py.torch` predicates, they must use
`-import_module(torch)` *without* `import_from(py.torch, ...)`, or
accept that `torch.*` resolves through the Clausal module.

### 5. Predicate naming: `numpy` renamed to `tensor_numpy` — FIXED

The original name `numpy` for the tensor-to-numpy conversion predicate
was problematic: it shadowed `-import_module(numpy)` and used a library
name as a verb. Renamed to `tensor_numpy` to match the `tensor_list`
pattern — both are nouns describing the same data in a different form.

### 6. `sum`/`max`/`min`/`abs` shadow Python builtins — DISMISSED

These names match the library's API. Module-scoped imports prevent
collision in user code. Inside the implementation file, the Python
builtins are not needed.

### 7. `++()` in goal position is a no-op — FIXED

`++(expr)` in goal position evaluates the Python expression but always
succeeds regardless of the result. Tests initially used patterns like
`++(V > 0.999)` which were silently vacuous. Fixed by using Clausal's
own comparison operators (`V > 0.999`) or dedicated predicates
(`is_contiguous/1`).
