"""clausal.logic.solve — top-level query API (Step 7).

Public API
----------
solve(goal, module=None, trail=None)             → Iterator[Trail]
once(goal, module=None, trail=None)              → Trail | None
query(goal, variables, module=None, trail=None)  → Iterator[dict[str, Any]]
call(functor, *args, module, trail=None)         → Iterator[Trail]

The ``module`` argument is optional for ``solve``, ``once``, and ``query``:
when omitted, the module is inferred from the PredicateMeta classes in the
goal term.  You can also pass an imported ``.clausal`` Python module directly
(e.g. ``import hello; solve(greeting(X), hello)``), or its dotted name as a
str (``solve(("greeting", X), "hello")``) — see ``resolve_module``, which is
also what the module-qualified goal ``(":", M, G)`` resolves *M* with.

Design
------
``solve`` handles arbitrary goal terms — both simple_ast nodes (Call, And, Or,
…) and runtime PredicateMeta instances (e.g. ``greeting(X := Var())``).
Runtime terms are converted to simple_ast nodes automatically.  Vars embedded
in the goal are injected into the compiled function's globals so that the
compiled code references the *user's* Var objects.  This lets the user read
bindings via ``deref()`` on their original Var objects after each solution.

``once`` returns the Trail for the first solution (bindings still live),
or None if the goal fails.

``query`` wraps solve and fully dereferences a named set of variables,
returning a plain dict per solution.

``call`` drives a named predicate's compiled dispatch function directly.
The user passes Var objects as args.  This is the fastest path for simple
predicate calls.
"""

from __future__ import annotations

import datetime as _datetime
import sys
import types as _types
from typing import Any, Iterator

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _spelling
from clausal.logic.database import Clause, Database, Module
from clausal.logic.predicate import (
    is_term_instance, term_field_names, _dispatch_at,
)
from clausal.logic.trampoline import StepGenerator, DONE, _drive_until_yield
from clausal.logic.cells import (
    CELL_GOAL_CONTROL_FUNCTORS,
    QUALIFIED_GOAL_FUNCTOR,
    compound_cell_shape,
    refuse_control_construct_cell,
    resolve_qualified_goal_cell,
)
from clausal.terms import Compound, Undefined
from clausal.terms import (
    Call as _ReifiedCall,
    LoadName as _ReifiedLoadName,
    LoadAttr as _ReifiedLoadAttr,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _deref_walk_py(term: Any) -> Any:
    """Fully dereference a term, recursively walking all Var bindings.

    Unbound Vars remain as Var objects in the result.
    """
    term = deref(term)
    if is_var(term):
        return term
    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return term
    if isinstance(term, list):
        return [_deref_walk_py(e) for e in term]
    if isinstance(term, tuple):
        return tuple(_deref_walk_py(e) for e in term)  # A01-F008: was blind
    if isinstance(term, dict):
        # A04-F005: rebuild plain-dict values so a frozen answer holding a dict
        # does not share live inner Vars that unbind on backtracking.
        return {_deref_walk_py(k): _deref_walk_py(v) for k, v in term.items()}
    if isinstance(term, (set, frozenset)):
        return type(term)(_deref_walk_py(e) for e in term)  # A04-F005
    # A01-F008: delegate to __walk__ hooks (Compound, KWTerm, DictTerm, Seg*),
    # keeping this Python fallback in sync with the C twin (_tabling_core
    # do_deref_walk) and with walk() itself. Preserves Compound _position and
    # F018 Seg promotion.
    hook = getattr(term, "__walk__", None)
    if hook is not None:
        return hook()
    if is_term_instance(term):
        cls = type(term)
        # Phase 0 fast-path gate -- KEEP ALL FIVE WALKERS IN SYNC. The five
        # sites are: this function (_deref_walk_py), inspection.py's
        # _copy_term_py, and their three C twins -- _variables.c do_walk
        # (~1735), _variables.c c_copy_term (~3002), and _tabling_core.c
        # do_deref_walk (~441). This docstring/comment is the single source
        # of truth for the gate rule; the C sites' comments point back here
        # rather than restating it.
        #
        # The rule: cls's OWN dict (never an inherited attribute -- `vars(cls)`
        # in Python, `PyType_GetDict` + `PyDict_GetItemRef` on the type's own
        # dict in C) has "_clausal_new" bound as a classmethod iff
        # PredicateMeta attached the positional-args fast constructor. When
        # it does, walk/copy the fields positionally and call
        # `cls._clausal_new(*args)`; otherwise fall back to the slow,
        # kwargs-based `cls(**kwargs)` reconstruction.
        fast = vars(cls).get("_clausal_new")
        if isinstance(fast, classmethod):
            return cls._clausal_new(*(
                _deref_walk_py(getattr(term, name))
                for name in term_field_names(term)
            ))
        return cls(**{
            name: _deref_walk_py(getattr(term, name))
            for name in term_field_names(term)
        })
    return term

_deref_walk = _deref_walk_py

try:
    from clausal.logic._tabling_core import _deref_walk as _deref_walk_c
    _deref_walk = _deref_walk_c
except ImportError:
    pass


def _drive_trampoline(dispatch_fn: Any, trail: Trail, *args: Any) -> Iterator[Trail]:
    """Drive a trampoline-protocol dispatch function, yielding trail per solution."""
    from clausal.logic.tabling import begin_drive_episode, end_drive_episode

    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    begin_drive_episode()
    try:
        while True:
            result = _drive_until_yield(sg)
            if result is None:
                return
            yield trail
    except NameError as exc:
        # Failure-only seam, and the only one solve time needs: this is the
        # outermost driver, so a NameError arriving here has already escaped
        # every catch/3 below it and is on its way to the author.  The hunt it
        # triggers reads sibling ``-module(...)`` lists off disk, which is why
        # it sits in an ``except`` and not on the loop — a solution costs
        # nothing, a raise pays once.
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            enrich_undefined_name,
        )
        better = enrich_undefined_name(exc)
        if better is None:
            raise
        # Re-raise on the ORIGINAL traceback so the frame still points at the
        # clause that used the name, and suppress the chained duplicate — the
        # replacement carries the same args.
        raise better.with_traceback(exc.__traceback__) from None
    finally:
        # A04-F007: close the root generator on ANY exit — normal, caller
        # abandonment (GeneratorExit), or a body exception that propagated past
        # the trampoline. This synchronously runs the tabled-wrapper cleanup
        # (drop a poisoned "evaluating" entry) instead of leaving it to GC.
        # close() is NOT sufficient on its own: it closes only sg's inner
        # generator, and a SuspendedConsumer registered on a table entry keeps
        # a parked tabled-wrapper frame reachable forever, so GeneratorExit
        # never reaches that wrapper's repair code. end_drive_episode() then
        # drops any still-"evaluating" entry this drive created (store, leader
        # stack, suspended consumers) so later queries recompute instead of
        # silently consuming the partial answer set.
        try:
            sg.close()
        finally:
            end_drive_episode()


