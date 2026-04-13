"""``GoalOp`` — the body intermediate representation.

Target-agnostic and strategy-agnostic.  Goal compilation pattern-matches
directly on ``clausal.pythonic_ast.nodes`` / ``clausal.terms`` types
today; Slice D of the compiler refactor replaces that with a two-phase
pipeline:

    clause.body ─ terms_to_goalop ─► GoalOp tree ─ lower_python_{shallow,trampoline} ─► ast.stmt list

This module (Slice D1) defines the IR — pure type definitions plus a
``walk_goal_ops`` traversal helper.  Nothing consumes these types yet;
``terms_to_goalop`` (D2), the lowering passes (D3), and the
parallel-implementation harness (D4) land as follow-up sub-slices.  See
``implementation_plans/COMPILER_MIGRATION_PLAN.md`` §6 and
``implementation_plans/COMPILER_TARGET_ARCHITECTURE.md`` §4 (``GoalOp``
— the body IR) for the design commitments.

Design choices baked into this file:

- **Tagged union via base class + subclass dataclasses.**  Each op is a
  frozen-in-spirit record; passes pattern-match with ``match``/``case``.
- **Operands are logic-level terms** (``Var``, ``Compound``,
  ``DictTerm``, ``TupleLiteral``, scalars, …), not AST expressions.
  Lowering from term to AST is a backend concern.
- **Arithmetic uses ``clausal.terms`` arith nodes directly** (``Add``,
  ``Sub``, ``Mult``, …) as the ``ArithExpr`` operand type.  No separate
  arith-IR mini-tree — the existing term classes already represent
  arithmetic as a tree.
- **Optimisation hints live on ``SubCall``** (``direct_bucket_ref``,
  ``tail_recursive``, ``destructive_reuse``).  Passes write them; the
  lowering reads them.  Keeping hints on the IR rather than on a
  side-table means a single ``walk_goal_ops`` sees everything.
- **``MetaCall``'s ``args`` is an open dict.**  The closed set of
  ``kind`` values makes each variant's shape static; an open dict
  defers field enumeration to D5 (meta-predicate coverage expansion)
  rather than committing now.
- **No ``needs_mark``, ``fresh_name_hint``, etc. on simple ops.**
  Those concerns are backend-specific (fresh names are drawn from
  ``ctx.fresh`` at lowering time).  The IR carries only what the
  analysis and lowering passes need to agree on.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal, Union

# Terms live in clausal.terms / clausal.pythonic_ast.nodes.  The IR
# references these concretely so passes can pattern-match on them, but
# does not reshape them — goal-position / expression-position
# polymorphism is resolved during ``terms_to_goalop`` (D2), not here.
Term = Any
"""Alias for logic-level term operands — ``Var | Compound | int | str |
DictTerm | SetTerm | TupleLiteral | StarUnpack | ...``.  Deliberately
loose: the IR does not restrict which concrete term shapes may appear
in operand position — that is a per-op contract documented on each
dataclass."""

ArithExpr = Any
"""Alias for arithmetic-expression operands — a tree of
``clausal.terms.{Add,Sub,Mult,Div,FloorDiv,Mod,Pow,Negate}`` with
``Var`` / numeric leaves.  Evaluation semantics (native math vs
unification) are the backend's concern; the IR only records that this
subtree is evaluated, not unified."""

FDOp = Literal["eq", "ne", "lt", "le", "gt", "ge"]
"""Closed enumeration of CLP(FD) comparison operators."""

ReifiedKind = Literal[
    "unify", "dif", "fd_eq", "fd_ne", "fd_lt", "fd_le", "fd_gt", "fd_ge",
]
"""Closed enumeration of reifiable ITE test shapes.  When
``Branch.reified_test`` is one of these, the backend may emit the
three-way reified form (``_reify_eq`` / ``_reify_fd``); ``None`` means
general single-evaluation ITE."""

MetaKind = Literal[
    "once", "call_nth", "count_all", "setup_call_cleanup", "call_cleanup",
    "freeze", "when", "findall", "bagof", "setof",
    "throw", "catch", "catch_error", "catch_recover",
    "forall", "halt",
]
"""Closed enumeration of meta-predicate kinds.  Each kind has a fixed
``args`` schema documented on ``MetaCall`` — see ``terms_to_goalop``
(D5) for the canonical lowering from ``Call(func=LoadName(...), ...)``."""


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────


class GoalOp:
    """Base class for compiled goal operations.

    Subclasses are ``@dataclass`` records.  Passes traverse them with
    ``walk_goal_ops`` or pattern-match on their types.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Binding / constraint ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Unify(GoalOp):
    """Unify two terms, committing bindings on the shared trail.

    The lowering must bracket the continuation with trail mark/undo so
    failure of a subsequent goal cleanly reverts the unification.
    """
    l: Term
    r: Term


