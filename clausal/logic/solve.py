"""clausal.logic.solve — top-level query API (Step 7).

Public API
----------
call(functor, *args, module, trail=None)    → Iterator[Trail]
solve(goal, module, trail=None)             → Iterator[Trail]
query(goal, variables, module, trail=None)  → Iterator[dict[str, Any]]
once(goal, module, trail=None)              → Trail | None

Design
------
``call`` drives a named predicate's compiled dispatch function directly.
The user passes Var objects as args; the dispatch function binds them through
the Trail.  This is the fastest path for simple predicate calls.

``solve`` handles arbitrary goal terms (Call, And, Or, Is, Not, In, …).
It compiles the goal on the fly as a synthetic zero-arity query predicate,
injecting any Var objects that appear in the goal into the compiled function's
globals so they are referenced by identity (not replaced with fresh Vars).
This lets the user read bindings via deref() on their original Var objects
after each solution.

``query`` wraps solve and fully dereferences a named set of variables,
returning a plain dict per solution.

``once`` returns the Trail for the first solution (bindings still live),
or None if the goal fails.
"""

from __future__ import annotations

from typing import Any, Iterator

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.database import Clause, Database, Module
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound


# ── Helpers ────────────────────────────────────────────────────────────────────


def _deref_walk(term: Any) -> Any:
    """Fully dereference a term, recursively walking all Var bindings.

    Unbound Vars remain as Var objects in the result.
    """
    term = deref(term)
    if is_var(term):
        return term
    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return term
    if isinstance(term, list):
        return [_deref_walk(e) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_deref_walk(a) for a in term.args))
    if is_term_instance(term):
        return type(term)(**{
            name: _deref_walk(getattr(term, name))
            for name in term_field_names(term)
        })
    return term


def _compile_as_query(goal: Any, module: Module) -> Any:
    """Compile goal as a zero-arity query predicate and return its dispatch fn.

    Vars embedded in the goal are injected into the compiled function's globals
    so that the compiled code references the *user's* Var objects rather than
    allocating fresh ones.  This means the trail binds the user's Vars directly,
    making deref(user_var) work during and after each solution.

    When module.module_dict is available, it is merged into the compiled
    function's globals so that predicate names resolve from the module namespace
    (Phase 5: cross-predicate resolution without _db string lookup).
    """
    from clausal.logic.compiler import (
        compile_predicate,
        compile_body,
        _collect_vars,
        _var_python_name,
        _collect_types_from_term,
    )

    db = module.db

    # Collect all Var objects reachable from goal.
    vars_in_goal = _collect_vars(goal)
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
        return compile_body(clause.body, db, var_context, "trail")

    dummy_head = Compound("_query", ())
    clause = Clause(head=dummy_head, body=[goal])
    return compile_predicate(
        "_query", 0, [clause], db,
        body_compiler=_query_body_compiler,
        globals_=extra_globals,
    )


# ── Public API ─────────────────────────────────────────────────────────────────


def call(
    functor: str,
    *args: Any,
    module: Module,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive a compiled predicate by name; yield the Trail after each solution.

    Args are passed directly to the compiled dispatch function.  Output-position
    args should be Var objects — they will be bound on the Trail during each
    yielded solution.

    Parameters
    ----------
    functor:  predicate name (without arity suffix)
    *args:    arguments; may include Var objects for output positions
    module:   Module whose database holds the compiled predicate
    trail:    optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).

    Raises
    ------
    KeyError  if the predicate is not defined in module.
    """
    arity = len(args)

    # Phase 5: look up PredicateMeta class from module globals first.
    dispatch_fn = None
    if module.module_dict is not None:
        pred_cls = module.module_dict.get(functor)
        if pred_cls is not None and hasattr(pred_cls, '_get_dispatch'):
            dispatch_fn = pred_cls._get_dispatch()

    # Phase 6: try builtins before Database fallback.
    if dispatch_fn is None:
        from clausal.logic.builtins import get_builtin_predicate  # noqa: PLC0415
        builtin = get_builtin_predicate(functor, arity, module.db)
        if builtin is not None:
            dispatch_fn = builtin._get_dispatch()

    # Fall back to Database dispatch lookup (test modules and Compound-head predicates).
    if dispatch_fn is None:
        dispatch_fn = module.db.get_dispatch(functor, arity)

    if dispatch_fn is None:
        raise KeyError(
            f"Predicate {functor!r}/{arity} is not defined in module {module.name!r}"
        )

    if trail is None:
        trail = Trail()

    for _ in dispatch_fn(*args, trail, None):
        yield trail


def solve(
    goal: Any,
    module: Module,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive an arbitrary goal; yield the Trail after each solution.

    The goal may be any term node: Call, And, Or, Is, Not, In, True, False, …
    Var objects embedded in the goal are referenced by identity in the compiled
    code so their bindings accumulate on the Trail and are readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  Module whose database holds compiled predicates
    trail:   optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).
    """
    if trail is None:
        trail = Trail()

    # Fast paths for trivial goals — avoid the compiler entirely.
    if goal is True:
        yield trail
        return
    if goal is False:
        return

    dispatch_fn = _compile_as_query(goal, module)
    for _ in dispatch_fn(trail, None):
        yield trail


def query(
    goal: Any,
    variables: dict[str, Var],
    module: Module,
    trail: Trail | None = None,
) -> Iterator[dict[str, Any]]:
    """Solve goal and yield one fully-dereferenced binding dict per solution.

    Parameters
    ----------
    goal:      goal term (embed the same Var objects as values of variables)
    variables: mapping of name → Var whose bindings to capture each solution
    module:    Module with compiled database
    trail:     optional Trail (fresh if not provided)

    Yields
    ------
    dict mapping each name in variables to its fully-dereferenced value.
    Unbound Vars remain as Var objects in the dict.
    """
    for _ in solve(goal, module, trail):
        yield {name: _deref_walk(var) for name, var in variables.items()}


def once(
    goal: Any,
    module: Module,
    trail: Trail | None = None,
) -> Trail | None:
    """Return the Trail for the first solution, or None if the goal fails.

    Bindings on the returned Trail are live and readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  Module with compiled database
    trail:   optional Trail (fresh if not provided)

    Returns
    -------
    Trail (with bindings live) on success, or None on failure.
    """
    for t in solve(goal, module, trail):
        return t
    return None


__all__ = [
    "call",
    "solve",
    "query",
    "once",
    "_deref_walk",
]
