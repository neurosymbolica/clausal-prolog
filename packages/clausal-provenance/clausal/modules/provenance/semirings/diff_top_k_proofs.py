"""diff_top_k_proofs — differentiable top-k-proofs.

Same DNF carrier as ``top_k_proofs``. The proof-selection step (top-k
truncation) is non-differentiable — we rank conjunctions by their
detached scalar probability — but the selected DNF's *probability* is a
smooth function of the input tags. ``recover_fn`` recomputes the
inclusion-exclusion sum using the original input *tensors*, so PyTorch /
JAX autograd traces back through it naturally.

Concretely: the engine produces a (small) DNF for each derived tuple at
fixpoint. Then for each goal answer we evaluate

    P(disj) = Σ_{∅ ≠ S ⊆ disj} (-1)^(|S|+1) · ∏_{lit in ⋃ S} factor(lit)

with ``factor(i, True) = p_i`` and ``factor(i, False) = 1 - p_i``,
where ``p_i`` is the original input *tensor*. Backward propagation
through this expression gives the correct sparse Jacobian.

For an explicit autograd-Function path (sparse Jacobian × upstream grad
in a single step, useful when ``recover_fn`` is called many times for
the same DNF), see ``bridges/torch_bridge.py`` and
``bridges/jax_bridge.py``.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from clausal.modules.provenance.semirings.top_k_proofs import (
    TopKProofs,
    Disj,
    _consistent,
)
from clausal.modules.provenance.semirings._framework import (
    detect_framework,
    torch_module,
    jax_module,
)


# ── Tensor-aware inclusion-exclusion ─────────────────────────────────────


def _conj_prob_tensor(conj, input_tags, one_value):
    """Tensor-valued probability of one conjunction.

    Multiplies the original input tensors (preserving autograd) for each
    literal. ``one_value`` is the framework's "tensor 1" (used when the
    conjunction is empty — ``one()`` reduces to probability 1).
    """
    out = None
    for (i, pol) in conj:
        ip = input_tags[i]
        factor = ip if pol else (1.0 - ip)
        out = factor if out is None else out * factor
    return one_value if out is None else out


def _ie_tensor(disj: Disj, input_tags: dict[int, Any], one_value, zero_value):
    """Inclusion-exclusion sum, tensor-valued. Returns ``zero_value`` for ⊥."""
    if not disj:
        return zero_value
    conj_list = list(disj)
    n = len(conj_list)
    total = None
    for r in range(1, n + 1):
        sign = 1.0 if (r % 2 == 1) else -1.0
        for combo in combinations(conj_list, r):
            merged: frozenset = frozenset()
            for c in combo:
                merged = merged | c
            if not _consistent(merged):
                continue
            term = _conj_prob_tensor(merged, input_tags, one_value)
            term = term if sign > 0 else -term
            total = term if total is None else total + term
    return zero_value if total is None else total


def _framework_unit_tensor(input_tags: dict[int, Any]):
    """Detect framework from any tensor in ``input_tags`` and return (one, zero).

    Picks the dtype/device from any tensor input. For an empty input set
    we fall back to plain Python floats — but in that situation
    ``recover_fn`` is also working on ⊥ or on the engine's bookkeeping
    constant and the caller path doesn't depend on autograd anyway.
    """
    if not input_tags:
        return 1.0, 0.0
    # Sample any input
    sample = next(iter(input_tags.values()))
    fw = detect_framework(sample)
    if fw == "torch":
        t = torch_module()
        # Match dtype/device so resulting tensors compose without warning.
        return (t.ones((), dtype=sample.dtype, device=sample.device),
                t.zeros((), dtype=sample.dtype, device=sample.device))
    if fw == "jax":
        _j, jnp = jax_module()
        return (jnp.array(1.0, dtype=sample.dtype),
                jnp.array(0.0, dtype=sample.dtype))
    return 1.0, 0.0


# ── Semiring ─────────────────────────────────────────────────────────────


class DiffTopKProofs(TopKProofs):
    """Differentiable variant of ``TopKProofs``.

    ⊕, ⊗, and the DNF carrier are inherited unchanged — selection uses
    detached scalar probabilities. ``recover_fn`` recomputes the
    inclusion-exclusion sum on the original tensor inputs so autograd
    traces backward through it.
    """

    name = "diff_top_k_proofs"

    def recover_fn(self, internal_tag: Disj) -> Any:
        one_value, zero_value = _framework_unit_tensor(self._input_tags)
        return _ie_tensor(internal_tag, self._input_tags, one_value, zero_value)

    # ── Aggregation (tensor-typed) ──────────────────────────────────────
    def aggregate_count(self, tags: list[Disj]) -> Any:
        if not tags:
            return 0.0
        out = None
        for t in tags:
            p = self.recover_fn(t)
            out = p if out is None else out + p
        return out if out is not None else 0.0

    def aggregate_sum(self, vals_tags: list[tuple[float, Disj]]) -> Any:
        if not vals_tags:
            return 0.0
        out = None
        for v, t in vals_tags:
            p = self.recover_fn(t)
            term = v * p
            out = term if out is None else out + term
        return out if out is not None else 0.0


# ── Public factory ───────────────────────────────────────────────────────


def diff_top_k_proofs(k: int = 3) -> DiffTopKProofs:
    """Construct a fresh ``DiffTopKProofs`` semiring instance.

    A new instance is required per ``evaluate`` call because the semiring
    binds input ids to the original tensor probabilities during fact
    loading; reusing an instance across calls would conflate them.
    """
    return DiffTopKProofs(k)


__all__ = [
    "DiffTopKProofs",
    "diff_top_k_proofs",
]
