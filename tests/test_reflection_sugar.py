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
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


_MATCHERS = """\
-implicit_atoms
-import_from(reflection, [
    reified_item, reified_clause, reified_subterm,
    clause_body, goal_functor,
    Clause, Goal, Variable,
])

ShapeXY(SRC) <- reified_clause(SRC, MyPred(A, B) <- (Goalx(A), Goaly(B)))

CaptureFirstArg(SRC, A) <- reified_clause(SRC, MyPred(A, _) <- GOALS)

CaptureBody(SRC, GOALS) <- reified_clause(SRC, MyPred(_, _) <- GOALS)

FactWithAtom(SRC) <- reified_clause(SRC, Tagged(_, ok) <- True)

OperatorBody(SRC) <- reified_clause(SRC, Positive(A) <- (A > 0))

NestedCompound(SRC) <- reified_clause(SRC, Holds(State(A)) <- Check(A))

NegationBody(SRC) <- reified_clause(SRC, Free(A) <- (not Busy(A)))

# Sugar goal inside a multi-goal body (exercises conjunction recursion).
TwoGoalBody(SRC) <- (
    reified_clause(SRC, MyPred(_, _) <- GOALS),
    GOALS is [_, _]
)

# Outside reflection arguments the arrow stays a runtime Predicate node.
Foo(0),
Bar(0),
KeepRaw(T) <- (T is (Foo(A) <- Bar(A)))
"""

_TARGET = """\
MyPred(X, Y) <- (Goalx(X), Goaly(Y))
Tagged(1, ok),
Positive(N) <- (N > 0)
Holds(State(W)) <- Check(W)
Free(Q) <- (not Busy(Q))
"""

_CROSSED = "MyPred(X, Y) <- (Goalx(Y), Goaly(X))\n"
_RENAMED = "MyPred(P, Q) <- (Goalx(P), Goaly(Q))\n"
_NEGATIVE = "Positive(N) <- (N < 0)\n"
_STRING_NOT_ATOM = 'Tagged(1, "ok"),\n'


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
        assert _succeeds("ShapeXY", _TARGET, module=matchers)

    def test_matches_alpha_renamed_clause(self, matchers):
        assert _succeeds("ShapeXY", _RENAMED, module=matchers)

    def test_rejects_crossed_variables(self, matchers):
        assert not _succeeds("ShapeXY", _CROSSED, module=matchers)


class TestCapture:
    def test_pattern_variable_captures_reified_variable(self, matchers):
        from clausal.reflection import Variable

        captured = Var()
        for _ in call("CaptureFirstArg", _TARGET, captured, module=matchers):
            break
        value = deref(captured)
        assert isinstance(value, Variable)
        assert value.name == "X"

    def test_variable_body_captures_goal_list(self, matchers):
        from clausal.reflection import Goal

        goals = Var()
        for _ in call("CaptureBody", _TARGET, goals, module=matchers):
            break
        value = deref(goals)
        assert isinstance(value, list)
        assert [g.name for g in value] == ["Goalx", "Goaly"]
        assert all(isinstance(g, Goal) for g in value)


class TestPatternForms:
    def test_fact_pattern_with_atom_argument(self, matchers):
        assert _succeeds("FactWithAtom", _TARGET, module=matchers)

    def test_atom_pattern_rejects_string_literal(self, matchers):
        assert not _succeeds("FactWithAtom", _STRING_NOT_ATOM, module=matchers)

    def test_operator_body_pattern(self, matchers):
        assert _succeeds("OperatorBody", _TARGET, module=matchers)

    def test_operator_body_rejects_different_operator(self, matchers):
        assert not _succeeds("OperatorBody", _NEGATIVE, module=matchers)

    def test_nested_compound_argument(self, matchers):
        assert _succeeds("NestedCompound", _TARGET, module=matchers)

    def test_negation_body_pattern(self, matchers):
        assert _succeeds("NegationBody", _TARGET, module=matchers)

    def test_sugar_goal_inside_conjunction(self, matchers):
        assert _succeeds("TwoGoalBody", _TARGET, module=matchers)


class TestBoundary:
    def test_arrow_outside_reflection_args_stays_predicate_node(self, matchers):
        from clausal.pythonic_ast.nodes import Predicate

        term = Var()
        for _ in call("KeepRaw", term, module=matchers):
            break
        assert isinstance(deref(term), Predicate)
