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


def _resolve_tabled_call(fname, call_arity, db):
    """Resolve ``fname/call_arity`` (as compiled against *db*) to the
    Database that tables it — ``(home_db, canonical_name)``, or ``None``
    if the call is not tabled anywhere it can see.

    *db* itself answers for a same-module callee.  An ``-import_from``-ed
    callee is tabled only in its OWN module's db, which its binding's ROW
    names (``predicate.tabled_home_of`` -- the SAME answer the runtime half,
    ``tabling._naf_tabled``, uses), and ``db.module_dict`` is exactly the
    namespace the compiled call resolves through at runtime — including the
    dotted spelling (``"lib.Win"``) the import rewrite emits — so consulting
    it keeps the NAF lowering decision aligned with what the positive call
    would actually reach (todo/cross-module-tabled-naf-loses-wfs-delay.md).
    The home db keys its tables (and dispatch, and signatures) by the
    predicate's own name, so the row's functor is the canonical spelling for
    everything done against the home db.
    """
    if db is None:
        return None
    if db.is_tabled(fname, call_arity):
        return db, fname
    md = db.module_dict
    cand = md.get(fname) if md is not None else None
    from clausal.logic.predicate import tabled_home_of  # noqa: PLC0415
    return tabled_home_of(cand, arity=call_arity, db=db)


def _is_tabled_naf(inner_goal, db) -> bool:
    """Return True if inner_goal is a Call to a tabled predicate (in the
    compiling module's own db, or — for an imported callee — in its home
    module's db)."""
    if not isinstance(inner_goal, Call):
        return False
    if not isinstance(inner_goal.func, LoadName):
        return False
    if db is None:
        return False
    fname = inner_goal.func.name
    call_arity = len(inner_goal.args) + len(inner_goal.kwargs)
    return _resolve_tabled_call(fname, call_arity, db) is not None


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
    # Normalize kwargs into positional using signature.  An imported tabled
    # callee registers its signature in its HOME db under its own name, not
    # in the caller's — ask the db that actually tables the call.
    if call_kwargs:
        call_arity = len(call_args) + len(call_kwargs)
        resolved = _resolve_tabled_call(fname, call_arity, db)
        sig_db, sig_name = resolved if resolved is not None else (db, fname)
        sig = sig_db.signature_for(sig_name, call_arity)
        if sig is not None:
            # Keyword nodes carry .name (never .arg — that is Python's
            # ast.keyword, not this AST); .arg crashed on any NAF'd tabled
            # call with keywords and a registered signature.
            kw_dict = {kw.name: kw.value for kw in call_kwargs}
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
        _name("$naf_tabled"),
        ast.Constant(value=fname),
        ast.Constant(value=arity),
        args_tuple,
        _name(trail_name),
        _name("$table_store"),
        _name("$naf_db"),
    )
    return [
        _assign_mark(mark, trail_name),
        _if(naf_call, k_stmts),
        _undo_stmt(mark, trail_name),
    ]
