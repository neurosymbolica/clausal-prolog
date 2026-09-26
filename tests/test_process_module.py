"""Tests for clausal.modules.py.process — Process and subprocess predicates."""

from __future__ import annotations

import time

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars, chars_text
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.process import (
    shell, shell_output, process_create, sleep,
    _shell_1, _shell_2, _shell_output_2, _shell_output_3,
    _process_create_3, _process_create_4, _sleep_1,
)
from clausal.terms import DictTerm
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── shell/1 ────────────────────────────────────────────────────────────


class TestShell1:
    def test_true_succeeds(self):
        # nv
        sols, _ = simple_solutions(_shell_1, chars("true"))
        assert len(sols) == 1

    def test_false_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, chars("false"))
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, Var())
        assert len(sols) == 0

    def test_non_string_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, 42)
        assert len(sols) == 0

    def test_trampoline_multi_arity(self):
        # Arity 1 via multi-dispatch
        # nv
        sols, _ = trampoline_solutions(shell, chars("true"))
        assert len(sols) == 1


# ── shell/2 ────────────────────────────────────────────────────────────


class TestShell2:
    def test_true_exit_zero(self):
        # nv
        code = Var()
        sols, trail = simple_solutions(_shell_2, chars("true"), code)
        assert len(sols) == 1
        assert deref(code) == 0

    def test_false_exit_one(self):
        # nv
        code = Var()
        sols, trail = simple_solutions(_shell_2, chars("false"), code)
        assert len(sols) == 1
        assert deref(code) == 1

    def test_trampoline(self):
        # nv
        code = Var()
        sols, trail = trampoline_solutions(shell, chars("true"), code)
        assert len(sols) == 1
        assert deref(code) == 0


# ── shell_output/2 ─────────────────────────────────────────────────────


class TestShellOutput2:
    def test_captures_stdout(self):
        # nv
        output = Var()
        sols, trail = simple_solutions(_shell_output_2, chars("echo hello"), output)
        assert len(sols) == 1
        assert chars_text(deref(output)).strip() == "hello"

    def test_nonzero_exit_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_output_2, chars("false"), Var())
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_output_2, Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        output = Var()
        sols, trail = trampoline_solutions(shell_output, chars("echo world"), output)
        assert len(sols) == 1
        assert chars_text(deref(output)).strip() == "world"


# ── shell_output/3 ─────────────────────────────────────────────────────


class TestShellOutput3:
    def test_captures_stdout_and_stderr(self):
        # nv
        out, err = Var(), Var()
        sols, trail = simple_solutions(
            _shell_output_3, chars("echo out && echo err >&2"), out, err
        )
        assert len(sols) == 1
        assert chars_text(deref(out)).strip() == "out"
        assert chars_text(deref(err)).strip() == "err"

    def test_trampoline(self):
        # nv
        out, err = Var(), Var()
        sols, trail = trampoline_solutions(
            shell_output, chars("echo hello && echo warn >&2"), out, err
        )
        assert len(sols) == 1
        assert chars_text(deref(out)).strip() == "hello"
        assert chars_text(deref(err)).strip() == "warn"


# ── process_create/3 ──────────────────────────────────────────────────


