"""Higher-order builtins: call_goal/1..8, call/1..8, maplist/2,3,
include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4,5,6,
take_while/3, drop_while/3, span/4, group_by/3, sort_by/3,
max_by/3, min_by/3, filter_map/3."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.atoms import demangle, is_mangled
from clausal.logic.exceptions import (
    LogicException, existence_error, instantiation_error, string_goal_error,
)
from clausal.logic.meta_predicate import is_goal_object as _is_goal_object
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.builtins.lists import _as_items, _open_skeleton, _partial, _seq_result, _was_string
from clausal.logic.builtins._helpers import _is_empty_list, _standard_order_key
from clausal.logic.predicate import (
    _dispatch_at, _refuse_unqualified_other_arity,
    is_declared_predicate_name, localize_goal, localize_owner_functor,
)

from clausal.logic.cells import (
    is_chars, chars_text,   # stage 1: the chars carrier
    CELL_GOAL_CONTROL_FUNCTORS,
    QUALIFIED_GOAL_FUNCTOR,
    compound_cell_shape,
    resolve_qualified_goal_cell,
    qualify_mangled_goal,
)

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _ensure_trampoline_dispatch,
    _DB_BUILTINS, _BUILTIN_FIELDS,
)
from clausal.logic.builtins.call_body import (
    is_body_term, body_goal_dispatch, body_with_extras_error,
    is_special_form, special_form_dispatch,
    non_callable_goal_error, iso_control_cell_dispatch, folded_existence_error,
    needs_meta_call, MetaCallGoal,
)
from clausal.pythonic_ast.nodes import BitXor as _BitXor


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
    when no db was threaded (nothing to resolve a name against).

    A goal that is not CALLABLE at all (a number, tuple data, None ...)
    RAISES ``type_error(callable, Goal)``, and a body term runs
    (``call_body``); call/N's extras on a body term or a control construct
    name no procedure (existence_error) -- operator ruling of 2026-09-25
    (follow Scryer), which retired the translator's "section 4.2" contract
    that such goals fail.

    A name that resolves to NO procedure RAISES ISO
    ``existence_error(procedure, Name/Arity)``, catchable -- operator ruling
    2 (2026-09-25, "like Scryer"); ``call(M:nosuch(X))`` with a resolvable M
    raises too.  A name the calling module binds to a predicate at another
    arity only raises the same ISO term as ``PredicateArityMismatchError`` --
    the refusal a body call at that arity gets
    (``_refuse_unqualified_other_arity``; ruling Q3, 2026-09-25).  Every
    caller of this resolver inherits these raises: call/N, phrase/2,3,
    time_goal/1 and every goal-first list builtin through ``call_body.MetaCallGoal`` --
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
    if is_body_term(goal_val):
        # A BODY term -- also reached as the inner goal of ``M:Body``, whose
        # arm below restarts here against M's db (ISO: M is the context
        # module of the whole body).
        if not extra_args:
            return body_goal_dispatch(db, goal_val, context)
        # call/N's extras fold onto the construct, and the folded goal names
        # no procedure (operator ruling 2026-09-25, follow Scryer):
        # ``call((A, B), X)`` -> existence_error(procedure, ','/3).
        raise LogicException(body_with_extras_error(
            goal_val, len(extra_args), context))
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
    elif type(goal_val) is list:
        # A non-empty list is the callable compound '.'/2 (ISO), and no
        # procedure '.'/N+2 exists: ``call([1, 2])`` -> existence_error(
        # procedure, '.'/2), ``call([a], x)`` -> '.'/3.  Operator rule
        # 2026-09-25 (ISO first; Scryer disagrees with itself here -- a
        # LITERAL ``call([a])`` is existence_error, a RUN-TIME ``G = [a],
        # call(G)`` type_error), reversing round 2's type_error.  A string
        # is the same list, answered by ``string_goal_error`` above.
        raise LogicException(folded_existence_error(
            ".", 2 + len(extra_args), context))
    else:
        # Not a callable term (operator ruling 2026-09-25, retiring the
        # translator's "section 4.2" silent-failure contract): a number,
        # tuple DATA, None, a dict ... is ``type_error(callable, Goal)``.
        raise LogicException(non_callable_goal_error(goal_val, context))
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
            # ``M:_`` is instantiation_error (Scryer, verified on the box).
            # Everything else restarts below against M's db: a body term runs
            # there, a list is existence_error '.'/N, and a non-callable (a
            # number, a unit Quantity ...) is type_error(callable, X) -- Scryer
            # answers ``call(lists:5)`` so.
            raise LogicException(instantiation_error(context))
        return _resolve_named_goal(
            target.db, inner, tuple(call_args[2:]), context)
    if (is_special_form(functor, len(call_args))
            and not _import_shadows_special_form(db, functor)):
        # A compiler SPECIAL FORM (findall/3, once/1, catch/3, throw/1 ...),
        # after the fold -- so ``call(findall(X), G, L)`` is findall/3 too.
        # No database defines these names (the compiler lowers them inline),
        # so they used to reach the lookup below, find nothing, and fail
        # SILENTLY.  Decided before the ``db is None`` bail for the same
        # reason as the zero-arity constructs: no db can answer for them.
        return special_form_dispatch(db, folded, context)
    # No arity condition (F3): ``call((",",))`` is as much a control construct
    # in goal position as ``call((",", A, B))``, and it used to fail silently
    # here while ``solve((",",), m)`` raised.
    if functor in CELL_GOAL_CONTROL_FUNCTORS:
        # Operator ruling 2026-09-25: the ISO cells ``(",", A, B)``,
        # ``(";", A, B)`` and ``("\\+", G)`` run as bodies; ``->`` and
        # ``*->`` are refused (cut-free, no committed choice); any other
        # arity -- what call/N's fold makes -- names no procedure.
        return iso_control_cell_dispatch(db, folded, functor,
                                         len(call_args), context)
    if call_args and functor in _ZERO_ARITY_CONTROL_GOALS:
        # ``call(true, X)`` / ``call(fail, X)``: the fold makes true/1, a
        # control construct with extra arguments, which no database defines
        # (Scryer: existence_error(procedure, true/1)) -- the same answer the
        # ``True``/``False`` object gets (operator ruling 2026-09-25).
        raise LogicException(folded_existence_error(
            functor, len(call_args), context))
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
    # A name the calling module binds to a NON-predicate goal object (a
    # ModulePredicate) is that object, before the db's row and the builtins:
    # a clause body calls the binding (``-import_from(py.random,
    # [permutation])`` makes ``permutation(L, P)`` py.random's, not the
    # builtin permutation/2), and so does ``solve.call`` ("Phase 5").
    _module_dict = getattr(db, "module_dict", None)
    dispatch = (_goal_object_dispatch(db, _module_dict.get(functor), arity)
                if isinstance(_module_dict, dict) else None)
    if dispatch is not None:
        return dispatch, call_args
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
            "procedure", ("/", functor, arity),
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


def _import_shadows_special_form(db, functor) -> bool:
    """True when the calling module IMPORTED a binding under the special-form
    name *functor* -- a ModulePredicate (``-import_from(py.re, [findall])``)
    or another module's predicate (``-import_from(m, [once])``).

    That is how the compiled body decides: ``-import_from`` rewrites every
    body call of an imported name to the dotted global (``py.re.findall``),
    which is no special form, so the body runs the import; a module's OWN
    predicate of that name is not rewritten, and its body still lowers the
    special form.  ``call/N`` of the cell answers the same way: the import
    wins, and the resolution below reaches it (the goal-object arm, or the
    adopted row).
    """
    module_dict = getattr(db, "module_dict", None)
    if not isinstance(module_dict, dict):
        return False
    binding = module_dict.get(functor)
    if binding is None:
        return False
    if is_declared_predicate_name(binding, db=db):
        from clausal.logic.predicate import _binding_owner_db  # noqa: PLC0415
        owner = _binding_owner_db(binding, db)
        return owner is not None and owner is not db
    return type(binding) is not str and hasattr(binding, "_get_dispatch")


def _goal_object_dispatch(db, binding, arity):
    """The dispatch of a NON-predicate goal object the name is bound to --
    a ``ModulePredicate`` (``-import_from(py.re, [match])``) or any other
    implementor of the duck-typed ``_get_dispatch`` protocol -- else None.

    A clause body calls such a binding through its ``_get_dispatch()``
    (``solve.call`` does the same, its "Phase 5"), so ``match(P, S)`` ran
    while ``call(("match", P, S))`` from the same module found no predicate
    class under the name and FAILED SILENTLY.  Resolved through
    ``predicate._dispatch_at``, the one place the protocol is called, so the
    binding's own arity check (a ``ModulePredicate``'s existence_error at an
    arity it does not register) answers as it does in the body.  Asked
    BEFORE the db's row and the builtins (``_resolve_named_goal``), because
    that is the body's order: with py.random's ``permutation`` imported, the
    body's ``permutation(L, P)`` is py.random's, not the builtin
    permutation/2.  A predicate binding (class or handle) answers None.
    """
    if (binding is None or type(binding) is str
            or not hasattr(binding, "_get_dispatch")
            or is_declared_predicate_name(binding, db=db)):
        return None
    return _dispatch_at(binding, arity, db)


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
            if is_var(goal_val):
                # ISO 7.8.3.3: an unbound goal is an instantiation error
                # (Scryer: ``call(_)`` and ``call(_, x)``), never a silent
                # failure.
                from clausal.logic.exceptions import instantiation_error  # noqa: PLC0415
                raise LogicException(instantiation_error(
                    f"call/{extra_n + 1}: the goal is unbound"))
            if type(goal_val) is _BitXor:
                # ``call(Y^G)``: ``^`` is a goal only inside bagof/setof's
                # iterated goal (ISO 7.1.1.4); anywhere else it is the
                # procedure (^)/2, which does not exist (Scryer:
                # existence_error(procedure, (^)/2)).  It used to be
                # type_error(callable).  With extras the fold is
                # library(lambda)'s (^)/3.. -- a builtin -- so the operator
                # node goes the way its cell spelling ``'^'(Y, G)`` goes.
                if extra_n == 0:
                    raise LogicException(folded_existence_error(
                        "^", 2, "call/1"))
                goal_val = ("^", goal_val.left, goal_val.right)
            # A BODY term (conjunction, or, not, if_, a comparison ...) is
            # interpreted by ``_resolve_named_goal`` -- see ``call_body``.
            # Checked first: its nodes are Python-``callable`` and would
            # otherwise take the goal-OBJECT route below and be refused.
            body = is_body_term(goal_val)
            # Operator ruling 2026-09-24: an imported predicate reached
            # through an unqualified name -- its class, or (after the flip)
            # the owner HANDLE an import binds -- resolves under that name
            # in the calling module, not in the owner.  A handle the calling
            # module does not bind by a plain name keeps the qualified route
            # through ``_resolve_named_goal`` below.
            localized = goal_val if body else localize_goal(db, goal_val)
            if body:
                dispatch, call_args = _resolve_named_goal(
                    db, goal_val, args[1:extra_n + 1], f"call/{extra_n + 1}")
            elif localized is not goal_val:
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


# ── findall/4 ─────────────────────────────────────────────────────────────────


def _findall_4_factory(db):
    """findall(Template, Goal, Bag, Tail) -- findall/3 whose result list ends
    in *Tail* instead of ``[]`` (Scryer, SWI: ``findall(X, member(X, [a, b]),
    L, [c])`` gives ``L = [a, b, c]``).  It did not exist
    (existence_error(procedure, findall/4)).  Runs ``call/1`` of the
    ``findall/3`` term, so the goal is resolved in the calling module and
    every findall/3 rule -- errors included -- applies unchanged."""
    call1 = _DB_BUILTINS[("call", 1)](db)

    def _findall__4(this_generator, _proceed, _fail, _catcher,
                    template, goal, bag, tail, trail):
        collected = Var()
        sg = StepGenerator(call1, this_generator, this_generator,
                           this_generator, ("findall", template, goal, collected),
                           trail)
        _st = yield (sg, None)
        while _st is not DONE:
            mark = trail.mark()
            items = _as_items(deref(collected))
            if items is not None and unify(bag, _partial(list(items), tail), trail):
                yield (_proceed, None)
            trail.undo(mark)
            _st = yield (sg, None)
        yield (_fail, DONE)
    return _findall__4


_findall_4_factory._db_optional = True
_DB_BUILTINS[("findall", 4)] = _findall_4_factory
_BUILTIN_FIELDS[("findall", 4)] = ("template", "goal", "bag", "tail")


# ── Higher-order list predicates (V2-11) ──────────────────────────────────────


# maplist/2,3 backtrack through EVERY solution of each call, as the ISO
# prologue's definition by call/N does (operator ruling R5/R6, 2026-09-28):
# ``maplist(p, [X, Y])`` with p(1). p(2). p(3). has 9 answers, X varying
# slowest.  They used to commit to each call's first solution.  The calls
# are driven depth-first from a stack of per-element step generators: a
# solution of the last call is an answer, and asking for the next answer
# re-asks the deepest call that has one left.


def _maplist_drive(this_generator, _proceed, dispatch, args_for, n, trail,
                   finish=None):
    """Yield the trampoline steps that run ``call(G, args_for(i)...)`` for
    ``i`` in ``0 .. n-1`` depth-first, proceeding once per combination --
    or, with *finish*, once per combination for which ``finish()`` (run
    under its own trail mark) succeeds."""
    if n == 0:
        mark = trail.mark()
        if finish is None or finish():
            yield (_proceed, None)
        trail.undo(mark)
        return
    stack = [StepGenerator(dispatch, this_generator, this_generator,
                           this_generator, *args_for(0), trail)]
    while stack:
        _st = yield (stack[-1], None)
        if _st is DONE:
            stack.pop()             # this call is exhausted: re-ask the one before
            continue
        if len(stack) == n:
            # every call succeeded: one answer, then the next solution of
            # the last call
            if finish is None:
                yield (_proceed, None)
            else:
                mark = trail.mark()
                if finish():
                    yield (_proceed, None)
                trail.undo(mark)
            continue
        stack.append(StepGenerator(dispatch, this_generator, this_generator,
                                   this_generator, *args_for(len(stack)), trail))


# ── Open lists: the prologue's recursion, clause by clause ──────────────────
#
# ``maplist(G, [], ...)`` and ``maplist(G, [X|Xs], ...)`` (likewise foldl/4-6)
# are tried in that order at every position, so an unbound or partial list
# argument enumerates as in Scryer: ``maplist(p, L)`` answers ``L = []``, then
# ``L = [1]``, ``L = [1, 1]``, ... depth first, without end.  A list argument
# is followed as ``(items, index, tail)``: its known elements, and the
# unbound variable (or None: the proper end) after them.  A goal may bind a
# tail as it runs, so each position re-reads the tail it reaches.


def _list_state(term):
    """``(items, 0, tail)`` for a proper or open list, else None."""
    d = deref(term)
    items = _as_items(d)
    if items is not None:
        return items, 0, None
    skel = _open_skeleton(d)
    if skel is None:
        return None
    return skel[0], 0, skel[1]


def _settle(st):
    """*st* with a bound tail it has reached read on, else None (not a list)."""
    items, i, tail = st
    while i >= len(items) and tail is not None:
        t = deref(tail)
        if is_var(t):
            return items, i, t
        st = _list_state(t)
        if st is None:
            return None
        items, i, tail = st
    return items, i, tail


def _open_lists_drive(this_generator, _proceed, dispatch, lists, call_args,
                      trail, finish=None):
    """Yield the trampoline steps of the prologue's recursion over *lists*
    (proper or open): at each position first "every list ends here" (then
    ``finish(depth)``, under its own trail mark, and an answer), then "every
    list has one more element" and ``call(G, *call_args(depth, heads))``,
    re-asking the deepest call on backtracking.  *call_args* runs under the
    position's trail mark and may answer None: the clause's head does not
    unify there."""
    states = []
    for t in lists:
        st = _list_state(t)
        if st is None:
            return
        states.append(st)
    outer = trail.mark()
    closed = {len(items) for items, _i, tail in states if tail is None}
    if closed:
        # A proper list fixes the length, so every open one is that long:
        # bind it to a plain list now (the recursion's own head unifications,
        # done up front; the answers and their order are the same, and they
        # read back as plain lists rather than a chain of partial ones).
        if len(closed) > 1:
            return
        n = closed.pop()
        for k, (items, _i, tail) in enumerate(states):
            if tail is not None:
                if len(items) > n or not unify(
                        tail, [Var() for _ in range(n - len(items))], trail):
                    trail.undo(outer)
                    return
                states[k] = (list(items) + deref(tail), 0, None)
    stack = []                       # (step generator, trail mark, next states)
    while True:
        states = [_settle(st) for st in states] if states is not None else None
        if states is not None and None in states:
            states = None
        if states is not None:
            # clause 1: all lists end at this position
            mark = trail.mark()
            ok = True
            for items, i, tail in states:
                if i < len(items) or (tail is not None
                                      and not unify(tail, [], trail)):
                    ok = False
                    break
            if ok and (finish is None or finish(len(stack))):
                yield (_proceed, None)
            trail.undo(mark)
            # clause 2: all lists have one more element
            mark = trail.mark()
            heads, nxt = [], []
            for items, i, tail in states:
                if i < len(items):
                    heads.append(deref(items[i]))
                    nxt.append((items, i + 1, tail))
                elif tail is None:
                    heads = None
                    break
                else:
                    h, t = Var(), Var()
                    if not unify(tail, _partial([h], t), trail):
                        heads = None
                        break
                    heads.append(h)
                    nxt.append(((), 0, t))
            args = None if heads is None else call_args(len(stack), heads)
            if args is not None:
                stack.append((StepGenerator(
                    dispatch, this_generator, this_generator, this_generator,
                    *args, trail), mark, nxt))
            else:
                trail.undo(mark)
        # the next solution of the deepest call
        while stack:
            _st = yield (stack[-1][0], None)
            if _st is not DONE:
                break
            trail.undo(stack.pop()[1])
        if not stack:
            trail.undo(outer)
            return
        states = stack[-1][2]


@_trampoline_builtin("maplist", 2)
def _map_list__2(this_generator, _proceed, _fail, _catcher, goal, lst, trail):
    """map_list(Goal, List) — Goal(Elem) succeeds for each element; every
    combination of the calls' solutions is an answer."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    if items is None:
        # an OPEN list enumerates, as the prologue's recursion does
        if _open_skeleton(lst_val) is not None:
            dispatch = _ensure_trampoline_dispatch(goal_val, 1)
            yield from _open_lists_drive(this_generator, _proceed, dispatch,
                                         [lst_val], lambda _i, hs: hs, trail)
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 1)
    outer_mark = trail.mark()
    yield from _maplist_drive(this_generator, _proceed, dispatch,
                              lambda i: (deref(items[i]),), len(items), trail)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("maplist", 3)
