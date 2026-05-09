"""top_k_proofs — DNF lineage truncated to the top-k highest-probability proofs.

Algebra:

    K = frozenset[frozenset[(input_id, polarity)]]   (DNF over input literals)
    0 = frozenset()                                   (no proofs ⇒ false)
    1 = frozenset({frozenset()})                      (empty proof ⇒ true)
    a ⊕ b = top_k(a ∪ b)                              (k-truncated union of proofs)
    a ⊗ b = top_k({c_a ∪ c_b for c_a in a, c_b in b   if consistent})

A proof is a conjunction of input literals — each literal naming one input
fact (`input_id`) and a polarity. The DNF carrier records *which* input
facts were combined to derive a tuple, allowing inclusion-exclusion to
compute the tuple's exact probability rather than the over-counting
``add_mult_prob`` produces when proofs share inputs.

The semiring is **stateful per ``evaluate``**: ``tagging_fn`` allocates a
fresh ``input_id`` on each call and records the input's probability.
Construct one instance per solve via the ``top_k_proofs(k=...)`` factory:

    out = evaluate(top_k_proofs(k=3), facts, goal)

The differentiable variant (``diff_top_k_proofs``) inherits this carrier
unchanged and overrides ``recover_fn`` so autograd traces back through
the inclusion-exclusion sum.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from clausal.modules.provenance.protocol import AggregateProvenance


# ── Type aliases ─────────────────────────────────────────────────────────
# A literal is (input_id: int, polarity: bool).
# A conjunction is a frozenset of literals — order-insensitive, hashable.
# A DNF (Disj) is a frozenset of conjunctions.
Conj = frozenset           # type: ignore[type-arg]
Disj = frozenset           # type: ignore[type-arg]


# Module-level constants — both are interned so == / hash are O(1) for
# the common cases.
_DISJ_ZERO: Disj = frozenset()
_DISJ_ONE: Disj = frozenset({frozenset()})


# ── Internal helpers ─────────────────────────────────────────────────────


def _consistent(conj: Conj) -> bool:
    """A conjunction is inconsistent iff it contains both (i, True) and (i, False)."""
    seen: dict[int, bool] = {}
    for (i, p) in conj:
        if i in seen and seen[i] != p:
            return False
        seen[i] = p
    return True


def _conj_prob(conj: Conj, input_probs: dict[int, float]) -> float:
    """Probability of one conjunction under independence: ∏ literal probs."""
    p = 1.0
    for (i, pol) in conj:
        ip = input_probs.get(i, 0.5)
        p *= ip if pol else (1.0 - ip)
    return p


def _inclusion_exclusion(disj: Disj, input_probs: dict[int, float]) -> float:
    """P(C1 ∨ C2 ∨ … ∨ Cn) via inclusion-exclusion. ``input_probs`` are floats."""
    if not disj:
        return 0.0
    conj_list = list(disj)
    # Special-case: ``one()`` (the empty conjunction). ``len(conj_list) == 1``
    # and that conj has no literals — its probability is 1.0.
    total = 0.0
    n = len(conj_list)
    for r in range(1, n + 1):
        sign = 1.0 if (r % 2 == 1) else -1.0
        for combo in combinations(conj_list, r):
            merged: frozenset = frozenset()
            for c in combo:
                merged = merged | c
            if not _consistent(merged):
                continue
            total += sign * _conj_prob(merged, input_probs)
    return total


def _truncate(disj: Disj, k: int, input_probs: dict[int, float]) -> Disj:
    """Keep the k conjunctions with the largest standalone probabilities."""
    if len(disj) <= k:
        return disj
    ranked = sorted(disj, key=lambda c: -_conj_prob(c, input_probs))
    return frozenset(ranked[:k])


# ── Semiring ─────────────────────────────────────────────────────────────


class TopKProofs(AggregateProvenance):
    """k-truncated DNF provenance semiring.

    Stateful per ``evaluate`` call: ``tagging_fn`` allocates fresh input
    ids and records the input's probability. Build a fresh instance via
    the ``top_k_proofs(k=...)`` factory each solve.
    """

    name = "top_k_proofs"

    def __init__(self, k: int = 3) -> None:
        if not isinstance(k, int) or k < 1:
            raise ValueError(f"top_k_proofs: k must be a positive int, got {k!r}")
        self.k = k
        # Maps input_id → original user-supplied tag (a Python float here;
        # the differentiable subclass uses tensors). The semiring instance
        # is fresh per solve, so these accumulate just for this run.
        self._input_tags: dict[int, Any] = {}
        # Float-cast scalars used by ⊕ ranking and the non-diff recover_fn.
        self._input_prob_scalars: dict[int, float] = {}

    # ── Algebra ──────────────────────────────────────────────────────────
    def zero(self) -> Disj:
        return _DISJ_ZERO

    def one(self) -> Disj:
        return _DISJ_ONE

    def add(self, a: Disj, b: Disj) -> Disj:
        union: Disj = a | b
        return _truncate(union, self.k, self._input_prob_scalars)

    def mult(self, a: Disj, b: Disj) -> Disj:
        if not a or not b:
            return _DISJ_ZERO
        out: list = []
        for ca in a:
            for cb in b:
                merged = ca | cb
                if _consistent(merged):
                    out.append(merged)
        return _truncate(frozenset(out), self.k, self._input_prob_scalars)

    def negate(self, a: Disj) -> Disj:
        """¬(C1 ∨ … ∨ Cn) = ¬C1 ∧ … ∧ ¬Cn = (∨ ¬lit_in_C1) ∧ ….

        Each negated conjunction becomes an OR of negated literals; the
        outer AND is computed via repeated semiring ``mult`` (which
        truncates after each step).
        """
        if not a:
            return self.one()
        result: Disj = self.one()
        for conj in a:
            neg_dnf: Disj = frozenset(
                frozenset({(i, not p)}) for (i, p) in conj
            )
            result = self.mult(result, neg_dnf)
        return result

    def saturated(self, old: Disj, new: Disj) -> bool:
        # Both are frozensets — equality on the conjunction set.
        return old == new

    def discard(self, a: Disj) -> bool:
        # An empty DNF is the false formula — prune.
        return not a

    # ── Boundary ─────────────────────────────────────────────────────────
    def tagging_fn(self, user_tag: Any) -> Disj:
        """Lift a user-supplied probability into a singleton DNF.

        Allocates a fresh ``input_id`` for the tag; stores both the
        original tag and a float scalar (for ranking) on the instance.
        """
        fresh_id = len(self._input_tags)
        self._input_tags[fresh_id] = user_tag
        self._input_prob_scalars[fresh_id] = self._to_float_scalar(user_tag)
        return frozenset({frozenset({(fresh_id, True)})})

    def recover_fn(self, internal_tag: Disj) -> float:
        """Reduce a DNF tag to a probability via inclusion-exclusion."""
        return _inclusion_exclusion(internal_tag, self._input_prob_scalars)

    # ── Aggregation (semiring-aware) ─────────────────────────────────────
    def aggregate_count(self, tags: list[Disj]) -> float:
        """Expected count: Σ P(t_i), each P(·) by inclusion-exclusion."""
        return sum(self.recover_fn(t) for t in tags)

    def aggregate_sum(self, vals_tags: list[tuple[float, Disj]]) -> float:
        return sum(v * self.recover_fn(t) for v, t in vals_tags)

    def aggregate_argmax(
        self, vals_tags: list[tuple[float, Disj]],
    ) -> tuple:
        if not vals_tags:
            return (None, _DISJ_ZERO)
        best_v = None
        best_p = -1.0
        best_t: Disj = _DISJ_ZERO
        for v, t in vals_tags:
            p = self.recover_fn(t)
            if p > best_p or (p == best_p and best_v is not None and v > best_v):
                best_p = p
                best_v = v
                best_t = t
        return (best_v, best_t)

    # ── Helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _to_float_scalar(x: Any) -> float:
        """Cast a user tag to a Python float (detached for tensors)."""
        # Bool: True → 1.0, False → 0.0. Keep this branch above the int
        # branch; ``isinstance(True, int)`` is True in Python.
        if isinstance(x, bool):
            return 1.0 if x else 0.0
        if isinstance(x, (int, float)):
            return float(x)
        # Tensor types: detach + extract scalar without disturbing autograd.
        item = getattr(x, "item", None)
        if callable(item):
            try:
                detach = getattr(x, "detach", None)
                target = detach() if callable(detach) else x
                return float(target.item())
            except Exception:
                pass
        return float(x)


# ── Public factory ───────────────────────────────────────────────────────


def top_k_proofs(k: int = 3) -> TopKProofs:
    """Construct a fresh ``TopKProofs`` semiring instance.

    A new instance is required per ``evaluate`` call because the semiring
    accumulates input-id ↔ probability bindings during fact loading.
    """
    return TopKProofs(k)


__all__ = [
    "TopKProofs",
    "top_k_proofs",
    "Conj",
    "Disj",
]
