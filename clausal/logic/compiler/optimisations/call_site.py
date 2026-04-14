"""Call-site bucket-ref specialisation as an ``analyse → apply`` pass.

The analysis is the D6c shadow
:func:`~clausal.logic.compiler.goal_trampoline.analyse_ir_bucket_refs`;
``analyse`` here wraps the result in a :class:`CallSitePlan` for
contract parity.

``apply`` walks the IR marking eligible :class:`SubCall` ops with
:attr:`~clausal.logic.compiler.ir.SubCall.direct_bucket_ref` set to
the global-key string that resolves to the pre-bound bucket
function.  The plan is scoped to a *single* clause's IR: analyse
receives ``[clause]`` so the returned entries all apply to that
clause's body; apply then rewrites the :class:`SubCall`s accordingly.

Contract:

- ``analyse(ir, head, base_globals, db=None) -> CallSitePlan`` is
  **pure** — no side effects, returns a plan with hashable state.
- ``apply(ir, plan) -> ir`` is **idempotent**.  Empty plan
  short-circuits to *ir* unchanged (reference equality).
- ``apply`` returns a new :class:`Sequence`; input *ir* is not
  mutated.

Joint-bucket entries from D6c are **not yet written as hints** —
``SubCall.direct_bucket_ref`` carries a single-position gkey
string, not the ``(pi, pj, ki, kj)``-keyed joint form.  Joint
specialisation will grow its own hint field (or a richer type
for ``direct_bucket_ref``) when lowering-reads-hints lands; E3
today covers the single-position case, which is the majority of
real call-site specialisations.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class CallSitePlan:
    """Single-position bucket-ref hints for one clause's IR.

    :attr:`hints` maps :class:`SubCall` op index (into the top-level
    ``Sequence.ops``) to the ``gkey`` global-name that resolves to
    the pre-bound bucket function.  ``apply`` writes each hint onto
    the matching :class:`SubCall.direct_bucket_ref`.

    :attr:`joint_hints` records the joint-position entries that
    D6c's legacy walker would have injected into
    ``joint_bucket_ref_map`` — carried here for future use when a
    richer hint type lands.
    """
    hints: tuple[tuple[int, str], ...]
    joint_hints: tuple[tuple[int, str], ...]


def analyse(
    ir: Any, head: Any, base_globals: dict, db: Any = None,
) -> CallSitePlan:
    """Compute the bucket-ref plan for *ir*.

    Walks ``ir.ops`` looking for :class:`SubCall` nodes whose
    ``(fname, arity, pos, static_key)`` matches an entry in the
    callee's ``_index_plans``.  Same criteria the legacy D6c
    analyser applies; reusing the canonical key-building helpers
    from ``arg_index`` keeps the gkeys byte-identical.
    """
    from ..ir import Sequence, SubCall
    from ..arg_index import _static_call_key, _bucket_key, _joint_bucket_key
    from ..terms_to_ast import term_to_ast_expr
    from clausal.logic.predicate import PredicateMeta

    if not isinstance(ir, Sequence):
        return CallSitePlan(hints=(), joint_hints=())

    hint_list: list[tuple[int, str]] = []
    joint_list: list[tuple[int, str]] = []

    for op_idx, op in enumerate(ir.ops):
        if not isinstance(op, SubCall):
            continue
        fname = op.fname
        arity = op.arity
        pred_obj = base_globals.get(fname)
        if not isinstance(pred_obj, PredicateMeta):
            continue
        if not getattr(pred_obj, "_locked", False):
            continue
        if not hasattr(pred_obj, "_index_plans"):
            continue

        arg_exprs = [term_to_ast_expr(a, {}) for a in op.args]

        # Single-position: pick the first matching bucket; legacy
        # writes all matching positions into the map, but per-call
        # ``_dispatch_call_trampoline`` uses the first it finds, so
        # a single hint on the SubCall is sufficient for the
        # single-position case.  For byte-parity with legacy we
        # record every match here — the plan stays faithful to the
        # legacy map shape.
        for pos, idx_dict in pred_obj._index_plans.items():
            if pos >= len(arg_exprs):
                continue
            key = _static_call_key(arg_exprs[pos])
            if key is None or key not in idx_dict:
                continue
            gkey = _bucket_key(fname, pos, key)
            hint_list.append((op_idx, gkey))
            break  # only need one bucket-ref hint per SubCall

        if hasattr(pred_obj, "_index_plans_joint"):
            for (pi, pj), jdict in pred_obj._index_plans_joint.items():
                if pi >= len(arg_exprs) or pj >= len(arg_exprs):
                    continue
                ki = _static_call_key(arg_exprs[pi])
                kj = _static_call_key(arg_exprs[pj])
                if ki is None or kj is None:
                    continue
                if (ki, kj) not in jdict:
                    continue
                gkey = _joint_bucket_key(fname, pi, pj, ki, kj)
                joint_list.append((op_idx, gkey))
                break

    return CallSitePlan(
        hints=tuple(hint_list),
        joint_hints=tuple(joint_list),
    )


def apply(ir: Any, plan: CallSitePlan) -> Any:
    """Write each plan hint onto the matching :class:`SubCall`.

    Returns a new :class:`Sequence` with a fresh ``ops`` list when
    any hint was written; returns *ir* unchanged (reference
    equality) when both single and joint hints are empty.

    Only single-position hints are written today — the joint-hint
    field on :class:`SubCall` doesn't exist yet.  Joint entries in
    the plan are preserved for the audit / future lowering step.
    """
    from ..ir import Sequence, SubCall
    if not isinstance(ir, Sequence):
        return ir
    if not plan.hints:
        return ir
    new_ops = list(ir.ops)
    for op_idx, gkey in plan.hints:
        op = new_ops[op_idx]
        if not isinstance(op, SubCall):
            continue
        if op.direct_bucket_ref == gkey:
            continue
        new_ops[op_idx] = dataclasses.replace(op, direct_bucket_ref=gkey)
    return Sequence(ops=new_ops)


__all__ = ["CallSitePlan", "analyse", "apply"]