def _map_list__3(this_generator, _proceed, _fail, _catcher, goal, xs, ys, trail):
    """map_list(Goal, Xs, Ys) — Goal(X, Y) maps each X to Y; every
    combination of the calls' solutions is an answer.

    F063 (C9 audit, option A): result is wrapped via ``_seq_result`` so
    str input with all-1-char-str result elements collapses to a
    ``str``; list input keeps list output.  When Ys is already a list of
    the same length, each call gets its own element of Ys (the prologue's
    ``call(G, X, Y)``), so a bound Y constrains the call instead of
    filtering its solutions afterwards.
    """
    xs_val = deref(xs)
    goal_val = deref(goal)
    xs_items = _as_items(xs_val)
    if not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    if xs_items is None:
        # an OPEN Xs: the prologue's recursion over both lists (a proper Ys
        # bounds it)
        if _open_skeleton(xs_val) is not None:
            dispatch = _ensure_trampoline_dispatch(goal_val, 2)
            yield from _open_lists_drive(this_generator, _proceed, dispatch,
                                         [xs_val, ys], lambda _i, hs: hs, trail)
        yield (_fail, DONE)
        return
    was_str = _was_string(xs_val)   # stage 1: str, carrier or ground SegString
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)
    outer_mark = trail.mark()
    n = len(xs_items)
    ys_val = deref(ys)
    ys_items = None if is_var(ys_val) or was_str else _as_items(ys_val)
    if ys_items is not None:
        if len(ys_items) == n:
            yield from _maplist_drive(
                this_generator, _proceed, dispatch,
                lambda i: (deref(xs_items[i]), ys_items[i]), n, trail)
        trail.undo(outer_mark)
        yield (_fail, DONE)
        return
    outs = [Var() for _ in range(n)]
    if not is_var(ys_val):
        # Ys neither a list nor unbound: a partial list hands its known
        # elements to the calls; anything else answers nothing, at once.
        skel = _open_skeleton(ys_val)
        if skel is None and not was_str:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        if skel is not None:
            if len(skel[0]) > n:
                trail.undo(outer_mark)
                yield (_fail, DONE)
                return
            outs[:len(skel[0])] = skel[0]
    yield from _maplist_drive(
        this_generator, _proceed, dispatch,
        lambda i: (deref(xs_items[i]), outs[i]), n, trail,
        finish=lambda: unify(ys, _seq_result([deref(y) for y in outs], was_str),
                             trail))
    trail.undo(outer_mark)
    yield (_fail, DONE)


