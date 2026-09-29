"""Compile-time globals-environment construction.

The functions in this module walk clause trees to gather everything
that needs to land in a compiled predicate's ``__globals__`` dict:
user-defined term types, PyThunk lambdas, call targets (with their
arities), and dispatch-function caches for locked predicates.

Also provides the small utilities ``_set_of_dedup``, ``_merge_builtin``,
``_disp_key`` plus the ``_DbDispatchAdapter`` / ``_GlobalsDb`` shims
used when compiling without live predicate classes.
"""

from __future__ import annotations

import ast
import sys as _sys
from typing import Any

from clausal.logic.generated_names import dollar_ref
from clausal.logic.variables import deref, is_var, unify
from clausal.terms import (
    Call, LoadName, LoadAttr,
    PyThunk,
    SegBytes, SegList, SegString, VarSeg,
)
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import (
    is_term_instance, term_field_names,
    is_declared_predicate, resolve_predicate_row,
    is_declared_predicate_name, _refuse_unqualified_other_arity,
    binding_grants_arity,
)
from clausal.logic.builtins import (
    get_builtin_predicate, BuiltinPredicate,
)

from clausal.logic.cells import _cell_shape, is_chars, is_pool_seeded_atom
from clausal.logic.atoms import is_atom as _term_is_atom, is_nil

from ._ast_helpers import _name, _call, _assign
from ._vars import _var_python_name, _collect_vars
from .terms_to_ast import (
    _dotted_name_from_loadattr,
    _is_opaque_head_literal, headlit_global_key,
)


_PyThunk = PyThunk  # alias used below in a few places for clarity


def _set_of_dedup(items: list) -> list:
    """Deduplicate a list preserving order. Tries hash first, falls back to ==."""
    try:
        return list(dict.fromkeys(items))
    except TypeError:
        seen: list = []
        for item in items:
            if item not in seen:
                seen.append(item)
        return seen


def _set_of_sort_dedup(items: list) -> list:
    """setof/3 result: sort into standard order, then remove duplicates.

    ISO / ``docs/meta_predicates.md`` promise a *sorted* list with duplicates
    removed (A03-F005). Reuses ``sort/2`` (``_sort__2``)'s ordering — the
    shared ``_standard_order_sorted`` — so there is only one standard term
    order in the system.
    """
    from clausal.logic.builtins._helpers import (  # noqa: PLC0415
        _NATIVE_ORDER_SAFE, _standard_order_key,
    )
    # A homogeneous list of a native-order-safe type (int, str, ...) is the
    # common case: native order IS the standard order there and Python ``==``
    # IS key equality, so no key is computed at all (``_standard_order_sorted``
    # takes the same fast path).
    types = set(map(type, items))
    if len(types) == 1 and next(iter(types)) in _NATIVE_ORDER_SAFE:
        return _set_of_dedup(sorted(items))
    # Otherwise each item's standard-order key is computed ONCE and serves
    # both the sort and the dedup.  The Python-``==`` dedup is kept as it was;
    # on top of it, two items with EQUAL standard-order keys are one term too
    # -- terms that are not Python-``==`` but that sort/2 treats as one,
    # and ISO 8.10.3 has setof sort as sort/2 does.  Sorted by key, equal keys are adjacent; the first survives.
    # (Deliberately NOT a pure key dedup: that would also stop setof merging
    # ``1`` and ``1.0``, a parked decision, A01-D001.)
    keyed = [(_standard_order_key(x), x) for x in items]
    keyed.sort(key=lambda pair: pair[0])
    key_of = {id(x): k for k, x in keyed}
    out: list = []
    last = None
    for item in _set_of_dedup([x for _, x in keyed]):
        key = key_of[id(item)]
        if out and key == last:
            continue
        out.append(item)
        last = key
    return out


# ── bagof/3 and setof/3: free variables (ISO 8.10.2, 8.10.3) ────────────────
#
# bagof(T, G, L) collects one bag PER binding of the goal's FREE variables --
# those in G that are neither in T nor existentially quantified by a leading
# ``V^`` -- and backtracks over the bags, sorted by that binding (the
# witness), as Scryer does.  Solutions whose witnesses are VARIANTS share a
# bag, and their witness variables are unified.  The compiled construct
# (``control_constructs._compile_find_all_core``) collects ``[W, T]`` rows and
# hands them to these helpers.


def _bag_witness(goal_vars, template, existential):
    """The witness of a bagof/setof call: the unbound variables of
    *goal_vars* (the goal's own variables, as a tuple) that occur neither in
    *template* nor in *existential* (the ``V^`` prefixes), as a list."""
    from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
    exclude: list = []
    _collect_vars_impl([template, list(existential)], exclude)
    excluded = {id(v) for v in exclude}
    found: list = []
    _collect_vars_impl(list(goal_vars), found)
    return [v for v in found if id(v) not in excluded]


def _bag_peel(goal):
    """``(existential, goal)``: a bagof/setof goal reached through a variable
    (``bagof(X, call(G), L)``, the Clausal spelling of ISO's
    ``bagof(X, G, L)``) with its leading ``V^`` prefixes -- a ``^`` operator
    node or a ``'^'`` cell -- read off at run time, as the compiler strips
    the ones written in source."""
    from clausal.pythonic_ast.nodes import BitXor  # noqa: PLC0415
    existential: list = []
    g = deref(goal)
    while True:
        if type(g) is BitXor:
            existential.append(g.left)
            g = deref(g.right)
        elif (type(g) is tuple and len(g) == 3 and g[0] == "^"):
            existential.append(g[1])
            g = deref(g[2])
        else:
            return tuple(existential), g


def _variant_key(term):
    """A key equal for two terms exactly when they are VARIANTS: each
    variable, in order of first appearance, is replaced by a numbered
    marker no program can write, then the standard-order key is taken."""
    from clausal.logic.builtins.inspection import (  # noqa: PLC0415
        _collect_vars_impl, _copy_term_py,
    )
    from clausal.logic.builtins._helpers import _standard_order_key  # noqa: PLC0415
    found: list = []
    _collect_vars_impl(term, found)
    if not found:
        return _standard_order_key(term)
    marks = {id(v): ("$bagof_variant", i) for i, v in enumerate(found)}
    return _standard_order_key(_copy_term_py(term, marks))


def _bagof_groups(rows, witness):
    """The bags of a bagof/setof call, in the order it answers them.

    *rows* are the collected ``[W, T]`` copies -- the bare templates when
    *witness* is empty, which make one bag.  Rows whose witnesses are
    variants form one bag, in collection order; the bags are ordered by
    their first witness in the standard order of terms (stable), as Scryer's
    keysort orders them.  Each bag is ``(witnesses, templates)``."""
    if not rows:
        return []
    if not witness:                          # no free variables: one bag
        return [([], rows)]
    groups: list = []
    index: dict = {}
    for w, t in rows:
        key = _variant_key(w)
        try:
            at = index.get(key)
        except TypeError:                    # an unhashable key: linear scan
            at = next((i for i, g in enumerate(groups) if g[0] == key), None)
        else:
            if at is None:
                index[key] = len(groups)
        if at is None:
            groups.append((key, [w], [t]))
        else:
            groups[at][1].append(w)
            groups[at][2].append(t)
    if len(groups) > 1:
        from clausal.logic.builtins._helpers import _standard_order_key  # noqa: PLC0415
        groups.sort(key=lambda g: _standard_order_key(g[1][0]))
    return [(ws, ts) for _, ws, ts in groups]


