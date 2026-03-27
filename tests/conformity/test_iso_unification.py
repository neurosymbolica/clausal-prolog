"""ISO Prolog conformity: unification (=/2, \\=/2, ==/2, \\==/2).

ISO §8.2.1 =/2 (unification)
ISO §8.2.2 \\=/2 (not unifiable)
ISO §8.2.3 ==/2 (arithmetic equality (CLP(FD)))
ISO §8.2.4 \\==/2 (arithmetic inequality (CLP(FD)))

Clausal equivalents:
  is    → unification (=/2)
  is not → does-not-unify (\\=/2)
  ==    → arithmetic equality (CLP(FD)) (==/2)
  !=    → arithmetic inequality (CLP(FD)) (\\==/2)

Differences from ISO:
  - Prolog atoms map to Python strings in clausal.
  - Prolog lists ./2 map to Python lists.
  - No occurs check by default (same as most Prolog implementations).
  - Arithmetic terms are structural in unification context (not evaluated).
  - C-level unify() does NOT recurse into Compound args — use
    structural_unify() for deep Compound unification.
  - Python's 1 == 1.0 is True, so arithmetic equality (==) treats
    int and float as equal, unlike ISO Prolog.
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Module
from clausal.logic.solve import solve, once
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.builtins import structural_unify
from clausal.terms import (
    Compound, Unify as Is, DoesNotUnify, ArithEq, ArithNeq,
    And, Call, LoadName, Add,
)


def _goal_succeeds(goal, mod=None):
    if mod is None:
        mod = Module("test")
    return once(goal, mod) is not None


def _goal_fails(goal, mod=None):
    return not _goal_succeeds(goal, mod)


def _solve_binding(goal, var, mod=None):
    """Collect deref'd values of var during solve iteration."""
    if mod is None:
        mod = Module("test")
    return [deref(var) for _ in solve(goal, mod)]


# ── =/2 (unification via 'is') ───────────────────────────────────────────────


class TestUnification:
    """ISO §8.2.1 — =/2."""

    def test_atom_unifies_with_itself(self):
        """ISO: 'a' = 'a' succeeds."""
        assert _goal_succeeds(Is(left="a", right="a"))

    def test_integer_unifies_with_itself(self):
        """ISO: 1 = 1 succeeds."""
        assert _goal_succeeds(Is(left=1, right=1))

    def test_float_unifies_with_itself(self):
        assert _goal_succeeds(Is(left=1.0, right=1.0))

    def test_var_unifies_with_atom(self):
        """ISO: X = a succeeds with X = a."""
        x = Var()
        results = _solve_binding(Is(left=x, right="a"), x)
        assert results == ["a"]

    def test_var_unifies_with_integer(self):
        x = Var()
        results = _solve_binding(Is(left=x, right=42), x)
        assert results == [42]

    def test_var_unifies_with_var(self):
        """ISO: X = Y succeeds (aliasing)."""
        x, y = Var(), Var()
        goal = Is(left=x, right=y)
        assert _goal_succeeds(goal)

    def test_different_atoms_fail(self):
        """ISO: a = b fails."""
        assert _goal_fails(Is(left="a", right="b"))

    def test_different_integers_fail(self):
        assert _goal_fails(Is(left=1, right=2))

    def test_int_vs_float(self):
        """ISO: 1 = 1.0 fails (distinct types).
        DIFFERS: clausal C-level unify uses Python ==, so 1 == 1.0 succeeds.
        This is a known difference."""
        # in_ ISO this would fail; in clausal it succeeds due to Python semantics.
        assert _goal_succeeds(Is(left=1, right=1.0))

    def test_different_functors_fail(self):
        """ISO: f(a) = g(a) fails."""
        assert _goal_fails(Is(
            left=Compound("f", ("a",)),
            right=Compound("g", ("a",)),
        ))

    def test_different_arity_fail(self):
        """ISO: f(a) = f(a, b) fails."""
        assert _goal_fails(Is(
            left=Compound("f", ("a",)),
            right=Compound("f", ("a", "b")),
        ))

    def test_list_unification(self):
        """ISO: [a|[]] = [a] succeeds (test 219 in conformity suite)."""
        assert _goal_succeeds(Is(left=["a"], right=["a"]))

    def test_list_unify_with_var(self):
        """Unify a Var with a list."""
        x = Var()
        results = _solve_binding(Is(left=x, right=[1, 2, 3]), x)
        assert results == [[1, 2, 3]]

    def test_number_syntax_equivalences(self):
        """ISO test 174-175: -1 = -0x1, t(0b1,0o1,0x1) = t(1,1,1).
        in_ Python, these are the same integer values."""
        assert -1 == -0x1  # Python-level
        assert 0b1 == 0o1 == 0x1 == 1
        # Logic-level:
        assert _goal_succeeds(Is(left=-1, right=-0x1))
        assert _goal_succeeds(Is(
            left=Compound("t", (0b1, 0o1, 0x1)),
            right=Compound("t", (1, 1, 1)),
        ))

    def test_arithmetic_is_structural(self):
        """Arithmetic expressions unify structurally, NOT by value.
        1+2 does NOT unify with 3.  This differs from Prolog's is/2
        but matches =/2 behavior."""
        assert _goal_fails(Is(left=Add(left=1, right=2), right=3))

    def test_ground_compound_unification(self):
        """Same ground Compound unifies (via ==)."""
        assert _goal_succeeds(Is(
            left=Compound("f", (1, 2)),
            right=Compound("f", (1, 2)),
        ))


