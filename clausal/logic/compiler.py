"""clausal.logic.compiler — predicate compiler (Steps 4 + 5).

Step 4 (head patterns): head_to_match_pattern, compile_head_to_match_case
Step 5 (body goals):    term_to_ast_expr, arith_to_ast_expr, compile_goal,
                        compile_body, _make_body_compiler

Two compilation strategies are provided:

**Simple / short-stack** (``compile_predicate``)
    Each clause becomes a ``match`` arm.  The body ends with ``yield None``
    for each solution.  Sub-predicate calls use Python ``for`` loops so the
    Python call stack grows with recursion depth.  Use for predicates whose
    call depth is bounded (e.g., fact tables, leaf predicates).

    Compiled function signature::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …
            yield None   # ← one solution

**Trampoline / stack-safe** (``compile_predicate_trampoline``)
    Every generated function is an immortal coroutine in the
    ``clausal.logic.trampoline`` Step protocol.  Sub-predicate calls use
    ``yield Step(child_gen, …)`` so the Python call stack does *not* grow.
    Solutions are surfaced via ``yield Step(parent, None)``; exhaustion via
    ``yield Step(parent, DONE)``.  The trampoline drives all generators.
    ``continuation_search.Search`` (Step 7) provides the ``__iter__``
    bridge.

    Compiled function signature::

        def {functor}__{arity}(parent, arg0, …, argN, trail):
            self = yield   # bootstrap hook
            …
            yield Step(parent, _DONE)   # ← search exhausted
"""

from __future__ import annotations

import ast
import dataclasses
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify
from clausal.logic.trampoline import Step
from clausal.terms import (
    Compound,
    ArithConstraint,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    And, Or, Not,
    Is, IsNot, Eq, NotEq,
    Lt, LtE, Gt, GtE,
    In, NotIn,
    Call, LoadName,
)
from clausal.logic.database import Clause, Database
from clausal.codegen import functiondef_to_function


# ── Variable naming ────────────────────────────────────────────────────────────


def _var_python_name(var: Var) -> str:
    """Return a stable Python identifier for a logic variable from its _id."""
    return f"_v{var._id}"


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


# ── Term → AST expression ──────────────────────────────────────────────────────


def term_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    Supports: Var, Python scalars, list, Compound, functor dataclasses.
    Does NOT recursively evaluate arithmetic — use arith_to_ast_expr for that.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        if vid in var_context:
            return _name(var_context[vid])
        # Body-only Var: introduce via walrus assignment
        vname = _var_python_name(term)
        var_context[vid] = vname
        return ast.NamedExpr(
            target=ast.Name(id=vname, ctx=ast.Store()),
            value=_call(_name("Var")),
        )

    if term is None or isinstance(term, bool):
        return ast.Constant(value=term)

    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.Constant(value=term)

    if isinstance(term, list):
        return ast.List(
            elts=[term_to_ast_expr(e, var_context) for e in term],
            ctx=ast.Load(),
        )

    if isinstance(term, Compound):
        f = term.functor
        f_expr: ast.expr
        if is_var(f):
            vid = f._id
            f_expr = _name(var_context[vid]) if vid in var_context else _call(_name("Var"))
        else:
            f_expr = ast.Constant(value=f)
        args_elts = [term_to_ast_expr(a, var_context) for a in term.args]
        return _call(
            _name("Compound"),
            f_expr,
            ast.Tuple(elts=args_elts, ctx=ast.Load()),
        )

    # Arithmetic term nodes: dispatch to arith_to_ast_expr so they generate
    # native Python binary/unary ops rather than functor-dataclass constructor calls.
    if isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)):
        return arith_to_ast_expr(term, var_context)

    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        cls_name = type(term).__name__
        return ast.Call(
            func=_name(cls_name),
            args=[],
            keywords=[
                ast.keyword(
                    arg=f.name,
                    value=term_to_ast_expr(getattr(term, f.name), var_context),
                )
                for f in dataclasses.fields(term)
            ],
        )

    raise NotImplementedError(
        f"term_to_ast_expr: unsupported term type {type(term).__name__}: {term!r}"
    )


# ── Arithmetic term → AST expression ──────────────────────────────────────────

