"""AST-construction leaf helpers used throughout the compiler.

Pure functions that build small ``ast`` fragments plus the
per-compilation ``FreshNames`` unique-name generator.  No
compiler-internal dependencies beyond
``clausal.pythonic_ast.nodes.TupleLiteral`` (used by ``_in_iter_expr``
to detect ``in`` goals that destructure pairs).
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.pythonic_ast.nodes import TupleLiteral


# ── Compiled-code naming constants ────────────────────────────────────────────
# Names emitted into generated function signatures and locals.  Centralised
# here (in the deepest-leaf submodule) so any other submodule can import them
# without creating a cycle back through _monolith.
_MARK_PREFIX = "_m"            # fresh mark variable prefix (ctx.fresh(_MARK_PREFIX))
_TRAIL_PARAM_NAME = "trail"    # compiled-function trail parameter
_K_PARAM_NAME = "k"            # shallow-strategy continuation parameter
_DISP_PREFIX = "_disp_"        # locked-dispatch globals-key prefix
_TRAMP_PARENT_NAME = "_tramp_parent"   # trampoline parent-generator parameter
_THIS_GEN_NAME = "this_generator"      # trampoline self-reference parameter


# Python 3.12+ added type_params to FunctionDef.  Spread into ast.FunctionDef
# kwargs so the compiler stays compatible with both 3.11 and 3.12+.
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


# ── ast helpers ────────────────────────────────────────────────────────────────


def _name(id_: str, ctx=None) -> ast.Name:
    return ast.Name(id=id_, ctx=ctx or ast.Load())


def _attr(obj_name: str, attr: str) -> ast.Attribute:
    return ast.Attribute(value=_name(obj_name), attr=attr, ctx=ast.Load())


def _call(func: ast.expr, *args: ast.expr, **kwargs_: ast.expr) -> ast.Call:
    kws = [ast.keyword(arg=k, value=v) for k, v in kwargs_.items()]
    return ast.Call(func=func, args=list(args), keywords=kws)


# ── Unique-name counter ────────────────────────────────────────────────────────


class FreshNames:
    """Per-compilation fresh-name generator.

    One instance lives on ``CompilationContext.fresh`` and is shared
    across all ``ctx.replace()`` forks of a single compilation, so each
    invocation of ``compile_predicate_*`` sees a monotonic counter that
    starts at 1.  Two separate compilations get two separate counters —
    the AST output of one compilation no longer depends on how many
    predicates were compiled earlier in the process.
    """

    __slots__ = ("_n",)

    def __init__(self) -> None:
        self._n = 0

    def __call__(self, prefix: str = "_t") -> str:
        self._n += 1
        return f"{prefix}{self._n}"


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
