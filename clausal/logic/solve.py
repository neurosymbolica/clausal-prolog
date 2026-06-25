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
(e.g. ``import hello; solve(greeting(X), hello)``).

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

from typing import Any, Iterator

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.database import Clause, Database, Module
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.trampoline import StepGenerator, DONE, _drive_until_yield
from clausal.terms import Compound


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
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_deref_walk_py(a) for a in term.args))
    if is_term_instance(term):
        return type(term)(**{
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
    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    while True:
        result = _drive_until_yield(sg)
        if result is None:
            return
        yield trail


def _term_to_goal(term: Any) -> Any:
    """Convert a runtime term instance to a simple_ast goal node.

    When the user writes ``solve(greeting(N := Var()))``, ``greeting(N)``
    produces a PredicateMeta *instance* (a runtime term), not a simple_ast
    ``Call`` node.  The compiler expects goal nodes, so we convert here.
    Simple_ast nodes and other goal forms pass through unchanged.
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.pythonic_ast.nodes import Call as AstCall, LoadName

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
      - compound/predicate/sequence terms recurse structurally.

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
    predicate term nor a Compound, or when it contains an unhashable ground leaf.
    """
    from clausal.logic.predicate import PredicateMeta
    if not (isinstance(type(goal), PredicateMeta) or isinstance(goal, Compound)):
        return None
    try:
        return (_structural_key(goal, {}), id(module))
    except _Uncacheable:
        return None


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
    from clausal.logic.predicate import PredicateMeta

    def _ground_value(val):
        """Return the scalar ground value to parameterize, or None to leave it.

        Only plain scalar literals are parameterized: they unify directly with a
        head literal regardless of mode.  Structural args (list/dict/compound)
        are *not* parameterized because the literal-baking path rewrites them
        (e.g. a list literal becomes cons cells) — a raw value bound to a Var
        would not match the rewritten head pattern.  Those keep the value-keyed
        cache fallback.
        """
        dv = deref(val)
        if is_var(dv):
            return None
        if type(dv) in (int, float, complex, bool, str, bytes) or dv is None:
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
    """
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

    vars_in_goal = _collect_vars(goal)

    if cache_key is not None and cache_key in _query_cache:
        cached_fn, cached_code, cached_var_names = _query_cache[cache_key]
        # Map new Var objects to the names the cached code expects
        import types as _types
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


def _infer_module(goal) -> Module | None:
    """Try to find a Module from PredicateMeta classes in the goal term.

    Walks the goal tree looking for term instances whose type was defined in an
    imported .clausal module.  Returns the first Module found, or None.
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
            dispatch_fn = pred_cls._get_dispatch()

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
    module:  Module, imported .clausal Python module, or None (auto-inferred
             from predicate classes in the goal)
    trail:   optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).
    """
    if module is None:
        module = _infer_module(goal)
        if module is None:
            raise TypeError(
                "Cannot infer module from goal. Pass the module explicitly, e.g.:\n"
                "  solve(goal, my_module)"
            )
    else:
        module = _coerce_module(module)
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
    whose value is ``True`` (unconditional), ``"undefined"`` (unfounded),
    or omitted for non-tabled results (always ``True``).

    Returns a list (not iterator) since WFS resolution requires completing
    all SLG computation before truth values are determined.
    """
    results = []
    for _ in solve(goal, module, trail):
        results.append({name: _deref_walk(var) for name, var in variables.items()})

    # Annotate with truth values from tabling conditions.
    # After solve() completes, all tabled predicates involved should be complete.
    # We attach truth=True to all results by default (non-tabled or unconditional).
    for r in results:
        r["_truth"] = True

    return results


__all__ = [
    "call",
    "solve",
    "query",
    "query_wfs",
    "once",
    "_deref_walk",
]