def _make_maplist_n(n_lists):
    """maplist/(n_lists + 1) for 3..7 lists: the prologue's definition by
    call/N over every list at once -- proper or open lists, every
    combination of the calls' solutions an answer (``_open_lists_drive``,
    which maplist/2,3 use for open lists).  Scryer's library(lists) has
    maplist/2..9; only /2 and /3 existed here, so ``maplist(plus, Xs, Ys,
    Zs)`` was existence_error(procedure, maplist/4)."""
    def fn(this_generator, _proceed, _fail, _catcher, goal, *rest):
        *lists, trail = rest
        goal_val = deref(goal)
        if not _is_goal(goal_val):
            yield (_fail, DONE)
            return
        dispatch = _ensure_trampoline_dispatch(goal_val, n_lists)
        yield from _open_lists_drive(this_generator, _proceed, dispatch,
                                     lists, lambda _i, hs: hs, trail)
        yield (_fail, DONE)
    fn.__name__ = f"_map_list__{n_lists + 1}"
    fields = ("goal",) + tuple(f"list{i + 1}" for i in range(n_lists))
    return _trampoline_builtin("maplist", n_lists + 1, fields=fields)(fn)


# up to maplist/8: its goal is called with 7 arguments, i.e. call/8, the
# highest call/N (ISO requires call/1..8).
for _n_lists in range(3, 8):
    globals()[f"_map_list__{_n_lists + 1}"] = _make_maplist_n(_n_lists)
