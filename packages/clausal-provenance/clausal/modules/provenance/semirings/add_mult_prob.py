"""add_mult_prob — independence-assumption probability semiring on [0, 1].

Algebra:

    K = [0, 1]
    0 = 0.0
    1 = 1.0
    a ⊕ b = clip(a + b − a·b, 0, 1)        # inclusion–exclusion / noisy-OR
    a ⊗ b = a · b

Treats alternative derivations as independent events. Not strictly correct
when the same input fact appears in multiple derivations of one tuple
(over-counting); ``top_k_proofs`` (P-4) tracks which proofs share inputs
and so avoids that. ``add_mult_prob`` is the cheap and useful baseline —
~1 LOC per operation, no tensor framework needed.
"""

from __future__ import annotations

from clausal.modules.provenance.protocol import AggregateProvenance


_EPSILON = 1e-9
_FIXPOINT_TOL = 1e-9


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


class AddMultProb(AggregateProvenance):
    name = "add_mult_prob"

    def zero(self) -> float:
        return 0.0

    def one(self) -> float:
        return 1.0

    def add(self, a: float, b: float) -> float:
        # Inclusion-exclusion under independence: P(A ∨ B) = P(A) + P(B) − P(A) P(B).
        return _clip01(a + b - a * b)

    def mult(self, a: float, b: float) -> float:
        return a * b

    def negate(self, a: float) -> float:
        return _clip01(1.0 - a)

    def saturated(self, old: float, new: float) -> bool:
        # Floating-point fixpoint check — equality is too strict for the
        # noisy-OR aggregation to terminate.
        return abs(new - old) <= _FIXPOINT_TOL

    def discard(self, a: float) -> bool:
        # Optional pruning: tags below ε do not meaningfully contribute.
        return a <= _EPSILON

    # ── Aggregation (semiring-aware = expectation under independence) ──
    def aggregate_count(self, tags: list[float]) -> float:
        """Expected count: ``Σ p_i`` (under the independence assumption)."""
        total = 0.0
        for t in tags:
            total += t
        return total

    def aggregate_sum(self, vals_tags: list[tuple[float, float]]) -> float:
        """Expected sum: ``Σ v_i · p_i``."""
        total = 0.0
        for v, t in vals_tags:
            total += v * t
        return total

    def aggregate_argmax(
        self, vals_tags: list[tuple[float, float]],
    ) -> tuple:
        """Maximum-likelihood value: ``(v*, p*)`` with ``p* = max p_i``.

        Ties broken by the value's natural order. Returns
        ``(None, 0.0)`` for an empty list.
        """
        best_v = None
        best_p = -1.0
        for v, t in vals_tags:
            if t > best_p or (t == best_p and best_v is not None and v > best_v):
                best_p = t
                best_v = v
        if best_v is None:
            return (None, 0.0)
        return (best_v, best_p)


# Singleton — public API value users pass to `solve`.
add_mult_prob = AddMultProb()
