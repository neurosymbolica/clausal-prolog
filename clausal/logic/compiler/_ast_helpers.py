"""AST-construction leaf helpers used throughout the compiler.

Pure functions that build small ``ast`` fragments plus the
compile-time ``_fresh`` unique-name generator.  No compiler-internal
dependencies beyond ``clausal.pythonic_ast.nodes.TupleLiteral`` (used
by ``_in_iter_expr`` to detect ``in`` goals that destructure pairs).
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.pythonic_ast.nodes import TupleLiteral


# ── ast helpers ────────────────────────────────────────────────────────────────


def _name(id_: str, ctx=None) -> ast.Name:
    return ast.Name(id=id_, ctx=ctx or ast.Load())


def _attr(obj_name: str, attr: str) -> ast.Attribute:
    return ast.Attribute(value=_name(obj_name), attr=attr, ctx=ast.Load())


def _call(func: ast.expr, *args: ast.expr, **kwargs_: ast.expr) -> ast.Call:
    kws = [ast.keyword(arg=k, value=v) for k, v in kwargs_.items()]
    return ast.Call(func=func, args=list(args), keywords=kws)


# ── Unique-name counter ────────────────────────────────────────────────────────

_compile_counter: list[int] = [0]


def _fresh(prefix: str = "_t") -> str:
    """Generate a compile-time unique Python local variable name."""
    _compile_counter[0] += 1
    return f"{prefix}{_compile_counter[0]}"


# ── Misc AST-building helpers ──────────────────────────────────────────────────


def _yield_none_stmt() -> ast.stmt:
    return ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))


def _assign(target: str, value: ast.expr) -> ast.stmt:
    return ast.Assign(
        targets=[_name(target, ast.Store())],
        value=value,
        lineno=0,
        col_offset=0,
    )


def _assign_mark(mark_name: str, trail_name: str) -> ast.stmt:
    return _assign(mark_name, _call(_attr(trail_name, "mark")))


def _undo_stmt(mark_name: str, trail_name: str) -> ast.stmt:
    return ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name)))


def _if(test: ast.expr, body: list[ast.stmt]) -> ast.If:
    return ast.If(test=test, body=body or [ast.Pass()], orelse=[])


def _in_iter_expr(elem: Any, coll_expr: ast.expr) -> ast.expr:
    """Build the iterator expression for an ``in`` goal.

    If *elem* is a TupleLiteral, emits ``_in_iter(deref(coll), True)`` so that
    DictTerms yield (key, value) pairs.  Otherwise emits ``deref(coll)``.
    """
    if isinstance(elem, TupleLiteral):
        return _call(
            _name("_in_iter"),
            _call(_name("deref"), coll_expr),
            ast.Constant(value=True),
        )
    return _call(_name("deref"), coll_expr)
