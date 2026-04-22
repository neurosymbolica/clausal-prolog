"""clausal.modules.py.jax_transforms — JAX function transforms.

JAX's higher-order transforms — ``grad``, ``jit``, ``vmap``, ``jvp``,
``vjp`` — are pure functions of functions. Unlike PyTorch's
autograd (which is a stateful training-time concept that has to stay
behind ``++()``), these transforms compose naturally with Clausal:
take a Python callable plus inputs, compute the transformed output,
unify.

Import usage::

    -import_from(py.jax_transforms, [
        grad_value, value_and_grad,
        jvp_value, vjp_value,
        jacobian, jacfwd, jacrev, hessian,
        vmap_apply, pmap_apply, jit_compile,
        make_jaxpr, eval_shape,
    ])

Phase 12 — Function Transforms
--------------------------------
All predicates are Tier 1 pure.

Differentiation:
    grad_value(F, X, G)                Gradient of F at X
    value_and_grad(F, X, (V, G))       Value and gradient — tuple result
    jvp_value(F, PRIMALS, TANGENTS, (P, T))
                                       Forward-mode JVP; tuple (primal, tangent)
    vjp_value(F, X, (V, VJP_FN))       Reverse-mode VJP; vjp_fn is a callable
    jacobian(F, X, J)                  Jacobian via reverse-mode (alias of jacrev)
    jacfwd(F, X, J)                    Forward-mode Jacobian
    jacrev(F, X, J)                    Reverse-mode Jacobian
    hessian(F, X, H)                   Hessian matrix

Vectorisation and compilation:
    vmap_apply(F, X, R)                Apply vmap(F) to X
    vmap_apply(F, X, OPTS, R)          OPTS is a dict — in_axes, out_axes, ...
    pmap_apply(F, X, R)                Parallel-map (needs multiple devices)
    pmap_apply(F, X, OPTS, R)
    jit_compile(F, F2)                 Return a JIT-compiled callable

Inspection:
    make_jaxpr(F, X, JAXPR)            Symbolic trace of F at X
    eval_shape(F, X, SHAPE_DTYPE_TREE) Abstract-eval — shapes without execution

Design note — one-shot predicates
----------------------------------
``jax.grad(f)`` returns a *function*. In procedural code you'd call
that function many times. In Clausal, the **one-shot** form (``take f,
take x, produce the result``) aligns with the declarative style. For
the rare case where a user genuinely needs the transformed function
itself as a value, ``jit_compile/2`` returns the callable.

Tuple returns
--------------
``value_and_grad``, ``jvp_value``, and ``vjp_value`` return Python
tuples. Decompose them with Clausal's own tuple syntax, consistent with
the decompositions in Phase 4 linalg (``svd``, ``qr``, ``eig``)::

    value_and_grad(F, X, RESULT),
    RESULT is (V, G)

Callables from Clausal
-----------------------
The first argument (``F``) is a Python callable, built inline with
``++()``. Same pattern as ``MatrixFunction`` in ``scipy_linalg.py`` and
the ``tree_map`` / ``tree_reduce`` predicates in Phase 9.

    F is ++(lambda x: x ** 2),
    grad_value(F, 3.0, G)
"""

from __future__ import annotations

from clausal.modules.py._helpers import _pred, _pure
from clausal.modules.py.jax import _ensure_jax, _jx


# ═══════════════════════════════════════════════════════════════════════════
# Differentiation
# ═══════════════════════════════════════════════════════════════════════════

grad_value = _pred("grad_value",
    (3, _pure(lambda f, x: _jx().grad(f)(x))),
)

value_and_grad = _pred("value_and_grad",
    (3, _pure(lambda f, x: tuple(_jx().value_and_grad(f)(x)))),
)

# PRIMALS and TANGENTS must be tuples for jax.jvp; accept either list
# or tuple from Clausal side.
jvp_value = _pred("jvp_value",
    (4, _pure(lambda f, primals, tangents:
              tuple(_jx().jvp(f, tuple(primals), tuple(tangents))))),
)

# vjp returns (primals_out, vjp_fn). The vjp_fn is a callable — users
# invoke it via ++() to apply cotangents.
vjp_value = _pred("vjp_value",
    (3, _pure(lambda f, x: tuple(_jx().vjp(f, x)))),
)

jacobian = _pred("jacobian",
    (3, _pure(lambda f, x: _jx().jacobian(f)(x))),
)

jacfwd = _pred("jacfwd",
    (3, _pure(lambda f, x: _jx().jacfwd(f)(x))),
)

jacrev = _pred("jacrev",
    (3, _pure(lambda f, x: _jx().jacrev(f)(x))),
)

hessian = _pred("hessian",
    (3, _pure(lambda f, x: _jx().hessian(f)(x))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Vectorisation and compilation
# ═══════════════════════════════════════════════════════════════════════════

vmap_apply = _pred("vmap_apply",
    (3, _pure(lambda f, x: _jx().vmap(f)(x))),
    (4, _pure(lambda f, x, opts: _jx().vmap(f, **opts)(x))),
)

pmap_apply = _pred("pmap_apply",
    (3, _pure(lambda f, x: _jx().pmap(f)(x))),
    (4, _pure(lambda f, x, opts: _jx().pmap(f, **opts)(x))),
)

jit_compile = _pred("jit_compile",
    (2, _pure(lambda f: _jx().jit(f))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Inspection
# ═══════════════════════════════════════════════════════════════════════════

make_jaxpr = _pred("make_jaxpr",
    (3, _pure(lambda f, x: _jx().make_jaxpr(f)(x))),
)

eval_shape = _pred("eval_shape",
    (3, _pure(lambda f, x: _jx().eval_shape(f, x))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Differentiation
    "grad_value", "value_and_grad",
    "jvp_value", "vjp_value",
    "jacobian", "jacfwd", "jacrev", "hessian",
    # Vectorisation + compilation
    "vmap_apply", "pmap_apply", "jit_compile",
    # Inspection
    "make_jaxpr", "eval_shape",
]