_ARITH_BINOP_MAP: list[tuple[type, ast.operator]] = [
    (Add,      ast.Add()),
    (Sub,      ast.Sub()),
    (Mult,     ast.Mult()),
    (Div,      ast.Div()),
    (FloorDiv, ast.FloorDiv()),
    (Mod,      ast.Mod()),
    (Pow,      ast.Pow()),
]


def arith_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert an arithmetic term to a Python arithmetic AST expression.

    Generates code that evaluates the expression to a Python number at runtime.
    Vars are dereferenced.  Arithmetic binary operators are unboxed to native
    Python ``ast.BinOp`` nodes.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        vname = var_context.get(vid, _var_python_name(term))
        return _call(_name("deref"), _name(vname))

    if isinstance(term, (int, float)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    if isinstance(term, Negate):
        return ast.UnaryOp(
            op=ast.USub(),
            operand=arith_to_ast_expr(term.operand, var_context),
        )

    for cls, ast_op in _ARITH_BINOP_MAP:
        if isinstance(term, cls):
            return ast.BinOp(
                left=arith_to_ast_expr(term.left, var_context),
                op=ast_op,
                right=arith_to_ast_expr(term.right, var_context),
            )

    # Fallback: treat as a plain term (e.g. a Var holding a number at runtime)
    return term_to_ast_expr(term, var_context)


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


def _compile_arith_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    l_expr = arith_to_ast_expr(l, var_context)
    r_expr = arith_to_ast_expr(r, var_context)
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _deref_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a structural comparison using deref on both sides."""
    l_expr = _call(_name("deref"), term_to_ast_expr(l, var_context))
    r_expr = _call(_name("deref"), term_to_ast_expr(r, var_context))
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _dispatch_call_iter(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
) -> ast.expr:
    """Generate: _db.table_for(fname, arity).get_dispatch()(arg0, …, trail)"""
    table_lookup = ast.Call(
        func=ast.Attribute(value=_name("_db"), attr="table_for"),
        args=[ast.Constant(value=fname), ast.Constant(value=arity)],
        keywords=[],
    )
    get_dispatch = ast.Call(
        func=ast.Attribute(value=table_lookup, attr="get_dispatch"),
        args=[],
        keywords=[],
    )
    return ast.Call(
        func=get_dispatch,
        args=arg_exprs + [_name(trail_name), _name("k")],
        keywords=[],
    )


# ── compile_goal ───────────────────────────────────────────────────────────────


def compile_goal(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a goal term into Python statements.

    On success, executes k_stmts (the inlined continuation).
    On failure, does nothing (falls through without executing k_stmts).

    Parameters
    ----------
    goal       : goal term (Is, And, Or, Call, True, False, …)
    db         : live database — used for predicate dispatch and signature lookup
    var_context: mutable Var._id → python_name dict; extended for body-only Vars
    trail_name : name of the trail parameter in the enclosing compiled function
    k_stmts    : continuation statements to inline on success
    """
    goal = deref(goal)

    # Booleans — must be tested before isinstance(term, int) in the general path
    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    match goal:

        # ── Unification ─────────────────────────────────────────────────────
        case Is(left=l, right=r):
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── Dif (POC: structural check only) ────────────────────────────────
        case IsNot(left=l, right=r):
            # POC: succeed iff deref(l) != deref(r) at this point.
            # Full dif/2 via attr-vars is deferred to the CLP step.
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        # ── Structural equality ──────────────────────────────────────────────
        case Eq(left=l, right=r):
            return _deref_cmp(l, r, ast.Eq(), var_context, k_stmts)

        case NotEq(left=l, right=r):
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        # ── Arithmetic comparisons ───────────────────────────────────────────
        case Lt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Lt(), var_context, k_stmts)

        case LtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.LtE(), var_context, k_stmts)

        case Gt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Gt(), var_context, k_stmts)

        case GtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.GtE(), var_context, k_stmts)

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            # Build right-to-left: r's stmts become k for l
            inner_k = compile_goal(r, db, var_context, trail_name, k_stmts)
            return compile_goal(l, db, var_context, trail_name, inner_k)

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh("_m")
            left_stmts = compile_goal(l, db, var_context, trail_name, k_stmts)
            right_stmts = compile_goal(r, db, var_context, trail_name, k_stmts)
            # Note: both branches share var_context; body-only vars in Or
            # branches that differ between branches are a known POC limitation.
            return [
                _assign_mark(mark, trail_name),
                *left_stmts,
                _undo_stmt(mark, trail_name),
                _assign_mark(mark, trail_name),
                *right_stmts,
                _undo_stmt(mark, trail_name),
            ]

        # ── Negation-as-failure ──────────────────────────────────────────────
        case Not(operand=inner):
            # Run inner as a sub-generator; succeed iff it yields no solutions.
            # Bindings from the inner goal do not escape (the nested function
            # closes over trail, and we use a fresh mark to undo any accidental
            # bindings that the sub-generator leaves before failing).
            naf_gen = _fresh("_naf_gen")
            naf_flag = _fresh("_naf")
            inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=inner_stmts or [ast.Pass()],
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = _fresh("_m")
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

        # ── Membership / enumeration ─────────────────────────────────────────
        case In(left=elem, right=collection):
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        # ── Non-membership ───────────────────────────────────────────────────
        case NotIn(left=elem, right=collection):
            found_flag = _fresh("_found")
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

        # ── CLP(FD) stub ─────────────────────────────────────────────────────
        case ArithConstraint():
            raise NotImplementedError(
                "CLP(FD) arithmetic constraints (==+) are not yet implemented"
            )

        # ── Compile-time-known predicate call ────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call(
                fname, call_args, call_kwargs, db, var_context, trail_name, k_stmts
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal: unsupported goal type {type(goal).__name__}: {goal!r}"
            )


