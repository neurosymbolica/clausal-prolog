"""ISO ``clause/2`` (13211-1 §8.8.1): ``clause(Head, Body)`` is true iff
``Head :- Body`` unifies with a clause of a DYNAMIC (public) procedure.

Step 2 of the ISO ``clause/2`` plan (operator ruling 2026-09-25, option B).

HEAD.  A stored clause is not the clause the program wrote: the head
normalizers (``database._normalize_dataclass_fact``,
``database._normalize_structural_head_args``,
``database_ops._normalize_fact_clause``) move constants and compound
arguments out of the head into leading ``Unify(V, Arg)`` body goals.
``Clause.hoisted`` counts them, and ``body[:hoisted]`` is put BACK -- run as
the unifications they are, which binds each fresh head variable to its
argument -- so ``fib(0, 0)`` reads back as ``fib(0, 0)`` with Body ``true``.

BODY.  ``body[hoisted:]`` is handed back as a TERM, in exactly the form term
position builds from the same text -- which is the form ``call/1`` runs
(step 1, ``call_body``).  It is built by the SAME lowering: the goals go
through the query compiler as ``Out = (G1, ..., Gn)``, the construction the
clause ``g(Out) <- (Out is (G1, ..., Gn))`` makes, on a private trail, and
the result is copied (a fresh renaming) before the trail is undone.

=========================================  =================================
stored goal (a node in the clause body)    Body term
=========================================  =================================
(none) / ``[True]``                        ``True``
``G1, ..., Gn`` (n > 1)                    the plain tuple ``(G1', ..., Gn')``
``Call(LoadName('p'), [A...])``            the cell ``("p", A'...)``
``Not(G)`` / ``Or(A, B)`` / ``IfExpr``     the same node over converted goals
``Unify`` ``Gt`` ``ArithEq`` ``in_`` ...   the same comparison node
``CompareChain``                           the same node
``Add(...)`` etc. in an argument           the same node (not evaluated)
``LoadName('p')`` in an argument           what the name is bound to
``True`` in a conjunction                  ``True``
a meta-call special form (``findall/3``,   the cell ``("findall", T', G', L')``
``once/1``, ``catch/3``, ``forall/2``,     (``SPECIAL_FORMS``)
``throw/1``, ``eval_/2`` ...)
a call of a name bound to nothing (a       the cell
procedure not yet defined)
a call of a ``_get_dispatch`` object       the cell (``match(P, S)``)
(``ModulePredicate``: ``regex.match``)
a ``PyThunk`` reading no variable          its value (``5(m)``, ``++len("ab")``)
a ``PyThunk`` reading clause variables     NO TERM -- see below
(``++(X+1)``, ``f"{X}"``, regex groups)
=========================================  =================================

The special forms have no term class and no runtime builtin, so term
position cannot build them
(``todo/control-builtins-cannot-be-built-as-terms-2026-09-25.md``); they come
back as the ISO term the text denotes, the CELL -- not refused, and not
lossy: it is the term ``findall(T, G, L)``, and since main d724dd52
``call/N`` runs it (and a ModulePredicate's cell), so ``clause(H, B),
call(B)`` answers what ``H`` does (``tests/test_clause_2_iso.py``, mf/2).

A clause whose body reads its variables from Python has NO term form: the
closure is not a term, and building it evaluates it with the variables
unbound (``f"v{Y}"`` builds ``'v_0'``).  So does one whose body the
construction cannot build at all.  ``clause/2`` refuses such a clause with
``permission_error(access, private_procedure, Name/Arity)`` -- ISO's "this
clause may not be inspected" -- and only when its HEAD unifies with the
query, so a query that does not select it is unaffected.

WHICH PROCEDURES.  ISO: a procedure is readable iff it is dynamic.  Here
that is ``row.dynamic`` (declared ``-dynamic``) or an UNLOCKED row -- one
``assertz`` created, or built from Python without a load: exactly the rows a
runtime ``assertz`` may write (``database.write_refusal``, rule 2).

====================================  ======================================
Head                                  answer
====================================  ======================================
unbound                               instantiation_error
not callable (number, tuple data...)  type_error(callable, Head)
Body not var and not callable         type_error(callable, Body)
dynamic procedure                     its clauses, fresh, in order, under the
                                      logical update view (a snapshot)
static (locked) user procedure        permission_error(access,
                                      private_procedure, Name/Arity)
builtin / meta-call special form /    permission_error(access,
control construct                     private_procedure, Name/Arity)
unknown procedure                     fails
a non-empty list or string            type_error(callable, List) -- Scryer,
(as Head or Body)                     by operator ruling (ISO would fail)
[] / ""                               fails (the atom '[]')
``M:H`` / a predicate handle          resolved in that module
====================================  ======================================

Checked on the box against Scryer and Trealla (2026-09-25) -- see
``tests/test_clause_2_iso.py`` for the pinned expectations and where the two
differ from ISO.
"""