def _bagof_bind(witness, ws, bag, ts, dedup: bool, trail) -> bool:
    """Answer one bag: unify the live *witness* with each collected witness
    of the bag (they are variants, so this also shares their variables
    across the bag's templates), then *bag* with the templates -- sorted and
    without duplicates for setof."""
    for w in ws:
        if not unify(witness, w, trail):
            return False
    if dedup:
        if ws:
            # the witness unification may have bound the rows' variables
            from clausal.logic.solve import _deref_walk  # noqa: PLC0415
            ts = [_deref_walk(t) for t in ts]
        ts = _set_of_sort_dedup(ts)
    return unify(bag, ts, trail)


def _findall_copy_row(template):
    """Collect one findall/bagof/setof solution as a copy with FRESH unbound
    vars (ISO copy_term semantics, A03-F006).

    ``_deref_walk`` resolves bindings but returns unbound vars *as-is*, so
    every collected row would share the caller's Var objects — a later
    binding then retroactively rewrites already-collected rows. Freshen the
    unbound vars per row via ``copy_term``. Ground rows skip the copy (fast
    path — ``_is_ground`` short-circuits on the first Var).
    """
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    from clausal.logic.builtins._helpers import _is_ground  # noqa: PLC0415
    walked = _deref_walk(template)
    if _is_ground(walked):
        return walked
    from clausal.logic.builtins.inspection import _copy_term  # noqa: PLC0415
    return _copy_term(walked, {})


