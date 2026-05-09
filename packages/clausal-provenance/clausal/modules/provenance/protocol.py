"""Provenance semiring protocol.

A provenance semiring `(K, ⊕, ⊗, 0, 1)` is the algebraic structure the
bottom-up engine evaluates rule programs over. ⊕ aggregates alternative
derivations of the same fact; ⊗ combines body atoms within one derivation.

Concrete semirings live in ``clausal.modules.provenance.semirings``.
The engine in ``engine.py`` is generic over any subclass of ``Provenance``.
"""

from __future__ import annotations

from typing import Generic, TypeVar


Tag = TypeVar("Tag")


class Provenance(Generic[Tag]):
    """A provenance semiring.

    Concrete subclasses must override ``zero``, ``one``, ``add``, ``mult``.
    ``negate`` is required only for stratified-negation programs.
    ``saturated``, ``discard``, ``tagging_fn`` and ``recover_fn`` have
    sensible defaults.
    """

    name: str = "<unnamed>"

    # ── Algebra ──────────────────────────────────────────────────────────
    def zero(self) -> Tag:
        """Additive identity. ``add(zero(), x) == x``."""
        raise NotImplementedError

    def one(self) -> Tag:
        """Multiplicative identity. ``mult(one(), x) == x``."""
        raise NotImplementedError

    def add(self, a: Tag, b: Tag) -> Tag:
        """⊕ — combine alternative derivations of the same fact."""
        raise NotImplementedError

    def mult(self, a: Tag, b: Tag) -> Tag:
        """⊗ — combine body atoms within one derivation."""
        raise NotImplementedError

    # ── Stratified extras ────────────────────────────────────────────────
    def negate(self, a: Tag) -> Tag:
        """¬ — required for stratified negation. Default: not supported."""
        raise NotImplementedError(
            f"Semiring {self.name!r} does not support negation"
        )

    def saturated(self, old: Tag, new: Tag) -> bool:
        """Per-tuple fixpoint check. Default: equality on the tag.

        Override when equality is too strict (e.g., ``add_mult_prob`` may
        want a tolerance to terminate on floating-point drift).
        """
        return old == new

    def discard(self, a: Tag) -> bool:
        """Cull a tuple whose tag has fallen below threshold. Default: never."""
        return False

    # ── Boundary ─────────────────────────────────────────────────────────
    # Identity by default; semirings whose internal carrier differs from
    # the user-facing tag form override these.
    def tagging_fn(self, user_tag):
        """Lift user-supplied tag into the engine's internal representation."""
        return user_tag

    def recover_fn(self, internal_tag):
        """Lower an internal tag back to the user-facing form."""
        return internal_tag


class AggregateProvenance(Provenance):
    """Extension for semirings supporting semiring-aware aggregation.

    Boolean Datalog gets ``count``/``sum``/``argmax`` for free (cardinality,
    plain sum, plain argmax). Probabilistic semirings need expectation-aware
    versions; see phase P-3.
    """

    def aggregate_count(self, tags: list) -> "Tag":
        raise NotImplementedError

    def aggregate_sum(self, vals_tags: list[tuple[float, "Tag"]]) -> "Tag":
        raise NotImplementedError

    def aggregate_argmax(
        self, vals_tags: list[tuple[float, "Tag"]],
    ) -> tuple[float, "Tag"]:
        raise NotImplementedError


class NonGroundTupleError(Exception):
    """A `-bottom_up` rule body produced a head tuple with unbound variables.

    Bottom-up Datalog operates on a ground-tuple least fixpoint; partial
    tuples are not representable. The error message identifies the rule,
    the offending tuple, and the unbound variable(s).
    """


__all__ = [
    "Provenance",
    "AggregateProvenance",
    "Tag",
    "NonGroundTupleError",
]
