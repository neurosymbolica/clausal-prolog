"""Regression tests: numeric literal in a ruled-clause head must unify with a
caller Var (output mode), not just match an already-equal argument (input mode).

Bug (2026-06-23): a numeric (int/float) literal in the head of a `<-` clause was
compiled to a Python `MatchValue` literal pattern (`case [_v0, 20000]`), which
only matches when the deref'd arg already equals the literal. An unbound Var
caller silently failed the match → no solution. String/atom literals and bare
facts took the capture+unify path and worked, which is why existing tests missed
this. See todo/numeric-head-literal-unification-bug.md.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(scope="module")
def mod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "numeric_head_literal.clausal"
    )
    return _load_module("numeric_head_literal_mod", fixture).__dict__["$module"]


def _collect(name, out_vars, *args, module):
    """Run a query and snapshot the out_vars' bindings inside the solution loop
    (bindings are undone once the generator resumes/exits)."""
    snapshots = []
    for _ in call(name, *args, module=module):
        snapshots.append(tuple(deref(v) for v in out_vars))
    return snapshots


def _count(name, *args, module):
    return sum(1 for _ in call(name, *args, module=module))


class TestNumericHeadLiteralVarBinding:
    def test_int_literal_head_query_as_var(self, mod):
        F = Var()
        assert _collect("fine_int", [F], 50, F, module=mod) == [(20000,)]

    def test_float_literal_head_query_as_var(self, mod):
        F = Var()
        assert _collect("fine_flt", [F], 50, F, module=mod) == [(3.5,)]

    def test_int_literal_first_arg_query_as_var(self, mod):
        F = Var()
        assert _collect("first_lit", [F], F, 50, module=mod) == [(20000,)]

    def test_int_literal_middle_arg_query_as_var(self, mod):
        M, R = Var(), Var()
        assert _collect("mid_lit", [M, R], 3, M, R, module=mod) == [(7, 4)]

    def test_int_literal_trivial_body(self, mod):
        X = Var()
        assert _collect("triv", [X], 50, X, module=mod) == [(99,)]


class TestSingletonHeadLiteralVarBinding:
    """True/False/None head literals share the bug class: MatchSingleton matches
    by identity, so an unbound Var caller never binds in output mode."""

    def test_true_literal_head_query_as_var(self, mod):
        F = Var()
        assert _collect("flag_t", [F], 5, F, module=mod) == [(True,)]

    def test_false_literal_head_query_as_var(self, mod):
        F = Var()
        assert _collect("flag_f", [F], 5, F, module=mod) == [(False,)]

    def test_none_literal_head_query_as_var(self, mod):
        F = Var()
        assert _collect("flag_n", [F], 5, F, module=mod) == [(None,)]

    def test_true_literal_input_mode(self, mod):
        assert _count("flag_t", 5, True, module=mod) == 1

    def test_true_literal_wrong_value_fails(self, mod):
        assert _count("flag_t", 5, False, module=mod) == 0


class TestNumericHeadLiteralInputMode:
    """Input mode (caller supplies the literal directly) must still work."""

    def test_int_literal_given_directly(self, mod):
        assert _count("fine_int", 50, 20000, module=mod) == 1

    def test_int_literal_wrong_value_fails(self, mod):
        # caller supplies a non-matching literal → no solution
        assert _count("fine_int", 50, 19999, module=mod) == 0

    def test_guard_still_filters(self, mod):
        # DAYS >= 40 must still fail for DAYS < 40 even in var-output mode
        F = Var()
        assert _count("fine_int", 10, F, module=mod) == 0


class TestControlsStillWork:
    def test_bare_fact_query_as_var(self, mod):
        F = Var()
        assert _collect("fact_int", [F], 50, F, module=mod) == [(20000,)]

    def test_string_literal_head_query_as_var(self, mod):
        S = Var()
        assert _collect("elig_dq", [S], "alice", S, module=mod) == [("yes",)]
