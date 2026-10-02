"""Tests for V2-17 Definite Clause Grammars (DCGs).

DCG rules use ``>>`` syntax and compile to ordinary predicates with two
extra state arguments (input list, remaining list) threaded through the body.
"""

from __future__ import annotations

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.logic.atoms import demangle
from clausal.logic.cells import chars
from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module
from tests._suffix import SEAM


# ── Helpers ──────────────────────────────────────────────────────────────────



def _nt(cls, *args):
    """A nonterminal term at its WRITTEN arity -- ``tok(T)`` is
    ``("tok", T)``.  Ruling C (2026-09-24): the class of a //N nonterminal is
    ONE arity (N+2), and applying it to N arguments no longer pads the two
    state slots with fresh variables -- it raises -- so the term phrase takes
    is built by name, and phrase appends S0/S to it (ISO call/N)."""
    # After the W4b-2d flip the module-dict binding is a mangled HANDLE
    # (a str); its name is the handle's predicate half.
    name = demangle(cls)[1] if isinstance(cls, str) else cls.__name__
    return (name, *args)


def _load(name, src_text, tmp_path):
    """write a .clausal file and load it as a module."""
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    """Return True if the predicate succeeds at least once."""
    for _ in call(functor, *args, module=module):
        return True
    return False


# ── Terminals ────────────────────────────────────────────────────────────────


# ── Dispatch contract (R1–R4 regression suite) ───────────────────────────────
#
# These tests pin the DCG head-matching and body-lowering contract that the
# 2026-06 DCG audit found broken.  See implementation_plans/dcg_audit/AUDIT.md.


class TestAtomHeadDispatch:
    """R1: atom-valued head arguments must dispatch by value.

    Regression from commit 92ce2636 (atoms became zero-field PredicateMeta
    classes): a ``PredicateMeta`` atom in a clause head fell through
    ``head_to_match_pattern`` to the wildcard fallback and matched *anything*.
    Affects every predicate, not just DCGs — pinned here because the audit
    surfaced it through DCG dispatch.
    """

    def test_dcg_atom_head_dispatch(self, tmp_path):
        """Two DCG clauses keyed on distinct atoms each return only their own."""
        src = (
            "-double_quotes(atom)\n-module(x, [r(T, S0, S), foo, bar])\n"
            'r(foo) >> (["F"])\n'
            'r(bar) >> (["B"])\n'
        )
        mod = _load("r1a", src, tmp_path)
        r = mod.module_dict["r"]
        foo = mod.module_dict["foo"]
        bar = mod.module_dict["bar"]
        assert _succeeds("phrase", _nt(r, foo), [mint("F")], module=mod)
        assert not _succeeds("phrase", _nt(r, foo), [mint("B")], module=mod)
        assert _succeeds("phrase", _nt(r, bar), [mint("B")], module=mod)
        assert not _succeeds("phrase", _nt(r, bar), [mint("F")], module=mod)

    def test_dcg_atom_head_no_compound_match(self, tmp_path):
        """An atom-head clause must NOT match a compound input."""
        src = (
            "-double_quotes(atom)\n-module(x, [r(T, S0, S), foo, ve(V)])\n"
            'r(foo) >> (["atom"])\n'
            'r(ve(V)) >> (["compound"])\n'
        )
        mod = _load("r1b", src, tmp_path)
        r = mod.module_dict["r"]
        foo = mod.module_dict["foo"]
        # P3-2 Task 2 (THE FLIP, R6): ``ve`` is a DATA functor -- the term is
        # the cell ``("ve", V)``, and the name binds the spelling.  ``r`` is a
        # predicate and ``foo`` an atom, both unchanged.
        assert mod.module_dict["ve"] == mint("ve")
        ve = lambda *args: ("ve", *args)
        # r(foo) only the atom clause
        assert _succeeds("phrase", _nt(r, foo), [mint("atom")], module=mod)
        assert not _succeeds("phrase", _nt(r, foo), [mint("compound")], module=mod)
        # r(ve(foo)) only the compound clause
        assert _succeeds("phrase", _nt(r, ve(foo)), [mint("compound")], module=mod)
        assert not _succeeds("phrase", _nt(r, ve(foo)), [mint("atom")], module=mod)

    def test_plain_rule_atom_head_dispatch(self, tmp_path):
        """core (non-DCG) regression: plain ``<-`` rule with atom heads."""
        src = (
            "-module(x, [r(T, O), foo, bar])\n"
            "r(foo, O) <- (O is 1)\n"
            "r(bar, O) <- (O is 2)\n"
        )
        mod = _load("r1c", src, tmp_path)
        r = mod.module_dict
        foo = r["foo"]
        bar = r["bar"]
        out = Var()
        foo_sols = [deref(out) for _ in call("r", foo, out, module=mod)]
        out2 = Var()
        bar_sols = [deref(out2) for _ in call("r", bar, out2, module=mod)]
        assert foo_sols == [1]
        assert bar_sols == [2]

    def test_compound_with_atom_arg_dispatch(self, tmp_path):
        """Nested atom inside a compound head must also discriminate."""
        src = (
            "-module(x, [r(T, O), ve(V), foo, bar])\n"
            "r(ve(foo), O) <- (O is 1)\n"
            "r(ve(bar), O) <- (O is 2)\n"
        )
        mod = _load("r1d", src, tmp_path)
        # R6: a cell constructor, as in test_dcg_atom_head_no_compound_match.
        assert mod.module_dict["ve"] == mint("ve")
        ve = lambda *args: ("ve", *args)
        foo = mod.module_dict["foo"]
        bar = mod.module_dict["bar"]
        out = Var()
        sols = [deref(out) for _ in call("r", ve(foo), out, module=mod)]
        assert sols == [1]

    def test_indexed_atom_head_dispatch(self, tmp_path):
        """≥4 atom-headed clauses (crosses the indexing threshold) still discriminate."""
        src = (
            "-module(x, [c(T, O), a, b, cc, d])\n"
            "c(a, O) <- (O is 1)\n"
            "c(b, O) <- (O is 2)\n"
            "c(cc, O) <- (O is 3)\n"
            "c(d, O) <- (O is 4)\n"
        )
        mod = _load("r1e", src, tmp_path)
        md = mod.module_dict
        for atom_name, expected in (("a", 1), ("b", 2), ("cc", 3), ("d", 4)):
            out = Var()
            sols = [deref(out) for _ in call("c", md[atom_name], out, module=mod)]
            assert sols == [expected], f"{atom_name} -> {sols}"