def _throw_ball(ball):
    """The exception ``throw(Ball)`` raises (ISO 13211-1 §7.8.10).

    ``instantiation_error`` when *Ball* is unbound (§7.8.10.3).  Otherwise
    the ball is a COPY made now (§7.8.10.1 b: "the system makes a copy B' of
    B"), before ``catch/3`` undoes the trail back to its mark.  Raising the
    ball as written kept its Vars, and the undo then unbound them: the
    catcher saw ``_`` where the thrower had bound a value.  That is what a
    ball reached through a variable always met -- ``G is throw(oops),
    catch(call(G), E, true)`` bound E to an unbound variable, not ``oops``.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, error_prose, instantiation_error,
    )
    if is_var(deref(ball)):
        return LogicException(instantiation_error(
            "throw/1: the ball is unbound (ISO 7.8.10.3)"))
    # A ball an engine builder made (caught, then thrown again) keeps the
    # explanatory prose its builder recorded, which lives off the term.
    return LogicException(_findall_copy_row(ball), error_prose(deref(ball)))


def _is_list_or_partial_list(term) -> bool:
    """ISO's "a list or a partial list": unbound, ``[]``, a list (in any of
    the engine's list shapes), or a SegList whose bound tail segments are
    lists or partial lists in turn -- ``[a, *T]`` with T unbound or a list,
    not with T bound to ``foo``.

    ``isinstance``, not ``type() in``: a ``-constant_value`` list is a
    ``_FrozenList`` (a ``list`` subclass) and IS a list.  The string carrier
    ``('$chars', s)`` is a list too -- a double-quoted string under
    ``double_quotes(chars)``, which is ISO's list of one-char atoms -- and a
    ``bytes`` is the code list.  A bare ``str`` is an ATOM (stage 2), so
    ``findall(X, G, foo)`` is the type_error."""
    t = deref(term)
    if (is_var(t) or isinstance(t, (list, bytes)) or is_chars(t)
            or is_nil(t)):
        return True
    if isinstance(t, (SegString, SegBytes)):
        return True
    if isinstance(t, SegList):
        return all(_is_list_or_partial_list(seg.var)
                   for seg in t.segments if isinstance(seg, VarSeg))
    return False


def _check_bag(bag, who: str) -> None:
    """``type_error(list, Bag)`` for a findall/bagof/setof result that is
    neither a list nor a partial list (ISO 13211-1 8.10.1.3 d, 8.10.2.3 c,
    8.10.3.3 c; Scryer raises it before running the goal).  It used to be a
    silent failure: the unify of the collected list with ``foo`` failed."""
    if _is_list_or_partial_list(bag):
        return
    # Only the ERROR path imports (the check above is the hot path).
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, type_error,
    )
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    culprit = _deref_walk(bag)
    raise LogicException(type_error(
        "list", culprit, f"{who}: the result must be a list or a partial list"))


# ── Predicate-as-class dispatch adapter ───────────────────────────────────────
#
# Phase 2 of the predicate-as-class refactor changes compiled dispatch calls
# from  ``_db.table_for(fname, arity).get_dispatch()(args, trail, k)``
# to    ``fname._get_dispatch()(args, trail, k)``
# where ``fname`` is resolved from the compiled function's globals.
#
# For predicates that are real PredicateMeta classes (e.g. from .clausal
# modules), the class itself is injected into globals and _get_dispatch()
# returns the compiled dispatch function directly.
#
# For predicates not yet available as classes (e.g. in tests that still use
# Database directly, or for builtin predicates), _DbDispatchAdapter wraps the
# Database lookup with the same _get_dispatch() interface.


from clausal.logic.exceptions import LogicException as _LogicException


class UndeclaredFunctorError(_LogicException, NameError):
    """A construction ``f(A1, ..., An)`` of a functor nothing declares.

    DUAL-TYPED, as ``PredicateArityMismatchError`` is (a LogicException and a
    TypeError): it is the ISO error term ``catch/3`` sees -- it used to be a
    raw Python ``NameError``, which ``catch/3`` could only see transliterated
    as ``('NameError', Message)`` (triage B4c, C1, C3) -- and it is still a
    ``NameError`` with ``name`` set, so every Python handler, and the
    undefined-name diagnostic that keys on ``exc.name``, keeps working.

    The TERM depends on where the construction stood, which the compiler
    knows and records (``terms_to_ast.construction_context``):

    * an evaluable position (``'is'(X, f(1))``, ``X == f(1)``'s arithmetic):
      ``type_error(evaluable, f/1)`` -- what ISO specifies for a compound
      the evaluator does not know;
    * the clause of ``assertz/1`` and friends:
      ``permission_error(modify, static_procedure, f/1)`` with the builtin as
      context (ruling R7, 2026-09-28: an undeclared procedure is static);
    * anywhere else: ``existence_error(procedure, f/1)``, the term the
      Python API already gives for an undeclared ``assertz`` target.

    The assert case follows ruling R7; the database builtins' own refusal
    (``database_ops._resolve_cell_head``) raises the same term.
    """

    def __init__(self, functor: str, arity: int, kind: "str | None" = None,
                 context: "str | None" = None,
                 why: "str | None" = None) -> None:
        from clausal.logic.exceptions import (  # noqa: PLC0415
            _error, existence_error, type_error,
        )
        from clausal.logic.atoms import mint  # noqa: PLC0415
        pi = ("/", functor, arity)
        prose = undeclared_functor_message(functor, arity)
        if kind == "evaluable":
            term = type_error("evaluable", pi,
                              f"{context}: {prose}" if context else prose)
        elif kind in ("procedure", "procedure_arg") and context:
            # RULED R7 (2026-09-28): the clause of assertz/asserta names a
            # procedure nothing declares -- ISO makes it static by default,
            # so writing it is permission_error(modify, static_procedure).
            from clausal.logic.exceptions import permission_error  # noqa: PLC0415
            term = permission_error(
                "modify", "static_procedure", pi,
                f"{context}: " + (why or (
                    f"nothing declares {functor}/{arity}; declare it "
                    f"-dynamic({functor}/{arity}) first"
                    + (", or set the flag assert_creates_dynamic to true in "
                       "this module" if kind == "procedure" else ""))))
        elif context:
            term = _error(("existence_error", mint("procedure"), pi),
                          f"{context}: {prose}")
        else:
            term = existence_error("procedure", pi, prose)
        super().__init__(term)
        self.name = functor
        self.functor = functor
        self.arity = arity


def undeclared_functor_error(functor: str, arity: int,
                             kind: "str | None" = None,
                             context: "str | None" = None) -> NameError:
    """The error a construction ``functor(A1, ..., An)`` of a functor nothing
    declares raises: "'f/N' is not in scope", with the declaration to write.
    An :class:`UndeclaredFunctorError` -- a ``NameError`` and an ISO error
    term at once; *kind*/*context* say where the construction stood.

    One sentence for both routes to it: ``_DbDispatchAdapter.__call__`` (the
    name is bound to nothing, so the adapter stands in) and
    ``$undeclared_functor`` (the name is bound to an ATOM, which is data and
    cannot build a term -- calling it was CPython's bare ``TypeError: 'str'
    object is not callable``).  ``name=`` is what lets the undefined-name
    diagnostic reach it (``enrich_undefined_name`` keys on ``exc.name``).
    """
    return UndeclaredFunctorError(functor, arity, kind, context)


def undeclared_functor_message(functor: str, arity: int) -> str:
    """The text of :func:`undeclared_functor_error`: which declaration builds
    the term.  A term is a cell, so the remedy is a declaration of the
    functor (where the module owns it) or an import of it -- never the Python
    import of a term class the message used to suggest."""
    slots = ", ".join(["_"] * arity) if arity > 0 else ""
    spec = f"{functor}({slots})" if arity > 0 else functor
    return (
        f"Predicate '{functor}/{arity}' is not in scope: nothing declares the "
        f"functor {functor}/{arity}, so {functor}(...) builds no term.\n"
        f"Declare it in the module that owns it, e.g. -private([{spec}]) or "
        f"its -module export list, or import it with "
        f"-import_from(owner, [{functor}])."
    )


def _undeclared_functor(functor: str, arity: int, *args, **kwargs):
    """``$undeclared_functor``: what a construction compiles to when its
    functor NAME is bound to an atom and nothing declares it as a functor.
    Raises at run time, where the adapter's NameError is raised for an
    unbound name, so a clause that never runs still loads."""
    raise undeclared_functor_error(functor, arity)


def _undeclared_functor_in(kind: str, context: "str | None", functor: str,
                           arity: int, *args, **kwargs):
    """``$undeclared_functor_in``: ``$undeclared_functor`` for a construction
    the compiler placed in a known position (``kind``/``context``, see
    :class:`UndeclaredFunctorError`).  Kind ``"cell"`` (the clause of
    retract/1) builds the plain cell instead: nothing is written, the goal
    only matches, and finding no procedure it fails, as ISO 8.9.3 says.

    Kind ``"procedure"`` (the clause of assertz/asserta) builds the cell
    too: whether writing it is allowed depends on the CALLING module's
    ``assert_creates_dynamic`` flag, which only the database builtin knows,
    so the builtin decides (``database_ops._resolve_cell_head``) and raises
    this same :class:`UndeclaredFunctorError` when the flag is off."""
    if kind in ("cell", "procedure") and not kwargs:
        return (functor, *args)
    raise undeclared_functor_error(functor, arity, kind, context)


def _constructor_in(obj: Any, kind: str, context: "str | None",
                    functor: str, arity: int) -> Any:
    """``$constructor_in``: the callee of a construction ``f(...)`` whose
    NAME the compiler found bound to nothing, in a known position.  The name
    is looked up at run time as before; when it is still unbound -- the
    ``_DbDispatchAdapter`` stand-in -- the construction raises the error for
    that position instead of the adapter's context-free one.  Anything else
    the name is bound to by then is returned unchanged."""
    if type(obj) is _DbDispatchAdapter:
        if kind in ("cell", "procedure"):
            def _cell(*args):
                return (functor, *args)
            return _cell
        def _refuse(*args, **kwargs):
            raise undeclared_functor_error(functor, arity, kind, context)
        return _refuse
    return obj


class _DbDispatchAdapter:
    """Adapter: wraps db.get_dispatch() with _get_dispatch() interface.

    Used when a called predicate is in the database but not in module globals.
    Provides the same ``_get_dispatch()`` protocol as PredicateMeta classes.
    """
    __slots__ = ("_db", "_functor", "_arity")

    def __init__(self, db: Database, functor: str, arity: int) -> None:
        self._db = db
        self._functor = functor
        self._arity = arity

    def _get_dispatch(self):
        fn = self._db.get_dispatch(self._functor, self._arity)
        if fn is None:
            # The candidate search runs HERE and nowhere else.  A successful
            # lookup returns above without touching the diagnostics module, so
            # the hunt for what the author could have called instead — which
            # reads and parses sibling source files — costs nothing on the
            # call path.  See todo/predicate-not-found-should-list-candidates.
            from clausal.predicate_diagnostics import (  # noqa: PLC0415
                predicate_not_found,
            )
            raise predicate_not_found(self._functor, self._arity, db=self._db)
        return fn

    def __call__(self, *args, **kwargs):
        # ``name=`` is what lets the undefined-name diagnostic reach this.  One
        # mistake — a sibling's predicate used without importing it — arrives as
        # this sentence when the compiler saw the name as a call target and as
        # CPython's bare ``name 'cite' is not defined`` when it did not, and
        # both should name the module that exports it.  ``enrich_undefined_name``
        # keys on ``exc.name``, which CPython sets only for its own raises.
        raise undeclared_functor_error(self._functor, self._arity)


class _GlobalsDb:
    """Minimal db-like proxy for signature lookup from module globals.

    Used by compile_predicate when ``db=None``.  Only ``signature_for`` is
    implemented; other Database methods are not needed when compiling without
    a live database, and ``hint_row`` documents this shim as the "no ``row``"
    shape it declines to read plans from.

    P1 (spec 2026-09-17 §2.2): the signature comes from the module's own
    Database ROW, reached through the ``$module`` handle the import hook binds
    into every loaded module's dict — not from an ``isinstance(...,
    PredicateMeta)`` test on whatever the name is bound to, and never through
    a predicate's ``_row.db``, which is a DIFFERENT Database for an imported
    name.

    THE CLASS FALLBACK, for a HAND-BUILT globals dict with no ``$module``
    (roborev M2, 2026-09-17).  That dict shape is documented and in use —
    the retired ``predicate.make_predicate``'s docstring built one (W4b-3
    slice 6), and a db-less compile still takes one — and it names no
    Database, so the row read cannot answer.  Answering ``None`` there is not
    "the same answer the class read gave": the class read ANSWERED, and a
    keyword-call body compiled against such a dict raises ``RuntimeError`` for
    a predicate sitting right there in it.  So the class answers when there is
    no ``$module``, and only then.

    ARITY-EXACT on both legs, where the class read took ``arity`` and ignored
    it: a row is keyed ``(functor, arity)``, and the fallback counts the
    class's fields for itself, so a call at arity N is never handed the
    signature registered for the same name at arity M.
    """
    __slots__ = ("_globals",)

    def __init__(self, globals_dict: dict) -> None:
        self._globals = globals_dict

    def signature_for(self, functor: str, arity: int):
        db = getattr(self._globals.get("$module"), "db", None)
        if db is not None:
            row = db.row(functor, arity)
            return row.signature if row is not None else None
        # No ``$module``: a hand-built dict names no Database, so the class
        # bound here answers — arity-checked, because a module dict holds one
        # class per NAME and this shim is handed the arity.
        #
        # W4b-2b: is_declared_predicate is the era-agnostic arity-exact
        # identity gate (it composes to the same len(cls._fields) == arity
        # test this used to spell by hand); resolve_predicate_row is the
        # era-agnostic row fetch, standing in for the RAW `cls._row` read
        # (not the `_signature` facade (W2) -- the facade would MINT a
        # private row for a class that has none, to read a field that is
        # `None` on a fresh row anyway, so `None` here is the same answer
        # without the allocation).
        cls = self._globals.get(functor)
        if not is_declared_predicate(cls, arity=arity):
            return None
        _row = resolve_predicate_row(cls, arity=arity)
        return _row.signature if _row is not None else None


def _record_term_type(types: dict[str, type], term: Any) -> type:
    """Record *term*'s class under its generated-code spelling and return it.

    Shared body for the four near-identical collector walkers below: each
    guards with ``is_term_instance(term)`` first, then wants ``type(term)``
    back both to key ``types`` and to recurse over its declared fields. The
    key is deliberately the class **name string**, not the class itself —
    last-writer-wins on a same-named-functor collision is a known,
    out-of-scope bug in ``_collect_globals_info``; see
    ``todo/assertz-foreign-same-named-functor-head-collision-2026-09-03.md``.
    This helper does not change that semantics, only dedups the four call
    sites that implement it.
    """
    cls = type(term)
    # Bound under the spelling the emitter uses for this class: the ``$``
    # twin for a runtime-table class (``$Add``), bare for a user's own.
    types[dollar_ref(cls)] = cls
    return cls


def _collect_head_types(clauses: list[Clause]) -> dict[str, type]:
    """Return a name→type dict for all user-defined dataclass types found in clause heads.

    These are injected into the compiled function's globals so that
    ``case dog(name=_v0):`` match patterns can resolve ``dog``.
    """
    types: dict[str, type] = {}

    def _walk(term: Any) -> None:
        term = deref(term)
        if isinstance(term, StarUnpack):
            _walk(term.value)
        elif isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            cls = _record_term_type(types, term)
            for name in term_field_names(term):
                _walk(getattr(term, name))
        elif _cell_shape(term)[0]:
            # A CELL -- the same arm ``_collect_globals_info._walk_head``
            # carries, and it has to stay the same arm: this function is not
            # called in production, it is the REFERENCE the single-pass
            # collector is differentially tested against
            # (``test_head_types_collected``), so a difference here reads as
            # a defect in the collector.  It drifted once already: the cell
            # arm went into the combined walker in P3-2 Task 3 fix round 1
            # and not into this one, and stayed invisible until P2's head
            # flip made a clause HEAD a cell and gave the comparison
            # something to disagree about.  See the combined walker for why
            # the slots are recursed into AND the whole-cell entry kept.
            for e in term[1:]:
                _walk(e)
            if _is_opaque_head_literal(term):
                types[headlit_global_key(term)] = term
        elif _is_opaque_head_literal(term):
            types[headlit_global_key(term)] = term

    for clause in clauses:
        _walk(clause.head)
        for goal in clause.body:
            _walk(goal)

    return types


def _collect_py_thunks(clauses: list[Clause]) -> dict[str, Any]:
    """Collect PyThunk lambdas from clause bodies for globals injection.

    Returns a dict mapping ``_pyt_<id>`` → ``thunk.fn`` for each PyThunk
    found in clause body goals.  The compiler references these names when
    emitting thunk calls.
    """
    thunks: dict[str, Any] = {}

    def _walk(term: Any) -> None:
        term = deref(term)
        if isinstance(term, PyThunk):
            thunks[f"_pyt_{id(term)}"] = term.fn
        elif isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            for name in term_field_names(term):
                _walk(getattr(term, name))

    for clause in clauses:
        for goal in clause.body:
            _walk(goal)

    return thunks


def _collect_types_from_term(term: Any) -> dict[str, type]:
    """Return a name→type dict for all user-defined term types in *term*.

    Like _collect_head_types but operates on a single arbitrary term, used by
    _compile_as_query to inject types from inline goal arguments.
    """
    types: dict[str, type] = {}

    def _walk(t: Any) -> None:
        t = deref(t)
        if isinstance(t, StarUnpack):
            _walk(t.value)
        elif isinstance(t, list):
            for e in t:
                _walk(e)
        elif isinstance(t, dict):
            for v in t.values():
                _walk(v)
        elif is_term_instance(t):
            cls = _record_term_type(types, t)
            for name in term_field_names(t):
                _walk(getattr(t, name))

    _walk(term)
    return types


def _collect_call_targets(clauses: list[Clause]) -> set[tuple[str, int]]:
    """Collect (fname, arity) pairs from Call(LoadName/LoadAttr) nodes in clause bodies.

    Also collects bare LoadName references with dotted names (from
    ``_import_remap``) so that non-callable imports like constants
    (``inf``, ``pi``) get injected into compiled function globals.
    These use arity -1 as a sentinel.

    Used to inject predicate class references (or _DbDispatchAdapter shims)
    into the compiled function's globals so that ``fname._get_dispatch()``
    resolves at runtime.
    """
    targets: set[tuple[str, int]] = set()

    def _walk(term: Any) -> None:
        if isinstance(term, Call) and isinstance(term.func, LoadName):
            n_kwargs = len(term.kwargs) if term.kwargs else 0
            targets.add((term.func.name, len(term.args) + n_kwargs))
        elif isinstance(term, Call) and isinstance(term.func, LoadAttr):
            dotted = _dotted_name_from_loadattr(term.func)
            if dotted is not None:
                n_kwargs = len(term.kwargs) if term.kwargs else 0
                targets.add((dotted, len(term.args) + n_kwargs))
        # Non-Call LoadName with a dot — imported constant/value reference
        elif isinstance(term, LoadName) and "." in term.name:
            targets.add((term.name, -1))
        if isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            for name in term_field_names(term):
                val = getattr(term, name)
                if val is not None:
                    _walk(val)

    for clause in clauses:
        for goal in clause.body:
            _walk(goal)

    return targets


def _collect_globals_info(
    clauses: list[Clause],
) -> tuple[dict[str, type], dict[str, Any], set[tuple[str, int]]]:
    """Single-pass collector replacing three separate traversals.

    Returns ``(types, thunks, targets)`` where:

    * ``types``   — name→type dict for user-defined term classes (from heads and bodies)
    * ``thunks``  — ``_pyt_<id>``→fn dict for PyThunk lambdas (from bodies)
    * ``targets`` — set of ``(fname, arity)`` call targets (from bodies)

    Replaces ``_collect_head_types``, ``_collect_py_thunks``, and
    ``_collect_call_targets`` with a single tree walk.
    """

    types: dict[str, type] = {}
    thunks: dict[str, Any] = {}
    targets: set[tuple[str, int]] = set()

    def _walk_head(term: Any) -> None:
        term = deref(term)
        if isinstance(term, StarUnpack):
            _walk_head(term.value)
        elif isinstance(term, list):
            for e in term:
                _walk_head(e)
        elif is_term_instance(term):
            cls = _record_term_type(types, term)
            for name in term_field_names(term):
                _walk_head(getattr(term, name))
        elif _cell_shape(term)[0]:
            # A CELL.  P3-2 Task 3 fix round 1: this walker and
            # ``head_match``'s live-cell branch have to agree about what a
            # cell IS, and they did not.  The walker treated a ground cell as
            # a LEAF and injected one ``$headlit_<id(whole cell)>``; the head
            # branch matches a cell STRUCTURALLY and asks instead for a
            # ``$headlit_<id(inner value)>`` per opaque slot — which nothing
            # injected, so a head arg like ``pt(1, <a date>)`` compiled to an
            # arm that raised ``NameError`` on its first caller (the
            # retired ``Compound`` twin, which this walker had always recursed
            # into, answered correctly — that asymmetry WAS the bug).
            #
            # So: recurse into the slots, on exactly what ``head_match``'s branch claims (§1b/Task
            # 5: str functor or ``TUPLE_TAG``, slot 0 read raw — this ``elif``
            # is one of three sites folded onto ``cells._cell_shape`` as the
            # shared cell-shape predicate, per the Task 5 carry-forward
            # consolidation; the other two are ``head_match``'s live-cell
            # branch and ``list_dispatch``'s gate helpers).
            for e in term[1:]:
                _walk_head(e)
            # ... AND keep the whole-cell entry, because one shape still
            # reaches the opaque-literal capture below rather than the cell
            # pattern: a ``TUPLE_TAG`` cell compiled where ``$cells`` was not
            # injected.  (Pre-Task-5, a cell whose functor slot was a BOUND
            # Var was a second such shape — read raw, so head_match could not
            # see a str there even though ``is_cell`` answered True for it
            # after a deref: the "T3-to-T5 window".  Task 5 closes that
            # window by retiring the Var-functor cell outright: ``is_cell``
            # now also reads slot 0 raw, so a bound-Var-functor tuple is not
            # a cell ANYWHERE, this ``elif`` included — it takes the
            # ``_is_opaque_head_literal`` branch below like any other plain
            # tuple, uniformly with every other recognition site.  See
            # ``tests/test_tagged_terms.py::TestCellHeadGuardLeaks::
            # test_a_bound_var_functor_cell_head_arg_does_not_crash``.)  An
            # unused entry costs one dict slot; a missing one is a
            # NameError, so it is injected rather than guessed about.
            if _is_opaque_head_literal(term):
                types[headlit_global_key(term)] = term
        elif _is_opaque_head_literal(term):
            # A02-F003: inject opaque ground head literals (date, Decimal,
            # tuple, set, …) so head_to_match_pattern's capture+unify guard can
            # reference them by $headlit_<id>. Keyed to match the guard emitter.
            types[headlit_global_key(term)] = term

    def _walk_body(term: Any) -> None:
        # Call-target detection runs on the raw (pre-deref) term so that
        # Call/LoadName nodes (which are dataclass instances, not Vars) are
        # seen before any potential deref() short-circuits them.
        if isinstance(term, Call) and isinstance(term.func, LoadName):
            n_kwargs = len(term.kwargs) if term.kwargs else 0
            targets.add((term.func.name, len(term.args) + n_kwargs))
        elif isinstance(term, Call) and isinstance(term.func, LoadAttr):
            dotted = _dotted_name_from_loadattr(term.func)
            if dotted is not None:
                n_kwargs = len(term.kwargs) if term.kwargs else 0
                targets.add((dotted, len(term.args) + n_kwargs))
        elif isinstance(term, LoadName) and "." in term.name:
            targets.add((term.name, -1))
        # Deref for type/thunk collection and recursive descent.
        dterm = deref(term)
        if isinstance(dterm, _PyThunk):
            thunks[f"_pyt_{id(dterm)}"] = dterm.fn
        elif isinstance(dterm, list):
            for e in dterm:
                _walk_body(e)
        elif is_term_instance(dterm):
            cls = _record_term_type(types, dterm)
            for name in term_field_names(dterm):
                val = getattr(dterm, name)
                if val is not None:
                    _walk_body(val)
        elif _cell_shape(dterm)[0]:
            # A CELL written as data in a goal argument (the native .pl front
            # end lowers an ISO compound to its cell): its slots can hold a
            # PyThunk (``X is 100 * constant(one_euro)``) that the compiled
            # code reads by its ``_pyt_<id>`` name, so the slots are walked
            # as ``_walk_head`` walks a head cell's.
            for e in dterm[1:]:
                _walk_body(e)

    for clause in clauses:
        _walk_head(clause.head)
        for goal in clause.body:
            _walk_body(goal)

    return types, thunks, targets


def _disp_key(fname: str, arity: int) -> str:
    """Return the base_globals key for a pre-captured dispatch function.

    Used by Phase 7: locked predicates have their dispatch function captured
    into compiled function globals under this key, so generated code can
    reference ``_disp_Foo_2`` directly instead of ``Foo._get_dispatch()``
    on every invocation.
    """
    return f"$disp_{fname.replace('.', '_')}_{arity}"


def _merge_builtin(base_globals: dict, name: str, builtin) -> None:
    """Inject a builtin into base_globals, merging multi-arity builtins."""
    existing = base_globals.get(name)
    if existing is not None and hasattr(existing, "_merge"):
        existing._merge(builtin)
    else:
        base_globals[name] = builtin


# ``_inject_call_targets`` -- the clause-taking twin of
# ``_inject_resolved_targets``, left behind when Phase 6 extracted the
# resolution loop out of it -- is DELETED (P3-3 Task 5b fix round 1, review
# finding F3).  It had no production call sites (only an unused import in
# ``compiler/predicate.py``), so it was exercised by nothing but two
# compiler-level tests, and Task 5b made it a DIVERGED copy rather than a
# merely redundant one: the live loop grew the dotted-key data precedence and
# the ``_atom_shadows_row`` rule and this one did not, so anything read off it
# would have been wrong about what the compiler does.  ``_collect_call_targets``
# above stays -- ``tests/test_compiler_optimizations.py`` uses it as the parity
# oracle for ``_collect_globals_info``'s combined walk.


def _unqualified_other_arity_dispatch(binding, db, name: str, arity: int):
    """The dispatch for an UNQUALIFIED call ``name/arity`` whose name is
    bound to a predicate that is not this name's predicate at *arity*
    (``predicate.binding_grants_arity``).  Re-resolves on every call, in the
    compiling module only: its own row at *arity* (one asserted later
    answers too), else a builtin under *name* (``Database.get_dispatch``
    asks both, row first), else ``predicate._refuse_unqualified_other_arity``
    -- the refusal, never the binding's owner.  Only what cannot go stale is
    cached (review round 5): a builtin, or a LOCKED row's dispatch; an
    unlocked row and "nothing answers" re-resolve per call, so this is safe
    under the ``$disp_`` key.  With no db (a db-less compile) only the builtin
    is asked.
    """
    cached = None
    cached_is_builtin = False

    def dispatch(*args):
        nonlocal cached, cached_is_builtin
        if cached is not None:
            # Round 6: a cached BUILTIN stands only while this db still has
            # no row of its own at name/arity -- an assertz after the first
            # call creates one, and the local row outranks the builtin
            # (solve.call sees it too).  One row() probe per call.
            if not (cached_is_builtin and db.row(name, arity) is not None):
                return cached(*args)
            cached = None
        if db is not None:
            fn = db.get_dispatch(name, arity)      # own row, then builtins
            row = db.row(name, arity) if fn is not None else None
            # Review round 5: cache what cannot change under us -- a BUILTIN
            # (no row of our own answered; re-checked per call, above) or a
            # LOCKED row's dispatch.  An unlocked (dynamic) row may be
            # recompiled or retracted, and "nothing answers" may stop being
            # true, so those re-resolve.
            if fn is not None and (row is None or row.locked):
                cached = fn
                cached_is_builtin = row is None
        else:
            bp = get_builtin_predicate(name, arity, None)
            fn = bp._get_dispatch() if bp is not None else None
            cached = fn
            cached_is_builtin = False      # no db: no local row can appear
        if fn is None:
            fn = _refuse_unqualified_other_arity(binding, name, arity, db)
        return fn(*args)
    dispatch.__qualname__ = f"unqualified_other_arity[{name}/{arity}]"
    return dispatch


def _is_plain_atom_binding(binding, db) -> bool:
    """True for an ATOM binding that is only data: not a predicate handle
    (a mangled str is an atom by shape but names a procedure) and not
    anything else the db sees as a predicate."""
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    return (_term_is_atom(binding) and not is_mangled(binding)
            and not is_declared_predicate_name(binding, db=db))


def _atom_bound_dispatch(atom, db, name: str, arity: int):
    """The dispatch for an UNQUALIFIED call ``name/arity`` whose name is
    bound to an ATOM while the compiling module has no ``name/arity`` row.

    An atom is data and never a call target, and ``_atom_shadows_row`` already
    lets this db's own row win over one -- but only a row present at COMPILE
    time.  The atom may be no more than a same-spelled atom some earlier
    module left in the process-wide pool the module dict is seeded from, so
    a procedure ``assertz`` creates later (under ``assert_creates_dynamic``;
    a ``-dynamic`` declaration makes its row at compile time and never
    reaches here) was shadowed by it, and the answer depended on what the
    process had loaded first.  This re-resolves on every call in the
    compiling module (its own row, then a builtin); only a LOCKED row's
    dispatch is cached, so a call to an asserted (never locked) row pays a
    ``get_dispatch`` and a ``row`` lookup each time.  When nothing answers, the call
    raises exactly what calling the atom always raised
    (``predicate._dispatch_at``'s atom branch).
    """
    from clausal.logic.predicate import _dispatch_at  # noqa: PLC0415
    cached = None

    def dispatch(*args):
        nonlocal cached
        if cached is not None:
            return cached(*args)
        fn = db.get_dispatch(name, arity)          # own row, then builtins
        if fn is not None:
            row = db.row(name, arity)
            if row is not None and row.locked:
                cached = fn
            return fn(*args)
        return _dispatch_at(atom, arity, db)(*args)
    dispatch.__qualname__ = f"atom_bound[{name}/{arity}]"
    return dispatch


def _clausal_module_name_of(value) -> str | None:
    """The Clausal ``Module`` name behind *value* (a ``Module`` or an
    imported ``.clausal`` module object), else None."""
    from clausal.logic.database import Module  # noqa: PLC0415
    if isinstance(value, Module):
        return value.name
    namespace = getattr(value, "__dict__", None)
    if isinstance(namespace, dict):
        for key in ("$module", "__clausal_module__"):
            mod = namespace.get(key)
            if isinstance(mod, Module):
                return mod.name
    return None


def _unresolved_qualified_dispatch(dotted: str, arity: int, globals_, db):
    """The dispatch for a module-qualified call ``m.name(...)`` at *arity*
    that resolved to nothing when the clause set was compiled.

    Operator ruling 2026-09-25 (Scryer): the call raises
    ``error(existence_error(procedure, name/Arity), Why)`` -- the bare
    indicator, the module named in the message only (ruling 2026-09-24, the
    shape a dangling predicate handle raises) -- as a
    ``PredicateNotFoundError``, the same Python type an unqualified unknown
    call raises.

    The base is resolved on EVERY call, never once at compile time (roborev,
    round 2): a base module that loads after this clause set compiled (a lazy
    or circular import) must answer once it has loaded.  When the base is a
    loaded Clausal module the call goes through that module's predicate
    HANDLE (``predicate._dispatch_at``, W4), so a predicate asserted into the
    module afterwards answers too, and a miss raises the handle route's own
    error.  Any other base (not loaded, or not a Clausal module) raises the
    same term directly.  This is the refusal path, so the walk costs nothing
    on a call that resolves.
    """
    parts = dotted.split(".")
    base_path, name = ".".join(parts[:-1]), parts[-1]

    def resolve_base():
        base = globals_.get(parts[0]) if globals_ else None
        for part in parts[1:-1]:
            if base is None:
                break
            base = getattr(base, part, None)
        if base is None:
            base = _sys.modules.get(base_path)
        return base

    def dispatch(*args):
        base = resolve_base()
        module_name = _clausal_module_name_of(base)
        if module_name is not None:
            from clausal.logic.atoms import mangle  # noqa: PLC0415
            from clausal.logic.predicate import _dispatch_at  # noqa: PLC0415
            return _dispatch_at(mangle(module_name, name), arity, db)(*args)
        from clausal.logic.exceptions import (  # noqa: PLC0415
            dangling_handle_indicator_and_why,
        )
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            PredicateNotFoundError,
        )
        _indicator, why = dangling_handle_indicator_and_why(
            base_path, name, arity, loaded=False)
        if base is not None:
            why = f"{name}/{arity} is not a predicate of {base_path!r}"
        raise PredicateNotFoundError(
            f"{why} (a module-qualified call {dotted}/{arity})", name, arity)
    dispatch.__qualname__ = f"unresolved_qualified[{dotted}/{arity}]"
    return dispatch


def _is_call_target(binding, arity: int, db=None, name=None) -> bool:
    """True when *binding* is what an APPLIED reference at *arity* calls.

    W4b-3 ruling (operator, 2026-09-24): a predicate name is name + ARITY.
    A predicate binding -- a ``PredicateMeta`` class today, a module-qualified
    HANDLE after the flip, alike -- is this call's target only when it is
    declared at exactly *arity*; at any other arity the call resolves
    normally (a builtin, this db's own row, ...), and the class-era
    ``PredicateArityMismatchError`` refusal was an artefact of the predicate
    being a class.  A data reference (*arity* < 0) has no arity to match.
    Every other ``_get_dispatch`` implementor (``BuiltinPredicate``, the
    foreign duck-typed ones) is accepted as before.

    With *db* and *name* (an UNQUALIFIED name in the module being compiled),
    an IMPORTED binding is the target only at an arity it was imported at
    (``predicate.binding_grants_arity``, aliased-import ruling 2026-09-24):
    the owner's other arities are not imported, in either era.  A dotted
    name passes neither -- it is the qualifier's, owner arities included.
    """
    if is_declared_predicate_name(binding, db=db):
        if arity < 0:
            return True
        if name is not None:
            return binding_grants_arity(binding, arity, db, name)
        return is_declared_predicate(binding, arity=arity, db=db)
    return hasattr(binding, "_get_dispatch")


def _atom_shadows_row(binding, db, name: str, arity: int) -> bool:
    """True when an ATOM module binding is hiding this db's own ``name/arity``.

    P3-3 Task 5b.  An ATOM is DATA and can never be a call target: reaching it
    from a call site raises ``existence_error`` out of ``predicate.
    _dispatch_at``'s atom branch.  When the very database being compiled
    defines ``name/arity``, the call site means THAT predicate -- resolution
    is keyed on ``(name, arity)`` and an atom has no arity-N meaning -- so the
    atom loses and the db adapter answers.

    Narrow on both axes: only an ATOM binding (every other shape, callable
    or not, is trusted exactly as before), and only when the row is really
    there (``row``, not ``get_dispatch``, so asking compiles nothing).  A
    call on an atom that names no local predicate keeps its existing,
    positioned diagnostic.

    2026-09-06-atoms-as-cells-strings, Task 9: the shape question is asked of
    ``atoms.is_atom`` -- the TERM test, which under Plan 0 is exactly the
    ``type(binding) is str`` this replaces, and which at Stage B admits the
    arity-0 cell.  Deliberately NOT ``predicate.is_atom_value``: that widens
    to a zero-field ``PredicateMeta``, which IS a live call target here.
    """
    # W4b-3 ruling: a PREDICATE binding (class or handle) declared at
    # ANOTHER arity is not this call's target, so this db's own
    # ``name/arity`` wins over it exactly as over an atom; one declared at
    # this very arity IS the target and is never shadowed.
    return (
        (_term_is_atom(binding) or is_declared_predicate_name(binding, db=db))
        and not (arity >= 0 and binding_grants_arity(binding, arity, db, name))
        and db is not None
        and arity >= 0
        and db.row(name, arity) is not None
    )


def _inject_resolved_targets(
    targets: set[tuple[str, int]],
    base_globals: dict,
    db: "Database | None",
    globals_: dict | None,
) -> None:
    """Resolve pre-collected call targets into base_globals.

    Phase 6: the resolution loop extracted from the clause-taking
    ``_inject_call_targets`` (deleted -- see the note above) so it
    can be called with targets already gathered by ``_collect_globals_info``,
    avoiding a fourth clause traversal.

    Phase 7: for each resolved target whose ``PredRow`` is locked,
    additionally captures its dispatch function under ``$disp_{fname}_{arity}`` (``_disp_key``)
    in ``base_globals``.  Generated code can then reference the dispatch
    function directly instead of calling ``_get_dispatch()`` on every
    predicate invocation.
    """

    def _maybe_cache_dispatch(obj: Any, name: str, arity: int) -> None:
        """Phase 7: if obj is a locked, compiled PredicateMeta, cache its dispatch.

        Not when *arity* disagrees with the predicate's own: caching there
        would bind ``$disp_citation_2`` to ``citation/3``'s dispatch function
        and the call site would jump straight into it, past the arity check
        ``_get_dispatch`` exists to make.  Leaving the key unset costs that one
        call site the fast path and gains it a message that names the fault.

        P3-3 Task 4: the two questions that decide the bake — "is this
        predicate closed?" and "what is its dispatch?" — are asked of the
        :class:`~clausal.logic.database.PredRow`, the single home of
        predicate state since Task 2, rather than of class attributes that
        forward there.  The row is the CLASS's own (``obj._row``), not
        ``db.row(name, arity)``: the call site this key serves resolves to
        THIS class, so it is this class's row whose dispatch may be baked
        under the key.  A same-named predicate in the compiling module's own
        Database is a different predicate, and baking its dispatch here would
        silently redirect the call to it.

        Only a LOCKED row is ever baked, and that is the whole staleness
        argument: an unlocked row's dispatch may be replaced or cleared at
        any moment, so ``row.invalidate()`` on one can never orphan a baked
        reference — there is none to orphan.
        """
        # W4b-2b: is_declared_predicate composes to the same
        # `arity == obj._arity` test this used to spell by hand
        # (`obj._arity` is `len(obj._fields)`, identical by construction --
        # see predicate.py's own note on the two spellings), era-agnostic;
        # resolve_predicate_row replaces the raw `obj._row` read.
        if not (arity >= 0 and is_declared_predicate(obj, arity=arity, db=db)):
            return
        row = resolve_predicate_row(obj, arity=arity, db=db)
        if row is None or not row.locked:
            return
        dispatch = row.dispatch_fn
        if dispatch is not None:
            base_globals[_disp_key(name, arity)] = dispatch

    # P3-3 Task 5b: the names this clause set APPLIES, as opposed to merely
    # reads.  ``_collect_globals_info`` yields a dotted name twice for an
    # applied reference -- once at its call arity and once at -1 for the
    # ``LoadName`` inside the ``Call`` -- so "is this name ever called here"
    # has to be asked of the whole target set, not of one target at a time.
    called_names = {name for name, arity in targets if arity >= 0}
    for target_name, target_arity in targets:
        existing = base_globals.get(target_name)
        # W4b-3: after the flip a predicate's binding is a module-qualified
        # HANDLE with no ``_get_dispatch``.  Unaccepted here it falls through
        # to the builtin lookup below (a same-named builtin then wins over the
        # user predicate) and a locked predicate loses its ``$disp_`` bake.
        # An APPLIED target accepts a predicate binding -- class or handle
        # alike -- only at its own arity (``_is_call_target``); at another
        # arity it falls through to the builtin lookup / ``_atom_shadows_row``
        # / the dotted routing like any non-predicate binding.
        if existing is not None and _is_call_target(
                existing, target_arity, db,
                None if "." in target_name else target_name):
            if isinstance(existing, BuiltinPredicate):
                builtin = get_builtin_predicate(target_name, target_arity, db)
                if builtin is not None and builtin._arity != existing._arity:
                    existing._merge(builtin)
            else:
                # Phase 7: cache dispatch for locked predicates already in base_globals
                # (e.g. injected from globals_ by the caller before _inject_resolved_targets).
                _maybe_cache_dispatch(existing, target_name, target_arity)
            continue
        if "." in target_name:
            # P3-3 Task 5b: for a DATA reference (arity -1) this module's OWN
            # binding for the dotted key wins over the attribute walk below.
            # ``-import_from`` writes that exact key (``compiler_v2.
            # _process_imports``) and it is the key the import remap emits for
            # every reference to the imported spelling, so it is where a
            # decision about what that spelling MEANS here belongs -- an
            # owner-declared atom that also carries /0 clauses binds the atom
            # str there while the owner's own module attribute stays the
            # predicate class.  The two agree for every other import, so this
            # only re-orders a question that used to have one answer; a dotted
            # reference the import machinery did NOT bind
            # (``-import_module``'s ``graphs.Path``, ``py.sympy.inf``) is
            # absent from this dict and falls through unchanged.
            #
            # A name that is also APPLIED in this predicate keeps the
            # attribute — one globals key cannot hold two answers, and the
            # applied form's own diagnostic (``PredicateMeta``'s "takes 0
            # arguments, but this call passes 1") is the better one.  Deciding
            # it from ``called_names`` rather than from whichever of the two
            # targets the set happened to yield last is what makes that
            # deterministic.
            if target_arity < 0 and target_name not in called_names:
                own = globals_.get(target_name) if globals_ else None
                if own is not None:
                    base_globals[target_name] = own
                    continue
            parts = target_name.split(".")
            obj = globals_.get(parts[0]) if globals_ else None
            parent = None
            for part in parts[1:]:
                if obj is None:
                    break
                parent = obj
                obj = getattr(obj, part, None)
            if (target_arity >= 0 and parent is not None and obj is not None
                    and is_pool_seeded_atom(getattr(parent, "__dict__", None),
                                            parts[-1])):
                # ``m.nosuch(1)`` where m only has ``nosuch`` because the
                # atom pool seeded it (another module declared the atom):
                # not m's data reference -- resolve as the unknown call it is.
                obj = None
            # W4b-3: a predicate HANDLE (post-flip module attribute) is
            # accepted and cached exactly as the class is, at its own arity.
            # At another arity the object is still kept (next branch): a
            # dotted name has no other resolution -- no builtin is dotted --
            # so the call reports the arity at run time.
            if obj is not None and _is_call_target(obj, target_arity, db):
                base_globals[target_name] = obj
                _maybe_cache_dispatch(obj, target_name, target_arity)
                continue
            if obj is not None:
                base_globals[target_name] = obj
                continue
            mod_path = ".".join(parts[:-1])
            attr_name = parts[-1]
            mod_obj = _sys.modules.get(mod_path)
            if mod_obj is not None:
                resolved = getattr(mod_obj, attr_name, None)
                if (target_arity >= 0 and resolved is not None
                        and is_pool_seeded_atom(
                            getattr(mod_obj, "__dict__", None), attr_name)):
                    resolved = None                 # see the walk above
                if resolved is not None and _is_call_target(
                        resolved, target_arity, db):   # W4b-3
                    base_globals[target_name] = resolved
                    _maybe_cache_dispatch(resolved, target_name, target_arity)
                    continue
            builtin = get_builtin_predicate(target_name, target_arity, db)
            if builtin is not None:
                _merge_builtin(base_globals, target_name, builtin)
            elif (mod_obj is not None and resolved is not None
                    and is_declared_predicate_name(resolved, db=db)):
                # W4b-3: a predicate at ANOTHER arity, and nothing else
                # answers a dotted name: keep it (as the attribute walk
                # keeps its object) so the call reports the arity at run
                # time instead of a NameError.
                base_globals[target_name] = resolved
            elif target_arity >= 0 and target_name not in base_globals:
                # Operator ruling 2026-09-25: a call of an unknown procedure
                # raises ISO existence_error(procedure, Name/Arity), like
                # Scryer -- and a module-qualified ``m.nosuch(1)`` is such a
                # call.  It used to die on CPython's bare ``NameError: name
                # 'm.nosuch' is not defined`` (the name key was never bound),
                # which ``catch/3`` could only see transliterated.  The goal
                # emitters prefer a ``$disp_`` key, so the refusal lives
                # THERE, per arity; the NAME key stays unbound, so a Python
                # use of the name (a term construction, an arithmetic call)
                # still raises exactly the NameError it always did.
                base_globals[_disp_key(target_name, target_arity)] = (
                    _unresolved_qualified_dispatch(
                        target_name, target_arity, globals_, db))
            continue
        # Name + ARITY ruling (operator, 2026-09-24, with the aliased-import
        # ruling and review rounds 2-4): an UNQUALIFIED call site at an arity
        # its PREDICATE binding (class or handle) is not this name's
        # predicate at (``_is_call_target`` above said no) resolves in THIS
        # module under THIS name -- this db's own row, then a builtin under
        # the name, else the arity refusal naming the name; never the
        # binding's owner.  All of that lives in ONE ``$disp_name_N`` entry
        # (``_unqualified_other_arity_dispatch``, re-resolving per call),
        # which the goal emitters prefer over ``$dispatch_at(name, N)``.
        #
        # The NAME key is never touched: it keeps the binding, which other
        # goals of this same clause set use at the binding's own arity and
        # for TERM CONSTRUCTION (``T = last(1)``).  Replacing it -- with a
        # ``_DbDispatchAdapter`` (arity-blind ``_get_dispatch``, NameError on
        # construction) or a merged builtin -- broke those, depending on the
        # order this loop happened to visit ``(name, 1)`` and ``(name, 2)``
        # (roborev round 4).  A class's ``_fields`` can be stale
        # (``PredicateMeta._clause_arity``); the local row answering first
        # covers that too.  An ATOM binding keeps its builtin-first order.
        binding = existing
        if binding is None and globals_:
            binding = globals_.get(target_name)
        if (target_arity >= 0 and binding is not None
                and is_declared_predicate_name(binding, db=db)
                and not _is_call_target(binding, target_arity, db,
                                        target_name)):
            base_globals.setdefault(target_name, binding)
            base_globals[_disp_key(target_name, target_arity)] = (
                _unqualified_other_arity_dispatch(
                    binding, db, target_name, target_arity))
            continue
        builtin = get_builtin_predicate(target_name, target_arity, db)
        if builtin is not None:
            _merge_builtin(base_globals, target_name, builtin)
            continue
        if (target_arity >= 0 and db is not None and globals_
                and target_name in globals_
                and _is_plain_atom_binding(globals_[target_name], db)
                and db.row(target_name, target_arity) is None):
            # An ATOM binding with no row behind it YET: the module dict is
            # seeded from the process-wide atom pool, so the binding may be
            # nothing more than another module's atom of the same spelling,
            # and a procedure ``assertz`` creates later must still answer
            # the call.  The NAME key keeps the atom (term construction and
            # data references read it); the call re-resolves per call.
            base_globals[target_name] = globals_[target_name]
            base_globals[_disp_key(target_name, target_arity)] = (
                _atom_bound_dispatch(globals_[target_name], db, target_name,
                                     target_arity))
            continue
        if globals_ and target_name in globals_ and not _atom_shadows_row(
            globals_[target_name], db, target_name, target_arity
        ):
            obj = globals_[target_name]
            base_globals[target_name] = obj
            _maybe_cache_dispatch(obj, target_name, target_arity)
        elif db is not None:
            obj = _DbDispatchAdapter(db, target_name, target_arity)
            base_globals[target_name] = obj


def _preallocate_body_vars(
    goals: list,
    var_context: dict[int, str],
) -> list[ast.stmt]:
    """Pre-scan goals left-to-right; emit ``_vN = Var()`` for body-only Vars.

    Populates ``var_context`` for every Var found in the goals so that
    subsequent right-to-left compilation sees them as already-known (name
    reference) rather than body-only (walrus).  Returns the list of allocation
    statements to prepend to the compiled body.

    This prevents the UnboundLocalError that arises when a Var first appears as
    an argument to an outer goal but gets walrus-assigned inside an inner goal
    due to right-to-left compilation order.
    """
    stmts: list[ast.stmt] = []
    seen: set[int] = set(var_context.keys())  # head Vars already allocated
    for goal in goals:
        for var in _collect_vars(goal, seen):
            if var._id not in var_context:
                name = _var_python_name(var)
                var_context[var._id] = name
                stmts.append(_assign(name, _call(_name("$Var"))))
    return stmts
