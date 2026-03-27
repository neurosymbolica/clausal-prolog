"""Tests for Extended DCGs (EDCGs).

EDCGs extend DCGs with multiple named accumulators and passed arguments,
declared via -edcg_acc, -edcg_pass, and -edcg_pred directives.
"""

from __future__ import annotations

import pytest

from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load(name, src_text, tmp_path):
    """write a .clausal file and load it as a module."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    """Return True if the predicate succeeds at least once."""
    for _ in call(functor, *args, module=module):
        return True
    return False


def _first(functor, *args, module):
    """Return the first set of bindings as a dict of deref'd Vars."""
    for _ in call(functor, *args, module=module):
        return True
    return False


# ── Phase 1: Directive Parsing ───────────────────────────────────────────────


class TestDirectiveParsing:
    """Test that EDCG directives are parsed without errors."""

    def test_edcg_acc_parses(self, tmp_path):
        """Basic -edcg_acc directive parses successfully."""
        src = (
            '-module(t1, [])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
        )
        mod = _load("t1", src, tmp_path)
        assert mod is not None

    def test_edcg_pass_parses(self, tmp_path):
        """Basic -edcg_pass directive parses successfully."""
        src = (
            '-module(t2, [])\n'
            '-edcg_pass(config)\n'
        )
        mod = _load("t2", src, tmp_path)
        assert mod is not None

    def test_edcg_pred_parses(self, tmp_path):
        """Basic -edcg_pred directive parses successfully."""
        src = (
            '-module(t3, [])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(inc, 0, [counter])\n'
        )
        mod = _load("t3", src, tmp_path)
        assert mod is not None

    def test_edcg_pred_with_dcg(self, tmp_path):
        """EDCG pred can include the built-in 'dcg' accumulator."""
        src = (
            '-module(t4, [])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(counted_token, 1, [counter, dcg])\n'
        )
        mod = _load("t4", src, tmp_path)
        assert mod is not None

    def test_edcg_pred_with_pass(self, tmp_path):
        """EDCG pred can include a passed argument."""
        src = (
            '-module(t5, [])\n'
            '-edcg_pass(config)\n'
            '-edcg_pred(use_config, 0, [config])\n'
        )
        mod = _load("t5", src, tmp_path)
        assert mod is not None

    def test_multiple_accumulators(self, tmp_path):
        """Multiple accumulators can be declared."""
        src = (
            '-module(t6, [])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_acc(items, _item, _in, _out, {_out is [_item, *_in]})\n'
            '-edcg_pred(process, 1, [counter, items])\n'
        )
        mod = _load("t6", src, tmp_path)
        assert mod is not None


class TestDirectiveErrors:
    """Test that malformed EDCG directives raise SyntaxError."""

    def test_edcg_acc_wrong_arg_count(self, tmp_path):
        src = '-module(e1, [])\n-edcg_acc(counter, _x, _in)\n'
        with pytest.raises(SyntaxError, match="5 arguments"):
            _load("e1", src, tmp_path)

    def test_edcg_pred_undeclared_acc(self, tmp_path):
        src = '-module(e2, [])\n-edcg_pred(foo, 0, [unknown])\n'
        with pytest.raises(SyntaxError, match="not a declared"):
            _load("e2", src, tmp_path)

    def test_edcg_pred_wrong_arity_type(self, tmp_path):
        src = (
            '-module(e3, [])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(foo, "one", [counter])\n'
        )
        with pytest.raises(SyntaxError, match="integer"):
            _load("e3", src, tmp_path)


# ── Phase 2: Single Accumulator ─────────────────────────────────────────────


