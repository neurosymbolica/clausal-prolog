"""clausal.logic.predicate — Predicate-as-Class via PredicateMeta.

PredicateMeta turns a class into a first-class predicate:
  - Class-level clause storage, dispatch, and signature
  - Locking to prevent cross-module mutation
  - __call__ override for partial term creation (missing fields → Var())
  - __init__, __eq__, __repr__, __match_args__ — no @dataclass needed

Usage:
    class fib(metaclass=PredicateMeta):
        _fields = ('n', 'f')

    # fib is a class (not a singleton instance)
    # fib(n=0) creates a term with f=Var()
    # fib._clauses, fib._get_dispatch(), fib._assertz(clause), etc.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable


_MISSING = object()  # sentinel for "field not provided"



_init_cache: dict[tuple[str, ...], Callable] = {}


def _make_init(fields: tuple[str, ...]):
    """Generate an __init__ that accepts fields as keyword args with _MISSING default."""
    cached = _init_cache.get(fields)
    if cached is not None:
        return cached
    if not fields:
        def __init__(self):
            pass
        _init_cache[fields] = __init__
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    fn = globs["__init__"]
    _init_cache[fields] = fn
    return fn


def _term_iter(self):
    """Iterate solutions for this term as a goal.

    Enables ``for trail in greeting(X := Var()): print(deref(X))``.
    """
    from clausal.logic.solve import solve  # noqa: PLC0415
    return solve(self)


def _make_eq(fields: tuple[str, ...]):
    """Generate an __eq__ that compares field values."""
    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return all(getattr(self, f) == getattr(other, f) for f in fields)
    return __eq__


def _make_unify(fields: tuple[str, ...]):
    """Generate a ``__unify__`` that recursively unifies corresponding fields.

    Called by the C ``do_unify`` when two PredicateMeta instances of the
    same type appear on both sides of a unification.
    """
    def __unify__(self, other, trail):
        if type(self) is not type(other):
            return NotImplemented
        from clausal.logic.variables import unify  # noqa: PLC0415
        for f in fields:
            if not unify(getattr(self, f), getattr(other, f), trail):
                return False
        return True
    return __unify__


def _make_repr(fields: tuple[str, ...]):
    """Generate an instance __repr__: ``fib(n=1, f=2)``."""
    def __repr__(self):
        cls_name = type(self).__name__
        parts = ", ".join(f"{f}={getattr(self, f)!r}" for f in fields)
        return f"{cls_name}({parts})"
    return __repr__


class PredicateMeta(type):
    """Metaclass that turns a class with ``_fields`` into a predicate.

    The class body should define ``_fields`` as a tuple of field name strings.
    PredicateMeta generates ``__init__``, ``__eq__``, ``__repr__``,
    ``__match_args__``, and ``__slots__`` from that tuple — no ``@dataclass``
    needed.

    It also adds predicate dispatch machinery:
      _clauses, _dispatch_fn, _lazy_recompile, _signature, _locked
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        **kwargs: Any,
    ) -> PredicateMeta:
        fields: tuple[str, ...] = namespace.get("_fields", ())

        # __slots__ for lightweight instances
        namespace["__slots__"] = fields
        namespace["__match_args__"] = fields

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Instance protocols — generated from _fields
        cls.__init__ = _make_init(fields)
        cls.__eq__ = _make_eq(fields)
        cls.__repr__ = _make_repr(fields)
        cls.__hash__ = None  # mutable terms shouldn't be hashable
        cls.__iter__ = _term_iter
        if fields:
            cls.__unify__ = _make_unify(fields)
        # For zero-field classes (atoms), skip __unify__: the class IS the
        # value, so identity comparison (C line 886: t1 == t2) and the
        # fallback PyObject_RichCompareBool handle unification correctly.

        return cls

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        # Predicate machinery — per-class, not inherited
        cls._clauses: list = []
        cls._dispatch_fn: Callable | None = None
        cls._lazy_recompile: Callable | None = None
        cls._signature: tuple[str, ...] | None = None
        cls._locked: bool = False  # starts unlocked; lock after module load

    # ── Term construction ─────────────────────────────────────────────────

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create a term instance, filling missing fields with fresh Var().

        For zero-arity predicates (atoms), returns the class itself —
        the class IS the atom value.  ``red() is red`` holds.

        - Positional args are mapped to fields in order.
        - Keyword args: any field not provided gets a fresh Var().
        - If no args at all, all fields get Var() (fully unbound term).
        """
        if not cls._fields and not args and not kwargs:
            return cls

        fields = cls._fields

        if args:
            for i, val in enumerate(args):
                if i < len(fields):
                    kwargs[fields[i]] = val

        instance = cls.__new__(cls)
        cls.__init__(instance, **kwargs)

        # Replace _MISSING with fresh Var()
        from clausal.logic.variables import Var  # noqa: PLC0415
        for f in fields:
            if getattr(instance, f) is _MISSING:
                object.__setattr__(instance, f, Var())

        return instance

    # ── Predicate properties ──────────────────────────────────────────────

    @property
    def _functor(cls) -> str:
        return cls.__name__

    @property
    def _arity(cls) -> int:
        return len(cls._fields)

    # ── Clause management ─────────────────────────────────────────────────

    def _assertz(cls, clause: Any) -> None:
        """append clause at end; invalidate compiled dispatch."""
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        cls._clauses.append(clause)
        cls._dispatch_fn = None

    def _asserta(cls, clause: Any) -> None:
        """Prepend clause at front; invalidate compiled dispatch."""
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        cls._clauses.insert(0, clause)
        cls._dispatch_fn = None

    def _retract(cls, head: Any) -> bool:
        """Remove first clause whose head equals head (structural equality).

        Returns True if a clause was removed, False if none matched.
        """
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime retraction."
            )
        for i, clause in enumerate(cls._clauses):
            if clause.head == head:
                del cls._clauses[i]
                cls._dispatch_fn = None
                return True
        return False

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _get_dispatch(cls) -> Callable:
        """Return the compiled dispatch function.

        If dispatch_fn was cleared by assertz/retract and a lazy recompile
        callback is registered, recompiles on demand.
        """
        if cls._dispatch_fn is None:
            if cls._lazy_recompile is not None:
                cls._dispatch_fn = cls._lazy_recompile()
            else:
                raise NotImplementedError(
                    f"Predicate {cls.__name__}/{cls._arity} has no compiled "
                    "dispatch function. The compiler must be run first."
                )
        return cls._dispatch_fn

    # ── Locking ───────────────────────────────────────────────────────────

    def _lock(cls) -> None:
        """Lock the predicate, preventing runtime assertz/retract."""
        cls._locked = True

    def _unlock(cls) -> None:
        """Unlock the predicate, allowing runtime assertz/retract."""
        cls._locked = False

    def __repr__(cls) -> str:
        if not cls._fields:
            return cls.__name__
        compiled = "compiled" if cls._dispatch_fn is not None else "uncompiled"
        n = len(cls._clauses)
        locked = ", locked" if cls._locked else ""
        return (
            f"<Predicate {cls.__name__}/{cls._arity}, "
            f"{n} clause(s), {compiled}{locked}>"
        )


def is_term_instance(obj: Any) -> bool:
    """True if obj is a term instance with named fields (not a type/class).

    Works for both PredicateMeta instances and @dataclass instances.
    Does NOT match built-in AST node types (Compound, Call, KWTerm) —
    callers that need to exclude those must check separately.
    """
    if isinstance(obj, type):
        return False
    if isinstance(type(obj), PredicateMeta):
        return True
    return dataclasses.is_dataclass(obj)


def is_atom(obj: Any) -> bool:
    """True if obj is a zero-arity PredicateMeta class (a declared atom)."""
    return isinstance(obj, PredicateMeta) and not obj._fields


def term_field_names(obj: Any) -> tuple[str, ...]:
    """Return field name strings for a term instance.

    Works for PredicateMeta instances and @dataclass instances.
    """
    cls = type(obj)
    if isinstance(cls, PredicateMeta):
        return cls._fields
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return tuple(f.name for f in dataclasses.fields(obj))
    raise TypeError(f"Not a term instance: {obj!r}")


def make_predicate(name: str, fields: list[str]) -> "PredicateMeta":
    """Dynamically create a PredicateMeta class.

    Useful in tests and runtime code that needs a predicate without a
    module-level class definition::

        foo = make_predicate("foo", ["a", "b"])
        foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
        compile_predicate("foo", 2, foo._clauses, pred_cls=foo)
        fn = foo._get_dispatch()
    """
    return PredicateMeta(name, (), {"_fields": tuple(fields)})


def make_atom(name: str) -> "PredicateMeta":
    """Create a zero-arity PredicateMeta atom.

    The returned class IS the atom value: ``a = make_atom("a"); a() is a``.
    Each call creates a NEW class — call once and reuse the result.

    equivalent to ``make_predicate(name, [])``.
    """
    return make_predicate(name, [])


__all__ = ["PredicateMeta", "_MISSING", "is_term_instance", "is_atom",
           "term_field_names", "make_predicate", "make_atom"]