from __future__ import annotations

import weakref
from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.cells import (
    CELL_GOAL_CONTROL_FUNCTORS, QUALIFIED_GOAL_FUNCTOR, compound_cell_shape,
    is_chars, make_cell, qualify_mangled_goal, resolve_qualified_goal_cell,
)
from clausal.logic.exceptions import (
    LogicException, instantiation_error, permission_error, type_error,
)
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.pythonic_ast import nodes

from clausal.logic.builtins._registry import (
    _BUILTINS, _DB_BUILTINS, _db_builtin, BuiltinTerm as _BuiltinTerm,
)

_CONTEXT = "clause/2"

# The compiler's meta-call special forms: goals ``terms_to_goalop`` lowers by
# NAME and ARITY to a MetaCall/ArithEval, which have no term class and no
# runtime builtin.  Kept in step with the ``case nodes.Call(func=nodes.
# LoadName(name=...))`` arms there; a name at another arity is an ordinary
# call (it falls through those arms), so the arity is part of the key.
SPECIAL_FORMS = frozenset({
    ("throw", 1), ("halt", 0), ("halt", 1), ("once", 1), ("call_nth", 2),
    ("count_all", 2), ("setup_call_cleanup", 3), ("call_cleanup", 2),
    ("freeze", 2), ("when", 2), ("findall", 3), ("bagof", 3), ("setof", 3),
    ("catch", 3), ("catch_error", 2), ("catch_recover", 3), ("forall", 2),
    ("eval_", 2),
})

# The zero-arity control constructs (``higher_order._ZERO_ARITY_CONTROL_GOALS``).
_ZERO_ARITY_CONTROL = frozenset({"true", "fail", "false", "!"})


def _indicator(name: str, arity: int):
    from clausal.logic.builtins.call_body import _indicator as ind  # noqa: PLC0415
    return ind(name, arity)


def _private(name: str, arity: int, why: str) -> LogicException:
    return LogicException(permission_error(
        "access", "private_procedure", _indicator(name, arity),
        f"{_CONTEXT}: {name}/{arity} {why}, so its clauses cannot be "
        f"inspected (ISO 8.8.1: only a dynamic procedure's can)"))


def _is_callable(t: Any) -> bool:
    """ISO callable: an atom or a compound -- in Clausal spellings."""
    from clausal.logic.builtins.call_body import is_body_term  # noqa: PLC0415
    if type(t) is str or t is True or t is False:
        return True                      # an atom (a handle is one too)
    if is_body_term(t) or compound_cell_shape(t)[0]:
        return True
    if _is_nonempty_list(t):
        # OPERATOR RULING 2026-09-25 -- an explicit exception to "ISO first":
        # ISO makes a non-empty list the callable compound '.'/2 (so
        # clause([a], B) would name an undefined procedure and fail), but
        # clause/2 follows Scryer and Trealla here: a non-empty list or
        # string, as Head or as Body, is type_error(callable, List).  (Trealla
        # fails for a list BODY; Scryer raises, and Scryer is the reference.)
        # The empty list is the atom '[]' in both: callable, and it fails.
        return False
    if type(t) is list or is_chars(t):
        return True                      # [] / "": the atom '[]'
    if isinstance(t, _BuiltinTerm):
        # A builtin's object (``clausal.between``) is what its CLASS was
        # before W4b-3 slice 3: callable here, as the class was.
        return True
    return is_term_instance(t) and not isinstance(t, nodes.Node)


def _is_nonempty_list(t: Any) -> bool:
    """A non-empty or partial list, or a non-empty string (the list of its
    chars), in any Clausal spelling."""
    from clausal.terms import SegList, SegString  # noqa: PLC0415
    from clausal.logic.cells import chars_text  # noqa: PLC0415
    if type(t) is list:
        return bool(t)
    if is_chars(t):
        return bool(chars_text(t))
    return isinstance(t, (SegList, SegString))