class TestTerminals:
    def test_single_terminal(self, tmp_path):
        # nv
        mod = _load("t1", '-double_quotes(atom)\nhi >> (["hello"])\n', tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, [mint("hello")], module=mod)

    def test_multi_terminal(self, tmp_path):
        # nv
        mod = _load("t2", '-double_quotes(atom)\ngreet >> (["hello", "world"])\n', tmp_path)
        cls = mod.module_dict["greet"]
        assert _succeeds("phrase", cls, [mint("hello"), mint("world")], module=mod)

    def test_empty_terminal(self, tmp_path):
        # nv
        mod = _load("t3", 'epsilon >> ([])\n', tmp_path)
        cls = mod.module_dict["epsilon"]
        assert _succeeds("phrase", cls, [], module=mod)

    def test_terminal_no_match(self, tmp_path):
        # nv
        mod = _load("t4", '-double_quotes(atom)\nhi >> (["hello"])\n', tmp_path)
        cls = mod.module_dict["hi"]
        assert not _succeeds("phrase", cls, ["goodbye"], module=mod)


# ── Non-terminals ────────────────────────────────────────────────────────────


class TestNonTerminals:
    def test_chained_non_terminals(self, tmp_path):
        # nv
        src = (
            '-double_quotes(atom)\nab_rule >> (["a"])\n'
            'cd_rule >> (["c"])\n'
            'abcd >> (ab_rule, cd_rule)\n'
        )
        mod = _load("nt1", src, tmp_path)
        cls = mod.module_dict["abcd"]
        assert _succeeds("phrase", cls, [mint("a"), mint("c")], module=mod)
        assert not _succeeds("phrase", cls, [mint("a")], module=mod)

    def test_non_terminal_with_args(self, tmp_path):
        # nv
        src = 'tok(_t) >> ([_t])\n'
        mod = _load("nt2", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), ["x"], module=mod):
            results.append(deref(v))
        assert results == ["x"]


# ── Inline Goals ─────────────────────────────────────────────────────────────


class TestInlineGoals:
    def test_inline_goal_passthrough(self, tmp_path):
        # nv
        src = 'pos(_d) >> ([_d], {_d > 0})\n'
        mod = _load("ig1", src, tmp_path)
        cls = mod.module_dict["pos"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), [5], module=mod):
            results.append(deref(v))
        assert results == [5]
        # Negative number should fail the inline goal.
        v2 = Var()
        results2 = []
        for _ in call("phrase", _nt(cls, v2), [-1], module=mod):
            results2.append(deref(v2))
        assert results2 == []

    def test_multiple_inline_goals(self, tmp_path):
        # nv
        src = 'bounded(_d) >> ([_d], {_d >= 0}, {_d <= 9})\n'
        mod = _load("ig2", src, tmp_path)
        cls = mod.module_dict["bounded"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), [5], module=mod):
            results.append(deref(v))
        assert results == [5]
        # Out of range.
        v2 = Var()
        results2 = []
        for _ in call("phrase", _nt(cls, v2), [10], module=mod):
            results2.append(deref(v2))
        assert results2 == []

    def test_multi_goal_block_in_sequence(self, tmp_path):
        """A single ``{g1, g2}`` block is a conjunction: BOTH goals enforced.

        Regression: the sequence rewriters used to take only ``elts[0]`` from a
        multi-element set, silently dropping every goal after the first — so
        ``[50]`` was wrongly accepted.
        """
        # nv
        src = 'bounded(_d) >> ([_d], {_d > 0, _d < 10})\n'
        mod = _load("igb", src, tmp_path)
        cls = mod.module_dict["bounded"]
        # In range: accepted.
        v = Var()
        results = [deref(v) for _ in call("phrase", _nt(cls, v), [5], module=mod)]
        assert results == [5]
        # The second goal (_d < 10) MUST reject [50].
        v2 = Var()
        results2 = [deref(v2) for _ in call("phrase", _nt(cls, v2), [50], module=mod)]
        assert results2 == []
        # The first goal (_d > 0) still rejects [-1].
        v3 = Var()
        results3 = [deref(v3) for _ in call("phrase", _nt(cls, v3), [-1], module=mod)]
        assert results3 == []

    def test_whole_body_multi_goal_block(self, tmp_path):
        """A whole-body ``{g1, g2}`` block must not raise SyntaxError.

        Regression: a bare multi-element-set body hit the ``case Set(elts=[goal])``
        miss and raised ``Unsupported DCG body element`` instead of behaving as a
        conjunction of embedded goals (consuming no input).
        """
        # nv
        src = 'ranged(_d) >> ({_d > 0, _d < 10})\n'
        mod = _load("igw", src, tmp_path)
        cls = mod.module_dict["ranged"]
        # No input consumed: succeeds on [] when both goals hold.
        assert _succeeds("phrase", _nt(cls, 5), [], module=mod)
        assert not _succeeds("phrase", _nt(cls, 50), [], module=mod)
        assert not _succeeds("phrase", _nt(cls, 0), [], module=mod)

    def test_empty_brace_block_error(self, tmp_path):
        """An empty ``{}`` DCG body gives a real error message, not an AST dump."""
        # nv
        with pytest.raises(SyntaxError, match=r"empty \{\} block in DCG body"):
            _load("ige", "e >> ({})\n", tmp_path)

    def test_bare_goal_body_hint(self, tmp_path):
        """A bare goal in body position errors with a wrap-in-braces hint."""
        # nv
        with pytest.raises(SyntaxError, match=r"wrap it in braces"):
            _load("igh", "bare(_d) >> ([_d], _d > 0)\n", tmp_path)


