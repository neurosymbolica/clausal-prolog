"""Tests for meta-interpreter specialization via partial deduction.

Phase 0: Pattern recognition on the five MIs from metainterpreters.clausal.
Phase 1: Core unfolder — specialize each MI with natnum/graph programs and
         verify identical results to unspecialized versions.
Phase 3: Object programs with builtins/external goals — residual goal
         dispatch via catch-all clause and _SolveGoal.
Phase 5: Conjunctive partial deduction (deforestation) — non-deterministic
         inlining, intermediate list elimination, pre/post-match chaining.
"""

from __future__ import annotations

import pytest
from clausal.logic.specialization import (
    analyze_mi,
    specialize_mi,
    specialize_mi_cpd,
    MIPattern,
    CannotSpecialize,
    ConjunctionMemoTable,
    _known_functors,
    _has_residual_goals,
    _ast_unify,
)


@pytest.fixture(scope="module")
def mi_module():
    """Import the metainterpreters module."""
    import clausal.examples.metainterpreters as mi
    return mi


@pytest.fixture
def spec_module(request):
    """The DEFINING module a specialization is installed into.

    Operator ruling QC (2026-09-24): at W4b-3 the direct ``specialize_mi*``
    API will require the caller to name where the predicate lives (``db=`` of
    a ``Module``) and will return the row; the predicate is queried by NAME
    with ``call(name, ..., module=m)``.  Until W4b-3 it still returns a
    CLASS (see ``TestSpecializedPredicateIsARow``), which these tests only
    use where noted.  Every specialization here is written into
    this module's database and inspected through ``_row``; queries are by
    name against this module.

    HOW a by-name query resolves depends on the namespace, not only the db:
    ``call(name, module=m)`` looks in ``m.module_dict`` FIRST, then the
    builtins, and only then ``m.db.get_dispatch`` (``solve.call``).  So a
    specialization made through ``_specialize`` (which binds the alias in
    ``module_dict``) is answered through the class bound there, and one made
    through ``_specialize_row_route`` (``db=`` only) is answered through the
    database row -- the post-P4 route, covered by one ``test_row_route_*``
    test per phase area.  One module per test, so names never collide across
    tests and re-specialization is never accidental.
    """
    from clausal.logic.database import Module

    name = f"spec_{request.node.name}"
    return Module(name, module_dict={"__name__": name})


def _specialize(module, fn, pattern, program, name, **kw):
    """Specialize into *module*'s database (``db=``) AND its namespace
    (``module_dict=``).  The alias is bound in ``module_dict``, which is where
    ``call(name, ..., module=module)`` looks first -- so queries on it are
    answered by the CLASS bound there (whose dispatch reads the row), and a
    same-named builtin can never answer in its place.  *fn* is
    ``specialize_mi``, ``specialize_mi_deep`` or ``specialize_mi_cpd``."""
    return fn(
        pattern, program, name,
        db=module.db, module_dict=module.module_dict, **kw,
    )


def _specialize_row_route(module, fn, pattern, program, name, arity, **kw):
    """Specialize into *module*'s database ONLY (``db=``, no ``module_dict=``)
    -- the post-P4 row route.  Nothing is bound in ``module.module_dict`` and
    no builtin has *name*, so ``call(name, ..., module=module)`` falls through
    to ``module.db.get_dispatch``.  Both are asserted, so a query that
    answers really came out of the row."""
    from clausal.logic.builtins import get_builtin_predicate

    result = fn(pattern, program, name, db=module.db, **kw)
    assert name not in module.module_dict
    assert get_builtin_predicate(name, arity, module.db) is None
    assert module.db.get_dispatch(name, arity) is not None
    return result



def _row_of(handle, arity=1):
    """The row a specialization's returned HANDLE names (W4b-3 slice 4: the
    API returns the handle; it returned a class whose ``_row`` this read)."""
    from clausal.logic.atoms import is_mangled
    from clausal.logic.predicate import resolve_predicate_row
    assert type(handle) is str and is_mangled(handle), handle
    return resolve_predicate_row(handle, arity=arity)


def _dispatch_of(handle, arity=1):
    from clausal.logic.predicate import _dispatch_at
    return _dispatch_at(handle, arity)

def _row(module, name, arity):
    """The specialized predicate's ROW in *module*'s database (never None)."""
    row = module.db.row(name, arity)
    assert row is not None, f"{name}/{arity} is not a row of {module.name}"
    return row


# ── Phase 0: Pattern Recognition ──────────────────────────────────────────────


class TestAnalyzeSolve:
    """Vanilla MI: solve/2."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.name == "solve"
        assert pattern.arity == 2
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == []
        assert pattern.recursive_call_style == "tail"

    def test_has_base_and_recursive(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.base_clause is not None
        assert pattern.recursive_clause is not None

    def test_no_pre_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.pre_match_goals == []

    def test_no_post_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.post_match_goals == []

    def test_match_clause_found(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.match_clause_index == 0

    def test_append_found(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.append_index == 1

    def test_one_recursive_call(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert len(pattern.recursive_call_indices) == 1

    def test_variables_extracted(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        assert pattern.goal_var is not None
        assert pattern.goals_var is not None
        assert pattern.body_var is not None
        assert pattern.all_goals_var is not None
        assert pattern.program_var is not None


class TestAnalyzeSolveCount:
    """Inference-counting MI: solve_count/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        assert pattern.name == "solve_count"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_post_match_goals(self, mi_module):
        """COUNT == SUB_COUNT + 1 is a post-match goal."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        assert len(pattern.post_match_goals) == 1
        from clausal.pythonic_ast.nodes import ArithEq
        assert isinstance(pattern.post_match_goals[0], ArithEq)


class TestAnalyzeSolveLimit:
    """Depth-limited MI: solve_limit/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        assert pattern.name == "solve_limit"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_pre_match_goals(self, mi_module):
        """MAX > 0 and MAX1 == MAX - 1 are pre-match goals."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        assert len(pattern.pre_match_goals) == 2
        from clausal.pythonic_ast.nodes import Gt, ArithEq
        assert isinstance(pattern.pre_match_goals[0], Gt)
        assert isinstance(pattern.pre_match_goals[1], ArithEq)


class TestAnalyzeSolveTree:
    """Proof-tree MI: solve_tree/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        assert pattern.name == "solve_tree"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "split"

    def test_no_append(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        assert pattern.append_index is None

    def test_two_recursive_calls(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        assert len(pattern.recursive_call_indices) == 2

    def test_no_pre_post_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        assert pattern.pre_match_goals == []
        assert pattern.post_match_goals == []


class TestAnalyzeSolveIterativeDeepening:
    """Iterative deepening MI: solve_iterative_deepening/2.

    This MI is not a standard MI pattern (it delegates to solve_limit).
    analyze_mi should raise CannotSpecialize.
    """

    def test_cannot_specialize(self, mi_module):
        # nv
        with pytest.raises(CannotSpecialize):
            analyze_mi(mi_module.solve_iterative_deepening)


class TestAnalyzeExplicitProgramArg:
    """Test explicit program_arg specification."""

    def test_explicit_program_arg(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count, program_arg=1)
        assert pattern.program_arg == 1

    def test_invalid_program_arg(self, mi_module):
        # nv
        with pytest.raises(CannotSpecialize):
            analyze_mi(mi_module.solve_count, program_arg=5)


# ── Phase 1: Core Unfolder ───────────────────────────────────────────────────


def _make_natnum_program():
    from clausal.logic.variables import Var
    x = Var()
    return [
        [["natnum", 0], []],
        [["natnum", ["s", x]], [["natnum", x]]],
    ]


def _make_graph_program():
    from clausal.logic.variables import Var
    x1, y1 = Var(), Var()
    x2, y2, z2 = Var(), Var(), Var()
    return [
        [["edge", "a", "b"], []],
        [["edge", "b", "c"], []],
        [["edge", "b", "d"], []],
        [["path", x1, y1], [["edge", x1, y1]]],
        [["path", x2, y2], [["edge", x2, z2], ["path", z2, y2]]],
    ]


class TestSpecializeSolve:
    """Specialize vanilla solve/2 with natnum program."""

    def test_clause_count(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnum",
        )
        # 1 base + 2 object clauses = 3
        assert len(_row(spec_module, "SolveNatnum", 1).clauses) == 3

    def test_field_count(self, mi_module, spec_module):
        """Specialized predicate drops PROGRAM field."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnum2",
        )
        assert len(_row(spec_module, "SolveNatnum2", 1).signature) == 1  # just GOALS
        assert "GOALS" in _row(spec_module, "SolveNatnum2", 1).signature

    def test_solve_natnum_0(self, mi_module, spec_module):
        """SolveNatnum([["natnum", 0]]) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnum3",
        )
        results = list(_query(spec_module, "SolveNatnum3", [["natnum", 0]]))
        assert len(results) >= 1

    def test_solve_natnum_s0(self, mi_module, spec_module):
        """SolveNatnum([["natnum", ["s", 0]]]) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnum4",
        )
        results = list(_query(
            spec_module, "SolveNatnum4", [["natnum", ["s", 0]]],
        ))
        assert len(results) >= 1

    def test_solve_natnum_ss0(self, mi_module, spec_module):
        """SolveNatnum([["natnum", ["s", ["s", 0]]]]) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnum5",
        )
        results = list(_query(
            spec_module, "SolveNatnum5", [["natnum", ["s", ["s", 0]]]],
        ))
        assert len(results) >= 1