def _type_check(t: Any, what: str) -> None:
    if not _is_callable(t):
        from clausal.logic.builtins.call_body import _culprit  # noqa: PLC0415
        from clausal.logic.cells import chars_text  # noqa: PLC0415
        # A string's culprit is the LIST of its chars, as Scryer reports
        # clause("ab", _): type_error(callable, [a,b]).
        culprit = list(chars_text(t)) if is_chars(t) else _culprit(t)
        raise LogicException(type_error(
            "callable", culprit,
            f"{_CONTEXT}: the {what} {culprit!r} is not a callable term"))


def _as_cell(head: Any) -> Any:
    """A stored head (a cell since P2; a class instance pre-P2) as the cell
    it spells."""
    if is_term_instance(head) and not compound_cell_shape(head)[0]:
        fields = term_field_names(head)
        name = type(head).__name__
        return make_cell(name, *(getattr(head, f) for f in fields)) if fields else name
    return head


# ── Stored goal -> term ─────────────────────────────────────────────────────


def _is_goal_object(binding: Any) -> bool:
    """A name bound to a runnable goal OBJECT that term construction cannot
    call: a ``_get_dispatch`` implementor that is not a predicate class or a
    builtin class (``ModulePredicate`` and the other out-of-tree adapters).
    Constructing ``match(P, S)`` calls ``match(...)``, and such an object
    raises ``TypeError`` -- its term is the cell."""
    return (hasattr(binding, "_get_dispatch")
            and not isinstance(binding, _BuiltinTerm))


_MISSING = object()


def _needs_cell(name: str, arity: int, namespace: dict, db=None) -> bool:
    """True for a call term construction cannot build:

    - a meta-call special form (``SPECIAL_FORMS``);
    - a name bound to NOTHING -- no module binding and no builtin: a
      procedure not (yet) defined, whose term is still the cell (ISO:
      ``clause/2`` hands back the body as written).  "Nothing" is a missing
      key, not a key bound to ``None``;
    - a name bound to a goal object (``_is_goal_object``);
    - a name bound to a predicate at ANOTHER arity: construction goes
      through that binding and refuses the argument count, where the call
      itself names ``name/arity`` -- a different procedure, spelled as the
      cell.
    """
    from clausal.logic.predicate import (  # noqa: PLC0415
        binding_grants_arity, is_declared_predicate_name,
    )
    if (name, arity) in SPECIAL_FORMS:
        return True
    binding = namespace.get(name, _MISSING)
    if binding is _MISSING:
        return (name, arity) not in _BUILTINS and (name, arity) not in _DB_BUILTINS
    if _is_goal_object(binding):
        return True
    if is_declared_predicate_name(binding, db=db):
        return not binding_grants_arity(binding, arity, db, name)
    return False


def _spell_as_cells(t: Any, namespace: dict, db=None) -> Any:
    """*t* with every goal term construction cannot build rewritten to the
    node that lowers to its CELL: ``Call(LoadName('findall'), [T, G, L])``
    becomes ``TupleLiteral(['findall', T, G, L])``, which term construction
    builds as ``("findall", T', G', L')`` -- for every call ``_needs_cell``
    names.  Everything else is returned unchanged -- the same
    object when nothing below it changed."""
    import dataclasses  # noqa: PLC0415
    if type(t) is list:
        new = [_spell_as_cells(e, namespace, db) for e in t]
        return t if all(a is b for a, b in zip(new, t)) else new
    if type(t) is tuple:
        new = tuple(_spell_as_cells(e, namespace, db) for e in t)
        return t if all(a is b for a, b in zip(new, t)) else new
    if not isinstance(t, nodes.Node) or not dataclasses.is_dataclass(t):
        return t
    if (type(t) is nodes.Call and type(t.func) is nodes.LoadName
            and not t.kwargs and _needs_cell(t.func.name, len(t.args),
                                             namespace, db)):
        return nodes.TupleLiteral(
            elements=[t.func.name] + [_spell_as_cells(a, namespace, db)
                                      for a in t.args])
    changed = {}
    for f in dataclasses.fields(t):
        v = getattr(t, f.name)
        nv = _spell_as_cells(v, namespace, db)
        if nv is not v:
            changed[f.name] = nv
    return dataclasses.replace(t, **changed) if changed else t


