"""bottom_up_/1 and pure_/1 — registration goals.

These can be invoked in three equivalent ways:

1. **Top-level in .clausal source** (Python expression executed at module-load
   time)::

       -import_from(provenance, [bottom_up_, pure_, solve, boolean])
       bottom_up_(Path),         # registers Path/2 for bottom-up evaluation
       pure_(SafeNeighbour),

2. **As an in-body goal** in a .clausal rule or Test clause::

       Test("setup") <- bottom_up_(Path)

3. **From Python**::

       from clausal.modules.provenance import bottom_up_
       bottom_up_(Path)            # call as a regular Python function

All three set the same flag on the named predicate's ``PredicateMeta`` class
that the bottom-up engine reads at solve time. Arity is taken from the
class.

The registration object presents three interfaces:
- ``__call__(cls)`` — Python-side (covers cases 1 and 3 above; .clausal source
  expressions like ``bottom_up_(Path)`` are compiled to a Python call at
  load time).
- ``_get_dispatch()`` — Clausal trampoline-protocol dispatch (covers case 2).

The trailing underscore mirrors existing Clausal naming for "registration
predicate that doubles as a directive" (cf. ``-discontiguous`` discussions
in core). A future core enhancement could promote these to true
``-bottom_up`` / ``-pure`` directives — strictly cosmetic, off the
critical path.
"""

from __future__ import annotations

import sys

from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import deref
from clausal.logic.trampoline import DONE


def _resolve_loadname(arg):
    """Resolve a ``LoadName(name=...)`` AST node to a runtime value.

    Clausal's compiler wraps bare identifiers in body and top-level term
    positions as ``LoadName`` nodes for late resolution. When we receive
    one as a ``__call__`` argument we walk the calling frame's globals
    to recover the actual class.
    """
    # Quick reject: PredicateMeta classes (already-resolved values) and
    # plain Python objects.
    if isinstance(arg, PredicateMeta):
        return arg
    name = getattr(arg, "name", None)
    if not isinstance(name, str):
        return arg
    # LoadName-shaped (has a string ``.name``) — search outward.
    frame = sys._getframe(2)  # skip __call__ + _resolve_loadname
    while frame is not None:
        for ns in (frame.f_locals, frame.f_globals):
            if name in ns:
                return ns[name]
        frame = frame.f_back
    return arg


# ── Flag attribute names (centralised so the engine can import them) ────

BOTTOM_UP_FLAG = "_provenance_bottom_up"
PURE_FLAG = "_provenance_pure"


# ── Combined Python-callable + ModulePredicate-shaped registration ──────


class _RegistrationGoal:
    """A registration helper usable as Python callable, builtin, or goal."""

    __slots__ = ("_name", "_flag", "_dispatch_fns")

    def __init__(self, name: str, flag: str) -> None:
        self._name = name
        self._flag = flag
        self._dispatch_fns: dict = {1: self._dispatch_1}

    # ── Python-callable form ────────────────────────────────────────
    def __call__(self, *args, **kwargs):
        # Accept positional (Python-side, ``bottom_up_(Path)``) or the
        # generated keyword form Clausal's compiler emits at top-level
        # (``bottom_up_(arg_0=Path)``). Clausal's TermTransformer wraps
        # bare names as ``LoadName(name=...)`` AST nodes — when we see
        # one, resolve it against the calling frame's globals.
        if args and not kwargs:
            cls = args[0]
        elif kwargs and not args:
            cls = next(iter(kwargs.values()))
        elif args and kwargs:
            cls = args[0]
        else:
            raise TypeError(f"{self._name}() requires one argument")
        cls = deref(cls)
        cls = _resolve_loadname(cls)
        if not isinstance(cls, PredicateMeta):
            raise TypeError(
                f"{self._name} expects a PredicateMeta class, got {cls!r}. "
                "Use the bare class name, e.g. `bottom_up_(Path)`."
            )
        setattr(cls, self._flag, True)
        return cls

    # ── In-body goal form (trampoline protocol) ─────────────────────
    def _dispatch_1(self, this_generator, _proceed, _fail, _catcher, pred, trail):
        try:
            self.__call__(pred)
        except Exception:
            yield (_fail, DONE)
            return
        yield (_proceed, None)
        yield (_fail, DONE)

    def _get_dispatch(self):
        return self._dispatch_1

    def __repr__(self) -> str:
        return f"<{self._name}/1 registration goal>"


# ── Public objects ──────────────────────────────────────────────────────

bottom_up_ = _RegistrationGoal("bottom_up_", BOTTOM_UP_FLAG)
pure_ = _RegistrationGoal("pure_", PURE_FLAG)


def is_bottom_up(cls) -> bool:
    """True if cls has been registered via bottom_up_."""
    return bool(getattr(cls, BOTTOM_UP_FLAG, False))


def is_pure(cls) -> bool:
    """True if cls has been marked via pure_."""
    return bool(getattr(cls, PURE_FLAG, False))


__all__ = [
    "bottom_up_",
    "pure_",
    "is_bottom_up",
    "is_pure",
    "BOTTOM_UP_FLAG",
    "PURE_FLAG",
]