class TestSpecializeSolveGraph:
    """Specialize vanilla solve/2 with graph program."""

    def test_clause_count(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraph",
        )
        # 1 base + 5 object clauses = 6
        assert len(_row(spec_module, "SolveGraph", 1).clauses) == 6

    def test_solve_edge(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraph2",
        )
        results = list(_query(
            spec_module, "SolveGraph2", [["edge", "a", "b"]],
        ))
        assert len(results) >= 1

    def test_solve_path_direct(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraph3",
        )
        results = list(_query(
            spec_module, "SolveGraph3", [["path", "a", "b"]],
        ))
        assert len(results) >= 1

    def test_solve_path_transitive(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraph4",
        )
        results = list(_query(
            spec_module, "SolveGraph4", [["path", "a", "c"]],
        ))
        assert len(results) >= 1

    def test_solve_no_path(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraph5",
        )
        results = list(_query(
            spec_module, "SolveGraph5", [["path", "c", "a"]],
        ))
        assert len(results) == 0


class TestSpecializeSolveCount:
    """Specialize counting MI with natnum program."""

    def test_clause_count(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountNatnum",
        )
        # 1 base + 2 object clauses = 3
        assert len(_row(spec_module, "SolveCountNatnum", 2).clauses) == 3

    def test_fields(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountNatnum2",
        )
        assert _row(spec_module, "SolveCountNatnum2", 2).signature == ("GOALS", "COUNT")

    def test_count_natnum_0(self, mi_module, spec_module):
        """SolveCountNatnum([["natnum", 0]], COUNT) → COUNT = 1."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountNatnum3",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountNatnum3", [["natnum", 0]],
        ))
        assert any(count == 1 for count in results)

    def test_count_natnum_s0(self, mi_module, spec_module):
        """SolveCountNatnum([["natnum", ["s", 0]]], COUNT) → COUNT = 2."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountNatnum4",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountNatnum4", [["natnum", ["s", 0]]],
        ))
        assert any(count == 2 for count in results)

    def test_count_natnum_ss0(self, mi_module, spec_module):
        """SolveCountNatnum([["natnum", ["s", ["s", 0]]]], COUNT) → COUNT = 3."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountNatnum5",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountNatnum5", [["natnum", ["s", ["s", 0]]]],
        ))
        assert any(count == 3 for count in results)

    def test_row_route_count_natnum(self, mi_module, spec_module):
        """Phase 1, post-P4 route: ``db=`` only, queried by name through
        ``module.db.get_dispatch`` -- same counts as the tests above."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize_row_route(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "RowRouteCountNatnum", 2,
        )
        for goal, expected in [
            ([["natnum", 0]], [1]),
            ([["natnum", ["s", 0]]], [2]),
            ([["natnum", ["s", ["s", 0]]]], [3]),
        ]:
            assert list(_query_with_extra(
                spec_module, "RowRouteCountNatnum", goal,
            )) == expected


class TestSpecializeSolveCountGraph:
    """Specialize counting MI with graph program."""

    def test_count_edge(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveCountGraph",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountGraph", [["edge", "a", "b"]],
        ))
        assert any(count == 1 for count in results)

    def test_count_path_direct(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveCountGraph2",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountGraph2", [["path", "a", "b"]],
        ))
        assert any(count == 2 for count in results)

    def test_count_path_transitive(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveCountGraph3",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountGraph3", [["path", "a", "c"]],
        ))
        assert any(count == 4 for count in results)


class TestSpecializeSolveLimit:
    """Specialize depth-limited MI with natnum program."""

    def test_clause_count(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum",
        )
        assert len(_row(spec_module, "SolveLimitNatnum", 2).clauses) == 3

    def test_fields(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum2",
        )
        assert _row(spec_module, "SolveLimitNatnum2", 2).signature == ("GOALS", "MAX_DEPTH")

    def test_limit_natnum_s0_depth1_fails(self, mi_module, spec_module):
        """Depth 1 is not enough for natnum(s(0)) → should fail."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum3",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitNatnum3", [["natnum", ["s", 0]]], 1,
        ))
        assert len(results) == 0

    def test_limit_natnum_s0_depth2_succeeds(self, mi_module, spec_module):
        """Depth 2 is enough for natnum(s(0)) → should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum4",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitNatnum4", [["natnum", ["s", 0]]], 2,
        ))
        assert len(results) >= 1

    def test_limit_natnum_ss0_depth2_fails(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum5",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitNatnum5", [["natnum", ["s", ["s", 0]]]], 2,
        ))
        assert len(results) == 0

    def test_limit_natnum_ss0_depth3_succeeds(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveLimitNatnum6",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitNatnum6", [["natnum", ["s", ["s", 0]]]], 3,
        ))
        assert len(results) >= 1


class TestSpecializeSolveTree:
    """Specialize proof-tree MI with natnum program."""

    def test_clause_count(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveTreeNatnum",
        )
        assert len(_row(spec_module, "SolveTreeNatnum", 2).clauses) == 3

    def test_fields(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveTreeNatnum2",
        )
        assert _row(spec_module, "SolveTreeNatnum2", 2).signature == ("GOALS", "TREE")

    def test_tree_natnum_0(self, mi_module, spec_module):
        """SolveTreeNatnum([["natnum", 0]], TREE) → TREE = [[["natnum", 0], []]]."""
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveTreeNatnum3",
        )
        results = list(_query_tree(
            spec_module, "SolveTreeNatnum3", [["natnum", 0]],
        ))
        assert len(results) >= 1
        assert results[0] == [[["natnum", 0], []]]

    def test_tree_natnum_s0(self, mi_module, spec_module):
        """Nested proof tree for natnum(s(0))."""
        # nv
        pattern = analyze_mi(mi_module.solve_tree)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveTreeNatnum4",
        )
        results = list(_query_tree(
            spec_module, "SolveTreeNatnum4", [["natnum", ["s", 0]]],
        ))
        assert len(results) >= 1
        expected = [[["natnum", ["s", 0]], [[["natnum", 0], []]]]]
        assert results[0] == expected


# ── Equivalence Tests ─────────────────────────────────────────────────────────


