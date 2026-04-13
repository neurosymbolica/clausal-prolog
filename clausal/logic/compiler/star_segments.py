"""Body-Is compilation for star-list patterns.

The three ``_compile_*_is`` functions lower an ``Is`` goal whose left
side contains ``*`` star-unpacks into AST statements that call the
runtime helpers in ``clausal.logic.runtime.body_star_unify``
(``_body_star_unify`` /
``_body_multi_star_unify``).

Parsing leaves (``_parse_star_segments``, ``_count_stars``,
``_is_star_list``) live in ``.terms_to_ast`` to avoid an import cycle.
"""

from __future__ import annotations

import ast
from typing import Any

from ._ast_helpers import (
    _name, _call, _assign_mark, _undo_stmt, _if,
    _MARK_PREFIX,
)
from .terms_to_ast import term_to_ast_expr, _parse_star_segments, _count_stars
from .compile_ctx import CompilationContext


def _compile_star_is(
    ctx: CompilationContext,
    star_side: list,
    other_side: Any,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile an Is goal where one side contains a star-list pattern.

    Generates a call to a runtime helper that handles bidirectional
    star-list unification (both construction and deconstruction).
    """
    segments = _parse_star_segments(star_side)
    n_stars = _count_stars(segments)
    other_expr = term_to_ast_expr(other_side, ctx.var_context, eval_arith=False)

    if n_stars == 1:
        return _compile_single_star_is(ctx, segments, other_expr, k_stmts)
    else:
        return _compile_multi_star_is(ctx, segments, other_expr, k_stmts)


def _compile_single_star_is(
    ctx: CompilationContext,
    segments: list[tuple],
    other_expr: ast.expr,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile single-star body Is: emit call to _body_star_unify."""
    before_vals: list = []
    star_val = None
    after_vals: list = []
    past_star = False

    for kind, val in segments:
        if kind == "star":
            star_val = val
            past_star = True
        elif not past_star:
            before_vals.extend(val)
        else:
            after_vals.extend(val)

    vc = ctx.var_context
    trail_name = ctx.trail_name
    before_exprs = [term_to_ast_expr(v, vc, eval_arith=False) for v in before_vals]
    star_expr = term_to_ast_expr(star_val, vc, eval_arith=False) if star_val is not None else ast.Constant(value=None)
    after_exprs = [term_to_ast_expr(v, vc, eval_arith=False) for v in after_vals]

    mark = ctx.fresh(_MARK_PREFIX)
    return [
        _assign_mark(mark, trail_name),
        _if(
            _call(
                _name("_body_star_unify"),
                other_expr,
                ast.List(elts=before_exprs, ctx=ast.Load()),
                star_expr,
                ast.List(elts=after_exprs, ctx=ast.Load()),
                _name(trail_name),
            ),
            k_stmts,
        ),
        _undo_stmt(mark, trail_name),
    ]


def _compile_multi_star_is(
    ctx: CompilationContext,
    segments: list[tuple],
    other_expr: ast.expr,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile multi-star body Is: emit for-loop over _body_multi_star_unify."""
    vc = ctx.var_context
    trail_name = ctx.trail_name
    # Build segments as a runtime list of tuples
    seg_elts: list[ast.expr] = []
    for kind, val in segments:
        if kind == "fixed":
            elems = ast.List(
                elts=[term_to_ast_expr(v, vc, eval_arith=False) for v in val],
                ctx=ast.Load(),
            )
            seg_elts.append(ast.Tuple(
                elts=[ast.Constant(value="fixed"), elems],
                ctx=ast.Load(),
            ))
        else:  # star
            seg_elts.append(ast.Tuple(
                elts=[ast.Constant(value="star"), term_to_ast_expr(val, vc, eval_arith=False)],
                ctx=ast.Load(),
            ))

    segments_expr = ast.List(elts=seg_elts, ctx=ast.Load())

    return [
        ast.For(
            target=_name("_", ast.Store()),
            iter=_call(
                _name("_body_multi_star_unify"),
                other_expr,
                segments_expr,
                _name(trail_name),
            ),
            body=k_stmts or [ast.Pass()],
            orelse=[],
        ),
    ]
