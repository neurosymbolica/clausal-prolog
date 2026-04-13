"""WFS: tabled negation-as-failure helpers.

Small pair: ``_is_tabled_naf`` tests whether a goal is a call to a
tabled predicate; ``_compile_tabled_naf_simple`` emits the
``_naf_tabled(…)`` guard that both shallow and trampoline goal
compilers use for WFS-sound negation.
"""

from __future__ import annotations

import ast

from clausal.terms import Call, LoadName

from ._ast_helpers import (
    _name, _call, _assign_mark, _undo_stmt, _if, _MARK_PREFIX,
)
from .terms_to_ast import term_to_ast_expr
from .compile_ctx import CompilationContext


def _is_tabled_naf(inner_goal, db) -> bool:
    """Return True if inner_goal is a Call to a tabled predicate."""
    if not isinstance(inner_goal, Call):
        return False
    if not isinstance(inner_goal.func, LoadName):
        return False
    if db is None:
        return False
    fname = inner_goal.func.name
    call_arity = len(inner_goal.args) + len(inner_goal.kwargs)
    return db.is_tabled(fname, call_arity)


def _compile_tabled_naf_simple(ctx: CompilationContext, inner_goal, k_stmts):
    """Emit _naf_tabled(...) call for tabled NAF (both simple and trampoline modes).

    Generates::

        _m = trail.mark()
        if _naf_tabled("fname", arity, (arg0, ..., argN), trail, _table_store):
            k_stmts
        trail.undo(_m)
    """
    db = ctx.db
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    fname = inner_goal.func.name
    call_args = inner_goal.args
    call_kwargs = inner_goal.kwargs
    # Normalize kwargs into positional using signature
    if call_kwargs:
        sig = db.signature_for(fname, len(call_args) + len(call_kwargs))
        if sig is not None:
            kw_dict = {kw.arg: kw.value for kw in call_kwargs}
            all_args = []
            for i, field in enumerate(sig):
                if i < len(call_args):
                    all_args.append(call_args[i])
                elif field in kw_dict:
                    all_args.append(kw_dict[field])
            call_args = all_args

    arity = len(call_args)
    arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in call_args]
    args_tuple = ast.Tuple(elts=arg_exprs, ctx=ast.Load())
    mark = ctx.fresh(_MARK_PREFIX)

    naf_call = _call(
        _name("_naf_tabled"),
        ast.Constant(value=fname),
        ast.Constant(value=arity),
        args_tuple,
        _name(trail_name),
        _name("_table_store"),
    )
    return [
        _assign_mark(mark, trail_name),
        _if(naf_call, k_stmts),
        _undo_stmt(mark, trail_name),
    ]
