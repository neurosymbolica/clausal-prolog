"""``terms_to_goalop`` — convert a clause body (term/AST-node list) into
a :class:`~clausal.logic.compiler.ir.GoalOp` tree.

Slice D2 prototype: handles the binding / constraint / membership subset
plus list-body and ``TupleLiteral`` conjunction.  Everything else raises
``NotImplementedError`` via :func:`_not_yet` so the D4 parallel-implementation
harness can fall back to the legacy path cleanly.

Subset covered:

- ``nodes.Unify`` / ``nodes.DoesNotUnify`` → :class:`Unify` / :class:`Dif`
- ``nodes.Evaluate`` (``eval_(RHS, LHS)``; formerly ``LHS := RHS``) → :class:`ArithEval`
- ``nodes.Lt`` / ``LtE`` / ``Gt`` / ``GtE`` / ``ArithEq`` / ``ArithNeq``
  → :class:`FDCompare`
- ``nodes.StructuralEq`` / ``StructuralNeq`` → :class:`StructuralEq`
- ``nodes.in_`` / ``NotIn`` → :class:`MemberIn`
- ``list`` body / ``TupleLiteral`` in goal position → flattened
  :class:`Sequence`

Coverage expands one construct at a time through Slice D5 (see
``todo/slice_d_goalop_ir.md``).
"""

from __future__ import annotations

from typing import Any, NoReturn

from clausal.pythonic_ast import nodes
from clausal.terms import DictTerm, PyThunk, Undefined
from clausal.logic.variables import is_var
from clausal.logic.compiler.terms_to_ast import (
    _is_star_list,
    _dotted_name_from_loadattr,
)
from clausal.logic.compiler.ite_reified import _is_reifiable
from clausal.logic.compiler.tabled_naf import _is_tabled_naf
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
    Negate,
    PyThunkOp,
    ReifiedKind,
    Sequence,
    StructuralEq,
    SubCall,
    Unify,
)


# Meta-predicate names that must never be converted to a plain
# :class:`SubCall` — the legacy dispatcher routes them to dedicated
# ``_compile_*`` helpers and we mirror that via explicit :class:`MetaCall`
# arms below.  Pre-D7c-β1 this list also gated a legacy-fallback deferral
# for meta-name calls with unexpected arity/kwargs (e.g. ``findall/4``);
# that deferral is gone — such calls now convert to :class:`SubCall` and
# resolve against the database like any other user predicate, which is
# what the legacy path did at those arities too.


def terms_to_goalop(body: list[Any], db: Any = None) -> GoalOp:
    """Convert a clause body (list of goals) to a :class:`Sequence`.

    Each element is converted recursively; nested list / ``TupleLiteral``
    conjunctions flatten into the outer :class:`Sequence`.

    ``db`` (when provided) is consulted for two D5e-era decisions:

    - WK-4 keyword normalisation on :class:`SubCall` — calls with
      ``kwargs`` need a predicate signature to reorder them.
    - Tabled-NAF detection — ``Not(Call(tabled_pred))`` must stay on
      the legacy path until :class:`MetaCall` support lands in D5f;
      without ``db`` we cannot tell, so such calls fall back.
    """
    ops: list[GoalOp] = []
    _extend(ops, body, db)
    return Sequence(ops=ops)


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


_FD_OP: dict[type, FDOp] = {
    nodes.ArithEq: "eq",
    nodes.ArithNeq: "ne",
    nodes.Lt: "lt",
    nodes.LtE: "le",
    nodes.Gt: "gt",
    nodes.GtE: "ge",
}


_REIFIED_KIND: dict[type, ReifiedKind] = {
    nodes.Unify: "unify",
    nodes.DoesNotUnify: "dif",
    nodes.ArithEq: "fd_eq",
    nodes.ArithNeq: "fd_ne",
    nodes.Lt: "fd_lt",
    nodes.LtE: "fd_le",
    nodes.Gt: "fd_gt",
    nodes.GtE: "fd_ge",
}