def _capturing_thunk(t: Any) -> Any:
    """The first deferred Python expression (``++(...)``, an f-string, a
    regex group binding) in *t* that READS clause variables, or ``None``.

    Such a goal is a Python closure over the clause's variables, not a term:
    building it evaluates it, with those variables unbound -- the f-string
    ``f"v{Y}"`` builds the string ``'v_0'``.  So a clause holding one has no
    Body term (see ``_unrepresentable``).  A thunk that reads NO variable (a
    quantity literal ``5(m)``, ``++len("ab")``) is a constant and builds as
    its value, exactly as term position builds it."""
    import dataclasses  # noqa: PLC0415
    from clausal.terms import PyThunk  # noqa: PLC0415
    if isinstance(t, PyThunk):
        return t if t.var_objects else None
    if type(t) in (list, tuple):
        for e in t:
            hit = _capturing_thunk(e)
            if hit is not None:
                return hit
        return None
    if isinstance(t, nodes.Node) and dataclasses.is_dataclass(t):
        for f in dataclasses.fields(t):
            hit = _capturing_thunk(getattr(t, f.name))
            if hit is not None:
                return hit
    return None


# The GOAL-position arguments of each meta-call special form (the rest are
# data): a thunk there is code the goal runs, not a value.
_GOAL_ARGS = {
    ("once", 1): (0,), ("call_nth", 2): (0,), ("count_all", 2): (0,),
    ("findall", 3): (1,), ("bagof", 3): (1,), ("setof", 3): (1,),
    ("forall", 2): (0, 1), ("catch", 3): (0, 2), ("catch_error", 2): (0,),
    ("catch_recover", 3): (0, 2), ("call_cleanup", 2): (0, 1),
    ("setup_call_cleanup", 3): (0, 1, 2), ("freeze", 2): (1,),
    ("when", 2): (1,),
}


# Goal-taking BUILTINS that are not special forms: their goal argument is
# run, so a thunk there is code.  (call/N is handled by name.)
_BUILTIN_GOAL_ARGS = {
    ("time_goal", 1): (0,), ("time_goal", 2): (0,),
    ("phrase", 2): (0,), ("phrase", 3): (0,),
    ("findall", 4): (1,),
}


def _goal_positions(name: str, n: int, db) -> tuple:
    """The argument positions of a ``name/n`` call that are GOALS: call/N
    and call_goal/N's first, a special form's (``_GOAL_ARGS``), a goal-first
    list builtin's first (``higher_order._GOAL_FIRST_LIST_BUILTINS``: maplist
    & co.), time_goal / phrase, and a user predicate's ``-meta_predicate``
    positions whose spec qualifies (``:`` or an integer, Scryer's
    ``qualified_spec``)."""
    if n and name in ("call", "call_goal"):
        return (0,)
    hit = _GOAL_ARGS.get((name, n)) or _BUILTIN_GOAL_ARGS.get((name, n))
    if hit:
        return hit
    from clausal.logic.builtins.higher_order import (  # noqa: PLC0415
        _GOAL_FIRST_LIST_BUILTINS,
    )
    if (name, n) in _GOAL_FIRST_LIST_BUILTINS:
        return (0,)
    specs = db.meta_predicate_specs(name, n) if db is not None else None
    if specs:
        from clausal.logic.meta_predicate import is_qualifying_spec  # noqa: PLC0415
        return tuple(i for i, sp in enumerate(specs) if is_qualifying_spec(sp))
    return ()


def _goal_thunk(goals: list, db=None) -> Any:
    """The first ``PyThunk`` in a GOAL position of *goals*, or ``None``.

    A thunk used as a goal (``fx(1) <- ++print("x")``) is Python code run
    for its effect, not a term -- even one that reads no variable.  Building
    the Body evaluates every thunk it reaches, so a goal thunk would run its
    side effect on every clause/2 call and leave its RETURN VALUE (``None``)
    where the goal was.  Goal positions: an element of the body, the
    operands of a conjunction / ``or`` / ``not`` / ``if_``, and the goal
    arguments of a call (``_goal_positions``)."""
    from clausal.terms import PyThunk  # noqa: PLC0415

    def walk(g):
        if isinstance(g, PyThunk):
            return g
        if type(g) is nodes.TupleLiteral:
            subs = g.elements
        elif type(g) in (nodes.And, nodes.Or):
            subs = (g.left, g.right)
        elif type(g) is nodes.Not:
            subs = (g.operand,)
        elif type(g) is nodes.IfExpr:
            subs = (g.test, g.body, g.orelse)
        elif type(g) is nodes.Call and type(g.func) is nodes.LoadName:
            idx = _goal_positions(g.func.name, len(g.args), db)
            subs = [g.args[i] for i in idx if i < len(g.args)]
        else:
            return None
        for sub in subs:
            hit = walk(sub)
            if hit is not None:
                return hit
        return None

    for g in goals:
        hit = walk(g)
        if hit is not None:
            return hit
    return None


