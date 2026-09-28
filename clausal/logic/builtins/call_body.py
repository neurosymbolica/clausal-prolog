"""``call/1`` of a BODY term: conjunction, disjunction, negation, if-then-else
and the builtin comparison goals, built as a runtime term.

ISO 13211-1 §7.6.2 ("converting a term to a body"): ``call(G)`` runs *G* as
though it had been written as a clause body -- a variable ``V`` in a goal
position becomes ``call(V)``, and ``','``/``;``/``->`` are control constructs.
The step-1 target of the ISO ``clause/2`` plan (2026-09-25) is that the Body
``clause/2`` hands back is callable, whatever its shape.

The Clausal spellings are the ones the SAME TEXT produces in term position
(the ISO cells ``(",", A, B)`` etc., which the surface never builds, run too
-- see ISO CELLS below):

====================================  ===================================
written                               term position (what ``G`` holds)
====================================  ===================================
``(A, B)``                            plain tuple ``(A', B')``, slot 0 not a str
``A and B``                           ``nodes.And``
``A or B``                            ``nodes.Or``
``not A``                             ``nodes.Not``
``if_(C, T, E)``                      ``nodes.IfExpr``
``X > Y`` ``X == Y`` ``X is Y`` ...   the comparison node (``Gt``, ``ArithEq``,
                                      ``Unify``, ``DoesNotUnify``, ``in_``, ...)
``0 < X < 9``                         ``nodes.CompareChain``
``true`` / ``fail``                   ``True`` / the atom ``'fail'``
``p(X)``                              the cell ``("p", X)``
====================================  ===================================

MECHANISM.  No second interpreter: the term is converted to the goal NODE
tree the clause-body compiler already lowers, and compiled through the query
compiler (``solve._compile_as_query``) against the calling module, whose cache
it then shares.  Two choices keep that faithful and cheap:

- Every PREDICATE-CALL leaf becomes ``call(P)`` with ``P`` bound, at run time,
  to the leaf.  So ``call((A, B))`` is exactly ``call(A), call(B)``: name
  resolution, module qualification, predicate handles, lambdas and the
  "unknown name fails" contract are ``call/1``'s own, never a second copy.
  The one exception is a leaf under ``not``/the test of ``if_`` that names a
  TABLED predicate: it is emitted as the direct call, because that is what
  makes the compiler pick WFS-sound tabled negation, as it does for the same
  text in a clause.
- Every Var and every atomic leaf in an ARGUMENT position is replaced by a
  fresh parameter Var bound to it just before the compiled body runs, so the
  compiled artifact depends only on the goal's STRUCTURE: one compile per
  shape, not per value.

ISO CELLS (operator ruling 2026-09-25).  ``(",", A, B)``, ``(";", A, B)``
and ``("\\+", G)`` -- what a runtime-built ISO term or a .pl import holds --
run through the same converter.  ``->`` and ``*->`` are refused
(``iso_control_cell_dispatch``): Clausal is cut-free with no committed choice.

ERRORS (checked against ISO first, then Scryer, 2026-09-25).  A
non-callable top-level goal (number, tuple data, None) is
``type_error(callable, G)``; a non-empty list or string is the callable
compound '.'/2, so it names a missing procedure --
``existence_error(procedure, '.'/2)`` (ISO; Scryer disagrees with itself:
literal ``call([a])`` agrees, run-time ``G = [a], call(G)`` gives
type_error); call/N's extras on a
construct name no procedure: ``call((A, B), X)`` is
``existence_error(procedure, ','/3)``.  An unbound goal is
``instantiation_error``.  A number in a goal position reached through the
transparent constructs (conjunction, ``or``, ``if_``) is
``type_error(callable, Whole)`` naming the WHOLE term, before anything runs --
Scryer's ``call((fail, 1))``.  ``not G`` is a predicate in ISO, so its operand
is checked when the negation runs (Scryer: ``call((fail, \\+ 1))`` fails).  A
variable in a goal position is ``call(V)``: ``call((fail, _))`` fails and
``call((true, _))`` is ``instantiation_error``.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.atoms import is_mangled
from clausal.logic.cells import _cell_shape, compound_cell_shape, is_chars
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.pythonic_ast import nodes


# Comparison / unification goal nodes: both operands are ARGUMENTS.
_CMP_GOALS = (
    nodes.Unify, nodes.DoesNotUnify, nodes.Evaluate,
    nodes.ArithEq, nodes.ArithNeq, nodes.Lt, nodes.LtE, nodes.Gt, nodes.GtE,
    nodes.StructuralEq, nodes.StructuralNeq, nodes.in_, nodes.NotIn,
)

# Goal-position node types a body term can be made of.
_BODY_NODES = _CMP_GOALS + (
    nodes.And, nodes.Or, nodes.Not, nodes.IfExpr, nodes.CompareChain,
    nodes.TupleLiteral,
)

# Non-callable in ISO terms: a number.  (bool is True/False -- a goal.)
_NUMBER_TYPES = (int, float, complex, Decimal, Fraction)


def is_conjunction_tuple(t: Any) -> bool:
    """A plain tuple whose slot 0 is not a functor: the conjunction ``(A, B)``
    as term position builds it.  (``(z, w)`` is the CELL ``z(w)`` -- the
    representation cannot tell them apart, and the cell reading wins.)

    The ``tuple`` type object in slot 0 is the RETIRED tuple-tag spelling
    ``(tuple, 1, 2)`` (the tag is the str ``"()"`` now): still DATA, not a
    conjunction, so it is ``type_error(callable, G)`` like any non-goal
    (``is_non_callable_term``; ``test_cell_goals.
    test_a_tuple_tag_data_cell_goal_is_a_type_error``)."""
    return (type(t) is tuple and len(t) >= 2 and not _cell_shape(t)[0]
            and t[0] is not tuple)


def is_body_term(t: Any) -> bool:
    """True when *t* (dereferenced) is a body term ``call/1`` must interpret,
    rather than a predicate-call goal it resolves by name or object."""
    if t is True or t is False:
        # ``call(true)`` built as a term: ``true`` IS ``True`` in term
        # position, and before this it reached no route at all -- ``True``
        # is neither a cell, an atom nor a goal object -- and failed.
        return True
    if type(t) in _BODY_NODES:
        return True
    return is_conjunction_tuple(t)


def _is_number(t: Any) -> bool:
    return isinstance(t, _NUMBER_TYPES) and type(t) is not bool


def _culprit(term: Any) -> Any:
    """The error culprit: the term itself when it is a plain term, else its
    string form -- a raw AST node breaks catch/3 matching (see
    ``_registry._ensure_trampoline_dispatch``)."""
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    walked = _deref_walk(term)

    def has_node(x):
        if isinstance(x, nodes.Node):
            return True
        if type(x) in (tuple, list):
            return any(has_node(e) for e in x)
        return False

    return str(walked) if has_node(walked) else walked


def check_callable_body(goal: Any, context: str) -> None:
    """ISO 7.6.2: raise ``type_error(callable, Goal)`` when a goal position
    reachable through the TRANSPARENT constructs holds a number.  ``not``'s
    operand is not walked (it is checked when the negation runs)."""
    def walk(t):
        t = deref(t)
        if is_var(t):
            return False
        if _is_number(t):
            return True
        if is_conjunction_tuple(t):
            return any(walk(e) for e in t)
        if type(t) is nodes.TupleLiteral:
            return any(walk(e) for e in t.elements)
        if type(t) in (nodes.And, nodes.Or):
            return walk(t.left) or walk(t.right)
        if type(t) is nodes.IfExpr:
            return walk(t.test) or walk(t.body) or walk(t.orelse)
        is_cell, functor = compound_cell_shape(t)
        if is_cell and len(t) == 3 and functor in (",", ";"):
            return walk(t[1]) or walk(t[2])
        return False

    if walk(goal):
        from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
        culprit = _culprit(goal)
        raise LogicException(type_error(
            "callable", culprit, f"{context}: {culprit} is not a callable body"))


class _Converter:
    """One conversion: the goal-node tree plus its run-time parameters."""

    def __init__(self, db):
        self.db = db
        self.params: list[tuple[Var, Any]] = []
        self._by_var: dict[int, Var] = {}

    def _param(self, value, raw=None):
        if raw is not None:
            pv = self._by_var.get(id(raw))
            if pv is not None:
                return pv
        pv = Var()
        self.params.append((pv, value))
        if raw is not None:
            self._by_var[id(raw)] = pv
        return pv

    # ── argument positions ──────────────────────────────────────────────
    def arg(self, raw):
        """An argument-position subterm with its VALUES lifted into run-time
        parameters, so the compiled body depends only on its structure.

        Only STRUCTURE is kept in the compiled code: lists, tuples/cells
        (slot 0 of a cell is the functor), and arithmetic nodes, whose
        elements are lifted in turn.  Every other value -- a number, an atom,
        a ``datetime.date``, an ndarray, any opaque Python object
        -- becomes a parameter, never a literal: a literal needs a lowering
        and a hashable cache key, and a parameter needs neither (roborev on
        152a8f64: a bound Var holding a date was inlined and lost the query
        compiler's bound-Var fallback).  The one exception is a MANGLED atom
        (a predicate handle), which keeps the literal lowering that knows how
        to treat it.
        """
        t = deref(raw)
        if is_var(t):
            return t                      # an unbound Var is already a slot
        memo = raw if isinstance(raw, Var) else None
        if type(t) is str and is_mangled(t):
            return t
        if type(t) is list:
            return [self.arg(e) for e in t]
        if type(t) is tuple:
            is_cell, _ = _cell_shape(t)
            if is_cell and not compound_cell_shape(t)[0]:
                return self._param(t, memo)   # TUPLE_TAG / chars carrier: data
            if is_cell:
                # Slot 0 is the functor -- structure, never a parameter.
                return (t[0],) + tuple(self.arg(e) for e in t[1:])
            return tuple(self.arg(e) for e in t)
        if isinstance(t, nodes.Node):
            if type(t) in _NODE_FIELDS:
                return self._rebuild(t, self.arg)
            return t                      # code (a Call, a Lambda ...): as is
        return self._param(t, memo)

    def _rebuild(self, node, fn):
        kw = {}
        for name in _NODE_FIELDS[type(node)]:
            v = getattr(node, name)
            if type(v) is list:
                kw[name] = [fn(e) for e in v]
            else:
                kw[name] = fn(v)
        return type(node)(**kw)

    # ── goal positions ──────────────────────────────────────────────────
    def _call_leaf(self, t):
        """``call(P)``, ``P`` bound at run time to the leaf goal *t*."""
        return nodes.Call(func=nodes.LoadName(name="call"),
                          args=[self._param(t)], kwargs=[])

    def _maybe_tabled(self, raw):
        """Under ``not`` / an ``if_`` test: a cell naming a TABLED predicate
        is emitted as the direct call (WFS-sound tabled negation, as the
        compiler gives the same text in a clause); None otherwise."""
        t = deref(raw)
        is_cell, functor = compound_cell_shape(t)
        if not is_cell or self.db is None or is_mangled(functor):
            return None
        from clausal.logic.compiler.tabled_naf import _is_tabled_naf  # noqa: PLC0415
        # The probe needs only the name and the arity; the arguments are
        # lifted into parameters only for the call that is actually emitted.
        probe = nodes.Call(func=nodes.LoadName(name=functor),
                           args=list(t[1:]), kwargs=[])
        if not _is_tabled_naf(probe, self.db):
            return None
        return nodes.Call(func=nodes.LoadName(name=functor),
                          args=[self.arg(a) for a in t[1:]], kwargs=[])

    def goal(self, raw):
        t = deref(raw)
        if is_var(t):
            return self._call_leaf(t)     # ISO: a variable goal is call(V)
        if t is True or t is False:
            return t
        if type(t) is str and t in ("true",):
            return True
        if type(t) is str and t in ("fail", "false"):
            return False
        if is_conjunction_tuple(t):
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t])
        tt = type(t)
        if tt is nodes.TupleLiteral:
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t.elements])
        if tt is nodes.And:
            return nodes.And(left=self.goal(t.left), right=self.goal(t.right))
        if tt is nodes.Or:
            return nodes.Or(left=self.goal(t.left), right=self.goal(t.right))
        if tt is nodes.Not:
            direct = self._maybe_tabled(t.operand)
            return nodes.Not(operand=direct if direct is not None
                             else self._call_leaf(t.operand))
        if tt is nodes.IfExpr:
            test = self._maybe_tabled(t.test)
            return nodes.IfExpr(
                test=test if test is not None else self.goal(t.test),
                body=self.goal(t.body), orelse=self.goal(t.orelse))
        if tt is nodes.CompareChain:
            return nodes.CompareChain(
                comparisons=[self._rebuild(c, self.arg) for c in t.comparisons])
        if tt in _CMP_GOALS:
            return self._rebuild(t, self.arg)
        is_cell, functor = compound_cell_shape(t)
        if is_cell and len(t) == 3 and functor == ",":
            return nodes.TupleLiteral(elements=[self.goal(t[1]), self.goal(t[2])])
        if is_cell and len(t) == 3 and functor == ";":
            return nodes.Or(left=self.goal(t[1]), right=self.goal(t[2]))
        if is_cell and len(t) == 2 and functor == "\\+":
            direct = self._maybe_tabled(t[1])
            return nodes.Not(operand=direct if direct is not None
                             else self._call_leaf(t[1]))
        # Everything else -- a cell, an atom, a predicate class, a lambda,
        # a qualified goal -- is call/1's to resolve, exactly as it would be
        # on its own.
        return self._call_leaf(t)


# ── the compiler's SPECIAL FORMS ────────────────────────────────────────────
#
# A goal the clause-body compiler lowers INLINE rather than through a
# dispatch: ``terms_to_goalop._convert``'s MetaCall arms (plus ``eval_/2``,
# which it lowers to ArithEval).  No runtime builtin carries these names, so
# before this ``call(("findall", X, G, L))`` resolved to nothing and FAILED
# SILENTLY.  Now the cell is turned back into the very ``Call`` node the same
# text is in a clause body, and compiled -- the compiler's lowering IS the
# semantics, there is no second copy of it.
#
# Each argument has a ROLE:
#   G  a goal.  Emitted as ``call(P)``, P bound at run time to the argument,
#      because every one of these forms is DEFINED on ``call/1`` of its goal
#      (ISO 7.8.9 catch/3, 8.10.1 findall/3, 8.15.2 once/1 ...): so an unbound
#      goal is instantiation_error, a number is type_error(callable, G) naming
#      the whole goal, and a body term, a special form or a qualified goal
#      runs exactly as call/1 runs it -- inside the form, so catch/3 catches it.
#   A  a term argument (template, bag, catcher, ball, counter, expression).
#   W  a when/2 condition: the compile-time ``or`` spelling is rebuilt, the
#      rest are terms the runtime reads (coroutining._install_when_condition).
#
# ``tests/test_call_runs_special_form_cells.py`` holds this table to
# ``terms_to_goalop`` in both directions, so a new special form cannot be
# added to the compiler without being made callable here.
SPECIAL_FORMS: dict[tuple[str, int], str] = {
    ("findall", 3): "AGA",
    ("bagof", 3): "AGA",
    ("setof", 3): "AGA",
    ("once", 1): "G",
    ("forall", 2): "GG",
    ("catch", 3): "GAG",
    ("catch_error", 2): "GA",
    ("catch_recover", 3): "GAG",
    ("throw", 1): "A",
    ("call_nth", 2): "GA",
    ("count_all", 2): "GA",
    ("setup_call_cleanup", 3): "GGG",
    ("call_cleanup", 2): "GG",
    ("freeze", 2): "AG",
    ("when", 2): "WG",
    ("eval_", 2): "AA",
    ("halt", 0): "",
    ("halt", 1): "A",
}


def is_special_form(functor: Any, arity: int) -> bool:
    """True when *functor*/*arity* is a compiler special form."""
    return type(functor) is str and (functor, arity) in SPECIAL_FORMS


def _when_condition(conv, raw):
    """A when/2 condition: ``or`` (and ISO ``;``) rebuilt as the node the
    compiler lowers to ``$install_when_disjunction``; everything else --
    ``nonvar(X)``, ``ground(X)``, a conjunction pair -- is a term the runtime
    reads, exactly as the compiled body hands it over."""
    t = deref(raw)
    if type(t) is nodes.Or:
        return nodes.Or(left=_when_condition(conv, t.left),
                        right=_when_condition(conv, t.right))
    is_cell, functor = compound_cell_shape(t)
    if is_cell and functor == ";" and len(t) == 3:
        return nodes.Or(left=_when_condition(conv, t[1]),
                        right=_when_condition(conv, t[2]))
    return conv.arg(t)


def special_form_dispatch(db, folded, context: str):
    """``(dispatch, [])`` running the special-form goal *folded* -- a cell
    ``(name, A1 ... An)`` or, for ``halt/0``, the atom -- in *db*'s module,
    as the same goal written in a clause body runs."""
    if type(folded) is str:
        functor, args = folded, ()
    else:
        functor, args = folded[0], tuple(folded[1:])
    roles = SPECIAL_FORMS[(functor, len(args))]
    conv = _Converter(db)
    built = []
    for role, a in zip(roles, args):
        if role == "G":
            built.append(conv._call_leaf(deref(a)))
        elif role == "W":
            built.append(_when_condition(conv, a))
        else:
            built.append(conv.arg(a))
    node = nodes.Call(func=nodes.LoadName(name=functor), args=built, kwargs=[])
    return _compiled_node_dispatch(db, conv, node)


# ── errors (operator ruling 2026-09-25: follow Scryer) ──────────────────────


def _indicator(name, arity):
    from clausal.logic.atoms import mint  # noqa: PLC0415
    return ("/", mint(name), arity)


# The construct a body term spells, as ``(name, arity)`` -- what call/N's
# fold extends.  Clausal's own spelling for the Clausal-only constructs
# (``if_``, and a comparison's operator, e.g. ``==`` for ArithEq).
def _construct(t):
    if t is True:
        return "true", 0
    if t is False:
        return "false", 0
    if type(t) in (tuple, nodes.TupleLiteral, nodes.And, nodes.CompareChain):
        return ",", 2
    if type(t) is nodes.Or:
        return ";", 2
    if type(t) is nodes.Not:
        return "\\+", 1
    if type(t) is nodes.IfExpr:
        return "if_", 3
    return _ISO_NAME.get(type(t), type(t).op), 2   # a comparison node


# The ISO name of each comparison node, which call/N's error names (checked
# on the box's Scryer: ``call((X =:= Y), z)`` -> existence_error ``(=:=)/3``
# and likewise ``==``, ``=\\=``, ``\\==``, ``=``, ``\\=``, ``<``, ``=<``,
# ``>``, ``>=``, ``is``).  Needed because the Clausal surface spells two
# different nodes alike: ``==`` is ArithEq (ISO ``=:=``) AND StructuralEq.
# ``in``/``not in`` have no ISO counterpart and keep the Clausal spelling.
_ISO_NAME = {
    nodes.ArithEq: "=:=", nodes.ArithNeq: "=\\=",
    nodes.StructuralEq: "==", nodes.StructuralNeq: "\\==",
    nodes.Unify: "=", nodes.DoesNotUnify: "\\=",
    nodes.Lt: "<", nodes.LtE: "=<", nodes.Gt: ">", nodes.GtE: ">=",
    nodes.Evaluate: "is", nodes.in_: "in", nodes.NotIn: "not in",
}


def folded_existence_error(name, arity, context):
    """``existence_error(procedure, Name/Arity)`` for a goal call/N's fold
    turned into a name no procedure has (Scryer: ``call(true, x)`` ->
    ``true/1``, ``call([a], x)`` -> ``'.'/3``)."""
    from clausal.logic.exceptions import existence_error  # noqa: PLC0415
    return existence_error(
        "procedure", _indicator(name, arity),
        f"{context}: call/N adds its extra arguments to the goal, and "
        f"{name}/{arity} is no procedure")


def body_with_extras_error(goal, n_extra, context):
    """``call((A, B), X)``: the fold makes ``','(A, B, X)``, which names no
    procedure -- Scryer: ``existence_error(procedure, ','/3)``, and the
    analogue for every other construct (``;``/3, ``\\+``/2, ``->``/3)."""
    name, arity = _construct(goal)
    return folded_existence_error(name, arity + n_extra, context)


def is_non_callable_term(t, lists: bool = True) -> bool:
    """True for a term that can never be a goal: a number, ``None``, tuple
    DATA, and -- with *lists* -- a non-empty list or a string.  *lists* is a
    ROUTING flag, not a callability claim: a list is the callable compound
    '.'/2 (ISO), which the shared resolver answers with existence_error
    '.'/N; callers that must send a list to that resolver pass True, and
    phrase (where a list is a DCG terminal) passes False.  An unbound Var,
    an atom, a cell and a goal object each have their own answer."""
    t = deref(t)
    if is_var(t):
        return False
    if _is_number(t) or t is None:
        return True
    if type(t) is tuple and t:
        is_cell, _ = _cell_shape(t)
        if t[0] is tuple or (is_cell and not compound_cell_shape(t)[0]
                             and not is_chars(t)):
            return True                   # tuple DATA (either tag spelling)
    if lists and ((type(t) is list and t) or is_chars(t)):
        return True
    return False


def needs_meta_call(t, db=None) -> bool:
    """True for a goal a goal-taking list builtin must hand to ``call/N`` per
    element: everything that is not already a runnable goal OBJECT (a closure,
    a predicate class, a ``_get_dispatch`` implementor, a declared predicate
    handle).  That is an unbound Var, a cell, a plain atom, a
    body term -- and a NON-callable term (number, list, string, tuple data).

    Operator rule 2026-09-25, ISO first: the WG17 Prolog prologue DEFINES
    ``maplist(G, [E|Es]) :- call(G, E), maplist(G, Es).`` (include/exclude/
    foldl alike), so each element must answer exactly what ``call/N``
    answers -- ``maplist(p(1), L)`` calls ``p(1, E)``, ``maplist(_, [1])``
    and ``maplist(42, [1])`` raise as ``call(_, 1)`` and ``call(42, 1)`` do,
    and ``maplist([a], [1])`` is ``existence_error(procedure, '.'/3)`` like
    ``call([a], 1)``.  *db* is the caller's database, the ruling-Q0 hint for
    the declared-handle check."""
    t = deref(t)
    if is_var(t):
        return True
    if callable(t) and not isinstance(t, nodes.Node):
        return False                      # a closure / predicate class
    if hasattr(t, "_get_dispatch"):
        return False
    if type(t) is str:
        from clausal.logic.predicate import is_declared_predicate_name  # noqa: PLC0415
        return not is_declared_predicate_name(t, db=db)
    return (compound_cell_shape(t)[0]
            or is_body_term(t) or is_non_callable_term(t))


class MetaCallGoal:
    """*goal* run through ``call/N`` in *db*'s module, whatever N is.

    What a goal-taking list builtin (maplist, foldl, include ...) receives in
    place of a goal only ``call/N`` can resolve: its dispatch (the duck-typed,
    single-argument ``_get_dispatch`` protocol) is ``call/(K+1)`` with the
    goal first, K being however many arguments the builtin supplies per
    element.  So every such shape behaves exactly as ``call(G, A1 ...)``
    does -- one resolution rule, not a second copy of it.
    """

    __slots__ = ("goal", "db", "_calls")

    def __init__(self, goal, db):
        self.goal = goal
        self.db = db
        self._calls = {}

    def __repr__(self):
        return f"MetaCallGoal({self.goal!r})"

    def _get_dispatch(self):
        goal, db, calls = self.goal, self.db, self._calls

        def _meta_call(this_generator, _proceed, _fail, _catcher, *args):
            n = len(args)                 # the extras, plus the trail
            fn = calls.get(n)
            if fn is None:
                from clausal.logic.builtins._registry import _DB_BUILTINS  # noqa: PLC0415
                fn = calls[n] = _DB_BUILTINS[("call", n)](db)
            return fn(this_generator, _proceed, _fail, _catcher, goal, *args)
        return _meta_call


def non_callable_goal_error(goal, context):
    """``call(42)``, ``call(None)``, tuple data: ``type_error(callable,
    Goal)``.  (A list or string is NOT this -- it is existence_error '.'/2.)"""
    from clausal.logic.exceptions import type_error  # noqa: PLC0415
    from clausal.logic.cells import chars_text  # noqa: PLC0415
    if is_chars(goal):
        # Scryer's culprit is the LIST of chars (``call("ab")`` ->
        # type_error(callable, [a, b])); the carrier spelling never leaks.
        text = chars_text(goal)
        culprit, shown = list(text), f'"{text}"'
    else:
        culprit = _culprit(goal)
        shown = repr(culprit)
    return type_error(
        "callable", culprit,
        f"{context}: {shown} is not a callable term (operator ruling "
        f"2026-09-25: follow Scryer)")


def iso_control_cell_dispatch(db, cell, functor, arity, context):
    """An ISO control-construct CELL in goal position (after call/N's fold).

    ``(",", A, B)``, ``(";", A, B)`` and ``("\\+", G)`` run as bodies, through
    the same converter as the Clausal spellings.  ``->`` and ``*->`` are
    REFUSED: Clausal is cut-free with no committed choice (ruled, forever).
    The refusal is ``existence_error(procedure, '->'/2)`` -- exactly what an
    ISO system that does not provide a construct answers when a program calls
    it, so a portable ``catch/3`` for "no such procedure" sees it; the
    context names the reason and the Clausal alternative.  Any other arity is
    the fold's ``','/3`` and friends (Scryer: existence_error).
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, existence_error,
    )
    if (functor in (",", ";") and arity == 2) or (functor == "\\+" and arity == 1):
        return body_goal_dispatch(db, cell, context)
    if functor in ("->", "*->") and arity == 2:
        raise LogicException(existence_error(
            "procedure", _indicator(functor, 2),
            f"{context}: {functor}/2 is not provided -- Clausal is cut-free "
            f"with no committed choice (ruled permanently), so if-then "
            f"{'(soft cut) ' if functor == '*->' else ''}has no construct; "
            f"write if_(Cond, Then, Else), whose test is not committed"))
    raise LogicException(existence_error(
        "procedure", _indicator(functor, arity),
        f"{context}: {functor}/{arity} is no procedure -- the control "
        f"construct {functor} takes "
        f"{1 if functor == chr(92) + '+' else 2} argument(s)"))


# The semantic fields of each node type the converter rebuilds (``position``
# is location only and is dropped).
def _node_fields(cls):
    import dataclasses  # noqa: PLC0415
    return tuple(f.name for f in dataclasses.fields(cls) if f.name != "position")


_NODE_FIELDS: dict[type, tuple[str, ...]] = {}
for _cls in (_CMP_GOALS + (
        nodes.CompareChain,
        nodes.Add, nodes.Sub, nodes.Mult, nodes.Div, nodes.FloorDiv,
        nodes.Mod, nodes.Pow, nodes.MatMult, nodes.LShift, nodes.RShift,
        nodes.BitOr, nodes.BitXor, nodes.BitAnd,
        nodes.UnaryPlus, nodes.Negate, nodes.Invert)):
    _NODE_FIELDS[_cls] = _node_fields(_cls)
del _cls


# ── the module the body compiles against ────────────────────────────────────

_DBLESS_MODULE = None


def _module_for(db):
    """The :class:`Module` whose namespace the body compiles against.

    The loaded module when *db* has one (``$module`` in its dict).  Otherwise
    one wrapper per db, kept ON the db: the query cache keys on
    ``id(module)``, so a fresh wrapper per call would both miss the cache and
    risk a recycled id serving code compiled against another db.
    """
    global _DBLESS_MODULE
    from clausal.logic.database import Module  # noqa: PLC0415
    if db is None:
        if _DBLESS_MODULE is None:
            _DBLESS_MODULE = Module("$call_body")
        return _DBLESS_MODULE
    module_dict = getattr(db, "module_dict", None)
    if module_dict is not None:
        mod = module_dict.get("$module")
        if isinstance(mod, Module) and mod.db is db:
            return mod
    mod = getattr(db, "_call_body_module", None)
    if mod is None:
        mod = Module("$call_body", db=db, module_dict=module_dict)
        db._call_body_module = mod
    return mod


def body_goal_dispatch(db, goal_val, context: str):
    """``(dispatch, [])`` running the body term *goal_val* in *db*'s module.

    The shape ``higher_order._resolve_named_goal`` returns, so ``call/N``
    drives it like any resolved goal.
    """
    check_callable_body(goal_val, context)
    conv = _Converter(db)
    node = conv.goal(goal_val)
    if node is True:
        from clausal.logic.builtins.higher_order import _control_succeed_once  # noqa: PLC0415
        return _control_succeed_once, []
    if node is False:
        from clausal.logic.builtins.higher_order import _control_fail  # noqa: PLC0415
        return _control_fail, []
    return _compiled_node_dispatch(db, conv, node)


def _compiled_node_dispatch(db, conv, node):
    """``(dispatch, [])`` running the goal NODE *node* -- *conv*'s product --
    compiled through the query compiler against *db*'s module."""
    from clausal.logic.solve import _compile_as_query  # noqa: PLC0415
    fn, param_pairs = _compile_as_query(node, _module_for(db))
    params = conv.params + list(param_pairs)

    def _call_body(this_generator, _proceed, _fail, _catcher, trail):
        for pv, value in params:
            unify(pv, value, trail)       # pv is fresh: binds, never fails
        sg = StepGenerator(fn, this_generator, this_generator, this_generator, trail)
        _st = yield (sg, None)
        while _st is not DONE:
            yield (_proceed, None)
            _st = yield (sg, None)
        yield (_fail, DONE)

    return _call_body, []


__all__ = [
    "is_body_term", "check_callable_body", "body_goal_dispatch",
    "body_with_extras_error", "non_callable_goal_error",
    "iso_control_cell_dispatch", "folded_existence_error",
    "is_non_callable_term",
    "needs_meta_call", "MetaCallGoal",
    "SPECIAL_FORMS", "is_special_form", "special_form_dispatch",
]