# ── Compound unification with Vars (structural_unify) ────────────────────────
# C-level unify() does not recurse into Compound args.
# structural_unify() provides deep unification for Compound/KWTerm.


class TestStructuralUnify:
    """Test deep Compound unification via structural_unify (Python level).

    These correspond to ISO =/2 tests involving Compound terms with
    variables, which would work in Prolog's built-in unification but
    require structural_unify in clausal.
    """

    def test_compound_var_args(self):
        """ISO: f(X, b) = f(a, Y) → X=a, Y=b."""
        x, y = Var(), Var()
        trail = Trail()
        left = Compound("f", (x, "b"))
        right = Compound("f", ("a", y))
        assert structural_unify(left, right, trail)
        assert deref(x) == "a"
        assert deref(y) == "b"

    def test_nested_compound(self):
        """ISO: f(g(X)) = f(g(a)) → X=a."""
        x = Var()
        trail = Trail()
        left = Compound("f", (Compound("g", (x,)),))
        right = Compound("f", (Compound("g", ("a",)),))
        assert structural_unify(left, right, trail)
        assert deref(x) == "a"

    def test_different_functors_fail(self):
        trail = Trail()
        assert not structural_unify(
            Compound("f", (1,)),
            Compound("g", (1,)),
            trail,
        )

    def test_different_arity_fail(self):
        trail = Trail()
        assert not structural_unify(
            Compound("f", (1,)),
            Compound("f", (1, 2)),
            trail,
        )

    def test_var_aliases(self):
        """ISO: f(X, X) = f(a, a) succeeds."""
        x = Var()
        trail = Trail()
        left = Compound("f", (x, x))
        right = Compound("f", ("a", "a"))
        assert structural_unify(left, right, trail)
        assert deref(x) == "a"

    def test_var_aliases_fail(self):
        """ISO: f(X, X) = f(a, b) fails (X can't be both a and b)."""
        x = Var()
        trail = Trail()
        left = Compound("f", (x, x))
        right = Compound("f", ("a", "b"))
        assert not structural_unify(left, right, trail)


# ── \=/2 (does-not-unify via 'is not') ───────────────────────────────────────


class TestDoesNotUnify:
    """``is not`` now has dif/2 semantics (constraint), not ISO \\=/2 (immediate).

    dif(X, Y) succeeds when X and Y *can* remain different, posting a
    constraint if they are not yet ground.  Use ``not (X is Y)`` for
    immediate \\=/2 behavior.
    """

    def test_different_atoms(self):
        """dif(a, b) succeeds — structurally incompatible."""
        assert _goal_succeeds(DoesNotUnify(left="a", right="b"))

    def test_same_atom_fails(self):
        """dif(a, a) fails — already identical."""
        assert _goal_fails(DoesNotUnify(left="a", right="a"))

    def test_var_and_atom_succeeds_with_constraint(self):
        """dif(X, a) succeeds — posts constraint (X is not yet 'a')."""
        assert _goal_succeeds(DoesNotUnify(left=Var(), right="a"))

    def test_different_numbers(self):
        assert _goal_succeeds(DoesNotUnify(left=1, right=2))

    def test_different_arity(self):
        assert _goal_succeeds(DoesNotUnify(
            left=Compound("f", ("a",)),
            right=Compound("f", ("a", "b")),
        ))


# ── ==/2 (arithmetic equality (CLP(FD))) ─────────────────────────────────────


class TestArithEquality:
    """ISO §8.2.3 — ==/2 (arithmetic equality (CLP(FD))).
    Posts CLP(FD) equality constraint; for ground terms behaves like ==."""

    def test_same_atom(self):
        assert _goal_succeeds(ArithEq(left="a", right="a"))

    def test_different_atoms(self):
        assert _goal_fails(ArithEq(left="a", right="b"))

    def test_same_integer(self):
        assert _goal_succeeds(ArithEq(left=42, right=42))

    def test_int_vs_float(self):
        """ISO: 1 \\== 1.0 (structurally different).
        DIFFERS: Python 1 == 1.0 is True, so clausal treats them as
        arithmetically equal."""
        assert _goal_succeeds(ArithEq(left=1, right=1.0))

    def test_var_vs_var_clpfd(self):
        """V2-6: == is CLP(FD). Two unbound Vars constrained to be equal → succeeds."""
        assert _goal_succeeds(ArithEq(left=Var(), right=Var()))

    def test_var_vs_var_same(self):
        """Same Var is arithmetically equal to itself."""
        x = Var()
        assert _goal_succeeds(ArithEq(left=x, right=x))

    def test_same_compound(self):
        assert _goal_succeeds(ArithEq(
            left=Compound("f", (1, 2)),
            right=Compound("f", (1, 2)),
        ))

    def test_different_compound_args(self):
        assert _goal_fails(ArithEq(
            left=Compound("f", (1,)),
            right=Compound("f", (2,)),
        ))


# ── \==/2 (arithmetic inequality (CLP(FD))) ──────────────────────────────────


class TestArithInequality:
    """ISO §8.2.4 — \\==/2 (arithmetic inequality (CLP(FD)))."""

    def test_different_atoms(self):
        assert _goal_succeeds(ArithNeq(left="a", right="b"))

    def test_same_atom(self):
        assert _goal_fails(ArithNeq(left="a", right="a"))

    def test_var_vs_atom(self):
        """An unbound Var is arithmetically different from an atom."""
        assert _goal_succeeds(ArithNeq(left=Var(), right="a"))

    def test_two_vars(self):
        """Two different Vars are arithmetically different."""
        assert _goal_succeeds(ArithNeq(left=Var(), right=Var()))
