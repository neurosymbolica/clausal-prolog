"""Higher-order builtins: call_goal/1..8, call/1..8, maplist/2,3,
include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4,
take_while/3, drop_while/3, span/4, group_by/3, sort_by/3,
max_by/3, min_by/3, filter_map/3."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.atoms import demangle, is_mangled
from clausal.logic.exceptions import (
    LogicException, existence_error, instantiation_error, string_goal_error,
    type_error,
)
from clausal.terms import Compound
from clausal.logic.meta_predicate import is_goal_object as _is_goal_object
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.builtins.lists import _as_items, _seq_result, _was_string
from clausal.logic.builtins._helpers import _is_empty_list, _standard_order_key
from clausal.logic.predicate import (
    _refuse_unqualified_other_arity,
    is_declared_predicate_name, localize_goal, localize_owner_functor,
)

from clausal.logic.cells import (
    is_chars, chars_text,   # stage 1: the chars carrier
    CELL_GOAL_CONTROL_FUNCTORS,
    QUALIFIED_GOAL_FUNCTOR,
    compound_cell_shape,
    refuse_control_construct_cell,
    resolve_qualified_goal_cell,
    qualify_mangled_goal,
)

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _ensure_trampoline_dispatch,
    _DB_BUILTINS, _BUILTIN_FIELDS,
)


# ── call_goal/1,2,3 — invoke a goal closure (V2-9 lambdas) ──────────────────


def _control_succeed_once(this_generator, _proceed, _fail, _catcher, trail):
    """Trampoline dispatch for ``true/0`` (and ``!/0``) reached by NAME.

    Final review I-3.  ``true`` is lowered at COMPILE time, so it has no row
    and no registry entry, and a name that resolves to nothing fails silently
    — which meant ``call("true")`` yielded zero solutions.  One solution, no
    choice point: exactly what the lowered form does.
    """
    yield (_proceed, None)
    yield (_fail, DONE)


def _control_fail(this_generator, _proceed, _fail, _catcher, trail):
    """Trampoline dispatch for ``fail/0`` and ``false/0`` reached by NAME."""
    yield (_fail, DONE)


# The zero-arity control constructs, which the compiler lowers and therefore
# never registers as predicates, mapped to the dispatch that reproduces the
# lowered behaviour when they are reached by NAME instead (final review I-3).
#
# ``!`` succeeds once and cuts NOTHING: ISO 7.8.3 makes a cut inside ``call/1``
# local to that call, so the barrier is the call itself and there is nothing
# left inside it to cut.  ``call("!")`` is therefore ``call("true")`` — opaque,
# not a no-op that silently changes the caller's choice points.
_ZERO_ARITY_CONTROL_GOALS = {
    "true": _control_succeed_once,
    "!": _control_succeed_once,
    "fail": _control_fail,
    "false": _control_fail,
}


def _raise_if_unloaded_handle(functor, arity, context):
    """Ruling 2 (2026-09-24): a MANGLED *functor* that ``qualify_mangled_goal``
    left unconverted is a handle whose module half is not a loaded Clausal
    module.  ``solve`` raises for it, so ``call/N`` does too, with the same
    term (``solve.dangling_handle_exception``).  Called only once nothing in
    the calling db can answer to the spelling -- see the two call sites."""
    if is_mangled(functor):
        from clausal.logic.solve import dangling_handle_exception  # noqa: PLC0415
        mod_name, name = demangle(functor)
        raise dangling_handle_exception(mod_name, name, arity, False, context)


def _resolve_named_goal(db, goal_val, extra_args, context):
    """Resolve a goal named by a CELL or a bare ATOM to ``(dispatch, args)``.

    P3-3 Task 5 (R11).  ``call_goal``'s pre-existing route is a goal OBJECT —
    a predicate class, a lambda closure, anything answering ``_get_dispatch``.
    A cell ``("p", A)`` and a bare atom ``"p"`` are neither: they NAME a
    predicate, so the name has to be looked up, and the only correct place to
    look it up is the CALLING module (which is why the call/N family became
    db-receiving — see ``_make_call_goal_factory``).  Two lookups, in the order
    ``solve`` uses: the db's own dispatch table (which also covers the builtin
    registry), then the module NAMESPACE — see ``_namespace_dispatch``.

    ISO argument folding: ``call(f(A), B)`` is the goal ``f(A, B)``, so the
    cell's own arguments come first and call/N's extras follow; a bare atom
    contributes none, giving ``call(p, X)`` → ``p/1``.  Everything after the
    fold is decided on the FOLDED goal, so the cell spelling and the atom
    spelling of one goal — ``call((":", M, G))`` and ``call(":", M, G)``,
    ``call((",", A, B))`` and ``call(",", A, B)`` — behave identically
    (P3-3 Task 5 fix round 1, F4).

    A module-QUALIFIED folded goal ``(":", M, G, ...)`` is resolved rather than
    looked up (P3-3 Task 6, replacing Task 5's stub): *M* names the module
    whose database answers, so the whole resolution restarts against THAT db —
    dispatch table first, then that module's namespace — and the calling db is
    not consulted at all.  That is the module-locality rule: an exporter's
    ``p/1`` answers a qualified call even when the caller defines its own.

    The fold puts ``call/N``'s extras AFTER ``M`` and ``G``, so on this path a
    folded ``:``/N for any N ≥ 2 is "M:G with N-2 extras still to fold": slots
    1 and 2 are the qualification and everything past them belongs to the
    INNER goal, giving ``call(M:p, X)`` → ``M:p(X)`` and ``call(M:pair(11), B)``
    → ``M:pair(11, B)`` (SWI's ``call(M:G, X) ≡ M:call(G, X)``).  That is
    narrower than it looks: ``:``/N≥3 is the qualified form HERE and nowhere
    else — on the lowering paths (``solve._term_to_goal``,
    ``solve._templatize_query_goal``) only ``:``/2 is, because no fold has run
    there and ``(":", A, B, C)`` written as a goal really is a ``:``/3 call.
    What Task 5 fix round 1 F5 pinned — that the two LOWERING guards agree —
    is untouched; what F4 pinned — that everything after the fold is decided
    on the folded goal, so ``call((":", M, G), X)`` and ``call(":", M, G, X)``
    behave identically — is what makes this arm arity-general rather than
    ``== 2``.

    Returns ``None`` — which the caller turns into a silent failure — only
    when the goal is not a cell or atom, or when no db was threaded (nothing
    to resolve a name against).

    A name that resolves to NO procedure RAISES ISO
    ``existence_error(procedure, Name/Arity)``, catchable -- operator ruling
    2 (2026-09-25, "like Scryer"), retiring the translator session's §4.2
    "a non-callable goal fails" contract for this case; ``call(M:nosuch(X))``
    with a resolvable M raises too.  A name the calling module binds to a
    predicate at another arity only raises the same ISO term as
    ``PredicateArityMismatchError`` -- the refusal a body call at that arity
    gets (``_refuse_unqualified_other_arity``; ruling Q3, 2026-09-25).
    Every caller of this resolver inherits both raises: call/N, phrase/2,3,
    time_goal/1 and every goal-first list builtin through ``_NamedGoal`` --
    pinned per builtin in
    ``tests/test_bare_predicate_name_in_source_is_the_plain_atom.py``.

    A resolved procedure declared ``-meta_predicate`` gets its meta-argument
    positions qualified with the resolving module (``_meta_qualified``).

    The one exception is a MANGLED predicate handle (ruling 2, 2026-09-24):
    it is not a name the caller wrote but a reference that was supposed to
    resolve, so a dangling one -- module never loaded, or loaded without the
    predicate -- RAISES ``existence_error(procedure, Name/Arity)``, the very
    term ``solve`` raises for it (``solve.dangling_handle_exception``).  A
    handle that resolves and has no solutions still just fails.

    Raises for an unresolvable module designator (P3-3 Task 6) and for the
    n-ary control constructs (deferred to the ISO-surface phase).  Both raise
    even when *db* is None, so the diagnostic never depends on how the builtin
    was reached.  The ZERO-arity constructs ``true``/``fail``/``false``/``!``
    are answered instead of refused, also independently of *db* — see
    ``_ZERO_ARITY_CONTROL_GOALS``.
    """
    is_cell, functor = compound_cell_shape(goal_val)
    if is_cell:
        goal_args = list(goal_val[1:])
    elif _is_empty_list(goal_val):
        # The EMPTY LIST in goal position, in any spelling (fix round 2,
        # item 4): ``call("")`` raised while ``call([])`` failed silently,
        # for one and the same term.  Both raise now -- ``[]`` is the atom
        # ``'[]'``, which is callable and names no procedure, so it is
        # ``existence_error(procedure, '[]'/N)``, exactly what Scryer
        # answers for ``call([])``.
        raise LogicException(string_goal_error("", len(extra_args), "call/N"))
    elif type(goal_val) is str:
        functor, goal_args = goal_val, []   # STAGE 2: an atom is the 0-arity goal of its name
    elif is_chars(goal_val):
        # THE FLIP (spec §6.4): a ``str`` is a STRING, so ``call("foo")`` is
        # not a call to ``foo/0``.  Task 15 item 3 (ISO alignment): the
        # string IS the compound ``'.'/2`` and so IS callable — what is
        # missing is the PROCEDURE, so this is an existence_error, matching
        # Scryer's ``call("foo", X)``.  It is raised rather than failed
        # silently (the treatment a non-callable goal otherwise gets) because
        # a string here is always a mistake about representation, and a
        # silent failure is exactly how that mistake stays invisible.
        raise LogicException(
            string_goal_error(chars_text(goal_val), len(extra_args), "call/N"))
    else:
        return None
    call_args = [deref(a) for a in goal_args] + [deref(a) for a in extra_args]
    # The goal as the fold leaves it — the term both special routes below are
    # decided on (F4), and the culprit the control-construct refusal names.
    folded = ((functor,) + tuple(call_args)) if call_args else functor   # STAGE 2: a 0-arity atom goal is the atom, never the reserved 1-tuple
    # W4: a MANGLED functor (the module-qualified handle) is the qualified
    # goal ``M:G`` spelled inside one atom.  Normalise and re-enter: the
    # ``:``/2 arm below resolves it exactly as it resolves an explicit one.
    _q = qualify_mangled_goal(folded, db=db)   # Q0: the calling db is the hint
    if _q is not folded:
        # Ruling 2 (2026-09-24): a handle whose module LOADED but which names
        # no predicate there RAISES, with the term ``solve`` raises -- the
        # same check ``solve``'s normalisation makes, called the same way,
        # so the two entry points cannot disagree on when or what.  A handle
        # that resolves falls through and, like any goal, may simply fail.
        # *functor* is the handle as the caller held it: slot 0 of a cell
        # goal, or the bare atom itself for an arity-0 ``call(H)``.
        from clausal.logic.solve import raise_if_dangling_handle  # noqa: PLC0415
        raise_if_dangling_handle(functor, _q, context)
        # -meta_predicate (operator ruling 2026-09-25): a handle the CALLING
        # module binds by a plain name (an import) is that module's own
        # unqualified reference -- in the handle era a cell built through an
        # import (``apply_all(my_pred)``) carries the owner's handle in slot
        # 0.  Its meta-arguments belong to the caller, as the class era's
        # plain functor gives; qualify them here, before the re-entry would
        # qualify them with the OWNER (the rule for a written ``M:G``).
        if call_args and type(functor) is str:
            _local = localize_goal(db, functor)
            _lname = getattr(_local, "name", None)
            if _local is not functor and type(_lname) is str:
                _qa = _meta_qualified(db, _lname, len(call_args), call_args)
                if _qa is not call_args:
                    _q = qualify_mangled_goal((functor, *_qa), db=db)
        return _resolve_named_goal(db, _q, (), context)
    if functor == QUALIFIED_GOAL_FUNCTOR and len(call_args) >= 2:
        # Slots 1 and 2 are the qualification; everything past them is an
        # extra the fold has not placed yet, and it belongs to the INNER goal.
        target, inner = resolve_qualified_goal_cell(
            (QUALIFIED_GOAL_FUNCTOR, call_args[0], call_args[1]),
            context, _calling_module(db))
        # One level only: the resolver unwraps nesting itself, so ``inner`` is
        # never another ``:``/2 and this recursion cannot repeat.  It restarts
        # the WHOLE resolution — the control-construct refusal included, so
        # ``call(M:(A, B))`` is refused exactly like ``call((A, B))`` — with
        # the leftover extras handed on to fold onto the inner goal there.
        inner_v = deref(inner)
        if _is_goal_object(inner_v):
            # ``M:G`` whose G is a goal OBJECT -- a predicate class, a lambda
            # closure, anything answering ``_get_dispatch`` -- not a name:
            # it resolves itself, so M has nothing to add.  This arm used to
            # hand it to the NAME resolver below, which answers None for a
            # non-name: a SILENT failure (a dotted ``m.p`` reference in data
            # position is p's class in the class era).
            extras = [deref(a) for a in call_args[2:]]
            return (_ensure_trampoline_dispatch(inner_v, len(extras), target.db),
                    extras)
        if is_var(inner_v):
            raise LogicException(instantiation_error(context))
        if not (type(inner_v) is str or compound_cell_shape(inner_v)[0]
                or _is_empty_list(inner_v) or is_chars(inner_v)):
            # ``M:X`` with X neither a name nor a goal object (a number, a
            # unit Quantity, ...): ISO type_error(callable, X) -- Scryer's
            # answer for ``call(lists:5)`` (verified on the box; M:_ is an
            # instantiation_error there too).  The name resolver below would
            # answer None -- a SILENT failure.
            raise LogicException(type_error("callable", inner_v, context))
        return _resolve_named_goal(
            target.db, inner, tuple(call_args[2:]), context)
    # No arity condition (F3): ``call((",",))`` is as much a control construct
    # in goal position as ``call((",", A, B))``, and it used to fail silently
    # here while ``solve((",",), m)`` raised.
    if functor in CELL_GOAL_CONTROL_FUNCTORS:
        refuse_control_construct_cell(folded, functor, context)
    if not call_args and functor in _ZERO_ARITY_CONTROL_GOALS:
        # SUPPORTED, not refused (final review I-3).  Unlike ``,``/``;``/``->``
        # these need no goal-tree interpreter: ``true`` succeeds once, ``fail``
        # and ``false`` fail, and ``!`` inside ``call/1`` is ISO-local to the
        # call, so it is ``true`` here.  Decided BEFORE the db lookups and
        # before the ``db is None`` bail, because these four are lowered
        # constructs rather than predicates — no database defines them, so no
        # database can answer for them, and a goal that is definitionally true
        # failing silently is the worst failure mode this engine has.
        # ``not call_args`` keeps it to arity 0: ``call("true", X)`` is the
        # ordinary (undefined) goal ``true/1``, as ISO has it.
        return _ZERO_ARITY_CONTROL_GOALS[functor], call_args
    arity = len(call_args)
    if db is None:
        # No db, so nothing can answer to a ``-hide`` spelling: a mangled
        # functor here is a dangling handle, decided now rather than failed.
        _raise_if_unloaded_handle(functor, arity, context)
        return None
    # A cell built through an ALIASED import carries the OWNER's functor
    # (``dd(N, M)`` is ``("dec", N, M)``); at an arity the alias IMPORTED it
    # resolves under the alias here.  Every other arity takes the normal
    # lookup below (round 6 decision) -- see ``predicate.localize_owner_functor``.
    aliased = localize_owner_functor(db, functor, arity)
    if aliased is not None:
        # *functor* is the OWNER's spelling; the adopted row -- and so the
        # owner's -meta_predicate declaration -- is keyed by the LOCAL alias,
        # which the adapter carries.
        return aliased.dispatch_at(arity), _meta_qualified(
            db, aliased.name, arity, call_args)
    dispatch = db.get_dispatch(functor, arity)
    if dispatch is None:
        dispatch = _namespace_dispatch(db, functor, arity)
    if dispatch is None:
        # Only AFTER the lookups: a ``-hide`` atom carries its bare declared
        # module name, and the calling db may define it under that spelling.
        _raise_if_unloaded_handle(functor, arity, context)
        # Nothing answers at this arity, but the calling module binds the
        # NAME to a predicate at another: the refusal a body call
        # ``citation(x)`` gets (name+arity ruling, 2026-09-24: "keep the
        # refusal where nothing else answers").  Needed since ruling S made
        # ``maplist(citation, L)`` pass the ATOM rather than the binding,
        # which ``_dispatch_at`` used to refuse the same way.
        module_dict = getattr(db, "module_dict", None)
        binding = (module_dict.get(functor)
                   if isinstance(module_dict, dict) else None)
        if binding is not None and is_declared_predicate_name(binding, db=db):
            return _refuse_unqualified_other_arity(
                binding, functor, arity, db), call_args
        # Ruling 2 (operator, 2026-09-25, "like Scryer"): a meta-call naming
        # an UNKNOWN procedure raises ISO existence_error(procedure, N/A) --
        # catchable -- where it used to fail silently (the old §4.2
        # "a non-callable goal fails" contract, retired for this case).
        _where = getattr(_calling_module(db), "name", None)
        raise LogicException(existence_error(
            "procedure", Compound("/", (functor, arity)),
            f"{context}: no procedure {functor}/{arity} is defined in "
            + (f"module {_where}" if _where else "the calling module")))
    return dispatch, _meta_qualified(db, functor, arity, call_args)


def _meta_qualified(db, functor, arity, call_args):
    """*call_args* with the ``-meta_predicate`` positions of the procedure
    ``functor/arity`` (as *db* means it) qualified with *db*'s module --
    Scryer's ``expand_call_goal``.  A qualified goal ``M:G`` reaches here
    with ``db`` = M's database, so G's meta-arguments are qualified with
    M, as Scryer does.  Builtins carry no declaration and are untouched
    (ruling 2A: they resolve in the module of the clause that calls them)."""
    specs = db.meta_predicate_specs(functor, arity)
    if not specs:
        return call_args
    from clausal.logic.meta_predicate import qualify_args  # noqa: PLC0415
    return qualify_args(specs, list(call_args), db)


def _calling_module(db):
    """The :class:`Module` whose database is *db*, when it can be named.

    P3-3 Task 6.  Only the diagnostic needs it (``resolve_module`` reports the
    module that asked), and there is no back-pointer from a ``Database`` to
    its ``Module`` — but the import hook binds the module object into the
    module dict under ``$module``, which is the same handle the test suite and
    the transformed source both use.  ``None`` for a db built without one.
    """
    module_dict = getattr(db, "module_dict", None)
    if module_dict is None:
        return None
    return module_dict.get("$module")


def _namespace_dispatch(db, functor, arity):
    """Second lookup for a named goal: the calling module's NAMESPACE.

    P3-3 Task 5 fix round 1 (F2).  ``db.get_dispatch`` reads the db's own
    dispatch table and falls back to the builtin registry — it does NOT read
    the module dict, and an ``-import_from``'d predicate lives on the OWNER's
    row, reachable from here only through the class the import bound into this
    module's namespace.  So ``solve(("lp", Z), importer)`` answered while
    ``call(("lp", Z))`` from the same module failed silently, for the same
    goal.

    Resolved the way ``database_ops`` resolves an assert's target, reusing its
    two helpers rather than growing a second copy of the rule:
    ``_find_pred_cls`` (arity-checked, so a name bound at another arity does
    not answer) then ``_home_db``, which is the row a shared class actually
    reads.  The row is keyed on the CLASS's name, not on the local spelling —
    an ``-import_from`` alias binds the exporter's class under a different
    name — so the home lookup uses the predicate's own name
    (``_canonical_functor``, era-agnostic).

    Returns ``None`` (→ silent failure, unchanged) when the name is not in the
    namespace at that arity.
    """
    from clausal.logic.builtins.database_ops import (  # noqa: PLC0415
        _canonical_functor, _find_pred_cls, _home_db,
    )
    module_dict = getattr(db, "module_dict", None)
    if module_dict is None:
        return None
    pred_cls = _find_pred_cls(functor, arity, module_dict)
    if pred_cls is None:
        return None
    home = _home_db(db, pred_cls, functor, arity)
    canonical = _canonical_functor(db, pred_cls, functor)
    if home is db and canonical == functor:
        return None  # the lookup that already came back empty
    return home.get_dispatch(canonical, arity)


def _make_call_goal_factory(extra_n: int):
    """Generate the db-receiving call_goal factory for *extra_n* extra args.

    DB-RECEIVING as of P3-3 Task 5: the product is still a native
    trampoline-protocol function of exactly the same arity and shape, but it is
    now built per-database so a cell/atom goal can be resolved against the
    caller's namespace.  Registered straight into ``_DB_BUILTINS`` (whose
    contract is ``fn(db) -> trampoline dispatch fn``) rather than through the
    ``@_db_builtin`` decorator, because that decorator wraps its product with
    ``_simple_to_trampoline`` and call_goal is already trampoline-native.

    ``_db_optional`` marks the factory as tolerating ``db=None`` — it then
    behaves exactly as the pre-Task-5 stateless builtin did, minus the name
    resolution it has no database to do.  ``_registry._stateless_dispatch``
    reads that flag on the paths that have no db to offer (the builtin CLASS
    table, and a ``BuiltinPredicate`` built without one).
    """
    def factory(db):
        def _call_goal_n(this_generator, _proceed, _fail, _catcher, *args):
            # args = (goal, extra1, ..., extraN, trail)
            goal_val = deref(args[0])
            trail = args[extra_n + 1]
            dispatch = None
            # Operator ruling 2026-09-24: an imported predicate reached
            # through an unqualified name -- its class, or (after the flip)
            # the owner HANDLE an import binds -- resolves under that name
            # in the calling module, not in the owner.  A handle the calling
            # module does not bind by a plain name keeps the qualified route
            # through ``_resolve_named_goal`` below.
            localized = localize_goal(db, goal_val)
            if localized is not goal_val:
                dispatch = _ensure_trampoline_dispatch(localized, extra_n)
                call_args = [deref(a) for a in args[1:extra_n + 1]]
                # An imported name reached through its binding (a dotted
                # import reference in data position stays the binding): the
                # -meta_predicate positions are qualified under that name
                # here, as the atom route does (operator ruling 2026-09-25).
                _name = getattr(localized, "name", None)
                if type(_name) is str:
                    call_args = _meta_qualified(db, _name, extra_n, call_args)
            elif callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
                # extra_n is exactly what the goal will be called with.
                dispatch = _ensure_trampoline_dispatch(goal_val, extra_n)
                call_args = [deref(a) for a in args[1:extra_n + 1]]
            else:
                resolved = _resolve_named_goal(
                    db, goal_val, args[1:extra_n + 1], f"call/{extra_n + 1}")
                if resolved is not None:
                    dispatch, call_args = resolved
            if dispatch is not None:
                sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *call_args, trail)
                _st = yield (sg, None)
                while _st is not DONE:
                    yield (_proceed, None)
                    _st = yield (sg, None)
            yield (_fail, DONE)
        return _call_goal_n

    factory._db_optional = True
    return factory


for _n in range(0, 8):  # extra_n=0..7 → arity 1..8
    _cg_arity = _n + 1
    _DB_BUILTINS[("call_goal", _cg_arity)] = _make_call_goal_factory(_n)
    _BUILTIN_FIELDS[("call_goal", _cg_arity)] = ("goal",) + tuple(f"a{i}" for i in range(_n))

# call/1..8 — aliases: call(Goal, A1, ...) = call_goal(Goal, A1, ...)
for _n in range(1, 9):
    _key = ("call_goal", _n)
    if _key in _DB_BUILTINS:
        _DB_BUILTINS[("call", _n)] = _DB_BUILTINS[_key]
        _BUILTIN_FIELDS[("call", _n)] = _BUILTIN_FIELDS[_key]

del _n, _cg_arity, _key  # clean up loop variables


# ── Higher-order list predicates (V2-11) ──────────────────────────────────────


@_trampoline_builtin("maplist", 2)
def _map_list__2(this_generator, _proceed, _fail, _catcher, goal, lst, trail):
    """map_list(Goal, List) — Goal(Elem) succeeds for each element."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    for elem in items:
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        # Got first solution — committed choice, move to next element
    yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("maplist", 3)
def _map_list__3(this_generator, _proceed, _fail, _catcher, goal, xs, ys, trail):
    """map_list(Goal, Xs, Ys) — Goal(X, Y) maps each X to Y.

    F063 (C9 audit, option A): result is wrapped via ``_seq_result`` so
    str input with all-1-char-str result elements collapses to a
    ``str``; list input keeps list output.
    """
    xs_val = deref(xs)
    goal_val = deref(goal)
    xs_items = _as_items(xs_val)
    if xs_items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(xs_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    results = []
    for x in xs_items:
        y = Var()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(x), y, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        results.append(deref(y))
    if unify(ys, _seq_result(results, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("include", 3)
def _include__3(this_generator, _proceed, _fail, _catcher, goal, lst, included, trail):
    """include(Goal, List, Included) — keep elements where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F003: keep the successful test's bindings (SWI `->`
            # semantics) so a Var element the test bound persists into the
            # result; only a FAILED test's half-bindings are undone.
            kept.append(deref(elem))
        else:
            trail.undo(mark)
    if unify(included, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("exclude", 3)
def _exclude__3(this_generator, _proceed, _fail, _catcher, goal, lst, excluded, trail):
    """exclude(Goal, List, Excluded) — keep elements where Goal(Elem) fails."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            # A09-F003: goal failed → element kept; undo its half-bindings.
            trail.undo(mark)
            kept.append(deref(elem))
        # goal succeeded → excluded; its bindings persist (SWI `->`).
    if unify(excluded, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("foldl", 4)
def _foldl__4(this_generator, _proceed, _fail, _catcher, goal, lst, v0, v, trail):
    """foldl(Goal, List, V0, V) — left fold with Goal(Elem, Acc0, Acc1)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 3)
    outer_mark = trail.mark()
    acc = v0
    for elem in items:
        next_acc = Var()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), deref(acc), next_acc, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        acc = next_acc
    if unify(v, deref(acc), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


# ── V3-5: Extended higher-order list predicates ──────────────────────────────


def _is_goal(val):
    """Check if val is a callable goal (closure, predicate with dispatch, or
    -- W4b-3 -- the module-qualified predicate HANDLE a predicate name is
    bound to after the flip; a mangled DATA atom is not one)."""
    return (callable(val) or hasattr(val, '_get_dispatch')
            or is_declared_predicate_name(val))


@_trampoline_builtin("take_while", 3)
def _take_while__3(this_generator, _proceed, _fail, _catcher, goal, lst, prefix, trail):
    """take_while(Goal, List, Prefix) — longest prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    taken = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        taken.append(deref(elem))  # keep the successful test's bindings
    if unify(prefix, _seq_result(taken, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("drop_while", 3)
def _drop_while__3(this_generator, _proceed, _fail, _catcher, goal, lst, suffix, trail):
    """drop_while(Goal, List, Suffix) — drop prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    i = 0
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        i += 1
    if unify(suffix, _seq_result(items[i:], was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("span", 4)
def _span__4(this_generator, _proceed, _fail, _catcher, goal, lst, yes, no, trail):
    """span(Goal, List, Yes, No) — take_while + drop_while in one pass."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    taken = []
    i = 0
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        taken.append(deref(elem))  # keep the successful test's bindings
        i += 1
    if unify(yes, _seq_result(taken, was_str), trail) and unify(no, _seq_result(items[i:], was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("group_by", 3)
def _group_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, groups, trail):
    """group_by(Goal, List, Groups) — group consecutive elements by key via Goal(Elem, Key).

    F063 (C9 audit, option A): inner groups and the outer container
    are wrapped via ``_seq_result`` so str input collapses each inner
    group (slice of the input) and the outer list of groups to str
    when the elements are 1-char strs; list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    result: list[list] = []
    prev_key = object()  # sentinel
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        if k == prev_key and result:
            result[-1].append(deref(elem))
        else:
            result.append([deref(elem)])
            prev_key = k
    # F063: each inner group is a slice of the input — promote to str
    # when the input was a str. The outer container stays a list (a
    # str cannot contain str elements as distinct cells under the
    # strings-as-lists contract).
    final = [_seq_result(g, was_str) for g in result]
    if unify(groups, final, trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("sort_by", 3)
def _sort_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, sorted_lst, trail):
    """sort_by(Goal, List, Sorted) — sort List by key projected via Goal(Elem, Key).

    F063 (C9 audit, option A): result is wrapped via ``_seq_result``
    so str input with all-1-char-str elements collapses to a ``str``;
    list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    try:
        keyed.sort(key=lambda pair: pair[0])
    except TypeError:
        keyed.sort(key=lambda pair: _standard_order_key(pair[0]))
    result = [e for _, e in keyed]
    if unify(sorted_lst, _seq_result(result, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("max_by", 3)
def _max_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, maximum, trail):
    """max_by(Goal, List, max_) — element with largest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not items or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    # A09-F012: incomparable keys (e.g. int vs str) raised a raw TypeError
    # from `k > best_key`, uncatchable by catch/3 — while sort_by silently
    # falls back. Use the same standard-order key so max_by/min_by are
    # consistent with sort_by instead of crashing.
    if keyed:
        try:
            best_elem = max(keyed, key=lambda pair: pair[0])[1]
        except TypeError:
            best_elem = max(keyed, key=lambda pair: _standard_order_key(pair[0]))[1]
    else:
        best_elem = None
    if best_elem is not None:
        m = trail.mark()
        if unify(maximum, best_elem, trail):
            yield (_proceed, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("min_by", 3)
def _min_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, minimum, trail):
    """min_by(Goal, List, min_) — element with smallest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not items or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    # A09-F012: same standard-order key as sort_by / max_by so incomparable
    # keys do not leak a raw TypeError.
    if keyed:
        try:
            best_elem = min(keyed, key=lambda pair: pair[0])[1]
        except TypeError:
            best_elem = min(keyed, key=lambda pair: _standard_order_key(pair[0]))[1]
    else:
        best_elem = None
    if best_elem is not None:
        m = trail.mark()
        if unify(minimum, best_elem, trail):
            yield (_proceed, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("filter_map", 3)
def _filter_map__3(this_generator, _proceed, _fail, _catcher, goal, lst, result, trail):
    """filter_map(Goal, List, Result) — map+filter: keep mapped value when Goal(Elem, Out) succeeds.

    F063 (C9 audit, option A): result is wrapped via ``_seq_result``
    so str input with all-1-char-str result elements collapses to a
    ``str``; list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        out = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), out, trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F002: keep the goal's bindings — deref(out) is a top-level
            # walk, so undoing here would strip the bindings the goal made
            # INSIDE the output term (e.g. pair(X, Y) with Y bound).
            kept.append(deref(out))
        else:
            trail.undo(mark)
    if unify(result, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("partition", 4)
def _partition__4(this_generator, _proceed, _fail, _catcher, goal, lst, included, excluded, trail):
    """partition(Goal, List, Included, Excluded) — split list by Goal.

    Included contains elements where Goal(Elem) succeeds.
    Excluded contains elements where Goal(Elem) fails.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F003: keep the successful test's bindings (SWI `->`).
            yes.append(deref(elem))
        else:
            trail.undo(mark)  # discard a failed test's half-bindings
            no.append(deref(elem))
    if unify(included, _seq_result(yes, was_str), trail) and unify(excluded, _seq_result(no, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("tfilter", 3)
def _tfilter__3(this_generator, _proceed, _fail, _catcher, goal, lst, filtered, trail):
    """tfilter(Goal, List, Filtered) — reified filter.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Keep elements where the first solution binds T to True.

    This is the reified counterpart of include/3: instead of testing whether
    Goal(Elem) succeeds or fails, it inspects the truth value that Goal
    binds its last argument to.  Useful with reified predicates like eq/3
    and dif_t/3 that always succeed but bind T to True or False.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        t_var = Var()
        mark = trail.mark()
        # Driven through the trampoline like include/3: a goal that DELEGATES
        # (a ``_NamedGoal`` running the caller's call/N yields a
        # StepGenerator) cannot be driven by a plain inline loop -- that read
        # the delegation step as a solution with T unbound, and every element
        # was dropped.  First solution only (committed choice): the step
        # generator is never resumed.
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), t_var, trail)
        _st = yield (sg, None)
        t_val = deref(t_var) if _st is not DONE else None
        trail.undo(mark)
        if t_val is True:
            kept.append(deref(elem))
    if unify(filtered, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("tpartition", 4)
def _tpartition__4(this_generator, _proceed, _fail, _catcher, goal, lst, included, excluded, trail):
    """tpartition(Goal, List, Included, Excluded) — reified partition.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Elements where first solution gives T=True go into Included,
    T=False into Excluded.

    This is the reified counterpart of partition/4.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in items:
        t_var = Var()
        mark = trail.mark()
        # Trampoline-driven, first solution only -- see tfilter/3.
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), t_var, trail)
        _st = yield (sg, None)
        t_val = deref(t_var) if _st is not DONE else None
        trail.undo(mark)
        if t_val is True:
            yes.append(deref(elem))
        elif t_val is False:
            no.append(deref(elem))
    if unify(included, _seq_result(yes, was_str), trail) and unify(excluded, _seq_result(no, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


# ── Goal-taking list builtins become db-receiving (operator ruling 2026-09-24)
#
# ``maplist(nl, [3], [L])`` in a module that does ``-import_from(alow,
# [alias(numlist, nl)])`` hands these builtins alow's numlist/1 binding (class
# or handle) and nothing else; ``_dispatch_at`` on that binding at arity 2
# answered alow's builtin numlist/2 -- the aliased-import leak, through a
# meta-call.  The ruling: a goal reached through an unqualified name resolves
# under THAT name in the CALLING module.  Only the caller's database can say
# which name that was, so each of these is re-registered as a db-receiving
# factory whose product localizes the goal (``predicate.localize_goal``) and
# then runs the unchanged builtin.  ``_db_optional``: with no db the goal is
# passed through untouched -- the pre-ruling builtin exactly -- so the db-less
# paths (``_BUILTIN_CLASSES``, a db-less ``BuiltinPredicate``) keep working;
# the same arrangement ``call/N``, ``phrase`` and ``time_goal`` already use.

_GOAL_FIRST_LIST_BUILTINS = (
    ("maplist", 2), ("maplist", 3), ("include", 3), ("exclude", 3),
    ("foldl", 4), ("take_while", 3), ("drop_while", 3), ("span", 4),
    ("group_by", 3), ("sort_by", 3), ("max_by", 3), ("min_by", 3),
    ("filter_map", 3), ("partition", 4), ("tfilter", 3), ("tpartition", 4),
)


class _NamedGoal:
    """A goal that arrived as a NAME -- a plain atom ``b`` or a cell
    ``add(1)`` -- handed to a goal-first list builtin, which can only run a
    goal object.  Operator ruling 2026-09-24 (ruling S's consequence): a bare
    predicate name in data position is its PLAIN atom, so ``maplist(b, L)``
    now passes ``'b'``, and it must resolve by name in the CALLER's module
    exactly as ``call(b, X)`` does.

    Not a second resolver: ``_get_dispatch`` answers a trampoline function
    that, handed the builtin's extras, runs the caller's own ``call/N``
    (``_make_call_goal_factory``) with this goal first -- the ISO fold
    (``call(add(1), X, Y)`` is ``add(1, X, Y)``), the namespace and qualified
    lookups, and the ISO ``existence_error(procedure, Name/Arity)`` for a
    name that resolves to nothing (operator ruling 2, 2026-09-25) all come
    from there.  Arity-free on purpose: the extras count is known only
    at the call, and ``_dispatch_at`` hands a non-``PredicateMeta`` object to
    its plain ``_get_dispatch()``.
    """
    __slots__ = ("db", "goal", "_by_extras")

    def __init__(self, db, goal) -> None:
        self.db = db
        self.goal = goal
        self._by_extras = {}

    def _get_dispatch(self):
        db, goal, cache = self.db, self.goal, self._by_extras

        def _named_goal(this_generator, _proceed, _fail, _catcher, *args):
            n = len(args) - 1                  # args = (*extras, trail)
            call_n = cache.get(n)
            if call_n is None:
                factory = _DB_BUILTINS.get(("call", n + 1))
                if factory is None:            # past call/8: nothing answers
                    return _fails(_fail)
                call_n = cache[n] = factory(db)
            return call_n(this_generator, _proceed, _fail, _catcher, goal, *args)
        return _named_goal

    def __repr__(self) -> str:
        return f"_NamedGoal({self.goal!r})"


def _fails(_fail):
    yield (_fail, DONE)


def _as_named_goal(db, goal):
    """*goal* wrapped as a ``_NamedGoal`` when it is a NAME the list builtins
    cannot run themselves (a plain atom or a cell); anything else unchanged."""
    if type(goal) is str and not is_declared_predicate_name(goal):
        return _NamedGoal(db, goal)
    if type(goal) is tuple and compound_cell_shape(goal)[0]:
        return _NamedGoal(db, goal)
    return goal


def _make_localizing_factory(impl):
    def factory(db):
        if db is None:
            return impl

        def _localized(this_generator, _proceed, _fail, _catcher, goal, *rest):
            return impl(this_generator, _proceed, _fail, _catcher,
                        _as_named_goal(db, localize_goal(db, deref(goal))),
                        *rest)
        _localized.__name__ = impl.__name__
        return _localized
    factory._db_optional = True
    factory._localizing = True
    return factory


def _register_localizing_list_builtins() -> None:
    """Move each goal-first list builtin from ``_BUILTINS`` to a localizing
    ``_DB_BUILTINS`` factory.  Idempotent (review round 4): a reload of this
    module re-runs the ``@_trampoline_builtin`` decorators, which put a fresh
    stateless entry back in ``_BUILTINS``; that entry is popped again and the
    factory rebuilt around the NEW function.  A key with no stateless entry
    whose factory is already a localizing one is left alone."""
    from clausal.logic.builtins._registry import _BUILTINS  # noqa: PLC0415
    for key in _GOAL_FIRST_LIST_BUILTINS:
        impl = _BUILTINS.pop(key, None)
        if impl is None:
            if getattr(_DB_BUILTINS.get(key), "_localizing", False):
                continue
            raise RuntimeError(f"goal-first list builtin {key} is not registered")
        _DB_BUILTINS[key] = _make_localizing_factory(impl)


_register_localizing_list_builtins()
