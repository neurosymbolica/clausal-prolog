"""Higher-order builtins: call_goal/1..8, call/1..8, maplist/2,3,
include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4,
take_while/3, drop_while/3, span/4, group_by/3, sort_by/3,
max_by/3, min_by/3, filter_map/3."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.exceptions import LogicException, string_goal_error
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.builtins.lists import _as_items, _seq_result, _was_string
from clausal.logic.builtins._helpers import _is_empty_list, _standard_order_key

from clausal.logic.cells import (
    is_chars, chars_text,   # stage 1: the chars carrier
    CELL_GOAL_CONTROL_FUNCTORS,
    QUALIFIED_GOAL_FUNCTOR,
    compound_cell_shape,
    refuse_control_construct_cell,
    resolve_qualified_goal_cell,
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

    Returns ``None`` — which the caller turns into a silent failure, the
    behaviour every non-callable goal has had — when the goal is not a cell or
    atom, when no db was threaded, or when the named predicate does not exist.
    That last case is deliberate: the translator session's pinned §4.2 contract
    is that a non-callable goal FAILS rather than raising, and a name that
    resolves to nothing is exactly the same non-goal it was before this task.
    A resolvable module does not change it: ``call(M:nosuch(X))`` fails.

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
    elif type(goal_val) is str or is_chars(goal_val):   # stage 1: the carrier too
        # THE FLIP (spec §6.4): a ``str`` is a STRING, so ``call("foo")`` is
        # not a call to ``foo/0``.  Task 15 item 3 (ISO alignment): the
        # string IS the compound ``'.'/2`` and so IS callable — what is
        # missing is the PROCEDURE, so this is an existence_error, matching
        # Scryer's ``call("foo", X)``.  It is raised rather than failed
        # silently (the treatment a non-callable goal otherwise gets) because
        # a string here is always a mistake about representation, and a
        # silent failure is exactly how that mistake stays invisible.
        raise LogicException(
            string_goal_error(chars_text(goal_val) if is_chars(goal_val) else goal_val, len(extra_args), "call/N"))
    else:
        return None
    call_args = [deref(a) for a in goal_args] + [deref(a) for a in extra_args]
    # The goal as the fold leaves it — the term both special routes below are
    # decided on (F4), and the culprit the control-construct refusal names.
    folded = (functor,) + tuple(call_args)
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
    if db is None:
        return None
    arity = len(call_args)
    dispatch = db.get_dispatch(functor, arity)
    if dispatch is None:
        dispatch = _namespace_dispatch(db, functor, arity)
    if dispatch is None:
        return None
    return dispatch, call_args


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
    name — so the home lookup uses ``pred_cls.__name__``.

    Returns ``None`` (→ silent failure, unchanged) when the name is not in the
    namespace at that arity.
    """
    from clausal.logic.builtins.database_ops import (  # noqa: PLC0415
        _find_pred_cls, _home_db,
    )
    module_dict = getattr(db, "module_dict", None)
    if module_dict is None:
        return None
    pred_cls = _find_pred_cls(functor, arity, module_dict)
    if pred_cls is None:
        return None
    home = _home_db(db, pred_cls)
    if home is db and pred_cls.__name__ == functor:
        return None  # the lookup that already came back empty
    return home.get_dispatch(pred_cls.__name__, arity)


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
            if callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    if xs_items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    """Check if val is a callable goal (closure or predicate with dispatch)."""
    return callable(val) or hasattr(val, '_get_dispatch')


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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = _was_string(lst_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        t_var = Var()
        mark = trail.mark()
        # Run the goal inline (simple-mode) to get the truth value
        # without going through the trampoline yield protocol.
        t_val = None
        for _ in _run_goal_once(dispatch, deref(elem), t_var, trail):
            t_val = deref(t_var)
            break  # committed choice: take first solution only
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
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
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
        t_val = None
        for _ in _run_goal_once(dispatch, deref(elem), t_var, trail):
            t_val = deref(t_var)
            break
        trail.undo(mark)
        if t_val is True:
            yes.append(deref(elem))
        elif t_val is False:
            no.append(deref(elem))
    if unify(included, _seq_result(yes, was_str), trail) and unify(excluded, _seq_result(no, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


def _run_goal_once(dispatch, *args_and_trail):
    """Run a trampoline dispatch function and yield for each solution.

    Drives the trampoline mini-loop internally so callers can iterate
    solutions with a plain ``for _ in _run_goal_once(...):`` loop.
    """
    gen = dispatch(None, None, None, None, *args_and_trail)
    for _parent, value in gen:
        if value is DONE:
            return
        yield value