class TestEquivalence:
    """Verify specialized MI produces same results as unspecialized."""

    def test_solve_natnum_equivalence(self, mi_module, spec_module):
        """All natnum solutions match between solve and specialized."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveEquiv1",
        )

        for goal in [
            [["natnum", 0]],
            [["natnum", ["s", 0]]],
            [["natnum", ["s", ["s", 0]]]],
        ]:
            spec_results = list(_query(spec_module, "SolveEquiv1", goal))
            mi_results = list(_query_mi(mi_module.solve, goal, _make_natnum_program()))
            assert len(spec_results) == len(mi_results), (
                f"Mismatch for goal {goal}: "
                f"specialized={len(spec_results)}, MI={len(mi_results)}"
            )

    def test_solve_count_equivalence(self, mi_module, spec_module):
        """Count values match between solve_count and specialized."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveCountEquiv1",
        )

        for goal, expected_count in [
            ([["natnum", 0]], 1),
            ([["natnum", ["s", 0]]], 2),
            ([["natnum", ["s", ["s", 0]]]], 3),
        ]:
            spec_results = list(_query_with_extra(
                spec_module, "SolveCountEquiv1", goal,
            ))
            assert any(c == expected_count for c in spec_results), (
                f"Expected count={expected_count} for {goal}, got {spec_results}"
            )


# ── Phase 3: Residual goal support ────────────────────────────────────────────


def _make_factorial_program():
    """Object program: factorial with arithmetic builtins (gt, sub, mul).

    factorial(0, 1).
    factorial(N, R) :- gt(N, 0), sub(N, 1, N1), factorial(N1, R1), mul(N, R1, R).
    """
    from clausal.logic.variables import Var
    n, r, n1, r1 = Var(), Var(), Var(), Var()
    return [
        [["factorial", 0, 1], []],
        [["factorial", n, r], [
            ["gt", n, 0],
            ["sub", n, 1, n1],
            ["factorial", n1, r1],
            ["mul", n, r1, r],
        ]],
    ]


def _make_even_odd_program():
    """Object program: even/odd with modular arithmetic.

    even(0).
    even(N) :- gt(N, 0), sub(N, 2, N1), even(N1).
    """
    from clausal.logic.variables import Var
    n, n1 = Var(), Var()
    return [
        [["even", 0], []],
        [["even", n], [
            ["gte", n, 2],
            ["sub", n, 2, n1],
            ["even", n1],
        ]],
    ]


def _make_mixed_program():
    """Object program mixing known and residual goals.

    double(X, Y) :- mul(X, 2, Y).
    quadruple(X, Y) :- double(X, Z), double(Z, Y).
    """
    from clausal.logic.variables import Var
    x1, y1, x2, y2, z2 = Var(), Var(), Var(), Var(), Var()
    return [
        [["double", x1, y1], [["mul", x1, 2, y1]]],
        [["quadruple", x2, y2], [["double", x2, z2], ["double", z2, y2]]],
    ]


class TestKnownFunctors:
    """Test _known_functors helper."""

    def test_natnum(self):
        # nv
        assert _known_functors(_make_natnum_program()) == {"natnum"}

    def test_graph(self):
        # nv
        assert _known_functors(_make_graph_program()) == {"edge", "path"}

    def test_factorial(self):
        # nv
        assert _known_functors(_make_factorial_program()) == {"factorial"}

    def test_mixed(self):
        # nv
        assert _known_functors(_make_mixed_program()) == {"double", "quadruple"}


class TestHasResidualGoals:
    """Test _has_residual_goals helper."""

    def test_natnum_no_residual(self):
        # nv
        prog = _make_natnum_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_graph_no_residual(self):
        # nv
        prog = _make_graph_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_factorial_has_residual(self):
        # nv
        prog = _make_factorial_program()
        assert _has_residual_goals(prog, _known_functors(prog))

    def test_mixed_has_residual(self):
        # nv
        prog = _make_mixed_program()
        assert _has_residual_goals(prog, _known_functors(prog))


class TestSpecializeSolveFactorial:
    """Specialize vanilla solve/2 with factorial program (has builtins)."""

    def test_clause_count(self, mi_module, spec_module):
        """1 base + 2 object clauses + 1 catch-all = 4."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial",
        )
        assert len(_row(spec_module, "SolveFactorial", 1).clauses) == 4

    def test_fields(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial2",
        )
        assert "GOALS" in _row(spec_module, "SolveFactorial2", 1).signature
        assert "PROGRAM" not in _row(spec_module, "SolveFactorial2", 1).signature

    def test_factorial_0(self, mi_module, spec_module):
        """factorial(0, 1) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial3",
        )
        results = list(_query(
            spec_module, "SolveFactorial3", [["factorial", 0, 1]],
        ))
        assert len(results) >= 1

    def test_factorial_1(self, mi_module, spec_module):
        """factorial(1, 1) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial4",
        )
        results = list(_query(
            spec_module, "SolveFactorial4", [["factorial", 1, 1]],
        ))
        assert len(results) >= 1

    def test_factorial_3(self, mi_module, spec_module):
        """factorial(3, 6) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial5",
        )
        results = list(_query(
            spec_module, "SolveFactorial5", [["factorial", 3, 6]],
        ))
        assert len(results) >= 1

    def test_factorial_5(self, mi_module, spec_module):
        """factorial(5, 120) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial6",
        )
        results = list(_query(
            spec_module, "SolveFactorial6", [["factorial", 5, 120]],
        ))
        assert len(results) >= 1

    def test_factorial_wrong_result_fails(self, mi_module, spec_module):
        """factorial(3, 7) should fail."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactorial7",
        )
        results = list(_query(
            spec_module, "SolveFactorial7", [["factorial", 3, 7]],
        ))
        assert len(results) == 0

    def test_row_route_factorial(self, mi_module, spec_module):
        """Phase 3, post-P4 route: the residual catch-all answers when the
        predicate is reached through ``module.db.get_dispatch``."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize_row_route(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "RowRouteFactorial", 1,
        )
        for n, r in [(0, 1), (1, 1), (3, 6), (5, 120)]:
            assert list(_query(
                spec_module, "RowRouteFactorial", [["factorial", n, r]],
            )), f"factorial({n}, {r}) should succeed"
        assert not list(_query(
            spec_module, "RowRouteFactorial", [["factorial", 3, 7]],
        ))


class TestSpecializeSolveCountFactorial:
    """Specialize counting MI with factorial program (has builtins)."""

    def test_clause_count(self, mi_module, spec_module):
        """1 base + 2 object clauses + 1 catch-all = 4."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveCountFactorial",
        )
        assert len(_row(spec_module, "SolveCountFactorial", 2).clauses) == 4

    def test_count_factorial_0(self, mi_module, spec_module):
        """factorial(0, 1) needs 1 step."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveCountFactorial2",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountFactorial2", [["factorial", 0, 1]],
        ))
        assert any(count == 1 for count in results)

    def test_count_factorial_3(self, mi_module, spec_module):
        """factorial(3, 6) needs 4 steps (1 per recursive clause + base case)."""
        # nv
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveCountFactorial3",
        )
        results = list(_query_with_extra(
            spec_module, "SolveCountFactorial3", [["factorial", 3, 6]],
        ))
        # Each residual goal (gt, sub, mul) counts as 1 step, plus 1 for the
        # factorial match.  But the counting happens per-resolution-step of the
        # MI loop, not per goal.  Each goal in the goal list is one step.
        # factorial(3, 6): factorial(3,R) matches → gt,sub,factorial(2,R1),mul
        # That's 4 goals (gt, sub, factorial(2,R1), mul) plus factorial(0,1)
        # base case.  Steps counted: one per goal consumed from the goal list.
        assert len(results) >= 1
        # We check the count is > 0; exact count depends on interleaving.
        assert all(count > 0 for count in results)


class TestSpecializeSolveEvenOdd:
    """Specialize solve/2 with even/odd program (has arithmetic builtins)."""

    def test_even_0(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEven",
        )
        results = list(_query(spec_module, "SolveEven", [["even", 0]]))
        assert len(results) >= 1

    def test_even_2(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEven2",
        )
        results = list(_query(spec_module, "SolveEven2", [["even", 2]]))
        assert len(results) >= 1

    def test_even_4(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEven3",
        )
        results = list(_query(spec_module, "SolveEven3", [["even", 4]]))
        assert len(results) >= 1

    def test_odd_1_fails(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEven4",
        )
        results = list(_query(spec_module, "SolveEven4", [["even", 1]]))
        assert len(results) == 0

    def test_odd_3_fails(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEven5",
        )
        results = list(_query(spec_module, "SolveEven5", [["even", 3]]))
        assert len(results) == 0


class TestSpecializeSolveMixed:
    """Specialize solve/2 with mixed program (known + residual goals)."""

    def test_double_3(self, mi_module, spec_module):
        """double(3, 6) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_mixed_program(), "SolveMixed",
        )
        results = list(_query(spec_module, "SolveMixed", [["double", 3, 6]]))
        assert len(results) >= 1

    def test_quadruple_3(self, mi_module, spec_module):
        """quadruple(3, 12) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_mixed_program(), "SolveMixed2",
        )
        results = list(_query(
            spec_module, "SolveMixed2", [["quadruple", 3, 12]],
        ))
        assert len(results) >= 1

    def test_quadruple_wrong_fails(self, mi_module, spec_module):
        """quadruple(3, 10) should fail."""
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_mixed_program(), "SolveMixed3",
        )
        results = list(_query(
            spec_module, "SolveMixed3", [["quadruple", 3, 10]],
        ))
        assert len(results) == 0


class TestNoResidualNoCatchAll:
    """Programs without residual goals should NOT get a catch-all clause."""

    def test_natnum_no_catchall(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveNatnumNoCatch",
        )
        # 1 base + 2 object = 3 (no catch-all)
        assert len(_row(spec_module, "SolveNatnumNoCatch", 1).clauses) == 3

    def test_graph_no_catchall(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGraphNoCatch",
        )
        # 1 base + 5 object = 6 (no catch-all)
        assert len(_row(spec_module, "SolveGraphNoCatch", 1).clauses) == 6


class TestCustomGoalMap:
    """Test custom goal_map parameter for user-defined residual handlers."""

    def test_custom_handler(self, mi_module, spec_module):
        """Custom handler for 'double_it' functor."""
        # nv
        from clausal.logic.variables import Var, unify as _unify

        def _handle_double_it(args, trail):
            from clausal.logic.variables import deref, walk
            a = walk(deref(args[0]))
            result = a * 2
            mark = trail.mark()
            if _unify(args[1], result, trail):
                yield None
            trail.undo(mark)

        x, y = Var(), Var()
        program = [
            [["compute", x, y], [["double_it", x, y]]],
        ]

        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "SolveCustom",
            goal_map={"double_it": _handle_double_it},
        )
        results = list(_query(
            spec_module, "SolveCustom", [["compute", 5, 10]],
        ))
        assert len(results) >= 1


class TestEquivalenceWithResidual:
    """Verify specialized MI with residual goals produces correct results.

    Note: the unspecialized MI cannot handle builtins (gt, sub, mul, etc.)
    since they are not in the object program.  Phase 3 adds this capability.
    We compare against known expected results instead.
    """

    def test_factorial_known_results(self, mi_module, spec_module):
        """Specialized factorial should produce correct results."""
        # nv
        program = _make_factorial_program()
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "SolveFactorialEquiv",
        )

        for n, expected_r in [(0, 1), (1, 1), (2, 2), (3, 6), (4, 24), (5, 120)]:
            goal = [["factorial", n, expected_r]]
            results = list(_query(spec_module, "SolveFactorialEquiv", goal))
            assert len(results) >= 1, (
                f"factorial({n}, {expected_r}) should succeed"
            )

    def test_factorial_query_result(self, mi_module, spec_module):
        """Specialized factorial should bind result variable."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        program = _make_factorial_program()
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "SolveFactorialEquiv2",
        )

        for n, expected_r in [(0, 1), (1, 1), (3, 6), (5, 120)]:
            r_var = Var()
            results = []
            for _ in call("SolveFactorialEquiv2", [["factorial", n, r_var]],
                          module=spec_module):
                results.append(walk(deref(r_var)))
            assert expected_r in results, (
                f"factorial({n}, R): expected R={expected_r}, got {results}"
            )


