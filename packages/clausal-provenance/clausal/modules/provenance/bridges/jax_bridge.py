"""JAX bridge for ``diff_top_k_proofs``.

Mirror of ``torch_bridge.py`` using ``jax.custom_vjp``: forward computes
the scalar probability and saves the sparse Jacobian; the vjp rule
returns ``cotangent · jacobian``.

Equivalent to the implicit autograd path baked into
``DiffTopKProofs.recover_fn``; the bridge is an opt-in optimisation when
the same DNF is decoded many times.
"""

from __future__ import annotations

from itertools import combinations

from clausal.modules.provenance.semirings._framework import jax_module
from clausal.modules.provenance.bridges.torch_bridge import (
    _serialise_disj,
    _value_and_jacobian,
)


def _custom_vjp_recover():
    """Build the ``jax.custom_vjp``-decorated recover function lazily."""
    j, jnp = jax_module()

    def _recover(probs_vec, disj_serialised):
        import numpy as np
        np_probs = np.asarray(probs_vec)
        value, _jac = _value_and_jacobian(disj_serialised, np_probs)
        return jnp.array(value, dtype=probs_vec.dtype)

    # ``disj_serialised`` is a static (non-tensor) Python tuple — declare it
    # nondiff so jax doesn't try to trace it.
    from functools import partial

    @partial(j.custom_vjp, nondiff_argnums=(1,))
    def recover(probs_vec, disj_serialised):
        return _recover(probs_vec, disj_serialised)

    def fwd(probs_vec, disj_serialised):
        import numpy as np
        np_probs = np.asarray(probs_vec)
        value, jac = _value_and_jacobian(disj_serialised, np_probs)
        return (jnp.array(value, dtype=probs_vec.dtype),
                jnp.array(jac, dtype=probs_vec.dtype))

    def bwd(disj_serialised, residual_jac, cotangent):
        # cotangent is a scalar; return cotangent * jac for probs_vec.
        # Per nondiff_argnums, the disj is passed as the first arg here.
        return (cotangent * residual_jac,)

    recover.defvjp(fwd, bwd)
    return recover


_cached_fn = None


def topk_recover_jax(disj, input_probs_dict):
    """Run the inclusion-exclusion sum via ``jax.custom_vjp``.

    Parameters
    ----------
    disj
        The DNF (a frozenset of frozensets of (input_id, polarity) tuples).
    input_probs_dict
        Maps ``input_id`` → probability *jax array*. All arrays must share
        a dtype.

    Returns
    -------
    A 0-d jax array with autograd-traced gradient w.r.t. each array in
    ``input_probs_dict``.
    """
    global _cached_fn
    _j, jnp = jax_module()
    if _cached_fn is None:
        _cached_fn = _custom_vjp_recover()

    if not input_probs_dict:
        return jnp.array(0.0)
    n = max(input_probs_dict) + 1
    sample = next(iter(input_probs_dict.values()))
    parts = []
    for i in range(n):
        if i in input_probs_dict:
            parts.append(jnp.asarray(input_probs_dict[i]).reshape(()))
        else:
            parts.append(jnp.array(0.0, dtype=sample.dtype))
    probs_vec = jnp.stack(parts)

    serialised = tuple(tuple(c) for c in _serialise_disj(disj))
    if not serialised:
        return jnp.array(0.0, dtype=sample.dtype)

    return _cached_fn(probs_vec, serialised)


__all__ = ["topk_recover_jax"]