def _extend(ops: list[GoalOp], body: Any, db: Any) -> None:
    """Flatten list / ``TupleLiteral`` conjunctions; convert each goal."""
    # ``True`` is conjunction identity — emit no ops.  ``False`` lowers
    # to :class:`Fail`, whose lowering returns ``[]`` and in a
    # right-to-left :class:`Sequence` fold truncates everything to its
    # left.
    body = nodes.literal_value(body)
    if body is True:
        return
    if body is False:
        ops.append(Fail())
        return
    if isinstance(body, list):
        for goal in body:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.TupleLiteral):
        for goal in body.elements:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.And):
        # Flatten arbitrarily-nested ``And(And(a, b), c)`` into
        # ``[a, b, c]``; the right-to-left :class:`Sequence` fold
        # produces the same AST as the nested-dispatch form.  The
        # :class:`And`'s own ``position`` is the outermost conjunction
        # span — useful as a fallback for child ops whose own position
        # is missing, but we don't stamp it onto a wrapper here because
        # the flattened ops carry their own.
        _extend(ops, body.left, db)
        _extend(ops, body.right, db)
        return
    if isinstance(body, nodes.CompareChain):
        # A10-F009: a chained comparison ``0 < X < 10`` is emitted as
        # CompareChain([Lt(0, X), Lt(X, 10)]) but had no lowerer here. Expand
        # it into its individual comparison goals — the shared operand (X) is
        # the same Var by identity, so it is still evaluated once (the node's
        # documented single-evaluation semantics).
        for comparison in body.comparisons:
            _extend(ops, comparison, db)
        return
    ops.append(_convert(body, db))


def _convert(goal: Any, db: Any) -> GoalOp:
    """Convert one goal term to a :class:`GoalOp`, stamping its source
    position from the originating term.

    Slice G threads :attr:`pythonic_ast.nodes.Node.position` (and the
    matching attribute carried by
    ``DictTerm`` / etc.) onto the produced op.  When the goal is a
    Python literal that carries no position (e.g. bare ``True`` /
    ``False``), the op's ``position`` stays ``None`` — call sites that
    care must scope the surrounding term's position.
    """
    op = _convert_inner(goal, db)
    # Terms (DictTerm/SetTerm/PyThunk) carry ``_position``
    # (underscore-prefixed — reserved, unreachable as a Clausal field name).
    # pythonic_ast Nodes still use ``position``; check both so this helper
    # works for either flavour of source node.
    pos = getattr(goal, "_position", None)
    if pos is None:
        pos = getattr(goal, "position", None)
    if pos is not None and op.position is None:
        op.position = pos
    return op