def _no_term_form(goals: list, db=None) -> "str | None":
    """Why *goals* cannot be built as terms without running Python, or
    ``None``: a thunk in goal position, or one that reads clause
    variables."""
    hit = _goal_thunk(goals, db)
    if hit is not None:
        return (f"its body runs the Python expression {hit!r} as a goal, "
                f"which is code, not a term")
    hit = _capturing_thunk(goals)
    if hit is not None:
        return (f"it holds the Python expression {hit!r}, which reads the "
                f"clause's variables and so is not a term")
    return None


def _as_goal(goals: list) -> Any:
    """The goal list as ONE goal node: ``True`` for none, the goal for one,
    the conjunction ``TupleLiteral`` for more."""
    if not goals or goals == [True]:
        return True
    if len(goals) == 1:
        return goals[0]
    return nodes.TupleLiteral(elements=list(goals))


class _Built:
    """A compiled construction over one clause's own variables.

    ``direct``: ``(Var, value)`` pairs bound straight onto the private trail
    -- a hoisted ``Unify`` whose argument is plain data needs no compile.
    ``fn``/``params``: the query that runs the rest (``None`` when nothing
    is left): the non-plain hoisted goals, then ``Out = <body remainder>``.
    ``out``: the Body -- ``Out``, ``True``, or ``None`` for a HEAD-only
    construction.  ``why``: ``None``, or why the body cannot be a term.
    """

    __slots__ = ("direct", "fn", "params", "out", "why")

    def __init__(self, direct, fn, params, out, why):
        self.direct, self.fn, self.params = direct, fn, params
        self.out, self.why = out, why


def _compile(goals: list, home_db):
    from clausal.logic.solve import _compile_as_query  # noqa: PLC0415
    from clausal.logic.builtins.call_body import _module_for  # noqa: PLC0415
    if not goals:
        return None, ()
    fn, params = _compile_as_query(_as_goal(goals), _module_for(home_db))
    return fn, tuple(params)


# What building a goal the construction cannot express raises: a name with
# no term class (``NameError``), an object that cannot be called to build one
# (``TypeError``), a node term position refuses (``NotImplementedError``,
# ``SyntaxError`` -- a lambda argument, say).
_BUILD_ERRORS = (NameError, TypeError, NotImplementedError, SyntaxError)

_PLAIN = (int, float, str, bool, bytes, type(None))


def _plain(v: Any) -> bool:
    """Data that is its own term: an atomic value, or a list / tuple of
    them.  Anything else -- a ``Call`` node, a ``PyThunk``, a Var -- goes
    through the compiled construction."""
    if type(v) in _PLAIN:
        return True
    if type(v) in (list, tuple):
        return all(_plain(e) for e in v)
    return False


def _split_lead(lead: list) -> tuple:
    """``(direct, rest)``: the leading hoisted ``Unify(V, plain)`` goals as
    pairs, and the goals from the first one that is not."""
    from clausal.terms import Unify  # noqa: PLC0415
    direct = []
    for i, g in enumerate(lead):
        if type(g) is Unify and is_var(g.left) and _plain(g.right):
            direct.append((g.left, g.right))
        else:
            return tuple(direct), list(lead[i:])
    return tuple(direct), []


# id(clause) -> (weakref to it, {"head": _Built, "full": _Built}).  Kept OFF
# the Clause, so a stored clause never carries a compiled function (nothing
# that copies or pickles one has to know about it); the weakref drops the
# entry with the clause.
_BUILT_CACHE: dict = {}


def _cache_for(clause) -> dict:
    key = id(clause)
    entry = _BUILT_CACHE.get(key)
    if entry is not None and entry[0]() is clause:
        return entry[1]
    slot: dict = {}
    _BUILT_CACHE[key] = (
        weakref.ref(clause, lambda _r, k=key: _BUILT_CACHE.pop(k, None)), slot)
    return slot


