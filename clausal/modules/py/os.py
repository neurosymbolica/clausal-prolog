"""clausal.modules.py.os — OS interaction predicates for Clausal.

Provides relational predicates for environment variables, working directory,
process info, and system metadata.  Import via::

    -import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])

Or via module import::

    -import_module(py.os)
    # then use py.os.EnvironmentVariable("HOME", H_), py.os.Pid(P_), etc.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_os = _import_stdlib("os")
_sys = _import_stdlib("sys")

from typing import Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ────────────────────────────────────────────────────


class _OsPredicate:
    """Adapter with ``_get_dispatch()`` for an os predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"os.{self._name}/{arities}"


# ── Simple-mode wrapper ─────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Predicates ──────────────────────────────────────────────────────────


def _environment_variable_2(name, value, trail, k):
    """EnvironmentVariable/2: get/enumerate environment variables.

    Name bound → look up value. Name unbound → enumerate all env vars.
    """
    name = deref(name)
    if is_var(name):
        # Enumerate all env vars
        for env_name, env_value in _os.environ.items():
            mark = trail.mark()
            if unify(name, env_name, trail) and unify(value, env_value, trail):
                yield None
            trail.undo(mark)
    else:
        if not isinstance(name, str):
            return
        env_value = _os.environ.get(name)
        if env_value is None:
            return
        if unify(value, env_value, trail):
            yield None


def _set_environment_variable_2(name, value, trail, k):
    """SetEnvironmentVariable/2: set an environment variable."""
    name, value = deref(name), deref(value)
    if is_var(name) or is_var(value):
        return
    if not isinstance(name, str) or not isinstance(value, str):
        return
    _os.environ[name] = value
    yield None


def _unset_environment_variable_1(name, trail, k):
    """UnsetEnvironmentVariable/1: remove an environment variable."""
    name = deref(name)
    if is_var(name) or not isinstance(name, str):
        return
    if name not in _os.environ:
        return
    del _os.environ[name]
    yield None


def _working_directory_1(path, trail, k):
    """WorkingDirectory/1: unify Path with the current working directory."""
    cwd = _os.getcwd()
    if unify(path, cwd, trail):
        yield None


def _change_directory_1(path, trail, k):
    """ChangeDirectory/1: change the current working directory."""
    path = deref(path)
    if is_var(path) or not isinstance(path, str):
        return
    try:
        _os.chdir(path)
    except OSError:
        return
    yield None


def _pid_1(p, trail, k):
    """Pid/1: unify P with the current process ID."""
    if unify(p, _os.getpid(), trail):
        yield None


def _argv_1(args, trail, k):
    """Argv/1: unify Args with sys.argv as a Python list."""
    if unify(args, list(_sys.argv), trail):
        yield None


def _platform_1(p, trail, k):
    """Platform/1: unify P with sys.platform."""
    if unify(p, _sys.platform, trail):
        yield None


def _cpu_count_1(n, trail, k):
    """CPUCount/1: unify N with os.cpu_count()."""
    count = _os.cpu_count()
    if count is not None and unify(n, count, trail):
        yield None


# ── Build and export predicate objects ──────────────────────────────────

EnvironmentVariable = _OsPredicate("EnvironmentVariable")
EnvironmentVariable._register(2, _simple_to_trampoline(_environment_variable_2))

SetEnvironmentVariable = _OsPredicate("SetEnvironmentVariable")
SetEnvironmentVariable._register(2, _simple_to_trampoline(_set_environment_variable_2))

UnsetEnvironmentVariable = _OsPredicate("UnsetEnvironmentVariable")
UnsetEnvironmentVariable._register(1, _simple_to_trampoline(_unset_environment_variable_1))

WorkingDirectory = _OsPredicate("WorkingDirectory")
WorkingDirectory._register(1, _simple_to_trampoline(_working_directory_1))

ChangeDirectory = _OsPredicate("ChangeDirectory")
ChangeDirectory._register(1, _simple_to_trampoline(_change_directory_1))

Pid = _OsPredicate("Pid")
Pid._register(1, _simple_to_trampoline(_pid_1))

Argv = _OsPredicate("Argv")
Argv._register(1, _simple_to_trampoline(_argv_1))

Platform = _OsPredicate("Platform")
Platform._register(1, _simple_to_trampoline(_platform_1))

CPUCount = _OsPredicate("CPUCount")
CPUCount._register(1, _simple_to_trampoline(_cpu_count_1))
