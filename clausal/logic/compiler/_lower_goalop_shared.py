"""Strategy-agnostic :class:`~clausal.logic.compiler.ir.GoalOp` lowering.

The ops in this module emit identical AST under both shallow and
trampoline strategies (see the legacy ``_compile_deterministic_goal``
/ ``_compile_shared_membership_goal`` helpers and the ``Or`` arm —
all strategy-invariant).  Both strategy-specific lowerings delegate
here after handling their own divergent ops.

The ``recurse`` parameter is the strategy-specific top-level ``lower``
function.  :class:`Sequence` and :class:`Alternate` dispatch their
children through *recurse* so the strategy's divergent ops (e.g.
``Negate``) lower in the correct dialect even when they appear nested
inside a shared op.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from typing import Callable, Union

from clausal.logic.compiler.ir import (
    Alternate,
    ArithEval,
    Branch,
    Dif,
    Fail,
    FDCompare,
    FDOp,
    GoalOp,
    ListPatternUnify,
    MemberIn,
    MetaCall,
    PyThunkOp,
    ReifiedKind,
    Sequence,
    StructuralEq,
    SubCall,
    Unify,
)
from clausal.logic.compiler.ite_reified import _three_way_reif_branch
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler._ast_helpers import (
    _MARK_PREFIX,
    _assign,
    _assign_mark,
    _call,
    _if,
    _in_iter_expr,
    _locate,
    _name,
    _undo_stmt,
)
from clausal.logic.compiler.terms_to_ast import (
    arith_to_ast_expr,
    runtime_eval_wrapper,
    term_to_ast_expr,
)
from clausal.logic.atoms import is_atom as _term_is_atom
from clausal.logic.predicate import field_names_for
from clausal.logic.variables import deref, is_var
from clausal.pythonic_ast.nodes import literal_value
from clausal.terms import LoadName


_FD_RUNTIME: dict[FDOp, str] = {
    "eq": "$fd_eq",
    "ne": "$fd_ne",
    "lt": "$fd_lt",
    "le": "$fd_le",
    "gt": "$fd_gt",
    "ge": "$fd_ge",
}


# (op_name, fd_true_name, fd_false_name) — the same triple the legacy
# ``_FD_REIFY_INFO`` carries, keyed here by :data:`ReifiedKind` literal
# rather than ``clausal.terms`` type so the IR has no term-level dep.
_FD_REIFY: dict[str, tuple[str, str, str]] = {
    "fd_eq": ("eq", "$fd_eq", "$fd_ne"),
    "fd_ne": ("ne", "$fd_ne", "$fd_eq"),
    "fd_lt": ("lt", "$fd_lt", "$fd_ge"),
    "fd_le": ("le", "$fd_le", "$fd_gt"),
    "fd_gt": ("gt", "$fd_gt", "$fd_le"),
    "fd_ge": ("ge", "$fd_ge", "$fd_lt"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Constant-list membership: the frozenset fast path
# ─────────────────────────────────────────────────────────────────────────────
#
# ``X in [c1, c2, …]`` lowers to a scan that ``unify()``s X against every
# element.  When the list is a run of compile-time constants the emitted
# code additionally carries a memoised frozenset and consults that instead,
# whenever the left operand derefs to a ground term of a type whose ``==``
# provably answers the same question as ``unify()``.  See
# :mod:`clausal.logic.runtime.const_set` for the soundness argument and for
# the runtime half of the guard.
#
# The gates below are the compile-time half.  They are deliberately narrow:
# the frozenset is built once and memoised, so the list expression must
# evaluate to the same values on every call, and the left-operand expression
# must be re-evaluable without side effects (it is emitted more than once).
# Anything else keeps the plain scan, unchanged.

#: Below this length the scan is cheap enough that the guard would not pay.
_CONST_SET_MIN_ELEMENTS = 2

#: Scalar types ``term_to_ast_expr`` renders as a bare ``ast.Constant``.
_CONST_SET_LITERALS = (int, float, bool, complex, str, bytes, Fraction)



#: The source spelling of each FD comparison, for an error context.
_FD_SPELLING = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=",
                "gt": ">", "ge": ">="}

def _is_const_element(term) -> bool:
    """True if *term* is a scalar literal, a zero-arity atom, or a global name.

    All three render to an expression whose value is fixed for the lifetime
    of the compiled function — an ``ast.Constant`` (an atom is the arity-0
    cell ``("foo",)``, a constant the compiler may fold) or a ``Name`` read
    from the function's globals — which is what lets the frozenset be built
    once and memoised.
    A Var, a nested list/dict, a compound term, a call, a splat: all
    excluded.
    """
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, LoadName):
        return True
    fields = field_names_for(term)
    if fields is not None:
        return fields == ()
    if _term_is_atom(term):
        # The arity-0 cell ``("foo",)``.  ``literal_value`` hands a tuple
        # back unchanged and ``tuple`` is not (and must not be) a
        # ``_CONST_SET_LITERALS`` member, so the atom shape is tested here
        # rather than through the literal arm below.
        return True
    value = literal_value(term)
    return value is None or isinstance(value, _CONST_SET_LITERALS)


def _const_set_eligible(elem, collection, var_context: dict) -> bool:
    """True if this ``MemberIn`` may carry the frozenset fast path."""
    if type(collection) is not list:
        return False
    if len(collection) < _CONST_SET_MIN_ELEMENTS:
        return False
    if not all(_is_const_element(e) for e in collection):
        return False
    # The left operand is emitted more than once (deref probe, set-lookup
    # source, scan unify), so it must be a repeatable, side-effect-free
    # expression.  A Var already in ``var_context`` is a plain local Name;
    # a Var *not* yet in it becomes a ``(_vN := Var())`` walrus, which must
    # not be duplicated — and being body-only it is unbound here anyway, so
    # it is the enumerating mode the fast path deliberately declines.
    elem = deref(elem)
    if is_var(elem):
        return elem._id in var_context
    return _is_const_element(elem)


def _const_set_prologue(ctx: CompilationContext, elem, collection):
    """Emit the memo-cell load and the left-operand deref, or return ``None``.

    ``None`` means "not eligible" — the caller then emits the plain scan
    exactly as before.  Otherwise returns
    ``(stmts, set_local, mode_local, elem_local)``
    where *stmts* leave ``set_local`` holding either the frozenset or
    ``False`` (ineligible, decided once at first execution by
    ``$const_set``) and ``elem_local`` holding the dereferenced left operand.
    """
    if "const_set" not in ctx.enabled_optimisations:
        return None
    if ctx.base_globals is None:
        return None
    if not _const_set_eligible(elem, collection, ctx.var_context):
        return None

    # One-slot memo cell, private to this predicate's globals.  ``$``-prefixed
    # so it cannot collide with a user name; ``ctx.fresh`` keeps it unique
    # across the callsites of one compilation.
    cell_name = ctx.fresh("$cset_")
    ctx.base_globals[cell_name] = [None]

    set_local = ctx.fresh("_cset")
    mode_local = ctx.fresh("_cmod")
    elem_local = ctx.fresh("_cel")

    def _cell_slot(store: bool) -> ast.expr:
        return _locate(ast.Subscript(
            value=_name(cell_name),
            slice=_locate(ast.Constant(value=0)),
            ctx=ast.Store() if store else ast.Load(),
        ))

    build = _call(
        _name("$const_set"),
        term_to_ast_expr(collection, ctx.var_context, eval_arith=False),
    )
    stmts = [
        _assign(set_local, _cell_slot(store=False)),
        _if(
            _locate(ast.Compare(
                left=_name(set_local),
                ops=[ast.Is()],
                comparators=[_locate(ast.Constant(value=None))],
            )),
            [_assign_multi(
                [_name(set_local, ast.Store()), _cell_slot(store=True)], build,
            )],
        ),
        # Which kind of set this callsite got, decided once per call rather
        # than twice: the guard and the key both read it.
        _assign(mode_local, _spellings_mode(set_local)),
        _assign(
            elem_local,
            _call(
                _name("$deref"),
                term_to_ast_expr(elem, ctx.var_context, eval_arith=False),
            ),
        ),
    ]
    return stmts, set_local, mode_local, elem_local


def _assign_multi(targets: list[ast.expr], value: ast.expr) -> ast.stmt:
    """``a = b[0] = value`` — chained assignment to several targets."""
    return _locate(ast.Assign(targets=targets, value=value))


def _spellings_mode(set_local: str) -> ast.expr:
    """``set_local.__class__ is $ATOM_SET`` — is this an all-atom callsite?

    ``$const_set`` answers an ``_AtomSpellings`` (a ``frozenset`` subclass)
    when every element of the constant list is an atom, and a plain
    ``frozenset`` otherwise.  The mode is only knowable at RUNTIME: the
    elements are usually ``LoadName`` reads of module globals, whose values
    the compiler does not have.  So both arms are emitted, and the prologue
    evaluates this once into a local that the guard and the key both read.
    """
    return _locate(ast.Compare(
        left=_locate(ast.Attribute(
            value=_name(set_local), attr="__class__", ctx=ast.Load(),
        )),
        ops=[ast.Is()],
        comparators=[_name("$ATOM_SET")],
    ))


def _is_atom_inline(elem_local: str) -> ast.expr:
    """``elem.__class__ is $str`` — ``atoms.is_atom`` spelled out in the
    emitted code.

    STAGE 2 of the atoms-as-str flip: an atom IS the Python ``str``, so the
    test is one class check (it was ``tuple`` + ``len == 1`` + slot-0 ``str``
    for the arity-0 cell).  Inline rather than the ``$cset_atom`` call this
    replaces on the hot arm, on measurement: the call was 67 ns of a ~110 ns
    fast path.  A string is the chars CARRIER (a 2-tuple) and never passes.

    ``elem_local`` is a plain local Name (the prologue's ``$deref`` result),
    so repeating it costs nothing and has no side effect.
    """
    return _locate(ast.Compare(
        left=_locate(ast.Attribute(
            value=_name(elem_local), attr="__class__", ctx=ast.Load(),
        )),
        ops=[ast.Is()],
        comparators=[_name("$str")],
    ))


def _const_set_lookup(set_local: str, mode_local: str, elem_local: str) -> ast.expr:
    """``elem in set_local``.

    STAGE 2: in spellings mode the set holds the atoms themselves (an atom IS
    its spelling), and in mixed mode it holds whole terms -- the operand is
    looked up as it stands in both, so *mode_local* no longer selects a
    slot-0 read.  It stays in the signature for the guard's sake.
    """
    return _locate(ast.Compare(
        left=_name(elem_local),
        ops=[ast.In()],
        comparators=[_name(set_local)],
    ))


def _const_set_guard(set_local: str, mode_local: str, elem_local: str) -> ast.expr:
    """``set_local and (<the operand may be looked up in this set>)``.

    The first conjunct rejects a callsite ``$const_set`` refused.  The second
    rejects a left operand — an unbound Var, a compound term, a list — whose
    ``==`` is not known to answer the same question as ``unify()``, or which
    is not hashable at all.  Either way the scan runs instead; for an unbound
    Var that is what preserves list-order enumeration.

    What "may be looked up" means depends on what the set holds:

    * **all-atom callsite** (``$const_set`` answered an ``_AtomSpellings``,
      which holds spellings): the operand must be an ATOM, full stop.  Any
      other term — a ``str`` above all — could otherwise test itself against
      a spelling and answer a hit for a term that does not unify with any
      element.  Everything else takes the scan, which is always correct and,
      against an all-atom list, fails on the first comparison.
    * **mixed callsite** (a plain ``frozenset`` of whole terms): a whitelisted
      type OR an atom, as before.  An ATOM cannot be spelled as a type — after
      the flip it is the arity-0 cell ``("bar",)``, and admitting ``tuple``
      wholesale would admit compound cells, whose ``==`` is not their
      ``unify()`` (see ``runtime/const_set``'s module docstring) — so
      ``$cset_atom`` tests the shape, ``or``-ed so that an operand which
      already passed the class test never pays for the call.  The mixed arm
      keeps the call: it runs only after the class test has already missed,
      which for a mixed list is the uncommon case.

    The all-atom arm spells the shape test out inline instead — see
    :func:`_is_atom_inline` for the measurement that says why.
    """
    mixed = _locate(ast.BoolOp(op=ast.Or(), values=[
        _locate(ast.Compare(
            left=_locate(ast.Attribute(
                value=_name(elem_local), attr="__class__", ctx=ast.Load(),
            )),
            ops=[ast.In()],
            comparators=[_name("$CSET_TYPES")],
        )),
        _call(_name("$cset_atom"), _name(elem_local)),
    ]))
    return _locate(ast.BoolOp(op=ast.And(), values=[
        _name(set_local),
        _locate(ast.IfExp(
            test=_name(mode_local),
            body=_is_atom_inline(elem_local),
            orelse=mixed,
        )),
    ]))


def lower_shared(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
    recurse: Callable[[GoalOp, CompilationContext, list[ast.stmt]], list[ast.stmt]],
) -> Union[list[ast.stmt], None]:
    """Lower a strategy-agnostic op, or return ``None`` if *ir* is
    strategy-specific and must be handled by the caller."""
    with ctx.at_position(ir.position):
        return _lower_shared_body(ir, ctx, k_stmts, recurse)


def _lower_shared_body(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
    recurse: Callable[[GoalOp, CompilationContext, list[ast.stmt]], list[ast.stmt]],
) -> Union[list[ast.stmt], None]:
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    match ir:

        case Sequence(ops=ops):
            k = list(k_stmts)
            for op in reversed(ops):
                k = recurse(op, ctx, k)
            return k

        # ── Constant failure (legacy ``goal is False``) — drops the
        # continuation entirely.  In a Sequence right-to-left fold this
        # truncates everything to its left.
        case Fail():
            return []

        # ── PyThunk as a body goal — evaluate the embedded callable
        # for side effects, then continue.  Identical between shallow
        # and trampoline.
        case PyThunkOp(thunk=thunk):
            call_expr = term_to_ast_expr(thunk, var_context, eval_arith=False)
            return [ast.Expr(value=call_expr)] + list(k_stmts)

        # ── Reified Branch — three-way ITE.  General Branch
        # (``reified_test is None``) is strategy-specific and handled
        # in the ``lower_python_{shallow,trampoline}`` caller.
        case Branch(test=t_op, then=th_op, else_=el_op, reified_test=kind) \
                if kind is not None:
            return _lower_reified_branch(
                ctx, kind, t_op, th_op, el_op, k_stmts, recurse,
            )

        case Alternate(ops=ops):
            mark = ctx.fresh(_MARK_PREFIX)
            out: list[ast.stmt] = [_assign_mark(mark, trail_name)]
            for op in ops:
                out.extend(recurse(op, ctx, k_stmts))
                out.append(_undo_stmt(mark, trail_name))
            return out

        case Unify(l=l, r=r):
            # A lambda on either side (e.g. ``G is ((A, B) <- ...)``) must be
            # hoisted to a compiled closure here — otherwise it reaches runtime
            # as a raw Lambda node that call_goal cannot invoke. See
            # _hoist_lambdas_in_term.
            from .control_constructs import _hoist_lambdas_in_term
            lambda_defs: list = []
            l = _hoist_lambdas_in_term(ctx, l, lambda_defs)
            r = _hoist_lambdas_in_term(ctx, r, lambda_defs)
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return lambda_defs + [
                _assign_mark(mark, trail_name),
                _if(_call(_name("$unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case ArithEval(target=l, expr=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context)
            # ``$present``: an integral Fraction produced anywhere in the
            # compiled tree is handed to unify as an int (predicate.py).
            r_expr = arith_to_ast_expr(r, var_context)
            wrapper = runtime_eval_wrapper(r)
            if wrapper is not None:
                # Ruling R9 A2 (2026-09-27): an operand that is not a literal
                # arithmetic tree -- a VARIABLE, whatever it is bound to at
                # runtime, or a literal term -- is evaluated through the one
                # evaluable table; it used to be unified unevaluated.
                r_expr = _call(_name(wrapper), r_expr)
            r_expr = _call(_name("$present"), r_expr)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("$unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case Dif(l=l, r=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("$dif"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case StructuralEq(l=l, r=r, negate=False):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("$structural_eq"), l_expr, r_expr), k_stmts)]

        case StructuralEq(l=l, r=r, negate=True):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("$structural_neq"), l_expr, r_expr), k_stmts)]

        case FDCompare(op=op, l=l, r=r):
            # Both sides are arithmetic: an UNDECLARED functor built here is
            # type_error(evaluable, F/N), in the constraint's own context.
            from .terms_to_ast import construction_context  # noqa: PLC0415
            with construction_context(
                    "evaluable", f"({_FD_SPELLING.get(op, op)})/2"):
                l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
                r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(
                    _call(_name(_FD_RUNTIME[op]), l_expr, r_expr, _name(trail_name)),
                    k_stmts,
                ),
            ]

        # ── Body-side star-list unification — delegate to the
        # ``_compile_star_is`` helper in ``.star_segments``.  Single
        # vs multi-star routing happens inside that helper; the IR
        # carries only the raw pair (see ``ir.py::ListPatternUnify``).
        case ListPatternUnify(star_side=ss, other_side=os):
            from .star_segments import _compile_star_is
            return _compile_star_is(ctx, ss, os, k_stmts)

        # ── Meta-predicate calls — delegate to the ``_compile_*``
        # helpers in :mod:`.control_constructs`.  Each ``MetaCall``
        # kind has a dedicated helper; inner goals lower via
        # :func:`.control_constructs._lower_inner` (shallow) or
        # :func:`._lower_inner_trampoline` (catch's trampoline branch).
        # ``args`` carries raw terms — see ``terms_to_goalop`` for
        # the rationale.  Function-local imports break the shared ↔
        # control_constructs cycle.
        case MetaCall(kind=kind, args=margs):
            return _lower_meta_call(ctx, kind, margs, k_stmts)

        # ── Predicate call — delegate to ``_compile_predicate_call_impl``.
        # That helper performs WK-4 keyword normalisation,
        # lambda-hoist (advances ``ctx.fresh``), ``term_to_ast_expr`` per
        # arg, then ``ctx.strategy.emit_sub_call``.  Keyword normalisation
        # was done by ``terms_to_goalop`` (WK-4) so we pass ``kwargs=[]``
        # here.  Function-local import breaks the shared ↔ goal_shallow
        # cycle (ratified B4/B6 idiom).
        case SubCall(fname=fname, arity=_arity, args=args):
            # Slice E4c: tail_recursive hint — emit the TRO tail
            # (``_compile_tro_tail``) and drop *k_stmts*.  ``ctx.tro_mode``
            # carries the per-clause-compile mode (``"loop"`` /
            # ``"signal"``); it must be set by the caller that wrote the
            # hint, otherwise refuse to lower (guards against a stray
            # hint reaching ``_compile_body_impl``).
            if ir.tail_recursive:
                if ctx.tro_mode is None:
                    raise AssertionError(
                        "SubCall.tail_recursive set but ctx.tro_mode is None — "
                        "TRO hint reached non-TRO compilation context."
                    )
                from clausal.terms import Call, LoadName
                from clausal.logic.compiler.tro import _compile_tro_tail
                fake_tail_call = Call(
                    func=LoadName(name=fname), args=list(args), kwargs=[],
                )
                return _compile_tro_tail(
                    ctx, fake_tail_call, ir.arity, ctx.var_context,
                    ctx.db, ctx.trail_name,
                    tro_mode=ctx.tro_mode,
                    check_indices=ir.tro_check_indices or None,
                )
            from clausal.logic.compiler.goal_shallow import (
                _compile_predicate_call_impl,
            )
            # Slice E4b: destructive-reuse hint — rewrite fname to the
            # ``_dr_<name>__<arity>`` variant so dispatch emission picks
            # the in-place bucket function.  The DR variants are
            # unconditionally registered in ``base_globals`` by
            # ``predicate.py`` (they're builtin dispatch entries), so
            # the rename is always resolvable.
            if ir.destructive_reuse:
                _DR_NAME_MAP = {
                    "append": "$dr_append__3",
                    "dict_put": "$dr_dict_put__4",
                    "set_union": "$dr_set_union__3",
                    "reverse": "$dr_reverse__2",
                }
                fname = _DR_NAME_MAP.get(fname, fname)
            return _compile_predicate_call_impl(
                ctx, fname, args, [], k_stmts,
                direct_bucket_ref=ir.direct_bucket_ref,
                direct_joint_bucket_ref=ir.direct_joint_bucket_ref,
                tail_position=ir.tail_position,
            )

        case MemberIn(elem=elem, collection=collection, negate=False):
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            fast = _const_set_prologue(ctx, elem, collection)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            iter_expr = _in_iter_expr(elem, coll_expr)
            prologue: list[ast.stmt] = []
            if fast is not None:
                # Feed the *same* loop a one- or zero-element tuple instead of
                # the list, so the continuation is emitted once.  Branching
                # around it would double the code size of every membership
                # goal and square it for nested ones.
                prologue, set_local, mode_local, elem_local = fast
                iter_local = ctx.fresh("_cit")
                prologue.append(ast.If(
                    test=_const_set_guard(set_local, mode_local, elem_local),
                    body=[_assign(iter_local, _locate(ast.IfExp(
                        test=_const_set_lookup(set_local, mode_local, elem_local),
                        # The left operand is ground here, so yielding it in
                        # place of the matching element is indistinguishable:
                        # the loop's unify() then succeeds by identity and
                        # binds nothing, exactly as it would against the
                        # element the scan would have found.
                        body=_locate(ast.Tuple(
                            elts=[_name(elem_local)], ctx=ast.Load(),
                        )),
                        orelse=_locate(ast.Tuple(elts=[], ctx=ast.Load())),
                    )))],
                    orelse=[_assign(iter_local, iter_expr)],
                ))
                iter_expr = _name(iter_local)
            return prologue + [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=iter_expr,
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("$unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        case MemberIn(elem=elem, collection=collection, negate=True):
            found_flag = ctx.fresh("_found")
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            fast = _const_set_prologue(ctx, elem, collection)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            scan = [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_in_iter_expr(elem, coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("$unify"), elem_expr, _name(loop_var), _name(trail_name)),
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
            ]
            test_flag = _if(
                ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts,
            )
            if fast is None:
                return scan + [test_flag]
            # ``not in`` already tests the flag *outside* the loop, so here
            # the fast path can set the flag directly — no continuation to
            # duplicate.
            prologue, set_local, mode_local, elem_local = fast
            return prologue + [
                ast.If(
                    test=_const_set_guard(set_local, mode_local, elem_local),
                    body=[_assign(found_flag,
                                  _const_set_lookup(set_local, mode_local,
                                                    elem_local))],
                    orelse=scan,
                ),
                test_flag,
            ]

    return None


def _lower_reified_branch(
    ctx: CompilationContext,
    kind: ReifiedKind,
    test_op: GoalOp,
    then_op: GoalOp,
    else_op: GoalOp,
    k_stmts: list[ast.stmt],
    recurse,
) -> list[ast.stmt]:
    """Emit the three-way reified ITE pattern, byte-identical to the
    legacy ``_compile_reified_ite_eq`` / ``_compile_reified_ite_fd``.

    The IR's ``reified_test`` literal carries enough information that
    operands can be read directly off ``test_op`` without re-deriving
    from a term — ``"unify"`` and ``"dif"`` come from a :class:`Unify`
    or :class:`Dif` IR op respectively, ``"fd_*"`` from :class:`FDCompare`.
    """
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    reif_var = ctx.fresh("_reif")
    l = test_op.l
    r = test_op.r
    l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(r, var_context, eval_arith=False)

    then_stmts = recurse(then_op, ctx, k_stmts)
    else_stmts = recurse(else_op, ctx, k_stmts)

    if kind == "unify" or kind == "dif":
        if kind == "dif":
            true_stmts, false_stmts = else_stmts, then_stmts
        else:
            true_stmts, false_stmts = then_stmts, else_stmts
        mark = ctx.fresh(_MARK_PREFIX)
        undetermined = [
            _assign_mark(mark, trail_name),
            _if(_call(_name("$unify"), l_expr, r_expr, _name(trail_name)), true_stmts),
            _undo_stmt(mark, trail_name),
            _if(_call(_name("$dif"), l_expr, r_expr, _name(trail_name)), false_stmts),
        ]
        reif_call = _call(_name("$reify_eq"), l_expr, r_expr, _name(trail_name))
        return _three_way_reif_branch(
            reif_var, reif_call, true_stmts, false_stmts, undetermined,
        )

    # FD reified.
    op_name, fd_true_name, fd_false_name = _FD_REIFY[kind]
    mark = ctx.fresh(_MARK_PREFIX)
    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_true_name), l_expr, r_expr, _name(trail_name)), then_stmts),
        _undo_stmt(mark, trail_name),
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_false_name), l_expr, r_expr, _name(trail_name)), else_stmts),
        _undo_stmt(mark, trail_name),
    ]
    reif_call = _call(
        _name("$reify_fd"), ast.Constant(op_name), l_expr, r_expr, _name(trail_name),
    )
    return _three_way_reif_branch(
        reif_var, reif_call, then_stmts, else_stmts, undetermined,
    )


def _lower_meta_call(
    ctx: CompilationContext,
    kind: str,
    margs: dict,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Dispatch a :class:`MetaCall` to the matching legacy helper.

    One arm per closed :data:`~clausal.logic.compiler.ir.MetaKind`
    literal.  Each arm reads the fixed ``args`` schema documented on
    :class:`~clausal.logic.compiler.ir.MetaCall` and forwards to the
    corresponding ``_compile_*`` helper in :mod:`.control_constructs`.
    """
    from .control_constructs import (
        _compile_once, _compile_call_nth, _compile_count_all,
        _compile_setup_call_cleanup, _compile_freeze, _compile_when,
        _compile_find_all_core,
        _compile_throw, _compile_catch,
    )
    from .tabled_naf import _compile_tabled_naf_simple
    from ._ast_helpers import _name, _call
    from .terms_to_ast import term_to_ast_expr
    # ── WFS-sound NAF of a call to a tabled predicate.  The legacy
    # ``_compile_tabled_naf_simple`` takes the raw :class:`Call` term
    # and handles kwargs signature normalisation itself.
    if kind == "naf_tabled":
        return _compile_tabled_naf_simple(ctx, margs["call"], k_stmts)
    # ``forall`` rewrites to ``Not(And(cond, Not(action)))``.  Legacy
    # re-dispatched through the shallow goal compiler; Slice D7c-β2
    # routes that through the IR pipeline via the local
    # :func:`_lower_inner` wrapper so no legacy dispatcher is reached.
    if kind == "forall":
        from clausal.terms import And, Not
        from .control_constructs import _lower_inner
        rewritten = Not(operand=And(
            left=margs["cond"],
            right=Not(operand=margs["action"]),
        ))
        return _lower_inner(ctx, rewritten, k_stmts)
    if kind == "throw":
        return _compile_throw(ctx, margs["term"])
    if kind == "halt":
        code_arg = margs["code"]
        if code_arg is None:
            return [ast.Raise(exc=_call(_name("SystemExit"), ast.Constant(0)))]
        code_expr = term_to_ast_expr(code_arg, ctx.var_context, eval_arith=True)
        # The code's VALUE, not the Var holding it: ``halt(X)`` with X bound
        # exited with the Var object as its status (SystemExit(AttVar)).
        code_expr = _call(_name("$deref_walk"), code_expr)
        return [ast.Raise(exc=_call(_name("SystemExit"), code_expr))]
    if kind == "once":
        return _compile_once(ctx, margs["inner"], k_stmts)
    if kind == "call_nth":
        return _compile_call_nth(ctx, margs["inner"], margs["n"], k_stmts)
    if kind == "count_all":
        return _compile_count_all(
            ctx, margs["inner"], margs["count"], k_stmts,
        )
    if kind == "setup_call_cleanup":
        return _compile_setup_call_cleanup(
            ctx, margs["setup"], margs["call"], margs["cleanup"], k_stmts,
        )
    if kind == "call_cleanup":
        # Legacy sugar: ``call_cleanup(C, Cl)`` → ``setup_call_cleanup(True, C, Cl)``.
        return _compile_setup_call_cleanup(
            ctx, True, margs["call"], margs["cleanup"], k_stmts,
        )
    if kind == "freeze":
        return _compile_freeze(ctx, margs["var"], margs["inner"], k_stmts)
    if kind == "when":
        return _compile_when(ctx, margs["cond"], margs["inner"], k_stmts)
    if kind == "findall":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=False, dedup=False,
        )
    if kind == "bagof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=False,
        )
    if kind == "setof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=True,
        )
    if kind == "catch":
        return _compile_catch(
            ctx, margs["inner"], margs["catcher"], margs["recovery"], k_stmts,
        )
    if kind == "catch_error":
        return _compile_catch(
            ctx, margs["inner"], margs["error"], True, k_stmts,
            always_catch=True,
        )
    if kind == "catch_recover":
        return _compile_catch(
            ctx, margs["inner"], margs["error"], margs["recovery"], k_stmts,
            always_catch=True,
        )
    raise NotImplementedError(
        f"_lower_meta_call: unknown MetaCall kind {kind!r}"
    )


__all__ = ["lower_shared"]