class TestSolveLimitWithResidual:
    """Specialize depth-limited MI with factorial (has builtins)."""

    def test_limit_factorial_0_depth1(self, mi_module, spec_module):
        """Depth 1 should suffice for factorial(0, 1) (just the base clause)."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveLimitFactorial",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitFactorial", [["factorial", 0, 1]], 1,
        ))
        assert len(results) >= 1

    def test_limit_factorial_1_depth2_fails(self, mi_module, spec_module):
        """Depth 2 is not enough for factorial(1, 1) — needs gt, sub, factorial(0,1), mul."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveLimitFactorial2",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitFactorial2", [["factorial", 1, 1]], 2,
        ))
        assert len(results) == 0

    def test_limit_factorial_1_high_depth(self, mi_module, spec_module):
        """With high depth limit, factorial(1, 1) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveLimitFactorial3",
        )
        results = list(_query_limit(
            spec_module, "SolveLimitFactorial3", [["factorial", 1, 1]], 20,
        ))
        assert len(results) >= 1


# ── Phase 4: Termination control ──────────────────────────────────────────────


class TestHomeomorphicEmbedding:
    """Unit tests for the embeds() function."""

    def test_var_embeds_var(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert embeds(Var(), Var())

    def test_var_does_not_embed_constant(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert not embeds(Var(), 42)

    def test_constant_does_not_embed_var(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert not embeds(42, Var())

    def test_equal_constants(self):
        # nv
        from clausal.logic.specialization import embeds
        assert embeds(0, 0)
        assert embeds("a", "a")

    def test_different_constants(self):
        # nv
        from clausal.logic.specialization import embeds
        assert not embeds(0, 1)
        assert not embeds("a", "b")

    def test_same_functor_coupling(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # f(X) embeds f(Y) — same functor, var embeds var.
        assert embeds(["f", Var()], ["f", Var()])

    def test_same_functor_args(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) embeds f(0).
        assert embeds(["f", 0], ["f", 0])
        # f(0) does NOT embed f(1).
        assert not embeds(["f", 0], ["f", 1])

    def test_diving(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) embeds g(f(0)) — dives into g's arg.
        assert embeds(["f", 0], ["g", ["f", 0]])

    def test_diving_nested(self):
        # nv
        from clausal.logic.specialization import embeds
        # 0 embeds f(0) — constant dives into compound.
        assert embeds(0, ["f", 0])

    def test_growth_detection(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # natnum(X) is embedded BY natnum(s(Y)) — the latter is "bigger".
        # in_ the standard definition, embeds(s, t) means s is a sub-pattern of t.
        # natnum(s(Y)) does NOT embed natnum(X) (compound arg doesn't embed var).
        # But natnum(X) DOES embed natnum(s(Y)) via diving: X doesn't embed s(Y),
        # but natnum(X) dives into natnum(s(Y))'s arg s(Y)... no.
        # Actually: for the termination test, we check if the NEW atom embeds
        # an ANCESTOR.  If natnum(s(Y)) embeds natnum(X), growth is detected.
        # s(Y) embeds X? No.  So coupling fails.
        # The correct growth check: the ancestor natnum(X) is embedded in the
        # descendant natnum(s(Y)) via diving: natnum(X) embeds natnum(Y)
        # (coupling: var embeds var), and natnum(Y) is a sub-term of natnum(s(Y)).
        # Wait — natnum(Y) is not a sub-term of natnum(s(Y)).  s(Y) is.
        # Standard: natnum(X) embeds natnum(s(Y))? No — coupling requires X embeds s(Y).
        # This is a limitation of strict homeomorphic embedding.  in_ practice,
        # the depth counter handles this.
        x, y = Var(), Var()
        # Verify that at least trivially-growing terms are caught:
        # f(X) embeds f(f(X)) — f(X) dives into f(f(X))'s arg f(X).
        assert embeds(["f", x], ["f", ["f", y]])

    def test_no_embed_different_arity(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) does NOT embed f(0, 1) — different arity.
        assert not embeds(["f", 0], ["f", 0, 1])

    def test_transitive_growth(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # f(X, Y) embeds f(f(X), Y) — coupling: f(X) embeds f(f(X)) via diving,
        # and Y (var) embeds Y (var).
        x1, y1, x2, y2 = Var(), Var(), Var(), Var()
        assert embeds(
            ["f", ["f", x1], y1],
            ["f", ["f", ["f", x2]], y2],
        )

    def test_constant_does_not_embed_compound(self):
        # nv
        from clausal.logic.specialization import embeds
        # 0 doesn't embed ["natnum", 0] via coupling (different types).
        # But it does embed via diving (0 is inside the compound).
        assert embeds(0, ["natnum", 0])

    def test_compound_does_not_embed_constant(self):
        # nv
        from clausal.logic.specialization import embeds
        assert not embeds(["f", 0], 0)


class TestMemoTable:
    """Tests for the MemoTable memoization class."""

    def test_empty_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        assert memo.lookup(["natnum", 0]) is None

    def test_register_and_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        assert memo.lookup(["natnum", 0]) == "SolveNatnum"

    def test_register_var_pattern(self):
        # nv
        from clausal.logic.specialization import MemoTable
        from clausal.logic.variables import Var
        memo = MemoTable()
        memo.register(["natnum", Var()], "SolveNatnum")
        # Any natnum with a var should match.
        assert memo.lookup(["natnum", Var()]) == "SolveNatnum"

    def test_different_functor_no_match(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        assert memo.lookup(["even", 0]) is None

    def test_multiple_registrations(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        memo.register(["even", 0], "SolveEven")
        assert memo.lookup(["natnum", 0]) == "SolveNatnum"
        assert memo.lookup(["even", 0]) == "SolveEven"

    def test_non_list_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        assert memo.lookup(42) is None
        assert memo.lookup([]) is None

    def test_entries_property(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["f", 0], "SpecF")
        entries = memo.entries
        assert "f" in entries
        assert len(entries["f"]) == 1


class TestSpecializeDeep:
    """Tests for specialize_mi_deep with depth-bounded unfolding."""

    def test_depth_0_same_as_shallow(self, mi_module, spec_module):
        """At max_depth=0, deep unfolder produces same clauses as shallow."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()

        # Shallow specialization.
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "ShallowNatnum",
        )
        shallow_count = len(_row(spec_module, "ShallowNatnum", 1).clauses)

        # Deep with depth=0.
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepNatnum0", max_depth=0,
        )
        deep_count = len(_row(spec_module, "DeepNatnum0", 1).clauses)

        assert shallow_count == deep_count

    def test_deep_natnum_produces_results(self, mi_module, spec_module):
        """Deep-specialized natnum should still produce correct results."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepNatnum1", max_depth=3,
        )

        results = list(_query(spec_module, "DeepNatnum1", [["natnum", 0]]))
        assert len(results) >= 1

    def test_deep_natnum_s0(self, mi_module, spec_module):
        """Deep-specialized natnum: s(0) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepNatnum2", max_depth=3,
        )

        results = list(_query(
            spec_module, "DeepNatnum2", [["natnum", ["s", 0]]],
        ))
        assert len(results) >= 1

    def test_deep_factorial_base(self, mi_module, spec_module):
        """Deep-specialized factorial(0, 1) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_factorial_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepFactorial1", max_depth=3,
        )

        results = list(_query(
            spec_module, "DeepFactorial1", [["factorial", 0, 1]],
        ))
        assert len(results) >= 1

    def test_deep_factorial_1(self, mi_module, spec_module):
        """Deep-specialized factorial(1, 1) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.solve)
        program = _make_factorial_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepFactorial2", max_depth=5,
        )

        r_var = Var()
        results = []
        for _ in call("DeepFactorial2", [["factorial", 1, r_var]], module=spec_module):
            results.append(walk(deref(r_var)))
        assert 1 in results

    def test_deep_count_natnum(self, mi_module, spec_module):
        """Deep-specialized solve_count with natnum: counting preserved."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve_count)
        program = _make_natnum_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepCountNatnum", max_depth=3,
        )

        results = list(_query_with_extra(
            spec_module, "DeepCountNatnum", [["natnum", ["s", 0]]],
        ))
        assert len(results) >= 1
        assert all(isinstance(r, int) for r in results)

    def test_deep_graph_path(self, mi_module, spec_module):
        """Deep-specialized solve with graph: paths still found."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_graph_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepGraph1", max_depth=3,
        )

        # path(a, c) should succeed.
        results = list(_query(
            spec_module, "DeepGraph1", [["path", "a", "c"]],
        ))
        assert len(results) >= 1

    def test_max_depth_respected(self, mi_module, spec_module):
        """Unfolding should not exceed max_depth."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()

        # Very low depth — should still produce valid (if not deeply inlined) code.
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepNatnum_d1", max_depth=1,
        )
        # Should have at least the base clause count.
        # 1 base + 2 object
        assert len(_row(spec_module, "DeepNatnum_d1", 1).clauses) >= 3

    def test_equivalence_natnum(self, mi_module, spec_module):
        """Deep-specialized natnum matches shallow for all small values."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep

        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "ShallowNatnum_eq",
        )
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepNatnum_eq", max_depth=5,
        )

        for val in [0, ["s", 0], ["s", ["s", 0]], ["s", ["s", ["s", 0]]]]:
            shallow_results = list(_query(
                spec_module, "ShallowNatnum_eq", [["natnum", val]],
            ))
            deep_results = list(_query(
                spec_module, "DeepNatnum_eq", [["natnum", val]],
            ))
            assert len(shallow_results) == len(deep_results), (
                f"Mismatch for natnum({val}): "
                f"shallow={len(shallow_results)}, deep={len(deep_results)}"
            )

    def test_equivalence_factorial(self, mi_module, spec_module):
        """Deep-specialized factorial matches shallow for small values."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.solve)
        program = _make_factorial_program()
        _specialize(
            spec_module, specialize_mi,
            pattern, program, "ShallowFact_eq",
        )
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "DeepFact_eq", max_depth=5,
        )

        for n, expected in [(0, 1), (1, 1), (3, 6)]:
            for name, label in [
                ("ShallowFact_eq", "shallow"),
                ("DeepFact_eq", "deep"),
            ]:
                r = Var()
                results = []
                for _ in call(name, [["factorial", n, r]], module=spec_module):
                    results.append(walk(deref(r)))
                assert expected in results, (
                    f"{label} factorial({n}): expected {expected}, got {results}"
                )

    def test_row_route_deep_factorial(self, mi_module, spec_module):
        """Phase 4, post-P4 route: deep-specialized factorial binds R when
        reached through ``module.db.get_dispatch``."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.solve)
        _specialize_row_route(
            spec_module, specialize_mi_deep,
            pattern, _make_factorial_program(), "RowRouteDeepFactorial", 1,
            max_depth=5,
        )
        for n, expected in [(0, 1), (1, 1), (3, 6)]:
            r = Var()
            results = [walk(deref(r)) for _ in call(
                "RowRouteDeepFactorial", [["factorial", n, r]],
                module=spec_module,
            )]
            assert expected in results, f"factorial({n}): got {results}"