del _n_lists


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


def _foldl(this_generator, _proceed, _fail, goal, lists, v0, v, trail):
    """foldl/4-6 as the prologue defines them (Scryer's library(lists))::

        foldl(G, [X|Xs], A0, A) :- call(G, X, A0, A1), foldl(G, Xs, A1, A).

    EVERY solution of each call is an answer on backtracking, as maplist's
    (operator ruling R5/R6, 2026-09-28) -- foldl used to commit to each
    call's first solution.  Proper lists of one length take the stack
    driver maplist uses; an open list (or lists that must be built)
    enumerates through :func:`_open_lists_drive`."""
    goal_val = deref(goal)
    if not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, len(lists) + 2)
    accs = [v0]

    def call_args(i, heads):
        del accs[i + 1:]
        nxt = Var()
        accs.append(nxt)
        return (*heads, accs[i], nxt)

    items = [_as_items(deref(t)) for t in lists]
    outer_mark = trail.mark()
    if all(it is not None for it in items) and len({len(it) for it in items}) == 1:
        n = len(items[0])
        accs.extend(Var() for _ in range(n))
        yield from _maplist_drive(
            this_generator, _proceed, dispatch,
            lambda i: (*(deref(it[i]) for it in items), accs[i], accs[i + 1]),
            n, trail, finish=lambda: unify(v, accs[n], trail))
    else:
        yield from _open_lists_drive(
            this_generator, _proceed, dispatch, lists, call_args, trail,
            finish=lambda i: unify(v, accs[i], trail))
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("foldl", 4)
def _foldl__4(this_generator, _proceed, _fail, _catcher, goal, lst, v0, v, trail):
    """foldl(Goal, List, V0, V) — left fold with Goal(Elem, Acc0, Acc1)."""
    yield from _foldl(this_generator, _proceed, _fail, goal, [lst], v0, v, trail)