# ── Conjunction ──────────────────────────────────────────────────────────────


class TestConjunction:
    def test_tuple_conjunction(self, tmp_path):
        # nv
        src = (
            '-double_quotes(atom)\nx_rule >> (["x"])\n'
            'y_rule >> (["y"])\n'
            'xy >> (x_rule, y_rule)\n'
        )
        mod = _load("cj1", src, tmp_path)
        cls = mod.module_dict["xy"]
        assert _succeeds("phrase", cls, [mint("x"), mint("y")], module=mod)

    def test_and_conjunction(self, tmp_path):
        # nv
        src = (
            '-double_quotes(atom)\na_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'ab_and >> (a_rule and b_rule)\n'
        )
        mod = _load("cj2", src, tmp_path)
        cls = mod.module_dict["ab_and"]
        assert _succeeds("phrase", cls, [mint("a"), mint("b")], module=mod)


# ── Disjunction ──────────────────────────────────────────────────────────────


class TestDisjunction:
    def test_or_branches(self, tmp_path):
        # nv
        src = '-double_quotes(atom)\nletter >> (["a"] or ["b"] or ["c"])\n'
        mod = _load("dj1", src, tmp_path)
        cls = mod.module_dict["letter"]
        assert _succeeds("phrase", cls, [mint("a")], module=mod)
        assert _succeeds("phrase", cls, [mint("b")], module=mod)
        assert _succeeds("phrase", cls, [mint("c")], module=mod)
        assert not _succeeds("phrase", cls, [mint("d")], module=mod)


# ── Negation ─────────────────────────────────────────────────────────────────


class TestNegation:
    def test_not_terminal(self, tmp_path):
        # nv
        src = '-double_quotes(atom)\nnot_a >> (not ["a"], [_x])\n'
        mod = _load("neg1", src, tmp_path)
        cls = mod.module_dict["not_a"]
        # Should succeed for non-'a' inputs.
        assert _succeeds("phrase", cls, [mint("b")], module=mod)
        # Should fail for 'a' input.
        assert not _succeeds("phrase", cls, [mint("a")], module=mod)


# ── If-then-else ─────────────────────────────────────────────────────────────


class TestIfThenElse:
    """if_/3 in a DCG body.  The condition must be a ``{Goal}`` block that
    consumes no input, with Goal reifiable (operator ruling 2026-10-01): a
    grammar body as the condition -- a terminal, a non-terminal -- is a plain
    goal, and it used to run as a soft cut.  Each refused shape below is
    followed by its reified rewrite: read the token, branch on it."""

    @pytest.mark.parametrize("rule", [
        "a_or_c >> (if_(a_rule, b_rule, c_rule))\n",
        "c(_x) >> (if_([_x], [done], [empty]))\n",
        "g >> (if_([x], [y], [z]))\n",
    ], ids=["nonterminal", "terminal-var", "terminal"])
    def test_grammar_body_condition_is_refused(self, tmp_path, rule):
        src = ("-double_quotes(atom)\n-private([a, b, c, done, empty, x, y, z])\n"
               "a_rule >> ([\"a\"])\nb_rule >> ([\"b\"])\nc_rule >> ([\"c\"])\n"
               + rule)
        with pytest.raises(SyntaxError, match="reifiable condition"):
            _load("ite_refused", src, tmp_path)

    def test_if_then_else_nonterminals(self, tmp_path):
        """The non-terminal condition, rewritten: read the token, branch on
        it reifiedly; the else branch consumes the token it read."""
        # nv
        src = (
            '-double_quotes(atom)\na_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'c_rule >> (["c"])\n'
            'a_or_c >> ([T], if_({T is "a"}, b_rule, {T is "c"}))\n'
        )
        mod = _load("ite1", src, tmp_path)
        cls = mod.module_dict["a_or_c"]
        # "a" matches condition → then branch "b"
        assert _succeeds("phrase", cls, [mint("a"), mint("b")], module=mod)
        # "c" doesn't match "a" condition → else branch "c"
        assert _succeeds("phrase", cls, [mint("c")], module=mod)
        # "b" doesn't match either path
        assert not _succeeds("phrase", cls, [mint("b")], module=mod)

    def test_if_then_else_terminal_branches(self, tmp_path):
        """Terminal (list) branches under a reified token test."""
        src = (
            "-module(x, [c(X, S0, S), done, empty])\n"
            "c(_x) >> ([T], if_({T is _x}, [done], {T is empty}))\n"
        )
        mod = _load("ite2", src, tmp_path)
        c = mod.module_dict["c"]
        done = mod.module_dict["done"]
        empty = mod.module_dict["empty"]
        # the token is `done`; then-branch [done] consumes the next.
        assert _succeeds("phrase", _nt(c, done), [done, done], module=mod)
        # leading token is not `done` → else-branch: it is `empty`.
        assert _succeeds("phrase", _nt(c, done), [empty], module=mod)
        # the token is `done`, then-branch needs another `done` but sees
        # `empty` — fails (a ground reified test takes one branch only).
        assert not _succeeds("phrase", _nt(c, done), [done, empty], module=mod)

    def test_if_then_else_terminal_else_branch(self, tmp_path):
        """The else-branch path also produces a parse."""
        src = (
            "-module(x, [g(S0, S), x, y, z])\n"
            "g >> ([T], if_({T is x}, [y], {T is z}))\n"
        )
        mod = _load("ite3", src, tmp_path)
        g = mod.module_dict["g"]
        x = mod.module_dict["x"]
        y = mod.module_dict["y"]
        z = mod.module_dict["z"]
        # input starts with x → cond holds → then-branch consumes y
        assert _succeeds("phrase", g, [x, y], module=mod)
        # input does not start with x → else-branch: it is z
        assert _succeeds("phrase", g, [z], module=mod)