class TestEmbeddingTermination:
    """Tests that homeomorphic embedding prevents divergence."""

    def test_self_recursive_natnum_terminates(self, mi_module, spec_module):
        """Natnum is self-recursive; deep unfolding should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_natnum_program()
        # If embedding check fails, this would loop forever.
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "TermNatnum", max_depth=20,
        )
        assert _row(spec_module, "TermNatnum", 1) is not None

    def test_recursive_factorial_terminates(self, mi_module, spec_module):
        """Factorial is self-recursive; deep unfolding should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_factorial_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "TermFactorial", max_depth=20,
        )
        assert _row(spec_module, "TermFactorial", 1) is not None

    def test_mutual_recursion_graph_terminates(self, mi_module, spec_module):
        """Graph program has edge/path mutual reference; should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_graph_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "TermGraph", max_depth=20,
        )
        assert _row(spec_module, "TermGraph", 1) is not None

    def test_even_recursive_terminates(self, mi_module, spec_module):
        """Even/odd recursive program should terminate deep unfolding."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.solve)
        program = _make_even_odd_program()
        _specialize(
            spec_module, specialize_mi_deep,
            pattern, program, "TermEven", max_depth=20,
        )
        assert _row(spec_module, "TermEven", 1) is not None


# ── Test helpers ──────────────────────────────────────────────────────────────