@_trampoline_builtin("foldl", 5)
def _foldl__5(this_generator, _proceed, _fail, _catcher, goal, xs, ys, v0, v, trail):
    """foldl(Goal, Xs, Ys, V0, V) — Goal(X, Y, Acc0, Acc1) over two lists."""
    yield from _foldl(this_generator, _proceed, _fail, goal, [xs, ys], v0, v, trail)


@_trampoline_builtin("foldl", 6)
def _foldl__6(this_generator, _proceed, _fail, _catcher, goal, xs, ys, zs, v0, v, trail):
    """foldl(Goal, Xs, Ys, Zs, V0, V) — Goal(X, Y, Z, Acc0, Acc1) over three lists."""
    yield from _foldl(this_generator, _proceed, _fail, goal, [xs, ys, zs], v0, v, trail)


def _unify_pairs(target, kvs, trail) -> bool:
    """Unify *target* with the list of ``K-V`` pairs *kvs* (``(K, V)``
    tuples), reading each element of a bound list in either spelling of a
    pair (the cell, or a ``k - v`` written in source), as the pairs
    builtins do."""
    from clausal.logic.builtins.pairs import _unify_pair  # noqa: PLC0415
    items = _as_items(deref(target))
    if items is None or len(items) != len(kvs):
        return unify(target, [("-", k, v) for k, v in kvs], trail)
    return all(_unify_pair(t, k, v, trail) for t, (k, v) in zip(items, kvs))


