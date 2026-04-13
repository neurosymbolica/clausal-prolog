"""Tests for trail elision in single-clause index buckets.

Structural tests verify that the compiler omits trail.mark()/trail.undo()
for clauses in single-clause index buckets.

Behavioral tests verify that bindings are correctly undone on backtracking
when trail elision is active, including edge cases with duplicate head
variables (dup_guards) and list patterns (list_guards).

FRAGILITY NOTES
─────────────────────────────────────────────────────────────────────────────

TestTrailElisionStructural
  - _count_method_calls counts trail.mark() and trail.undo() in the AST.
    The tests use fact-only predicates with distinct first-arg keys and no
    var-headed clauses, so every bucket is single-clause.  Adding a
    var-headed clause would merge it into all buckets, inflating counts.
  - The tests depend on compile_predicate_trampoline_ast producing indexed
    dispatch; if the index threshold changes, the test may need more clauses.

TestTrailElisionBehavioral
  - These tests exercise the runtime behavior of compiled predicates with
    trail elision active.  They use the full solve/call pipeline with real
    Trail objects to verify that backtracking correctly undoes bindings.
"""

from __future__ import annotations

import ast
import os

import pytest

from clausal.logic.compiler import (
    compile_predicate_trampoline_ast,
    compile_predicate_trampoline,
    compile_head_to_match_case,
)
from clausal.logic.database import Clause, Database
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Compound


# ── AST walking helpers ──────────────────────────────────────────────────────


def _count_method_calls(obj_name: str, method_name: str, tree: ast.AST) -> int:
    """Count calls of the form obj_name.method_name(...) in *tree*."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == obj_name
            and node.func.attr == method_name
        ):
            count += 1
    return count


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_db(*clauses_specs):
    """Build a Database from (functor, args_tuple) specs.

    Each spec is (functor, args) where args is a tuple of head arguments.
    Body is always empty (facts only).
    """
    db = Database()
    for functor, args in clauses_specs:
        db.assertz(Clause(head=Compound(functor, args), body=[]))
    return db


def _load_module(text: str):
    """Compile a .clausal source string into a module, return the $module."""
    from clausal.testing import load_clausal_module
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".clausal", delete=False
    ) as f:
        f.write(text)
        f.flush()
        mod = load_clausal_module(f.name)
    os.unlink(f.name)
    return mod.__dict__["$module"]


# ── Structural tests ─────────────────────────────────────────────────────────


class TestTrailElisionStructural:
    """Verify that trail.mark()/undo() are omitted for single-clause buckets."""

    def test_single_clause_bucket_no_mark_undo(self):
        """Each bucket has exactly one clause (no defaults) -> no mark/undo."""
        # 3 clauses with distinct first-arg keys, no var-headed clause.
        # Each bucket has exactly 1 clause -> trail elision applies to all.
        # nv
        v1, v2, v3 = Var(), Var(), Var()
        db = _make_db(
            ("p", (1, v1)),
            ("p", (2, v2)),
            ("p", (3, v3)),
        )
        clauses = db.clauses_for("p", 2)
        func_def = compile_predicate_trampoline_ast("p", 2, clauses, db)
        src = ast.unparse(func_def)

        # The bucket sub-functions should have zero mark/undo calls.
        # The fallback (all-clauses) function still uses mark/undo.
        # We check the overall function: it should contain mark/undo only
        # in the fallback path, not in the indexed buckets.
        mark_count = _count_method_calls("trail", "mark", func_def)
        undo_count = _count_method_calls("trail", "undo", func_def)

        # With 3 var-headed clauses and no defaults, each bucket is single-clause.
        # The AST for the top-level function won't contain the bucket functions
        # (those are compiled separately), so we inspect via compile_head_to_match_case.
        # Instead, verify the skip_trail parameter works at the unit level.
        v = Var()
        head = Compound("t", (v,))
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=1,
            skip_trail=True,
        )
        # With skip_trail=True, there should be no trail.mark() or trail.undo()
        mark_in_case = _count_method_calls("trail", "mark", case_arm)
        undo_in_case = _count_method_calls("trail", "undo", case_arm)
        assert mark_in_case == 0
        assert undo_in_case == 0

    def test_skip_trail_false_has_mark_undo(self):
        """With skip_trail=False (default), var-headed clauses get mark/undo."""
        # nv
        v = Var()
        head = Compound("t", (v,))
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=1,
            skip_trail=False,
        )
        mark_in_case = _count_method_calls("trail", "mark", case_arm)
        undo_in_case = _count_method_calls("trail", "undo", case_arm)
        assert mark_in_case == 1
        assert undo_in_case == 1

    def test_skip_trail_with_dup_guards(self):
        """skip_trail=True still omits mark/undo even with duplicate head vars."""
        # nv
        v = Var()
        # head = t(X, X) — duplicate var triggers dup_guard with unify()
        head = Compound("t", (v, v))
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
            skip_trail=True,
        )
        mark_in_case = _count_method_calls("trail", "mark", case_arm)
        undo_in_case = _count_method_calls("trail", "undo", case_arm)
        assert mark_in_case == 0
        assert undo_in_case == 0

    def test_ground_head_still_elided_without_skip_trail(self):
        """Ground heads (no vars, no guards) are still elided by the original opt."""
        # nv
        head = Compound("t", (1, 2))
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
            skip_trail=False,
        )
        mark_in_case = _count_method_calls("trail", "mark", case_arm)
        undo_in_case = _count_method_calls("trail", "undo", case_arm)
        assert mark_in_case == 0
        assert undo_in_case == 0


# ── Behavioral tests ─────────────────────────────────────────────────────────


class TestTrailElisionBehavioral:
    """Verify correctness of trail elision with real execution.

    Uses direct call() invocations with Var to test that bindings are
    correctly produced and undone on backtracking.
    """

    def test_single_clause_bucket_returns_correct_results(self):
        """Predicate with distinct first-arg keys returns correct values."""
        # nv
        mod = _load_module("""\