def _compile_predicate_call(
    fname: str,
    call_args: list,
    call_kwargs: list,   # list of Keyword nodes from the term
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a call to a named predicate.

    WK-4: When kwargs are present, look up the predicate's signature in the
    database and reorder keyword args to positional order.  Raises RuntimeError
    if no signature is registered.
    """
    from clausal.pythonic_ast.nodes import Keyword as KWNode

    n_pos = len(call_args)
    arity = n_pos + len(call_kwargs)

    ordered_args: list = list(call_args)
    if call_kwargs:
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"No signature registered for {fname}/{arity}; "
                "cannot compile keyword call without a signature"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            if param_name not in kw_dict:
                raise RuntimeError(
                    f"Missing argument {param_name!r} in keyword call to {fname}/{arity}"
                )
            ordered_args.append(kw_dict[param_name])

    arg_exprs = [term_to_ast_expr(a, var_context) for a in ordered_args]
    iter_expr = _dispatch_call_iter(fname, arity, arg_exprs, trail_name)
    return [
        ast.For(
            target=_name("_", ast.Store()),
            iter=iter_expr,
            body=k_stmts or [ast.Pass()],
            orelse=[],
        )
    ]


# ── compile_body ───────────────────────────────────────────────────────────────


def compile_body(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction.

    The leaf continuation is ``yield None`` (one solution).
    Goals are processed right-to-left so each wraps the next as its k_stmts.
    """
    k: list[ast.stmt] = [_yield_none_stmt()]
    for goal in reversed(goals):
        k = compile_goal(goal, db, var_context, trail_name, k)
    return k


def _make_body_compiler(db: Database) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body(clause.body, db, var_context, "trail")
    return _body_compiler


# ── Trampoline Step-protocol compilation ───────────────────────────────────────
#
# DONE sentinel: yielded as Step(parent, DONE) when a predicate generator has
# exhausted all clauses.  The calling generator receives DONE as the value of
# its ``_st = yield Step(child, None)`` expression and exits its while loop.
#
DONE: object = object()


# ── AST helpers for Step yields ────────────────────────────────────────────────


def _step_expr(gen_expr: ast.expr, value_expr: ast.expr) -> ast.expr:
    """Generate AST for: Step(gen_expr, value_expr)"""
    return _call(_name("Step"), gen_expr, value_expr)


def _yield_step_stmt(gen_expr: ast.expr, value_expr: ast.expr) -> ast.stmt:
    """Generate AST for statement: yield Step(gen_expr, value_expr)"""
    return ast.Expr(value=ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _assign_yield_step(
    target: str, gen_expr: ast.expr, value_expr: ast.expr
) -> ast.stmt:
    """Generate AST for: target = (yield Step(gen_expr, value_expr))

    The yielded Step tells the trampoline to (re)start gen_expr.  When
    gen_expr next yields Step(back_to_us, v), the trampoline sends v here
    and target is bound to v.
    """
    return _assign(target, ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _dispatch_call_trampoline(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
    self_name: str,
) -> ast.expr:
    """Generate: _db.table_for(fname, arity).get_dispatch()(self, arg0, …, trail)

    ``self`` is passed as ``parent`` so the child generator knows who to
    Step back to when it finds a solution.
    """
    table_lookup = ast.Call(
        func=ast.Attribute(value=_name("_db"), attr="table_for"),
        args=[ast.Constant(value=fname), ast.Constant(value=arity)],
        keywords=[],
    )
    get_dispatch = ast.Call(
        func=ast.Attribute(value=table_lookup, attr="get_dispatch"),
        args=[],
        keywords=[],
    )
    return ast.Call(
        func=get_dispatch,
        args=[_name(self_name)] + arg_exprs + [_name(trail_name)],
        keywords=[],
    )


# ── compile_goal_trampoline ────────────────────────────────────────────────────


def compile_goal_trampoline(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str = "self",
    parent_name: str = "parent",
) -> list[ast.stmt]:
    """Compile a goal using the trampoline Step protocol.

    Identical to ``compile_goal`` for deterministic goals (Is, Eq, comparisons,
    And, Or, Not, In, NotIn).  Differs for predicate ``Call`` nodes: instead of

        for _ in dispatch(args, trail, k): k_stmts

    it generates the stack-safe coroutine pattern::

        _gen  = dispatch(self, args, trail)        # child generator
        _st   = (yield Step(_gen, None))           # start child; get solution or DONE
        while _st is not _DONE:
            <k_stmts>                              # continuation (ends with yield Step(parent,None))
            _st = (yield Step(_gen, None))         # ask child for next solution

    ``k_stmts`` for the innermost goal must be
    ``[yield Step(parent, None)]`` — use ``compile_body_trampoline`` to build
    these correctly from the inside out.

    Note: ``Not`` (NAF) compiles its inner goal with ``compile_goal`` (simple
    mode) so the inner check runs via a local for loop.  NAF inner goals must
    therefore be simple-compiled predicates or primitive goals.
    """
    goal = deref(goal)

    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    match goal:

        # ── Deterministic goals — identical to simple mode ───────────────────
        case Is(left=l, right=r):
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case IsNot(left=l, right=r):
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        case Eq(left=l, right=r):
            return _deref_cmp(l, r, ast.Eq(), var_context, k_stmts)

        case NotEq(left=l, right=r):
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        case Lt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Lt(), var_context, k_stmts)

        case LtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.LtE(), var_context, k_stmts)

        case Gt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Gt(), var_context, k_stmts)

        case GtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.GtE(), var_context, k_stmts)

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            inner_k = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            return compile_goal_trampoline(
                l, db, var_context, trail_name, inner_k, self_name, parent_name
            )

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh("_m")
            left_stmts = compile_goal_trampoline(
                l, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            right_stmts = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            return [
                _assign_mark(mark, trail_name),
                *left_stmts,
                _undo_stmt(mark, trail_name),
                _assign_mark(mark, trail_name),
                *right_stmts,
                _undo_stmt(mark, trail_name),
            ]

        # ── Negation-as-failure ──────────────────────────────────────────────
        # Inner goal uses simple mode (local for-loop check; no deep recursion).
        # The trampoline outer function has no ``k`` parameter, so inject
        # ``k = None`` into the inner generator's local scope so that any
        # simple-mode predicate calls inside the inner stmts can pass it.
        case Not(operand=inner):
            naf_gen = _fresh("_naf_gen")
            naf_flag = _fresh("_naf")
            inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
            k_none_stmt = _assign("k", ast.Constant(None))
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=[k_none_stmt] + (inner_stmts or [ast.Pass()]),
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = _fresh("_m")
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

        # ── Membership / enumeration (Python for-loop, safe) ─────────────────
        case In(left=elem, right=collection):
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        # ── Non-membership ───────────────────────────────────────────────────
        case NotIn(left=elem, right=collection):
            found_flag = _fresh("_found")
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

        case ArithConstraint():
            raise NotImplementedError(
                "CLP(FD) arithmetic constraints (==+) are not yet implemented"
            )

        # ── Stack-safe predicate call ─────────────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call_trampoline(
                fname, call_args, call_kwargs, db, var_context,
                trail_name, k_stmts, self_name,
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal_trampoline: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal_trampoline: unsupported goal type {type(goal).__name__}: {goal!r}"
            )