@_trampoline_builtin("map_list_to_pairs", 3)
def _map_list_to_pairs__3(this_generator, _proceed, _fail, _catcher, goal, ls, ps, trail):
    """map_list_to_pairs(Goal, Ls, Pairs) -- Pairs is ``[K1-L1, K2-L2, ...]``
    with ``call(Goal, Li, Ki)`` for each element, as Scryer's
    library(pairs)::

        map_list_to_pairs2([], _, []).
        map_list_to_pairs2([H|T0], Pred, [K-H|T]) :-
                call(Pred, H, K), map_list_to_pairs2(T0, Pred, T).

    Every solution of each call is an answer on backtracking, and open lists
    enumerate, as that definition does."""
    goal_val = deref(goal)
    if not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val, 2)

    def call_args(_i, heads):
        h, p = heads
        k = Var()
        if not unify(p, ("-", k, h), trail):
            return None
        return h, k

    outer_mark = trail.mark()
    items = _as_items(deref(ls))
    if items is not None:
        # a proper Ls: each combination of the calls' solutions binds Pairs
        # to plain Key-Elem cells holding the values themselves (as the
        # pairs builtins build them), not variables bound to them
        hs = [deref(h) for h in items]
        ks = [Var() for _ in hs]
        finish = None
        if is_var(deref(ps)):
            # nothing in Pairs to constrain the calls: bind it once per
            # answer, to cells holding the values themselves
            finish = lambda: unify(ps, [("-", deref(k), deref(h))  # noqa: E731
                                        for k, h in zip(ks, hs)], trail)
        elif not _unify_pairs(ps, list(zip(ks, hs)), trail):
            # a bound or partial Pairs is the clauses' head: unified BEFORE
            # the calls, so each call sees its key (Scryer:
            # map_list_to_pairs(length, [X], [2-X]) runs length(X, 2))
            hs = None
        if hs is not None:
            yield from _maplist_drive(
                this_generator, _proceed, dispatch, lambda i: (hs[i], ks[i]),
                len(hs), trail, finish=finish)
    else:
        yield from _open_lists_drive(this_generator, _proceed, dispatch,
                                     [ls, ps], call_args, trail)
    trail.undo(outer_mark)
    yield (_fail, DONE)


