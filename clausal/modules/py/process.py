"""clausal.modules.py.process — Process and subprocess predicates for Clausal.

Provides relational predicates for running shell commands, launching
subprocesses, and sleeping.  Import via::

    -import_from(py.process, [shell, shell_output, process_create, sleep])

Or via module import::

    -import_module(py.process)
    # then use py.process.shell("ls"), py.process.sleep(1.0), etc.
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    NUMBER_TYPES,
    expect_type,
    has_option,
    option,
    raise_os_error,
    require_text,
    simple_to_trampoline,
    text_or_str,
    to_text,
)
_subprocess = _import_stdlib("subprocess")
_time = _import_stdlib("time")


from clausal.logic.atoms import mint
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import DictTerm


# The keys of the ``process_create`` result dict, minted once.
#
# Spec §6.8: a dict written in source has ATOM keys, and an atom key is
# distinct from the string of the same spelling, so a result dict built with
# plain ``str`` keys is unreadable by the syntax the docs show -- ``R.stdout``
# looks up ``("stdout",)`` and raises ``existence_error(dict_key, stdout)``,
# and ``get(R, stdout, V)`` fails silently.  The keys a wrapper emits for
# source to consume are therefore atoms, exactly as ``py.json``'s parsed
# object keys are (§9.2).  The VALUES stay text (§9.4).
_EXIT_CODE = mint("exit_code")
_STDOUT = mint("stdout")
_STDERR = mint("stderr")


# ── Spawn failures (RULED 2026-10-02) ─────────────────────────────────────
#
# A program that cannot be started RAISES; what a started program DOES is a
# value.  So a nonexistent program is ``existence_error(source_sink,
# Program)``, a program that may not be executed (no execute permission, a
# directory, not an executable format) ``permission_error(create, process,
# Program)`` -- Scryer's ``process_create/3`` term for a failed spawn -- and a
# ``cwd`` option naming a missing directory ``existence_error(source_sink,
# Cwd)``.  A nonzero exit status is NOT an error: ``shell/2`` and
# ``process_create/3,4`` answer it, and ``shell/1``, ``shell_output/2,3``
# (which answer no status) fail on it, as they always did.  A
# ``process_create/4`` timeout answers ``exit_code: timeout``, Scryer's
# ``process_wait/3`` status for a process that outlived its timeout.

_TIMEOUT = mint("timeout")


def _raise_spawn_error(exc, program_term, pred, *, cwd=None, cwd_term=None):
    import errno as _errno  # noqa: PLC0415
    if cwd is not None and getattr(exc, "filename", None) == cwd:
        raise_os_error(exc, cwd_term, pred, path=cwd)
    from clausal.modules.py import _PERMISSION_ERRNOS  # noqa: PLC0415
    import os as _os_mod  # noqa: PLC0415
    program = getattr(exc, "filename", None)
    if exc.errno in _PERMISSION_ERRNOS or exc.errno == _errno.ENOEXEC or (
            exc.errno == _errno.ENOTDIR and program is not None
            and _os_mod.path.lexists(program)):
        # Every "it is there but cannot be run" is the one Scryer term.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, permission_error,
        )
        raise LogicException(permission_error(
            "create", "process", program_term,
            f"{pred}: {exc.strerror or exc}")) from exc
    raise_os_error(exc, program_term, pred, action="create")


def _out_text(v):
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


# ── Predicates ──────────────────────────────────────────────────────────


def _shell_1(command, trail, k):
    """shell/1: run shell command. Succeeds if exit code is 0."""
    command_term = deref(command)
    command = require_text(command_term, "shell/1")
    try:
        result = _subprocess.run(command, shell=True)
    except OSError as exc:
        _raise_spawn_error(exc, command_term, "shell/1")
    if result.returncode == 0:
        yield None


def _shell_2(command, exit_code, trail, k):
    """shell/2: run shell command, unify ExitCode with the exit code."""
    command_term = deref(command)
    command = require_text(command_term, "shell/2")
    try:
        result = _subprocess.run(command, shell=True)
    except OSError as exc:
        _raise_spawn_error(exc, command_term, "shell/2")
    if unify(exit_code, result.returncode, trail):
        yield None


def _shell_output_2(command, output, trail, k):
    """shell_output/2: run shell command, capture stdout. Fails on non-zero exit."""
    command_term = deref(command)
    command = require_text(command_term, "shell_output/2")
    try:
        result = _subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
    except OSError as exc:
        _raise_spawn_error(exc, command_term, "shell_output/2")
    if result.returncode != 0:
        return
    if unify(output, text_result(result.stdout), trail):
        yield None


def _shell_output_3(command, output, error, trail, k):
    """shell_output/3: run shell command, capture stdout and stderr. Fails on non-zero exit."""
    command_term = deref(command)
    command = require_text(command_term, "shell_output/3")
    try:
        result = _subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
    except OSError as exc:
        _raise_spawn_error(exc, command_term, "shell_output/3")
    if result.returncode != 0:
        return
    if unify(output, text_result(result.stdout), trail) and unify(error, text_result(result.stderr), trail):
        yield None


def _process_create_3(program, args, result_var, trail, k):
    """process_create/3: run a program with argument list (no shell).

    Result is a ``DictTerm`` keyed by the ATOMS ``exit_code``, ``stdout``
    and ``stderr`` (spec §6.8), so ``R.stdout`` reads it.
    """
    program_term = deref(program)
    program = require_text(program_term, "process_create/3")
    args = deref(args)
    if not expect_type(args, list, "process_create/3", arg=2):
        return
    cmd = [program] + [text_or_str(deref(a)) for a in args]
    try:
        result = _subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        _raise_spawn_error(exc, program_term, "process_create/3")
    result_dict = DictTerm({
        _EXIT_CODE: result.returncode,
        _STDOUT: result.stdout,
        _STDERR: result.stderr,
    })
    if unify(result_var, text_result(result_dict), trail):
        yield None


def _process_create_4(program, args, options, result_var, trail, k):
    """process_create/4: run a program with options DictTerm.

    The options are read under either spelling of each option name (see
    ``modules.py.option``): a dict written in source has ATOM keys (§6.8).
    The Result dict is keyed by the ATOMS ``exit_code``/``stdout``/``stderr``
    for the same reason.
    """
    program_term = deref(program)
    program = require_text(program_term, "process_create/4")
    args = deref(args)
    options = deref(options)
    if not expect_type(args, list, "process_create/4", arg=2):
        return

    cmd = [program] + [text_or_str(deref(a)) for a in args]

    # Extract options
    run_kwargs: dict = {"capture_output": True, "text": True}
    if isinstance(options, DictTerm):
        opts_data = options.data
    elif isinstance(options, dict):
        opts_data = options
    else:
        expect_type(options, (DictTerm, dict), "process_create/4", arg=3)
        return

    cwd = cwd_term = None
    if has_option(opts_data, "cwd"):
        cwd_term = deref(option(opts_data, "cwd"))
        cwd = to_text(cwd_term)
        if cwd is not None:
            run_kwargs["cwd"] = cwd

    if has_option(opts_data, "timeout"):
        timeout = deref(option(opts_data, "timeout"))
        if isinstance(timeout, (int, float)):
            run_kwargs["timeout"] = float(timeout)

    if has_option(opts_data, "input"):
        input_str = to_text(deref(option(opts_data, "input")))
        if input_str is not None:
            run_kwargs["input"] = input_str
            run_kwargs.pop("capture_output", None)
            run_kwargs["stdout"] = _subprocess.PIPE
            run_kwargs["stderr"] = _subprocess.PIPE

    if has_option(opts_data, "env"):
        env_val = deref(option(opts_data, "env"))
        if isinstance(env_val, DictTerm):
            import os as _os_mod
            merged = dict(_os_mod.environ)
            merged.update({text_or_str(k_): text_or_str(deref(v_))
                           for k_, v_ in env_val.data.items()})
            run_kwargs["env"] = merged
        elif isinstance(env_val, dict):
            import os as _os_mod
            merged = dict(_os_mod.environ)
            merged.update({text_or_str(k_): text_or_str(deref(v_))
                           for k_, v_ in env_val.items()})
            run_kwargs["env"] = merged

    try:
        result = _subprocess.run(cmd, **run_kwargs)
    except _subprocess.TimeoutExpired as exc:
        # The process outlived its timeout and was killed: a VALUE, as
        # Scryer's process_wait/3 answers ``timeout`` -- it used to fail.
        exit_code, out, err = _TIMEOUT, exc.stdout, exc.stderr
    except OSError as exc:
        _raise_spawn_error(exc, program_term, "process_create/4",
                           cwd=cwd, cwd_term=cwd_term)
    else:
        exit_code, out, err = result.returncode, result.stdout, result.stderr

    # text_result per VALUE, not on the dict: the exit code ``timeout`` is
    # an ATOM, and an atom is a ``str`` that text_result would turn into text.
    result_dict = DictTerm({
        _EXIT_CODE: exit_code,
        _STDOUT: text_result(_out_text(out)),
        _STDERR: text_result(_out_text(err)),
    })
    if unify(result_var, result_dict, trail):
        yield None


def _sleep_1(seconds, trail, k):
    """sleep/1: pause execution for the given number of seconds."""
    seconds = deref(seconds)
    expect_type(seconds, NUMBER_TYPES, "sleep/1", arg=1)
    _time.sleep(float(seconds))
    yield None


# ── Build and export predicate objects ──────────────────────────────────

shell = ModulePredicate("shell")
shell._register(1, simple_to_trampoline(_shell_1))
shell._register(2, simple_to_trampoline(_shell_2))

shell_output = ModulePredicate("shell_output")
shell_output._register(2, simple_to_trampoline(_shell_output_2))
shell_output._register(3, simple_to_trampoline(_shell_output_3))

process_create = ModulePredicate("process_create")
process_create._register(3, simple_to_trampoline(_process_create_3))
process_create._register(4, simple_to_trampoline(_process_create_4))

sleep = ModulePredicate("sleep")
sleep._register(1, simple_to_trampoline(_sleep_1))