def _compile_predicate_call_trampoline(
    fname: str,
    call_args: list,
    call_kwargs: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str,
) -> list[ast.stmt]:
    """Trampoline variant of _compile_predicate_call.

    Generates the coroutine-backtracking pattern::

        _gen_N  = dispatch(self, arg0, …, trail)
        _st_N   = (yield Step(_gen_N, None))
        while _st_N is not _DONE:
            <k_stmts>
            _st_N = (yield Step(_gen_N, None))

    When ``_gen_N`` yields ``Step(self, None)`` (solution found), the
    trampoline sends ``None`` to ``self`` so ``_st_N`` gets ``None`` (not
    DONE) and the while body runs.  When ``_gen_N`` yields
    ``Step(self, DONE)`` (exhausted), ``_st_N`` gets ``DONE`` and the
    while loop exits.

    WK-4 keyword normalisation is applied identically to the simple variant.
    """
    from clausal.pythonic_ast.nodes import Keyword as KWNode

    n_pos = len(call_args)
    arity = n_pos + len(call_kwargs)

    ordered_args: list = list(call_args)
    if call_kwargs:
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"No signature registered for {fname}/{arity}; "
                "cannot compile keyword call without a signature"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            if param_name not in kw_dict:
                raise RuntimeError(
                    f"Missing argument {param_name!r} in keyword call to {fname}/{arity}"
                )
            ordered_args.append(kw_dict[param_name])

    arg_exprs = [term_to_ast_expr(a, var_context) for a in ordered_args]
    gen_name = _fresh("_gen")
    status_name = _fresh("_st")

    call_expr = _dispatch_call_trampoline(fname, arity, arg_exprs, trail_name, self_name)

    # _gen_N = dispatch(self, arg0, …, trail)
    gen_assign = _assign(gen_name, call_expr)

    # _st_N = (yield Step(_gen_N, None))
    first_step = _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))

    # while _st_N is not _DONE: k_stmts; _st_N = (yield Step(_gen_N, None))
    loop_body = (k_stmts or [ast.Pass()]) + [
        _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))
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