def _convert_inner(goal: Any, db: Any) -> GoalOp:
    # ``PyThunk`` as a body goal — wrap in :class:`PyThunkOp`; the
    # lowering reuses ``term_to_ast_expr`` to emit a single
    # ``ast.Expr(call)``.
    if isinstance(goal, PyThunk):
        return PyThunkOp(thunk=goal)
    # A bare logic variable in goal position.  All Clausal logic
    # variables are ``AttVar`` instances (``Var = AttVar``), so a clause
    # body whose goal is just a variable — typically a generated rulebase
    # ending in an output variable, e.g. ``... , RESULT`` — reaches here
    # as an ``AttVar``.  Only goals (never operands) flow through
    # ``_convert``, so any variable here is genuinely in goal position.
    # Reject it with a clear, actionable error rather than the generic
    # ``_not_yet`` internal-shape crash; ``compile_predicate_trampoline``
    # enriches it with the offending predicate's name.
    if is_var(goal):
        raise BareGoalVariableError(goal)
    goal = nodes.literal_value(goal)
    # ``False`` reaching ``_convert`` (e.g. as an :class:`Or` arm or an
    # :class:`IfExpr` branch) — same :class:`Fail` op the conjunction
    # path emits.  ``True`` in the same position becomes an empty
    # :class:`Sequence` (the unit) so the surrounding op sees an
    # always-succeed leaf.
    if goal is False:
        return Fail()
    if goal is True:
        return Sequence(ops=[])
    # ``Undefined`` (the Kleene K3 third truth value) is *data*, never a goal
    # outcome.  ``True`` compiles to the unit and ``False`` to ``Fail`` above,
    # but there is no third success/failure mode: a bare ``Undefined`` in goal
    # position is an author error (e.g. writing ``Undefined`` where a call was
    # meant).  Reject it at compile time with a clear, actionable message —
    # mirroring ``BareGoalVariableError`` — rather than silently treating it
    # as truthy/falsy or crashing in ``_not_yet``.
    if goal is Undefined:
        raise BareGoalUndefinedError()
    # ``Undefined`` in goal position also arrives here as an unresolved
    # ``LoadName`` node (it is an injected runtime binding, not a parser
    # literal like ``True``/``False`` which become ``BoolLiteral``s and
    # deref to Python bools above).  Reject that shape too, with the same
    # clear error, before it falls through to the generic ``_not_yet``.
    if isinstance(goal, nodes.LoadName) and goal.name == "Undefined":
        raise BareGoalUndefinedError()
    # ``TupleLiteral`` reaching ``_convert`` (nested inside an
    # :class:`Or` arm, :class:`Not` operand, or :class:`IfExpr` branch
    # rather than at the conjunction top where ``_extend`` flattens
    # it) — flatten its elements into an inner :class:`Sequence`.
    if isinstance(goal, nodes.TupleLiteral) and goal.elements:
        inner_ops: list[GoalOp] = []
        _extend(inner_ops, list(goal.elements), db)
        return Sequence(ops=inner_ops)
    # ``And`` reaching ``_convert`` (nested inside an :class:`Or` arm,
    # :class:`Not` operand, or :class:`IfExpr` branch — at the
    # conjunction top :func:`_extend` flattens ``And`` directly).  Wrap
    # the flattened conjunction in an inner :class:`Sequence`.
    if isinstance(goal, nodes.And):
        inner_ops: list[GoalOp] = []
        _extend(inner_ops, goal.left, db)
        _extend(inner_ops, goal.right, db)
        return Sequence(ops=inner_ops)
    if (type(goal) is str and goal == "fail") or (
            isinstance(goal, nodes.LoadName) and goal.name == "fail"):
        # ``fail`` as a GOAL is failure (ISO 7.8.2), the same as ``False``
        # and as ``call(fail)`` -- operator ruling 2026-09-25.  ``fail`` is
        # not a truth-value alias (``true``/``false`` are), so it reaches
        # here as the ATOM (declared) or an unresolved ``LoadName`` (needs
        # no declaration: ``compiler_v2.BUILTIN_GOAL_ATOMS``); it used to be
        # a call of an undefined ``fail/0``: existence_error.
        return Fail()
    if type(goal) is str:
        # STAGE 2 of the atoms-as-str flip: an atom in GOAL position is the
        # call of the 0-arity predicate of its name -- the rule solve/1 and
        # call/N already apply, here for a bare ``p`` conjunct in a body
        # (``p()`` and ``call(p)`` were the only accepted spellings before).
        goal = nodes.Call(func=nodes.LoadName(name=goal), args=[], kwargs=[])
    elif isinstance(goal, (nodes.LoadName, nodes.LoadAttr)):
        # A bare NAME in goal position that is not an atom of this module: a
        # builtin's name (``p <- nl``), an ``-import_from``'d predicate (the
        # rewriter spells it ``lib.ask``), or a dotted ``lib.ask``.  It is the
        # call of that 0-arity predicate, as the atom above is, and as in ISO
        # and Scryer.  It used to reach ``_not_yet`` below and fail the load
        # with "goal shape not yet supported (LoadName)".
        goal = nodes.Call(func=goal, args=[], kwargs=[])
    match goal:
        # ``Or`` stays binary — nested ``Or(Or(a, b), c)`` must round-trip
        # to nested ``Alternate`` so the lowering emits the same nested
        # mark/undo pattern as the legacy dispatcher.  Flattening would
        # change the number of trail marks and break byte-for-byte
        # AST equivalence.
        case nodes.Or(left=l, right=r):
            return Alternate(ops=[_convert(l, db), _convert(r, db)])

        # ``Not(op)`` → ``Negate(op)``.  Tabled NAF (``Not`` of a call
        # to a tabled predicate) routes through
        # ``_compile_tabled_naf_simple`` in the legacy path rather than
        # the inline NAF that ``lower(Negate)`` emits.  Slice D5h maps
        # those to :class:`MetaCall` with ``kind="naf_tabled"`` (Option
        # A from ``todo/slice_d_goalop_ir.md``) — semantically distinct
        # from standard NAF (WFS delay semantics), so a dedicated kind
        # rather than a hint on ``Negate``.  Non-tabled ``Not(Call)``
        # is fine — ``SubCall`` lowering + ``Negate`` lowering compose
        # to the same inline-NAF AST the legacy dispatcher emits.
        case nodes.Not(operand=op):
            if isinstance(op, nodes.Call) and _is_tabled_naf(op, db):
                return MetaCall(kind="naf_tabled", args={"call": op})
            return Negate(op=_convert(op, db))

        # ``IfExpr(test, body, orelse)`` → ``Branch``.  ``reified_test``
        # is populated for the legacy reifiable test types
        # (unify/dif/FD comparisons); otherwise ``None`` — the general
        # single-eval ITE shape that each strategy lowers in its own
        # dialect.  An ``IfExpr`` whose test is a tabled-predicate call
        # exercises a bespoke ``_naf_tabled`` branch in the legacy
        # general-ITE compiler; defer those to D5f.
        case nodes.IfExpr(test=test, body=then, orelse=else_):
            tabled = (
                isinstance(test, nodes.Call) and _is_tabled_naf(test, db)
            )
            # A unify test whose either side is a star-list converts to a
            # ListPatternUnify op (see the nodes.Unify case below), which the
            # reified-branch lowering can't consume (it reads test_op.l/.r).
            # Such a test is NOT reifiable as a simple eq — fall back to the
            # general single-eval ITE shape. Surfaces with DCG terminal-branch
            # if-then-else, e.g. ``g >> (if_([x], [y], [z]))``.
            star_list_unify = (
                isinstance(test, nodes.Unify)
                and (_is_star_list(test.left) or _is_star_list(test.right))
            )
            kind = (
                None if tabled or star_list_unify
                else (_REIFIED_KIND[type(test)] if _is_reifiable(test) else None)
            )
            return Branch(
                test=_convert(test, db),
                then=_convert(then, db),
                else_=_convert(else_, db),
                reified_test=kind,
                tabled_naf=tabled,
            )

        # ── Meta-predicate calls ─────────────────────────────────────
        # Inner goals are passed through as raw terms (not recursively
        # ``_convert``ed).  The ``_compile_*`` helpers in
        # :mod:`.control_constructs` consume them via the
        # ``_lower_inner`` / ``_lower_inner_trampoline`` wrappers, which
        # perform the conversion and the strategy-specific lowering in
        # one step — keeping raw terms here avoids a redundant
        # convert-at-analysis / rebuild-at-lowering round trip.  A
        # future cleanup may tighten ``MetaCall.args`` to carry
        # :class:`GoalOp` children directly (see
        # ``todo/slice_d_goalop_ir.md``).
        case nodes.Call(func=nodes.LoadName(name="throw"),
                        args=[term_arg], kwargs=[]):
            return MetaCall(kind="throw", args={"term": term_arg})
        case nodes.Call(func=nodes.LoadName(name="halt"),
                        args=[], kwargs=[]):
            return MetaCall(kind="halt", args={"code": None})
        case nodes.Call(func=nodes.LoadName(name="halt"),
                        args=[code_arg], kwargs=[]):
            return MetaCall(kind="halt", args={"code": code_arg})
        case nodes.Call(func=nodes.LoadName(name="once"),
                        args=[inner], kwargs=[]):
            return MetaCall(kind="once", args={"inner": inner})
        case nodes.Call(func=nodes.LoadName(name="call_nth"),
                        args=[inner, n_arg], kwargs=[]):
            return MetaCall(kind="call_nth",
                            args={"inner": inner, "n": n_arg})
        case nodes.Call(func=nodes.LoadName(name="count_all"),
                        args=[inner, count_arg], kwargs=[]):
            return MetaCall(kind="count_all",
                            args={"inner": inner, "count": count_arg})
        case nodes.Call(func=nodes.LoadName(name="setup_call_cleanup"),
                        args=[setup, call_g, cleanup], kwargs=[]):
            return MetaCall(kind="setup_call_cleanup", args={
                "setup": setup, "call": call_g, "cleanup": cleanup,
            })
        case nodes.Call(func=nodes.LoadName(name="call_cleanup"),
                        args=[call_g, cleanup], kwargs=[]):
            return MetaCall(kind="call_cleanup",
                            args={"call": call_g, "cleanup": cleanup})
        case nodes.Call(func=nodes.LoadName(name="freeze"),
                        args=[x_arg, inner], kwargs=[]):
            return MetaCall(kind="freeze",
                            args={"var": x_arg, "inner": inner})
        case nodes.Call(func=nodes.LoadName(name="when"),
                        args=[cond, inner], kwargs=[]):
            return MetaCall(kind="when",
                            args={"cond": cond, "inner": inner})
        case nodes.Call(func=nodes.LoadName(name="findall"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="findall", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="findall"),
                        args=[template, inner, bag, tail], kwargs=[]):
            # findall/4 (Scryer's builtins, the difference-list form):
            # findall/3 whose collected list ends in *tail*, not ``[]``.
            return MetaCall(kind="findall", args={
                "template": template, "inner": inner, "bag": bag,
                "tail": tail,
            })
        case nodes.Call(func=nodes.LoadName(name="bagof"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="bagof", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="setof"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="setof", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="catch"),
                        args=[goal_arg, catcher, recovery], kwargs=[]):
            return MetaCall(kind="catch", args={
                "inner": goal_arg, "catcher": catcher, "recovery": recovery,
            })
        case nodes.Call(func=nodes.LoadName(name="catch_error"),
                        args=[goal_arg, error_var], kwargs=[]):
            return MetaCall(kind="catch_error", args={
                "inner": goal_arg, "error": error_var,
            })
        case nodes.Call(func=nodes.LoadName(name="catch_recover"),
                        args=[goal_arg, error_var, recovery], kwargs=[]):
            return MetaCall(kind="catch_recover", args={
                "inner": goal_arg, "error": error_var, "recovery": recovery,
            })
        case nodes.Call(func=nodes.LoadName(name="forall"),
                        args=[cond, action], kwargs=[]):
            return MetaCall(kind="forall",
                            args={"cond": cond, "action": action})
        case nodes.Call(func=nodes.LoadName(name="eval_"),
                        args=[expr_arg, target_arg], kwargs=[]):
            # eval_(EXPR, RESULT) — eager arithmetic evaluate-and-bind
            # (Prolog is/2).  Successor of the deprecated ':=' operator;
            # same backend (ArithEval).  Evaluates like ISO is/2: a variable
            # operand at runtime, a non-evaluable term raises (ruling R9 A2).
            return ArithEval(target=target_arg, expr=expr_arg)

        # ``Call(LoadName | LoadAttr)`` → ``SubCall``.  Meta-predicate
        # names not captured by the explicit arms above (wrong arity,
        # unexpected kwargs) fall through here and resolve as ordinary
        # user predicate calls — the legacy dispatcher did the same at
        # those arities.  Keyword arguments on user predicates are
        # normalised here (WK-4) using the predicate signature on
        # ``db``; when no signature is registered we defer to legacy
        # rather than guessing argument order.  Lambda hoisting stays
        # in the lowering, so :class:`SubCall.args` carries the terms
        # unchanged.
        case nodes.Call(func=func, args=call_args, kwargs=call_kwargs) \
                if isinstance(func, (nodes.LoadName, nodes.LoadAttr)):
            if isinstance(func, nodes.LoadName):
                fname = func.name
            else:
                fname = _dotted_name_from_loadattr(func)
                if fname is None:
                    _not_yet(goal)
            n_pos = len(call_args)
            arity = n_pos + len(call_kwargs or [])
            ordered_args: list = list(call_args)
            if call_kwargs:
                if db is None:
                    _not_yet(goal)
                sig = db.signature_for(fname, arity)
                if sig is None:
                    _not_yet(goal)
                kw_dict = {
                    kw.name: kw.value for kw in call_kwargs
                    if isinstance(kw, nodes.Keyword)
                }
                for param_name in sig[n_pos:]:
                    if param_name not in kw_dict:
                        _not_yet(goal)
                    ordered_args.append(kw_dict[param_name])
            if db is not None:
                # -meta_predicate (operator ruling 2026-09-25, Scryer): an
                # argument in a ``:``/integer position is qualified with THIS
                # module at the call -- decided here, where the callee the
                # name means in this module is known; done at run time by
                # ``$meta_qualify`` (the value may be a variable bound to an
                # already-qualified goal, which is left alone).
                from clausal.logic.meta_predicate import (  # noqa: PLC0415
                    MetaArg, dotted_module_prefix, is_qualifying_spec,
                    meta_specs_for_call,
                )
                meta_specs = meta_specs_for_call(db, fname, arity)
                if meta_specs:
                    # A DOTTED ``lib.p(...)`` / ``lib.p`` written in a
                    # qualifying position is the qualified goal ``lib:p(...)``
                    # (operator ruling 2026-09-25), as the same dotted call in
                    # goal position resolves in lib -- not a term (ruling (a)
                    # makes that the plain ``p`` cell) that ``$meta_qualify``
                    # would then qualify with THIS module.  Only a LoadAttr
                    # the author wrote: an ``-import_from`` rewrite of a bare
                    # name is a dotted LoadName and keeps caller qualification.
                    _ns = getattr(db, "module_dict", None)

                    def _dotted_goal_module(a):
                        node = a.func if isinstance(a, nodes.Call) else a
                        if not isinstance(node, nodes.LoadAttr):
                            return None
                        dotted = _dotted_name_from_loadattr(node)
                        return (None if dotted is None
                                else dotted_module_prefix(dotted, _ns))

                    # A lambda LITERAL in a GOAL (integer) position is a
                    # closure compiled in THIS module -- its body's names
                    # resolve here, as Scryer qualifies a yall lambda with
                    # its defining module -- so there is nothing to add.  A
                    # ``:`` position is module-sensitive DATA and is always
                    # qualified (the hoisting walk still compiles the lambda
                    # inside the marker).
                    ordered_args = [
                        a if (type(spec) is int and isinstance(a, nodes.Lambda))
                        else a if not is_qualifying_spec(spec)
                        else MetaArg(a, spec, _mod)
                        if (_mod := _dotted_goal_module(a)) is not None
                        else MetaArg(a, spec)
                        for spec, a in zip(meta_specs, ordered_args)]
            return SubCall(fname=fname, arity=arity, args=ordered_args)

        case nodes.Unify(left=l, right=r):
            # Star-list unification (e.g. ``X is [*T, Last]``) routes
            # through ``_compile_star_is`` in the legacy path.  Mirror
            # the legacy preference for putting the star side first:
            # when both sides carry stars the left side wins (legacy
            # shallow / trampoline dispatchers both test ``l`` first).
            if _is_star_list(l):
                return ListPatternUnify(star_side=l, other_side=r)
            if _is_star_list(r):
                return ListPatternUnify(star_side=r, other_side=l)
            return Unify(l=l, r=r)
        case nodes.DoesNotUnify(left=l, right=r):
            return Dif(l=l, r=r)
        case nodes.Evaluate(left=l, right=r):
            return ArithEval(target=l, expr=r)
        case nodes.StructuralEq(left=l, right=r):
            return StructuralEq(l=l, r=r, negate=False)
        case nodes.StructuralNeq(left=l, right=r):
            return StructuralEq(l=l, r=r, negate=True)
        case nodes.in_(left=l, right=r):
            return MemberIn(elem=l, collection=r, negate=False)
        case nodes.NotIn(left=l, right=r):
            return MemberIn(elem=l, collection=r, negate=True)
        case nodes.ArithEq() | nodes.ArithNeq() | nodes.Lt() | nodes.LtE() \
                | nodes.Gt() | nodes.GtE():
            return FDCompare(op=_FD_OP[type(goal)], l=goal.left, r=goal.right)
        case nodes.SetLiteral():
            # A set literal in GOAL position is a CLP(Q) constraint set, the
            # seam twin of clpq's ``{C}`` (operator ruling 2026-09-30): it is
            # the goal ``clpq.rational((elements...))`` and converts through
            # that very arm, so the two spellings produce one GoalOp.  A set
            # in DATA position (a head, an argument) is untouched: only
            # goals reach ``_convert``.
            return _convert_inner(_set_goal_as_clpq_rational(goal), db)
    if isinstance(goal, DictTerm):
        # ``{}`` parses as the empty DICT (Python's reading), and a dict is
        # data: it reached ``_not_yet`` and surfaced the internal
        # NotImplementedError.  (A NON-empty ``{...}`` of comparisons is a
        # set literal -- the CLP(Q) constraint set above.)
        raise DictGoalError(goal)
    _not_yet(goal)


