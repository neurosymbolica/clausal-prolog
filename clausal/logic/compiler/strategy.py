"""Explicit compilation strategy — shallow vs trampoline.

See ``implementation_plans/COMPILER_TARGET_ARCHITECTURE.md`` §9 and
``implementation_plans/COMPILER_MIGRATION_PLAN.md`` §5.

A :class:`Strategy` carries every decision that used to be implicit
in "am I in shallow mode or trampoline mode?":

- ``emit_leaf_yield``    — AST for surfacing one solution.
- ``emit_sub_call``      — AST for calling a sub-predicate.
- ``preprocess_clause``  — clause-body rewrite (DR for trampoline).
- ``function_params``    — compiled-function parameter list.
- ``supports_tro`` / ``supports_destructive_reuse`` — feature flags.

The strategy instance lives on :class:`CompilationContext`.  Shared
helpers (``_compile_body_impl``, ``_compile_predicate_call_impl``,
``_make_body_compiler_impl``) consult ``ctx.strategy`` instead of
taking per-hook kwargs.

Cycle handling: every method that touches goal-dispatch or call-site
emission uses **function-local imports** into ``goal_shallow`` /
``goal_trampoline`` to break the otherwise mutual import between this
module and those modules (the ratified B4/B6 idiom).
"""

from __future__ import annotations

import ast
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from clausal.logic.database import Clause
    from .compile_ctx import CompilationContext


class Strategy(Protocol):
    supports_tro: bool
    supports_destructive_reuse: bool

    def emit_leaf_yield(self, ctx: "CompilationContext") -> ast.stmt: ...

    def emit_exhaustion_yield(
        self, ctx: "CompilationContext",
    ) -> ast.stmt | None: ...

    def emit_sub_call(
        self,
        ctx: "CompilationContext",
        fname: str,
        arity: int,
        arg_exprs: list[ast.expr],
        k_stmts: list[ast.stmt],
        *,
        direct_bucket_ref: str | None = None,
        direct_joint_bucket_ref: str | None = None,
        tail_position: bool = False,
    ) -> list[ast.stmt]: ...

    def function_params(
        self, ctx: "CompilationContext", arg_names: list[str],
    ) -> list[str]: ...


class ShallowStrategy:
    """``compile_predicate_shallow`` — Python ``for`` loops over sub-generators."""

    supports_tro = False
    supports_destructive_reuse = False

    def emit_leaf_yield(self, ctx):
        from ._ast_helpers import _yield_none_stmt
        return _yield_none_stmt()

    def emit_exhaustion_yield(self, ctx):
        # Shallow generators fall off the end of the function naturally.
        return None

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts, *, direct_bucket_ref=None, direct_joint_bucket_ref=None, tail_position=False):
        from ._ast_helpers import _name
        from .goal_shallow import _dispatch_call_iter
        # Shallow strategy does not support bucket-ref specialisation
        # or continuation-TCO; the hints are accepted for uniform
        # plumbing and ignored.
        iter_expr = _dispatch_call_iter(ctx, fname, arity, arg_exprs)
        return [
            ast.For(
                target=_name("_", ast.Store()),
                iter=iter_expr,
                body=k_stmts or [ast.Pass()],
                orelse=[],
            )
        ]

    def function_params(self, ctx, arg_names):
        from ._ast_helpers import _TRAIL_PARAM_NAME, _K_PARAM_NAME
        return arg_names + [_TRAIL_PARAM_NAME, _K_PARAM_NAME]


def _k_stmts_is_bare_leaf_yield(k_stmts, ctx) -> bool:
    """True when *k_stmts* is exactly ``[yield (_proceed, None)]``.

    Used by :meth:`TrampolineStrategy.emit_sub_call` to decide whether
    continuation-TCO is safe to apply at a given call site.  When
    head-pattern output-mode unification wrapped the leaf yield with a
    conditional, the structural equality fails and we fall back to the
    non-TCO emission shape.
    """
    if len(k_stmts) != 1:
        return False
    from ._ast_helpers import _name
    from .goal_trampoline import _yield_step_stmt
    leaf = _yield_step_stmt(_name(ctx.proceed_name), ast.Constant(None))
    return ast.dump(k_stmts[0]) == ast.dump(leaf)


class TrampolineStrategy:
    """``compile_predicate_trampoline`` — StepGenerator tuple-protocol."""

    supports_tro = True
    supports_destructive_reuse = True

    def emit_leaf_yield(self, ctx):
        from ._ast_helpers import _name
        from .goal_trampoline import _yield_step_stmt
        return _yield_step_stmt(_name(ctx.proceed_name), ast.Constant(None))

    def emit_exhaustion_yield(self, ctx):
        from ._ast_helpers import _name
        from .goal_trampoline import _yield_step_stmt
        return _yield_step_stmt(_name(ctx.fail_name), _name("_DONE"))

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts, *, direct_bucket_ref=None, direct_joint_bucket_ref=None, tail_position=False):
        from ._ast_helpers import _name, _assign
        from .goal_trampoline import (
            _dispatch_call_trampoline, _assign_yield_step,
        )
        gen_name = ctx.fresh("_gen")
        status_name = ctx.fresh("_st")
        # Continuation-TCO is only sound when the k_stmts we would run
        # per-solution is exactly the leaf yield.  Head-pattern
        # compilation can wrap the leaf yield with deferred output-mode
        # unification (``if _head_list_unify_output(...): yield (_proceed,
        # None)``) that MUST run between the child's solution and the
        # caller's observation — dropping it would lose bindings.  The
        # IR-level analysis can't see those wrappers because they're
        # emitted by head-pattern lowering, not body-IR lowering.
        # Check structurally here: apply TCO only when k_stmts is a
        # single leaf-yield statement identical to ``emit_leaf_yield``.
        tco_safe = tail_position and _k_stmts_is_bare_leaf_yield(k_stmts, ctx)
        # Continuation-TCO: route the child's solutions to our caller
        # (``_proceed``) instead of back through us.  ``fail`` and
        # ``catcher`` stay pointed at ``this_generator`` so we still
        # wake for cleanup / next clause / next loop iteration / thrown
        # exceptions.  See ``implementation_plans/CONTINUATION_TCO_PLAN.md``.
        call_expr = _dispatch_call_trampoline(
            ctx, fname, arity, arg_exprs,
            direct_bucket_ref=direct_bucket_ref,
            direct_joint_bucket_ref=direct_joint_bucket_ref,
            tail_position=tco_safe,
        )
        gen_assign = _assign(gen_name, call_expr)
        first_step = _assign_yield_step(
            status_name, _name(gen_name), ast.Constant(None),
        )
        # Under TCO the child now emits our leaf yield directly on our
        # caller's ``_proceed`` — running ``k_stmts`` (which is the lone
        # leaf yield) on resume would double-yield each solution.
        resume_k = [] if tco_safe else (k_stmts or [ast.Pass()])
        loop_body = resume_k + [
            _assign_yield_step(
                status_name, _name(gen_name), ast.Constant(None),
            )
        ]
        loop = ast.While(
            test=ast.Compare(
                left=_name(status_name),
                ops=[ast.IsNot()],
                comparators=[_name("_DONE")],
            ),
            body=loop_body,
            orelse=[],
        )
        return [gen_assign, first_step, loop]

    def function_params(self, ctx, arg_names):
        from ._ast_helpers import _TRAIL_PARAM_NAME
        return (
            [ctx.self_name, ctx.proceed_name, ctx.fail_name, ctx.catcher_name]
            + arg_names
            + [_TRAIL_PARAM_NAME]
        )