# ── Pushback / Semicontext ───────────────────────────────────────────────────


class TestPushback:
    def test_look_ahead(self, tmp_path):
        # nv
        src = '(peek(_t), [_t]) >> ([_t])\n'
        mod = _load("pb1", src, tmp_path)
        cls = mod.module_dict["peek"]
        v = Var()
        rest = Var()
        # peek should consume the token but push it back. Under the
        # Phase 2 Task 13 Liskov rule, the rest list of 1-char strs may
        # promote to ``"x"`` — accept either form.
        results = []
        for _ in call("phrase", _nt(cls, v), ["x"], rest, module=mod):
            results.append((deref(v), deref(rest)))
        assert results == [("x", ["x"])] or results == [("x", chars("x"))]


# ── phrase/2 and phrase/3 ────────────────────────────────────────────────────


class TestPhrase:
    def test_phrase_2_success(self, tmp_path):
        # nv
        src = '-double_quotes(atom)\nhi >> (["hello", "world"])\n'
        mod = _load("ph1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, [mint("hello"), mint("world")], module=mod)

    def test_phrase_2_fail(self, tmp_path):
        # nv
        src = '-double_quotes(atom)\nhi >> (["hello", "world"])\n'
        mod = _load("ph2", src, tmp_path)
        cls = mod.module_dict["hi"]
        # Extra elements — must consume entire list.
        assert not _succeeds("phrase", cls, ["hello", "world", "extra"], module=mod)

    def test_phrase_3_partial(self, tmp_path):
        # nv
        src = 'tok(_t) >> ([_t])\n'
        mod = _load("ph3", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        rest = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), ["a", "b", "c"], rest, module=mod):
            results.append((deref(v), deref(rest)))
        assert results == [("a", ["b", "c"])]


# ── Recursive DCGs ──────────────────────────────────────────────────────────


