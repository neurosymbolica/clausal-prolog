"""clausal.modules.py — canonical Python library wrappers.

Each wrapper module is named after the Python library it wraps. Stdlib
wrappers (``csv``, ``datetime``, ``json``, ``os``, ``random``, ``re``,
``uuid``, etc.) ship with core Clausal. Third-party wrappers (``torch``,
``sympy``, ``jax``, ``opencv``, ``scipy_*``, ``sklearn``, ``spacy``,
``yaml``) ship in separately installable extension distributions
(clausal-torch, clausal-sympy, …) that contribute files into this
subpackage via PEP 420 namespace packaging.
"""

from __future__ import annotations

# Extend __path__ so that separately-installed wrapper distributions
# (e.g. clausal-torch) that place files under clausal/modules/py/ in
# site-packages are discoverable alongside the core source tree.
_sp = _candidate = _finder = _finder_module = _namespaces = None
import os as _os, site as _site
for _sp in _site.getsitepackages():
    _candidate = _os.path.join(_sp, "clausal", "modules", "py")
    if _os.path.isdir(_candidate) and _candidate not in __path__:
        __path__.append(_candidate)

# Discover editable installs: setuptools' modern editable finder (verified
# against setuptools >=64) registers a class in sys.meta_path; the
# NAMESPACES dict mapping fully-qualified package names to source
# directories lives on the finder *module* (reachable via
# sys.modules[finder.__module__]). Without this, `pip install -e
# packages/clausal-X` would not contribute its `clausal/modules/py/<name>.py`
# to clausal.modules.py.__path__.
import sys as _sys
for _finder in list(_sys.meta_path):
    _finder_module = _sys.modules.get(getattr(_finder, "__module__", None) or "")
    _namespaces = getattr(_finder_module, "NAMESPACES", None)
    if not isinstance(_namespaces, dict):
        continue
    for _candidate in _namespaces.get("clausal.modules.py", ()):
        if _candidate and _candidate not in __path__:
            __path__.append(_candidate)
del _os, _site, _sp, _sys, _finder, _finder_module, _namespaces, _candidate

from typing import Callable

from clausal.logic.trampoline import DONE


# ── Shared base adapter ─────────────────────────────────────────────────────


