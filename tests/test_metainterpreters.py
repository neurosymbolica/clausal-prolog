"""tests/test_metainterpreters.py — Python-level tests for meta-interpreters.

Tests variable binding, multiple solutions, and enumeration behaviour
that are difficult to express as inline .clausal Test predicates.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var, Trail, deref
from clausal.testing import load_clausal_module


_EXAMPLE = os.path.join(
    os.path.dirname(__file__), os.pardir, "clausal", "examples",
    "metainterpreters.clausal",
)


@pytest.fixture(scope="module")
def mod():
    return load_clausal_module(_EXAMPLE)


def _module(mod):
    return mod.__dict__["$module"]


def _terms(mod):
    """Cell CONSTRUCTORS for the module's object-level data functors.

    P3-2 Task 2 (THE FLIP, R6): ``natnum``/``succ``/``Edge``/``Path`` are
    ``-private`` DATA functors, so the module's own clauses build them as
    cells and their names bind interned SPELLINGS, not classes -- a Python
    caller can no longer construct one by calling ``mod.natnum``.  Returning
    builders instead of classes keeps every call site below reading as the
    term it constructs while handing the engine the shape its clauses match.
    """
    d = mod.__dict__
    assert d["natnum"] == mint("natnum")  # R6: the binding IS the atom
    return (
        lambda *args: ("natnum", *args),
        lambda *args: ("succ", *args),
        lambda *args: ("edge", *args),
        lambda *args: ("path", *args),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _solve_bindings(mod, goals_val, program_pred="natnum_program"):
    """Call solve(goals, program) and return list of deref'd goals per solution."""
    m = _module(mod)
    p = Var()
    results = []
    for _ in call(program_pred, p, module=m):
        prog = _deref_walk(p)
        for _ in call("solve", goals_val, prog, module=m):
            results.append(_deref_walk(goals_val))
    return results


# ── Vanilla MI: variable binding ─────────────────────────────────────────────


class TestSolveBindings:

    def test_natnum_binds_variable(self, mod):
        """solve [natnum(X)] should enumerate X = 0, succ(0), succ(succ(0)), ..."""
        # nv
        Natnum, succ, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        x = Var()
        goal = [Natnum(x)]
        results = []
        for _ in call("natnum_program", p, module=m):
            prog = deref(p)
            count = 0
            for _ in call("solve", goal, prog, module=m):
                results.append(_deref_walk(x))
                count += 1
                if count >= 4:
                    break
        assert results[0] == 0
        assert results[1] == succ(0)
        assert results[2] == succ(succ(0))
        assert results[3] == succ(succ(succ(0)))

    def test_edge_binds_destination(self, mod):
        """solve [edge(a, Y)] should enumerate Y = b."""
        # nv
        _, _, Edge, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        y = Var()
        goal = [Edge(mint("a"), y)]
        results = []
        for _ in call("graph_program", p, module=m):
            prog = deref(p)
            for _ in call("solve", goal, prog, module=m):
                results.append(_deref_walk(y))
        assert mint("b") in results

    def test_path_binds_destination(self, mod):
        """solve [path(a, Y)] should find Y = b, c, d."""
        # nv
        _, _, _, Path = _terms(mod)
        m = _module(mod)
        p = Var()
        y = Var()
        goal = [Path(mint("a"), y)]
        results = []
        for _ in call("graph_program", p, module=m):
            prog = deref(p)
            count = 0
            for _ in call("solve", goal, prog, module=m):
                results.append(_deref_walk(y))
                count += 1
                if count >= 5:
                    break
        assert set(results[:3]) == {mint("b"), mint("c"), mint("d")}


# ── Inference counting: exact values ─────────────────────────────────────────


class TestSolveCount:

    def test_count_single_fact(self, mod):
        """Resolving a single fact takes 1 inference step."""
        # nv
        Natnum, _, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        count = Var()
        for _ in call("natnum_program", p, module=m):
            for _ in call("solve_count", [Natnum(0)], deref(p), count, module=m):
                assert deref(count) == 1
                return
        pytest.fail("no solution")

    def test_count_path_transitive(self, mod):
        """path(a,c) via edge(a,b) + path(b,c) via edge(b,c) = 4 steps."""
        # nv
        _, _, _, Path = _terms(mod)
        m = _module(mod)
        p = Var()
        count = Var()
        for _ in call("graph_program", p, module=m):
            for _ in call("solve_count", [Path(mint("a"), mint("c"))], deref(p), count, module=m):
                assert deref(count) == 4
                return
        pytest.fail("no solution")