def _head_built(clause, home_db) -> _Built:
    """The HEAD-only construction: ``body[:hoisted]`` alone -- for a fact
    table, just the direct pairs, no compile at all.  When the hoisted
    arguments cannot be built (a thunk reading clause variables, a build
    error) it builds NOTHING and carries *why*: ``head_matches`` then
    matches the stored head as it is, hoisted positions still fresh
    variables, and the caller refuses the clause if that matches."""
    slot = _cache_for(clause)
    built = slot.get("head")
    if built is None:
        lead = list(clause.body[:clause.hoisted])
        why = _no_term_form(lead, home_db)
        if why is None:
            direct, rest = _split_lead(lead)
            try:
                fn, params = _compile(rest, home_db)
            except _BUILD_ERRORS as exc:
                why = f"its head cannot be built as a term ({exc})"
            else:
                built = _Built(direct, fn, params, None, None)
        if built is None:
            built = _Built((), None, (), None, why)
        slot["head"] = built
    return built


def _head_failed(clause, home_db, exc) -> _Built:
    """Record that the head-only construction raised at RUN time."""
    built = _Built((), None, (), None,
                   f"its head cannot be built as a term ({exc})")
    _cache_for(clause)["head"] = built
    return built


def _full_built(clause, home_db, why: "str | None" = None) -> _Built:
    """The construction of ``(Head, Body)``, compiled once and cached: it
    mentions only the clause's OWN variables, which never change, so one
    compile serves every later ``clause/2`` call.  When the body has no term
    form this is the head-only construction with *why* set; *why* forces
    that (after the full one failed at run time)."""
    slot = _cache_for(clause)
    cached = slot.get("full")
    if cached is not None and (why is None or cached.why is not None):
        return cached
    from clausal.terms import Unify  # noqa: PLC0415
    rest = list(clause.body[clause.hoisted:])
    head = _head_built(clause, home_db)
    if why is None:
        why = head.why or _no_term_form(rest, home_db)
    built = None
    if why is None:
        namespace = getattr(home_db, "module_dict", None) or {}
        body = _as_goal([_spell_as_cells(g, namespace, home_db) for g in rest])
        if body is True:
            built = _Built(head.direct, head.fn, head.params, True, None)
        else:
            _, lead = _split_lead(list(clause.body[:clause.hoisted]))
            out = Var()
            try:
                fn, params = _compile(
                    lead + [Unify(left=out, right=body)], home_db)
            except _BUILD_ERRORS as exc:
                why = f"its body cannot be built as a term ({exc})"
            else:
                built = _Built(head.direct, fn, params, out, None)
    if built is None:
        built = _Built(head.direct, head.fn, head.params, None, why)
    slot["full"] = built
    return built


class _ConstructionFailed(Exception):
    """The construction query had no solution -- it only binds fresh
    variables, so this is an engine defect, reported like a build error."""


class _BuildFailed(Exception):
    """The CONSTRUCTION itself raised one of ``_BUILD_ERRORS`` (or had no
    solution): a fact about the clause, which the caller may cache.  Nothing
    else is wrapped -- an exception from the ``then`` callback (which unifies
    with the CALLER's term) or any other error propagates as it is, uncached,
    so a transient failure does not make a clause uninspectable for good."""

    def __init__(self, exc):
        super().__init__(str(exc))
        self.exc = exc


_NO_SOLUTION = object()


def _on_private_trail(built: _Built, then):
    """Run *built* on a private trail, call ``then(tmp)`` with its bindings
    in place, undo, and return what *then* returned.

    The construction binds the STORED clause's variables, so nothing else
    may see them bound -- a meta-interpreter calls clause/2 again, on the
    same clause, while an answer is live.  The drive is CLOSED before the
    trail is undone, so no suspended frame outlives the bindings it ran on.
    A build error from the construction comes out as ``_BuildFailed``."""
    from clausal.logic.solve import _drive_trampoline  # noqa: PLC0415
    tmp = Trail()
    mark = tmp.mark()
    gen = None
    try:
        try:
            for v, value in built.direct:
                unify(v, value, tmp)          # a fresh head Var: binds
            if built.fn is not None:
                for pv, value in built.params:
                    unify(pv, value, tmp)
                gen = _drive_trampoline(built.fn, tmp)
                if next(gen, _NO_SOLUTION) is _NO_SOLUTION:
                    raise _ConstructionFailed(
                        "the construction query has no solution")
        except (*_BUILD_ERRORS, _ConstructionFailed) as exc:
            raise _BuildFailed(exc) from exc
        return then(tmp)
    finally:
        if gen is not None:
            gen.close()
        tmp.undo(mark)


