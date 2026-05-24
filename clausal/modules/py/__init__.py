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

        Hash = ModulePredicate("Hash")
        Hash._register(3, simple_to_trampoline(_hash_3))
    """

    __slots__ = ("_name", "_module", "_dispatch_fns")

    def __init__(self, name: str, *, module: str = "") -> None:
        self._name = name
        self._module = module
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (_fail, DONE)
            return
        yield from fn(this_generator, _proceed, _fail, _catcher, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        prefix = f"{self._module}." if self._module else ""
        return f"{prefix}{self._name}/{arities}"


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


def to_bytes(val):
    """Convert string or bytes to bytes, or return None."""
    if isinstance(val, str):
        return val.encode("utf-8")
    if isinstance(val, bytes):
        return val
    return None


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