class TestProcessCreate3:
    def test_runs_program(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(
            _process_create_3, chars("echo"), [chars("hello")], result
        )
        assert len(sols) == 1
        r = deref(result)
        assert isinstance(r, DictTerm)
        # Task 12c: a result dict built for SOURCE has atom keys (§6.8) —
        # ``R.stdout`` looks up ``("stdout",)``.
        assert r.data[mint("exit_code")] == 0
        assert "hello" in chars_text(r.data[mint("stdout")])

    def test_nonexistent_program_fails(self):
        # nv
        sols, _ = simple_solutions(
            _process_create_3, chars("/nonexistent_program_xyz"), [], Var()
        )
        assert len(sols) == 0

    def test_unbound_program_fails(self):
        # nv
        sols, _ = simple_solutions(_process_create_3, Var(), [], Var())
        assert len(sols) == 0

    def test_unbound_args_fails(self):
        # nv
        sols, _ = simple_solutions(_process_create_3, chars("echo"), Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        result = Var()
        sols, trail = trampoline_solutions(
            process_create, chars("echo"), [chars("test")], result
        )
        assert len(sols) == 1
        r = deref(result)
        assert r.data[mint("exit_code")] == 0


# ── process_create/4 ──────────────────────────────────────────────────


class TestProcessCreate4:
    def test_with_cwd(self, tmp_path):
        # nv
        result = Var()
        opts = DictTerm({"cwd": chars(str(tmp_path))})
        sols, trail = simple_solutions(
            _process_create_4, chars("pwd"), [], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert str(tmp_path) in chars_text(r.data[mint("stdout")])

    def test_with_timeout(self):
        # nv
        result = Var()
        opts = DictTerm({"timeout": 0.01})
        sols, _ = simple_solutions(
            _process_create_4, chars("sleep"), [chars("10")], opts, result
        )
        # Should fail due to timeout
        assert len(sols) == 0

    def test_with_input(self):
        # nv
        result = Var()
        opts = DictTerm({"input": chars("hello from stdin")})
        sols, trail = simple_solutions(
            _process_create_4, chars("cat"), [], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert r.data[mint("stdout")] == chars("hello from stdin")

    def test_trampoline(self):
        # nv
        result = Var()
        opts = DictTerm({})
        sols, trail = trampoline_solutions(
            process_create, chars("echo"), [chars("trampoline")], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert "trampoline" in chars_text(r.data[mint("stdout")])


# ── sleep/1 ──────────────────────────────────────────────────────────


class TestSleep:
    def test_sleeps(self):
        # nv
        start = time.monotonic()
        sols, _ = simple_solutions(_sleep_1, 0.05)
        elapsed = time.monotonic() - start
        assert len(sols) == 1
        assert elapsed >= 0.04  # allow small tolerance

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_sleep_1, Var())
        assert len(sols) == 0

    def test_non_numeric_fails(self):
        # nv
        sols, _ = simple_solutions(_sleep_1, "not a number")
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        sols, _ = trampoline_solutions(sleep, 0.01)
        assert len(sols) == 1


# ── Task 12b: atoms in the text and option positions (spec §9.4) ─────────


class TestAtomArguments:
    """A wrapper that takes text accepts a string OR an ATOM (spec §9.4).

    ``py.process`` was migrated onto ``to_text`` for env names/values only;
    the command, the program, its argument list and the ``cwd``/``input``
    options still gated on ``isinstance(x, str)``, and the options dict was
    read under ``str`` keys.  Source writes atoms in every one of those
    positions (§6.8 for the dict keys), so they silently failed — or, for
    the argument list, went to the shell as a Python tuple repr.
    """

    def test_shell_accepts_an_atom_command(self):
        # nv
        assert len(simple_solutions(_shell_1, mint("true"))[0]) == 1
        assert len(simple_solutions(_shell_1, mint("false"))[0]) == 0

    def test_shell_output_accepts_an_atom_command(self):
        # nv
        out = Var()
        sols, _ = simple_solutions(_shell_output_2, mint("echo t12b"), out)
        assert len(sols) == 1
        assert chars_text(deref(out)).strip() == "t12b"

    def test_process_create_accepts_atom_program_and_args(self):
        # nv
        result = Var()
        sols, _ = simple_solutions(
            _process_create_3, mint("echo"), [mint("t12b"), mint("args")],
            result)
        assert len(sols) == 1
        # ``str(("t12b",))`` would have echoed the tuple repr.
        # Task 12c closed the residual this line used to pin: the result dict
        # is emitted with ATOM keys, so ``R.stdout`` from source (which looks
        # up ``("stdout",)``, §6.8) now finds it.
        assert chars_text(deref(result).data[mint("stdout")]).strip() == "t12b args"

    def test_process_create_reads_an_atom_keyed_options_dict(self, tmp_path):
        # nv
        result = Var()
        opts = DictTerm({mint("cwd"): mint(str(tmp_path))})
        sols, _ = simple_solutions(
            _process_create_4, mint("pwd"), [], opts, result)
        assert len(sols) == 1
        assert str(tmp_path) in chars_text(deref(result).data[mint("stdout")])

    def test_process_create_accepts_an_atom_input(self):
        # nv
        result = Var()
        opts = DictTerm({mint("input"): mint("t12b stdin")})
        sols, _ = simple_solutions(
            _process_create_4, mint("cat"), [], opts, result)
        assert len(sols) == 1
        assert deref(result).data[mint("stdout")] == chars("t12b stdin")


# ── Task 12c: the result dict is keyed by ATOMS (spec §6.8) ─────────────


class TestResultDictKeysAreAtoms:
    """``process_create/3,4`` answers a dict for SOURCE to read.

    Spec §6.8 keeps an atom key distinct from the string of the same
    spelling, so a ``str``-keyed result was unreadable by the syntax the
    docs show: ``R.stdout`` raised ``existence_error(dict_key, stdout)``
    and ``get(R, stdout, V)`` failed silently.
    """

    def test_process_create_3_keys(self):
        # nv
        result = Var()
        sols, _ = simple_solutions(_process_create_3, chars("echo"), [chars("k")], result)
        assert len(sols) == 1
        # The whole key set, not just the one the reads above touch.
        assert set(deref(result).data) == {
            mint("exit_code"), mint("stdout"), mint("stderr")}

    def test_process_create_4_keys(self):
        # nv
        result = Var()
        sols, _ = simple_solutions(
            _process_create_4, chars("echo"), [chars("k")], DictTerm({}), result)
        assert len(sols) == 1
        assert set(deref(result).data) == {
            mint("exit_code"), mint("stdout"), mint("stderr")}


# ── 2026-09-26: an option key is matched by TEXT, whichever way it was quoted ─
#
# The -double_quotes default is chars, so ``{"input": ...}`` in a module that
# declares no mode has a chars-carrier key.  Before this, option()/has_option()
# tried only the atom and the plain str, the option was dropped silently, and
# process_create ran with no stdin (measured: stdout came back empty).

class TestOptionKeySpellings:

    def test_option_and_has_option_read_the_chars_carrier_key(self):
        from clausal.modules.py import has_option, option
        opts = DictTerm({chars("cwd"): 1, mint("timeout"): 2, "input": 3})
        assert option(opts, "cwd") == 1
        assert option(opts, "timeout") == 2
        assert option(opts, "input") == 3
        assert has_option(opts, "cwd") and has_option(opts, "timeout") \
            and has_option(opts, "input")
        assert not has_option(opts, "env")
        assert option(opts, "env", "dflt") == chars("dflt")

    def test_process_create_reads_a_string_keyed_options_dict(self):
        # nv
        result = Var()
        opts = DictTerm({chars("input"): chars("t12b stdin")})
        sols, _ = simple_solutions(
            _process_create_4, mint("cat"), [], opts, result)
        assert len(sols) == 1
        assert deref(result).data[mint("stdout")] == chars("t12b stdin")

    def test_a_default_mode_module_writing_string_keys_is_heard(self, tmp_path):
        """End to end, the shape docs/process.md shows: no -double_quotes
        directive, ``{"input": ...}`` written in source."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        p = tmp_path / "opt_keys.clausal"
        p.write_text(
            "-import_from(py.process, [process_create])\n"
            'by_string(R) <- process_create("cat", [], {"input": "hello"}, R)\n'
            "by_quoted(R) <- process_create('cat', [], {'input': 'hello'}, R)\n"
        )
        m = _load_module("_opt_keys_chars", str(p)).__dict__["$module"]
        for pred in ("by_string", "by_quoted"):
            R = Var()
            rows = [deref(R) for _ in call(pred, R, module=m)]
            assert len(rows) == 1, pred
            assert rows[0].data[mint("stdout")] == chars("hello"), pred
