"""Registry infrastructure for builtin predicates.

Provides the decorator-based registration system, adapter classes
(BuiltinPredicate, MultiArityBuiltin), and the public lookup API.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.predicate import (
    PredicateMeta, is_term_instance, term_field_names, make_predicate,
)
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.terms import Compound, DictTerm, SetTerm, KWTerm


# ── Simple → trampoline adapter ──────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode dispatch function as a trampoline-protocol function.

    Simple-mode signature:  ``fn(*args, trail, k)`` → yields ``None``
    Trampoline signature:   ``fn(this_gen, parent, *args, trail)`` → yields ``(parent, None)`` / ``(parent, DONE)``
    """
    def trampoline_fn(this_generator, parent, *args):
        # args = (*pred_args, trail)  — trail is always last
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


def _wrap_db_factory(factory):
    """Wrap a DB-builtin factory so its product is trampoline-protocol."""
    def wrapped_factory(db):
        simple_fn = factory(db)
        return _simple_to_trampoline(simple_fn)
    return wrapped_factory


# ── Registry dicts ─────────────────────────────────────────────────────────────
# _BUILTINS: trampoline-protocol dispatch functions  {(functor, arity) → fn}
# _DB_BUILTINS: factory callables  {(functor, arity) → fn(db) → trampoline dispatch_fn}

_BUILTINS: dict[tuple[str, int], Callable] = {}
_DB_BUILTINS: dict[tuple[str, int], Callable] = {}
_BUILTIN_FIELDS: dict[tuple[str, int], tuple[str, ...]] = {}


def _extract_fields_simple(fn: Callable) -> tuple[str, ...]:
    """Extract field names from a simple-mode builtin (strip trail, k)."""
    params = list(inspect.signature(fn).parameters)
    return tuple(params[:-2])  # drop trail, k


def _extract_fields_trampoline(fn: Callable) -> tuple[str, ...]:
    """Extract field names from a trampoline builtin (strip this_generator, parent, trail)."""
    params = list(inspect.signature(fn).parameters)
    return tuple(params[2:-1])  # drop this_generator, parent, and trail


def _builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None):
    """Decorator: register a function as a stateless built-in (auto-wrapped to trampoline)."""
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = _simple_to_trampoline(fn)
        _BUILTIN_FIELDS[(functor, arity)] = fields or _extract_fields_simple(fn)
        return fn
    return decorator


def _trampoline_builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None):
    """Decorator: register a native trampoline-protocol built-in (no wrapping).

    Use for builtins that operate on lists or call sub-goals, so they
    participate directly in the trampoline without an extra wrapper layer.

    Signature: ``fn(this_generator, parent, arg0, …, argN-1, trail)``
    Must yield ``(parent, None)`` per solution and ``(parent, DONE)`` at end.
    """
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = fn
        _BUILTIN_FIELDS[(functor, arity)] = fields or _extract_fields_trampoline(fn)
        return fn
    return decorator


def _ensure_trampoline_dispatch(goal_val):
    """Return a trampoline-protocol dispatch function for *goal_val*.

    Handles:
    - PredicateMeta / BuiltinPredicate with ``_get_dispatch()`` → returns that
    - Simple-mode callable ``fn(*args, trail, k)`` → wraps to trampoline
    """
    if hasattr(goal_val, '_get_dispatch'):
        return goal_val._get_dispatch()
    # Assume simple-mode callable
    return _simple_to_trampoline(goal_val)


def _db_builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None):
    """Decorator: register a factory as a db-dependent built-in (auto-wrapped to trampoline)."""
    def decorator(factory: Callable) -> Callable:
        _DB_BUILTINS[(functor, arity)] = _wrap_db_factory(factory)
        if fields is not None:
            _BUILTIN_FIELDS[(functor, arity)] = fields
        else:
            _BUILTIN_FIELDS[(functor, arity)] = tuple(f"arg{i}" for i in range(arity))
        return factory
    return decorator


# ── structural_unify ──────────────────────────────────────────────────────────