# ── Depth-limited: boundary behaviour ────────────────────────────────────────


class TestSolveLimit:

    def test_depth_0_fails_on_any_goal(self, mod):
        """Depth 0 means no resolution steps allowed — any non-empty goal list fails."""
        # nv
        Natnum, _, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        for _ in call("natnum_program", p, module=m):
            results = list(call("solve_limit", [Natnum(0)], deref(p), 0, module=m))
            assert results == []
            return
        pytest.fail("no program")

    def test_exact_depth_succeeds(self, mod):
        """natnum(succ(succ(succ(0)))) needs exactly 4 steps."""
        # nv
        Natnum, succ, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        goal = [Natnum(succ(succ(succ(0))))]
        for _ in call("natnum_program", p, module=m):
            prog = deref(p)
            # depth 3 should fail
            assert list(call("solve_limit", goal, prog, 3, module=m)) == []
            # depth 4 should succeed
            assert len(list(call("solve_limit", goal, prog, 4, module=m))) > 0
            return
        pytest.fail("no program")


# ── Iterative deepening ─────────────────────────────────────────────────────


class TestSolveIterativeDeepening:

    def test_finds_path_in_cyclic_graph(self, mod):
        """Iterative deepening finds path(a,b) in graph with a→b→a cycle."""
        # nv
        _, _, _, Path = _terms(mod)
        m = _module(mod)
        p = Var()
        for _ in call("cyclic_program", p, module=m):
            results = []
            for _ in call("solve_iterative_deepening",
                          [Path(mint("a"), mint("b"))], deref(p), module=m):
                results.append(True)
                break  # just need one solution
            assert results == [True]
            return
        pytest.fail("no program")


# ── Proof tree ───────────────────────────────────────────────────────────────


class TestSolveTree:

    def test_fact_tree(self, mod):
        """Proof tree for a fact is [goal, []]."""
        # nv
        Natnum, _, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        tree = Var()
        for _ in call("natnum_program", p, module=m):
            for _ in call("solve_tree", [Natnum(0)], deref(p), tree, module=m):
                t = _deref_walk(tree)
                assert t == [[Natnum(0), []]]
                return
        pytest.fail("no solution")

    def test_recursive_tree_structure(self, mod):
        """Proof tree for natnum(succ(0)) has correct nesting."""
        # nv
        Natnum, succ, _, _ = _terms(mod)
        m = _module(mod)
        p = Var()
        tree = Var()
        for _ in call("natnum_program", p, module=m):
            for _ in call("solve_tree", [Natnum(succ(0))], deref(p), tree, module=m):
                t = _deref_walk(tree)
                assert len(t) == 1  # one goal in the list
                node = t[0]
                assert node[0] == Natnum(succ(0))  # the resolved goal
                assert len(node[1]) == 1  # one body goal proved
                sub = node[1][0]
                assert sub == [Natnum(0), []]  # the body fact
                return
        pytest.fail("no solution")

    def test_transitive_path_tree(self, mod):
        """Proof tree for path(a,c) shows edge(a,b) + path(b,c) subtree."""
        # nv
        _, _, Edge, Path = _terms(mod)
        m = _module(mod)
        p = Var()
        tree = Var()
        for _ in call("graph_program", p, module=m):
            for _ in call("solve_tree", [Path(mint("a"), mint("c"))], deref(p), tree, module=m):
                t = _deref_walk(tree)
                # Top-level: one node for path(a,c)
                assert len(t) == 1
                goal, subtree = t[0]
                assert goal == Path(mint("a"), mint("c"))
                # Subtree: edge(a,b) and path(b,c)
                assert len(subtree) == 2
                assert subtree[0] == [Edge(mint("a"), mint("b")), []]
                path_bc = subtree[1]
                assert path_bc[0] == Path(mint("b"), mint("c"))
                return
        pytest.fail("no solution")
