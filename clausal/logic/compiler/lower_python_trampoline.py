"""Lower a :class:`~clausal.logic.compiler.ir.GoalOp` tree to Python
``ast.stmt`` list — trampoline strategy.

Covers the D2 subset plus ``Alternate`` (D5b) and ``Negate`` (D5c).
The D4 parallel-implementation harness that once enforced byte-for-byte
``ast.dump`` parity against ``compile_goal_trampoline`` retired in
D7c-alpha (see ``goal_shallow._compile_body_impl``'s docstring); the
``Negate`` mini-loop here no longer replicates that legacy shape verbatim
-- it delegates its drive step to a shared runtime helper
(``$naf_has_solution``) instead of emitting its own inline
``StepGenerator`` loop.  (The general-``Branch`` mini-loop -- a soft-cut
if-then-else over a plain-goal condition -- was removed when ``if_/3``
came to require a reifiable condition, operator ruling 2026-10-01; every
``Branch`` is now the reified three-way form in ``_lower_goalop_shared``.)

Strategy-agnostic cases delegate to ``_lower_goalop_shared``.  The
trampoline-specific arms (``Negate`` -- a mini-trampoline that builds a
``StepGenerator`` and drives it through a shared runtime helper -- and
later ``SubCall``, catch-family, meta-call arms that diverge from
shallow) live in this module.

Before D5c, this module delegated entirely to ``lower_python_shallow``
because every covered op was strategy-agnostic.  ``Negate`` is the
first divergent op and forces the fork; see commit history for the
transition.
"""

from __future__ import annotations

import ast
from typing import NoReturn

from clausal.logic.compiler.ir import GoalOp, Negate
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler._ast_helpers import (
    _EXTRA_FUNCDEF,
    _MARK_PREFIX,
    _assign,
    _assign_mark,
    _call,
    _if,
    _name,
    _undo_stmt,
)
from clausal.logic.compiler._lower_goalop_shared import lower_shared


def lower(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Lower *ir* (trampoline strategy), threading *k_stmts* as continuation."""
    with ctx.at_position(ir.position):
        return _lower_body(ir, ctx, k_stmts)


def _lower_body(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    match ir:

        # ── Negation-as-failure — trampoline form.
        # Inner goal is compiled in trampoline mode with swapped
        # ``self_name`` / ``parent_name``; a mini-trampoline
        # ``StepGenerator`` loop checks if at least one solution exists.
        # Mirrors the legacy ``_dispatch_goal_trampoline`` ``Not`` arm
        # byte-for-byte.
        case Negate(op=inner):
            from clausal.logic.compiler.goal_trampoline import _yield_step_stmt
            trail_name = ctx.trail_name
            naf_gen_fn = ctx.fresh("_naf_gen_fn")
            naf_flag = ctx.fresh("_naf")
            naf_sg = ctx.fresh("_naf_sg")
            naf_g = ctx.fresh("_naf_g")
            naf_v = ctx.fresh("_naf_v")
            inner_k = [_yield_step_stmt(_name("_naf_proceed"), ast.Constant(None))]
            inner_stmts = lower(
                inner,
                ctx.replace(
                    self_name="_naf_self",
                    proceed_name="_naf_proceed",
                    fail_name="_naf_fail",
                    catcher_name="_naf_catcher",
                ),
                inner_k,
            )
            naf_body = inner_stmts + [
                _yield_step_stmt(_name("_naf_fail"), _name("$DONE")),
            ]
            naf_fn_def = ast.FunctionDef(
                name=naf_gen_fn,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="_naf_self"),
                          ast.arg(arg="_naf_proceed"),
                          ast.arg(arg="_naf_fail"),
                          ast.arg(arg="_naf_catcher"),
                          ast.arg(arg=trail_name)],
                    vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = ctx.fresh(_MARK_PREFIX)
            sg_create = _assign(naf_sg,
                _call(_name("StepGenerator"), _name(naf_gen_fn),
                      ast.Constant(None), ast.Constant(None), ast.Constant(None),
                      _name(trail_name)))
            # The drive loop lives in $naf_has_solution, not here.  Emitted
            # inline it was a fifth copy of the loop and the only one with no
            # exception routing, so a catch/3 inside a negated goal was inert
            # and its exception escaped the negation (review, 2026-08-25).
            drive = _assign(naf_flag, ast.UnaryOp(
                op=ast.Not(),
                operand=_call(_name("$naf_has_solution"), _name(naf_sg)),
            ))
            return [
                naf_fn_def,
                _assign_mark(naf_mark, trail_name),
                sg_create,
                drive,
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

    shared = lower_shared(ir, ctx, k_stmts, lower)
    if shared is not None:
        return shared
    _not_yet(ir)


def _not_yet(ir: GoalOp) -> NoReturn:
    raise NotImplementedError(
        f"lower_python_trampoline: IR op not yet supported: {type(ir).__name__}"
    )


__all__ = ["lower"]