class ModulePredicate:
    """Base adapter providing ``_get_dispatch()`` for module predicates.

    Every ``py.*`` module needs a tiny adapter class so the Clausal runtime
    can look up the dispatch function for a given arity.  This base class
    captures the pattern that was previously copy-pasted into every module.

    Usage::

        hash = ModulePredicate("hash")
        hash._register(3, simple_to_trampoline(_hash_3))
    """

    __slots__ = ("_name", "_module", "_dispatch_fns", "_dispatch_wrapper")

    def __init__(self, name: str, *, module: str = "") -> None:
        self._name = name
        self._module = module
        self._dispatch_fns: dict[int, Callable] = {}
        self._dispatch_wrapper: Callable | None = None

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        # Always route through the arity-checking dispatcher so wrong-arity is
        # a consistent, catchable error (F005) and stdlib exceptions raised by
        # the implementation are converted to catchable terms (F004). Compiled
        # goals call _get_dispatch per invocation, so cache the wrapper —
        # _multi_dispatch reads _dispatch_fns at call time, so later
        # _register calls are still honoured.
        wrapper = self._dispatch_wrapper
        if wrapper is None:
            wrapper = self._dispatch_wrapper = _catchable_dispatch(
                self._multi_dispatch
            )
        return wrapper

    def _multi_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            # Unregistered arity is an existence error, not a silent failure —
            # consistent whether the predicate has one arity or several (F005).
            from clausal.logic.exceptions import (
                LogicException, existence_error,
            )
            from clausal.terms import Compound
            indicator = Compound("/", (self._name, arity))
            raise LogicException(
                existence_error("procedure", indicator, self._name)
            )
        yield from fn(this_generator, _proceed, _fail, _catcher, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        prefix = f"{self._module}." if self._module else ""
        return f"{prefix}{self._name}/{arities}"


def _catchable_dispatch(dispatch_fn):
    """Wrap a module-predicate dispatch so stdlib exceptions are catchable.

    Module predicates are driven by the top-level trampoline, so a raw Python
    exception raised inside the implementation propagates *outside* any
    enclosing catch/3 Python try-block and escapes solve() uncaught — unlike a
    ``++`` thunk, whose errors the compiler converts. Only ``LogicException``
    is routed through the catcher chain. Convert every other exception to a
    ``LogicException`` carrying ``python_error_term(exc)`` so catch/3 catches
    module-predicate errors the same way it catches ``throw/1`` (F004).
    """
    def wrapped(this_generator, _proceed, _fail, _catcher, *args):
        from clausal.logic.exceptions import LogicException, python_error_term
        try:
            yield from dispatch_fn(this_generator, _proceed, _fail, _catcher, *args)
        except LogicException:
            raise
        except Exception as exc:  # noqa: BLE001 — deliberate boundary conversion
            raise LogicException(python_error_term(exc)) from exc
    return wrapped


def simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(arg1, ..., argN, trail, k) → trampoline protocol.

    Simple-mode functions yield ``None`` for each solution.  The wrapper
    translates to the trampoline protocol where solutions are ``(parent, None)``
    and termination is ``(parent, DONE)``.

    The ``k`` (continuation) parameter is passed as ``None`` since
    trampoline-mode predicates don't use continuations.
    """
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args, None):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


def to_text(val):
    """The plain ``str`` a ``py.*`` wrapper argument denotes, or ``None``.

    Spec §9.4: a wrapper that takes text accepts an **atom** or a **string**,
    and both convert to the same ``str``.  THE FLIP
    (2026-09-06-atoms-as-cells-strings) made routing this through ``str()``
    a live footgun: ``str(("bar",))`` is the Python tuple *repr*
    ``"('bar',)"``, so a wrapper that coerced that way would silently use a
    repr as a filename, a regex, a logger name or a SQL string — during the
    flip that is exactly how a file literally named ``(':memory:',)`` got
    created in the repo root.  Every text coercion in a wrapper routes here.

    - a ``str`` → itself;
    - an ATOM ``("bar",)`` → its spelling;
    - a ``SegString`` / any object with a ``__walk__`` that yields a ``str``
      (a partial string that is now complete) → that ``str``;
    - a list/tuple of char atoms → the string it denotes;
    - a CELL of arity >= 1 → ``type_error(text, …)``: a compound is not text,
      and answering with its repr is the bug above;
    - anything else (an unbound ``Var``, a number, a non-char list, …) →
      ``None``, so the caller keeps its own "fail cleanly / record a
      type-mismatch note" behaviour.
    """
    if type(val) is str:
        return val
    from clausal.logic.atoms import is_atom as _is_atom, spelling as _spelling
    from clausal.logic.variables import deref
    val = deref(val)
    if type(val) is str:
        return val
    if _is_atom(val):
        return _spelling(val)
    walk = getattr(val, "__walk__", None)
    if callable(walk):
        walked = walk()
        if type(walked) is str:
            return walked
        val = walked
    if isinstance(val, tuple) and val and type(val[0]) is str:
        # A cell of arity >= 1: a compound term, not text.  Loud, never a repr.
        from clausal.logic.exceptions import LogicException, type_error
        raise LogicException(type_error("text", val))
    if isinstance(val, (list, tuple)):
        if not val:
            return ""
        from clausal.logic.runtime._seg_helpers import maybe_promote_to_str
        promoted = maybe_promote_to_str([deref(e) for e in val])
        if type(promoted) is str:
            return promoted
    return None


def to_bytes(val):
    """Convert text (a string or an ATOM, spec §9.4) or bytes to bytes, else None."""
    if isinstance(val, bytes):
        return val
    text = to_text(val)
    if text is not None:
        return text.encode("utf-8")
    return None


# ── Type-mismatch diagnostic notes ──────────────────────────────────────────
#
# A py-interop predicate that bails on a type guard produces a bare "no" —
# indistinguishable from a goal that genuinely has no solution (see
# todo/C1-ill-typed-interop-calls-are-silent-failures.md).  Raising type_error
# instead would change semantics for every existing caller, so the guards
# stay guards; but while a collector is active (the failure-diagnostic re-run
# in clausal.testing) each rejection records what it rejected.

# The active note sink, or None outside a diagnostic re-run.  A plain module
# global, not a contextvar: the engine solves single-threaded and the
# diagnostic re-run is synchronous.
_mismatch_notes: list | None = None
_mismatch_seen: set | None = None


class _NoteCollection:
    """Context manager handed out by :func:`collect_type_mismatch_notes`."""

    def __enter__(self):
        global _mismatch_notes, _mismatch_seen
        self._prev = (_mismatch_notes, _mismatch_seen)
        _mismatch_notes = []
        _mismatch_seen = set()
        return _mismatch_notes

    def __exit__(self, *exc_info):
        global _mismatch_notes, _mismatch_seen
        _mismatch_notes, _mismatch_seen = self._prev
        return False


def collect_type_mismatch_notes():
    """Collect py-interop type-rejection notes for the ``with`` block.

    Yields the (deduplicated, in rejection order) list of note strings; it is
    filled in place as guards fire, so it can be read after the block.
    """
    return _NoteCollection()


def _record_note(message: str) -> None:
    if _mismatch_notes is None or message in _mismatch_seen:
        return
    _mismatch_seen.add(message)
    _mismatch_notes.append(message)


def expect_type(value, types, pred, *, expected=None, arg=None) -> bool:
    """Type guard for a py-interop argument: True iff *value* may be used.

    ``isinstance``-check plus rejection note.  An unbound Var fails silently
    — that is a mode signal, and the diagnostic's rung-2 analysis already
    reports unbound arguments; only a BOUND value of the wrong type records
    "*pred* was called with <actual> where <expected> is required".

    *expected* overrides the type-derived wording (e.g. "date or datetime");
    *arg* is the 1-based argument position for the "(argument N)" suffix.
    """
    if isinstance(value, types):
        return True
    # Import on the failure path only — the success path above is hot
    # (every well-typed interop call passes through it).
    from clausal.logic.variables import is_var
    if not is_var(value):
        if expected is None:
            if isinstance(types, tuple):
                expected = " or ".join(t.__name__ for t in types)
            else:
                expected = types.__name__
        where = f" (argument {arg})" if arg is not None else ""
        _record_note(
            f"{pred} was called with {type(value).__name__} "
            f"where {expected} is required{where}"
        )
    return False


def note_mismatch(pred, detail: str) -> None:
    """Record a rejection the ``isinstance`` helper cannot phrase.

    For guards where the mismatch is not "wrong class" — e.g. ``date`` mixed
    with ``datetime`` (not comparable), or a ``datetime`` where a plain
    ``date`` is required (a subclass, so ``isinstance`` passes).  *detail*
    completes the sentence: ``f"{pred} {detail}"``.
    """
    _record_note(f"{pred} {detail}")


def value_is_ground(value) -> bool:
    """Conservative groundness check for gating rejection notes.

    A term whose top level is bound can still hold a nested unbound Var; a
    serializer choking on that Var is a mode/instantiation situation, not
    an ill-typed call, and its exception text leaks internal type names
    ("Object of type Var is not JSON serializable") — the same rule as the
    datetime constructors' fully-bound-only notes.  True on any doubt: a
    wrongly-recorded note is better than a wrongly-suppressed one.
    """
    try:
        from clausal.logic.builtins._helpers import _is_ground
        return bool(_is_ground(value))
    except Exception:  # noqa: BLE001 - gate must never break the guard
        return True


def note_rejected_call(pred, exc) -> None:
    """Record that *pred*'s underlying Python call rejected its arguments.

    For the try/except twin of the isinstance guard: constructors like
    ``datetime.date`` reject bad values (month=13) or bad types with an
    exception whose message says exactly what was wrong — worth surfacing
    for the same reason as the guard note.
    """
    _record_note(
        f"{pred} rejected its arguments — {type(exc).__name__}: {exc}"
    )


# ── Stdlib import helper ─────────────────────────────────────────────────────


def _import_stdlib(name):
    """Import a stdlib/third-party module, bypassing clausal's ModulesFinder.

    Prevents circular imports when a ``py/*.py`` implementation file has
    the same name as the Python module it wraps (e.g. ``py/uuid.py``
    wrapping stdlib ``uuid``).
    """
    import importlib
    from clausal.import_hook import ModulesFinder

    ModulesFinder._resolving.add(name)
    try:
        return importlib.import_module(name)
    finally:
        ModulesFinder._resolving.discard(name)
