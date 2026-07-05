"""Tests for clausal.modules.reflection — matching reified terms from Clausal.

Phase 2 of implementation_plans/clausal-ast-reflection-and-structural-matching.md:
``-import_from(reflection, [...])`` exposes the reified vocabulary plus
enumeration/destructuring builtins, so linters and matchers are written in
Clausal itself.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "examples",
)


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


_MATCHERS = """\
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, clause_body, goal_functor, reified_subterm,
    Clause, Goal, Variable, Atom, Escape,
])

HeadName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

DirectHeadName(SRC, NAME) <- reified_clause(SRC, Clause(Goal(NAME, _, _), _, _))

FactName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, []),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

CalledPredicate(SRC, NAME, ARITY) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, GOALS),
    GOAL in GOALS,
    goal_functor(GOAL, NAME, ARITY)
)

DefinedName(SRC, NAME) <- HeadName(SRC, NAME)

UndefinedCall(SRC, NAME) <- (
    CalledPredicate(SRC, NAME, _),
    not DefinedName(SRC, NAME)
)

EscapeCode(SRC, CODE) <- (
    reified_item(SRC, ITEM),
    reified_subterm(ITEM, Escape(CODE, _, _))
)

FileHeadName(PATH, NAME) <- (
    reified_file_item(PATH, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

# ── DCG construction matching over a body's goal list (phase 3) ──────────────

edge_goal >> ([Goal("Edge", _, _)])
any_goal >> ([_])
any_goals >> ([])
any_goals >> (any_goal, any_goals)

starts_with_edge >> (edge_goal, any_goals)

StartsWithEdge(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _),
    clause_body(CLAUSE, GOALS),
    phrase(starts_with_edge, GOALS)
)
"""

_TARGET = """\
Edge(1, 2),
Edge(2, 3),

Connected(X, Y) <- Edge(X, Y)
Connected(X, Y) <- (Edge(X, Z), Connected(Z, Y), Ghost(Z))

Size(L, N) <- (N is ++len(L))
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("reflection") / "matchers.clausal"
    path.write_text(_MATCHERS)
    mod = _load_module("_test_reflection_matchers", str(path))
    return mod.__dict__["$module"]


def _all_bindings(functor, *args, module):
    """Call with a trailing Var, collect every deref'd binding."""
    out = Var()
    results = []
    for _ in call(functor, *args, out, module=module):
        results.append(deref(out))
    return results


class TestEnumeration:
    def test_head_names_enumerate_all_clauses(self, matchers):
        names = _all_bindings("HeadName", _TARGET, module=matchers)
        assert names == ["Edge", "Edge", "Connected", "Connected", "Size"]

    def test_direct_pattern_matching_without_accessors(self, matchers):
        names = _all_bindings("DirectHeadName", _TARGET, module=matchers)
        assert set(names) == {"Edge", "Connected", "Size"}

    def test_fact_names_only_facts(self, matchers):
        names = _all_bindings("FactName", _TARGET, module=matchers)
        assert names == ["Edge", "Edge"]


class TestCallGraph:
    def test_called_predicates_with_arity(self, matchers):
        name, arity = Var(), Var()
        found = set()
        for _ in call("CalledPredicate", _TARGET, name, arity, module=matchers):
            found.add((deref(name), deref(arity)))
        assert ("Edge", 2) in found
        assert ("Connected", 2) in found
        assert ("Ghost", 1) in found

    def test_undefined_call_lint_finds_ghost(self, matchers):
        names = _all_bindings("UndefinedCall", _TARGET, module=matchers)
        assert set(names) == {"Ghost"}


class TestEscapes:
    def test_escape_code_found_by_subterm_walk(self, matchers):
        codes = _all_bindings("EscapeCode", _TARGET, module=matchers)
        assert codes == ["len(L)"]


class TestFiles:
    def test_file_head_names_from_real_example(self, matchers):
        path = os.path.join(EXAMPLES_DIR, "graph.clausal")
        names = _all_bindings("FileHeadName", path, module=matchers)
        assert "Path" in names
        assert names.count("Edge") == 7


class TestDcgMatching:
    def test_dcg_matches_bodies_starting_with_edge_call(self, matchers):
        names = _all_bindings("StartsWithEdge", _TARGET, module=matchers)
        assert names == ["Connected", "Connected"]


class TestPythonSide:
    def test_module_exports_vocabulary_and_builtins(self):
        from clausal.modules import reflection

        for name in (
            "reified_item", "reified_clause", "reified_file_item",
            "clause_head", "clause_body", "goal_functor", "reified_subterm",
            "Clause", "Goal", "Variable", "Atom", "Escape",
        ):
            assert hasattr(reflection, name), name
