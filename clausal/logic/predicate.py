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


class _FakeField:
    """Minimal stand-in for ``dataclasses.Field`` so that PredicateMeta classes
    pass ``dataclasses.is_dataclass()`` and ``dataclasses.fields()`` checks.

    Only ``name`` and ``_field_type`` are needed; existing code only reads
    ``f.name`` from the result of ``dataclasses.fields()``.
    """
    __slots__ = ("name", "_field_type")

    def __init__(self, name: str) -> None:
        self.name = name
        self._field_type = dataclasses._FIELD  # noqa: SLF001


def _make_init(fields: tuple[str, ...]):
    """Generate an __init__ that accepts fields as keyword args with _MISSING default."""
    if not fields:
        def __init__(self):
            pass
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    return globs["__init__"]


def _make_eq(fields: tuple[str, ...]):
    """Generate an __eq__ that compares field values."""
    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return all(getattr(self, f) == getattr(other, f) for f in fields)
    return __eq__


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

        # Dataclass compatibility — lets existing dataclasses.is_dataclass()
        # and dataclasses.fields() calls work without changes.  Cleaned up
        # in Phase 7 when all call sites switch to PredicateMeta-aware checks.
        cls.__dataclass_fields__ = {f: _FakeField(f) for f in fields}

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

        - Positional args are mapped to fields in order.
        - Keyword args: any field not provided gets a fresh Var().
        - If no args at all, all fields get Var() (fully unbound term).
        """
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
        """Append clause at end; invalidate compiled dispatch."""
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
        compiled = "compiled" if cls._dispatch_fn is not None else "uncompiled"
        n = len(cls._clauses)
        locked = ", locked" if cls._locked else ""
        return (
            f"<Predicate {cls.__name__}/{cls._arity}, "
            f"{n} clause(s), {compiled}{locked}>"
        )


__all__ = ["PredicateMeta", "_MISSING"]
