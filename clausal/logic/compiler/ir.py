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
    "naf_tabled",
]
"""Closed enumeration of meta-predicate kinds.  Each kind has a fixed
``args`` schema documented on ``MetaCall`` — see ``terms_to_goalop``
(D5) for the canonical lowering from ``Call(func=LoadName(...), ...)``."""


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class GoalOp:
    """Base class for compiled goal operations.

    Subclasses are ``@dataclass`` records.  Passes traverse them with
    ``walk_goal_ops`` or pattern-match on their types.

    ``position`` (Slice G) is the source-position tuple
    ``(start_line, start_col, end_line, end_col)`` of the originating
    ``.clausal`` body term.  ``terms_to_goalop`` stamps it from the body
    term's own ``position`` attribute; lowering opens a position scope
    on this value before emitting AST so generated nodes carry truthful
    ``lineno`` / ``col_offset``.

    Declared keyword-only so subclasses may continue to specify their
    own positional fields without colliding with the inherited default.
    """
    position: "tuple[int, int, int, int] | None" = dataclasses.field(
        default=None, kw_only=True, compare=False, repr=False,
    )


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

    ``tabled_naf`` — set when ``reified_test is None`` and ``test`` is
    a :class:`SubCall` to a tabled predicate.  The general-ITE lowering
    then replaces the ``if not _found`` else-guard with a
    ``_naf_tabled(...)`` call, matching legacy
    ``_compile_general_ite_{shallow,trampoline}`` under
    ``use_tabled_naf``.  WFS-sound: required so cycles through negation
    delay-and-resume correctly.  Must be ``False`` when
    ``reified_test is not None`` (reifiable tests never target tabled
    predicates in practice; legacy does not emit that combination).
    """
    test: GoalOp
    then: GoalOp
    else_: GoalOp
    reified_test: Union[ReifiedKind, None] = None
    tabled_naf: bool = False


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

    - ``direct_bucket_ref`` — name of a pre-bound single-position
      bucket function in ``base_globals`` that dispatch may short-
      circuit to when a statically-known argument matches an indexed
      position (call-site specialisation).
    - ``direct_joint_bucket_ref`` — same idea for **joint-position**
      (two-arg) specialisation: global name of the pre-bound joint
      bucket function when the call site has two statically-known
      args matching an ``(pos_i, pos_j)`` joint index of the callee.
      Takes precedence over ``direct_bucket_ref`` (joint entries are
      more selective), matching the legacy
      ``_dispatch_call_trampoline`` joint-first preference.
    - ``tail_recursive`` — ``True`` when this call is the tail of a
      TRO-eligible clause; the lowering rewrites it as an argument
      reassignment + loop continue rather than a real sub-call.
    - ``tro_check_indices`` — companion to ``tail_recursive``: arg
      positions needing a runtime ``is_var()`` ground-check before
      the TRO short-circuit fires.  Empty ``frozenset`` when no
      check is required (or when ``tail_recursive`` is ``False``).
    - ``destructive_reuse`` — ``True`` when the source container of
      this call is provably dead at the call site; the lowering picks
      the ``_dr_*`` in-place variant (trampoline-only).
    - ``tail_position`` — ``True`` when this call is in tail position
      of the clause body (continuation-level TCO).  Trampoline
      lowering emits the child's ``proceed`` slot as the caller's own
      ``_proceed`` (solutions bypass our frame) while keeping ``fail``
      / ``catcher`` routed through us (completion and exceptions still
      wake our frame).  Mutually exclusive with ``tail_recursive``
      (TRO wins and is a richer special case — arg reassignment + loop
      continue).  See ``implementation_plans/CONTINUATION_TCO_PLAN.md``.
    """
    fname: str
    arity: int
    args: list[Term]
    direct_bucket_ref: Union[str, None] = None
    direct_joint_bucket_ref: Union[str, None] = None
    tail_recursive: bool = False
    tro_check_indices: frozenset = dataclasses.field(default_factory=frozenset)
    destructive_reuse: bool = False
    tail_position: bool = False


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
    - ``naf_tabled``:           ``{"call": Term}`` — WFS-sound negation
      of a call to a tabled predicate.  ``call`` is the raw
      :class:`~clausal.terms.Call` node; lowering forwards it to
      ``_compile_tabled_naf_simple`` which handles kwargs signature
      normalisation itself.

    Backends pattern-match on ``kind`` to lower.  The open ``dict``
    shape lets D5 expand coverage one meta-kind at a time without
    rewriting this class.

    **Transitional shape (still in place post-D7c).**  Goal-position
    args (``"inner" / "call" / "setup" / "cleanup" / "cond" / "action"``
    /etc.) carry **raw Term**, not :class:`GoalOp`.  The
    ``_lower_meta_call`` arms forward them to the ``_compile_*``
    helpers in :mod:`.control_constructs`, which call the
    ``_lower_inner`` / ``_lower_inner_trampoline`` wrappers to build
    a singleton IR and lower.  Promoting these slots to :class:`GoalOp`
    would eliminate that intermediate conversion; it's a cosmetic
    tightening, not correctness-blocking.

    For walks that need to *see* the nested goals (E's analyses,
    in particular), use :func:`walk_goal_ops_deep` rather than
    :func:`walk_goal_ops` — the deep walker consults
    :data:`META_GOAL_POSITIONS` and lazily converts the raw-term
    inners through ``terms_to_goalop._convert`` so the visitor
    sees a proper GoalOp tree.
    """
    kind: MetaKind
    args: dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Low-level ops
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Fail(GoalOp):
    """The constant-failure goal — succeeds for nobody, drops the
    continuation.  Lowering returns ``[]``; in a :class:`Sequence` fold
    that truncates everything to its left.
    """


@dataclasses.dataclass
class PyThunkOp(GoalOp):
    """A ``PyThunk`` as a body goal — evaluate the embedded callable
    for side effects, then continue.  The lowering emits a single
    ``ast.Expr`` wrapping ``term_to_ast_expr(thunk)`` followed by the
    continuation.

    ``thunk`` carries the raw :class:`~clausal.terms.PyThunk` term
    unchanged — the lowering reuses ``term_to_ast_expr`` so PyThunk
    globals registration (handled at module-compile time by
    ``globals_env``) is not duplicated here.
    """
    thunk: Term


@dataclasses.dataclass
class ListPatternUnify(GoalOp):
    """Body-side star-list unification (``X is [A, *T, B]`` and friends).

    ``star_side`` is the Python list containing one or more
    :class:`~clausal.pythonic_ast.nodes.StarUnpack` entries; the lowering
    routes to ``_compile_single_star_is`` or ``_compile_multi_star_is``
    depending on how many stars the list contains.  ``other_side`` is
    the term being unified with the pattern (always a single term).

    D1 originally spelled this op out with parsed before/star/after
    fields plus a ``phase`` literal for head-match reuse; Slice D5g
    simplified to a raw-terms wrapper because (a) the parsed shape
    leaked single-star implementation details into the IR, and (b)
    head-match is not part of the body IR's scope.  A separate IR op
    can land if head-match compilation is ever absorbed into the body
    pipeline.
    """
    star_side: list[Term]
    other_side: Term


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

    **Meta-call inner goals.**  ``MetaCall.args`` carries raw terms
    today (see :class:`MetaCall` for the transitional-shape note);
    this walker only descends into args entries that are *already*
    :class:`GoalOp` instances or lists thereof.  Goal-position raw
    terms (``once``'s ``"inner"`` etc.) are skipped.  Use
    :func:`walk_goal_ops_deep` for analyses that need to see them.
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


# ─────────────────────────────────────────────────────────────────────────────
# Meta-call inner-goal manifest (Slice E precursor)
# ─────────────────────────────────────────────────────────────────────────────


# For each ``MetaKind``, the tuple of arg-dict keys whose values
# represent *body goals* (callable / re-dispatched as goals at
# lowering time).  Other arg positions carry term operands
# (templates, bags, counters, error vars).
#
# :func:`walk_goal_ops_deep` consults this manifest to descend into
# meta-call inners, lazily converting the raw term at each goal
# position through ``terms_to_goalop._convert`` so the visitor sees
# a proper GoalOp tree.  E's analyses use the deep walker so they
# can reason about nested ``SubCall`` / ``Unify`` / etc.
META_GOAL_POSITIONS: dict[str, tuple[str, ...]] = {
    "once":                 ("inner",),
    "call_nth":             ("inner",),
    "count_all":            ("inner",),
    "setup_call_cleanup":   ("setup", "call", "cleanup"),
    "call_cleanup":         ("call", "cleanup"),
    "freeze":               ("inner",),
    "when":                 ("inner",),
    "findall":              ("inner",),
    "bagof":                ("inner",),
    "setof":                ("inner",),
    "catch":                ("inner", "recovery"),
    "catch_error":          ("inner",),
    "catch_recover":        ("inner", "recovery"),
    "forall":               ("cond", "action"),
    # ``naf_tabled`` carries the tabled call as a raw ``Call`` term,
    # not a goal in the body sense — lowering forwards it directly
    # to ``_compile_tabled_naf_simple`` rather than re-dispatching.
    # The deep walker treats it the same as the wrapping ``MetaCall``
    # for analysis purposes (the call would be picked up at the
    # outer SubCall level once D7c arrives — see
    # ``terms_to_goalop`` for the open question).
}


def walk_goal_ops_deep(
    ir: GoalOp,
    visit: Callable[[GoalOp], None],
    db: Any = None,
) -> None:
    """Like :func:`walk_goal_ops` but descends into meta-call inners.

    For each :class:`MetaCall` op visited, the goal-position args
    listed in :data:`META_GOAL_POSITIONS` are pulled out of the
    args dict and lazily converted to GoalOp via
    ``terms_to_goalop._convert``, then walked recursively.

    *db* is forwarded to ``_convert`` for kwarg-bearing
    :class:`SubCall` normalisation; pass the live database when
    calling on bodies that may contain such calls.  Without *db*,
    ``_convert`` falls back via ``NotImplementedError`` on
    kwarg-bearing inners and the deep walker silently skips them
    (matching the D4 fallback contract).

    Use this walker for analyses that need a complete view of all
    nested goals — E's optimisation passes, for instance.  Most
    existing analyses iterate ``ir.ops`` directly because they only
    care about top-level conjunction members and the legacy
    detectors had the same limitation; those should stay on
    :func:`walk_goal_ops` until they actually need the recursion.
    """
    visit(ir)
    match ir:
        case Sequence(ops=ops) | Alternate(ops=ops):
            for child in ops:
                walk_goal_ops_deep(child, visit, db=db)
        case Negate(op=child):
            walk_goal_ops_deep(child, visit, db=db)
        case Branch(test=t, then=th, else_=e):
            walk_goal_ops_deep(t, visit, db=db)
            walk_goal_ops_deep(th, visit, db=db)
            walk_goal_ops_deep(e, visit, db=db)
        case MetaCall(kind=kind, args=margs):
            from .terms_to_goalop import _convert
            for key in META_GOAL_POSITIONS.get(kind, ()):
                if key not in margs:
                    continue
                inner = margs[key]
                if isinstance(inner, GoalOp):
                    # Already a GoalOp (post-E schema or a
                    # caller-provided GoalOp).  Walk directly.
                    walk_goal_ops_deep(inner, visit, db=db)
                    continue
                try:
                    inner_op = _convert(inner, db)
                except NotImplementedError:
                    continue
                walk_goal_ops_deep(inner_op, visit, db=db)
        case _:
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
    "Fail", "PyThunkOp", "ListPatternUnify",
    # Traversal
    "walk_goal_ops", "walk_goal_ops_deep",
    # Meta-call manifest (Slice E precursor)
    "META_GOAL_POSITIONS",
]
