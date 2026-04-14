"""Tail-recursion optimisation as an independent ``analyse → apply`` pass.

The analysis is the D6a shadow that landed with
:func:`clausal.logic.compiler.tro.analyse_ir`; ``analyse`` here wraps
the result in a :class:`TROPlan` for contract parity with the other
E passes.

``apply`` sets :attr:`~clausal.logic.compiler.ir.SubCall.tail_recursive`
to ``True`` on the tail :class:`SubCall` when the clause is eligible.
Today the legacy TRO body compiler (``_compile_tro_body``) is still
the source-of-truth for TRO code generation — it bypasses
``_compile_body_impl`` entirely and runs in its own pipeline branch
from ``predicate.py``.  The IR-side ``apply`` writes the hint so
lowering-reads-hints (future E sub-slice) can drive a unified
tail-call rewrite without the bypass.

Contract:

- ``analyse(ir, head, functor, arity, db=None) -> TROPlan`` is
  **pure** — no side effects, returns a plan object with only
  hashable state.  ``(eligible, check_indices)`` mirror the D6a
  tuple exactly.
- ``apply(ir, plan) -> ir`` is **idempotent**.  Ineligible plan
  short-circuits to *ir* unchanged (reference equality).
- ``apply`` returns a new :class:`Sequence`; input *ir* is not
  mutated.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..tro import analyse_ir as _legacy_analyse_ir


@dataclasses.dataclass(frozen=True)
class TROPlan:
    """Tail-recursion eligibility plan.

    :attr:`eligible` is ``True`` iff the clause's body IR ends in
    a TRO-safe self-recursive :class:`SubCall`.
    :attr:`check_indices` is the frozenset of tail-call arg
    positions that need a runtime ``is_var()`` ground-check (empty
    when ineligible, or when no prefix goals exist).

    Matches the ``(bool, frozenset[int])`` shape that legacy
    :func:`~clausal.logic.compiler.tro.analyse_ir` already returns.
    """
    eligible: bool
    check_indices: frozenset[int]


def analyse(
    ir: Any, head: Any, functor: str, arity: int, db: Any = None,
) -> TROPlan:
    """Compute the TRO plan for *ir* against the given clause head.

    Mirrors :func:`~clausal.logic.compiler.tro.analyse_ir` arm-for-arm
    because the latter already operates on :class:`GoalOp` trees (D6a)
    and is the verified-equivalent of the legacy term-walking
    ``_detect_tro_clause``.

    ``db`` is accepted for signature parity but not yet consumed —
    the analysis reads head/arg terms directly off the IR.
    """
    eligible, check = _legacy_analyse_ir(ir, head, functor, arity)
    return TROPlan(eligible=bool(eligible), check_indices=frozenset(check))


def apply(ir: Any, plan: TROPlan) -> Any:
    """Rewrite *ir* to mark the tail :class:`SubCall` with
    ``tail_recursive=True`` when the plan says the clause is eligible.

    Returns a new :class:`Sequence` (with a fresh ops list) when the
    hint is written; returns *ir* unchanged (reference equality) for
    ineligible plans.
    """
    from ..ir import Sequence, SubCall
    if not plan.eligible:
        return ir
    if not isinstance(ir, Sequence) or not ir.ops:
        return ir
    last = ir.ops[-1]
    if not isinstance(last, SubCall):
        # Plan said eligible but tail op isn't a SubCall — defensive
        # skip.  Round-trip tests guarantee this can't happen when
        # the plan came from the same IR.
        return ir
    if last.tail_recursive:
        return ir
    new_ops = list(ir.ops)
    new_ops[-1] = dataclasses.replace(last, tail_recursive=True)
    return Sequence(ops=new_ops)


__all__ = ["TROPlan", "analyse", "apply"]