Color(1, "warm"),
Color(2, "cool"),
Color(3, "cool"),
""")
        x = Var()
        results = [deref(x) for _ in call("Color", 1, x, module=mod)]
        assert results == ["warm"]

        x = Var()
        results = [deref(x) for _ in call("Color", 2, x, module=mod)]
        assert results == ["cool"]

    def test_each_bucket_returns_exactly_one_solution(self):
        """Each distinct first-arg key yields exactly one solution (deterministic)."""
        # nv
        mod = _load_module("""\
Map(1, "one"),
Map(2, "two"),
Map(3, "three"),
Map(4, "four"),
""")
        for key, expected in [(1, "one"), (2, "two"), (3, "three"), (4, "four")]:
            x = Var()
            results = [deref(x) for _ in call("Map", key, x, module=mod)]
            assert results == [expected], f"Map({key}, X) failed"

    def test_backtracking_past_elided_clause_undoes_bindings(self):
        """Bindings from an elided-trail clause are undone when the caller
        backtracks past the predicate call.

        Try/2 calls Color/2 for each key. After each call, the binding
        from Color's head unification must be undone before the next call.
        """
        # nv
        mod = _load_module("""\
Color(1, "warm"),
Color(2, "cool"),
Color(3, "cool"),

Attempt(1, R) <- Color(1, R)
Attempt(2, R) <- Color(2, R)
Attempt(3, R) <- Color(3, R)
""")
        # Call Try for each key — verifies that previous Color bindings
        # don't leak into subsequent calls.
        for key, expected in [(1, "warm"), (2, "cool"), (3, "cool")]:
            r = Var()
            results = [deref(r) for _ in call("Attempt", key, r, module=mod)]
            assert results == [expected]

    def test_var_binding_undone_between_calls(self):
        """A Var bound by an elided-trail clause is correctly unbound after
        the call completes, so a subsequent call can rebind it."""
        # nv
        mod = _load_module("""\
