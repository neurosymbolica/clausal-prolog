"""ISO Prolog conformity: Python-level infrastructure for unification.

Behavior tests have moved to ``tests/conformity/iso_unification.clausal``.
What remains here needs Python-level access:

- ``structural_unify()`` deep unification (C ``unify()`` does not recurse into
  Compound args; ``structural_unify`` is a Python-level helper).
- ``structural_eq()`` runtime function over ``SegList`` / ``DictTerm`` /
  ``SetTerm``, which cannot be embedded as literal AST args in ``.clausal``.
- Tests that assert on post-goal variable state via ``is_var(deref(x))``.
"""

from __future__ import annotations

from clausal.logic.database import Module
from clausal.logic.solve import once
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.builtins import structural_unify
from clausal.terms import StructuralEq, SegList, ConcreteSeg, VarSeg, DictTerm, SetTerm


def _goal_succeeds(goal, mod=None):
    if mod is None:
        mod = Module("test")
    return once(goal, mod) is not None


def _goal_fails(goal, mod=None):
    return not _goal_succeeds(goal, mod)


# ── structural_unify (Python-level deep unification) ────────────────────────


class TestStructuralUnify:
    """Deep Compound unification — C-level ``unify()`` does not recurse, so
    ``structural_unify()`` is a Python-level helper tested here directly."""

    def test_compound_var_args(self):
        x, y = Var(), Var()
        trail = Trail()
        left = ("f", x, "b")
        right = ("f", "a", y)
        assert structural_unify(left, right, trail)
        assert deref(x) == "a"
        assert deref(y) == "b"

    def test_nested_compound(self):
        x = Var()
        trail = Trail()
        left = ("f", ("g", x))
        right = ("f", ("g", "a"))
        assert structural_unify(left, right, trail)
        assert deref(x) == "a"

    def test_different_functors_fail(self):
        trail = Trail()
        assert not structural_unify(("f", 1), ("g", 1), trail)

    def test_different_arity_fail(self):
        trail = Trail()
        assert not structural_unify(("f", 1), ("f", 1, 2), trail)

    def test_var_aliases(self):
        x = Var()
        trail = Trail()
        assert structural_unify(("f", x, x), ("f", "a", "a"), trail)
        assert deref(x) == "a"

    def test_var_aliases_fail(self):
        x = Var()
        trail = Trail()
        assert not structural_unify(
            ("f", x, x), ("f", "a", "b"), trail
        )


# ── structural_eq runtime over SegList / DictTerm / SetTerm ─────────────────


class TestStructuralEqRuntimeTypes:
    """``SegList``, ``DictTerm`` and ``SetTerm`` cannot be embedded as literal
    AST arguments in ``.clausal`` source, so the runtime ``structural_eq``
    function is exercised here directly."""

    def test_seglist_same(self):
        from clausal.logic.constraints import structural_eq as seq
        assert seq(SegList([ConcreteSeg([1, 2, 3])]), SegList([ConcreteSeg([1, 2, 3])]))

    def test_seglist_different(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(SegList([ConcreteSeg([1, 2])]), SegList([ConcreteSeg([1, 3])]))

    def test_seglist_with_same_var(self):
        from clausal.logic.constraints import structural_eq as seq
        x = Var()
        assert seq(
            SegList([ConcreteSeg([1]), VarSeg(x)]),
            SegList([ConcreteSeg([1]), VarSeg(x)]),
        )

    def test_seglist_with_different_vars(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(
            SegList([ConcreteSeg([1]), VarSeg(Var())]),
            SegList([ConcreteSeg([1]), VarSeg(Var())]),
        )

    def test_dictterm_same(self):
        from clausal.logic.constraints import structural_eq as seq
        assert seq(DictTerm({"a": 1, "b": 2}), DictTerm({"a": 1, "b": 2}))

    def test_dictterm_different_values(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(DictTerm({"a": 1}), DictTerm({"a": 2}))

    def test_dictterm_different_keys(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(DictTerm({"a": 1}), DictTerm({"b": 1}))

    def test_dictterm_var_value_same_var(self):
        from clausal.logic.constraints import structural_eq as seq
        x = Var()
        assert seq(DictTerm({"k": x}), DictTerm({"k": x}))

    def test_dictterm_var_value_different_vars(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(DictTerm({"k": Var()}), DictTerm({"k": Var()}))

    def test_setterm_same(self):
        from clausal.logic.constraints import structural_eq as seq
        assert seq(SetTerm({1, 2, 3}), SetTerm({1, 2, 3}))

    def test_setterm_different(self):
        from clausal.logic.constraints import structural_eq as seq
        assert not seq(SetTerm({1, 2}), SetTerm({1, 3}))


# ── StructuralEq AST node: Python-state side-effect checks ──────────────────


class TestStructuralEqSideEffects:
    """Assertions on variable state after a StructuralEq goal — require
    Python-level ``deref``/``is_var`` access."""

    def test_no_binding(self):
        """StructuralEq must NOT bind variables — an unbound Var vs atom fails
        and the Var stays unbound afterwards."""
        x = Var()
        assert _goal_fails(StructuralEq(left=x, right="a"))
        assert is_var(deref(x))

    def test_bound_var_equals_value(self):
        """A Var pre-bound at the Python layer to 5 is structurally equal to 5."""
        x = Var()
        t = Trail()
        unify(x, 5, t)
        assert _goal_succeeds(StructuralEq(left=x, right=5))