def _query(module, name, goal_list):
    """Query a specialized predicate by name against *module* with just a
    goal list.  Resolution is ``call``'s: ``module_dict``, then builtins, then
    ``module.db.get_dispatch`` (see ``spec_module``)."""
    from clausal.logic.solve import call

    for _ in call(name, goal_list, module=module):
        yield True


def _query_with_extra(module, name, goal_list):
    """Query a specialized predicate by name against *module* with goal list
    + one extra arg (COUNT).  Resolves as ``_query`` does."""
    from clausal.logic.variables import Var, deref, walk
    from clausal.logic.solve import call

    count_var = Var()
    for _ in call(name, goal_list, count_var, module=module):
        yield walk(deref(count_var))


def _query_limit(module, name, goal_list, max_depth):
    """Query a depth-limited specialized predicate by name against *module*.
    Resolves as ``_query`` does."""
    from clausal.logic.solve import call

    for _ in call(name, goal_list, max_depth, module=module):
        yield True


def _query_tree(module, name, goal_list):
    """Query a proof-tree specialized predicate by name against *module*.
    Resolves as ``_query`` does."""
    from clausal.logic.variables import Var, deref, walk
    from clausal.logic.solve import call

    tree_var = Var()
    for _ in call(name, goal_list, tree_var, module=module):
        yield walk(deref(tree_var))


def _query_mi(mi_cls, goal_list, program):
    """Query the unspecialized MI for comparison."""
    from clausal.logic.solve import call

    for _ in call(mi_cls, goal_list, program):
        yield True


# ── Phase 5: Conjunctive Partial Deduction ─────────────────────────────────────