# ── compile_body_trampoline ────────────────────────────────────────────────────


def compile_body_trampoline(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    parent_name: str = "parent",
    self_name: str = "self",
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction using the Step protocol.

    The leaf continuation is ``yield Step(parent, None)`` — one solution
    surfaced to the calling generator.

    Builds right-to-left: each goal wraps the next as its k_stmts, ending
    with the leaf.
    """
    k: list[ast.stmt] = [_yield_step_stmt(_name(parent_name), ast.Constant(None))]
    for goal in reversed(goals):
        k = compile_goal_trampoline(goal, db, var_context, trail_name, k, self_name, parent_name)
    return k


def _make_body_compiler_trampoline(
    db: Database,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a trampoline body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body_trampoline(clause.body, db, var_context, "trail")
    return _body_compiler


# ── compile_predicate_trampoline ───────────────────────────────────────────────


def _build_predicate_trampoline_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a trampoline-protocol compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate_trampoline`` and ``compile_predicate_trampoline_ast``.
    """
    arg_names = [f"arg{i}" for i in range(arity)]
    params = ["parent"] + arg_names + ["trail"]

    bootstrap = ast.Assign(
        targets=[_name("self", ast.Store())],
        value=ast.Yield(value=None),
        lineno=0, col_offset=0,
    )
    all_stmts: list[ast.stmt] = [bootstrap]

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity)
        body_stmts = body_compiler(clause, var_context)
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
        )
        subject = ast.Tuple(
            elts=[_name(n) for n in arg_names],
            ctx=ast.Load(),
        )
        all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    all_stmts.append(_yield_step_stmt(_name("parent"), _name("_DONE")))

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def compile_predicate_trampoline(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
) -> Callable:
    """Compile all clauses into a trampoline Step-protocol immortal coroutine.

    Unlike ``compile_predicate`` (simple/short-stack), the generated function:

    - Takes ``parent`` as first argument — the generator to Step back to.
    - Opens with ``self = yield`` — the trampoline's bootstrap hook; ``self``
      receives the generator's own reference so it can pass itself as
      ``parent`` to child generators.
    - At each solution: ``yield Step(parent, None)`` — suspends; the calling
      generator (via the trampoline) processes the solution, then resumes
      this generator to find more.
    - After all clauses exhausted: ``yield Step(parent, _DONE)`` — signals
      end of search for this predicate.

    Sub-predicate calls within clause bodies use the coroutine-backtracking
    pattern::

        _gen  = dispatch(self, args, trail)
        _st   = (yield Step(_gen, None))
        while _st is not _DONE:
            <continuation>
            _st = (yield Step(_gen, None))

    so the Python call stack does *not* grow with predicate recursion depth.

    Compiled function signature::

        def {functor}__{arity}(parent, arg0, …, argN, trail):
            self = yield   # bootstrap hook
            …              # clause match arms
            yield Step(parent, _DONE)

    The trampoline (``clausal.logic.trampoline.trampoline``) drives execution.
    ``continuation_search.Search`` (Step 7) will provide the ``__iter__``
    interface over solutions.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(db)

    if not clauses:
        fn = _compile_always_fail_trampoline(functor, arity)
        _install(db, functor, arity, fn)
        return fn

    func_def = _build_predicate_trampoline_funcdef(functor, arity, clauses, db, body_compiler)

    base_globals: dict = {
        "Compound": Compound,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "_db": db,
        "Step": Step,
        "_DONE": DONE,
    }
    if globals_:
        base_globals.update(globals_)

    fn = functiondef_to_function(func_def, globals_=base_globals)

    def _recompile_trampoline() -> Callable:
        return compile_predicate_trampoline(
            functor, arity, db.clauses_for(functor, arity), db,
            body_compiler=body_compiler, globals_=globals_,
        )

    _install(db, functor, arity, fn, lazy_recompile=_recompile_trampoline)
    return fn


def compile_predicate_trampoline_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a trampoline-mode compiled predicate.

    Identical to ``compile_predicate_trampoline`` but returns the AST node
    instead of executing it.  Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = ["parent"] + arg_names + ["trail"]
        func_def = ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[
                ast.Assign(
                    targets=[_name("self", ast.Store())],
                    value=ast.Yield(value=None),
                    lineno=0, col_offset=0,
                ),
                _yield_step_stmt(_name("parent"), _name("_DONE")),
            ],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
        ast.fix_missing_locations(func_def)
        return func_def
    return _build_predicate_trampoline_funcdef(functor, arity, clauses, db, body_compiler)


def _compile_always_fail_trampoline(functor: str, arity: int) -> Callable:
    """Trampoline variant: generator that immediately yields Step(parent, DONE)."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = ["parent"] + arg_names + ["trail"]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=[
            ast.Assign(
                targets=[_name("self", ast.Store())],
                value=ast.Yield(value=None),
                lineno=0, col_offset=0,
            ),
            _yield_step_stmt(_name("parent"), _name("_DONE")),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={"Step": Step, "_DONE": DONE})


