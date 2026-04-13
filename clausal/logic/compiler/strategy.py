"""Explicit compilation strategy — shallow vs trampoline.

See ``implementation_plans/COMPILER_TARGET_ARCHITECTURE.md`` §9 and
``implementation_plans/COMPILER_MIGRATION_PLAN.md`` §5.

A :class:`Strategy` carries every decision that used to be implicit
in "am I in shallow mode or trampoline mode?":

- ``emit_leaf_yield``    — AST for surfacing one solution.
- ``emit_sub_call``      — AST for calling a sub-predicate.
- ``preprocess_clause``  — clause-body rewrite (DR for trampoline).
- ``function_params``    — compiled-function parameter list.
- ``compile_goal``       — recursive goal dispatcher (shallow vs trampoline).
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

    def emit_sub_call(
        self,
        ctx: "CompilationContext",
        fname: str,
        arity: int,
        arg_exprs: list[ast.expr],
        k_stmts: list[ast.stmt],
    ) -> list[ast.stmt]: ...

    def preprocess_clause(self, clause: "Clause") -> list[Any]: ...

    def function_params(
        self, ctx: "CompilationContext", arg_names: list[str],
    ) -> list[str]: ...

    def compile_goal(
        self,
        ctx: "CompilationContext",
        goal: Any,
        k_stmts: list[ast.stmt],
    ) -> list[ast.stmt]: ...


class ShallowStrategy:
    """``compile_predicate_shallow`` — Python ``for`` loops over sub-generators."""

    supports_tro = False
    supports_destructive_reuse = False

    def emit_leaf_yield(self, ctx):
        from ._ast_helpers import _yield_none_stmt
        return _yield_none_stmt()

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts):
        from ._ast_helpers import _name
        from .goal_shallow import _dispatch_call_iter
        iter_expr = _dispatch_call_iter(ctx, fname, arity, arg_exprs)
        return [
            ast.For(
                target=_name("_", ast.Store()),
                iter=iter_expr,
                body=k_stmts or [ast.Pass()],
                orelse=[],
            )
        ]

    def preprocess_clause(self, clause):
        return list(clause.body)

    def function_params(self, ctx, arg_names):
        from ._ast_helpers import _TRAIL_PARAM_NAME, _K_PARAM_NAME
        return arg_names + [_TRAIL_PARAM_NAME, _K_PARAM_NAME]

    def compile_goal(self, ctx, goal, k_stmts):
        from .goal_shallow import _dispatch_goal
        return _dispatch_goal(ctx, goal, k_stmts)


class TrampolineStrategy:
    """``compile_predicate_trampoline`` — StepGenerator tuple-protocol."""

    supports_tro = True
    supports_destructive_reuse = True

    def emit_leaf_yield(self, ctx):
        from ._ast_helpers import _name
        from .goal_trampoline import _yield_step_stmt
        return _yield_step_stmt(_name(ctx.parent_name), ast.Constant(None))

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts):
        from ._ast_helpers import _name, _assign
        from .goal_trampoline import (
            _dispatch_call_trampoline, _assign_yield_step,
        )
        gen_name = ctx.fresh("_gen")
        status_name = ctx.fresh("_st")
        call_expr = _dispatch_call_trampoline(ctx, fname, arity, arg_exprs)
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

    def preprocess_clause(self, clause):
        from .destructive_reuse import (
            _flatten_and_goals,
            _find_destructive_reuse_goals,
            _apply_destructive_reuse,
        )
        flat = _flatten_and_goals(clause.body)
        eligible = _find_destructive_reuse_goals(clause)
        return _apply_destructive_reuse(flat, eligible)

    def function_params(self, ctx, arg_names):
        from ._ast_helpers import _TRAIL_PARAM_NAME
        return [ctx.self_name, ctx.parent_name] + arg_names + [_TRAIL_PARAM_NAME]

    def compile_goal(self, ctx, goal, k_stmts):
        from .goal_trampoline import _dispatch_goal_trampoline
        return _dispatch_goal_trampoline(ctx, goal, k_stmts)
