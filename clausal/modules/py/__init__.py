"""clausal.modules.py — Python library wrapper modules for Clausal.

This subpackage contains Clausal predicate wrappers around Python
standard library and third-party modules::

    -import_from(py.sympy, [Simplify, Solve, Diff, sin, cos])
    -import_from(py.uuid, [UUIDv4, UUIDStr, IsUUID])
    -import_from(py.yaml, [Read, write, Get])
    -import_from(py.sqlite, [SQLiteConnect, SQLiteQuery])
    -import_from(py.datetime, [Now, Today, Date, TimeDelta])
    -import_from(py.re, [Match, Search, Replace, Split, findall])
    -import_from(py.logging, [GetLogger, Info, Debug, Warning, Error])
    -import_from(py.random, [Random, RandomInteger, RandomMember, Maybe])
    -import_from(py.json, [Parse, Generate, Get, ReadFile])
    -import_from(py.csv, [Parse, ParseRow, ReadFile, ReadRecords])
    -import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])
    -import_from(py.files, [FileExists, DirectoryFiles, ReadFileToString, JoinPath])
    -import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])

The legacy names (``sympy_module``, ``uuid_mod``, ``yaml_module``,
``regex``, ``log``, ``date_time``, ``sqlite``) are compatibility shims
that re-export from here.
"""

from __future__ import annotations

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
