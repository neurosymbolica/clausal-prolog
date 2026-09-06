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
    ModulePredicate,
    _import_stdlib,
    expect_type,
    has_option,
    option,
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


def _cmd_text(val, pred, arg=1):
    """The ``str`` a command, program or argument denotes, or ``None``.

    Spec §9.4: a wrapper that takes text accepts a string or an ATOM, and
    both convert to the same ``str`` -- so ``shell('true')`` written in a
    ``.clausal`` file works exactly as ``shell("true")`` does under
    ``-double_quotes(chars)``.  THE FLIP (2026-09-06-atoms-as-cells-strings)
    made the bare ``isinstance(command, str)`` guards below reject every
    source-written command, silently, and made ``str(deref(a))`` on an
    argument hand the SHELL a Python tuple repr.  Routed through ``to_text``.

    A bound value that is not text keeps this module's existing behaviour --
    a recorded type-mismatch note and a clean failure, not a raise.
    """
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=arg)  # records the note; always False here
    return None


# ── Predicates ──────────────────────────────────────────────────────────


def _shell_1(command, trail, k):
    """shell/1: run shell command. Succeeds if exit code is 0."""
    command = _cmd_text(deref(command), "shell/1")
    if command is None:
        return
    try:
        result = _subprocess.run(command, shell=True)
    except OSError:
        return
    if result.returncode == 0:
        yield None


def _shell_2(command, exit_code, trail, k):
    """shell/2: run shell command, unify ExitCode with the exit code."""
    command = _cmd_text(deref(command), "shell/2")
    if command is None:
        return
    try:
        result = _subprocess.run(command, shell=True)
    except OSError:
        return
    if unify(exit_code, result.returncode, trail):
        yield None


def _shell_output_2(command, output, trail, k):
    """shell_output/2: run shell command, capture stdout. Fails on non-zero exit."""
    command = _cmd_text(deref(command), "shell_output/2")
    if command is None:
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
    """shell_output/3: run shell command, capture stdout and stderr. Fails on non-zero exit."""
    command = _cmd_text(deref(command), "shell_output/3")
    if command is None:
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
    """process_create/3: run a program with argument list (no shell).

    Result is a ``DictTerm`` keyed by the ATOMS ``exit_code``, ``stdout``
    and ``stderr`` (spec §6.8), so ``R.stdout`` reads it.
    """
    program = _cmd_text(deref(program), "process_create/3")
    args = deref(args)
    if program is None:
        return
    if not expect_type(args, list, "process_create/3", arg=2):
        return
    cmd = [program] + [text_or_str(deref(a)) for a in args]
    try:
        result = _subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, FileNotFoundError):
        return
    result_dict = DictTerm({
        _EXIT_CODE: result.returncode,
        _STDOUT: result.stdout,
        _STDERR: result.stderr,
    })
    if unify(result_var, result_dict, trail):
        yield None


def _process_create_4(program, args, options, result_var, trail, k):
    """process_create/4: run a program with options DictTerm.

    The options are read under either spelling of each option name (see
    ``modules.py.option``): a dict written in source has ATOM keys (§6.8).
    The Result dict is keyed by the ATOMS ``exit_code``/``stdout``/``stderr``
    for the same reason.
    """
    program = _cmd_text(deref(program), "process_create/4")
    args = deref(args)
    options = deref(options)
    if program is None:
        return
    if not expect_type(args, list, "process_create/4", arg=2):
        return
    if is_var(options):
        return

    cmd = [program] + [text_or_str(deref(a)) for a in args]

    # Extract options
    run_kwargs: dict = {"capture_output": True, "text": True}
    if isinstance(options, DictTerm):
        opts_data = options.data
    elif isinstance(options, dict):
        opts_data = options
    else:
        expect_type(options, (DictTerm, dict), "process_create/4",
                    expected="dict", arg=3)
        return

    if has_option(opts_data, "cwd"):
        cwd = to_text(deref(option(opts_data, "cwd")))
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
    except (OSError, FileNotFoundError, _subprocess.TimeoutExpired):
        return

    result_dict = DictTerm({
        _EXIT_CODE: result.returncode,
        _STDOUT: result.stdout or "",
        _STDERR: result.stderr or "",
    })
    if unify(result_var, result_dict, trail):
        yield None


def _sleep_1(seconds, trail, k):
    """sleep/1: pause execution for the given number of seconds."""
    seconds = deref(seconds)
    if is_var(seconds):
        return
    if not expect_type(seconds, (int, float), "sleep/1",
                       expected="int or float", arg=1):
        return
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
