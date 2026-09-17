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
  The callee is resolved as ``db.row(fname, arity)``: ARITY-EXACT,
  so a call at arity N never sees the plans compiled for arity M.
  With no ``db`` (or a Database-less shim) the plan is empty.
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
    from ..arg_index import (
        _static_call_key, _bucket_key, _joint_bucket_key, hint_row,
    )
    from ..terms_to_ast import term_to_ast_expr

    if not isinstance(ir, Sequence):
        return CallSitePlan(hints=(), joint_hints=())

    hint_list: list[tuple[int, str]] = []
    joint_list: list[tuple[int, str]] = []

    for op_idx, op in enumerate(ir.ops):
        if not isinstance(op, SubCall):
            continue
        fname = op.fname
        arity = op.arity
        # ARITY-EXACT callee resolution: the Database row for
        # (fname, arity), never a by-name lookup in ``base_globals``.
        row = hint_row(db, fname, arity, base_globals)
        if row is None:
            continue

        arg_exprs = [term_to_ast_expr(a, {}) for a in op.args]

        # Single-position: pick the first matching bucket; legacy
        # writes all matching positions into the map, but per-call
        # ``_dispatch_call_trampoline`` uses the first it finds, so
        # a single hint on the SubCall is sufficient for the
        # single-position case.  For byte-parity with legacy we
        # record every match here — the plan stays faithful to the
        # legacy map shape.
        for pos, idx_dict in row.index_plans.items():
            if pos >= len(arg_exprs):
                continue
            key = _static_call_key(arg_exprs[pos])
            if key is None or key not in idx_dict:
                continue
            gkey = _bucket_key(fname, pos, key)
            hint_list.append((op_idx, gkey))
            break  # only need one bucket-ref hint per SubCall

        if row.index_plans_joint:
            for (pi, pj), jdict in row.index_plans_joint.items():
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
    equality) when both single and joint hint sets are empty.

    Both single-position (``direct_bucket_ref``) and joint-position
    (``direct_joint_bucket_ref``) hints are written.  The
    :func:`~clausal.logic.compiler.goal_trampoline._dispatch_call_trampoline`
    prefers the joint hint over the single hint, matching legacy's
    joint-first preference.
    """
    from ..ir import Sequence, SubCall
    if not isinstance(ir, Sequence):
        return ir
    if not plan.hints and not plan.joint_hints:
        return ir
    new_ops = list(ir.ops)
    for op_idx, gkey in plan.hints:
        op = new_ops[op_idx]
        if not isinstance(op, SubCall):
            continue
        if op.direct_bucket_ref == gkey:
            continue
        new_ops[op_idx] = dataclasses.replace(op, direct_bucket_ref=gkey)
    for op_idx, gkey in plan.joint_hints:
        op = new_ops[op_idx]
        if not isinstance(op, SubCall):
            continue
        if op.direct_joint_bucket_ref == gkey:
            continue
        new_ops[op_idx] = dataclasses.replace(op, direct_joint_bucket_ref=gkey)
    return Sequence(ops=new_ops)


def populate_runtime_from_plan(
    ir: Any, plan: CallSitePlan, ctx: Any, base_globals: dict,
    db: Any = None,
) -> None:
    """Populate :attr:`ctx.bucket_ref_map` / :attr:`joint_bucket_ref_map`
    **and** *base_globals* with entries derived from *plan*.

    E6b replaces the legacy per-predicate ``_inject_bucket_refs_trampoline``
    pre-scan with this per-body populator driven off the IR plan.
    For each :class:`SubCall` with a plan hint:

    - Looks up the matching ``pos`` / ``key`` / bucket callable on
      the callee's row (``index_plans`` / ``index_plans_joint``),
      resolved ARITY-EXACTLY as ``db.row(fname, arity)``.  ``db``
      defaults to ``ctx.db`` — the compile pipeline's own Database.
    - Writes the ``(fname, arity, pos, key)`` → gkey entry into the
      legacy map so the legacy fold's ``_dispatch_call_trampoline``
      emission sees it.
    - Injects ``base_globals[gkey] = bucket_fn`` so the generated
      code can resolve the direct bucket reference at load time.

    Idempotent: re-running with the same plan is a no-op.
    """
    from ..ir import Sequence, SubCall
    from ..arg_index import _static_call_key, hint_row
    from ..terms_to_ast import term_to_ast_expr

    if db is None:
        db = getattr(ctx, "db", None)
    if not isinstance(ir, Sequence):
        return
    if not plan.hints and not plan.joint_hints:
        return

    hint_idx = {op_idx: gkey for op_idx, gkey in plan.hints}
    joint_idx = {op_idx: gkey for op_idx, gkey in plan.joint_hints}

    for op_idx, op in enumerate(ir.ops):
        if not isinstance(op, SubCall):
            continue
        fname = op.fname
        arity = op.arity
        row = hint_row(db, fname, arity, base_globals)
        if row is None:
            continue
        arg_exprs = [term_to_ast_expr(a, {}) for a in op.args]

        single_gkey = hint_idx.get(op_idx)
        if single_gkey is not None:
            for pos, idx_dict in row.index_plans.items():
                if pos >= len(arg_exprs):
                    continue
                key = _static_call_key(arg_exprs[pos])
                if key is None or key not in idx_dict:
                    continue
                ctx.bucket_ref_map[(fname, arity, pos, key)] = single_gkey
                if single_gkey not in base_globals:
                    base_globals[single_gkey] = idx_dict[key]
                break

        joint_gkey = joint_idx.get(op_idx)
        if joint_gkey is not None and row.index_plans_joint:
            for (pi, pj), jdict in row.index_plans_joint.items():
                if pi >= len(arg_exprs) or pj >= len(arg_exprs):
                    continue
                ki = _static_call_key(arg_exprs[pi])
                kj = _static_call_key(arg_exprs[pj])
                if ki is None or kj is None:
                    continue
                if (ki, kj) not in jdict:
                    continue
                ctx.joint_bucket_ref_map[(fname, arity, pi, pj, ki, kj)] = joint_gkey
                if joint_gkey not in base_globals:
                    base_globals[joint_gkey] = jdict[(ki, kj)]
                break


__all__ = ["CallSitePlan", "analyse", "apply", "populate_runtime_from_plan"]
