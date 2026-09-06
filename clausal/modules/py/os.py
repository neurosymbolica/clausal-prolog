"""clausal.modules.py.os — OS interaction predicates for Clausal.

Provides relational predicates for environment variables, working directory,
process info, and system metadata.  Import via::

    -import_from(py.os, [environment_variable, working_directory, pid, platform])

Or via module import::

    -import_module(py.os)
    # then use py.os.environment_variable("HOME", H_), py.os.pid(P_), etc.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    require_text,
    simple_to_trampoline,
)
_os = _import_stdlib("os")
_sys = _import_stdlib("sys")

from clausal.logic.variables import Var, deref, is_var, unify


# ── Helper ──────────────────────────────────────────────────────────────


# ── Predicates ──────────────────────────────────────────────────────────


def _environment_variable_2(name, value, trail, k):
    """environment_variable/2: get/enumerate environment variables.

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
        name = require_text(name, "environment_variable/2", 1)
        if name is None:
            return
        env_value = _os.environ.get(name)
        if env_value is None:
            return
        if unify(value, env_value, trail):
            yield None


def _set_environment_variable_2(name, value, trail, k):
    """set_environment_variable/2: set an environment variable."""
    name, value = deref(name), deref(value)
    if is_var(name) or is_var(value):
        return
    name = require_text(name, "set_environment_variable/2", 1)
    value = require_text(value, "set_environment_variable/2", 2)
    if name is None or value is None:
        return
    _os.environ[name] = value
    yield None


def _unset_environment_variable_1(name, trail, k):
    """unset_environment_variable/1: remove an environment variable."""
    name = require_text(deref(name), "unset_environment_variable/1", 1)
    if name is None:
        return
    if name not in _os.environ:
        return
    del _os.environ[name]
    yield None


def _working_directory_1(path, trail, k):
    """working_directory/1: unify Path with the current working directory."""
    cwd = _os.getcwd()
    if unify(path, cwd, trail):
        yield None


def _change_directory_1(path, trail, k):
    """change_directory/1: change the current working directory."""
    path = require_text(deref(path), "change_directory/1", 1)
    if path is None:
        return
    try:
        _os.chdir(path)
    except OSError:
        return
    yield None


def _pid_1(p, trail, k):
    """pid/1: unify P with the current process ID."""
    if unify(p, _os.getpid(), trail):
        yield None


def _argv_1(args, trail, k):
    """argv/1: unify Args with sys.argv as a Python list."""
    if unify(args, list(_sys.argv), trail):
        yield None


def _platform_1(p, trail, k):
    """platform/1: unify P with sys.platform."""
    if unify(p, _sys.platform, trail):
        yield None


def _cpu_count_1(n, trail, k):
    """cpu_count/1: unify N with os.cpu_count()."""
    count = _os.cpu_count()
    if count is not None and unify(n, count, trail):
        yield None


# ── Build and export predicate objects ──────────────────────────────────

environment_variable = ModulePredicate("environment_variable")
environment_variable._register(2, simple_to_trampoline(_environment_variable_2))

set_environment_variable = ModulePredicate("set_environment_variable")
set_environment_variable._register(2, simple_to_trampoline(_set_environment_variable_2))

unset_environment_variable = ModulePredicate("unset_environment_variable")
unset_environment_variable._register(1, simple_to_trampoline(_unset_environment_variable_1))

working_directory = ModulePredicate("working_directory")
working_directory._register(1, simple_to_trampoline(_working_directory_1))

change_directory = ModulePredicate("change_directory")
change_directory._register(1, simple_to_trampoline(_change_directory_1))

pid = ModulePredicate("pid")
pid._register(1, simple_to_trampoline(_pid_1))

argv = ModulePredicate("argv")
argv._register(1, simple_to_trampoline(_argv_1))

platform = ModulePredicate("platform")
platform._register(1, simple_to_trampoline(_platform_1))

cpu_count = ModulePredicate("cpu_count")
cpu_count._register(1, simple_to_trampoline(_cpu_count_1))
