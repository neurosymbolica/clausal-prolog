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

from clausal.logic.variables import deref
from clausal.terms import (
    Compound,
    Call, LoadName, LoadAttr,
    PyThunk,
)
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import (
    PredicateMeta, is_term_instance, term_field_names,
)
from clausal.logic.builtins import (
    get_builtin_predicate, BuiltinPredicate,
)

from clausal.logic.cells import _cell_shape

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
    from clausal.logic.builtins._helpers import _standard_order_sorted  # noqa: PLC0415
    return _set_of_dedup(_standard_order_sorted(items))


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
        raise NameError(
            f"Predicate '{self._functor}/{self._arity}' is not in scope as a term class.\n"
            f"To construct a '{self._functor}' goal term, import it first, e.g.:\n"
            f"  from your_module import {self._functor}",
            name=self._functor,
        )


class _GlobalsDb:
    """Minimal db-like proxy for signature lookup from module globals.

    Used by compile_predicate when ``db=None`` — looks up ``_signature`` from
    PredicateMeta classes found in the provided globals dict.  Only
    ``signature_for`` is implemented; other Database methods are not needed
    when compiling without a live database.
    """
    __slots__ = ("_globals",)

    def __init__(self, globals_dict: dict) -> None:
        self._globals = globals_dict

    def signature_for(self, functor: str, arity: int):
        cls = self._globals.get(functor)
        if isinstance(cls, PredicateMeta):
            return cls._signature
        return None


def _record_term_type(types: dict[str, type], term: Any) -> type:
    """Record *term*'s class under its ``__name__`` key and return that class.

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
    types[cls.__name__] = cls
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
        elif isinstance(term, Compound):
            for a in term.args:
                _walk(a)
        elif isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            cls = _record_term_type(types, term)
            for name in term_field_names(term):
                _walk(getattr(term, name))

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
        elif isinstance(term, Compound):
            for a in term.args:
                _walk(a)
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
        elif isinstance(t, Compound):
            for a in t.args:
                _walk(a)
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
        elif isinstance(term, Compound):
            for a in term.args:
                _walk_head(a)
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
            # ``Compound`` twin, which this walker has always recursed into,
            # answered correctly — that asymmetry WAS the bug).
            #
            # So: recurse into the slots, mirroring the ``Compound`` branch
            # above, on exactly what ``head_match``'s branch claims (§1b/Task
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
        elif isinstance(dterm, Compound):
            for a in dterm.args:
                _walk_body(a)
        elif isinstance(dterm, list):
            for e in dterm:
                _walk_body(e)
        elif is_term_instance(dterm):
            cls = _record_term_type(types, dterm)
            for name in term_field_names(dterm):
                val = getattr(dterm, name)
                if val is not None:
                    _walk_body(val)

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


def _atom_shadows_row(binding, db, name: str, arity: int) -> bool:
    """True when a ``str`` module binding is hiding this db's own ``name/arity``.

    P3-3 Task 5b.  Post-pivot an ATOM is a plain ``str`` (§1b/R2), so a module
    binding of that shape is DATA and can never be a call target: reaching it
    from a call site raises ``existence_error`` out of ``predicate.
    _dispatch_at``'s str branch.  When the very database being compiled
    defines ``name/arity``, the call site means THAT predicate -- resolution
    is keyed on ``(name, arity)`` and an atom has no arity-N meaning -- so the
    str loses and the db adapter answers.

    Narrow on both axes: only a ``str`` binding (every other shape, callable
    or not, is trusted exactly as before), and only when the row is really
    there (``row``, not ``get_dispatch``, so asking compiles nothing).  A
    call on an atom that names no local predicate keeps its existing,
    positioned diagnostic.
    """
    return (
        type(binding) is str
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
    additionally captures its dispatch function under ``_disp_{fname}_{arity}``
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
        if not (
            arity >= 0
            and isinstance(obj, PredicateMeta)
            and arity == obj._arity
        ):
            return
        row = obj._row
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
        if existing is not None and hasattr(existing, "_get_dispatch"):
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
            for part in parts[1:]:
                if obj is None:
                    break
                obj = getattr(obj, part, None)
            if obj is not None and hasattr(obj, "_get_dispatch"):
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
                if resolved is not None and hasattr(resolved, "_get_dispatch"):
                    base_globals[target_name] = resolved
                    _maybe_cache_dispatch(resolved, target_name, target_arity)
                    continue
            builtin = get_builtin_predicate(target_name, target_arity, db)
            if builtin is not None:
                _merge_builtin(base_globals, target_name, builtin)
            continue
        builtin = get_builtin_predicate(target_name, target_arity, db)
        if builtin is not None:
            _merge_builtin(base_globals, target_name, builtin)
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
                stmts.append(_assign(name, _call(_name("Var"))))
    return stmts
