"""Tests for V2-15 I/O builtins — write, writeln, print_term, nl, tab,
write_to_string, term_to_string, and Var __format__/__str__ for f-string support.
"""

from __future__ import annotations

import io
import sys
import pytest

from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import Compound, term_str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_builtin(name, arity, *args):
    """Run a builtin via trampoline and return number of solutions."""
    dispatch = get_builtin_dispatch(name, arity, None)
    trail = args[-1]  # trail is always last
    pred_args = args[:-1]
    return solutions(StepGenerator(dispatch, None, None, None, *pred_args, trail))


def _capture_stdout(name, arity, *args):
    """Run a builtin via trampoline and capture its stdout output."""
    dispatch = get_builtin_dispatch(name, arity, None)
    trail = args[-1]
    pred_args = args[:-1]
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, None, None, *pred_args, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


# ── Var __str__ and __format__ ────────────────────────────────────────────────

class TestVarFormat:
    """Test that Var.__str__ and __format__ auto-deref for f-string support."""

    def test_str_unbound(self):
        # nv
        v = Var()
        s = str(v)
        assert s.startswith("_")
        assert s[1:].isdigit()

    def test_str_bound_int(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, 42, t)
        assert str(v) == "42"

    def test_str_bound_string(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, "hello", t)
        # str() on a string-bound var should give the string without quotes
        assert str(v) == "hello"

    def test_format_unbound(self):
        # nv
        v = Var()
        s = f"{v}"
        assert s.startswith("_")

    def test_format_bound_int(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, 42, t)
        assert f"{v}" == "42"

    def test_format_bound_string(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, "world", t)
        assert f"{v}" == "world"

    def test_format_spec_float(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, 3.14159, t)
        assert f"{v:.2f}" == "3.14"

    def test_format_spec_int_padding(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, 7, t)
        assert f"{v:03d}" == "007"

    def test_fstring_interpolation(self):
        # nv
        x = Var()
        y = Var()
        t = Trail()
        unify(x, "Alice", t)
        unify(y, 30, t)
        assert f"Name: {x}, Age: {y}" == "Name: Alice, Age: 30"

    def test_fstring_with_unbound(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 42, t)
        y = Var()
        result = f"x={x}, y={y}"
        assert result.startswith("x=42, y=_")

    def test_format_spec_unbound_ignores_spec(self):
        """Format spec on unbound Var is ignored — returns _N."""
        # nv
        v = Var()
        result = f"{v:05d}"
        assert result.startswith("_")

    def test_format_bound_none(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, None, t)
        assert f"{v}" == "None"

    def test_str_bound_list(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, [1, 2, 3], t)
        assert str(v) == "[1, 2, 3]"

    def test_str_chain_deref(self):
        """Var bound to another var which is bound to a value."""
        # nv
        v1 = Var()
        v2 = Var()
        t = Trail()
        unify(v1, v2, t)
        unify(v2, "chained", t)
        assert str(v1) == "chained"
        assert f"{v1}" == "chained"


# ── write/1 ───────────────────────────────────────────────────────────────────

class TestWrite:

    def test_write_string(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, "hello", t)
        assert out == "hello"

    def test_write_int(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, 42, t)
        assert out == "42"

    def test_write_var_bound(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, "world", t)
        out = _capture_stdout("write", 1, v, t)
        assert out == "world"

    def test_write_fstring(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 42, t)
        out = _capture_stdout("write", 1, f"The answer is {x}", t)
        assert out == "The answer is 42"

    def test_write_unbound_var(self):
        # nv
        v = Var()
        t = Trail()
        out = _capture_stdout("write", 1, v, t)
        assert out.startswith("_")

    def test_write_compound(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, Compound("f", (1, 2)), t)
        assert "f" in out

    def test_write_tuple_data_cell(self):
        """P3-2 Task 7: ``_format_term_for_io`` grew a ``TUPLE_TAG`` branch
        alongside the str-functor cell branch -- a tuple-DATA cell renders
        as the plain tuple it displays, not the Python tuple repr with the
        ``TUPLE_TAG`` marker leaked into slot 0."""
        from clausal.logic.cells import TUPLE_TAG

        t = Trail()
        out = _capture_stdout("write", 1, (TUPLE_TAG, 1, 2), t)
        assert out == "(1, 2)"

    def test_write_does_not_treat_a_bound_var_functor_tuple_as_a_cell(self):
        """Task 5/Task 7 review ruling: cell recognition reads slot 0 RAW.
        BEFORE this fix ``_format_term_for_io`` tested
        ``isinstance(deref(val[0]), str)``, so a tuple whose slot 0 was a
        Var *bound* to a str routed through ``term_str`` and printed as a
        compound.  AFTER: it keeps the ordinary ``str()`` (Python tuple
        repr) rendering, same as any other non-str, non-``TUPLE_TAG`` slot 0."""
        v = Var()
        t = Trail()
        unify(v, "pt", t)
        out = _capture_stdout("write", 1, (v, 1, 2), t)
        assert "pt(1, 2)" not in out

    def test_write_no_newline(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, "test", t)
        assert "\n" not in out

    def test_write_succeeds(self):
        # nv
        t = Trail()
        results = _run_builtin("write", 1, "x", t)
        assert len(results) >= 1


