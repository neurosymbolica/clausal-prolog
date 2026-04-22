# Phase 12 — Function Transforms

JAX's higher-order transforms — `grad`, `jit`, `vmap`, `jvp`, `vjp`.
Where PyTorch's autograd is a stateful training-time concept (and stays
as `++()` in the PyTorch plan), JAX's transforms are pure functions of
functions. We expose them as one-shot predicates: take a Python callable
plus inputs, compute the transformed output, unify.

**File to create:** `clausal/modules/py/jax_transforms.py`

**Depends on:** Phase 1 — `clausal/modules/py/jax.py` for lazy import
and helpers. Phase 9 (pytrees) — `grad` works on pytrees of arrays, not
just arrays.

---

## Predicates

### Differentiation

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `grad_value` | `/3` | `(+F, +X, -G)` | pure | `jax.grad(F)(X)` — gradient at a point |
| `value_and_grad` | `/4` | `(+F, +X, -V, -G)` | pure | `jax.value_and_grad(F)(X)` |
| `jvp_value` | `/4` | `(+F, +PRIMALS, +TANGENTS, -OUT)` | pure | Forward-mode Jacobian-vector product |
| `vjp_value` | `/4` | `(+F, +X, -V, -VJP_FN)` | pure | Reverse-mode: returns value and a pullback callable |
| `jacobian` | `/3` | `(+F, +X, -J)` | pure | `jax.jacobian(F)(X)` (alias for `jacrev`) |
| `jacfwd` | `/3` | `(+F, +X, -J)` | pure | Forward-mode Jacobian |
| `jacrev` | `/3` | `(+F, +X, -J)` | pure | Reverse-mode Jacobian |
| `hessian` | `/3` | `(+F, +X, -H)` | pure | `jax.hessian(F)(X)` |

### Vectorisation and compilation

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `vmap_apply` | `/3, /4` | `(+F, +X, -R)`, `(+F, +X, +AXES, -R)` | pure | Vectorise then apply |
| `pmap_apply` | `/3, /4` | | pure | Parallel-map then apply |
| `jit_compile` | `/2` | `(+F, -F2)` | pure | Return a JIT-compiled callable |

### Inspection

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `make_jaxpr` | `/3` | `(+F, +X, -JAXPR)` | pure | Symbolic trace of F at X |
| `eval_shape` | `/3` | `(+F, +X, -SHAPE_DTYPE_TREE)` | pure | Abstract-eval — shape + dtype without computing |

---

## Context and Reference Patterns

### Why one-shot predicates, not transform wrappers

`jax.grad(f)` returns a *function*. In procedural code you typically
call it multiple times:

```python
g = jax.grad(f)
for x in xs:
    print(g(x))
```

In Clausal, this pattern is awkward — users would have to hold and pass
around Python callables. The **one-shot** form aligns with Clausal's
declarative style:

```clausal
F is ++(lambda x: x ** 2),
grad_value(F, 3.0, G)
```

For cases where the user genuinely needs the transformed function as a
value, `jit_compile(F, F_JIT)` returns the function itself.

### Argument types

The first argument (`F`) is a Python callable. Users construct it with
`++()`. This is the same pattern as `MatrixFunction(A, FUNC, RESULT)`
in `scipy_linalg.py`:

```python
MatrixFunction = _pred("MatrixFunction",
    (3, _pure(lambda a, fn: _sl().funm(a, fn))),
)
```

### Implementation pattern

All transforms are pure — use `_pure()`:

```python
grad_value = _pred("grad_value",
    (3, _pure(lambda f, x: _jx().grad(f)(x))),
)

value_and_grad = _pred("value_and_grad",
    (4, _pure_two_outputs(lambda f, x: _jx().value_and_grad(f)(x))),
)
```

Where `_pure_two_outputs` is a variant of `_pure` that unifies two
output vars with the two elements of the returned tuple. Alternatively,
return a 2-tuple and decompose with `is`:

```python
value_and_grad = _pred("value_and_grad",
    (3, _pure(lambda f, x: tuple(_jx().value_and_grad(f)(x)))),
)
```

Then users write:

```clausal
value_and_grad(F, X, RESULT),
RESULT is (V, G)
```

Decision: **use the 2-tuple form for consistency with linalg decompositions**.
Change the arity to `/3` and update the catalogue above. See Issue 1.

### `vmap_apply` with axes

`jax.vmap(f, in_axes=..., out_axes=...)` takes keyword args. The
4-arity variant accepts a dict:

```python
vmap_apply = _pred("vmap_apply",
    (3, _pure(lambda f, x: _jx().vmap(f)(x))),
    (4, _pure(lambda f, x, opts: _jx().vmap(f, **opts)(x))),
)
```

### `jit_compile` — returns a callable

```python
jit_compile = _pred("jit_compile",
    (2, _pure(lambda f: _jx().jit(f))),
)
```

Users can then call `F_JIT` via `++()`:

```clausal
F is ++(lambda x: jax.numpy.sum(x ** 2)),
jit_compile(F, F_JIT),
Y is ++(F_JIT(X))
```

Limited usefulness in pure Clausal — mostly for users who want to hand
a JIT-compiled function to other Python code.

### `eval_shape` — pytree of `ShapeDtypeStruct`

`jax.eval_shape(f, x)` returns a pytree of `ShapeDtypeStruct` matching
the output structure. Useful for reasoning about shapes without
computing values. Return the tree as-is and let the user decompose with
pytree predicates from Phase 9:

```python
eval_shape = _pred("eval_shape",
    (3, _pure(lambda f, x: _jx().eval_shape(f, x))),
)
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, array_list, shape, matmul, sum])
-import_from(py.jax_transforms, [grad_value, value_and_grad,
                                  jacobian, hessian,
                                  vmap_apply, jit_compile,
                                  eval_shape])
-import_module(jax)
-import_module(jax.numpy)

Test("grad of x^2 at 3") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array(3.0)),
    grad_value(F, X, G),
    array_list(G, 6.0)
)

Test("value_and_grad of sum(x^2)") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    X is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    value_and_grad(F, X, RESULT),
    RESULT is (V, G),
    array_list(V, 14.0),
    array_list(G, [2.0, 4.0, 6.0])
)

Test("jacobian of sin") <- (
    F is ++(jax.numpy.sin),
    X is ++(jax.numpy.array([0.0, 1.0, 2.0])),
    jacobian(F, X, J),
    shape(J, [3, 3])
)

Test("hessian of quadratic") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    X is ++(jax.numpy.array([1.0, 2.0])),
    hessian(F, X, H),
    shape(H, [2, 2])
)

Test("vmap doubles each element") <- (
    F is ++(lambda x: x * 2),
    X is ++(jax.numpy.arange(5)),
    vmap_apply(F, X, R),
    array_list(R, [0, 2, 4, 6, 8])
)

Test("jit_compile returns callable") <- (
    F is ++(lambda x: x * x),
    jit_compile(F, F_JIT),
    Y is ++(F_JIT(jax.numpy.array(5.0))),
    array_list(Y, 25.0)
)

Test("eval_shape without executing") <- (
    F is ++(lambda x: x @ x.T),
    X is ++(jax.ShapeDtypeStruct((10, 5), jax.numpy.float32)),
    eval_shape(F, X, SHAPE_DTYPE),
    S is ++(SHAPE_DTYPE.shape),
    S == (10, 10)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_transforms_tests.clausal`):

- `grad_value` on scalar, vector, pytree inputs
- `value_and_grad` tuple decomposition
- `jacfwd` vs `jacrev` agreement
- `hessian` on quadratic
- `vmap_apply` with default axes and explicit `in_axes=0`
- `jit_compile` returns a callable whose output equals the non-compiled
  version
- `eval_shape` on a function that would allocate GB of memory — verify
  it's cheap

**Python unit tests:**
- Callable pass-through via `++()` doesn't lose closure state

---

## Docs

Create `docs/jax_transforms.md`:
- Overview: JAX's transforms as pure functions of functions
- One-shot vs. function-returning predicates — design choice
- Each transform with a realistic example
- Interaction with pytrees (grad of pytree-of-arrays)
- When to use `vmap` vs. Clausal's own enumeration-plus-`findall`
- `jit_compile` caveats — tracing abstracts array values

---

## Issues

1. **Tuple-decomposition arity chosen.** `value_and_grad/3`,
   `jvp_value/4`, `vjp_value/3` all return tuples — users decompose
   with `RESULT is (V, G)` syntax. Matches `svd`, `qr`, `eig` in
   Phase 4.

2. **`grad` of non-scalar outputs.** `jax.grad(f)` requires `f` to
   return a scalar. Vector-valued `f` raises, which `_pure`'s exception
   handler surfaces as predicate failure — covered by the
   `grad of vector output fails` test. For vector-valued functions,
   use `jacobian/3` instead.

3. **Pytree inputs to grad work cleanly.** `grad_value(F, PARAMS, G)`
   with a dict `PARAMS` produces a dict `G` with matching structure.
   Users extract entries via `GA is ++(G["a"])`. Combines with Phase 9
   pytree predicates for structural traversal.

4. **`jvp` primals/tangents shape.** `jax.jvp(f, primals, tangents)`
   requires both to be tuples, one element per positional arg of `f`.
   Implementation wraps Clausal-side lists with `tuple(...)` so either
   `[x]` or `(x,)` works.

5. **`vjp_fn` callback from Clausal.** `vjp_value` returns
   `(primal, vjp_fn)` — `vjp_fn` is a callable that users invoke via
   `++(vjp_fn(cotangent))`. This is the only predicate that
   deliberately hands back a closure; the value goes back through
   `++()` the next time it's applied.

6. **`jit_compile` returns a callable.** Unlike other transforms,
   users *do* want the JIT'd function as a value — it's the whole
   point of the compilation. Invoke via `++(F_JIT(x))`.

7. **`pmap_apply` needs multi-device.** On single-device hosts (CPU,
   single GPU) `pmap` reduces to a degenerate case. Tests currently
   exercise `vmap_apply` only. Multi-device testing deferred to
   Phase 13 when `make_mesh` lands.

8. **Closures baked at trace time.** Under `jit`, Python closures that
   capture concrete arrays bake in those arrays at trace time — if the
   captured value changes, re-compile. Standard JAX semantics, not a
   wrapper concern. Flagged in `docs/jax_transforms.md`.

9. **Memory of JAX caches.** `jax.jit` caches compiled programs per
   function object. Tests compile many one-off lambdas — total memory
   stays bounded because each lambda's cache is small, but for a
   long-lived Clausal session users can call
   `jax.clear_caches()` via `++()` if needed.

10. **`ShapeDtypeStruct` and `make_jaxpr` return JAX types.** The
    predicates pass them through unchanged — users poke attributes via
    `++(SD.shape)` / `++(JP.jaxpr)`. No Clausal-side wrapping; these
    objects are inspection artifacts, not data.