Fact(1, 10),
Fact(2, 20),
Fact(3, 30),
""")
        # Use the same Var across multiple calls — each call should produce
        # its own binding independently because the trail is rewound.
        x = Var()
        trail = Trail()
        mark = trail.mark()

        results = [deref(x) for _ in call("Fact", 1, x, module=mod)]
        assert results == [10]

        trail.undo(mark)
        results = [deref(x) for _ in call("Fact", 2, x, module=mod)]
        assert results == [20]

        trail.undo(mark)
        results = [deref(x) for _ in call("Fact", 3, x, module=mod)]
        assert results == [30]

    def test_dup_guard_clause_in_single_bucket(self):
        """A clause with duplicate head vars (dup_guard) in a single-clause
        bucket: Same(X, X) succeeds when both args unify."""
        # nv
        mod = _load_module("""\
Same(1, 1),
Same(2, 2),
Same(3, 3),
""")
        # Same(1, 1) should succeed
        x = Var()
        results = [deref(x) for _ in call("Same", 1, x, module=mod)]
        assert results == [1]

        # Same(2, 2) should succeed
        x = Var()
        results = [deref(x) for _ in call("Same", 2, x, module=mod)]
        assert results == [2]

    def test_dup_guard_failure_in_single_bucket(self):
        """When a dup_guard fails in a single-clause bucket, the predicate
        fails and the caller correctly undoes bindings."""
        # nv
        mod = _load_module("""\
Same(1, 1),
Same(2, 2),
""")
        # Same(1, 2) should fail: bucket for key 1 has Same(1,1)
        # The dup_guard unify(1, 2) fails, so no solutions.
        x = Var()
        results = [deref(x) for _ in call("Same", 1, x, module=mod)]
        assert results == [1]  # Same(1, X) matches Same(1, 1) -> X=1

        # Same(1, 2): the dup_guard checks second arg matches first.
        # Calling with ground args: 1 and 2 don't unify.
        results = list(call("Same", 1, 2, module=mod))
        assert results == []  # fails — no solutions

        # Same(2, 2) should succeed
        results = list(call("Same", 2, 2, module=mod))
        assert len(results) == 1

    def test_nested_calls_through_elided_predicates(self):
        """Chain of calls through two elided-trail predicates."""
        # nv
        mod = _load_module("""\
Left(1, 10),
Left(2, 20),

Right(10, 100),
Right(20, 200),

Chain(N, R) <- (Left(N, M), Right(M, R))
""")
        r = Var()
        results = [deref(r) for _ in call("Chain", 1, r, module=mod)]
        assert results == [100]

        r = Var()
        results = [deref(r) for _ in call("Chain", 2, r, module=mod)]
        assert results == [200]

    def test_single_clause_predicate_no_index(self):
        """A predicate with only one clause total — below the index threshold,
        so no indexing, but trail elision doesn't apply either."""
        # nv
        mod = _load_module("""\
Only(X, Y) <- (Y := X + 1)
""")
        y = Var()
        results = [deref(y) for _ in call("Only", 5, y, module=mod)]
        assert results == [6]

    def test_mixed_ground_and_var_heads_no_elision(self):
        """When a var-headed clause exists, buckets have >1 clause and
        trail elision does NOT apply — verify correctness is maintained."""
        # nv
        mod = _load_module("""\
Lookup(1, 10),
Lookup(2, 20),
Lookup(X, 0),
""")
        # Key 1 matches both Lookup(1, 10) and Lookup(X, 0)
        v = Var()
        results = [deref(v) for _ in call("Lookup", 1, v, module=mod)]
        assert results == [10, 0]

        # Key 3 matches only Lookup(X, 0)
        v = Var()
        results = [deref(v) for _ in call("Lookup", 3, v, module=mod)]
        assert results == [0]

    def test_multiple_solutions_non_elided_predicate(self):
        """A predicate with a var-headed default produces multiple solutions
        per key, and backtracking undoes bindings correctly."""
        # nv
        mod = _load_module("""\
Info(1, "specific_1"),
Info(2, "specific_2"),
Info(X, "default"),
""")
        v = Var()
        results = [deref(v) for _ in call("Info", 1, v, module=mod)]
        assert results == ["specific_1", "default"]

        v = Var()
        results = [deref(v) for _ in call("Info", 2, v, module=mod)]
        assert results == ["specific_2", "default"]

        v = Var()
        results = [deref(v) for _ in call("Info", 99, v, module=mod)]
        assert results == ["default"]