# ── writeln/1 ─────────────────────────────────────────────────────────────────

class TestWriteln:

    def test_writeln_string(self):
        # nv
        t = Trail()
        out = _capture_stdout("writeln", 1, "hello", t)
        assert out == "hello\n"

    def test_writeln_int(self):
        # nv
        t = Trail()
        out = _capture_stdout("writeln", 1, 99, t)
        assert out == "99\n"

    def test_writeln_var_bound(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, [1, 2, 3], t)
        out = _capture_stdout("writeln", 1, v, t)
        assert out == "[1, 2, 3]\n"

    def test_writeln_fstring(self):
        # nv
        x = Var()
        y = Var()
        t = Trail()
        unify(x, "Alice", t)
        unify(y, 25, t)
        out = _capture_stdout("writeln", 1, f"{x} is {y} years old", t)
        assert out == "Alice is 25 years old\n"

    def test_writeln_succeeds(self):
        # nv
        t = Trail()
        results = _run_builtin("writeln", 1, "x", t)
        assert len(results) >= 1


# ── print_term/1 ───────────────────────────────────────────────────────────────

class TestPrintTerm:

    def test_print_term_int(self):
        # nv
        t = Trail()
        out = _capture_stdout("print_term", 1, 42, t)
        assert out.strip() == "42"

    def test_print_term_string(self):
        # nv
        t = Trail()
        out = _capture_stdout("print_term", 1, "hello", t)
        # term_str shows strings with quotes
        assert out.strip() == "'hello'"

    def test_print_term_list(self):
        # nv
        t = Trail()
        out = _capture_stdout("print_term", 1, [1, 2, 3], t)
        assert out.strip() == "[1, 2, 3]"

    def test_print_term_compound(self):
        # nv
        t = Trail()
        c = Compound("foo", (1, "bar"))
        out = _capture_stdout("print_term", 1, c, t)
        assert "foo" in out

    def test_print_term_var_bound(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, [1, 2], t)
        out = _capture_stdout("print_term", 1, v, t)
        assert out.strip() == "[1, 2]"

    def test_print_term_succeeds(self):
        # nv
        t = Trail()
        results = _run_builtin("print_term", 1, 42, t)
        assert len(results) >= 1


# ── nl/0 ──────────────────────────────────────────────────────────────────────

class TestNl:

    def test_nl_outputs_newline(self):
        # nv
        t = Trail()
        out = _capture_stdout("nl", 0, t)
        assert out == "\n"

    def test_nl_succeeds(self):
        # nv
        t = Trail()
        results = _run_builtin("nl", 0, t)
        assert len(results) >= 1


# ── tab/1 ─────────────────────────────────────────────────────────────────────

class TestTab:

    def test_tab_spaces(self):
        # nv
        t = Trail()
        out = _capture_stdout("tab", 1, 4, t)
        assert out == "    "

    def test_tab_zero(self):
        # nv
        t = Trail()
        out = _capture_stdout("tab", 1, 0, t)
        assert out == ""

    def test_tab_var_fails(self):
        # nv
        v = Var()
        t = Trail()
        out = _capture_stdout("tab", 1, v, t)
        assert out == ""

    def test_tab_negative_no_output(self):
        """tab with negative number produces empty string (Python ' ' * -N == '')."""
        # nv
        t = Trail()
        out = _capture_stdout("tab", 1, -3, t)
        assert out == ""


# ── print_term edge cases ─────────────────────────────────────────────────────

class TestPrintTermEdgeCases:

    def test_print_term_unbound_var(self):
        # nv
        v = Var()
        t = Trail()
        out = _capture_stdout("print_term", 1, v, t)
        assert "_" in out


