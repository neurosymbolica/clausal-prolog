"""clausal.modules.py.process — Process and subprocess predicates for Clausal.

Provides relational predicates for running shell commands, launching
subprocesses, and sleeping.  Import via::

    -import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])

Or via module import::

    -import_module(py.process)
    # then use py.process.Shell("ls"), py.process.Sleep(1.0), etc.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_subprocess = _import_stdlib("subprocess")
_time = _import_stdlib("time")

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import DictTerm


# ── Predicates ──────────────────────────────────────────────────────────


def _shell_1(command, trail, k):
    """Shell/1: run shell command. Succeeds if exit code is 0."""
    command = deref(command)
    if is_var(command) or not isinstance(command, str):
        return
    try:
        result = _subprocess.run(command, shell=True)
    except OSError:
        return
    if result.returncode == 0:
        yield None


def _shell_2(command, exit_code, trail, k):
    """Shell/2: run shell command, unify ExitCode with the exit code."""
    command = deref(command)
    if is_var(command) or not isinstance(command, str):
        return
    try:
        result = _subprocess.run(command, shell=True)
    except OSError:
        return
    if unify(exit_code, result.returncode, trail):
        yield None


def _shell_output_2(command, output, trail, k):
    """ShellOutput/2: run shell command, capture stdout. Fails on non-zero exit."""
    command = deref(command)
    if is_var(command) or not isinstance(command, str):
        return
    try:
        result = _subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
    except OSError:
        return
    if result.returncode != 0:
        return
    if unify(output, result.stdout, trail):
        yield None


def _shell_output_3(command, output, error, trail, k):
    """ShellOutput/3: run shell command, capture stdout and stderr. Fails on non-zero exit."""
    command = deref(command)
    if is_var(command) or not isinstance(command, str):
        return
    try:
        result = _subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
    except OSError:
        return
    if result.returncode != 0:
        return
    if unify(output, result.stdout, trail) and unify(error, result.stderr, trail):
        yield None


def _process_create_3(program, args, result_var, trail, k):
    """ProcessCreate/3: run a program with argument list (no shell)."""
    program = deref(program)
    args = deref(args)
    if is_var(program) or not isinstance(program, str):
        return
    if is_var(args) or not isinstance(args, list):
        return
    cmd = [program] + [str(deref(a)) for a in args]
    try:
        result = _subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, FileNotFoundError):
        return
    result_dict = DictTerm({
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    })
    if unify(result_var, result_dict, trail):
        yield None


def _process_create_4(program, args, options, result_var, trail, k):
    """ProcessCreate/4: run a program with options DictTerm."""
    program = deref(program)
    args = deref(args)
    options = deref(options)
    if is_var(program) or not isinstance(program, str):
        return
    if is_var(args) or not isinstance(args, list):
        return
    if is_var(options):
        return

    cmd = [program] + [str(deref(a)) for a in args]

    # Extract options
    run_kwargs: dict = {"capture_output": True, "text": True}
    if isinstance(options, DictTerm):
        opts_data = options.data
    elif isinstance(options, dict):
        opts_data = options
    else:
        return

    if "cwd" in opts_data:
        cwd = deref(opts_data["cwd"])
        if isinstance(cwd, str):
            run_kwargs["cwd"] = cwd

    if "timeout" in opts_data:
        timeout = deref(opts_data["timeout"])
        if isinstance(timeout, (int, float)):
            run_kwargs["timeout"] = float(timeout)

    if "input" in opts_data:
        input_str = deref(opts_data["input"])
        if isinstance(input_str, str):
            run_kwargs["input"] = input_str
            run_kwargs.pop("capture_output", None)
            run_kwargs["stdout"] = _subprocess.PIPE
            run_kwargs["stderr"] = _subprocess.PIPE

    if "env" in opts_data:
        env_val = deref(opts_data["env"])
        if isinstance(env_val, DictTerm):
            import os as _os_mod
            merged = dict(_os_mod.environ)
            merged.update({str(k_): str(deref(v_)) for k_, v_ in env_val.data.items()})
            run_kwargs["env"] = merged
        elif isinstance(env_val, dict):
            import os as _os_mod
            merged = dict(_os_mod.environ)
            merged.update({str(k_): str(deref(v_)) for k_, v_ in env_val.items()})
            run_kwargs["env"] = merged

    try:
        result = _subprocess.run(cmd, **run_kwargs)
    except (OSError, FileNotFoundError, _subprocess.TimeoutExpired):
        return

    result_dict = DictTerm({
        "exit_code": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    })
    if unify(result_var, result_dict, trail):
        yield None


def _sleep_1(seconds, trail, k):
    """Sleep/1: pause execution for the given number of seconds."""
    seconds = deref(seconds)
    if is_var(seconds):
        return
    if not isinstance(seconds, (int, float)):
        return
    _time.sleep(float(seconds))
    yield None


# ── Build and export predicate objects ──────────────────────────────────

Shell = ModulePredicate("Shell")
Shell._register(1, simple_to_trampoline(_shell_1))
Shell._register(2, simple_to_trampoline(_shell_2))

ShellOutput = ModulePredicate("ShellOutput")
ShellOutput._register(2, simple_to_trampoline(_shell_output_2))
ShellOutput._register(3, simple_to_trampoline(_shell_output_3))

ProcessCreate = ModulePredicate("ProcessCreate")
ProcessCreate._register(3, simple_to_trampoline(_process_create_3))
ProcessCreate._register(4, simple_to_trampoline(_process_create_4))

Sleep = ModulePredicate("Sleep")
Sleep._register(1, simple_to_trampoline(_sleep_1))
