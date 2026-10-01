"""Reified if-then-else helpers shared across shallow and trampoline.

Slice D7c-β3 reduced this module to two primitives that the IR lowering
pipeline (``_lower_goalop_shared._lower_reified_branch``) consults:

- :func:`_is_reifiable` — the reified comparisons, which
  :mod:`.terms_to_goalop` lowers to a three-way
  :class:`~clausal.logic.compiler.ir.Branch`.
- :func:`_three_way_reif_branch` — the shared three-way-branch AST
  assembly, used by ``_lower_reified_branch`` for both strategies.

Since the 2026-10-01 ruling (if_/3 requires a reifiable condition) it also
holds :func:`if_expansion`, the term an ``if_`` node compiles as -- the
general (soft-cut) ITE form it used to fall back to is gone.

Pre-β3 this module also carried ``_compile_reified_ite*`` and
``_compile_general_ite*`` helpers driven by the retired
``_dispatch_goal[_trampoline]`` dispatchers; they moved to
``_lower_goalop_shared`` / ``lower_python_{shallow,trampoline}`` as
pure IR ops during slice D5 and retired alongside the dispatchers.
"""

from __future__ import annotations

import ast

from clausal.terms import (
    Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
)

from ._ast_helpers import _name, _assign


_REIFIABLE_TYPES = (Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE)


def _is_reifiable(test) -> bool:
    """Return True if *test* can be compiled as a reified three-way branch."""
    return isinstance(test, _REIFIABLE_TYPES)


def _three_way_reif_branch(
    reif_var: str,
    reif_call: ast.expr,
    true_stmts: list[ast.stmt],
    false_stmts: list[ast.stmt],
    undetermined: list[ast.stmt],
) -> list[ast.stmt]:
    """Assemble the three-way branch."""
    reif_assign = _assign(reif_var, reif_call)
    branch = ast.If(
        test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(True)]),
        body=true_stmts or [ast.Pass()],
        orelse=[
            ast.If(
                test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(False)]),
                body=false_stmts or [ast.Pass()],
                orelse=undetermined,
            ),
        ],
    )
    return [reif_assign, branch]




# ── if_/3's reifiable-condition expansion (operator ruling 2026-10-01) ──────

class NonReifiable:
    """The expansion of an ``if_`` whose condition is not reifiable: the
    compiler refuses it (``terms_to_goalop.NonReifiableConditionError``)."""

    __slots__ = ("test", "reason")

    def __init__(self, test, reason=None):
        self.test = test
        self.reason = reason


def _is_star_list_term(t) -> bool:
    from clausal.logic.compiler.terms_to_ast import _is_star_list  # noqa: PLC0415
    return _is_star_list(t)


def if_expansion(ifexpr):
    """The TERM ``if_(Cond, Then, Else)`` (an ``IfExpr`` node) stands for,
    with library(reif)'s meaning -- computed once per node and cached on it,
    so the body-variable pre-scan (``_vars._collect_vars``) and the goal
    conversion (``terms_to_goalop``) see the SAME truth variable:

    * a reified comparison (:func:`_is_reifiable`) -> *ifexpr* itself, the
      three-way reified branch;
    * ``(A, B)`` / ``A and B`` -> ``if_(A, if_(B, Then, Else), Else)``;
      ``A or B`` -> ``if_(A, Then, if_(B, Then, Else))`` (reif's (',')/3 and
      (;)/3, unfolded as the native .pl front end does);
    * a closure -- a goal ``p(Args...)``, an atom ``p``, a variable, or a
      unification with a partial (star) list (reif's =/3) ->
      ``(p(Args..., T), must_be(boolean, T), if_(T is True, Then, Else))``,
      reif's own body;
    * anything else -> :class:`NonReifiable`.

    Whether a closure's ``p/N+1`` exists is the compiler's question (it
    needs the module), not this one's."""
    key = (ifexpr.test, ifexpr.body, ifexpr.orelse)
    cached = ifexpr.__dict__.get("_reif_expansion")
    if cached is not None and all(a is b for a, b in zip(cached[0], key)):
        return cached[1]
    exp = _expand_if(ifexpr)
    ifexpr.__dict__["_reif_expansion"] = (key, exp)
    return exp


def _expand_if(ifexpr):
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    from clausal.logic.variables import Var, is_var  # noqa: PLC0415
    test, then, else_ = ifexpr.test, ifexpr.body, ifexpr.orelse
    pos = getattr(ifexpr, "position", None)

    def _at(n):
        if pos is not None and getattr(n, "position", None) is None:
            n.position = pos
        return n

    def closure(func, args):
        truth = Var()
        return _at(nodes.TupleLiteral(elements=[
            _at(nodes.Call(func=func, args=list(args) + [truth], kwargs=[])),
            _at(nodes.Call(func=nodes.LoadName(name="must_be"),
                           args=["boolean", truth], kwargs=[])),
            _at(nodes.IfExpr(test=nodes.Unify(left=truth, right=True),
                             body=then, orelse=else_)),
        ]))

    if is_var(test):
        return closure(nodes.LoadName(name="call"), [test])
    test = nodes.literal_value(test)
    if _is_reifiable(test):
        if isinstance(test, Unify) and (_is_star_list_term(test.left)
                                        or _is_star_list_term(test.right)):
            # A star-list unification converts to a ListPatternUnify op,
            # which the reified lowering cannot consume; reif's =/3 answers
            # the same three ways (reify_eq reads the partial list).
            return closure(nodes.LoadName(name="="), [test.left, test.right])
        return ifexpr
    conj = None
    if isinstance(test, nodes.TupleLiteral):
        els = list(test.elements)
        if len(els) == 1:
            return _at(nodes.IfExpr(test=els[0], body=then, orelse=else_))
        if len(els) >= 2:
            conj = (els[0], els[1] if len(els) == 2
                    else nodes.TupleLiteral(elements=els[1:]))
    elif isinstance(test, nodes.And):
        conj = (test.left, test.right)
    if conj is not None:
        a, b = conj
        return _at(nodes.IfExpr(
            test=a, body=_at(nodes.IfExpr(test=b, body=then, orelse=else_)),
            orelse=else_))
    if isinstance(test, nodes.Or):
        return _at(nodes.IfExpr(
            test=test.left, body=then,
            orelse=_at(nodes.IfExpr(test=test.right, body=then,
                                    orelse=else_))))
    if isinstance(test, nodes.Call) and not test.kwargs and isinstance(
            test.func, (nodes.LoadName, nodes.LoadAttr)):
        return closure(test.func, test.args)
    if isinstance(test, nodes.LoadName):
        return closure(test, [])
    if type(test) is str:
        return closure(nodes.LoadName(name=test), [])
    return NonReifiable(test)