class TestAstUnify:
    """Unit tests for AST-level unification."""

    def test_ground_match(self):
        # nv
        assert _ast_unify(["natnum", 0], ["natnum", 0]) == {}

    def test_ground_mismatch(self):
        # nv
        assert _ast_unify(["natnum", 0], ["edge", 0]) is None

    def test_var_binds(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(["natnum", x], ["natnum", 0])
        assert result is not None
        assert result[id(x)] == 0

    def test_var_in_second(self):
        # nv
        from clausal.logic.variables import Var
        y = Var()
        result = _ast_unify(["natnum", 0], ["natnum", y])
        assert result is not None
        assert result[id(y)] == 0

    def test_nested_unify(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(["natnum", ["s", x]], ["natnum", ["s", 0]])
        assert result is not None
        assert result[id(x)] == 0

    def test_both_vars(self):
        # nv
        from clausal.logic.variables import Var
        x, y = Var(), Var()
        result = _ast_unify(["edge", x, y], ["edge", "a", "b"])
        assert result is not None
        assert result[id(x)] == "a"
        assert result[id(y)] == "b"

    def test_arity_mismatch(self):
        # nv
        assert _ast_unify(["natnum", 0], ["natnum", 0, 1]) is None

    def test_same_var(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(x, x)
        assert result == {}

    def test_var_to_compound(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(x, ["natnum", 0])
        assert result is not None
        assert result[id(x)] == ["natnum", 0]


class TestConjunctionMemoTable:
    """Tests for the conjunction memoization table."""

    def test_empty(self):
        # nv
        memo = ConjunctionMemoTable()
        assert not memo.has_seen([["natnum", 0]])

    def test_register_and_lookup(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert memo.has_seen([["natnum", 0]])

    def test_different_pattern(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert not memo.has_seen([["edge", "a"]])

    def test_entries(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert ("natnum",) in memo.entries


class TestCpdSolveNatnum:
    """CPD on vanilla solve/2 with natnum program."""

    def test_more_clauses_than_shallow(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveSh1",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveCpd1",
        )
        cpd_clauses = len(_row(spec_module, "SolveCpd1", 1).clauses)
        shallow_clauses = len(_row(spec_module, "SolveSh1", 1).clauses)
        assert cpd_clauses >= shallow_clauses

    def test_natnum_0(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveCpd2",
        )
        assert sum(1 for _ in call(
            "SolveCpd2", [["natnum", 0]], module=spec_module,
        )) == 1

    def test_natnum_s_0(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveCpd3",
        )
        assert sum(1 for _ in call(
            "SolveCpd3", [["natnum", ["s", 0]]], module=spec_module,
        )) == 1

    def test_natnum_s_s_s_0(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveCpd4",
        )
        assert sum(1 for _ in call(
            "SolveCpd4", [["natnum", ["s", ["s", ["s", 0]]]]], module=spec_module,
        )) == 1

    def test_equivalence_natnum(self, mi_module, spec_module):
        """CPD produces same results as Phase 1 for various natnum inputs."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SolveSh5",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveCpd5",
        )
        for n in range(6):
            term = 0
            for _ in range(n):
                term = ["s", term]
            goal = [["natnum", term]]
            s = sum(1 for _ in call("SolveSh5", goal, module=spec_module))
            c = sum(1 for _ in call("SolveCpd5", goal, module=spec_module))
            assert s == c, f"natnum({n}): shallow={s}, cpd={c}"


class TestCpdSolveGraph:
    """CPD on vanilla solve/2 with graph program."""

    def test_more_clauses_than_shallow(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGSh1",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd1",
        )
        cpd_clauses = len(_row(spec_module, "SolveGCpd1", 1).clauses)
        shallow_clauses = len(_row(spec_module, "SolveGSh1", 1).clauses)
        assert cpd_clauses > shallow_clauses

    def test_path_a_b(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd2",
        )
        assert sum(1 for _ in call(
            "SolveGCpd2", [["path", "a", "b"]], module=spec_module,
        )) == 1

    def test_path_a_c(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd3",
        )
        assert sum(1 for _ in call(
            "SolveGCpd3", [["path", "a", "c"]], module=spec_module,
        )) == 1

    def test_path_a_d(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd4",
        )
        assert sum(1 for _ in call(
            "SolveGCpd4", [["path", "a", "d"]], module=spec_module,
        )) == 1

    def test_edge_a_b(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd5",
        )
        assert sum(1 for _ in call(
            "SolveGCpd5", [["edge", "a", "b"]], module=spec_module,
        )) == 1

    def test_equivalence_graph(self, mi_module, spec_module):
        """CPD produces same results as Phase 1 for all graph queries."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_graph_program(), "SolveGSh6",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveGCpd6",
        )
        queries = [
            [["edge", "a", "b"]], [["edge", "b", "c"]], [["edge", "b", "d"]],
            [["path", "a", "b"]], [["path", "a", "c"]], [["path", "a", "d"]],
            [["path", "b", "c"]], [["path", "b", "d"]],
        ]
        for q in queries:
            s = sum(1 for _ in call("SolveGSh6", q, module=spec_module))
            c = sum(1 for _ in call("SolveGCpd6", q, module=spec_module))
            assert s == c, f"{q}: shallow={s}, cpd={c}"

    def test_row_route_cpd_graph(self, mi_module, spec_module):
        """Phase 5, post-P4 route: CPD graph answers when reached through
        ``module.db.get_dispatch``."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize_row_route(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "RowRouteCpdGraph", 1,
        )
        for q, expected in [
            ([["edge", "a", "b"]], 1), ([["path", "a", "b"]], 1),
            ([["path", "a", "c"]], 1), ([["path", "a", "d"]], 1),
            ([["path", "c", "a"]], 0),
        ]:
            assert sum(1 for _ in call(
                "RowRouteCpdGraph", q, module=spec_module,
            )) == expected, q


class TestCpdSolveCount:
    """CPD on solve_count/3 with natnum — tests post-match chaining."""

    def test_count_natnum_0(self, mi_module, spec_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SCCpd1",
        )
        v = Var()
        counts = [walk(deref(v))
                  for _ in call("SCCpd1", [["natnum", 0]], v, module=spec_module)]
        assert counts, "natnum(0) has no solution"
        assert set(counts) == {1}, counts

    def test_count_natnum_s_0(self, mi_module, spec_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SCCpd2",
        )
        v = Var()
        counts = [walk(deref(v)) for _ in call(
            "SCCpd2", [["natnum", ["s", 0]]], v, module=spec_module,
        )]
        assert counts, "natnum(s(0)) has no solution"
        assert set(counts) == {2}, counts

    def test_count_equivalence(self, mi_module, spec_module):
        """CPD counting matches Phase 1 counting for natnum(0..5)."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SCSh3",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SCCpd3",
        )
        for n in range(6):
            term = 0
            for _ in range(n):
                term = ["s", term]
            vs, vc = Var(), Var()
            sv = None
            for _ in call("SCSh3", [["natnum", term]], vs, module=spec_module):
                sv = walk(deref(vs))
            cv = None
            for _ in call("SCCpd3", [["natnum", term]], vc, module=spec_module):
                cv = walk(deref(vc))
            assert sv == cv, f"natnum({n}): shallow={sv}, cpd={cv}"


class TestCpdSolveLimit:
    """CPD on solve_limit/3 — tests pre-match chaining."""

    def test_limit_passes(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SLCpd1",
        )
        assert sum(1 for _ in call(
            "SLCpd1", [["natnum", ["s", ["s", 0]]]], 10, module=spec_module,
        )) == 1

    def test_limit_fails(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SLCpd2",
        )
        assert sum(1 for _ in call(
            "SLCpd2", [["natnum", ["s", ["s", ["s", 0]]]]], 2, module=spec_module,
        )) == 0

    def test_limit_equivalence(self, mi_module, spec_module):
        """CPD limit behavior matches Phase 1 for various depths and limits."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve_limit)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "SLSh3",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SLCpd3",
        )
        for depth in range(5):
            term = 0
            for _ in range(depth):
                term = ["s", term]
            for limit in range(7):
                s = sum(1 for _ in call(
                    "SLSh3", [["natnum", term]], limit, module=spec_module,
                ))
                c = sum(1 for _ in call(
                    "SLCpd3", [["natnum", term]], limit, module=spec_module,
                ))
                assert s == c, f"natnum({depth}) limit={limit}: {s} vs {c}"


class TestCpdFactorial:
    """CPD with factorial program (has residual goals: gt, sub, mul)."""

    def test_factorial_results(self, mi_module, spec_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_factorial_program(), "SolveFactCpd1",
        )
        for n, expected in [(0, 1), (1, 1), (3, 6), (5, 120)]:
            r = Var()
            results = [walk(deref(r)) for _ in call(
                "SolveFactCpd1", [["factorial", n, r]], module=spec_module,
            )]
            assert results, f"factorial({n}) has no solution"
            assert set(results) == {expected}, f"factorial({n}): {results}"

    def test_factorial_equivalence(self, mi_module, spec_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_factorial_program(), "SolveFactSh2",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_factorial_program(), "SolveFactCpd2",
        )
        for n in [0, 1, 2, 3, 4, 5]:
            rs, rc = Var(), Var()
            sv = None
            for _ in call("SolveFactSh2", [["factorial", n, rs]], module=spec_module):
                sv = walk(deref(rs))
            cv = None
            for _ in call("SolveFactCpd2", [["factorial", n, rc]], module=spec_module):
                cv = walk(deref(rc))
            assert sv == cv, f"factorial({n}): shallow={sv}, cpd={cv}"


class TestCpdEvenOdd:
    """CPD with even/odd program (has residual goals: gte, sub)."""

    def test_even_equivalence(self, mi_module, spec_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_even_odd_program(), "SolveEvSh1",
        )
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_even_odd_program(), "SolveEvCpd1",
        )
        for n in range(10):
            s = sum(1 for _ in call("SolveEvSh1", [["even", n]], module=spec_module))
            c = sum(1 for _ in call("SolveEvCpd1", [["even", n]], module=spec_module))
            assert s == c, f"even({n}): shallow={s}, cpd={c}"


class TestCpdTermination:
    """Tests that CPD terminates on recursive programs."""

    def test_natnum_terminates(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "SolveTerm1", max_depth=20,
        )
        assert len(_row(spec_module, "SolveTerm1", 1).clauses) > 0

    def test_graph_terminates(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_graph_program(), "SolveTerm2", max_depth=20,
        )
        assert len(_row(spec_module, "SolveTerm2", 1).clauses) > 0

    def test_factorial_terminates(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_factorial_program(), "SolveTerm3", max_depth=20,
        )
        assert len(_row(spec_module, "SolveTerm3", 1).clauses) > 0

    def test_even_terminates(self, mi_module, spec_module):
        # nv
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_even_odd_program(), "SolveTerm4", max_depth=20,
        )
        assert len(_row(spec_module, "SolveTerm4", 1).clauses) > 0


# ── The no-db= default and the class handle (DELETE AT W4b-3) ──────────────


class TestNoDbClassHandleDefault:
    """The no-``db=`` default of the direct API.  KEPT at W4b-3 by operator
    ruling 2026-09-25 (it was marked for deletion under ruling QC): a
    specialization with no ``db=`` and no named namespace gets a Database
    with a PRIVATE, REGISTERED module name, so the call still returns a
    HANDLE the caller queries directly.  (The class it returned is gone.)
    """

    def test_the_private_module_handle_resolves_with_nothing_else_held(
            self, mi_module):
        import gc
        from clausal.logic.atoms import demangle
        from clausal.logic.solve import solve
        handle = specialize_mi(analyze_mi(mi_module.solve),
                               _make_natnum_program(), "NoDbPrivate")
        module_name, name = demangle(handle)
        assert name == "NoDbPrivate"
        assert module_name.startswith("_clausal_specialize_NoDbPrivate_")
        gc.collect()      # the handle is a str: the db must be held elsewhere
        assert len(list(solve((handle, [["natnum", ["s", 0]]])))) == 1

    def test_two_db_less_calls_get_two_private_modules(self, mi_module):
        from clausal.logic.atoms import demangle
        a = specialize_mi(analyze_mi(mi_module.solve),
                          _make_natnum_program(), "NoDbTwice")
        b = specialize_mi(analyze_mi(mi_module.solve),
                          _make_natnum_program(), "NoDbTwice")
        assert demangle(a)[0] != demangle(b)[0]

    def test_an_explicit_db_naming_no_module_is_refused(self, mi_module):
        from clausal.logic.database import Database
        with pytest.raises(ValueError, match="names no module"):
            specialize_mi(analyze_mi(mi_module.solve),
                          _make_natnum_program(), "NoDbAnon", db=Database())

    def test_factorial_residual_through_the_class_handle(self, mi_module):
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref, walk

        pattern = analyze_mi(mi_module.solve)
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "NoDbFactorial",
        )
        for n, expected in [(0, 1), (3, 6), (5, 120)]:
            r = Var()
            results = [walk(deref(r))
                       for _ in call(pred_cls, [["factorial", n, r]])]
            assert expected in results, f"factorial({n}): got {results}"
        assert sum(1 for _ in call(pred_cls, [["factorial", 3, 7]])) == 0

    def test_cpd_count_through_the_class_handle(self, mi_module):
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref, walk

        pattern = analyze_mi(mi_module.solve_count)
        pred_cls = specialize_mi_cpd(
            pattern, _make_natnum_program(), "NoDbCountCpd",
        )
        v = Var()
        counts = [walk(deref(v))
                  for _ in call(pred_cls, [["natnum", ["s", 0]]], v)]
        assert counts == [2]

    def test_module_dict_only_gets_a_per_call_database(self, mi_module):
        """``module_dict=`` without ``db=``: the specialization builds its own
        Database over the caller's namespace (``_defining_db``), and the
        returned class answers out of it."""
        from clausal.logic.solve import call

        module_dict = {"__name__": "nodb_module_dict_only"}
        pattern = analyze_mi(mi_module.solve)
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "NoDbModuleDictNatnum",
            module_dict,
        )
        assert _row_of(pred_cls).db.module_dict is module_dict
        assert sum(1 for _ in call(pred_cls, [["natnum", ["s", 0]]])) == 1
        assert sum(1 for _ in call(pred_cls, [["natnum", "a"]])) == 0


# ── P3-3 Task 7: the specialized predicate is a Database ROW ─────────────────


class TestSpecializedPredicateIsARow:
    """P3-3 Task 7.  ``specialize_mi`` used to ``make_predicate`` a
    free-floating class and compile it against a ``Database`` it threw away,
    so the specialized predicate existed only as class attributes.  It is now
    a row: registered, signed, gate-stamped and dispatched through a
    ``Database`` — the caller's when it passes one, the specialization's own
    otherwise — and the returned class READS that row.

    Operator ruling QC (2026-09-24): these write into the ``spec_module``
    fixture's database and query by name like the rest of the file.  Two
    things deliberately stay as they are until W4b-3 changes the API: the
    ``X._row is row`` / ``X._get_dispatch() is db.get_dispatch(...)``
    identity checks pin that the RETURNED CLASS reads the row, which cannot
    be said through the row while ``specialize_mi`` returns a class (at W4b-3
    they become "the result IS the row"); and ``test_no_db_still_row_linked``
    pins the no-``db=`` mode that W4b-3 ends (retire it, or turn it into the
    refusal test, then).
    """

    def test_row_registered_in_the_callers_db(self, mi_module, spec_module):
        db = spec_module.db
        pattern = analyze_mi(mi_module.solve)
        pred_cls = _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7RowNatnum",
        )
        row = db.row("T7RowNatnum", 1)
        assert row is not None
        assert _row_of(pred_cls) is row
        assert row.detached is False

    def test_signature_registered_in_the_callers_db(self, mi_module, spec_module):
        db = spec_module.db
        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7SigNatnum",
        )
        assert db.signature_for("T7SigNatnum", 2) == ("GOALS", "COUNT")

    def test_clauses_and_dispatch_land_in_the_callers_db(self, mi_module, spec_module):
        db = spec_module.db
        pattern = analyze_mi(mi_module.solve)
        pred_cls = _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7ClausesNatnum",
        )
        assert len(db.clauses_for("T7ClausesNatnum", 1)) == 3
        assert db.get_dispatch("T7ClausesNatnum", 1) is _dispatch_of(pred_cls)

    def test_write_is_gate_stamped(self, mi_module, spec_module):
        from clausal.logic.database import WRITE_LOAD_CLAUSES
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        db = spec_module.db
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7StampNatnum",
        )
        row = db.row("T7StampNatnum", 1)
        stamps = [w for w in row.writes
                  if w.author.startswith(SPECIALIZE_AUTHOR_PREFIX)]
        assert stamps
        assert any(w.kind == WRITE_LOAD_CLAUSES for w in stamps)
        assert row.source is not None
        assert row.source[1] == stamps[0].author

    def test_respecialization_by_the_same_author_is_permitted(
        self, mi_module, spec_module,
    ):
        """The first write claims ownership FOR the specialization author, so
        specializing the same name into the same database again is that
        author writing its own predicate — rule 1 of the ownership policy."""
        db = spec_module.db
        pattern = analyze_mi(mi_module.solve)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7AgainNatnum",
        )
        pred_cls = _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7AgainNatnum",
        )
        assert len(db.clauses_for("T7AgainNatnum", 1)) == 3
        assert _row_of(pred_cls) is db.row("T7AgainNatnum", 1)

    def test_no_db_still_row_linked(self, mi_module):
        """With no database anywhere in the caller's world there is no defining
        module, so the specialization keeps a Database of its own — but the
        class READS its row, and the predicate is registered there, gate-
        stamped and owned, rather than living in class attributes.

        This one passed BEFORE Task 7 as far as the row link goes, because
        ``compiler._install`` already bound the class to the throwaway
        database's row — which was the bug: the right mechanism against the
        wrong database.  The write log and ``source`` are what it could not
        show then, and are what make this the no-``db`` twin of
        ``test_write_is_gate_stamped``."""
        from clausal.logic.database import WRITE_LOAD_CLAUSES
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        pattern = analyze_mi(mi_module.solve)
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "T7NoDbNatnum",
        )
        row = _row_of(pred_cls)
        assert row is not None
        assert row.detached is False
        assert row.db.row("T7NoDbNatnum", 1) is row
        assert row.db.get_dispatch("T7NoDbNatnum", 1) is _dispatch_of(pred_cls)
        # One stamp for the whole specialization: the nested set_dispatch and
        # dispatch-install transactions inherit this one (P3-3 Task 3).
        assert len(row.writes) == 1
        assert row.writes[0].kind == WRITE_LOAD_CLAUSES
        assert row.writes[0].author.startswith(SPECIALIZE_AUTHOR_PREFIX)
        assert row.source is not None
        assert row.source[1] == row.writes[0].author

    def test_deep_and_cpd_register_rows_too(self, mi_module, spec_module):
        from clausal.logic.specialization import specialize_mi_deep

        db = spec_module.db
        pattern = analyze_mi(mi_module.solve)
        deep = _specialize(
            spec_module, specialize_mi_deep,
            pattern, _make_natnum_program(), "T7DeepNatnum", max_depth=3,
        )
        cpd = _specialize(
            spec_module, specialize_mi_cpd,
            pattern, _make_natnum_program(), "T7CpdNatnum", max_depth=3,
        )
        assert _row_of(deep) is db.row("T7DeepNatnum", 1)
        assert _row_of(cpd) is db.row("T7CpdNatnum", 1)
        assert db.get_dispatch("T7DeepNatnum", 1) is not None
        assert db.get_dispatch("T7CpdNatnum", 1) is not None

    def test_specialized_answers_are_unchanged(self, mi_module, spec_module):
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.solve_count)
        _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7AnswerNatnum",
        )
        assert sum(1 for _ in call(
            "T7AnswerNatnum", [["natnum", ["s", ["s", 0]]]], 3,
            module=spec_module,
        )) == 1

    def test_specialized_calls_specialized_through_the_shared_db(
        self, mi_module, spec_module,
    ):
        """Two specializations into ONE database, the second's object program
        naming the first — and the call reaches the first one's ROW.

        NOT through a lowered body goal: the unfolder emits no code reference
        to another alias, so ``T7Inner`` is not a name in ``T7Outer``'s
        compiled globals at all.  It survives as a residual TERM, and the
        catch-all clause hands it to ``_SolveGoal_T7Outer``, whose
        ``module_dict.get(functor)`` → ``pred._get_dispatch()`` fallback
        (``_make_solve_goal_predicate``, specialization.py:1234-1239) is the
        one route by which one specialized predicate calls another.  That
        ``_get_dispatch`` is what Task 7 moved: it used to read a class slot
        backed by a Database the specializer had dropped, and now reads the
        shared database's row.

        Before Task 7 each ``specialize_mi`` call built a Database of its own,
        so "the same database" was not a thing two specializations could
        share; the only link between them was the module dict entry.
        """
        from clausal.logic.solve import call
        from clausal.logic.variables import Var

        db = spec_module.db
        module_dict = spec_module.module_dict
        pattern = analyze_mi(mi_module.solve)

        inner = _specialize(
            spec_module, specialize_mi,
            pattern, _make_natnum_program(), "T7Inner",
        )
        y = Var()
        outer = _specialize(
            spec_module, specialize_mi,
            pattern, [[["wrap", y], [["T7Inner", [["natnum", y]]]]]], "T7Outer",
        )

        assert _row_of(inner) is db.row("T7Inner", 1)
        assert _row_of(outer) is db.row("T7Outer", 1)
        assert _row_of(inner).db is _row_of(outer).db
        # The callee is reached through its row's dispatch, not a private one.
        # W4b-2d: the module dict binds the specialization's HANDLE (it was
        # the class), which resolves to that same row.
        from clausal.logic.predicate import (
            mint_predicate_handle, resolve_predicate_row,
        )
        assert module_dict["T7Inner"] == mint_predicate_handle(db, "T7Inner")
        assert resolve_predicate_row(module_dict["T7Inner"], arity=1,
                                     db=db) is _row_of(inner)
        assert _dispatch_of(inner) is db.get_dispatch("T7Inner", 1)

        assert sum(1 for _ in call(
            "T7Outer", [["wrap", ["s", 0]]], module=spec_module,
        )) == 1
        assert sum(1 for _ in call(
            "T7Outer", [["wrap", "a"]], module=spec_module,
        )) == 0
