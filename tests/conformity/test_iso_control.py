"""ISO Prolog conformity: control constructs.

ISO §7.8 — conjunction, disjunction, if-then(-else), negation, cut, true, fail.

Clausal equivalents:
  ,/2   (conjunction)   → and
  ;/2   (disjunction)   → or
  \\+/1  (negation)      → not
  true/0               → True (Python literal, only at top level of solve)
  fail/0               → False (Python literal, only at top level of solve)

Not available:
  !/0   (cut)           → no cut; use once() or other control
  ->/2  (if-then)       → no direct syntax; use (cond and then) or or
  call/1..N             → call() API function, not a goal term
  catch/throw           → no exception-based control
  halt/0..1             → no process termination goal

Differences from ISO:
  - No cut (!).  Clausal's search is always exhaustive per-clause.
    Use once() or deterministic predicates for commit behavior.
  - No if-then-else (C -> T ; E).  Use Python-style or/and combinations.
  - True/False work at the top level of solve() but cannot be used inside
    And/Or/Not goal terms (limitation of the compiler).
  - Conjunction associates right: (a and b and c) = And(a, And(b, c)).
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Clause, Module
from clausal.logic.compiler import compile_predicate_trampoline as compile_predicate
from clausal.logic.solve import solve, once, call
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import (
    And, Or, Not,
    Unify as Is,
    Call, LoadName, Compound,
)


def _goal_succeeds(goal, mod=None):
    if mod is None:
        mod = Module("test")
    return once(goal, mod) is not None


def _goal_fails(goal, mod=None):
    return not _goal_succeeds(goal, mod)


def _solve_binding(goal, var, mod=None):
    if mod is None:
        mod = Module("test")
    return [deref(var) for _ in solve(goal, mod)]


def _solution_count(goal, mod=None):
    if mod is None:
        mod = Module("test")
    return len(list(solve(goal, mod)))


# ── true/0, fail/0 ───────────────────────────────────────────────────────────


class TestTrueFail:
    """ISO §7.8.1 (true), §7.8.2 (fail)."""

    def test_true_succeeds(self):
        """ISO: true succeeds.  Clausal: True at top level of solve."""
        assert _goal_succeeds(True)

    def test_fail_fails(self):
        """ISO: fail fails.  Clausal: False at top level of solve."""
        assert _goal_fails(False)

    # Note: And(True, False) etc. cannot be tested because True/False
    # are only handled at the top level of solve(), not inside goal terms.
    # This is a known limitation documented above.


# ── Conjunction (and) ────────────────────────────────────────────────────────


class TestConjunction:
    """ISO §7.8.5 — ,/2."""

    def test_simple_conjunction(self):
        """ISO: (X = 1, Y = 2) succeeds with X=1, Y=2."""
        x, y = Var(), Var()
        goal = And(
            left=Is(left=x, right=1),
            right=Is(left=y, right=2),
        )
        mod = Module("test")
        results = []
        for _ in solve(goal, mod):
            results.append((deref(x), deref(y)))
        assert results == [(1, 2)]

    def test_conjunction_first_fails(self):
        """(a = b, X = 1) fails because first goal fails."""
        x = Var()
        goal = And(
            left=Is(left="a", right="b"),
            right=Is(left=x, right=1),
        )
        assert _goal_fails(goal)

    def test_conjunction_second_fails(self):
        """(X = 1, a = b) fails because second goal fails."""
        x = Var()
        goal = And(
            left=Is(left=x, right=1),
            right=Is(left="a", right="b"),
        )
        assert _goal_fails(goal)

    def test_conjunction_backtracking(self):
        """Conjunction backtracks into first goal.
        member(X, [1,2]) and member(Y, [a,b]) generates 4 solutions."""
        x, y = Var(), Var()
        goal = And(
            left=Call(func=LoadName(name="In"), args=[x, [1, 2]], kwargs=[]),
            right=Call(func=LoadName(name="In"), args=[y, ["a", "b"]], kwargs=[]),
        )
        mod = Module("test")
        solutions = []
        for _ in solve(goal, mod):
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 4
        assert (1, "a") in solutions
        assert (2, "b") in solutions

    def test_triple_conjunction(self):
        """(X = 1, Y = 2, Z = 3) — three-way conjunction."""
        x, y, z = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=1),
            right=And(
                left=Is(left=y, right=2),
                right=Is(left=z, right=3),
            ),
        )
        mod = Module("test")
        results = []
        for _ in solve(goal, mod):
            results.append((deref(x), deref(y), deref(z)))
        assert results == [(1, 2, 3)]


# ── Disjunction (or) ─────────────────────────────────────────────────────────


class TestDisjunction:
    """ISO §7.8.6 — ;/2."""

    def test_first_branch_succeeds(self):
        """(X = 1 ; X = 2) — first branch produces X=1."""
        x = Var()
        goal = Or(
            left=Is(left=x, right=1),
            right=Is(left=x, right=2),
        )
        results = _solve_binding(goal, x)
        assert 1 in results

    def test_second_branch_succeeds(self):
        """Both branches produce solutions."""
        x = Var()
        goal = Or(
            left=Is(left=x, right=1),
            right=Is(left=x, right=2),
        )
        results = _solve_binding(goal, x)
        assert results == [1, 2]

    def test_first_fails_second_succeeds(self):
        """(a = b ; X = 1) — first fails, second succeeds."""
        x = Var()
        goal = Or(
            left=Is(left="a", right="b"),
            right=Is(left=x, right=1),
        )
        results = _solve_binding(goal, x)
        assert results == [1]

    def test_both_fail(self):
        """(a = b ; c = d) fails."""
        goal = Or(
            left=Is(left="a", right="b"),
            right=Is(left="c", right="d"),
        )
        assert _goal_fails(goal)

    def test_both_succeed_two_solutions(self):
        """(X = 1 ; X = 2) has two solutions."""
        x = Var()
        goal = Or(
            left=Is(left=x, right=1),
            right=Is(left=x, right=2),
        )
        assert _solution_count(goal) == 2

    def test_disjunction_with_conjunction(self):
        """(X = 1, Y = a ; X = 2, Y = b) has two solutions."""
        x, y = Var(), Var()
        goal = Or(
            left=And(left=Is(left=x, right=1), right=Is(left=y, right="a")),
            right=And(left=Is(left=x, right=2), right=Is(left=y, right="b")),
        )
        mod = Module("test")
        solutions = []
        for _ in solve(goal, mod):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(1, "a"), (2, "b")]


# ── Negation as failure (not) ────────────────────────────────────────────────


class TestNegation:
    """ISO §8.15.1 — \\+/1."""

    def test_not_failed_unification(self):
        """ISO: \\+(1 = 2) succeeds."""
        assert _goal_succeeds(Not(operand=Is(left=1, right=2)))

    def test_not_successful_unification(self):
        """ISO: \\+(1 = 1) fails."""
        assert _goal_fails(Not(operand=Is(left=1, right=1)))

    def test_naf_does_not_bind(self):
        """Negation as failure does NOT bind variables.
        \\+(X = a) fails because X = a WOULD succeed."""
        assert _goal_fails(Not(operand=Is(left=Var(), right="a")))

    def test_naf_with_member(self):
        """not(member(d, [a,b,c])) succeeds — d is not in the list."""
        goal = Not(operand=Call(
            func=LoadName(name="In"),
            args=["d", ["a", "b", "c"]],
            kwargs=[],
        ))
        assert _goal_succeeds(goal)

    def test_naf_with_member_present(self):
        """not(member(b, [a,b,c])) fails — b IS in the list."""
        goal = Not(operand=Call(
            func=LoadName(name="In"),
            args=["b", ["a", "b", "c"]],
            kwargs=[],
        ))
        assert _goal_fails(goal)

    def test_double_negation_succeeds(self):
        """not(not(1 = 1)) succeeds: inner succeeds, outer negation fails,
        but outer-outer negation succeeds."""
        assert _goal_succeeds(Not(operand=Not(operand=Is(left=1, right=1))))

    def test_double_negation_fails(self):
        """not(not(1 = 2)) fails: inner (1=2) fails, not(1=2) succeeds,
        not(not(1=2)) fails."""
        assert _goal_fails(Not(operand=Not(operand=Is(left=1, right=2))))


# ── Cut — NOT AVAILABLE ──────────────────────────────────────────────────────
# ISO §7.8.4 — !/0
#
# Clausal has no cut.  The equivalent is using once() or structuring
# predicates to be deterministic.


class TestNoCut:
    """Document that cut is not available."""

    def test_once_as_soft_cut(self):
        """once() gives first solution only — similar to (Goal, !) in Prolog."""
        x = Var()
        goal = Or(
            left=Is(left=x, right=1),
            right=Is(left=x, right=2),
        )
        mod = Module("test")
        trail = once(goal, mod)
        assert trail is not None
        # Only one solution returned (we can't check the binding after once,
        # but we know at least one solution exists).


# ── If-Then-Else — NOT AVAILABLE as syntax ────────────────────────────────────
# ISO §7.8.7/8 — (C -> T ; E), (C -> T)
#
# Clausal has no -> operator.  The pattern can be approximated:
#   (cond and then) or (not(cond) and else)
# but this evaluates cond twice.


class TestNoIfThenElse:
    """Document if-then-else approximation."""

    def test_if_then_else_via_or_true_branch(self):
        """Approximate: if X=1 then Y="one" else Y="other".
        Via: (X is 1 and Y is "one") or (not(X is 1) and Y is "other").
        X already unified with 1, so true branch taken."""
        x, y = Var(), Var()
        goal = And(
            left=Is(left=x, right=1),
            right=Or(
                left=And(
                    left=Is(left=x, right=1),
                    right=Is(left=y, right="one"),
                ),
                right=And(
                    left=Not(operand=Is(left=x, right=1)),
                    right=Is(left=y, right="other"),
                ),
            ),
        )
        mod = Module("test")
        results = []
        for _ in solve(goal, mod):
            results.append(deref(y))
        assert "one" in results


# ── User-defined predicates with multiple clauses ─────────────────────────────


class TestMultipleClauses:
    """Clausal predicates with multiple clauses behave like Prolog
    predicates: each clause is tried in order on backtracking."""

    def test_multiple_facts(self):
        """color(red). color(green). color(blue)."""
        mod = Module("test")
        db = mod.db
        for c in ["red", "green", "blue"]:
            v = Var()
            db.assertz(Clause(
                head=Compound("color", (v,)),
                body=[Is(left=v, right=c)],
            ))
        compile_predicate("color", 1, db.clauses_for("color", 1), db)

        x = Var()
        results = [
            deref(x)
            for _ in call("color", x, module=mod)
        ]
        assert results == ["red", "green", "blue"]

    def test_recursive_predicate(self):
        """ancestor(X, Y) :- parent(X, Y).
        ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y)."""
        mod = Module("test")
        db = mod.db

        # parent facts
        for p, c in [("a", "b"), ("b", "c"), ("c", "d")]:
            pv = Var()
            db.assertz(Clause(
                head=Compound("parent", (p, pv)),
                body=[Is(left=pv, right=c)],
            ))
        compile_predicate("parent", 2, db.clauses_for("parent", 2), db)

        # ancestor base case
        x, y = Var(), Var()
        db.assertz(Clause(
            head=Compound("ancestor", (x, y)),
            body=[Call(func=LoadName(name="parent"), args=[x, y], kwargs=[])],
        ))
        # ancestor recursive
        x2, y2, z2 = Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("ancestor", (x2, y2)),
            body=[
                Call(func=LoadName(name="parent"), args=[x2, z2], kwargs=[]),
                Call(func=LoadName(name="ancestor"), args=[z2, y2], kwargs=[]),
            ],
        ))
        compile_predicate("ancestor", 2, db.clauses_for("ancestor", 2), db)

        # "a" is ancestor of b, c, d
        dest = Var()
        results = [
            deref(dest)
            for _ in call("ancestor", "a", dest, module=mod)
        ]
        assert set(results) == {"b", "c", "d"}