# ── head_to_match_pattern ──────────────────────────────────────────────────────


def head_to_match_pattern(
    term: Any,
    var_context: dict[int, str],
) -> ast.pattern:
    """Convert a head field value to a Python ``ast.pattern`` node.

    Parameters
    ----------
    term:        value from a clause head (may be a Var, literal, dataclass, …)
    var_context: mutable dict mapping ``Var._id`` → Python local variable name.
                 Unbound Vars are registered here on first encounter.

    Pattern mapping
    ---------------
    Var (unbound)          → ``MatchAs(name="_v{id}")`` — captures the arg
    Var (bound)            → recurse after dereferencing
    None / True / False    → ``MatchSingleton``
    int, float, str, bytes → ``MatchValue(Constant(value))``
    complex                → ``MatchValue(Constant(value))``
    list                   → ``MatchSequence`` of sub-patterns
    Compound(f, args)      → ``MatchClass(Compound, functor=f, args=...)``
    functor dataclass      → ``MatchClass(cls, kwd field patterns)``
    other                  → ``MatchAs(name=None)``  (wildcard ``_``)
    """
    term = deref(term)

    # Unbound Var → MatchAs to capture the incoming argument
    if is_var(term):
        name = _var_python_name(term)
        var_context[term._id] = name
        return ast.MatchAs(pattern=None, name=name)

    # Python singletons
    if term is None or term is True or term is False:
        return ast.MatchSingleton(value=term)

    # Python scalar literals
    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.MatchValue(value=ast.Constant(value=term))

    # Python list → MatchSequence of sub-patterns
    if isinstance(term, list):
        return ast.MatchSequence(
            patterns=[head_to_match_pattern(e, var_context) for e in term]
        )

    # Compound(functor, args) → MatchClass on Compound
    if isinstance(term, Compound):
        f = term.functor
        if is_var(f):
            # Variable functor: cannot match statically → wildcard
            return ast.MatchAs(pattern=None, name=None)
        sub_patterns = [head_to_match_pattern(a, var_context) for a in term.args]
        return ast.MatchClass(
            cls=_name("Compound"),
            patterns=[],
            kwd_attrs=["functor", "args"],
            kwd_patterns=[
                ast.MatchValue(value=ast.Constant(value=f)),
                ast.MatchSequence(patterns=sub_patterns),
            ],
        )

    # Functor dataclass instance → MatchClass with field patterns
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        cls_name = type(term).__name__
        fields = dataclasses.fields(term)
        return ast.MatchClass(
            cls=_name(cls_name),
            patterns=[],
            kwd_attrs=[f.name for f in fields],
            kwd_patterns=[
                head_to_match_pattern(getattr(term, f.name), var_context)
                for f in fields
            ],
        )

    # Fallback: wildcard (accept anything, no binding)
    return ast.MatchAs(pattern=None, name=None)