class OpenConjunction:
    """A body pattern ``(G1, ..., Gk, Rest)`` whose tail Rest is unbound:
    it matches a stored flat body of MORE than k goals, Rest taking the
    remaining goals (one goal as itself, several as the flat tuple)."""
    __slots__ = ("prefix", "tail")

    def __init__(self, prefix, tail):
        self.prefix = prefix
        self.tail = tail


def engine_body_pattern(t):
    """A body PATTERN as Prolog source spells it, in the shape clause_terms
    builds a body: the atom ``true`` is True, ``\\+ G`` the Not node, a
    right-nested ``','``/2 cell chain the flat tuple of its goals (as the
    compiler flattens a body) -- an :class:`OpenConjunction` when its tail
    is unbound -- and a ``';'``/2 cell the Or node.  So
    ``clause(g(X), (X = 1, X > 0))`` finds ``g(X) :- X = 1, X > 0``; it
    found nothing (the cell never unified with the tuple).  Known residue:
    the compiler's flat body has lost a clause's own grouping, so a body
    written ``A, (B, C)`` matches the pattern ``(A, B, C)`` (Scryer: no),
    and a left-nested pattern ``((A, B), C)`` matches nothing.  Match with
    :func:`unify_body`."""
    t = deref(t)
    if type(t) is str and t == "true":
        return True
    if type(t) is tuple and len(t) == 2 and t[0] == "\\+":
        return nodes.Not(operand=engine_body_pattern(t[1]))
    if type(t) is not tuple or len(t) != 3 or type(t[0]) is not str:
        return t
    if t[0] == ";":
        return nodes.Or(left=engine_body_pattern(t[1]),
                        right=engine_body_pattern(t[2]))
    if t[0] != ",":
        return t
    goals = []
    x = t
    while type(x) is tuple and len(x) == 3 and x[0] == ",":
        left = deref(x[1])
        if type(left) is tuple and len(left) == 3 and left[0] == ",":
            # ((A, B), C): the clause as written had that grouping, which
            # the compiler's flat body no longer shows -- no match
            return t
        goals.append(engine_body_pattern(left))
        x = deref(x[2])
    if is_var(x):
        return OpenConjunction(tuple(goals), x)
    goals.append(engine_body_pattern(x))
    return tuple(goals)


def unify_body(pattern, body, trail) -> bool:
    """Unify an :func:`engine_body_pattern` result with a stored body."""
    if type(pattern) is not OpenConjunction:
        return unify(pattern, body, trail)
    body = deref(body)
    k = len(pattern.prefix)
    if type(body) is not tuple or len(body) <= k:
        return False
    for p, g in zip(pattern.prefix, body):
        if not unify(p, g, trail):
            return False
    rest = body[k:]
    return unify(pattern.tail, rest[0] if len(rest) == 1 else rest, trail)


def head_matches(clause, home_db, cell) -> "tuple[bool, str | None]":
    """``(matched, why)``: whether *clause*'s head, hoisted arguments put
    back, unifies with the query head *cell* -- decided on the private
    trail, with nothing copied and the body not built.  The filter that
    keeps ``clause(p(1), B)`` on a large table from building every clause.

    *why* is set when the hoisted arguments cannot be built: *matched* then
    says whether the stored head with those positions left as fresh
    variables unifies -- the clause MAY be the one asked about, and the
    caller refuses it rather than answer with a wrong head."""
    head = _as_cell(clause.head)
    built = _head_built(clause, home_db)
    try:
        matched = _on_private_trail(built, lambda tmp: bool(unify(cell, head, tmp)))
    except _BuildFailed as failed:
        built = _head_failed(clause, home_db, failed.exc)
        matched = _on_private_trail(built, lambda tmp: bool(unify(cell, head, tmp)))
    return matched, built.why


