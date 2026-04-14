"""Destructive-reuse as an independent ``analyse → apply`` pass.

The analysis is the one that landed in D6b
(:func:`clausal.logic.compiler.destructive_reuse.analyse_ir`);
``analyse`` here is a thin wrapper that returns the result
wrapped in a :class:`DRPlan` so the pass contract mirrors the
other E-slice optimisations.

``apply`` rewrites the IR by setting
:attr:`~clausal.logic.compiler.ir.SubCall.destructive_reuse` to
``True`` on the eligible SubCall ops.  Today lowering does not
read that hint — the legacy path still runs destructive-reuse via
a pre-``terms_to_goalop`` body rewrite in
:class:`~clausal.logic.compiler.strategy.TrampolineStrategy.preprocess_clause`.
Applying the IR rewrite alongside is verification-only; D7c + E's
lowering-reads-hints step will retire the legacy rewrite.

Contract:

- ``analyse(ir, head, db=None) -> DRPlan`` is **pure** — no
  side effects, returns a plan object with only hashable state.
- ``apply(ir, plan) -> ir`` is **idempotent**: applying twice
  yields the same IR as applying once.  Empty plan is a no-op
  (returns *ir* unchanged, modulo a shallow copy of the
  Sequence).
- ``apply`` returns a new :class:`Sequence`; input *ir* is not
  mutated.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..destructive_reuse import analyse_ir as _legacy_analyse_ir


@dataclasses.dataclass(frozen=True)
class DRPlan:
    """Destructive-reuse eligibility plan.

    :attr:`eligible` is the set of indices into the top-level
    :class:`Sequence.ops` whose :class:`SubCall` nodes are safe
    to mark ``destructive_reuse=True``.  Matches the set returned
    by the legacy D6b ``analyse_ir`` (same body → same plan).

    Frozen so ``apply`` can't accidentally mutate the plan it
    reads and so plans are hashable (useful for round-trip tests).
    """
    eligible: frozenset[int]


def analyse(ir: Any, head: Any, db: Any = None) -> DRPlan:
    """Compute the destructive-reuse plan for *ir*.

    Wraps the D6b analysis; the ``db`` parameter is accepted for
    signature parity with other E passes but is not currently
    consumed (the analysis doesn't look at meta-call inners, and
    top-level SubCall kwargs were already normalised by
    ``terms_to_goalop``).
    """
    eligible = _legacy_analyse_ir(ir, head)
    return DRPlan(eligible=frozenset(eligible))


def apply(ir: Any, plan: DRPlan) -> Any:
    """Rewrite *ir* to mark eligible SubCalls with ``destructive_reuse=True``.

    Returns a new :class:`Sequence` with a fresh ``ops`` list;
    each eligible :class:`SubCall` is replaced by a
    :func:`dataclasses.replace`-copy carrying the hint.  Other ops
    are reused by reference (shallow copy of the list).

    Empty plan short-circuits to *ir* unchanged (reference equality,
    not a copy) — useful for no-op detection in downstream passes.
    """
    from ..ir import Sequence, SubCall
    if not isinstance(ir, Sequence):
        return ir
    if not plan.eligible:
        return ir
    new_ops = list(ir.ops)
    for idx in plan.eligible:
        op = new_ops[idx]
        if not isinstance(op, SubCall):
            # Defensive: plan was built for a different IR shape.
            # Skip silently — analyse/apply roundtrip tests assert
            # this can't happen when the plan came from the same IR.
            continue
        if op.destructive_reuse:
            continue
        new_ops[idx] = dataclasses.replace(op, destructive_reuse=True)
    return Sequence(ops=new_ops)


__all__ = ["DRPlan", "analyse", "apply"]