# ── V3-5: Extended higher-order list predicates ──────────────────────────────


def _is_goal(val):
    """Check if val is a callable goal (closure, predicate with dispatch, or
    -- W4b-3 -- the module-qualified predicate HANDLE a predicate name is
    bound to after the flip; a mangled DATA atom is not one)."""
    return (callable(val) or hasattr(val, '_get_dispatch')
            or is_declared_predicate_name(val)
            # Operator rule 2026-09-25 (ISO first: the WG17 prologue defines
            # maplist & co. via call/N): EVERY other goal passes too, and
            # ``_ensure_trampoline_dispatch`` runs it AS call/N per element --
            # a cell, an atom, an unbound Var, a number, a list ...  They used
            # to FAIL here; now maplist(G, []) succeeds for any G, and the
            # first element answers what call(G, E) answers.
            or needs_meta_call(val))


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
        # (a ``MetaCallGoal`` running the caller's call/N yields a
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
    ("maplist", 2), ("maplist", 3), ("maplist", 4), ("maplist", 5),
    ("maplist", 6), ("maplist", 7), ("maplist", 8),
    ("include", 3), ("exclude", 3),
    ("foldl", 4), ("foldl", 5), ("foldl", 6), ("map_list_to_pairs", 3),
    ("take_while", 3), ("drop_while", 3), ("span", 4),
    ("group_by", 3), ("sort_by", 3), ("max_by", 3), ("min_by", 3),
    ("filter_map", 3), ("partition", 4), ("tfilter", 3), ("tpartition", 4),
)


def _make_localizing_factory(impl):
    def factory(db):
        if db is None:
            return impl

        def _localized(this_generator, _proceed, _fail, _catcher, goal, *rest):
            goal = localize_goal(db, deref(goal))
            if needs_meta_call(goal, db):
                # Resolved against THIS db, per element, by call/N itself
                # (operator ruling 2026-09-25) -- see ``MetaCallGoal``.
                goal = MetaCallGoal(goal, db)
            return impl(this_generator, _proceed, _fail, _catcher, goal, *rest)
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