# ── write_to_string/2 ───────────────────────────────────────────────────────────

class TestWriteToString:

    def test_string_passthrough(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, "hello", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["hello"]

    def test_int_to_string(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["42"]

    def test_var_bound(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        unify(v, "world", t)
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["world"]

    def test_tuple_data_cell(self):
        """P3-2 Task 7: routed through the same ``TUPLE_TAG``-aware
        ``_format_term_for_io`` branch ``write/1`` uses."""
        from clausal.logic.cells import TUPLE_TAG

        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(
            StepGenerator(dispatch, None, None, None, (TUPLE_TAG, "a", "b"), result, t),
            snapshot=lambda: deref(result))
        assert vals == ["('a', 'b')"]

    def test_fstring(self):
        # nv
        x = Var()
        result = Var()
        t = Trail()
        unify(x, 42, t)
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, f"answer={x}", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["answer=42"]

    def test_unbound_var(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert len(vals) == 1
        assert vals[0].startswith("_")


# ── term_to_string/2 ────────────────────────────────────────────────────────────

class TestTermToString:

    def test_int(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["42"]

    def test_string_quoted(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, "hello", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["'hello'"]

    def test_list(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, [1, 2], result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["[1, 2]"]

    def test_unbound_var(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert len(vals) == 1
        assert "_" in vals[0]

    def test_compound(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, Compound("f", (1, 2)), result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["f(1, 2)"]


# ── Integration: .clausal file ────────────────────────────────────────────────

class TestClausalIntegration:
    """Test I/O builtins work from .clausal files via import hook."""

    def test_writeln_from_clausal(self, tmp_path):
        """writeln works as a builtin call in a .clausal file."""
        # nv
        src = tmp_path / "io_test.clausal"
        src.write_text(
            "Greet(_name) <- writeln(f\"Hello, {_name}!\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_test", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("Greet", "World", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "Hello, World!\n"

    def test_write_fstring_from_clausal(self, tmp_path):
        """F-string with multiple vars works in .clausal."""
        # nv
        src = tmp_path / "io_fstr.clausal"
        src.write_text(
            "ShowPair(_a, _b) <- writeln(f\"{_a} and {_b}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_fstr", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowPair", "cats", "dogs", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "cats and dogs\n"

    def test_fstring_len_expression(self, tmp_path):
        """f"{len(_l)}" works — Python function on a logic variable."""
        # nv
        src = tmp_path / "io_len.clausal"
        src.write_text(
            "ShowLen(_l) <- writeln(f\"length is {len(_l)}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_len", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowLen", [1, 2, 3], module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "length is 3\n"

    def test_fstring_arithmetic_expression(self, tmp_path):
        """f"{_n + 1}" works — arithmetic on a logic variable."""
        # nv
        src = tmp_path / "io_arith.clausal"
        src.write_text(
            "ShowNext(_n) <- writeln(f\"next is {_n + 1}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_arith", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowNext", 5, module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "next is 6\n"

    def test_fstring_str_upper(self, tmp_path):
        """f"{_s.upper()}" works — method call on a logic variable."""
        # nv
        src = tmp_path / "io_upper.clausal"
        src.write_text(
            "ShowUpper(_s) <- writeln(f\"{_s.upper()}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_upper", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowUpper", "hello", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "HELLO\n"

    def test_writeln_with_backtracking(self, tmp_path):
        """writeln fires once per solution during backtracking."""
        # nv
        src = tmp_path / "io_bt.clausal"
        src.write_text(
            "Color('red'),\n"
            "Color('green'),\n"
            "Color('blue'),\n"
            "ShowColors(_x) <- (Color(_x), writeln(_x))\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_bt", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowColors", Var(), module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 3
        assert buf.getvalue() == "red\ngreen\nblue\n"

    def test_fstring_format_spec_in_clausal(self, tmp_path):
        """f"{_x:.2f}" with format spec works in .clausal files."""
        # nv
        src = tmp_path / "io_spec.clausal"
        src.write_text(
            "ShowFloat(_x) <- writeln(f\"{_x:.2f}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_spec", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("ShowFloat", 3.14159, module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "3.14\n"

    def test_fstring_no_vars(self, tmp_path):
        """f-string with no logic variables produces a zero-arg lambda."""
        # nv
        src = tmp_path / "io_novar.clausal"
        src.write_text(
            "Hello() <- writeln(f\"hello world\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_novar", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("Hello", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "hello world\n"