def clause_terms(clause, home_db) -> tuple:
    """``(Head, Body, why)`` for *clause*: the head with its hoisted
    arguments put back and the body remainder as a term, both a FRESH
    renaming.  When the body cannot be a term, Body is ``None`` and *why*
    says so."""
    from clausal.logic.builtins.inspection import _copy_term  # noqa: PLC0415
    head = _as_cell(clause.head)
    built = _full_built(clause, home_db)
    if built.why is None:
        try:
            h, b = _on_private_trail(
                built, lambda tmp: _copy_term((head, built.out), {}))
            return h, b, None
        except _BuildFailed as failed:
            built = _full_built(
                clause, home_db,
                why=f"its body cannot be built as a term ({failed.exc})")
    return None, None, built.why


# ── Head resolution ─────────────────────────────────────────────────────────


def _resolve(db, head):
    """The row whose clauses *head* reads, as ``(row, cell_head)``; ``None``
    for an unknown procedure (fails).  Raises for everything ISO refuses."""
    from clausal.logic.builtins.call_body import _construct, is_body_term  # noqa: PLC0415
    from clausal.logic.builtins.higher_order import _calling_module  # noqa: PLC0415
    from clausal.logic.builtins.io import _indicator_row  # noqa: PLC0415

    head = qualify_mangled_goal(head, db)
    ok, functor = compound_cell_shape(head)
    if ok and functor == QUALIFIED_GOAL_FUNCTOR and len(head) == 3:
        module, inner = resolve_qualified_goal_cell(
            head, _CONTEXT, _calling_module(db))
        inner = deref(inner)
        if is_var(inner):
            raise LogicException(instantiation_error(
                f"{_CONTEXT}: the head of M:Head is unbound"))
        _type_check(inner, "head")
        return _resolve(module.db, inner)
    if is_body_term(head):
        name, arity = _construct(head)
        raise _private(name, arity, "is a control construct")
    if isinstance(head, _BuiltinTerm):
        head = head._functor           # its class's __name__ before slice 3
    if type(head) is str:
        name, arity, cell = head, 0, head
    elif compound_cell_shape(head)[0]:
        name, arity, cell = head[0], len(head) - 1, head
    elif is_term_instance(head):
        cell = _as_cell(head)
        name, arity = (cell, 0) if type(cell) is str else (cell[0], len(cell) - 1)
    else:
        return None          # [] or "": the atom '[]', which nothing defines
    if name in CELL_GOAL_CONTROL_FUNCTORS or (
            arity == 0 and name in _ZERO_ARITY_CONTROL):
        raise _private(name, arity, "is a control construct")
    row = _indicator_row(db, name, arity, None) if db is not None else None
    if row is not None:
        if row.dynamic or not row.locked:
            return row, cell
        raise _private(name, arity, "is a static procedure")
    if (name, arity) in SPECIAL_FORMS:
        raise _private(name, arity, "is a control construct")
    if (name, arity) in _BUILTINS or (name, arity) in _DB_BUILTINS:
        raise _private(name, arity, "is a builtin predicate")
    return None


@_db_builtin("clause", 2, fields=("head", "body"))
def _clause_factory(db):
    """clause(Head, Body) — ISO 8.8.1; see the module docstring."""

    def clause__2(head, body, trail, k):
        h = deref(head)
        if is_var(h):
            raise LogicException(instantiation_error(
                f"{_CONTEXT}: the head is unbound"))
        _type_check(h, "head")
        b = deref(body)
        if not is_var(b):
            _type_check(b, "body")
            # the Prolog spelling of a body (the atom ``true``, ``','``/2
            # and ``';'``/2 cells) as the engine's body term
            body = engine_body_pattern(b)
        resolved = _resolve(db, h)
        if resolved is None:
            return
        row, cell = resolved
        home = row.db
        # The logical update view (ISO 7.5.4): the clauses as they are NOW;
        # an assertz/retract made while this iterates changes nothing here.
        for clause in list(row.clauses):
            # Head first, cheaply: the body is built only for a clause the
            # query selects.
            matched, why = head_matches(clause, home, cell)
            if not matched:
                continue
            if why is not None:
                name, arity = row.key
                raise _private(name, arity, (
                    f"has a clause with no term form -- {why}"))
            c_head, c_body, why = clause_terms(clause, home)
            if why is not None:
                name, arity = row.key
                raise _private(name, arity, (
                    f"has a clause whose body has no term form -- {why}"))
            mark = trail.mark()
            if unify(cell, c_head, trail) and unify_body(body, c_body, trail):
                yield None
            trail.undo(mark)

    return clause__2