@dataclasses.dataclass
class Dif(GoalOp):
    """Post a dis-equality constraint (``dif/2``) on two terms.

    Unlike :class:`Unify`, ``Dif`` does not bind — it registers a
    constraint that may fail the current goal when the arguments become
    unifiable later.  No mark/undo is required around the continuation
    because no trail entries are written by ``Dif`` itself.
    """
    l: Term
    r: Term


@dataclasses.dataclass
class StructuralEq(GoalOp):
    """Prolog ``==`` / ``\\==`` — succeed iff arguments are structurally
    identical under current bindings.  No unification, no constraints.
    """
    l: Term
    r: Term
    negate: bool = False  # False → ==, True → \\==


@dataclasses.dataclass
class ArithEval(GoalOp):
    """Evaluate an arithmetic expression, unify the result with target.

    ``target`` is typically a fresh ``Var`` but may be a bound term
    (``X is 1+2`` with ``X`` already bound to ``3`` succeeds silently).
    """
    target: Term
    expr: ArithExpr


@dataclasses.dataclass
class FDCompare(GoalOp):
    """CLP(FD) comparison constraint (``#=``, ``#\\=``, ``#<``, …)."""
    op: FDOp
    l: Term
    r: Term


# ─────────────────────────────────────────────────────────────────────────────
# Control flow ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Sequence(GoalOp):
    """Conjunction — run each op in order, succeed iff all succeed.

    Empty ``ops`` is the unit (``true``).  Canonical form: ``And``,
    list-body conjunction, and ``TupleLiteral`` in goal position all
    lower to a single flat ``Sequence``.
    """
    ops: list[GoalOp]


@dataclasses.dataclass
class Alternate(GoalOp):
    """Disjunction (``Or``) — try each op in order; solutions from all
    branches are enumerated.

    Two-operand ``Or(a, b)`` lowers to ``Alternate(ops=[a, b])``;
    n-way disjunctions may flatten during ``terms_to_goalop``.
    """
    ops: list[GoalOp]


@dataclasses.dataclass
class Negate(GoalOp):
    """Negation as failure — succeed iff ``op`` has no solutions.

    Bindings made inside ``op`` do not escape (the lowering must wrap
    with mark/undo or a sub-generator, strategy-dependent).
    """
    op: GoalOp


@dataclasses.dataclass
class Branch(GoalOp):
    """If-then-else with reifiability hint.

    When ``reified_test`` is a :data:`ReifiedKind` value, the backend
    may emit the three-way reified form (``_reify_eq`` / ``_reify_fd``):

    - returned ``True``  → run ``then``
    - returned ``False`` → run ``else_``
    - returned ``None``  → explore both with the matching constraint.

    ``reified_test is None`` means general single-evaluation ITE
    (sub-generator for the test; ``_found`` flag gates ``else_``).
    """
    test: GoalOp
    then: GoalOp
    else_: GoalOp
    reified_test: Union[ReifiedKind, None] = None


# ─────────────────────────────────────────────────────────────────────────────
# Membership ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class MemberIn(GoalOp):
    """``elem in collection`` — backtracks over collection elements.

    When ``negate`` is true, encodes ``not_in`` — succeed iff ``elem``
    does not unify with any element of ``collection``.
    """
    elem: Term
    collection: Term
    negate: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Call ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class SubCall(GoalOp):
    """Call a named sub-predicate.

    ``fname`` is resolved at load time (phase 1); ``base_globals``
    carries the matching callable.  The IR does not reference Python
    callables directly — that keeps the IR backend-agnostic.

    Optimisation hints (written by analysis passes, consumed by
    lowering):

    - ``direct_bucket_ref`` — name of a pre-bound bucket function in
      ``base_globals`` that dispatch may short-circuit to when one or
      more arguments are statically known (call-site specialisation).
    - ``tail_recursive`` — ``True`` when this call is the tail of a
      TRO-eligible clause; the lowering rewrites it as an argument
      reassignment + loop continue rather than a real sub-call.
    - ``destructive_reuse`` — ``True`` when the source container of
      this call is provably dead at the call site; the lowering picks
      the ``_dr_*`` in-place variant (trampoline-only).
    """
    fname: str
    arity: int
    args: list[Term]
    direct_bucket_ref: Union[str, None] = None
    tail_recursive: bool = False
    destructive_reuse: bool = False