#: The node shapes a goal-position set may hold: the comparisons
#: ``clpq_constraint_block`` posts (a ``CompareChain`` is a chain of them).
_CLPQ_SET_ELEMENTS = (nodes.ArithEq, nodes.ArithNeq, nodes.Lt, nodes.LtE,
                      nodes.Gt, nodes.GtE)


def _is_clpq_constraint(element: Any) -> bool:
    if isinstance(element, _CLPQ_SET_ELEMENTS):
        return True
    return (isinstance(element, nodes.CompareChain)
            and all(isinstance(c, _CLPQ_SET_ELEMENTS)
                    for c in element.comparisons))


def _set_goal_as_clpq_rational(goal: nodes.SetLiteral) -> nodes.Call:
    """``{C1, C2, ...}`` in goal position -> the ``clpq.rational((C1, C2,
    ...))`` call node (one element: ``clpq.rational(C1)``), the exact AST the
    seam's long spelling and the ``.pl`` front end's ``{C}`` lowering
    produce.  Every element must be a constraint; anything else is a
    load-time :class:`SetGoalElementError` naming it."""
    elements = list(goal.elements)
    if not elements:
        raise SetGoalElementError(goal, None)
    for element in elements:
        if not _is_clpq_constraint(element):
            raise SetGoalElementError(goal, element)
    pos = goal.position
    arg = elements[0] if len(elements) == 1 else nodes.TupleLiteral(
        elements=elements, position=pos)
    func = nodes.LoadAttr(
        object=nodes.LoadName(name="clpq", position=pos), attr="rational",
        position=pos)
    return nodes.Call(func=func, args=[arg], kwargs=[], position=pos)


