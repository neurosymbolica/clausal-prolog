"""Tests for V2-15 I/O builtins — write, writeln, print_term, nl, tab,
write_to_string, term_to_string, and Var __format__/__str__ for f-string support.
"""

from __future__ import annotations

import io
import sys
import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars, chars_text
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import term_str
from tests._suffix import SEAM


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
        """Task 15 item 4 as amended (2026-09-07): ``write/1`` is the ISO
        writer, so a STRING prints as the list of characters it is.  The
        TEXT rendering moved to ``write_text/1`` (pinned below)."""
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, chars("hello"), t)
        assert out == "[h,e,l,l,o]"

    def test_write_int(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, 42, t)
        assert out == "42"

    def test_write_var_bound(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, chars("world"), t)
        out = _capture_stdout("write", 1, v, t)
        assert out == "[w,o,r,l,d]"

    def test_write_fstring(self):
        """An f-string is a STRING, so ``write/1`` spells it out; the family
        an f-string wants is ``write_text/1`` (pinned in ``TestWriteText``)."""
        # nv
        x = Var()
        t = Trail()
        unify(x, 42, t)
        out = _capture_stdout("write", 1, chars(f"hi {x}"), t)
        assert out == "[h,i, ,4,2]"

    def test_write_unbound_var(self):
        # nv
        v = Var()
        t = Trail()
        out = _capture_stdout("write", 1, v, t)
        assert out.startswith("_")

    def test_write_compound(self):
        # nv
        t = Trail()
        out = _capture_stdout("write", 1, ("f", 1, 2), t)
        assert "f" in out

    def test_write_tuple_data_cell(self):
        """P3-2 Task 7: ``io._format_term_iso`` grew a ``TUPLE_TAG`` branch
        alongside the str-functor cell branch -- a tuple-DATA cell renders
        as the plain tuple it displays, not the Python tuple repr with the
        ``TUPLE_TAG`` marker leaked into slot 0."""
        from clausal.logic.cells import TUPLE_TAG

        t = Trail()
        out = _capture_stdout("write", 1, (TUPLE_TAG, 1, 2), t)
        assert out == "(1,2)"

    def test_write_does_not_treat_a_bound_var_functor_tuple_as_a_cell(self):
        """Task 5/Task 7 review ruling: cell recognition reads slot 0 RAW.
        BEFORE this fix ``io._format_term_iso`` tested
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


# ── write_text/1, writeln_text/1, write_text_to_string/2 ─────────────────────
#
# Task 15 item 4 as amended (operator, 2026-09-07): the TEXT behaviour that
# ``write/1``/``writeln/1``/``write_to_string/2`` used to have moved to these
# three names unchanged, and the ISO behaviour took the old names.  Every
# assertion in this class is one the old names carried before the move.

class TestWriteText:

    def test_write_text_string(self):
        # nv
        t = Trail()
        assert _capture_stdout("write_text", 1, chars("hello"), t) == "hello"

    def test_write_text_char_list(self):
        # nv
        from clausal.logic.atoms import char_atom
        t = Trail()
        out = _capture_stdout(
            "write_text", 1, [char_atom("h"), char_atom("i")], t)
        assert out == "hi"

    def test_write_text_var_bound(self):
        # nv
        v = Var()
        t = Trail()
        unify(v, chars("world"), t)
        assert _capture_stdout("write_text", 1, v, t) == "world"

    def test_write_text_fstring(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 42, t)
        out = _capture_stdout("write_text", 1, chars(f"The answer is {x}"), t)
        assert out == "The answer is 42"

    def test_write_text_int_and_list_are_unchanged(self):
        # nv
        t = Trail()
        assert _capture_stdout("write_text", 1, 42, t) == "42"
        assert _capture_stdout("write_text", 1, [1, 2], t) == "[1, 2]"

    def test_write_text_empty_string_is_the_empty_list(self):
        # nv
        t = Trail()
        assert _capture_stdout("write_text", 1, chars(""), t) == "[]"

    def test_writeln_text_appends_a_newline(self):
        # nv
        t = Trail()
        assert _capture_stdout("writeln_text", 1, chars("hello"), t) == "hello\n"

    def test_write_text_to_string(self):
        # nv
        t = Trail()
        out = Var()
        dispatch = get_builtin_dispatch("write_text_to_string", 2, None)
        vals = solutions(
            StepGenerator(dispatch, None, None, None, chars("hello"), out, t),
            snapshot=lambda: deref(out))
        assert vals == [chars("hello")]


# ── writeln/1 ─────────────────────────────────────────────────────────────────

class TestWriteln:

    def test_writeln_string(self):
        # nv
        t = Trail()
        out = _capture_stdout("writeln", 1, chars("hello"), t)
        assert out == "[h,e,l,l,o]\n"

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
        assert out == "[1,2,3]\n"

    def test_writeln_fstring(self):
        """``writeln/1`` follows ``write/1``: an f-string is a STRING and
        spells itself out.  ``writeln_text/1`` is where f-strings go."""
        # nv
        x = Var()
        y = Var()
        t = Trail()
        unify(x, "Alice", t)
        unify(y, 25, t)
        out = _capture_stdout("writeln_text", 1, chars(f"{x} is {y} years old"), t)
        assert out == "Alice is 25 years old\n"
        out2 = _capture_stdout("writeln", 1, chars(f"{y}!"), t)
        assert out2 == "[2,5,!]\n"

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
        out = _capture_stdout("print_term", 1, chars("hello"), t)
        # term_str shows a STRING double-quoted (spec §6.7)
        assert out.strip() == '"hello"'

    def test_print_term_list(self):
        # nv
        t = Trail()
        out = _capture_stdout("print_term", 1, [1, 2, 3], t)
        assert out.strip() == "[1, 2, 3]"

    def test_print_term_compound(self):
        # nv
        t = Trail()
        c = ("foo", 1, "bar")
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

    def test_string_spells_itself_out(self):
        """Task 15 item 4 as amended: ``write_to_string/2`` follows
        ``write/1`` (ISO), so a string renders as its char list.
        ``write_text_to_string/2`` is the passthrough."""
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, chars("hello"), result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("[h,e,l,l,o]")]

    def test_int_to_string(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("42")]

    def test_var_bound(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        unify(v, chars("world"), t)
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("[w,o,r,l,d]")]

    def test_tuple_data_cell(self):
        """P3-2 Task 7: routed through the same ``TUPLE_TAG``-aware
        branch ``write/1`` uses (``io._format_term_iso``)."""
        from clausal.logic.cells import TUPLE_TAG

        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(
            StepGenerator(dispatch, None, None, None,
                          (TUPLE_TAG, mint("a"), mint("b")), result, t),
            snapshot=lambda: deref(result))
        assert vals == [chars("(a,b)")]

    def test_fstring(self):
        """An f-string is a STRING: ``write_to_string/2`` spells it out and
        ``write_text_to_string/2`` passes the text through."""
        # nv
        x = Var()
        result = Var()
        t = Trail()
        unify(x, 42, t)
        dispatch = get_builtin_dispatch("write_text_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, chars(f"answer={x}"), result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("answer=42")]
        result2 = Var()
        dispatch2 = get_builtin_dispatch("write_to_string", 2, None)
        vals2 = solutions(
            StepGenerator(dispatch2, None, None, None, chars(f"a{x}"), result2, t),
            snapshot=lambda: deref(result2))
        assert vals2 == [chars("[a,4,2]")]

    def test_unbound_var(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("write_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert len(vals) == 1
        assert chars_text(vals[0]).startswith("_")


# ── term_to_string/2 ────────────────────────────────────────────────────────────

class TestTermToString:

    def test_int(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, 42, result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("42")]

    def test_string_quoted(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, chars("hello"), result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars('"hello"')]

    def test_list(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, [1, 2], result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("[1, 2]")]

    def test_unbound_var(self):
        # nv
        v = Var()
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, v, result, t),
                         snapshot=lambda: deref(result))
        assert len(vals) == 1
        assert "_" in chars_text(vals[0])

    def test_compound(self):
        # nv
        result = Var()
        t = Trail()
        dispatch = get_builtin_dispatch("term_to_string", 2, None)
        vals = solutions(StepGenerator(dispatch, None, None, None, ("f", 1, 2), result, t),
                         snapshot=lambda: deref(result))
        assert vals == [chars("f(1, 2)")]


# ── Integration: .clausal file ────────────────────────────────────────────────

class TestClausalIntegration:
    """Test I/O builtins work from .clausal files via import hook."""

    def test_writeln_from_clausal(self, tmp_path):
        """writeln works as a builtin call in a .clausal file."""
        # nv
        src = tmp_path / f"io_test{SEAM}"
        src.write_text(
            "-double_quotes(atom)\ngreet(_name) <- writeln_text(f\"hello, {_name}!\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_test", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("greet", mint("World"), module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "hello, World!\n"

    def test_write_fstring_from_clausal(self, tmp_path):
        """F-string with multiple vars works in .clausal."""
        # nv
        src = tmp_path / f"io_fstr{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nshow_pair(_a, _b) <- writeln_text(f\"{_a} and {_b}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_fstr", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_pair", mint("cats"), mint("dogs"), module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "cats and dogs\n"

    def test_fstring_len_expression(self, tmp_path):
        """f"{len(_l)}" works — Python function on a logic variable."""
        # nv
        src = tmp_path / f"io_len{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nshow_len(_l) <- writeln_text(f\"length is {len(_l)}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_len", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_len", [1, 2, 3], module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "length is 3\n"

    def test_fstring_arithmetic_expression(self, tmp_path):
        """f"{_n + 1}" works — arithmetic on a logic variable."""
        # nv
        src = tmp_path / f"io_arith{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nshow_next(_n) <- writeln_text(f\"next is {_n + 1}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_arith", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_next", 5, module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "next is 6\n"

    def test_fstring_str_upper(self, tmp_path):
        """f"{_s.upper()}" works — method call on a logic variable."""
        # nv
        src = tmp_path / f"io_upper{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nshow_upper(_s) <- writeln_text(f\"{_s.upper()}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_upper", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_upper", mint("hello"), module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "HELLO\n"

    def test_writeln_with_backtracking(self, tmp_path):
        """writeln fires once per solution during backtracking."""
        # nv
        src = tmp_path / f"io_bt{SEAM}"
        src.write_text(
            "color('red'),\n"
            "color('green'),\n"
            "color('blue'),\n"
            "show_colors(_x) <- (color(_x), writeln(_x))\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_bt", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_colors", Var(), module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 3
        assert buf.getvalue() == "red\ngreen\nblue\n"

    def test_fstring_format_spec_in_clausal(self, tmp_path):
        """f"{_x:.2f}" with format spec works in .clausal files."""
        # nv
        src = tmp_path / f"io_spec{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nshow_float(_x) <- writeln_text(f\"{_x:.2f}\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_spec", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show_float", 3.14159, module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "3.14\n"

    def test_fstring_no_vars(self, tmp_path):
        """f-string with no logic variables produces a zero-arg lambda."""
        # nv
        src = tmp_path / f"io_novar{SEAM}"
        src.write_text(
            "-double_quotes(atom)\nhello() <- writeln_text(f\"hello world\")\n"
        )
        from clausal.logic.solve import call
        from clausal.import_hook import _load_module
        mod = _load_module("io_novar", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("hello", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "hello world\n"