@dataclasses.dataclass
class MetaCall(GoalOp):
    """Meta-predicate call.

    ``kind`` is a closed enumeration; each value fixes the shape of
    ``args``:

    - ``once``:                 ``{"inner": GoalOp}``
    - ``call_nth``:             ``{"inner": GoalOp, "n": Term}``
    - ``count_all``:            ``{"inner": GoalOp, "count": Term}``
    - ``setup_call_cleanup``:   ``{"setup": GoalOp, "call": GoalOp, "cleanup": GoalOp}``
    - ``call_cleanup``:         ``{"call": GoalOp, "cleanup": GoalOp}``
    - ``freeze``:               ``{"var": Term, "inner": GoalOp}``
    - ``when``:                 ``{"cond": Term, "inner": GoalOp}``
    - ``findall|bagof|setof``:  ``{"template": Term, "inner": GoalOp, "bag": Term}``
    - ``throw``:                ``{"term": Term}``
    - ``catch``:                ``{"inner": GoalOp, "catcher": Term, "recovery": GoalOp}``
    - ``catch_error``:          ``{"inner": GoalOp, "error": Term}``
    - ``catch_recover``:        ``{"inner": GoalOp, "error": Term, "recovery": GoalOp}``
    - ``forall``:               ``{"cond": GoalOp, "action": GoalOp}``
    - ``halt``:                 ``{"code": Term | None}``

    Backends pattern-match on ``kind`` to lower.  The open ``dict``
    shape lets D5 expand coverage one meta-kind at a time without
    rewriting this class.
    """
    kind: MetaKind
    args: dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Low-level ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class ListPatternUnify(GoalOp):
    """Runtime bidirectional list-pattern unification guard.

    Backends emit a call to their runtime's equivalent of
    ``_head_list_unify_input`` / ``_head_list_unify_output`` — see
    ``compiler/README.md`` §7 for the runtime/compile-time boundary.

    ``phase`` distinguishes head-unification (``"input"`` — target is
    derefed, pattern binds on match) from body-side emission
    (``"output"`` — pattern is constructed, target unified with the
    built list).
    """
    target: Term
    before_vars: list[Term]
    star_var: Union[Term, None]
    after_vars: list[Term]
    phase: Literal["input", "output"]


# ─────────────────────────────────────────────────────────────────────────────
# Traversal
# ─────────────────────────────────────────────────────────────────────────────


def walk_goal_ops(ir: GoalOp, visit: Callable[[GoalOp], None]) -> None:
    """Pre-order traversal of a ``GoalOp`` tree.

    Calls ``visit(node)`` on every :class:`GoalOp` in *ir*, including
    *ir* itself, descending into structural children (``Sequence.ops``,
    ``Alternate.ops``, ``Branch.{test,then,else_}``, ``Negate.op``, and
    :class:`MetaCall.args` entries whose values are themselves
    ``GoalOp`` instances).

    Traversal is pre-order and left-to-right.  Operand ``Term`` fields
    (``l``, ``r``, ``target``, ``elem``, ``collection``, ``fname``,
    argument lists, …) are **not** descended — this is a GoalOp walk,
    not a term walk.  Callers that need to see the terms as well can
    pattern-match inside their ``visit`` callback.

    The callback is read-only by convention (walkers do not replace
    nodes); rewrite passes use a dedicated ``map_goal_ops`` helper
    that will land with D6 when optimisation passes need it.
    """
    visit(ir)
    match ir:
        case Sequence(ops=ops) | Alternate(ops=ops):
            for child in ops:
                walk_goal_ops(child, visit)
        case Negate(op=child):
            walk_goal_ops(child, visit)
        case Branch(test=t, then=th, else_=e):
            walk_goal_ops(t, visit)
            walk_goal_ops(th, visit)
            walk_goal_ops(e, visit)
        case MetaCall(args=args):
            for v in args.values():
                if isinstance(v, GoalOp):
                    walk_goal_ops(v, visit)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, GoalOp):
                            walk_goal_ops(item, visit)
        case _:
            # Leaf ops (Unify, Dif, StructuralEq, ArithEval, FDCompare,
            # MemberIn, SubCall, ListPatternUnify) have no GoalOp
            # children to descend into.
            pass


__all__ = [
    # Operand aliases
    "Term", "ArithExpr", "FDOp", "ReifiedKind", "MetaKind",
    # Base
    "GoalOp",
    # Binding / constraint
    "Unify", "Dif", "StructuralEq", "ArithEval", "FDCompare",
    # Control flow
    "Sequence", "Alternate", "Negate", "Branch",
    # Membership
    "MemberIn",
    # Call
    "SubCall", "MetaCall",
    # Low-level
    "ListPatternUnify",
    # Traversal
    "walk_goal_ops",
]