class SetGoalElementError(Exception):
    """A set literal in goal position held something that is not a
    constraint.

    In goal position ``{...}`` is a CLP(Q) constraint set (the seam's twin
    of clpq's ``{C}``), so each element must be a comparison ``==``, ``!=``,
    ``<``, ``<=``, ``>``, ``>=`` or a chain of them.  ``predicate`` is
    filled in by the predicate compiler once the enclosing ``functor/arity``
    is known (like :class:`BareGoalVariableError`).
    """

    def __init__(self, goal: Any, element: Any,
                 predicate: str | None = None) -> None:
        self.goal = goal
        self.element = element
        self.predicate = predicate
        location = f" in predicate {predicate}" if predicate else ""
        culprit = (f"`{element}` in `{goal}`{location} is not one"
                   if element is not None
                   else f"`{goal}`{location} holds no constraint")
        super().__init__(
            f"a set literal in goal position is a CLP(Q) constraint set "
            f"(the twin of clpq's {{C}}): each element must be a comparison "
            f"(==, !=, <, <=, >, >= or a chain of them), but {culprit}. "
            f"A set of VALUES belongs in an argument, not in goal position."
        )


class DictGoalError(Exception):
    """A dict term was used in goal position -- most often ``{}``, which
    Python (and so the seam) reads as the empty DICT, not an empty
    constraint set.  ``predicate`` is filled in by the predicate compiler
    once the enclosing ``functor/arity`` is known (like
    :class:`BareGoalVariableError`)."""

    def __init__(self, goal: Any, predicate: str | None = None) -> None:
        self.goal = goal
        self.predicate = predicate
        location = f" in predicate {predicate}" if predicate else ""
        pos = getattr(goal, "_position", None)
        line = pos[0] if isinstance(pos, tuple) and pos else None
        where = f" (line {line})" if line is not None else ""
        if len(goal) == 0:
            what = "`{}` is an empty dict, not a goal"
        else:
            what = "`{...}` (a dict with keys) is a dict, not a goal"
        super().__init__(
            f"{what}{location}{where}: a dict is data. It belongs in an "
            f"argument; `true` is the goal that always succeeds, and a "
            f"CLP(Q) constraint set needs at least one comparison "
            f"(e.g. {{X >= 0}})."
        )


