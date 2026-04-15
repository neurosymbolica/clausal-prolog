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

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts, *, direct_bucket_ref=None, direct_joint_bucket_ref=None):
        from ._ast_helpers import _name
        from .goal_shallow import _dispatch_call_iter
        # Shallow strategy does not support bucket-ref specialisation;
        # the hints are accepted for uniform plumbing and ignored.
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

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts, *, direct_bucket_ref=None, direct_joint_bucket_ref=None):
        from ._ast_helpers import _name, _assign
        from .goal_trampoline import (
            _dispatch_call_trampoline, _assign_yield_step,
        )
        gen_name = ctx.fresh("_gen")
        status_name = ctx.fresh("_st")
        call_expr = _dispatch_call_trampoline(
            ctx, fname, arity, arg_exprs,
            direct_bucket_ref=direct_bucket_ref,
            direct_joint_bucket_ref=direct_joint_bucket_ref,
        )
        gen_assign = _assign(gen_name, call_expr)
        first_step = _assign_yield_step(
            status_name, _name(gen_name), ast.Constant(None),
        )
        loop_body = (k_stmts or [ast.Pass()]) + [
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