class TestRecursive:
    def test_recursive_list(self, tmp_path):
        # nv
        src = (
            'items >> ([_x], items)\n'
            'items >> ([])\n'
        )
        mod = _load("rec1", src, tmp_path)
        cls = mod.module_dict["items"]
        assert _succeeds("phrase", cls, [1, 2, 3], module=mod)
        assert _succeeds("phrase", cls, [], module=mod)

    def test_recursive_digits(self, tmp_path):
        # nv
        src = (
            'digits >> ([_d], {_d >= 0}, {_d <= 9}, digits)\n'
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
            os.path.dirname(__file__), "fixtures", "dcg_grammar.seam"
        )
        mod = _load_module("dcg_grammar", fixture)
        self.mod = mod.__dict__["$module"]
        self.module_dict = mod.__dict__

    def test_greeting(self):
        # nv
        cls = self.module_dict["greeting"]
        assert _succeeds(
            "phrase", cls, [mint("hello"), mint("world")], module=self.mod
        )
        assert not _succeeds("phrase", cls, [mint("hi")], module=self.mod)

    def test_noun_phrase(self):
        # nv
        cls = self.module_dict["noun_phrase"]
        assert _succeeds("phrase", cls, [mint("the"), mint("dog")], module=self.mod)
        assert _succeeds("phrase", cls, [mint("a"), mint("bird")], module=self.mod)
        assert not _succeeds(
            "phrase", cls, [mint("the"), mint("fish")], module=self.mod
        )

    def test_sentence(self):
        # nv
        cls = self.module_dict["sentence"]
        assert _succeeds(
            "phrase", cls,
            [mint("the"), mint("dog"), mint("chases"), mint("the"), mint("cat")],
            module=self.mod,
        )
        assert not _succeeds(
            "phrase",
            cls,
            [mint("the"), mint("dog"), mint("chases")],
            module=self.mod,
        )

    def test_digit_with_args(self):
        # nv
        cls = self.module_dict["digit"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), [5], module=self.mod):
            results.append(deref(v))
        assert results == [5]

    def test_valid_sentence_regular_pred(self):
        """Regular <- predicate coexisting with DCG rules."""
        # nv
        assert _succeeds(
            "valid_sentence",
            [mint("the"), mint("dog"), mint("sees"), mint("a"), mint("bird")],
            module=self.mod,
        )

    def test_look_ahead_pushback(self):
        # nv. Under Phase 2 Task 13 Liskov rule, ["x"] may promote to "x".
        cls = self.module_dict["look_ahead"]
        v = Var()
        rest = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), ["x"], rest, module=self.mod):
            results.append((deref(v), deref(rest)))
        assert results == [("x", ["x"])] or results == [("x", chars("x"))]

    def test_not_a(self):
        # nv
        cls = self.module_dict["not_a"]
        assert _succeeds("phrase", cls, [mint("b")], module=self.mod)
        assert not _succeeds("phrase", cls, [mint("a")], module=self.mod)


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
        # nv
        src = (
            '-module(s1, [state(_s, _s0, S_2)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
        )
        mod = _load("s1", src, tmp_path)
        cls = mod.module_dict["state"]
        s = Var()
        rest = Var()
        for _ in call("phrase", _nt(cls, s), [42], rest, module=mod):
            assert deref(s) == 42
            assert deref(rest) == [42]  # state unchanged

    def test_state_read_write(self, tmp_path):
        """state/2 reads old state and writes new state."""
        # nv
        src = (
            '-module(s2, [state2(_s0, _s, S0_2, S_2)])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
        )
        mod = _load("s2", src, tmp_path)
        cls = mod.module_dict["state2"]
        s0 = Var()
        rest = Var()
        for _ in call("phrase", _nt(cls, s0, 99), [42], rest, module=mod):
            assert deref(s0) == 42
            assert deref(rest) == [99]

    # -- Counter via state threading --

    def test_increment_counter(self, tmp_path):
        """Single increment: state goes from [0] to [1]."""
        # nv
        src = (
            '-module(inc1, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2), inc(_s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'inc >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
        )
        mod = _load("inc1", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["inc"], [0], [n], module=mod):
            assert deref(n) == 1

    def test_count_three(self, tmp_path):
        """Three increments: [0] -> [3]."""
        # nv
        src = (
            '-module(c3, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2), inc(_s0, _s), count3(_s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'inc >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("c3", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["count3"], [0], [n], module=mod):
            assert deref(n) == 3

    def test_counter_start_nonzero(self, tmp_path):
        """Counting starts from a nonzero initial state."""
        # nv
        src = (
            '-module(c4, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2), inc(_s0, _s), count3(_s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'inc >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count3 >> (inc, inc, inc)\n'
        )
        mod = _load("c4", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["count3"], [10], [n], module=mod):
            assert deref(n) == 13

    # -- Tree leaf counting --

    def test_count_leaves_single(self, tmp_path):
        """Count leaves in a single-leaf tree."""
        # nv
        src = (
            '-double_quotes(atom)\n-module(tc1, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' count_leaves(_t, _s0, _s), num_leaves(_t, _n)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'count_leaves("leaf") >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count_leaves([_l, _r]) >> (count_leaves(_l), count_leaves(_r))\n'
            'num_leaves(_t, _n) <- phrase(count_leaves(_t), [0], [_n])\n'
        )
        mod = _load("tc1", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", "leaf", n, module=mod):
            assert deref(n) == 1

    def test_count_leaves_two(self, tmp_path):
        """Count leaves in a two-leaf tree: [leaf, leaf]."""
        # nv
        src = (
            '-double_quotes(atom)\n-module(tc2, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' count_leaves(_t, _s0, _s), num_leaves(_t, _n)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'count_leaves("leaf") >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count_leaves([_l, _r]) >> (count_leaves(_l), count_leaves(_r))\n'
            'num_leaves(_t, _n) <- phrase(count_leaves(_t), [0], [_n])\n'
        )
        mod = _load("tc2", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=mod):
            assert deref(n) == 2

    def test_count_leaves_nested(self, tmp_path):
        """Count leaves in nested tree: [leaf, [leaf, leaf]] = 3."""
        # nv
        src = (
            '-double_quotes(atom)\n-module(tc3, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' count_leaves(_t, _s0, _s), num_leaves(_t, _n)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'count_leaves("leaf") >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count_leaves([_l, _r]) >> (count_leaves(_l), count_leaves(_r))\n'
            'num_leaves(_t, _n) <- phrase(count_leaves(_t), [0], [_n])\n'
        )
        mod = _load("tc3", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", ["leaf", "leaf"]], n, module=mod):
            assert deref(n) == 3

    # -- Accumulator: collect items into a list --

    def test_accumulator_push(self, tmp_path):
        """Push items onto accumulator state."""
        # nv
        src = (
            '-module(acc1, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' push(_x, _s0, _s), push_all(_xs, _s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'push(_x) >> (state(_acc0), {_acc is [_x, *_acc0]}, state2(_, _acc))\n'
            'push_all([]) >> ([])\n'
            'push_all([_x, *_xs]) >> (push(_x), push_all(_xs))\n'
        )
        mod = _load("acc1", src, tmp_path)
        rest = Var()
        for _ in call("phrase", _nt(mod.module_dict["push_all"], [1, 2, 3]),
                       [[]], rest, module=mod):
            # Items pushed in order → reversed due to prepend
            assert deref(rest) == [[3, 2, 1]]

    def test_accumulator_empty(self, tmp_path):
        """Empty list: accumulator state unchanged."""
        # nv
        src = (
            '-module(acc2, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' push(_x, _s0, _s), push_all(_xs, _s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'push(_x) >> (state(_acc0), {_acc is [_x, *_acc0]}, state2(_, _acc))\n'
            'push_all([]) >> ([])\n'
            'push_all([_x, *_xs]) >> (push(_x), push_all(_xs))\n'
        )
        mod = _load("acc2", src, tmp_path)
        rest = Var()
        for _ in call("phrase", _nt(mod.module_dict["push_all"], []),
                       [[]], rest, module=mod):
            assert deref(rest) == [[]]

    # -- State-only DCG (no token parsing) --

    def test_state_only_dcg(self, tmp_path):
        """DCG used purely for state-passing, no token consumption."""
        # nv
        src = (
            '-module(so, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' double(_s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'double >> (state(_n0), {_n == _n0 * 2}, state2(_, _n))\n'
        )
        mod = _load("so", src, tmp_path)
        n = Var()
        for _ in call("phrase", mod.module_dict["double"], [5], [n], module=mod):
            assert deref(n) == 10

    def test_state_chained_operations(self, tmp_path):
        """Chain multiple state operations: inc then double."""
        # nv
        src = (
            '-module(ch, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' inc(_s0, _s), double(_s0, _s), inc_then_double(_s0, _s)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'inc >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'double >> (state(_n0), {_n == _n0 * 2}, state2(_, _n))\n'
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
        # nv
        src = (
            '-module(ss, [state2(_s0, _s, S0_2, S_2), set_name(_n, _s0, _s)])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'set_name(_n) >> (state2(_, _n))\n'
        )
        mod = _load("ss", src, tmp_path)
        rest = Var()
        for _ in call("phrase", _nt(mod.module_dict["set_name"], "alice"),
                       ["bob"], rest, module=mod):
            assert deref(rest) == ["alice"]

    # -- phrase/3 for calling DCG from regular predicate (term arg) --

    def test_phrase_with_term_arg(self, tmp_path):
        """phrase/3 called from a regular clause with a term argument."""
        # nv
        src = (
            '-module(pt, [state(_s, _s0, S_2), state2(_s0, _s, S0_2, S_2),'
            ' inc(_s0, _s), run_inc(_n0, _n)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'inc >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'run_inc(_n0, _n) <- phrase(inc, [_n0], [_n])\n'
        )
        mod = _load("pt", src, tmp_path)
        n = Var()
        for _ in call("run_inc", 0, n, module=mod):
            assert deref(n) == 1

    def test_phrase_with_instance_arg(self, tmp_path):
        """phrase/3 called from clause body with instance arg (Call fix)."""
        # nv
        src = (
            '-double_quotes(atom)\n-module(pi, [count_leaves(_t, _s0, _s), state(_s, _s0, S_2),'
            ' state2(_s0, _s, S0_2, S_2), num_leaves(_t, _n)])\n'
            '(state(_s), [_s]) >> ([_s])\n'
            '(state2(_s0, _s), [_s]) >> ([_s0])\n'
            'count_leaves("leaf") >> (state(_n0), {_n == _n0 + 1}, state2(_, _n))\n'
            'count_leaves([_l, _r]) >> (count_leaves(_l), count_leaves(_r))\n'
            'num_leaves(_t, _n) <- phrase(count_leaves(_t), [0], [_n])\n'
        )
        mod = _load("pi", src, tmp_path)
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=mod):
            assert deref(n) == 2


# ── Integration: dcg_state.seam example ──────────────────────────────────


class TestDcgStateExample:
    """End-to-end tests against clausal/examples/dcg_state.seam."""

    @pytest.fixture(autouse=True)
    def load_example(self):
        import os
        example = os.path.join(
            os.path.dirname(__file__), os.pardir,
            "clausal", "examples", "dcg_state.seam",
        )
        mod = _load_module("dcg_state", os.path.abspath(example))
        self.mod = mod.__dict__["$module"]
        self.md = mod.__dict__

    def test_count3(self):
        # nv
        n = Var()
        for _ in call("phrase", self.md["count3"], [0], [n], module=self.mod):
            assert deref(n) == 3

    def test_inc_then_double(self):
        # nv
        n = Var()
        for _ in call("phrase", self.md["inc_then_double"],
                       [5], [n], module=self.mod):
            assert deref(n) == 12  # (5+1)*2

    def test_num_leaves_two(self):
        # nv
        n = Var()
        for _ in call("num_leaves", ["leaf", "leaf"], n, module=self.mod):
            assert deref(n) == 2

    def test_num_leaves_nested(self):
        # nv
        n = Var()
        for _ in call("num_leaves", ["leaf", ["leaf", "leaf"]],
                       n, module=self.mod):
            assert deref(n) == 3

    def test_collect_items(self):
        # nv
        r = Var()
        for _ in call("collect_items", [1, 2, 3], r, module=self.mod):
            assert deref(r) == [3, 2, 1]

    def test_collect_items_empty(self):
        # nv
        r = Var()
        for _ in call("collect_items", [], r, module=self.mod):
            assert deref(r) == []


# ── Phase 3: DCGs accept strings ────────────────────────────────────────────


class TestDCGStringInput:
    """phrase/2 and phrase/3 accept strings, converting to char lists."""

    def test_phrase2_string_match(self, tmp_path):
        """phrase(rule, "hi") works — string converted to char list."""
        # nv
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("ds1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, chars("hi"), module=mod)

    def test_phrase2_string_no_match(self, tmp_path):
        """phrase(rule, "ho") fails when grammar expects "hi"."""
        # nv
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("ds2", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert not _succeeds("phrase", cls, chars("ho"), module=mod)

    def test_phrase2_string_empty(self, tmp_path):
        """phrase(eps, "") succeeds for empty grammar."""
        # nv
        src = 'eps >> ([])\n'
        mod = _load("ds3", src, tmp_path)
        cls = mod.module_dict["eps"]
        assert _succeeds("phrase", cls, chars(""), module=mod)

    def test_phrase2_string_multi_terminal(self, tmp_path):
        """phrase(rule, "hello") matches multi-char terminal sequence."""
        # nv
        src = '-double_quotes(atom)\nhello >> (["h", "e", "l", "l", "o"])\n'
        mod = _load("ds4", src, tmp_path)
        cls = mod.module_dict["hello"]
        assert _succeeds("phrase", cls, chars("hello"), module=mod)
        assert not _succeeds("phrase", cls, chars("hell"), module=mod)

    def test_phrase3_string_remainder(self, tmp_path):
        """phrase(rule, "hiXY", Rest) — Rest preserves str type.

        Updated in Phase 2 Task 14 (F067 closure): under the Liskov
        "strings-as-lists" rule, phrase/3 no longer eagerly splits str
        input into chars at entry. Native str destructuring in
        ``_head_list_unify_input`` / ``_body_star_unify`` binds Rest to
        a str slice rather than a list of 1-char strs.
        """
        # nv
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("ds5", src, tmp_path)
        cls = mod.module_dict["hi"]
        rest = Var()
        results = []
        for _ in call("phrase", cls, chars("hiXY"), rest, module=mod):
            results.append(deref(rest))
        assert results == [chars("XY")]

    def test_phrase2_chained_nonterminals_string(self, tmp_path):
        """Chained non-terminals consume a string."""
        # nv
        src = (
            '-double_quotes(atom)\na_rule >> (["a"])\n'
            'b_rule >> (["b"])\n'
            'ab >> (a_rule, b_rule)\n'
        )
        mod = _load("ds6", src, tmp_path)
        cls = mod.module_dict["ab"]
        assert _succeeds("phrase", cls, chars("ab"), module=mod)
        assert not _succeeds("phrase", cls, chars("ac"), module=mod)

    def test_phrase2_recursive_string(self, tmp_path):
        """Recursive DCG parses a string character by character."""
        # nv
        src = (
            '-double_quotes(atom)\nchars >> (["a"], chars)\n'
            'chars >> ([])\n'
        )
        mod = _load("ds7", src, tmp_path)
        cls = mod.module_dict["chars"]
        assert _succeeds("phrase", cls, chars("aaa"), module=mod)
        assert _succeeds("phrase", cls, chars(""), module=mod)
        assert not _succeeds("phrase", cls, chars("aab"), module=mod)

    def test_phrase2_dcg_with_args_string(self, tmp_path):
        """DCG with args extracts characters from string input."""
        # nv
        src = 'tok(_t) >> ([_t])\n'
        mod = _load("ds8", src, tmp_path)
        cls = mod.module_dict["tok"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), chars("x"), module=mod):
            results.append(deref(v))
        assert results == [mint("x")]

    def test_phrase2_inline_goal_string(self, tmp_path):
        """DCG with inline goal on string input."""
        # nv
        src = '-double_quotes(atom)\nvowel(_v) >> ([_v], {in_(_v, ["a", "e", "i", "o", "u"])})\n'
        mod = _load("ds9", src, tmp_path)
        cls = mod.module_dict["vowel"]
        v = Var()
        results = []
        for _ in call("phrase", _nt(cls, v), chars("e"), module=mod):
            results.append(deref(v))
        assert results == [mint("e")]
        # Consonant should fail
        results2 = []
        for _ in call("phrase", _nt(cls, v), chars("b"), module=mod):
            results2.append(deref(v))
        assert results2 == []

    def test_list_input_still_works(self, tmp_path):
        """List input is unchanged (no regression)."""
        # nv
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("ds10", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, [mint("h"), mint("i")], module=mod)


# ── P3-1 Task 5 audit: cons-rule retirement vs the DCG strings-as-lists ──────
#
# §1b retires ONE specific rule: the C ``do_unify`` cross-type branch that
# made a bare ``str`` unify with a plain ``list`` via element-wise char
# comparison (``_variables.c``'s "String <-> List unification" block, now
# deleted). DCG's string support (``TestDCGStringInput``/``TestStringTerminals``
# above) is a DIFFERENT, older, and still-intentional contract (Phase 2 Tasks
# 13/14, "Liskov strings-as-lists"): ``phrase``'s difference-list plumbing
# (``_head_list_unify_input`` / ``_body_star_unify`` in
# ``clausal/logic/runtime/list_unify.py`` / ``body_star_unify.py``) natively
# destructures a bare ``str`` target itself — it never calls the retired
# ``do_unify`` cross-type branch DIRECTLY, so most of that machinery is
# unchanged by this task.
#
# The audit DID find one real, load-bearing reliance: ``phrase/2``'s "List
# must be consumed entirely" contract hardcoded the Python list ``[]`` as the
# "nothing left" sentinel for the rule's final state var. When ``List`` was a
# str, the rule's terminal matching correctly produces an empty STR residue
# (``""``, not ``[]``) — and pre-retirement, ``unify("", [], trail)`` secretly
# succeeded via the retired rule's degenerate empty-vs-empty case. Once that
# rule is gone, ``"" != []`` (str unifies with str, lists with lists — no
# empty-case exception), so EVERY ``phrase/2`` call over a non-empty str input
# broke (9 tests in ``TestDCGStringInput``/``TestStringTerminals`` above).
# Fixed in ``clausal/logic/builtins/dcg.py`` (``_empty_remainder_like``):
# the sentinel now matches ``list_val``'s own type (``""`` for str, ``b""``
# for bytes, ``[]`` otherwise), restoring the Liskov strings-as-lists
# contract WITHOUT resurrecting the retired cross-type unify rule.
#
# The two tests below are the plan's requested pair: an explicit-char-list
# regression pin, and a "bare str where a [char] list is expected" failure —
# for the one shape in ``phrase/2,3`` that IS a hard char-list requirement:
# the RULE reference itself (first argument) must be a nonterminal (a
# zero/N-ary term-instance/class), not a bare str. That predates this task,
# but is the accurate, honest answer to "what fails cleanly here after
# retirement" for the RULE-reference argument specifically (the LIST
# argument keeps accepting str natively, per the fix above).


class TestConsRuleRetirementDCGAudit:
    def test_phrase_over_explicit_char_list_still_works(self, tmp_path):
        # nv — pin: an explicit char-list caller is untouched by the
        # retirement (it was never going through the retired str~list
        # branch — list-vs-list unify is unaffected).
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("t5_dcg1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, [mint("h"), mint("i")], module=mod)
        assert not _succeeds("phrase", cls, [mint("h"), mint("o")], module=mod)

    def test_phrase_bare_atom_rule_reference_names_the_nonterminal(self, tmp_path):
        # nv — FLIPPED 2026-09-24 (operator ruling S): this pinned that a
        # bare atom standing in for the RULE does NOT resolve.  A bare
        # predicate name in data position is now its PLAIN atom, so the atom
        # is exactly what source ``phrase(hi, L)`` passes; it names hi//0 and
        # resolves in the calling module like call/N.
        src = '-double_quotes(atom)\nhi >> (["h", "i"])\n'
        mod = _load("t5_dcg2", src, tmp_path)
        assert _succeeds("phrase", "hi", ["h", "i"], module=mod)
        assert not _succeeds("phrase", "hi", ["h", "o"], module=mod)
        # FLIPPED 2026-09-25 -- operator ruling 2 ("like Scryer"): an unknown
        # nonterminal N//0 raises existence_error(procedure, N/2); it used to
        # fail silently.
        from clausal import cell_args
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            _succeeds("phrase", "nosuch", ["h", "i"], module=mod)
        assert tuple(cell_args(cell_args(cell_args(exc.value.term)[0])[1])) == ("nosuch", 2)


# ── String / bytes terminals in rule bodies (R3) ─────────────────────────────


class TestStringTerminals:
    """R3: a ``str``/``bytes`` constant terminal in a DCG body.

    Standard Prolog treats ``"abc"`` as a terminal sequence; under the
    strings-as-lists rule it should expand the same as the list form.
    """

    def test_string_terminal_string_input(self, tmp_path):
        src = '-double_quotes(atom)\nhi >> ("hi")\n'
        mod = _load("st1", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, chars("hi"), module=mod)
        assert not _succeeds("phrase", cls, chars("ho"), module=mod)

    def test_string_terminal_list_input(self, tmp_path):
        """A string terminal also matches a char-list caller (strings-as-lists).

        THE FLIP (spec §6.2): the chars of "hi" are the ATOMS ('h', 'i').
        The pre-flip list of 1-char STRINGS is a different term (a list of two
        one-character strings) and no longer matches.
        """
        src = '-double_quotes(atom)\nhi >> ("hi")\n'
        mod = _load("st2", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, [char_atom("h"), char_atom("i")], module=mod)
        assert not _succeeds("phrase", cls, [chars("h"), chars("i")], module=mod)

    def test_string_terminal_in_sequence(self, tmp_path):
        """String terminal threaded between other terminals."""
        src = '-double_quotes(atom)\ngreet >> ("he", ["l"], "lo")\n'
        mod = _load("st3", src, tmp_path)
        cls = mod.module_dict["greet"]
        assert _succeeds("phrase", cls, chars("hello"), module=mod)

    def test_bytes_terminal(self, tmp_path):
        src = "-double_quotes(atom)\nhi >> (b\"hi\")\n"
        mod = _load("st4", src, tmp_path)
        cls = mod.module_dict["hi"]
        assert _succeeds("phrase", cls, b"hi", module=mod)


# ── call//1 — variable nonterminal bodies (R4) ───────────────────────────────


class TestCallNonterminal:
    """R4: a bare logic-variable DCG body invokes the bound nonterminal."""

    def test_call_variable_nonterminal(self, tmp_path):
        src = (
            "-double_quotes(atom)\n-module(x, [run(G, S0, S), greeting(S0, S)])\n"
            'greeting >> (["hello"])\n'
            "run(_g) >> (_g)\n"
        )
        mod = _load("cn1", src, tmp_path)
        run = mod.module_dict["run"]
        greeting = mod.module_dict["greeting"]
        assert _succeeds("phrase", _nt(run, greeting), [mint("hello")], module=mod)
        assert not _succeeds("phrase", _nt(run, greeting), [mint("bye")], module=mod)


# ── Prolog import round-trip of {..} embedded goals ──────────────────────────


class TestPrologImportInlineGoals:
    """End-to-end: Prolog DCG rules with ``{Goal}`` bodies import + run.

    Regression: ``prolog_to_clausal`` emitted the inline goal WITHOUT braces, so
    a single goal was lowered as a non-terminal (silent corruption) and a
    conjunction body failed to load (``Unsupported DCG body element``). The
    translator now emits ``{Goal}`` / ``{(A, B, ...)}``.
    """

    def _translate_and_load(self, name, prolog_src, tmp_path):
        from clausal.tools.prolog_to_clausal import prolog_to_clausal

        clausal_src = prolog_to_clausal(prolog_src)
        # Translator Titlecases predicate names, so the nonterminals become
        # ``Count`` / ``Bounded`` in the loaded module.
        return _load(name, clausal_src + "\n", tmp_path), clausal_src

    def test_single_goal_body_roundtrip(self, tmp_path):
        # nv
        mod, src = self._translate_and_load(
            "rt_count", "count(N) --> [x], {N is 1}.\n", tmp_path
        )
        # A single {Goal} must be emitted braced, not as a bare non-terminal.
        assert "{eval_(1, N)}" in src
        cls = mod.module_dict["count"]
        # [x] is an ATOM terminal; query with the module's interned ``x`` atom.
        xatom = mod.module_dict["x"]
        n = Var()
        results = [deref(n) for _ in call("phrase", _nt(cls, n), [xatom], module=mod)]
        assert results == [1]

    def test_conjunction_body_roundtrip(self, tmp_path):
        # nv
        mod, src = self._translate_and_load(
            "rt_bounded", "bounded(D) --> [D], {D >= 0, D =< 9}.\n", tmp_path
        )
        # A conjunction body is emitted as the parenthesised form ``{(A, B)}``.
        assert "{(D >= 0, D <= 9)}" in src
        cls = mod.module_dict["bounded"]
        # In range: accepted.
        assert _succeeds("phrase", _nt(cls, Var()), [5], module=mod)
        # BOTH guards enforced: [12] rejected (the >= 0 / <= 9 pair).
        assert not _succeeds("phrase", _nt(cls, Var()), [12], module=mod)
        assert not _succeeds("phrase", _nt(cls, Var()), [-1], module=mod)
