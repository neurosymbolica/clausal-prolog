# jax_transforms — JAX Function Transforms

JAX's headline feature is composable higher-order transforms:
`grad`, `jit`, `vmap`, `jvp`, `vjp`. Unlike PyTorch's autograd —
which is a stateful training-time concept tied to tensors — JAX
transforms are **pure functions of functions**. `jax.grad(f)` is
a function you can `jit`, `vmap`, or pass around; the transform
itself has no state.

That purity makes transforms natural Clausal Prolog predicates: take a
Python callable, take inputs, produce the transformed output,
unify.

All predicates are Tier 1 pure.

## Import

```seam
-import_module(jax)
-import_from(py.jax_transforms, [
    grad_value, value_and_grad,
    jvp_value, vjp_value,
    jacobian, jacfwd, jacrev, hessian,
    vmap_apply, pmap_apply, jit_compile,
    make_jaxpr, eval_shape
])
```

---

## Design — one-shot, not function-returning

`jax.grad(f)` returns a *function*. In procedural code you typically
bind that function and call it many times:

```python
g = jax.grad(f)
for x in xs:
    print(g(x))
```

In Clausal Prolog that pattern is awkward: you'd hold a Python callable in
a variable and call it via `++()` each time. Instead, the
predicates are **one-shot** — they take the function *and* the input
and produce the output directly:

```seam
test("one-shot grad") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array(3.0)),
    grad_value(F, X, G),
    array_list(G, 6.0)
)
```

For the rare case where the user genuinely wants the transformed
function itself, `jit_compile/2` returns a callable they can invoke
via `++()`.

---

## Differentiation

### `grad_value(F, X, G)`

Gradient of `F` at `X`. `F` must return a scalar; for vector-valued
`F`, reach for `jacobian/3`.

```seam
test("grad of x^2 at 3") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array(3.0)),
    grad_value(F, X, G),
    array_list(G, 6.0)
)
```

### `value_and_grad(F, X, RESULT)`

Returns a tuple `(value, gradient)` — decompose with the seam's tuple
syntax, consistent with Phase 4's `svd`, `qr`, `eig`.

```seam
test("value_and_grad of x^3 at 2") <- (
    F is ++(lambda x: x ** 3),
    X is ++(jax.numpy.array(2.0)),
    value_and_grad(F, X, RESULT),
    RESULT is (V, G),
    array_list(V, 8.0),
    array_list(G, 12.0)
)
```

### `jvp_value(F, PRIMALS, TANGENTS, RESULT)` — forward-mode JVP

Jacobian-vector product in the forward direction. `PRIMALS` and
`TANGENTS` are lists matching the signature of `F` (one entry per
positional arg). `RESULT` is a tuple `(primal_out, tangent_out)`.

```seam
test("jvp of x^2 at 3 with tangent 1") <- (
    F is ++(lambda x: x ** 2),
    P is ++(jax.numpy.array(3.0)),
    T is ++(jax.numpy.array(1.0)),
    jvp_value(F, [P], [T], RESULT),
    RESULT is (PRIMAL, TANGENT),
    array_list(PRIMAL, 9.0),
    array_list(TANGENT, 6.0)          # 2x at x=3
)
```

### `vjp_value(F, X, RESULT)` — reverse-mode VJP

Reverse-mode analogue. Returns `(value, vjp_fn)` — where `vjp_fn` is a
Python callable that maps cotangents to gradients. Invoke it via `++()`:

```seam
test("vjp_fn gives gradient") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    X is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    vjp_value(F, X, RESULT),
    RESULT is (_V, VJP_FN),
    COTANGENT is ++(jax.numpy.array(1.0)),
    PULLED is ++(VJP_FN(COTANGENT)),
    G is ++(PULLED[0]),
    array_list(G, [2.0, 4.0, 6.0])
)
```

### `jacobian(F, X, J)` / `jacfwd` / `jacrev`

Jacobian via reverse-mode by default; `jacfwd` for forward-mode,
`jacrev` for explicit reverse-mode (same as `jacobian`).

```seam
test("jacobian of elementwise square") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    jacobian(F, X, J),
    shape(J, [3, 3]),
    array_list(J, [[2.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 6.0]])
)
```

### `hessian(F, X, H)`

The Hessian matrix — second derivatives:

```seam
test("hessian of sum(x^2) is 2I") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    X is ++(jax.numpy.array([1.0, 2.0])),
    hessian(F, X, H),
    shape(H, [2, 2]),
    array_list(H, [[2.0, 0.0], [0.0, 2.0]])
)
```

### Pytree inputs

`jax.grad` accepts pytree inputs (dicts, lists, tuples of arrays).
The wrapper passes the pytree term through to JAX unchanged:

```seam
test("grad with dict params") <- (
    F is ++(lambda p: (p["a"] ** 2) + (p["b"] ** 2)),
    PARAMS is ++({"a": jax.numpy.array(3.0), "b": jax.numpy.array(4.0)}),
    grad_value(F, PARAMS, G),
    GA is ++(G["a"]),
    GB is ++(G["b"]),
    array_list(GA, 6.0),
    array_list(GB, 8.0)
)
```

Combines naturally with Phase 9's pytree predicates — traverse the
gradient tree with `leaf/2`, query structure with `tree_structure/2`,
and so on.

### Scalar output requirement

`grad_value` requires `F` to return a scalar. Calling it with a
vector-valued `F` fails cleanly:

```seam
test("grad of vector fails") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    not grad_value(F, X, _G)       # fails — x^2 is not scalar
)
```

For the vector case, use `jacobian/3` instead.

---

## Vectorisation

### `vmap_apply(F, X, R)` and `vmap_apply(F, X, OPTS, R)`

Apply `jax.vmap(F)` to `X`. The 4-arity form takes a dict of keyword
options — `in_axes`, `out_axes`, etc.

```seam
test("vmap doubles each element") <- (
    F is ++(lambda x: x * 2),
    X is ++(jax.numpy.arange(5)),
    vmap_apply(F, X, R),
    array_list(R, [0, 2, 4, 6, 8])
)

test("vmap with in_axes=0") <- (
    F is ++(lambda x: x + 1),
    X is ++(jax.numpy.array([[0, 1], [2, 3]])),
    vmap_apply(F, X, {"in_axes": 0}, R),
    shape(R, [2, 2])
)
```

### `vmap` vs Clausal Prolog's own enumeration

`vmap` and `findall/3` both "apply a function many times", but with
different semantics:

- `vmap` is **numerical batching** — one vectorised kernel call on the
  full batch, no Python-level loop. Best for numerical workloads.
- `findall(L, (leaf(TREE, L2), F(L2, L)), LS)` is **relational
  enumeration** — each solution is a choice point, with
  backtracking and unification.

Use `vmap_apply` when the work is pure array math; use `findall` +
predicate iteration when you need backtracking.

---

## Compilation

### `jit_compile(F, F_JIT)`

Returns a JIT-compiled callable. This is the one predicate that *does*
return a function (the whole point of JIT is the compiled artifact):

```seam
test("jit_compile") <- (
    F is ++(lambda x: x * x),
    jit_compile(F, F_JIT),
    X is ++(jax.numpy.array(5.0)),
    Y is ++(F_JIT(X)),
    array_list(Y, 25.0)
)
```

Caveats:

- Under `jit`, JAX replaces array arguments with abstract tracers.
  Python closures that capture concrete arrays get "baked in" at trace
  time — if the closure needs to change, re-compile.
- JIT caches live on the function object. Repeated `jit_compile(F, ...)`
  with the same `F` returns the same cached compilation.
- `jax.clear_caches()` (still available via `++()`) clears the cache
  across all JAX-compiled functions if memory is an issue.

### `pmap_apply`

Parallel-map across devices. Degrades to `vmap`-like semantics on
single-device hosts. Most useful on multi-device setups (multiple GPUs
or TPU cores). Signature mirrors `vmap_apply`.

---

## Inspection

### `make_jaxpr(F, X, JAXPR)`

Returns the symbolic trace of `F` at `X` — a JAX `Jaxpr` object
describing the computation graph. Useful for debugging or for printing
the traced form.

```seam
test("make_jaxpr captures computation") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jax.numpy.array(3.0)),
    make_jaxpr(F, X, JP),
    JP != ++(None)
)
```

### `eval_shape(F, X, SHAPE_DTYPE)`

Abstract evaluation — returns a `ShapeDtypeStruct` pytree describing
what the output would look like, without actually computing it.
Cheap; works even for inputs that would need terabytes if
materialised.

```seam
test("eval_shape doesn't allocate") <- (
    F is ++(lambda x: x + 1),
    X is ++(jax.ShapeDtypeStruct((1000000, 1000000), jax.numpy.float32)),
    eval_shape(F, X, SD),
    S is ++(SD.shape),
    S == (1000000, 1000000)
)
```

Use this to reason about shape compatibility before committing
memory.

---

## Deferred

- **Custom `pjit` / `shard_map`.** These are sharding-aware compilation
  primitives — scheduled for Phase 13 alongside `device_put` / `mesh`.
- **`checkpoint` / `remat`.** Gradient-checkpointing for memory-vs-recompute
  trade-offs. Useful in training loops; not native enough to Clausal Prolog to
  justify right now.
- **Stateful transforms via `linen.apply` (Flax) or Equinox.** Those
  libraries wrap the functional transforms inside a module system. A
  separate wrapper phase would be the right home.
