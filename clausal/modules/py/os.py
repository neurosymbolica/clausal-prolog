"""clausal.modules.py.os — OS interaction predicates for Clausal.

Provides relational predicates for environment variables, working directory,
process info, and system metadata.  Import via::

    -import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])

Or via module import::

    -import_module(py.os)
    # then use py.os.EnvironmentVariable("HOME", H_), py.os.Pid(P_), etc.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_os = _import_stdlib("os")
_sys = _import_stdlib("sys")

from clausal.logic.variables import Var, deref, is_var, unify


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

EnvironmentVariable = ModulePredicate("EnvironmentVariable")
EnvironmentVariable._register(2, simple_to_trampoline(_environment_variable_2))

SetEnvironmentVariable = ModulePredicate("SetEnvironmentVariable")
SetEnvironmentVariable._register(2, simple_to_trampoline(_set_environment_variable_2))

UnsetEnvironmentVariable = ModulePredicate("UnsetEnvironmentVariable")
UnsetEnvironmentVariable._register(1, simple_to_trampoline(_unset_environment_variable_1))

WorkingDirectory = ModulePredicate("WorkingDirectory")
WorkingDirectory._register(1, simple_to_trampoline(_working_directory_1))

ChangeDirectory = ModulePredicate("ChangeDirectory")
ChangeDirectory._register(1, simple_to_trampoline(_change_directory_1))

Pid = ModulePredicate("Pid")
Pid._register(1, simple_to_trampoline(_pid_1))

Argv = ModulePredicate("Argv")
Argv._register(1, simple_to_trampoline(_argv_1))

Platform = ModulePredicate("Platform")
Platform._register(1, simple_to_trampoline(_platform_1))

CPUCount = ModulePredicate("CPUCount")
CPUCount._register(1, simple_to_trampoline(_cpu_count_1))
