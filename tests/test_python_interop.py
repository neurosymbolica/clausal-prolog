"""Tests for V2-16 Python interop — ++() escape in .clausal files.

The ++() operator evaluates a Python expression at search time with
logic variables automatically dereferenced. It produces a PyThunk that
the compiler calls with deref'd values.
"""

from __future__ import annotations

import io
import sys
import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module


def _call_and_capture(functor, *args, module, output_index=-1):
    """Call a predicate, injecting a Var at output_index, return deref'd results.

    By default, the last argument is the output variable.
    """
    v = Var()
    full_args = list(args)
    if output_index == -1:
        full_args.append(v)
    else:
        full_args.insert(output_index, v)
    results = []
    for _ in call(functor, *full_args, module=module):
        results.append(deref(v))
    return results


class TestPyThunkValue:
    """++() used as a value (predicate argument)."""

    def test_len(self, tmp_path):
        """++len(L_) returns the length of a bound list."""
        # nv
        src = tmp_path / "interop_len.clausal"
        src.write_text("list_len(_l, _n) <- (_n is ++len(_l))\n")
        mod = _load_module("interop_len", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("list_len", [1, 2, 3], module=logic_mod)
        assert results == [3]

    def test_upper(self, tmp_path):
        """++S_.upper() calls a method on a dereferenced variable."""
        # nv
        src = tmp_path / "interop_upper.clausal"
        src.write_text("to_upper(_s, _r) <- (_r is ++_s.upper())\n")
        mod = _load_module("interop_upper", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("to_upper", "hello", module=logic_mod)
        assert results == ["HELLO"]

    def test_arithmetic(self, tmp_path):
        """++(X_ + 1) does Python arithmetic on a dereferenced variable."""
        # nv
        src = tmp_path / "interop_arith.clausal"
        src.write_text("inc(_x, _r) <- (_r is ++(_x + 1))\n")
        mod = _load_module("interop_arith", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("inc", 5, module=logic_mod)
        assert results == [6]

    def test_multi_var(self, tmp_path):
        """++() with multiple logic variables."""
        # nv
        src = tmp_path / "interop_multi.clausal"
        src.write_text("add_len(_a, _b, _r) <- (_r is ++(len(_a) + len(_b)))\n")
        mod = _load_module("interop_multi", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("add_len", [1, 2], [3, 4, 5], module=logic_mod)
        assert results == [5]

    def test_no_vars(self, tmp_path):
        """++() with no logic variables — pure Python expression."""
        # nv
        src = tmp_path / "interop_pure.clausal"
        src.write_text("get_pi(_r) <- (_r is ++(3.14159))\n")
        mod = _load_module("interop_pure", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("get_pi", module=logic_mod)
        assert len(results) == 1
        assert abs(results[0] - 3.14159) < 1e-10

    def test_subscript(self, tmp_path):
        """++L_[0] indexes a list."""
        # nv
        src = tmp_path / "interop_sub.clausal"
        src.write_text("first(_l, _r) <- (_r is ++_l[0])\n")
        mod = _load_module("interop_sub", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("first", [10, 20, 30], module=logic_mod)
        assert results == [10]

    def test_dict_access(self, tmp_path):
        """++D_['key'] accesses a dict."""
        # nv
        src = tmp_path / "interop_dict.clausal"
        src.write_text("get_key(_d, _k, _r) <- (_r is ++_d[_k])\n")
        mod = _load_module("interop_dict", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("get_key", {"a": 1, "b": 2}, "b", module=logic_mod)
        assert results == [2]

    def test_string_format(self, tmp_path):
        """++str.join() works."""
        # nv
        src = tmp_path / "interop_join.clausal"
        src.write_text('join_words(_w, _r) <- (_r is ++", ".join(_w))\n')
        mod = _load_module("interop_join", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("join_words", ["a", "b", "c"], module=logic_mod)
        assert results == ["a, b, c"]


class TestPyThunkGoal:
    """++() used as a goal (side effects, no return value)."""

    def test_print_side_effect(self, tmp_path):
        """++print(X_) executes Python print as a goal."""
        # nv
        src = tmp_path / "interop_goal.clausal"
        src.write_text("show(_x) <- ++print(_x)\n")
        mod = _load_module("interop_goal", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = list(call("show", "hello", module=logic_mod))
        finally:
            sys.stdout = old
        assert len(results) == 1
        assert buf.getvalue() == "hello\n"

    def test_goal_with_continuation(self, tmp_path):
        """++() goal followed by another goal in the body."""
        # nv
        src = tmp_path / "interop_cont.clausal"
        src.write_text(
            "process(_x, _r) <- (\n"
            "    ++print(_x),\n"
            "    _r is ++(_x * 2)\n"
            ")\n"
        )
        mod = _load_module("interop_cont", str(src))
        logic_mod = mod.__dict__["$module"]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            results = _call_and_capture("process", 5, module=logic_mod)
        finally:
            sys.stdout = old
        assert results == [10]
        assert buf.getvalue() == "5\n"


class TestPyThunkMultiSolution:
    """++() evaluated per solution during backtracking."""

    def test_thunk_per_choice_point(self, tmp_path):
        """PyThunk value is computed for each solution."""
        # nv
        src = tmp_path / "interop_multi_sol.clausal"
        src.write_text(
            "Item(1),\n"
            "Item(2),\n"
            "Item(3),\n"
            "Doubled(_r) <- (Item(_x), _r is ++(_x * 2))\n"
        )
        mod = _load_module("interop_multi_sol", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("Doubled", module=logic_mod)
        assert results == [2, 4, 6]

    def test_thunk_no_vars(self, tmp_path):
        """++() with no logic variables — pure Python constant."""
        # nv
        src = tmp_path / "interop_const.clausal"
        src.write_text("the_answer(_r) <- (_r is ++(21 * 2))\n")
        mod = _load_module("interop_const", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("the_answer", module=logic_mod)
        assert results == [42]

    def test_thunk_list_comprehension(self, tmp_path):
        """++[x*2 for x in X_] — list comprehension over a logic var."""
        # nv
        src = tmp_path / "interop_comp.clausal"
        src.write_text("double_all(_l, _r) <- (_r is ++[x*2 for x in _l])\n")
        mod = _load_module("interop_comp", str(src))
        logic_mod = mod.__dict__["$module"]
        results = _call_and_capture("double_all", [1, 2, 3], module=logic_mod)
        assert results == [[2, 4, 6]]
