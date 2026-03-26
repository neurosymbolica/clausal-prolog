"""Tests for V2-17 Definite Clause Grammars (DCGs).

DCG rules use ``>>`` syntax and compile to ordinary predicates with two
extra state arguments (input list, remaining list) threaded through the body.
"""

from __future__ import annotations

import pytest

from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load(name, src_text, tmp_path):
    """Write a .clausal file and load it as a module."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    """Return True if the predicate succeeds at least once."""
    for _ in call(functor, *args, module=module):
        return True
    return False


# ── Terminals ────────────────────────────────────────────────────────────────


class TestTerminals:
    def test_single_terminal(self, tmp_path):
        mod = _load("t1", 'hi >> (["hello"])\n', tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, ["hello"], module=mod)

    def test_multi_terminal(self, tmp_path):
        mod = _load("t2", 'greet >> (["hello", "world"])\n', tmp_path)
        cls = mod.module_dict["greet"]
        assert _succeeds("phrase", cls, ["hello", "world"], module=mod)

    def test_empty_terminal(self, tmp_path):
        mod = _load("t3", 'epsilon >> ([])\n', tmp_path)
        cls = mod.module_dict["epsilon"]
        assert _succeeds("phrase", cls, [], module=mod)

    def test_terminal_no_match(self, tmp_path):
        mod = _load("t4", 'hi >> (["hello"])\n', tmp_path)
        cls = mod.module_dict["hi"]
        assert not _succeeds("phrase", cls, ["goodbye"], module=mod)


# ── Non-terminals ────────────────────────────────────────────────────────────


class TestNonTerminals:
    def test_chained_non_terminals(self, tmp_path):
        src = (
            'ab_rule >> (["a"])\n'
            'cd_rule >> (["c"])\n'
            'abcd >> (ab_rule, cd_rule)\n'
        )
        mod = _load("nt1", src, tmp_path)
        cls = mod.module_dict["abcd"]
        assert _succeeds("phrase", cls, ["a", "c"], module=mod)
        assert not _succeeds("phrase", cls, ["a"], module=mod)

    def test_non_terminal_with_args(self, tmp_path):
        src = 'tok(T_) >> ([T_])\n'
        mod = _load("nt2", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), ["x"], module=mod):
            results.append(deref(v))
        assert results == ["x"]


# ── Inline Goals ─────────────────────────────────────────────────────────────


class TestInlineGoals:
    def test_inline_goal_passthrough(self, tmp_path):
        src = 'pos(D_) >> ([D_], {D_ > 0})\n'
        mod = _load("ig1", src, tmp_path)
        cls = mod.module_dict["pos"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), [5], module=mod):
            results.append(deref(v))
        assert results == [5]
        # Negative number should fail the inline goal.
        v2 = Var()
        results2 = []
        for _ in call("phrase", cls(v2), [-1], module=mod):
            results2.append(deref(v2))
        assert results2 == []

    def test_multiple_inline_goals(self, tmp_path):
        src = 'bounded(D_) >> ([D_], {D_ >= 0}, {D_ <= 9})\n'
        mod = _load("ig2", src, tmp_path)
        cls = mod.module_dict["bounded"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), [5], module=mod):
            results.append(deref(v))
        assert results == [5]
        # Out of range.
        v2 = Var()
        results2 = []
        for _ in call("phrase", cls(v2), [10], module=mod):
            results2.append(deref(v2))
        assert results2 == []


# ── Conjunction ──────────────────────────────────────────────────────────────


class TestConjunction:
    def test_tuple_conjunction(self, tmp_path):
        src = (
            'x_rule >> (["x"])\n'
            'y_rule >> (["y"])\n'
            'xy >> (x_rule, y_rule)\n'
        )
        mod = _load("cj1", src, tmp_path)
        cls = mod.module_dict["xy"]
        assert _succeeds("phrase", cls, ["x", "y"], module=mod)

    def test_and_conjunction(self, tmp_path):
        src = (
            'a_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'ab_and >> (a_rule and b_rule)\n'
        )
        mod = _load("cj2", src, tmp_path)
        cls = mod.module_dict["ab_and"]
        assert _succeeds("phrase", cls, ["a", "b"], module=mod)


# ── Disjunction ──────────────────────────────────────────────────────────────


class TestDisjunction:
    def test_or_branches(self, tmp_path):
        src = 'letter >> (["a"] or ["b"] or ["c"])\n'
        mod = _load("dj1", src, tmp_path)
        cls = mod.module_dict["letter"]
        assert _succeeds("phrase", cls, ["a"], module=mod)
        assert _succeeds("phrase", cls, ["b"], module=mod)
        assert _succeeds("phrase", cls, ["c"], module=mod)
        assert not _succeeds("phrase", cls, ["d"], module=mod)


# ── Negation ─────────────────────────────────────────────────────────────────


class TestNegation:
    def test_not_terminal(self, tmp_path):
        src = 'not_a >> (not ["a"], [X_])\n'
        mod = _load("neg1", src, tmp_path)
        cls = mod.module_dict["not_a"]
        # Should succeed for non-'a' inputs.
        assert _succeeds("phrase", cls, ["b"], module=mod)
        # Should fail for 'a' input.
        assert not _succeeds("phrase", cls, ["a"], module=mod)


# ── If-then-else ─────────────────────────────────────────────────────────────


class TestIfThenElse:
    def test_if_then_else_nonterminals(self, tmp_path):
        """If-then-else with non-terminal conditions (no star-list in If)."""
        src = (
            'a_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'c_rule >> (["c"])\n'
            'a_or_c >> (If(a_rule, b_rule, c_rule))\n'
        )
        mod = _load("ite1", src, tmp_path)
        cls = mod.module_dict["a_or_c"]
        # "a" matches condition → then branch "b"
        assert _succeeds("phrase", cls, ["a", "b"], module=mod)
        # "c" doesn't match "a" condition → else branch "c"
        assert _succeeds("phrase", cls, ["c"], module=mod)
        # "b" doesn't match either path
        assert not _succeeds("phrase", cls, ["b"], module=mod)


# ── Pushback / Semicontext ───────────────────────────────────────────────────


class TestPushback:
    def test_look_ahead(self, tmp_path):
        src = '(peek(T_), [T_]) >> ([T_])\n'
        mod = _load("pb1", src, tmp_path)
        cls = mod.module_dict["peek"]
        v = Var()
        rest = Var()
        # peek should consume the token but push it back.
        results = []
        for _ in call("phrase", cls(v), ["x"], rest, module=mod):
            results.append((deref(v), deref(rest)))
        assert results == [("x", ["x"])]


# ── phrase/2 and phrase/3 ────────────────────────────────────────────────────


class TestPhrase:
    def test_phrase_2_success(self, tmp_path):
        src = 'hi >> (["hello", "world"])\n'
        mod = _load("ph1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, ["hello", "world"], module=mod)

    def test_phrase_2_fail(self, tmp_path):
        src = 'hi >> (["hello", "world"])\n'
        mod = _load("ph2", src, tmp_path)
        cls = mod.module_dict["hi"]
        # Extra elements — must consume entire list.
        assert not _succeeds("phrase", cls, ["hello", "world", "extra"], module=mod)

    def test_phrase_3_partial(self, tmp_path):
        src = 'tok(T_) >> ([T_])\n'
        mod = _load("ph3", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        rest = Var()
        results = []
        for _ in call("phrase", cls(v), ["a", "b", "c"], rest, module=mod):
            results.append((deref(v), deref(rest)))
        assert results == [("a", ["b", "c"])]


# ── Recursive DCGs ──────────────────────────────────────────────────────────


class TestRecursive:
    def test_recursive_list(self, tmp_path):
        src = (
            'items >> ([X_], items)\n'
            'items >> ([])\n'
        )
        mod = _load("rec1", src, tmp_path)
        cls = mod.module_dict["items"]
        assert _succeeds("phrase", cls, [1, 2, 3], module=mod)
        assert _succeeds("phrase", cls, [], module=mod)

    def test_recursive_digits(self, tmp_path):
        src = (
            'digits >> ([D_], {D_ >= 0}, {D_ <= 9}, digits)\n'
            'digits >> ([])\n'
        )
        mod = _load("rec2", src, tmp_path)
        cls = mod.module_dict["digits"]
        assert _succeeds("phrase", cls, [1, 2, 3], module=mod)
        assert _succeeds("phrase", cls, [], module=mod)
        assert not _succeeds("phrase", cls, [10], module=mod)


# ── Integration: fixture ─────────────────────────────────────────────────────


class TestFixtureIntegration:
    @pytest.fixture(autouse=True)
    def load_fixture(self):
        import os
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "dcg_grammar.clausal"
        )
        mod = _load_module("dcg_grammar", fixture)
        self.mod = mod.__dict__["$module"]
        self.module_dict = mod.__dict__

    def test_greeting(self):
        cls = self.module_dict["greeting"]
        assert _succeeds("phrase", cls, ["hello", "world"], module=self.mod)
        assert not _succeeds("phrase", cls, ["hi"], module=self.mod)

    def test_noun_phrase(self):
        cls = self.module_dict["noun_phrase"]
        assert _succeeds("phrase", cls, ["the", "dog"], module=self.mod)
        assert _succeeds("phrase", cls, ["a", "bird"], module=self.mod)
        assert not _succeeds("phrase", cls, ["the", "fish"], module=self.mod)

    def test_sentence(self):
        cls = self.module_dict["sentence"]
        assert _succeeds(
            "phrase", cls,
            ["the", "dog", "chases", "the", "cat"],
            module=self.mod,
        )
        assert not _succeeds(
            "phrase", cls, ["the", "dog", "chases"], module=self.mod
        )

    def test_digit_with_args(self):
        cls = self.module_dict["digit"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), [5], module=self.mod):
            results.append(deref(v))
        assert results == [5]

    def test_valid_sentence_regular_pred(self):
        """Regular <- predicate coexisting with DCG rules."""
        assert _succeeds(
            "valid_sentence",
            ["the", "dog", "sees", "a", "bird"],
            module=self.mod,
        )

    def test_look_ahead_pushback(self):
        cls = self.module_dict["look_ahead"]
        v = Var()
        rest = Var()
        results = []
        for _ in call("phrase", cls(v), ["x"], rest, module=self.mod):
            results.append((deref(v), deref(rest)))
        assert results == [("x", ["x"])]

    def test_not_a(self):
        cls = self.module_dict["not_a"]
        assert _succeeds("phrase", cls, ["b"], module=self.mod)
        assert not _succeeds("phrase", cls, ["a"], module=self.mod)


# ── State threading (Triska-style) ─────────────────────────────────────────


class TestStateThreading:
    """DCGs as general state-passing mechanism.

    The difference-list pair can carry *any* state encoded as a single-element
    list ``[State]``.  ``phrase/3`` sets initial/final state.  Pushback writes
    the new state, terminals read it.
    """

    # -- state/1 and state/2 helpers --

    def test_state_read(self, tmp_path):
        """state/1 reads current state without modifying it."""
        src = (
            '-module(s1, [state(S_, S0_, S_2)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
        )
        mod = _load("s1", src, tmp_path)
        cls = mod.module_dict["state"]
        s = Var()
        rest = Var()
        for _ in call("phrase", cls(s), [42], rest, module=mod):
            assert deref(s) == 42
            assert deref(rest) == [42]  # state unchanged

    def test_state_read_write(self, tmp_path):
        """state/2 reads old state and writes new state."""
        src = (
            '-module(s2, [state2(S0_, S_, S0_2, S_2)])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
        )
        mod = _load("s2", src, tmp_path)
        cls = mod.module_dict["state2"]
        s0 = Var()
        rest = Var()
        for _ in call("phrase", cls(s0, 99), [42], rest, module=mod):
            assert deref(s0) == 42
            assert deref(rest) == [99]

    # -- Counter via state threading --

    def test_increment_counter(self, tmp_path):
        """Single increment: state goes from [0] to [1]."""
        src = (
            '-module(inc1, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2), inc(S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
        )
        mod = _load("inc1", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["inc"], [0], [n], module=mod):
            assert deref(n) == 1

    def test_count_three(self, tmp_path):
        """Three increments: [0] -> [3]."""
        src = (
            '-module(c3, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2), inc(S0_, S_), count3(S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("c3", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["count3"], [0], [n], module=mod):
            assert deref(n) == 3

    def test_counter_start_nonzero(self, tmp_path):
        """Counting starts from a nonzero initial state."""
        src = (
            '-module(c4, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2), inc(S0_, S_), count3(S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("c4", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["count3"], [10], [n], module=mod):
            assert deref(n) == 13

    # -- Tree leaf counting --

    def test_count_leaves_single(self, tmp_path):
        """Count leaves in a single-leaf tree."""
        src = (
            '-module(tc1, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' count_leaves(T_, S0_, S_), num_leaves(T_, N_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'count_leaves("leaf") >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count_leaves([L_, R_]) >> (count_leaves(L_), count_leaves(R_))\n'
            'num_leaves(T_, N_) <- phrase(count_leaves(T_), [0], [N_])\n'
        )
        mod = _load("tc1", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", "leaf", n, module=mod):
            assert deref(n) == 1

    def test_count_leaves_two(self, tmp_path):
        """Count leaves in a two-leaf tree: [leaf, leaf]."""
        src = (
            '-module(tc2, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' count_leaves(T_, S0_, S_), num_leaves(T_, N_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'count_leaves("leaf") >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count_leaves([L_, R_]) >> (count_leaves(L_), count_leaves(R_))\n'
            'num_leaves(T_, N_) <- phrase(count_leaves(T_), [0], [N_])\n'
        )
        mod = _load("tc2", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=mod):
            assert deref(n) == 2

    def test_count_leaves_nested(self, tmp_path):
        """Count leaves in nested tree: [leaf, [leaf, leaf]] = 3."""
        src = (
            '-module(tc3, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' count_leaves(T_, S0_, S_), num_leaves(T_, N_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'count_leaves("leaf") >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count_leaves([L_, R_]) >> (count_leaves(L_), count_leaves(R_))\n'
            'num_leaves(T_, N_) <- phrase(count_leaves(T_), [0], [N_])\n'
        )
        mod = _load("tc3", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", ["leaf", "leaf"]], n, module=mod):
            assert deref(n) == 3

    # -- Accumulator: collect items into a list --

    def test_accumulator_push(self, tmp_path):
        """Push items onto accumulator state."""
        src = (
            '-module(acc1, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' push(X_, S0_, S_), push_all(XS_, S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'push(X_) >> (state(Acc0_), {Acc_ is [X_, *Acc0_]}, state2(_, Acc_))\n'
            'push_all([]) >> ([])\n'
            'push_all([X_, *Xs_]) >> (push(X_), push_all(Xs_))\n'
        )
        mod = _load("acc1", src, tmp_path)
        rest = Var()
        for _ in call("phrase", mod.module_dict["push_all"]([1, 2, 3]),
                       [[]], rest, module=mod):
            # Items pushed in order → reversed due to prepend
            assert deref(rest) == [[3, 2, 1]]

    def test_accumulator_empty(self, tmp_path):
        """Empty list: accumulator state unchanged."""
        src = (
            '-module(acc2, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' push(X_, S0_, S_), push_all(XS_, S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'push(X_) >> (state(Acc0_), {Acc_ is [X_, *Acc0_]}, state2(_, Acc_))\n'
            'push_all([]) >> ([])\n'
            'push_all([X_, *Xs_]) >> (push(X_), push_all(Xs_))\n'
        )
        mod = _load("acc2", src, tmp_path)
        rest = Var()
        for _ in call("phrase", mod.module_dict["push_all"]([]),
                       [[]], rest, module=mod):
            assert deref(rest) == [[]]

    # -- State-only DCG (no token parsing) --

    def test_state_only_dcg(self, tmp_path):
        """DCG used purely for state-passing, no token consumption."""
        src = (
            '-module(so, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' double(S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'double >> (state(N0_), {N_ := N0_ * 2}, state2(_, N_))\n'
        )
        mod = _load("so", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["double"], [5], [n], module=mod):
            assert deref(n) == 10

    def test_state_chained_operations(self, tmp_path):
        """Chain multiple state operations: inc then double."""
        src = (
            '-module(ch, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' inc(S0_, S_), double(S0_, S_), inc_then_double(S0_, S_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'double >> (state(N0_), {N_ := N0_ * 2}, state2(_, N_))\n'
            'inc_then_double >> (inc, double)\n'
        )
        mod = _load("ch", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["inc_then_double"],
                       [5], [n], module=mod):
            assert deref(n) == 12  # (5+1)*2

    # -- phrase/3 with compound state value --

    def test_string_state(self, tmp_path):
        """State can be any value — here a string."""
        src = (
            '-module(ss, [state2(S0_, S_, S0_2, S_2), set_name(N_, S0_, S_)])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'set_name(N_) >> (state2(_, N_))\n'
        )
        mod = _load("ss", src, tmp_path)
        rest = Var()
        for _ in call("phrase", mod.module_dict["set_name"]("alice"),
                       ["bob"], rest, module=mod):
            assert deref(rest) == ["alice"]

    # -- phrase/3 for calling DCG from regular predicate (term arg) --

    def test_phrase_with_term_arg(self, tmp_path):
        """phrase/3 called from a regular clause with a term argument."""
        src = (
            '-module(pt, [state(S_, S0_, S_2), state2(S0_, S_, S0_2, S_2),'
            ' inc(S0_, S_), run_inc(N0_, N_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'run_inc(N0_, N_) <- phrase(inc, [N0_], [N_])\n'
        )
        mod = _load("pt", src, tmp_path)
        n = Var()
        for _ in call("run_inc", 0, n, module=mod):
            assert deref(n) == 1

    def test_phrase_with_instance_arg(self, tmp_path):
        """phrase/3 called from clause body with instance arg (Call fix)."""
        src = (
            '-module(pi, [count_leaves(T_, S0_, S_), state(S_, S0_, S_2),'
            ' state2(S0_, S_, S0_2, S_2), num_leaves(T_, N_)])\n'
            '(state(S_), [S_]) >> ([S_])\n'
            '(state2(S0_, S_), [S_]) >> ([S0_])\n'
            'count_leaves("leaf") >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))\n'
            'count_leaves([L_, R_]) >> (count_leaves(L_), count_leaves(R_))\n'
            'num_leaves(T_, N_) <- phrase(count_leaves(T_), [0], [N_])\n'
        )
        mod = _load("pi", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=mod):
            assert deref(n) == 2


# ── Integration: dcg_state.clausal example ──────────────────────────────────


class TestDcgStateExample:
    """End-to-end tests against clausal/examples/dcg_state.clausal."""

    @pytest.fixture(autouse=True)
    def load_example(self):
        import os
        example = os.path.join(
            os.path.dirname(__file__), os.pardir,
            "clausal", "examples", "dcg_state.clausal",
        )
        mod = _load_module("dcg_state", os.path.abspath(example))
        self.mod = mod.__dict__["$module"]
        self.md = mod.__dict__

    def test_count3(self):
        n = Var()
        for _ in call("phrase", self.md["count3"], [0], [n], module=self.mod):
            assert deref(n) == 3

    def test_inc_then_double(self):
        n = Var()
        for _ in call("phrase", self.md["inc_then_double"],
                       [5], [n], module=self.mod):
            assert deref(n) == 12  # (5+1)*2

    def test_num_leaves_two(self):
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=self.mod):
            assert deref(n) == 2

    def test_num_leaves_nested(self):
        n = Var()
        for _ in call("num_leaves", ["leaf", ["leaf", "leaf"]],
                       n, module=self.mod):
            assert deref(n) == 3

    def test_collect_items(self):
        r = Var()
        for _ in call("collect_items", [1, 2, 3], r, module=self.mod):
            assert deref(r) == [3, 2, 1]

    def test_collect_items_empty(self):
        r = Var()
        for _ in call("collect_items", [], r, module=self.mod):
            assert deref(r) == []


# ── Phase 3: DCGs accept strings ────────────────────────────────────────────


class TestDCGStringInput:
    """phrase/2 and phrase/3 accept strings, converting to char lists."""

    def test_phrase2_string_match(self, tmp_path):
        """phrase(rule, "hi") works — string converted to char list."""
        src = 'hi >> (["h", "i"])\n'
        mod = _load("ds1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, "hi", module=mod)

    def test_phrase2_string_no_match(self, tmp_path):
        """phrase(rule, "ho") fails when grammar expects "hi"."""
        src = 'hi >> (["h", "i"])\n'
        mod = _load("ds2", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert not _succeeds("phrase", cls, "ho", module=mod)

    def test_phrase2_string_empty(self, tmp_path):
        """phrase(eps, "") succeeds for empty grammar."""
        src = 'eps >> ([])\n'
        mod = _load("ds3", src, tmp_path)
        cls = mod.module_dict["eps"]
        assert _succeeds("phrase", cls, "", module=mod)

    def test_phrase2_string_multi_terminal(self, tmp_path):
        """phrase(rule, "hello") matches multi-char terminal sequence."""
        src = 'hello >> (["h", "e", "l", "l", "o"])\n'
        mod = _load("ds4", src, tmp_path)
        cls = mod.module_dict["hello"]
        assert _succeeds("phrase", cls, "hello", module=mod)
        assert not _succeeds("phrase", cls, "hell", module=mod)

    def test_phrase3_string_remainder(self, tmp_path):
        """phrase(rule, "hiXY", Rest) — Rest is a char list."""
        src = 'hi >> (["h", "i"])\n'
        mod = _load("ds5", src, tmp_path)
        cls = mod.module_dict["hi"]
        rest = Var()
        results = []
        for _ in call("phrase", cls, "hiXY", rest, module=mod):
            results.append(deref(rest))
        assert results == [["X", "Y"]]

    def test_phrase2_chained_nonterminals_string(self, tmp_path):
        """Chained non-terminals consume a string."""
        src = (
            'a_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'ab >> (a_rule, b_rule)\n'
        )
        mod = _load("ds6", src, tmp_path)
        cls = mod.module_dict["ab"]
        assert _succeeds("phrase", cls, "ab", module=mod)
        assert not _succeeds("phrase", cls, "ac", module=mod)

    def test_phrase2_recursive_string(self, tmp_path):
        """Recursive DCG parses a string character by character."""
        src = (
            'chars >> (["a"], chars)\n'
            'chars >> ([])\n'
        )
        mod = _load("ds7", src, tmp_path)
        cls = mod.module_dict["chars"]
        assert _succeeds("phrase", cls, "aaa", module=mod)
        assert _succeeds("phrase", cls, "", module=mod)
        assert not _succeeds("phrase", cls, "aab", module=mod)

    def test_phrase2_dcg_with_args_string(self, tmp_path):
        """DCG with args extracts characters from string input."""
        src = 'tok(T_) >> ([T_])\n'
        mod = _load("ds8", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), "x", module=mod):
            results.append(deref(v))
        assert results == ["x"]

    def test_phrase2_inline_goal_string(self, tmp_path):
        """DCG with inline goal on string input."""
        src = 'vowel(V_) >> ([V_], {In(V_, ["a", "e", "i", "o", "u"])})\n'
        mod = _load("ds9", src, tmp_path)
        cls = mod.module_dict["vowel"]
        v = Var()
        results = []
        for _ in call("phrase", cls(v), "e", module=mod):
            results.append(deref(v))
        assert results == ["e"]
        # Consonant should fail
        results2 = []
        for _ in call("phrase", cls(v), "b", module=mod):
            results2.append(deref(v))
        assert results2 == []

    def test_list_input_still_works(self, tmp_path):
        """List input is unchanged (no regression)."""
        src = 'hi >> (["h", "i"])\n'
        mod = _load("ds10", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, ["h", "i"], module=mod)