# ── compile_head_to_match_case ─────────────────────────────────────────────────


def compile_head_to_match_case(
    head: Any,
    body_stmts: list[ast.stmt],
    var_context: dict[int, str],
    arity: int,
    trail_name: str = "trail",
    mark_name: str = "_mark",
) -> ast.match_case:
    """Compile a clause head into one ``match_case`` arm.

    Parameters
    ----------
    head:        head term (functor dataclass or Compound)
    body_stmts:  pre-compiled body statements (from compile_body or a placeholder)
    var_context: mutable dict; Var._id → python_name mappings are added here
    arity:       expected number of arguments (len of head's fields/args)
    trail_name:  name of the trail parameter in the enclosing function
    mark_name:   name for the trail mark local variable

    Generated structure::

        case (<per-arg patterns…>,):
            _mark = trail.mark()
            try:
                <body_stmts>
            finally:
                trail.undo(_mark)
    """
    arg_patterns = _head_arg_patterns(head, var_context, arity)
    outer_pattern = ast.MatchSequence(patterns=arg_patterns)

    # _mark = trail.mark()
    mark_assign = ast.Assign(
        targets=[_name(mark_name, ast.Store())],
        value=_call(_attr(trail_name, "mark")),
        lineno=0,
        col_offset=0,
    )

    # trail.undo(_mark)
    undo_stmt = ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name)))

    inner = body_stmts if body_stmts else [ast.Pass()]
    try_finally = ast.Try(
        body=inner,
        handlers=[],
        orelse=[],
        finalbody=[undo_stmt],
    )

    return ast.match_case(
        pattern=outer_pattern,
        guard=None,
        body=[mark_assign, try_finally],
    )


def _head_arg_patterns(
    head: Any, var_context: dict[int, str], arity: int
) -> list[ast.pattern]:
    """Extract per-argument patterns from a head term."""
    if isinstance(head, Compound):
        return [head_to_match_pattern(a, var_context) for a in head.args]
    if dataclasses.is_dataclass(head) and not isinstance(head, type):
        return [
            head_to_match_pattern(getattr(head, f.name), var_context)
            for f in dataclasses.fields(head)
        ]
    # Fallback: arity wildcards (accept any args)
    return [ast.MatchAs(pattern=None, name=None) for _ in range(arity)]


