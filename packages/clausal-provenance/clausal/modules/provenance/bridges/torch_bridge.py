"""PyTorch autograd bridge for ``diff_top_k_proofs``.

Provides ``topk_recover_torch(disj, input_probs_tensor)`` which wraps
the inclusion-exclusion probability computation in a
``torch.autograd.Function``. Forward computes the scalar probability
*and* the sparse Jacobian in one numpy pass; backward returns a single
multiply.

Equivalent in value + first-order gradient to ``DiffTopKProofs.recover_fn``,
which traces through the I-E expression with autograd directly. Use this
bridge when the same DNF is decoded many times with different input
probability tensors and the per-decode I-E unrolling cost matters.
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

from clausal.modules.provenance.semirings._framework import torch_module


def _serialise_disj(disj) -> list[list[tuple[int, bool]]]:
    """Convert a frozenset-DNF into a list-of-list-of-(id, polarity).

    The conjunctions are ordered for stable Jacobian construction; the
    literals within each conjunction are sorted by id.
    """
    return [
        sorted(c, key=lambda lit: (lit[0], lit[1]))
        for c in sorted(disj, key=lambda c: (len(c), sorted(c)))
    ]


def _consistent(merged: dict[int, bool]) -> bool:
    return True   # ``merged`` is built incrementally — caller already checked


def _value_and_jacobian(
    disj: list[list[tuple[int, bool]]],
    probs,                                 # 1-D numpy array, length n
):
    """Compute scalar P(disj) and ∂P/∂p_i for every i, via inclusion-exclusion.

    Returns ``(value, jacobian)`` as numpy arrays, both ``probs.dtype``.
    """
    import numpy as np
    n_inputs = probs.shape[0]
    value = 0.0
    jac = np.zeros(n_inputs, dtype=probs.dtype)

    for r in range(1, len(disj) + 1):
        sign = 1.0 if (r % 2 == 1) else -1.0
        for combo in combinations(disj, r):
            merged: dict[int, bool] = {}
            consistent = True
            for c in combo:
                for (i, p) in c:
                    if i in merged and merged[i] != p:
                        consistent = False
                        break
                    merged[i] = p
                if not consistent:
                    break
            if not consistent:
                continue

            # Per-literal factor and full product.
            factor: dict[int, float] = {}
            for (i, pol) in merged.items():
                factor[i] = float(probs[i]) if pol else (1.0 - float(probs[i]))
            full = 1.0
            for f in factor.values():
                full *= f
            value += sign * full

            # ∂full/∂p_j: replace factor[j] with d(factor[j])/dp_j (= 1 or -1)
            # times the product of the other factors. Done robustly even
            # when factor[j] == 0.
            for (j, polj) in merged.items():
                rest = 1.0
                for (i, _pol) in merged.items():
                    if i != j:
                        rest *= factor[i]
                deriv = rest if polj else (-rest)
                jac[j] += sign * deriv

    return value, jac


def _autograd_function():
    """Build the ``torch.autograd.Function`` lazily — torch is an optional dep."""
    t = torch_module()

    class _TopKProofsFn(t.autograd.Function):
        @staticmethod
        def forward(ctx, probs_tensor, disj_serialised: list[list[tuple[int, bool]]]):
            import numpy as np
            np_probs = probs_tensor.detach().cpu().to(t.float64).numpy()
            value, jac = _value_and_jacobian(disj_serialised, np_probs)
            jac_t = t.from_numpy(jac).to(dtype=probs_tensor.dtype, device=probs_tensor.device)
            ctx.save_for_backward(jac_t)
            return t.tensor(
                float(value),
                dtype=probs_tensor.dtype, device=probs_tensor.device,
            )

        @staticmethod
        def backward(ctx, grad_output):
            (jac,) = ctx.saved_tensors
            return grad_output * jac, None

    return _TopKProofsFn


_cached_fn = None


def topk_recover_torch(disj, input_probs_dict):
    """Run the inclusion-exclusion sum via ``torch.autograd.Function``.

    Parameters
    ----------
    disj
        The DNF (a frozenset of frozensets of (input_id, polarity) tuples).
    input_probs_dict
        Maps ``input_id`` → probability *tensor*. The tensors must share a
        dtype and device.

    Returns
    -------
    A 0-d tensor with autograd-traced gradient w.r.t. each tensor in
    ``input_probs_dict``.
    """
    global _cached_fn
    t = torch_module()
    if _cached_fn is None:
        _cached_fn = _autograd_function()

    # Stack the input tensors into a single 1-D vector indexed by input_id.
    if not input_probs_dict:
        return t.tensor(0.0)
    n = max(input_probs_dict) + 1
    sample = next(iter(input_probs_dict.values()))
    # Build the vector while preserving each tensor's leaf-ness for
    # autograd: ``stack`` keeps the graph; pad missing ids with detached zeros.
    parts: list = []
    for i in range(n):
        if i in input_probs_dict:
            parts.append(input_probs_dict[i].reshape(()))
        else:
            parts.append(t.zeros((), dtype=sample.dtype, device=sample.device))
    probs_vec = t.stack(parts)

    serialised = _serialise_disj(disj)
    if not serialised:
        return t.zeros((), dtype=sample.dtype, device=sample.device)

    return _cached_fn.apply(probs_vec, serialised)


__all__ = ["topk_recover_torch"]