def _term_to_goal(term: Any) -> Any:
    """Convert a runtime term instance to a simple_ast goal node.

    When the user writes ``solve(greeting(N := Var()))``, ``greeting(N)``
    produces a PredicateMeta *instance* (a runtime term), not a simple_ast
    ``Call`` node.  The compiler expects goal nodes, so we convert here.
    A CELL goal ``("f", a, b)`` lowers the same way (P3-3 Task 5, R11): slot 0
    names the predicate, the rest are its arguments, so it becomes
    ``AstCall(LoadName("f"), [a, b])`` — the identical node a ``Compound`` goal
    produces, which is what makes a cell goal and a class-term goal share
    compiled code and answer alike.  Two cell functors are not ordinary calls
    and are handled before that: the module-qualified form ``(":", M, G)``,
    which lowers to the INNER goal's node (P3-3 Task 6), and the control
    constructs (deferred to the ISO-surface phase) — see
    ``cells.resolve_qualified_goal_cell`` and
    ``cells.refuse_control_construct_cell``.

    A qualified goal's module SWITCH is not made here — this function lowers a
    term to a node and has no say in which database the node compiles against.
    ``_strip_module_qualification`` makes it, in ``_compile_as_query``, before
    this function is reached, so on the query path the qualification is
    already gone by the time it arrives.  The branch below is what keeps the
    lowering total for a direct caller (and keeps the designator validated
    wherever the term is lowered): it resolves, which is what raises on an
    unresolvable module, then lowers the inner goal.

    Simple_ast nodes and other goal forms pass through unchanged.
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.pythonic_ast.nodes import Call as AstCall, LoadName

    if type(term) is str:
        # THE FLIP (spec §6.4): a ``str`` is a STRING, not an atom, and a
        # string is not callable.  ``solve("z0", m)`` used to be the same
        # call as ``solve(("z0",), m)``; it is now a type error, and the
        # cell spelling is the only one that names a goal.
        from clausal.logic.exceptions import LogicException, type_error
        raise LogicException(type_error("callable", term, "solve/1"))
    if isinstance(type(term), PredicateMeta):
        cls = type(term)
        fields = term_field_names(term)
        args = [getattr(term, f) for f in fields]
        return AstCall(func=LoadName(name=cls.__name__), args=args, kwargs=[])
    if isinstance(term, Compound):
        return AstCall(
            func=LoadName(name=term.functor),
            args=list(term.args),
            kwargs=[],
        )
    is_cell_goal, functor = compound_cell_shape(term)
    if is_cell_goal:
        if functor == QUALIFIED_GOAL_FUNCTOR and len(term) == 3:
            _module, inner = resolve_qualified_goal_cell(term, "solve/1")
            return _term_to_goal(inner)
        refuse_control_construct_cell(term, functor, "solve/1")
        return AstCall(
            func=LoadName(name=functor), args=list(term[1:]), kwargs=[],
        )
    return term


_VAR_SENTINEL = object()

# Cache: (structural_key, module_id) → (fn, code_object, var_names)
_query_cache: dict = {}

# Upper bound on distinct cached query shapes; see eviction note at the
# insertion site in _compile_as_query.
_QUERY_CACHE_MAX = 4096


class _Uncacheable(Exception):
    """Raised internally when a goal contains a ground leaf we cannot key on."""


def _structural_key(term: Any, var_index: dict) -> tuple:
    """Recursively canonicalise a goal term into a hashable structural key.

    The compiled query bakes ground arguments into the generated code as literal
    constants, while logic variables become rebindable globals (remapped on a
    cache hit).  So two goals may share compiled code *only* when they have the
    same structure, the same ground literal *values* (not merely the same
    types), and variables in the same positions.  This key captures all three:

      - variables become ``('var', n)`` where ``n`` is the first-occurrence index,
        so ``p(V, V)`` (aliased) and ``p(V, W)`` (distinct) get different keys;
      - ground leaves become ``('lit', type, value)`` — keying on the value, which
        is what distinguishes ``p(1, V)`` from ``p(2, V)``;
      - compound/predicate/sequence terms recurse structurally;
      - a CELL gets its own ``('cell', functor, args)`` tag rather than falling
        into the ``('seq', tuple, ...)`` branch below (P3-3 Task 5).  A cell in
        GOAL position compiles to a CALL, while the equal-shaped tuple in
        argument position is baked as tuple DATA — two different compiled
        artifacts, so they get two different tags rather than one that reads
        "a tuple of N+1 elements" for both.  (There is no live collision to
        repair: ``_goal_cache_key`` admits only goal shapes, and a data tuple
        is never a top-level goal.  The tag is what keeps that true.)

    Raises :class:`_Uncacheable` if a ground leaf is unhashable (e.g. a list,
    dict, or ndarray argument), in which case the caller skips caching entirely
    rather than risk a stale or colliding entry.
    """
    from clausal.logic.predicate import PredicateMeta

    t = deref(term)
    if is_var(t):
        idx = var_index.get(id(t))
        if idx is None:
            idx = len(var_index)
            var_index[id(t)] = idx
        return ("var", idx)
    if isinstance(type(t), PredicateMeta):
        return ("pred", type(t),
                tuple(_structural_key(getattr(t, f), var_index)
                      for f in term_field_names(t)))
    if isinstance(t, Compound):
        return ("cmp", t.functor,
                tuple(_structural_key(a, var_index) for a in t.args))
    if isinstance(t, (list, tuple)):
        is_cell, functor = compound_cell_shape(t)
        if is_cell:
            return ("cell", functor,
                    tuple(_structural_key(x, var_index) for x in t[1:]))
        return ("seq", type(t),
                tuple(_structural_key(x, var_index) for x in t))
    try:
        hash(t)
    except TypeError as e:
        raise _Uncacheable() from e
    return ("lit", type(t), t)


def _goal_cache_key(goal: Any, module: Module):
    """Structural, value-sensitive cache key for a top-level query goal.

    Returns ``None`` (caching disabled for this goal) when the goal is neither a
    predicate term, a Compound, nor a CELL, or when it contains an unhashable
    ground leaf.

    Cells were previously in the "neither" bucket and so were uncached
    outright; they are hashable tuples with the same structural discipline as
    a Compound, and ``_structural_key`` gives them their own ``('cell', ...)``
    tag, so a cell goal caches like any other predicate call (P3-3 Task 5).
    """
    from clausal.logic.predicate import PredicateMeta
    if not (isinstance(type(goal), PredicateMeta)
            or isinstance(goal, Compound)
            or compound_cell_shape(goal)[0]):
        return None
    try:
        return (_structural_key(goal, {}), id(module))
    except _Uncacheable:
        return None


# The datetime scalar types _templatize_query_goal parameterizes (see
# _ground_value): first-class value terms the input-lowering path otherwise
# rejects. Exact types — subclasses are deliberately excluded.
_DATETIME_QUERY_SCALARS = (
    _datetime.date, _datetime.datetime, _datetime.time, _datetime.timedelta,
)


def _templatize_query_goal(goal: Any):
    """Parameterize the fully-ground top-level arguments of a predicate-call goal.

    Returns ``(template_goal, [(param_var, value), ...])``. Each direct argument
    of a single predicate-call goal (PredicateMeta instance or Compound) that is
    fully ground is replaced with a fresh unbound Var; the var is bound to that
    value at run time (see ``solve``). The compiled query therefore contains no
    baked-in argument literals and is reused across calls that differ only in
    their ground arguments — instead of recompiling once per distinct value.

    Composite/control/arithmetic goals are returned unchanged (``params`` empty);
    they keep the value-keyed cache as a correct fallback.
    """
    from clausal.logic.predicate import PredicateMeta, is_zero_field_class

    def _ground_value(val):
        """Return the scalar ground value to parameterize, or None to leave it.

        Only plain scalar literals and zero-arity atoms are parameterized: they
        unify directly with a head literal regardless of mode.  Structural args
        (list/dict/compound) are *not* parameterized because the literal-baking
        path rewrites them (e.g. a list literal becomes cons cells) — a raw value
        bound to a Var would not match the rewritten head pattern.  Those keep the
        value-keyed cache fallback.

        Atoms (zero-arity ``PredicateMeta`` classes) are parameterized so the
        atom *object* is passed in as a bound arg rather than baked into the
        compiled query as a bare ``Name(atom.__name__)`` — the latter raises
        ``NameError`` for a cross-module atom whose bare name is not in the
        target function's globals (e.g. imported via ``-import_module`` only).
        """
        dv = deref(val)
        if is_var(dv):
            return None
        if type(dv) in (int, float, complex, bool, str, bytes) or dv is None:
            return dv
        # datetime values are first-class scalar terms at runtime (immutable,
        # hashable, unify by value — `Date/4` produces them, `DaysBetween`
        # consumes them), so parameterize them like ints: the OBJECT is bound
        # at run time, which also spares tz-aware values any reconstruction.
        # Exact types only — a subclass may carry state the base constructor
        # cannot rebuild, so it keeps the structural fallback.
        if type(dv) in _DATETIME_QUERY_SCALARS:
            return dv
        if is_zero_field_class(dv):
            return dv
        return None

    if isinstance(type(goal), PredicateMeta):
        params: list = []
        new_vals: dict = {}
        for f in term_field_names(goal):
            gv = _ground_value(getattr(goal, f))
            if gv is None:
                new_vals[f] = getattr(goal, f)
            else:
                pv = Var()
                params.append((pv, gv))
                new_vals[f] = pv
        if not params:
            return goal, []
        return type(goal)(**new_vals), params

    if isinstance(goal, Compound):
        params = []
        new_args: list = []
        for a in goal.args:
            gv = _ground_value(a)
            if gv is None:
                new_args.append(a)
            else:
                pv = Var()
                params.append((pv, gv))
                new_args.append(pv)
        if not params:
            return goal, []
        return Compound(goal.functor, tuple(new_args)), params

    # A CELL goal parameterizes exactly like a Compound one (P3-3 Task 5): the
    # goal's own arguments are slots 1.. and slot 0 is the functor, which is
    # never a parameter.  Without this branch every distinct ground argument
    # compiled its own query — a cell goal is a predicate call, and it gets the
    # same value-independent compiled query a Compound call gets.
    is_cell_goal, cell_f = compound_cell_shape(goal)
    if is_cell_goal and (
        # ARITY-MATCHED to ``_term_to_goal``'s own guard (P3-3 Task 5 fix
        # round 1, F5): only ``:``/2 is the qualified form, so
        # ``(":", A, B, C)`` is an ordinary ``:``/3 call and templatizes like
        # any other. The two guards disagreeing meant one path treated it as
        # special and the other as ordinary.
        (cell_f == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3)
        or cell_f in CELL_GOAL_CONTROL_FUNCTORS
    ):
        # Neither of these two is an ordinary predicate call, so neither has
        # top-level arguments to parameterize.  A control construct is refused
        # by ``_term_to_goal`` a few lines later, and leaving it alone is what
        # makes the refusal quote the goal the caller wrote rather than a
        # template with fresh Vars in it.  A ``:``/2 goal is already GONE by
        # the time a query reaches here — ``_compile_as_query`` strips the
        # qualification before calling this function (P3-3 Task 6), and the
        # inner goal it hands over templatizes on the branch below like any
        # other cell.  What remains here is the direct caller, for whom
        # "M:G has no arguments of its own" is simply true.
        return goal, []
    if is_cell_goal:
        params = []
        new_args = []
        for a in goal[1:]:
            gv = _ground_value(a)
            if gv is None:
                new_args.append(a)
            else:
                pv = Var()
                params.append((pv, gv))
                new_args.append(pv)
        if not params:
            return goal, []
        return (goal[0],) + tuple(new_args), params

    return goal, []


def _compile_as_query(goal: Any, module: Module) -> Any:
    """Compile goal as a zero-arity query predicate and return its dispatch fn.

    Vars embedded in the goal are injected into the compiled function's globals
    so that the compiled code references the *user's* Var objects rather than
    allocating fresh ones.  This means the trail binds the user's Vars directly,
    making deref(user_var) work during and after each solution.

    when module.module_dict is available, it is merged into the compiled
    function's globals so that predicate names resolve from the module namespace
    (Phase 5: cross-predicate resolution without _db string lookup).

    A module-QUALIFIED cell goal ``(":", M, G)`` switches *module* to *M* here
    (P3-3 Task 6) before anything else looks at either — see
    ``_strip_module_qualification`` for why this is the right point.
    """
    goal, module = _strip_module_qualification(goal, module)

    # Parameterize ground top-level args so distinct values reuse one compiled
    # query.  The returned param_pairs are bound to their values (on the trail)
    # by the caller before driving the search.
    goal, param_pairs = _templatize_query_goal(goal)

    # Compute cache key before AST conversion (needs original term).  After
    # templatizing, ground args are Vars, so the key is value-independent.
    cache_key = _goal_cache_key(goal, module)

    goal = _term_to_goal(goal)
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.compiler.goal_trampoline import compile_body_trampoline
    from clausal.logic.compiler._vars import _collect_vars, _var_python_name
    from clausal.logic.compiler.globals_env import _collect_types_from_term

    # include_bound: a Var already bound to a value with no literal lowering
    # (e.g. a datetime.date from an earlier goal, common in the test harness's
    # diagnostic re-runs) must be referenceable BY NAME from the compiled code
    # — term_to_ast_expr falls back to that reference instead of raising.
    vars_in_goal = _collect_vars(goal, include_bound=True)

    if cache_key is not None and cache_key in _query_cache:
        cached_fn, cached_code, cached_var_names = _query_cache[cache_key]
        # Map new Var objects to the names the cached code expects
        new_globals = dict(cached_fn.__globals__)
        for old_name, new_var in zip(cached_var_names, vars_in_goal):
            new_globals[old_name] = new_var
        fn = _types.FunctionType(cached_code, new_globals, cached_fn.__name__)
        return fn, param_pairs

    db = module.db

    # Collect all Var objects reachable from goal.
    pre_var_context = {v._id: _var_python_name(v) for v in vars_in_goal}
    extra_globals: dict = {}
    # Start with module globals so predicate names resolve from the namespace.
    if module.module_dict is not None:
        extra_globals.update(module.module_dict)
    # Var globals take precedence over module globals.
    extra_globals.update({_var_python_name(v): v for v in vars_in_goal})
    # Also collect user-defined dataclass types that appear in the goal args
    # so that term_to_ast_expr can reference them in the compiled code.
    extra_globals.update(_collect_types_from_term(goal))

    def _query_body_compiler(clause: Clause, var_context: dict) -> list:
        # Pre-populate var_context so _preallocate_body_vars skips user Vars
        # and term_to_ast_expr references them by name (→ global) rather than
        # emitting a walrus that creates a new Var().
        var_context.update(pre_var_context)
        # The goal's arguments are live TERM OBJECTS handed in by the caller,
        # but this template's globals are the CALLEE's module namespace.  An
        # atom in those terms (a DictTerm key/value, a list element, …) is a
        # global-by-spelling interned str (§1b/R2): it lowers to a plain
        # ``ast.Constant`` and is never re-resolved by name in the callee's
        # namespace, so it cannot land on a same-named predicate there — the
        # by-identity lowering this comment used to describe is deleted.
        return compile_body_trampoline(clause.body, db, var_context, "trail")

    dummy_head = Compound("_query", ())
    clause = Clause(head=dummy_head, body=[goal])
    dispatch_fn = compile_predicate_trampoline(
        "_query", 0, [clause], db,
        body_compiler=_query_body_compiler,
        globals_=extra_globals,
    )

    if cache_key is not None:
        cached_var_names = [_var_python_name(v) for v in vars_in_goal]
        # Bound the cache: keying on ground *values* (for correctness) means a
        # workload that queries one module with many distinct argument values
        # would otherwise grow this dict without limit.  Evict in FIFO order
        # (dicts preserve insertion order) once the cap is reached.
        if len(_query_cache) >= _QUERY_CACHE_MAX:
            _query_cache.pop(next(iter(_query_cache)), None)
        _query_cache[cache_key] = (dispatch_fn, dispatch_fn.__code__, cached_var_names)

    return dispatch_fn, param_pairs


# ── Public API ─────────────────────────────────────────────────────────────────


def _coerce_module(module) -> Module:
    """Accept a clausal Module or a Python module imported from a .clausal file.

    When *module* is a regular Python module (e.g. ``import hello_world``), the
    logic Module stored during import-hook compilation is returned via its
    ``__clausal_module__`` attribute.
    """
    if isinstance(module, Module):
        return module
    cm = getattr(module, '__clausal_module__', None)
    if cm is not None:
        return cm
    # Last resort: wrap a bare dict / module namespace as a Module.
    if hasattr(module, '__dict__') and hasattr(module, '__name__'):
        return Module(module.__name__, module_dict=vars(module))
    raise TypeError(
        f"Expected a clausal Module or an imported .clausal module, got {type(module).__name__}"
    )


def resolve_module(designator: Any, calling_module: Any = None,
                   context: str = "") -> Module:
    """Resolve a module DESIGNATOR to the :class:`Module` whose database answers.

    P3-3 Task 6 (R10).  This is the one place that answers "which module does
    this name mean?" for the module-qualified goal ``(":", M, G)`` and for
    ``solve``'s ``module=`` argument, so the two cannot drift apart on what a
    designator is.

    The chain, in order:

      - a ``str`` is a DOTTED PYTHON MODULE NAME, looked up in ``sys.modules``
        -- which is exactly where ``clausal/import_hook.py`` registers every
        ``.clausal`` module it loads (``_load_module`` and the finder both
        write ``sys.modules[fullname]``), so the spelling a designator uses is
        the spelling an ``import`` would use.  The result is then coerced like
        any module object.
      - everything else goes straight to :func:`_coerce_module`, which is the
        pre-existing chain and stays the only copy of it: a ``Module`` is
        itself, an imported ``.clausal`` module yields its
        ``__clausal_module__``, and any other module namespace is wrapped.

    LOOKUP ONLY.  Resolution never imports -- no ``importlib.import_module``,
    no side effect on ``sys.modules``.  A module that is merely *importable*
    does not resolve, because a goal is not an import statement and running
    one must not execute a module body.

    Anything the chain refuses -- an ``int``, a cell, an unbound ``Var``, a
    ``str`` that misses in ``sys.modules`` -- raises
    ``LogicException(existence_error(module, <designator repr'd>))``.  The
    culprit is the REPR rather than the designator itself so that the error
    term is always a ground atom: an unbound-``Var`` designator must not end
    up as a culprit that unifies with whatever pattern a ``catch/3`` offers.

    *calling_module* is the module the designator was written in, when the
    caller knows it.  It does not participate in resolution (a designator is
    absolute, per the R10 chain above) -- it names the asking module in the
    diagnostic, and it is the hook a future alias/short-name chain would use.
    """
    # The culprit is the DEREFERENCED designator, not the term the caller
    # handed over: ``M`` in a ``(":", M, G)`` cell is routinely a Var bound to
    # the real designator, and reporting ``AttVar(_4=7)`` names the plumbing
    # rather than the fault (P3-3 Task 6 fix round 1, F6).  It stays the
    # designator even when the ``sys.modules`` hit below replaces *target*:
    # a str that resolved to a module object and then failed to coerce is
    # still a fault about the name the caller wrote.
    culprit = deref(designator)
    target = culprit
    # Spec §6.4: a designator WRITTEN in source arrives as an atom, so it is
    # read by spelling here.  The Python-API ``str`` path below is untouched
    # (``solve(goal, module="pkg.mod")`` passes a Python argument, not a
    # term), and under today's representation a str atom's spelling is itself.
    if _term_is_atom(target):
        target = _spelling(target)
    if isinstance(target, str):
        found = sys.modules.get(target)
        if found is None:
            _no_such_module(culprit, calling_module, context)
        target = found
    try:
        return _coerce_module(target)
    except TypeError as exc:
        _no_such_module(culprit, calling_module, context, cause=exc)


def _no_such_module(designator, calling_module, context: str, cause=None):
    """Raise ``existence_error(module, repr(designator))``.  Never returns."""
    from clausal.logic.exceptions import (  # noqa: PLC0415 -- clausal.logic.
        LogicException, existence_error,    # exceptions imports clausal.terms,
    )                                       # which imports this module's kin
    asker = ""
    if calling_module is not None:
        asker = f" (asked from {getattr(calling_module, 'name', calling_module)!r})"
    prefix = f"{context}: " if context else ""
    exc = LogicException(existence_error(
        "module", repr(designator),
        f"{prefix}{designator!r} does not name a module{asker} — a module "
        f"designator is a dotted Python module name already present in "
        f"sys.modules (resolution is lookup-only and never imports), a "
        f"clausal Module, or an imported .clausal module object",
    ))
    if cause is not None:
        raise exc from cause
    raise exc


def _module_for_moduleless_solve(goal) -> tuple[Any, Module]:
    """Pick the goal and module for a ``solve(goal)`` called without ``module=``.

    Returns ``(goal, module)``.  The goal comes back STRIPPED of a top-level
    qualification when that is where the module came from, so the caller can
    hand both on and nothing resolves the same designator twice (P3-3 Task 6
    fix round 1, F8).  Resolving twice was not merely wasteful: the second
    resolution ran with the exporter as the calling module, so a diagnostic
    from it named the module that ANSWERS as the one that ASKED.

    Three cases, in the order they are asked:

      - a module-QUALIFIED cell goal carries its own answer.  ``(":", M, G)``
        names the module that answers, so ``module=`` is redundant rather than
        missing and the goal runs.  There is no calling module to report, and
        ``None`` is passed as one rather than a guess.
      - any other CELL goal has no module at all, and none can be guessed:
        a cell is a plain tuple, so there is no defining class to walk back to
        (which is what ``_infer_module`` does) and the tuple's functor is a
        bare name that any number of modules may define.  Guessing here is
        exactly the module-locality bug this task exists to prevent, so the
        gap is REPORTED.
      - anything else keeps the legacy behaviour: ``_infer_module`` walks the
        goal for class-instance terms, and its failure is the same ``TypeError``
        it has always raised.
    """
    is_cell_goal, functor = compound_cell_shape(goal)
    if is_cell_goal:
        if functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3:
            return _strip_module_qualification(goal, None)
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, existence_error,
        )
        raise LogicException(existence_error(
            # The REPR, not the goal (P3-3 Task 6 fix round 1, F4): the live
            # cell holds the caller's Vars, so a ``catch/3`` pattern unifying
            # with the culprit would alias them.  Same rule as
            # ``resolve_module``'s culprit — an error term is a ground atom.
            "module", repr(goal),
            f"solve/1: the unqualified cell goal {functor}/{len(goal) - 1} has "
            f"no calling module — pass module= (the module whose database "
            f"answers), or qualify the goal as (':', M, Goal).  A cell names a "
            f"predicate but carries no module of its own, so there is nothing "
            f"here to infer one from",
        ))
    module = _infer_module(goal)
    if module is None:
        raise TypeError(
            "Cannot infer module from goal. Pass the module explicitly, e.g.:\n"
            "  solve(goal, my_module)"
        )
    return goal, module


def _resolved_goal_and_module(goal, module, context: str):
    """The shared entry resolution: ``(stripped goal, resolved Module)``.

    P3-3 Task 6 fix round 1 (F1, F2).  ``solve`` and ``query_wfs`` both have to
    answer "which module?" and both have to answer it the SAME way, because
    ``query_wfs`` asks a second question afterwards — which table entry holds
    this goal's truth values — of ``_tabled_entry_for_goal``, and that lookup
    must be made against the module the goal actually RAN against.  Before this
    round ``query_wfs`` passed its raw ``module`` argument to both, so a str
    designator crashed the entry lookup with an uncaught ``TypeError`` after
    the goal had already run (F1), and ``module=None`` with a qualified goal
    made the lookup bail and report every WFS-``Undefined`` answer as ``True``
    (F2).  One resolution, one answer, handed to both.
    """
    if module is None:
        return _module_for_moduleless_solve(goal)
    return _strip_module_qualification(goal, resolve_module(module, None, context))


def _strip_module_qualification(goal, module):
    """Peel a top-level ``(":", M, G)`` off *goal*, returning ``(G, M's Module)``.

    P3-3 Task 6.  This is where a qualified goal becomes a module SWITCH: the
    inner goal is compiled against — and cached under — the EXPORTING module,
    which is what makes ``solve((":", e, ("p", X)), module=i)`` answer *e*'s
    ``p/1`` while ``solve(("p", X), module=i)`` answers *i*'s.

    Doing it here, before ``_templatize_query_goal`` and ``_goal_cache_key``,
    is deliberate: from that point on a qualified goal IS an ordinary cell
    goal against another module, so it templatizes like one (ground arguments
    parameterize, distinct values share a compiled query) and its cache key is
    the ordinary ``(structural_key, id(module))`` with the RESOLVED module's
    id — which is the module the compiled artifact actually depends on.

    Non-qualified goals come back untouched.
    """
    is_cell_goal, functor = compound_cell_shape(goal)
    if not (is_cell_goal
            and functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
        return goal, module
    target, inner = resolve_qualified_goal_cell(goal, "solve/1", module)
    return inner, target


def _infer_module(goal) -> Module | None:
    """Try to find a Module from PredicateMeta classes in the goal term.

    Walks the goal tree looking for term instances whose type was defined in an
    imported .clausal module.  Returns the first Module found, or None.

    LEGACY CUSTOMERS ONLY (P3-3 Task 6).  A CELL goal never reaches here: a
    cell is a plain tuple with a bare-name functor, so there is no defining
    class to walk back to and any number of modules may define that name.
    ``_module_for_moduleless_solve`` refuses it with an ``existence_error``
    naming the gap instead of guessing — see the module-locality rule R10.
    """
    import sys
    from clausal.logic.predicate import PredicateMeta

    def _find_pred_class(term):
        if isinstance(type(term), PredicateMeta):
            return type(term)
        # Walk simple_ast compound nodes (And, Or, Not, etc.)
        for attr in ('left', 'right', 'operand', 'goal', 'condition',
                     'then_goal', 'else_goal', 'args'):
            child = getattr(term, attr, None)
            if child is not None:
                if isinstance(child, (list, tuple)):
                    for c in child:
                        cls = _find_pred_class(c)
                        if cls is not None:
                            return cls
                else:
                    cls = _find_pred_class(child)
                    if cls is not None:
                        return cls
        return None

    pred_cls = _find_pred_class(goal)
    if pred_cls is None:
        return None

    mod_name = getattr(pred_cls, '__module__', None)
    if mod_name is not None:
        py_mod = sys.modules.get(mod_name)
        if py_mod is not None:
            cm = getattr(py_mod, '__clausal_module__', None)
            if cm is not None:
                return cm
            # Fall back to wrapping the module namespace.
            return Module(mod_name, module_dict=vars(py_mod))
    return None


def call(
    functor,
    *args: Any,
    module: Module | None = None,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive a compiled predicate; yield the Trail after each solution.

    ``functor`` may be either a predicate name string (requires ``module``) or
    a PredicateMeta class (``module`` is not needed in that case).

    Args are passed directly to the compiled dispatch function.  Output-position
    args should be Var objects — they will be bound on the Trail during each
    yielded solution.

    Parameters
    ----------
    functor:  predicate name string, or a PredicateMeta class
    *args:    arguments; may include Var objects for output positions
    module:   Module whose database holds the compiled predicate (not required
              when functor is a PredicateMeta class)
    trail:    optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).

    Raises
    ------
    KeyError  if the predicate is not defined in module.
    """
    # Fast path: predicate class passed directly — no module lookup needed.
    if hasattr(functor, '_get_dispatch'):
        dispatch_fn = functor._get_dispatch()
        if trail is None:
            trail = Trail()
        yield from _drive_trampoline(dispatch_fn, trail, *args)
        return

    if module is not None:
        module = _coerce_module(module)

    arity = len(args)

    # Phase 5: look up PredicateMeta class from module globals first.
    dispatch_fn = None
    if module is not None and module.module_dict is not None:
        pred_cls = module.module_dict.get(functor)
        if pred_cls is not None and hasattr(pred_cls, '_get_dispatch'):
            # Pass the arity: call("citation", A, B) against citation/3 is the
            # same fault as writing it in a clause body, and gets the same
            # message rather than a TypeError about a missing `trail`.  Via
            # _dispatch_at, because pred_cls need not be a PredicateMeta.
            dispatch_fn = _dispatch_at(pred_cls, arity)

    # Phase 6: try builtins before Database fallback.
    if dispatch_fn is None and module is not None:
        from clausal.logic.builtins import get_builtin_predicate  # noqa: PLC0415
        builtin = get_builtin_predicate(functor, arity, module.db)
        if builtin is not None:
            dispatch_fn = builtin._get_dispatch()

    # Fall back to Database dispatch lookup (test modules and Compound-head predicates).
    if dispatch_fn is None and module is not None:
        dispatch_fn = module.db.get_dispatch(functor, arity)

    if dispatch_fn is None:
        if module is None:
            raise KeyError(
                f"Predicate {functor!r}/{arity}: module is required when functor is a string"
            )
        raise KeyError(
            f"Predicate {functor!r}/{arity} is not defined in module {module.name!r}"
        )

    if trail is None:
        trail = Trail()

    yield from _drive_trampoline(dispatch_fn, trail, *args)


def solve(
    goal: Any,
    module=None,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive an arbitrary goal; yield the Trail after each solution.

    The goal may be any term node: Call, And, Or, Is, Not, in_, True, False, …
    Var objects embedded in the goal are referenced by identity in the compiled
    code so their bindings accumulate on the Trail and are readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  a module DESIGNATOR — a clausal Module, an imported .clausal
             Python module, or (P3-3 Task 6) the dotted name of one as a str —
             or None.  None means: a module-qualified cell goal names its own
             module; any other cell goal is an error naming the gap; anything
             else is auto-inferred from the predicate classes in the goal.
             See ``resolve_module`` and ``_module_for_moduleless_solve``.
    trail:   optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).
    """
    goal, module = _resolved_goal_and_module(goal, module, "solve/2")
    if trail is None:
        trail = Trail()

    # Fast paths for trivial goals — avoid the compiler entirely.
    if goal is True:
        yield trail
        return
    if goal is False:
        return

    dispatch_fn, param_pairs = _compile_as_query(goal, module)
    # Bind parameterized ground args to their values before driving so the
    # value-independent compiled query sees the concrete arguments.
    for param_var, value in param_pairs:
        unify(param_var, value, trail)
    yield from _drive_trampoline(dispatch_fn, trail)


def query(
    goal: Any,
    variables: dict[str, Var],
    module=None,
    trail: Trail | None = None,
) -> Iterator[dict[str, Any]]:
    """Solve goal and yield one fully-dereferenced binding dict per solution.

    .. deprecated::
        Prefer iterating the goal directly and reading ``Var.value``::

            for trail in greeting(X := Var()):
                print(X.value)

    Parameters
    ----------
    goal:      goal term (embed the same Var objects as values of variables)
    variables: mapping of name → Var whose bindings to capture each solution
    module:    Module, imported .clausal Python module, or None (auto-inferred)
    trail:     optional Trail (fresh if not provided)

    Yields
    ------
    dict mapping each name in variables to its fully-dereferenced value.
    Unbound Vars remain as Var objects in the dict.
    """
    import warnings
    warnings.warn(
        "query() is deprecated. Iterate the goal directly and use Var.value:\n"
        "  for trail in pred(X := Var()): print(X.value)",
        DeprecationWarning,
        stacklevel=2,
    )
    for _ in solve(goal, module, trail):
        yield {name: _deref_walk(var) for name, var in variables.items()}


def once(
    goal: Any,
    module=None,
    trail: Trail | None = None,
) -> Trail | None:
    """Return the Trail for the first solution, or None if the goal fails.

    Bindings on the returned Trail are live and readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  Module, imported .clausal Python module, or None (auto-inferred)
    trail:   optional Trail (fresh if not provided)

    Returns
    -------
    Trail (with bindings live) on success, or None on failure.
    """
    for t in solve(goal, module, trail):
        return t
    return None


def query_wfs(
    goal: Any,
    variables: dict[str, Var],
    module=None,
    trail: Trail | None = None,
) -> list[dict[str, Any]]:
    """Solve goal and return results with WFS truth annotations.

    Like ``query()``, but each result dict includes a ``"_truth"`` key
    whose value is ``True`` (unconditional), ``Undefined`` (unfounded), or
    ``True`` for non-tabled results.  The third value is the strong-Kleene
    ``Undefined`` singleton — the same one ``.clausal`` code writes — so a
    WFS-undefined answer can flow straight into Kleene-aware code.

    Each result also carries ``"_delays"``: a frozenset of ``DelayedNegation``
    objects, non-empty exactly when ``_truth`` is ``Undefined``.  Each names
    the negated tabled call the answer is conditional on (``.functor``,
    ``.arity``, ``.frozen_args``) — for a negation cycle, the cycle partner —
    so a caller can report *which* pair is unresolved, not just that
    something is.

    *module* takes the same designators ``solve`` takes — a Module, an imported
    .clausal module, its dotted name as a str, or None — and means the same
    thing, because it is resolved by the same chain before either the solve or
    the table lookup sees it.

    Returns a list (not iterator) since WFS resolution requires completing
    all SLG computation before truth values are determined.
    """
    # Resolve the module ONCE, here, and hand the same answer to both the
    # solve below and the entry lookup further down (P3-3 Task 6 fix round 1,
    # F1/F2 — see ``_resolved_goal_and_module``).  Passing the raw argument to
    # both let them disagree: the entry lookup does not accept a str
    # designator, and it bails outright on ``module=None``, which silently
    # turned every Undefined answer of a qualified goal into True.
    goal, module = _resolved_goal_and_module(goal, module, "query_wfs/3")

    results = []
    for _ in solve(goal, module, trail):
        results.append({name: _deref_walk(var) for name, var in variables.items()})

    # A04-F004: annotate each result with its REAL WFS truth value read from the
    # tabled entry's conditions, instead of hardcoding True. A single tabled-goal
    # query maps each result to a stored answer (by normalized value) and uses
    # TableEntry.truth_value(i) → True | Undefined. Non-tabled goals stay True
    # (documented). Composite/conjunctive goals are not decomposed here and keep
    # True (a min-truth semantics over tabled conjuncts is future work).
    entry, goal_args = _tabled_entry_for_goal(goal, module, trail)
    if entry is None:
        for r in results:
            r["_truth"] = True
            r["_delays"] = frozenset()
        return results

    from clausal.logic.tabling import make_subgoal_key
    var_to_name = {id(v): name for name, v in variables.items()}
    kept = []
    for r in results:
        cand = []
        for a in goal_args:
            da = deref(a)
            cand.append(r[var_to_name[id(da)]] if id(da) in var_to_name else da)
        # The entry's own answer index is keyed by exactly this
        # normalization (make_subgoal_key IS tuple-of-_normalize_for_key),
        # so answer lookup is one dict get instead of an O(answers) scan
        # per result.
        idx = entry._answer_index.get(make_subgoal_key(cand, None))
        truth = True
        delays = frozenset()
        if idx is not None:
            truth = entry.truth_value(idx)
            if truth is Undefined:
                delays = entry.delays_for(idx)
        if truth is False:
            # The stored row was invalidated (WFS-false) AFTER solve()
            # streamed it — resolution can outrun the incremental yields.
            # A definite-false answer must not surface at all (a rerun of
            # the same query yields nothing for it), and it must certainly
            # not default to _truth=True.
            continue
        r["_truth"] = truth
        r["_delays"] = delays
        kept.append(r)
    return kept


def _tabled_entry_for_goal(goal, module, trail):
    """Return ``(TableEntry, goal_args)`` for a single tabled-predicate goal,
    or ``(None, None)`` for a non-tabled or composite goal (A04-F004).

    Handles every single-goal shape ``solve()`` accepts: term instances,
    ``Compound`` (checked FIRST — ``is_term_instance`` is also true for a
    Compound and would mangle its functor into ``"Compound"``), reified
    ``Call(LoadName(...))`` — the shape ``docs/wfs.md`` and the test suite
    build (todo/wfs-undefined-lost-at-query-surface.md §3) — and qualified
    ``Call(LoadAttr(LoadName(mod), pred))``, whose table lives in the
    EXPORTING module's db. Keyword arguments are normalized positionally
    via the owning db's registered signature, mirroring the tabled-NAF
    compiler seam.

    P3-3 Task 6 adds the two CELL shapes ``solve()`` accepts: the plain cell
    ``("p", A)`` (invisible here before — it fell to the final ``else`` and
    every cell goal read as non-tabled), and the module-qualified
    ``(":", M, G)``, resolved through ``resolve_module`` so the entry is
    looked up in the EXPORTING module's db — the same rule the dotted
    ``LoadAttr`` path below already follows, reached by the new resolver
    rather than by that path's caller-dict walk.  The two are deliberately
    NOT converged here: the legacy walk stays pinned as R10 records, and
    the convergence is a filed follow-up."""
    if module is None:
        return None, None
    mod = _coerce_module(module)
    kwargs = []
    is_cell_goal, cell_functor = compound_cell_shape(goal)
    if (is_cell_goal
            and cell_functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
        # Resolve the qualification, then fall through to the cell branch with
        # the EXPORTING module in hand.  A designator that does not resolve is
        # not this function's error to raise: it is asked AFTER solve() has
        # already run the goal, so solve() has raised it already; here the
        # honest answer for a goal that names no module is "no table".
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        try:
            mod, goal = resolve_qualified_goal_cell(goal, "query_wfs/2", mod)
        except LogicException:
            return None, None
        is_cell_goal, cell_functor = compound_cell_shape(goal)
    if is_cell_goal:
        functor = cell_functor
        goal_args = list(goal[1:])
    elif isinstance(goal, Compound):
        functor = deref(goal.functor)
        if not isinstance(functor, str):
            return None, None
        goal_args = list(goal.args)
    elif isinstance(goal, _ReifiedCall):
        func = goal.func
        if isinstance(func, _ReifiedLoadName):
            functor = func.name
        elif isinstance(func, _ReifiedLoadAttr):
            # Qualified goal, possibly nested (pkg.sub.Pred) — walk the
            # dotted chain down to a LoadName base, then resolve segment by
            # segment through the querying module's dict and getattr, and
            # consult the EXPORTING module's db. A directly-constructed
            # Module has module_dict=None — fall back gracefully.
            functor = func.attr
            segments = []
            node = func.object
            while isinstance(node, _ReifiedLoadAttr):
                segments.append(node.attr)
                node = node.object
            if not isinstance(node, _ReifiedLoadName):
                return None, None
            segments.append(node.name)
            segments.reverse()
            md = mod.module_dict
            if md is None:
                return None, None
            owner = md.get(segments[0])
            if len(segments) > 1:
                # The import hook does not bind submodules as parent-package
                # attributes, so walk sys.modules by the full dotted name
                # first; fall back to a getattr chain for plain objects.
                dotted = sys.modules.get(".".join(segments))
                if dotted is not None:
                    owner = dotted
                else:
                    for seg in segments[1:]:
                        if owner is None:
                            return None, None
                        owner = getattr(owner, seg, None)
            if owner is None:
                return None, None
            try:
                mod = _coerce_module(owner)
            except (TypeError, AttributeError, KeyError):
                return None, None
        else:
            return None, None
        goal_args = list(goal.args)
        kwargs = list(goal.kwargs)
    elif is_term_instance(goal):
        functor = type(goal).__name__
        goal_args = [getattr(goal, f) for f in term_field_names(goal)]
    else:
        return None, None
    if kwargs:
        if any(kw.name is None for kw in kwargs):
            return None, None  # **splat — positions unknowable here
        sig = mod.db.signature_for(functor, len(goal_args) + len(kwargs))
        if sig is None:
            return None, None
        kw_map = {kw.name: kw.value for kw in kwargs}
        merged = list(goal_args)
        for field in sig[len(goal_args):]:
            if field not in kw_map:
                return None, None
            merged.append(kw_map[field])
        goal_args = merged
    arity = len(goal_args)
    if not mod.db.is_tabled(functor, arity):
        # An -import_from-remapped predicate resolves by bare name here but
        # is tabled — and tabled INTO — the exporting module's db. Follow
        # the PredicateMeta back to its defining module before giving up.
        md = mod.module_dict
        pred_cls = md.get(functor) if md is not None else None
        owner_name = getattr(pred_cls, "__module__", None)
        owner = sys.modules.get(owner_name) if owner_name else None
        if owner is None:
            return None, None
        try:
            owner_mod = _coerce_module(owner)
        except (TypeError, AttributeError, KeyError):
            return None, None
        if owner_mod.db is mod.db or not owner_mod.db.is_tabled(functor, arity):
            return None, None
        mod = owner_mod
    from clausal.logic.tabling import make_subgoal_key
    key = make_subgoal_key(goal_args, trail or Trail())
    return mod.db.table_store.get((functor, arity, key)), goal_args


__all__ = [
    "call",
    "solve",
    "query",
    "query_wfs",
    "once",
    "resolve_module",
    "_deref_walk",
]