def structural_unify(t1: Any, t2: Any, trail: Any) -> bool:
    """Python-level structural unification that handles Compound, KWTerm, and dataclasses.

    The C extension's ``unify`` handles Var, tuple, list, and atomic equality.
    This wrapper adds recursive unification for Compound, KWTerm, and dataclass
    terms (WK-6 cross-representation unification).
    """
    t1 = deref(t1)
    t2 = deref(t2)

    # If either is unbound Var, delegate to the C unify (it handles Var binding).
    if is_var(t1) or is_var(t2):
        return bool(unify(t1, t2, trail))

    # Both are ground (or at least non-Var at the top level).
    # Compound ↔ Compound
    if isinstance(t1, Compound) and isinstance(t2, Compound):
        if t1.functor != t2.functor or len(t1.args) != len(t2.args):
            return False
        mark = trail.mark()
        for a1, a2 in zip(t1.args, t2.args):
            if not structural_unify(a1, a2, trail):
                trail.undo(mark)
                return False
        return True

    # list ↔ list
    if isinstance(t1, list) and isinstance(t2, list):
        if len(t1) != len(t2):
            return False
        mark = trail.mark()
        for e1, e2 in zip(t1, t2):
            if not structural_unify(e1, e2, trail):
                trail.undo(mark)
                return False
        return True

    # term instance ↔ term instance (same type)
    if (
        is_term_instance(t1)
        and is_term_instance(t2)
        and type(t1) is type(t2)
    ):
        fields = term_field_names(t1)
        mark = trail.mark()
        for name in fields:
            if not structural_unify(getattr(t1, name), getattr(t2, name), trail):
                trail.undo(mark)
                return False
        return True

    # KWTerm ↔ KWTerm (same functor and same key set)
    if isinstance(t1, KWTerm) and isinstance(t2, KWTerm):
        if t1.functor != t2.functor or set(t1.keys()) != set(t2.keys()):
            return False
        mark = trail.mark()
        for key in t1.keys():
            if not structural_unify(t1._fields[key], t2._fields[key], trail):
                trail.undo(mark)
                return False
        return True

    # DictTerm ↔ DictTerm (same key set, values unify pairwise)
    if isinstance(t1, DictTerm) and isinstance(t2, DictTerm):
        if t1.keys() != t2.keys():
            return False
        mark = trail.mark()
        for key in t1.keys():
            if not structural_unify(t1[key], t2[key], trail):
                trail.undo(mark)
                return False
        return True

    # SetTerm ↔ SetTerm (same elements — elements must be ground)
    if isinstance(t1, SetTerm) and isinstance(t2, SetTerm):
        return t1.elements == t2.elements

    # Fall back to C unify for all other combinations (atoms, tuples, etc.)
    return bool(unify(t1, t2, trail))


# ── BuiltinPredicate adapter ─────────────────────────────────────────────────


class BuiltinPredicate:
    """Adapter wrapping a builtin dispatch function with the ``_get_dispatch()``
    protocol used by PredicateMeta classes.

    Stateless builtins store the dispatch function directly.  DB-dependent
    builtins (assertz, retract, etc.) store the factory; ``_get_dispatch()``
    calls the factory lazily on first use.

    Multi-arity support: when a predicate name has multiple arities (e.g.
    Match/2 and Match/3), ``_merge`` combines them into one adapter with
    an arity-dispatching ``_get_dispatch()`` that selects at call time.
    """
    __slots__ = ("_functor", "_arity", "_dispatch_fn", "_factory", "_db",
                 "_arity_map")

    def __init__(
        self,
        functor: str,
        arity: int,
        dispatch_fn: Callable | None = None,
        factory: Callable | None = None,
        db: Any = None,
    ) -> None:
        self._functor = functor
        self._arity = arity
        self._dispatch_fn = dispatch_fn
        self._factory = factory
        self._db = db
        self._arity_map: dict[int, Callable] | None = None

    def _get_dispatch(self) -> Callable:
        if self._arity_map is not None:
            return self._arity_dispatch
        if self._dispatch_fn is None:
            if self._factory is not None and self._db is not None:
                self._dispatch_fn = self._factory(self._db)
            else:
                raise NotImplementedError(
                    f"Builtin {self._functor}/{self._arity} has no dispatch function"
                )
        return self._dispatch_fn

    def _arity_dispatch(self, this_generator, parent, *args):
        """Dispatch to the correct arity handler based on arg count.

        Trampoline protocol: args = (*pred_args, trail).
        Arity = len(args) - 1.
        """
        arity = len(args) - 1  # exclude trail
        fn = self._arity_map.get(arity)
        if fn is None:
            from clausal.logic.trampoline import DONE as _DONE
            yield (parent, _DONE)
            return
        yield from fn(this_generator, parent, *args)

    def _merge(self, other: "BuiltinPredicate") -> None:
        """Merge another BuiltinPredicate into this one for multi-arity dispatch."""
        if self._arity_map is None:
            self._arity_map = {}
            # Add our own arity to the map.
            if self._dispatch_fn is not None:
                self._arity_map[self._arity] = self._dispatch_fn
            elif self._factory is not None and self._db is not None:
                self._arity_map[self._arity] = self._factory(self._db)
        if other._dispatch_fn is not None:
            self._arity_map[other._arity] = other._dispatch_fn
        elif other._factory is not None and other._db is not None:
            self._arity_map[other._arity] = other._factory(other._db)

    def __repr__(self) -> str:
        if self._arity_map:
            arities = sorted(self._arity_map)
            return f"BuiltinPredicate({self._functor!r}/{arities})"
        return f"BuiltinPredicate({self._functor!r}/{self._arity})"