class BareGoalVariableError(Exception):
    """A bare logic variable was used in goal position.

    A variable on its own is not a callable goal.  This usually means a
    clause accidentally ended with an output variable (common in
    machine-generated rulebases, e.g. ``decide(...) <- (..., RESULT)``);
    an intended meta-call must be written explicitly as ``call/1``
    (``call(RESULT)``).

    ``var`` carries the offending variable.  ``predicate`` is filled in
    by :func:`compile_predicate_trampoline` once the enclosing
    predicate's ``functor/arity`` is known, so the surfaced message can
    locate the clause; it is ``None`` when raised in isolation (e.g.
    a direct :func:`terms_to_goalop` unit call).
    """

    def __init__(self, var: Any, predicate: str | None = None) -> None:
        self.var = var
        self.predicate = predicate
        location = f" in predicate {predicate}" if predicate else ""
        super().__init__(
            f"{var!r} is not a callable goal: a bare variable appears in "
            f"goal position{location}. If a meta-call was intended, wrap "
            f"it as call/1 (e.g. call(R))."
        )


class BareGoalUndefinedError(Exception):
    """The Kleene ``Undefined`` truth value was used in goal position.

    ``Undefined`` is *data* (the third strong-Kleene truth value), not a goal:
    ``True`` compiles to the unit and ``False`` to ``Fail``, but there is no
    third goal outcome.  A bare ``Undefined`` in a clause body is therefore an
    author error — typically ``Undefined`` written where a call/relation was
    intended.

    Note the deliberate divergence from XSB/SWI, whose ``undefined/0`` *is* a
    callable goal denoting a third outcome.  Clausal shares the spelling (the
    lowercase ``undefined`` alias resolves to this very singleton) but not the
    goal semantics: the engine has two goal outcomes, and an unfounded answer is
    reported through :meth:`TableEntry.truth_value` rather than by a goal that
    neither succeeds nor fails.  The message says so, because an author arriving
    from XSB will have written the goal on purpose.

    ``predicate`` is filled in by :func:`compile_predicate_trampoline` once the
    enclosing ``functor/arity`` is known (like :class:`BareGoalVariableError`),
    so the surfaced message can locate the clause; it is ``None`` when raised in
    isolation (e.g. a direct :func:`terms_to_goalop` unit call).
    """

    def __init__(self, predicate: str | None = None) -> None:
        self.predicate = predicate
        location = f" in predicate {predicate}" if predicate else ""
        super().__init__(
            f"Undefined is not a callable goal: the Kleene truth value Undefined "
            f"appears in goal position{location}. Undefined is data (a truth "
            f"value), not a goal — it has no success/failure outcome. If a "
            f"comparison was intended, write it explicitly (e.g. `T is Undefined`). "
            f"(Unlike XSB/SWI, Clausal has no `undefined/0` goal: a goal either "
            f"succeeds or fails, and an unfounded tabled answer carries its "
            f"Undefined truth value on the answer, not on the call.)"
        )


def _not_yet(goal: Any) -> NoReturn:
    """Signal that the D2 subset does not yet cover this goal shape.

    The D4 parallel-implementation harness catches this and falls back
    to the legacy compilation path; Slice D5 flips each of these to a
    real conversion.
    """
    raise NotImplementedError(
        f"terms_to_goalop: goal shape not yet supported "
        f"({type(goal).__name__}): {goal!r}"
    )


__all__ = ["terms_to_goalop", "BareGoalVariableError", "BareGoalUndefinedError",
           "SetGoalElementError", "DictGoalError"]
