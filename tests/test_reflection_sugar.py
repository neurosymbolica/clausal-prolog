"""Tests for arrow-pattern sugar: (HEAD <- BODY) as a match pattern.

Goal expansion rewrites ``(HEAD <- BODY)`` expressions appearing in the
argument positions of the reflection builtins into the equivalent reified
vocabulary pattern at compile time.  Pattern variables remain the matcher
clause's own variables, so unification against the ground reified terms
gives capture and sharing semantics.

Outside reflection-builtin arguments the arrow expression keeps its
existing meaning: a runtime ``Predicate`` node (the assertz write-side
currency).
"""

import pytest

from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


_MATCHERS = """\
-private([ok])
-import_from(reflection, [
    reified_item, reified_clause, reified_subterm,
    clause_body, goal_functor,
    Clause, Goal, Variable,
])

shape_xy(SRC) <- reified_clause(SRC, my_pred(A, B) <- (goalx(A), goaly(B)))

capture_first_arg(SRC, A) <- reified_clause(SRC, my_pred(A, _) <- GOALS)

capture_body(SRC, GOALS) <- reified_clause(SRC, my_pred(_, _) <- GOALS)

fact_with_atom(SRC) <- reified_clause(SRC, tagged(_, ok) <- True)

operator_body(SRC) <- reified_clause(SRC, positive(A) <- (A > 0))

nested_compound(SRC) <- reified_clause(SRC, holds(state(A)) <- check(A))

negation_body(SRC) <- reified_clause(SRC, free(A) <- (not busy(A)))

# Sugar goal inside a multi-goal body (exercises conjunction recursion).
two_goal_body(SRC) <- (
    reified_clause(SRC, my_pred(_, _) <- GOALS),
    GOALS is [_, _]
)

# Outside reflection arguments the arrow stays a runtime Predicate node.
foo(0),
bar(0),
keep_raw(T) <- (T is (foo(A) <- bar(A)))
"""

_TARGET = """\
my_pred(X, Y) <- (goalx(X), goaly(Y))
tagged(1, ok),
positive(N) <- (N > 0)
holds(state(W)) <- check(W)
free(Q) <- (not busy(Q))
"""

_CROSSED = "my_pred(X, Y) <- (goalx(Y), goaly(X))\n"
_RENAMED = "my_pred(P, Q) <- (goalx(P), goaly(Q))\n"
_NEGATIVE = "positive(N) <- (N < 0)\n"
# THE FLIP (spec §7): ``"ok"`` is an ATOM under the default
# ``-double_quotes(atom)`` -- the source has to DECLARE the chars mode for
# its ``"ok"`` to be the string this negative case is about.
_STRING_NOT_ATOM = '-double_quotes(chars)\ntagged(1, "ok"),\n'


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("reflection_sugar") / "sugar_matchers.clausal"
    path.write_text(_MATCHERS)
    mod = _load_module("_test_reflection_sugar", str(path))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    return any(True for _ in call(functor, *args, module=module))


class TestShapeMatching:
    def test_matches_target_clause(self, matchers):
        assert _succeeds("shape_xy", chars(_TARGET), module=matchers)

    def test_matches_alpha_renamed_clause(self, matchers):
        assert _succeeds("shape_xy", chars(_RENAMED), module=matchers)

    def test_rejects_crossed_variables(self, matchers):
        assert not _succeeds("shape_xy", chars(_CROSSED), module=matchers)


class TestCapture:
    def test_pattern_variable_captures_reified_variable(self, matchers):
        from clausal.reflection import Variable, is_v, vfield

        captured = Var()
        for _ in call("capture_first_arg", chars(_TARGET), captured, module=matchers):
            break
        value = deref(captured)
        assert is_v(value, Variable)
        assert vfield(value, "name") == "X"

    def test_variable_body_captures_goal_list(self, matchers):
        from clausal.reflection import Goal, is_v, vfield

        goals = Var()
        for _ in call("capture_body", chars(_TARGET), goals, module=matchers):
            break
        value = deref(goals)
        assert isinstance(value, list)
        assert [vfield(g, "name") for g in value] == ["goalx", "goaly"]
        assert all(is_v(g, Goal) for g in value)


class TestPatternForms:
    def test_fact_pattern_with_atom_argument(self, matchers):
        assert _succeeds("fact_with_atom", chars(_TARGET), module=matchers)

    def test_atom_pattern_rejects_string_literal(self, matchers):
        assert not _succeeds("fact_with_atom", chars(_STRING_NOT_ATOM), module=matchers)

    def test_operator_body_pattern(self, matchers):
        assert _succeeds("operator_body", chars(_TARGET), module=matchers)

    def test_operator_body_rejects_different_operator(self, matchers):
        assert not _succeeds("operator_body", chars(_NEGATIVE), module=matchers)

    def test_nested_compound_argument(self, matchers):
        assert _succeeds("nested_compound", chars(_TARGET), module=matchers)

    def test_negation_body_pattern(self, matchers):
        assert _succeeds("negation_body", chars(_TARGET), module=matchers)

    def test_sugar_goal_inside_conjunction(self, matchers):
        assert _succeeds("two_goal_body", chars(_TARGET), module=matchers)


class TestBoundary:
    def test_arrow_outside_reflection_args_stays_predicate_node(self, matchers):
        from clausal.pythonic_ast.nodes import Predicate

        term = Var()
        for _ in call("keep_raw", term, module=matchers):
            break
        assert isinstance(deref(term), Predicate)