class TestSingleAccumulator:
    """Test EDCG rules with a single named accumulator."""

    def test_simple_counter(self, tmp_path):
        """Increment a counter accumulator."""
        src = (
            '-module(sc1, [count3(_counter0, _counter)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(inc, 0, [counter])\n'
            '-edcg_pred(count3, 0, [counter])\n'
            'inc >> ([1] // counter)\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("sc1", src, tmp_path)
        n = Var()
        for _ in call("count3", 0, n, module=mod):
            assert deref(n) == 3
            break

    def test_counter_start_nonzero(self, tmp_path):
        """Counter starts at a nonzero value."""
        src = (
            '-module(sc2, [count3(_counter0, _counter)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(inc, 0, [counter])\n'
            '-edcg_pred(count3, 0, [counter])\n'
            'inc >> ([1] // counter)\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("sc2", src, tmp_path)
        n = Var()
        for _ in call("count3", 10, n, module=mod):
            assert deref(n) == 13
            break

    def test_list_accumulator(self, tmp_path):
        """Accumulate items into a list."""
        src = (
            '-module(la1, [collect_all(_xs, _items0, _items)])\n'
            '-edcg_acc(items, _item, _in, _out, {_out is [_item, *_in]})\n'
            '-edcg_pred(collect, 1, [items])\n'
            '-edcg_pred(collect_all, 1, [items])\n'
            'collect(_x) >> ([_x] // items)\n'
            'collect_all([]) >> ([])\n'
            'collect_all([_x, *_xs]) >> (collect(_x), collect_all(_xs))\n'
        )
        mod = _load("la1", src, tmp_path)
        result = Var()
        for _ in call("collect_all", [1, 2, 3], [], result, module=mod):
            assert deref(result) == [3, 2, 1]
            break

    def test_accumulator_read(self, tmp_path):
        """Read current accumulator value with acc / Var."""
        src = (
            '-module(ar1, [get_and_inc(_v, _counter0, _counter)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(get_and_inc, 1, [counter])\n'
            'get_and_inc(_v) >> (counter / _v, [1] // counter)\n'
        )
        mod = _load("ar1", src, tmp_path)
        v = Var()
        n = Var()
        for _ in call("get_and_inc", v, 5, n, module=mod):
            assert deref(v) == 5   # read before increment
            assert deref(n) == 6   # after increment
            break

    def test_custom_joiner_product(self, tmp_path):
        """Accumulator with multiplication joiner."""
        src = (
            '-module(cp1, [mul_all(_xs, _prod0, _prod)])\n'
            '-edcg_acc(product, _x, _in, _out, {_out := _in * _x})\n'
            '-edcg_pred(mul, 1, [product])\n'
            '-edcg_pred(mul_all, 1, [product])\n'
            'mul(_x) >> ([_x] // product)\n'
            'mul_all([]) >> ([])\n'
            'mul_all([_x, *_xs]) >> (mul(_x), mul_all(_xs))\n'
        )
        mod = _load("cp1", src, tmp_path)
        result = Var()
        for _ in call("mul_all", [2, 3, 4], 1, result, module=mod):
            assert deref(result) == 24
            break


# ── Phase 3: Multiple Accumulators ──────────────────────────────────────────


class TestMultipleAccumulators:
    """Test EDCG rules threading multiple accumulators simultaneously."""

    def test_counter_and_list(self, tmp_path):
        """Count and collect items simultaneously."""
        src = (
            '-module(ma1, [process_all(_xs, _cnt0, _cnt, _items0, _items)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_acc(items, _item, _in, _out, {_out is [_item, *_in]})\n'
            '-edcg_pred(process, 1, [counter, items])\n'
            '-edcg_pred(process_all, 1, [counter, items])\n'
            'process(_x) >> ([1] // counter, [_x] // items)\n'
            'process_all([]) >> ([])\n'
            'process_all([_x, *_xs]) >> (process(_x), process_all(_xs))\n'
        )
        mod = _load("ma1", src, tmp_path)
        cnt = Var()
        items = Var()
        for _ in call("process_all", ["a", "b", "c"], 0, cnt, [], items, module=mod):
            assert deref(cnt) == 3
            assert deref(items) == ["c", "b", "a"]
            break

    def test_partial_overlap(self, tmp_path):
        """Caller uses [counter, items], callee uses [counter] only."""
        src = (
            '-module(po1, [do_both(_x, _cnt0, _cnt, _items0, _items)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_acc(items, _item, _in, _out, {_out is [_item, *_in]})\n'
            '-edcg_pred(inc_only, 0, [counter])\n'
            '-edcg_pred(do_both, 1, [counter, items])\n'
            'inc_only >> ([1] // counter)\n'
            'do_both(_x) >> (inc_only, [_x] // items)\n'
        )
        mod = _load("po1", src, tmp_path)
        cnt = Var()
        items = Var()
        for _ in call("do_both", "x", 0, cnt, [], items, module=mod):
            assert deref(cnt) == 1
            assert deref(items) == ["x"]
            break


# ── Phase 4: Passed Arguments ───────────────────────────────────────────────


class TestPassedArguments:
    """Test read-only passed arguments threading."""

    def test_basic_pass(self, tmp_path):
        """Pass a config value that is read but not modified."""
        src = (
            '-module(pa1, [check_config(_result, _config)])\n'
            '-edcg_pass(config)\n'
            '-edcg_pred(get_config, 1, [config])\n'
            '-edcg_pred(check_config, 1, [config])\n'
            'get_config(_v) >> (config / _v)\n'
            'check_config(_r) >> (get_config(_r))\n'
        )
        mod = _load("pa1", src, tmp_path)
        result = Var()
        for _ in call("check_config", result, "verbose", module=mod):
            assert deref(result) == "verbose"
            break

    def test_pass_with_accumulator(self, tmp_path):
        """Pass + accumulator together."""
        src = (
            '-module(pac1, [scaled_inc(_cnt0, _cnt, _scale)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pass(scale)\n'
            '-edcg_pred(scaled_inc, 0, [counter, scale])\n'
            'scaled_inc >> (scale / _s, [_s] // counter)\n'
        )
        mod = _load("pac1", src, tmp_path)
        result = Var()
        for _ in call("scaled_inc", 0, result, 10, module=mod):
            assert deref(result) == 10
            break


# ── Phase 5: Mixed EDCG + DCG ───────────────────────────────────────────────


class TestMixedEdcgDcg:
    """Test EDCG rules that also parse tokens (dcg accumulator)."""

    def test_counted_parser(self, tmp_path):
        """Count tokens while parsing them."""
        src = (
            '-module(cp1, [parse(_cnt0, _cnt, _tokens, _rest)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(token, 1, [counter, dcg])\n'
            '-edcg_pred(parse, 0, [counter, dcg])\n'
            'token(_t) >> ([_t], [1] // counter)\n'
            'parse >> (token(_), parse)\n'
            'parse >> ([])\n'
        )
        mod = _load("cp1", src, tmp_path)
        rest = Var()
        cnt = Var()
        # Args in edcg_pred order: counter_in, counter_out, dcg_in, dcg_out
        for _ in call("parse", 0, cnt, ["token", "token", "token"], rest, module=mod):
            assert deref(cnt) == 3
            assert deref(rest) == []
            break


# ── Phase 6: Control Flow ───────────────────────────────────────────────────


class TestEdcgControlFlow:
    """Test disjunction, if-then-else, negation in EDCG rules."""

    def test_disjunction(self, tmp_path):
        """Disjunction in EDCG body."""
        src = (
            '-module(dj1, [inc_or_double(_cnt0, _cnt)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(inc_or_double, 0, [counter])\n'
            'inc_or_double >> ([1] // counter or [2] // counter)\n'
        )
        mod = _load("dj1", src, tmp_path)
        solutions = []
        n = Var()
        trail = Trail()
        for _ in call("inc_or_double", 0, n, module=mod):
            solutions.append(deref(n))
        assert 1 in solutions
        assert 2 in solutions

    def test_inline_goal(self, tmp_path):
        """Inline goals {goal} don't thread accumulators."""
        src = (
            '-module(ig1, [inc_if_positive(_cnt0, _cnt)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(inc_if_positive, 0, [counter])\n'
            'inc_if_positive >> (counter / _n, {_n >= 0}, [1] // counter)\n'
        )
        mod = _load("ig1", src, tmp_path)
        n = Var()
        for _ in call("inc_if_positive", 5, n, module=mod):
            assert deref(n) == 6
            break


# ── Phase 7: Real-World Patterns ────────────────────────────────────────────


class TestEdcgPatterns:
    """Port of classic EDCG patterns."""

    def test_len_adder(self, tmp_path):
        """Port of the len/adder example from EDCG docs."""
        src = (
            '-module(len1, [my_len(_list, _n)])\n'
            '-edcg_acc(adder, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(count_elem, 0, [adder, dcg])\n'
            '-edcg_pred(count_list, 0, [adder, dcg])\n'
            'count_elem >> ([_], [1] // adder)\n'
            'count_list >> (count_elem, count_list)\n'
            'count_list >> ([])\n'
            'my_len(_list, _n) <- count_list(_edcg_adder_in_=0, _edcg_adder_out_=_n, _edcg_dcg_in_=_list, _edcg_dcg_out_=[])\n'
        )
        mod = _load("len1", src, tmp_path)
        n = Var()
        for _ in call("my_len", [1, 2, 3], n, module=mod):
            assert deref(n) == 3
            break

    def test_compiler_pass(self, tmp_path):
        """Simulate compiler: parse tokens + emit instructions + count ops."""
        src = (
            '-module(comp1, [compile_all(_code0, _code, _ops0, _ops, _toks, _rest)])\n'
            '-edcg_acc(code, _instr, _in, _out, {_out is [_instr, *_in]})\n'
            '-edcg_acc(ops, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(emit, 1, [code, ops])\n'
            '-edcg_pred(compile_one, 0, [code, ops, dcg])\n'
            '-edcg_pred(compile_all, 0, [code, ops, dcg])\n'
            'emit(_i) >> ([_i] // code, [1] // ops)\n'
            'compile_one >> (["push", _v], emit(("PUSH", _v)))\n'
            'compile_one >> (["add"], emit("ADD"))\n'
            'compile_all >> (compile_one, compile_all)\n'
            'compile_all >> ([])\n'
        )
        mod = _load("comp1", src, tmp_path)
        rest = Var()
        code = Var()
        ops = Var()
        # Args in edcg_pred order: code_in, code_out, ops_in, ops_out, dcg_in, dcg_out
        for _ in call("compile_all",
                       [], code, 0, ops,
                       ["push", 1, "push", 2, "add"], rest,
                       module=mod):
            assert deref(rest) == []
            assert deref(ops) == 3
            # code is built by prepend, so reversed
            code_val = deref(code)
            assert code_val[0] == "ADD"
            assert len(code_val) == 3
            break


# ── Phase 8: Fixture Integration ────────────────────────────────────────────


class TestEdcgFixture:
    """Test EDCG via .clausal fixture files."""

    def test_counter_fixture(self, tmp_path):
        """Load edcg_counter.clausal and run a scaled count."""
        import shutil, os
        fixture_src = os.path.join(
            os.path.dirname(__file__), "fixtures", "edcg_counter.clausal"
        )
        dest = tmp_path / "edcg_counter.clausal"
        shutil.copy(fixture_src, dest)
        mod = _load_module("edcg_counter", str(dest))
        lm = mod.__dict__["$module"]
        count = Var()
        items = Var()
        for _ in call("run_scaled", ["a", "b", "c"], 10, count, items, module=lm):
            assert deref(count) == 30  # 3 items * scale 10
            assert deref(items) == ["c", "b", "a"]  # reversed due to prepend
            break


# ── Phase 9: Edge Cases ─────────────────────────────────────────────────────


class TestEdcgEdgeCases:
    """Test edge cases and corner conditions."""

    def test_empty_body(self, tmp_path):
        """EDCG rule with empty body []."""
        src = (
            '-module(eb1, [noop(_cnt0, _cnt)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(noop, 0, [counter])\n'
            'noop >> ([])\n'
        )
        mod = _load("eb1", src, tmp_path)
        n = Var()
        for _ in call("noop", 42, n, module=mod):
            assert deref(n) == 42  # unchanged
            break

    def test_recursive_accumulator(self, tmp_path):
        """Recursive EDCG predicate counting list length."""
        src = (
            '-module(rc1, [my_length(_l, _n)])\n'
            '-edcg_acc(len, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(count_elems, 1, [len])\n'
            'count_elems([]) >> ([])\n'
            'count_elems([_, *_xs]) >> ([1] // len, count_elems(_xs))\n'
            'my_length(_l, _n) <- count_elems(_l, _edcg_len_in_=0, _edcg_len_out_=_n)\n'
        )
        mod = _load("rc1", src, tmp_path)
        n = Var()
        for _ in call("my_length", [1, 2, 3, 4, 5], n, module=mod):
            assert deref(n) == 5
            break

    def test_multiple_pushes_in_sequence(self, tmp_path):
        """Multiple pushes to the same accumulator in a single rule."""
        src = (
            '-module(mp1, [add_three(_cnt0, _cnt)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_pred(add_three, 0, [counter])\n'
            'add_three >> ([1] // counter, [1] // counter, [1] // counter)\n'
        )
        mod = _load("mp1", src, tmp_path)
        n = Var()
        for _ in call("add_three", 0, n, module=mod):
            assert deref(n) == 3
            break

    def test_two_independent_accumulators(self, tmp_path):
        """Two accumulators updated independently in different sub-rules."""
        src = (
            '-module(ti1, [run(_cnt0, _cnt, _items0, _items)])\n'
            '-edcg_acc(counter, _x, _in, _out, {_out := _in + _x})\n'
            '-edcg_acc(items, _item, _in, _out, {_out is [_item, *_in]})\n'
            '-edcg_pred(inc_only, 0, [counter])\n'
            '-edcg_pred(collect_only, 1, [items])\n'
            '-edcg_pred(run, 0, [counter, items])\n'
            'inc_only >> ([1] // counter)\n'
            'collect_only(_x) >> ([_x] // items)\n'
            'run >> (inc_only, collect_only("hello"), inc_only, collect_only("world"))\n'
        )
        mod = _load("ti1", src, tmp_path)
        cnt = Var()
        items = Var()
        for _ in call("run", 0, cnt, [], items, module=mod):
            assert deref(cnt) == 2
            assert deref(items) == ["world", "hello"]
            break
