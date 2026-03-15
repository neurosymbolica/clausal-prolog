"""Tests for V2-15 I/O builtins — Write, Writeln, PrintTerm, Nl, Tab,
WriteToString, TermToString, and Var __format__/__str__ for f-string support.
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
    return solutions(StepGenerator(dispatch, None, *pred_args, trail))


def _capture_stdout(name, arity, *args):
    """Run a builtin via trampoline and capture its stdout output."""
    dispatch = get_builtin_dispatch(name, arity, None)
    trail = args[-1]
    pred_args = args[:-1]
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, *pred_args, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


# ── Var __str__ and __format__ ────────────────────────────────────────────────

class TestVarFormat:
    """Test that Var.__str__ and __format__ auto-deref for f-string support."""

    def test_str_unbound(self):
        v = Var()
        s = str(v)
        assert s.startswith("_")
        assert s[1:].isdigit()

    def test_str_bound_int(self):
        v = Var()
        t = Trail()
        unify(v, 42, t)
        assert str(v) == "42"

    def test_str_bound_string(self):
        v = Var()
        t = Trail()
        unify(v, "hello", t)
        # str() on a string-bound var should give the string without quotes
        assert str(v) == "hello"

    def test_format_unbound(self):
        v = Var()
        s = f"{v}"
        assert s.startswith("_")

    def test_format_bound_int(self):
        v = Var()
        t = Trail()
        unify(v, 42, t)
        assert f"{v}" == "42"

    def test_format_bound_string(self):
        v = Var()
        t = Trail()
        unify(v, "world", t)
        assert f"{v}" == "world"

    def test_format_spec_float(self):
        v = Var()
        t = Trail()
        unify(v, 3.14159, t)
        assert f"{v:.2f}" == "3.14"

    def test_format_spec_int_padding(self):
        v = Var()
        t = Trail()
        unify(v, 7, t)
        assert f"{v:03d}" == "007"

    def test_fstring_interpolation(self):
        x = Var()
        y = Var()
        t = Trail()
        unify(x, "Alice", t)
        unify(y, 30, t)
        assert f"Name: {x}, Age: {y}" == "Name: Alice, Age: 30"

    def test_fstring_with_unbound(self):
        x = Var()
        t = Trail()
        unify(x, 42, t)
        y = Var()
        result = f"x={x}, y={y}"
        assert result.startswith("x=42, y=_")

    def test_str_bound_list(self):
        v = Var()
        t = Trail()
        unify(v, [1, 2, 3], t)
        assert str(v) == "[1, 2, 3]"

    def test_str_chain_deref(self):
        """Var bound to another var which is bound to a value."""
        v1 = Var()
        v2 = Var()
        t = Trail()
        unify(v1, v2, t)
        unify(v2, "chained", t)
        assert str(v1) == "chained"
        assert f"{v1}" == "chained"


# ── Write/1 ───────────────────────────────────────────────────────────────────

class TestWrite:

    def test_write_string(self):
        t = Trail()
        out = _capture_stdout("Write", 1, "hello", t)
        assert out == "hello"

    def test_write_int(self):
        t = Trail()
        out = _capture_stdout("Write", 1, 42, t)
        assert out == "42"

    def test_write_var_bound(self):
        v = Var()
        t = Trail()
        unify(v, "world", t)
        out = _capture_stdout("Write", 1, v, t)
        assert out == "world"

    def test_write_fstring(self):
        x = Var()
        t = Trail()
        unify(x, 42, t)
        out = _capture_stdout("Write", 1, f"The answer is {x}", t)
        assert out == "The answer is 42"

    def test_write_no_newline(self):
        t = Trail()
        out = _capture_stdout("Write", 1, "test", t)
        assert "\n" not in out

    def test_write_succeeds(self):
        t = Trail()
        results = _run_builtin("Write", 1, "x", t)
        assert len(results) >= 1


# ── Writeln/1 ─────────────────────────────────────────────────────────────────

class TestWriteln:

    def test_writeln_string(self):
        t = Trail()
        out = _capture_stdout("Writeln", 1, "hello", t)
        assert out == "hello\n"

    def test_writeln_int(self):
        t = Trail()
        out = _capture_stdout("Writeln", 1, 99, t)
        assert out == "99\n"

    def test_writeln_var_bound(self):
        v = Var()
        t = Trail()
        unify(v, [1, 2, 3], t)
        out = _capture_stdout("Writeln", 1, v, t)
        assert out == "[1, 2, 3]\n"

    def test_writeln_fstring(self):
        x = Var()
        y = Var()
        t = Trail()
        unify(x, "Alice", t)
        unify(y, 25, t)
        out = _capture_stdout("Writeln", 1, f"{x} is {y} years old", t)
        assert out == "Alice is 25 years old\n"

    def test_writeln_succeeds(self):
        t = Trail()
        results = _run_builtin("Writeln", 1, "x", t)
        assert len(results) >= 1


# ── PrintTerm/1 ───────────────────────────────────────────────────────────────

class TestPrintTerm:

    def test_print_term_int(self):
        t = Trail()
        out = _capture_stdout("PrintTerm", 1, 42, t)
        assert out.strip() == "42"

    def test_print_term_string(self):
        t = Trail()
        out = _capture_stdout("PrintTerm", 1, "hello", t)
        # term_str shows strings with quotes
        assert out.strip() == "'hello'"

    def test_print_term_list(self):
        t = Trail()
        out = _capture_stdout("PrintTerm", 1, [1, 2, 3], t)
        assert out.strip() == "[1, 2, 3]"

    def test_print_term_compound(self):
        t = Trail()
        c = Compound("foo", (1, "bar"))
        out = _capture_stdout("PrintTerm", 1, c, t)
        assert "foo" in out

    def test_print_term_var_bound(self):
        v = Var()
        t = Trail()
        unify(v, [1, 2], t)
        out = _capture_stdout("PrintTerm", 1, v, t)
        assert out.strip() == "[1, 2]"

    def test_print_term_succeeds(self):
        t = Trail()
        results = _run_builtin("PrintTerm", 1, 42, t)
        assert len(results) >= 1


# ── Nl/0 ──────────────────────────────────────────────────────────────────────

class TestNl:

    def test_nl_outputs_newline(self):
        t = Trail()
        out = _capture_stdout("Nl", 0, t)
        assert out == "\n"

    def test_nl_succeeds(self):
        t = Trail()
        results = _run_builtin("Nl", 0, t)
        assert len(results) >= 1


# ── Tab/1 ─────────────────────────────────────────────────────────────────────

class TestTab:

    def test_tab_spaces(self):
        t = Trail()
        out = _capture_stdout("Tab", 1, 4, t)
        assert out == "    "

    def test_tab_zero(self):
        t = Trail()
        out = _capture_stdout("Tab", 1, 0, t)
        assert out == ""

    def test_tab_var_fails(self):
        v = Var()
        t = Trail()
        out = _capture_stdout("Tab", 1, v, t)
        assert out == ""


# ── WriteToString/2 ───────────────────────────────────────────────────────────

class TestWriteToString:

    def test_string_passthrough(self):
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("WriteToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, "hello", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["hello"]

    def test_int_to_string(self):
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("WriteToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["42"]

    def test_var_bound(self):
        v = Var()
        result = Var()
        t = Trail()
        unify(v, "world", t)
        dispatch = get_builtin_dispatch("WriteToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["world"]

    def test_fstring(self):
        x = Var()
        result = Var()
        t = Trail()
        unify(x, 42, t)
        dispatch = get_builtin_dispatch("WriteToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, f"answer={x}", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["answer=42"]


# ── TermToString/2 ────────────────────────────────────────────────────────────

class TestTermToString:

    def test_int(self):
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("TermToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["42"]

    def test_string_quoted(self):
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("TermToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, "hello", result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["'hello'"]

    def test_list(self):
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("TermToString", 2, None)
        vals = solutions(StepGenerator(dispatch, None, [1, 2], result, t),
                         snapshot=lambda: deref(result))
        assert vals == ["[1, 2]"]


# ── Integration: .clausal file ────────────────────────────────────────────────

class TestClausalIntegration:
    """Test I/O builtins work from .clausal files via import hook."""

    def test_writeln_from_clausal(self, tmp_path):
        """Writeln works as a builtin call in a .clausal file."""
        src = tmp_path / "io_test.clausal"
        src.write_text(
            "Greet(Name_) <- Writeln(f\"Hello, {Name_}!\")\n"
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
        src = tmp_path / "io_fstr.clausal"
        src.write_text(
            "ShowPair(A_, B_) <- Writeln(f\"{A_} and {B_}\")\n"
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
        """f"{len(X_)}" works — Python function on a logic variable."""
        src = tmp_path / "io_len.clausal"
        src.write_text(
            "ShowLen(L_) <- Writeln(f\"length is {len(L_)}\")\n"
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
        """f"{X_ + 1}" works — arithmetic on a logic variable."""
        src = tmp_path / "io_arith.clausal"
        src.write_text(
            "ShowNext(N_) <- Writeln(f\"next is {N_ + 1}\")\n"
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
        """f"{X_.upper()}" works — method call on a logic variable."""
        src = tmp_path / "io_upper.clausal"
        src.write_text(
            "ShowUpper(S_) <- Writeln(f\"{S_.upper()}\")\n"
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