# ── Public lookup API ─────────────────────────────────────────────────────────


def get_builtin_predicate(
    functor: str, arity: int, db: Any = None
) -> BuiltinPredicate | None:
    """Return a ``BuiltinPredicate`` adapter for the given functor/arity, or None.

    For stateless builtins the same singleton is returned on every call.
    For DB-dependent builtins a new adapter is created with the given ``db``.
    """
    key = (functor, arity)
    fn = _BUILTINS.get(key)
    if fn is not None:
        return BuiltinPredicate(functor, arity, dispatch_fn=fn)
    factory = _DB_BUILTINS.get(key)
    if factory is not None:
        return BuiltinPredicate(functor, arity, factory=factory, db=db)
    return None


def get_builtin_dispatch(
    functor: str, arity: int, db: Any
) -> Callable | None:
    """Return the dispatch function for a built-in predicate, or None.

    Called by ``Database.get_dispatch`` when a predicate is not found locally.
    """
    key = (functor, arity)
    fn = _BUILTINS.get(key)
    if fn is not None:
        return fn
    factory = _DB_BUILTINS.get(key)
    if factory is not None:
        return factory(db)
    return None


# ── MultiArityBuiltin + class builder ─────────────────────────────────────────


class MultiArityBuiltin:
    """Wrapper for builtins with multiple arities (e.g. MapList/2 and MapList/3).

    Routes term construction to the correct PredicateMeta class based on the
    number of positional arguments, and provides arity-based dispatch.
    """
    __slots__ = ("_functor", "_arity_classes", "_arity_dispatch_fns")

    def __init__(self, functor: str) -> None:
        self._functor = functor
        self._arity_classes: dict[int, PredicateMeta] = {}
        self._arity_dispatch_fns: dict[int, Callable] = {}

    def _add(self, arity: int, cls: PredicateMeta, dispatch_fn: Callable | None) -> None:
        self._arity_classes[arity] = cls
        if dispatch_fn is not None:
            self._arity_dispatch_fns[arity] = dispatch_fn

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Construct a term, routing to the correct arity class by arg count."""
        arity = len(args) + len(kwargs)
        cls = self._arity_classes.get(arity)
        if cls is None:
            # Fall back to max arity class and let it fill missing fields
            cls = self._arity_classes[max(self._arity_classes)]
        return cls(*args, **kwargs)

    def _get_dispatch(self) -> Callable:
        """Return an arity-dispatching function for the trampoline."""
        fns = self._arity_dispatch_fns

        def _dispatch(this_generator, parent, *args):
            arity = len(args) - 1  # exclude trail
            fn = fns.get(arity)
            if fn is None:
                yield (parent, DONE)
                return
            yield from fn(this_generator, parent, *args)

        return _dispatch

    def __repr__(self) -> str:
        arities = sorted(self._arity_classes)
        return f"<BuiltinClass {self._functor}/{arities}>"


# Populated by _build_all_builtin_classes() at module load time.
# Maps functor name → PredicateMeta class (single-arity) or MultiArityBuiltin.
_BUILTIN_CLASSES: dict[str, PredicateMeta | MultiArityBuiltin] = {}


def _build_all_builtin_classes() -> None:
    """Create PredicateMeta classes for all registered builtins.

    Called once at module load.  Groups multi-arity builtins under one name.
    """
    # Collect all (functor, arity) → dispatch_fn pairs
    all_keys: dict[str, list[int]] = {}
    for functor, arity in list(_BUILTIN_FIELDS):
        all_keys.setdefault(functor, []).append(arity)

    for functor, arities in all_keys.items():
        if len(arities) == 1:
            arity = arities[0]
            fields = _BUILTIN_FIELDS[(functor, arity)]
            cls = make_predicate(functor, list(fields))
            dispatch_fn = _BUILTINS.get((functor, arity))
            if dispatch_fn is not None:
                cls._dispatch_fn = dispatch_fn
            cls._locked = True
            _BUILTIN_CLASSES[functor] = cls
        else:
            wrapper = MultiArityBuiltin(functor)
            for arity in sorted(arities):
                fields = _BUILTIN_FIELDS[(functor, arity)]
                cls = make_predicate(f"{functor}", list(fields))
                dispatch_fn = _BUILTINS.get((functor, arity))
                if dispatch_fn is not None:
                    cls._dispatch_fn = dispatch_fn
                cls._locked = True
                wrapper._add(arity, cls, dispatch_fn)
            _BUILTIN_CLASSES[functor] = wrapper


def get_builtin_class(functor: str) -> PredicateMeta | MultiArityBuiltin | None:
    """Return the constructable class/wrapper for a builtin, or None."""
    return _BUILTIN_CLASSES.get(functor)