# ── compile_predicate ─────────────────────────────────────────────────────────

# Python 3.12+ added type_params to FunctionDef
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


def _build_predicate_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a simple/short-stack compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate`` (which then calls ``functiondef_to_function``) and
    ``compile_predicate_ast`` (which returns the FunctionDef directly).
    """
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + ["trail", "k"]

    all_stmts: list[ast.stmt] = []

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity)
        body_stmts = body_compiler(clause, var_context)
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
        )
        subject = ast.Tuple(
            elts=[_name(n) for n in arg_names],
            ctx=ast.Load(),
        )
        all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
) -> Callable:
    """Compile all clauses of a predicate into a dispatch generator function.

    Each clause becomes one ``match`` block in the generated function.
    Clauses are tried in order; when a head matches, the body runs.
    The generator yields one value per solution (via the body).

    Parameters
    ----------
    functor:       predicate name (used for the function name)
    arity:         predicate arity
    clauses:       all current clauses for this predicate
    db:            the database; used for dispatch lookup and signature registry
    body_compiler: optional callable(clause, var_context) → list[ast.stmt].
                   Defaults to the Step-5 body compiler (compile_body via db).
    globals_:      additional names injected into the compiled function scope.
                   ``Compound``, ``Var``, ``unify``, ``deref``, and ``_db``
                   are always included automatically.

    The compiled function signature is::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …

    ``k`` is reserved for the Step-7 CPS trampoline; the Step-5 body always
    ends with ``yield None`` regardless of ``k``.

    Returns the compiled callable.  Also installs it on
    ``PredicateTable.dispatch_fn`` so subsequent ``get_dispatch()`` calls work.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler(db)

    if not clauses:
        fn = _compile_always_fail(functor, arity)
        _install(db, functor, arity, fn)
        return fn

    func_def = _build_predicate_funcdef(functor, arity, clauses, db, body_compiler)

    base_globals: dict = {
        "Compound": Compound,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "_db": db,
    }
    if globals_:
        base_globals.update(globals_)

    fn = functiondef_to_function(func_def, globals_=base_globals)

    def _recompile_simple() -> Callable:
        return compile_predicate(
            functor, arity, db.clauses_for(functor, arity), db,
            body_compiler=body_compiler, globals_=globals_,
        )

    _install(db, functor, arity, fn, lazy_recompile=_recompile_simple)
    return fn


def compile_predicate_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a simple-mode compiled predicate.

    Identical to ``compile_predicate`` but returns the AST node instead of
    executing it.  Useful for inspecting or pretty-printing generated code.
    Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = arg_names + ["trail", "k"]
        return ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[ast.Return(value=ast.Constant(value=None)),
                  ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
    return _build_predicate_funcdef(functor, arity, clauses, db, body_compiler)


def _stub_body_stmts() -> list[ast.stmt]:
    """Placeholder body: succeed once by yielding None."""
    return [ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))]


def _compile_always_fail(functor: str, arity: int) -> Callable:
    """Return a generator function that matches any args but never yields."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + ["trail", "k"]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        # return; yield  →  generator that stops immediately
        body=[
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={})


def _install(
    db: Database,
    functor: str,
    arity: int,
    fn: Callable,
    lazy_recompile: Callable | None = None,
) -> None:
    """Install fn on PredicateTable.dispatch_fn, creating the table if needed.

    Also stores ``lazy_recompile`` on the table so that future assertz/asserta/
    retract calls (which clear dispatch_fn) will trigger lazy recompilation on
    the next get_dispatch() call rather than raising NotImplementedError.
    """
    table = db._table(functor, arity)
    table.dispatch_fn = fn
    if lazy_recompile is not None:
        table._lazy_recompile = lazy_recompile


__all__ = [
    # Simple / short-stack compilation
    "compile_predicate",
    "compile_predicate_ast",
    "compile_goal",
    "compile_body",
    # Trampoline / stack-safe compilation
    "compile_predicate_trampoline",
    "compile_predicate_trampoline_ast",
    "compile_goal_trampoline",
    "compile_body_trampoline",
    "DONE",
    # Shared utilities
    "head_to_match_pattern",
    "compile_head_to_match_case",
    "term_to_ast_expr",
    "arith_to_ast_expr",
]
