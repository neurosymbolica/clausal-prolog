"""diff_add_mult_prob — differentiable add-mult-prob over tensor tags.

Same algebra as ``add_mult_prob`` but tags are PyTorch tensors or JAX
arrays. ⊕ and ⊗ are tensor ops; gradients flow through naturally — no
custom ``autograd.Function`` is required at this tier.

    K = tensor of shape () or (...) holding values in [0, 1]
    0 = scalar 0.0 tensor
    1 = scalar 1.0 tensor
    a ⊕ b = a + b − a·b        # noisy-OR; no clip — relies on inputs ∈ [0, 1]
    a ⊗ b = a · b

Clip is *deliberately* absent: hard clipping zeros gradients at the
boundary. Inputs from a softmax are already in [0, 1]; staying inside
the algebra preserves that property up to floating-point noise. Add a
soft saturation outside the engine if needed.

Mixing torch and jax tags in one ``solve`` raises — see
``check_homogeneous`` in ``_framework``.
"""

from __future__ import annotations

from typing import Any

from clausal.modules.provenance.protocol import AggregateProvenance
from clausal.modules.provenance.semirings._framework import (
    detect_framework,
    torch_module,
    jax_module,
)


_FIXPOINT_ATOL = 1e-7
_FIXPOINT_RTOL = 1e-5
_DISCARD_THRESHOLD = 1e-9


class DiffAddMultProb(AggregateProvenance):
    """Differentiable noisy-OR / product semiring on tensor tags."""

    name = "diff_add_mult_prob"

    # The semiring itself doesn't fix a framework — the tag values
    # supplied by the user select torch vs jax per call. zero/one return
    # plain Python floats; tensor add/mult promote them via the user
    # tensor's ``+`` / ``*`` operators.
    def zero(self) -> float:
        return 0.0

    def one(self) -> float:
        return 1.0

    def add(self, a: Any, b: Any) -> Any:
        # P(A ∨ B) = P(A) + P(B) − P(A) P(B). Autograd traces through.
        return a + b - a * b

    def mult(self, a: Any, b: Any) -> Any:
        return a * b

    def negate(self, a: Any) -> Any:
        return 1.0 - a

    def saturated(self, old: Any, new: Any) -> bool:
        """Tensor-aware fixpoint check.

        Detached / no-grad equality — the saturation test is control flow,
        not part of the differentiable forward pass.
        """
        fw = detect_framework(new)
        if fw == "torch":
            t = torch_module()
            with t.no_grad():
                a = old.detach() if isinstance(old, t.Tensor) else t.tensor(old)
                b = new.detach()
                return bool(t.allclose(a, b, atol=_FIXPOINT_ATOL, rtol=_FIXPOINT_RTOL))
        if fw == "jax":
            j, jnp = jax_module()
            return bool(jnp.allclose(jnp.asarray(old), new,
                                     atol=_FIXPOINT_ATOL, rtol=_FIXPOINT_RTOL))
        # Plain Python float (no tensor inputs in this iteration yet).
        try:
            return abs(float(new) - float(old)) <= _FIXPOINT_ATOL
        except (TypeError, ValueError):
            return old == new

    def discard(self, a: Any) -> bool:
        """Optional pruning — only on plain-Python tags.

        Discarding a tensor would break the autograd graph, so for tensor
        tags we never discard. The ε prune still helps the float fast
        path during semi-naive iteration when tags happen to be scalars.
        """
        fw = detect_framework(a)
        if fw == "python":
            try:
                return float(a) <= _DISCARD_THRESHOLD
            except (TypeError, ValueError):
                return False
        return False

    # ── Aggregation (tensor-typed; gradients flow through) ─────────────
    def aggregate_count(self, tags: list) -> Any:
        """Expected count under independence: ``Σ p_i`` (tensor sum)."""
        if not tags:
            return 0.0
        out = tags[0]
        for t in tags[1:]:
            out = out + t
        return out

    def aggregate_sum(self, vals_tags: list) -> Any:
        """Expected sum: ``Σ v_i · p_i`` (tensor sum)."""
        if not vals_tags:
            return 0.0
        v0, t0 = vals_tags[0]
        out = v0 * t0
        for v, t in vals_tags[1:]:
            out = out + v * t
        return out

    def aggregate_argmax(self, vals_tags: list) -> tuple:
        """``(v*, p*)`` with the maximum tag.

        The argmax pick itself is non-differentiable; the *value* of the
        winning tag is returned with grad intact so loss can be wired
        directly to it. For a fully differentiable expectation use
        ``aggregate_sum``.
        """
        if not vals_tags:
            return (None, 0.0)
        best_v, best_t = vals_tags[0]

        def _scalar(x):
            fw = detect_framework(x)
            if fw == "torch":
                return float(x.detach().item())
            if fw == "jax":
                return float(x)
            return float(x)

        best_score = _scalar(best_t)
        for v, t in vals_tags[1:]:
            s = _scalar(t)
            if s > best_score or (s == best_score and best_v is not None and v > best_v):
                best_score = s
                best_v = v
                best_t = t
        return (best_v, best_t)


# Singleton — public API value users pass to `solve`.
diff_add_mult_prob = DiffAddMultProb()
