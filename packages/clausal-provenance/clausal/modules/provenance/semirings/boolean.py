"""Boolean semiring (B, ∨, ∧, ⊥, ⊤) — plain Datalog set semantics."""

from __future__ import annotations

from clausal.modules.provenance.protocol import AggregateProvenance


class Boolean(AggregateProvenance):
    name = "boolean"

    def zero(self) -> bool:
        return False

    def one(self) -> bool:
        return True

    def add(self, a: bool, b: bool) -> bool:
        return a or b

    def mult(self, a: bool, b: bool) -> bool:
        return a and b

    def negate(self, a: bool) -> bool:
        return not a

    def discard(self, a: bool) -> bool:
        # ``False``-tagged tuples don't belong in the relation — under set
        # semantics they correspond to "not derived", not "derived
        # negatively". Without this, ``not P(x)`` would still record an
        # entry for the head with tag ``False`` instead of the head
        # simply not being in the relation.
        return a is False

    # ── Aggregation ──────────────────────────────────────────────────
    def aggregate_count(self, tags: list) -> int:
        """Cardinality: number of True-tagged entries."""
        return sum(1 for t in tags if t)

    def aggregate_sum(self, vals_tags: list) -> float:
        """Plain sum over values whose tag is True."""
        total: float = 0
        for v, t in vals_tags:
            if t:
                total = total + v
        return total

    def aggregate_argmax(self, vals_tags: list):
        """Largest value among the True-tagged entries.

        Returns ``(value, True)`` or ``(None, False)`` when nothing is
        True-tagged.
        """
        best_v = None
        for v, t in vals_tags:
            if t and (best_v is None or v > best_v):
                best_v = v
        if best_v is None:
            return (None, False)
        return (best_v, True)


# Singleton — the public-API value users pass to `solve`.
boolean = Boolean()
