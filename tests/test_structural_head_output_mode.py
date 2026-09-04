"""Regression tests: structural literals in a ruled-clause head must bind into a
caller Var (output / var-query mode), not only match an already-equal argument.

Follow-up to the equality-vs-unification audit
(todo/done/equality-vs-unification-audit.md) and the mode-coverage audit
(todo/audit-tests-input-output-mode-coverage.md). Structural head args
(Compound / functor-instance / nested compound / list) are hoisted at assert
time into a fresh Var + a prepended Unify goal, so the var-query direction is
handled by unification in the body — these end-to-end tests pin that. The atomic
head kinds are covered by test_numeric_head_literal.py; the structural kinds were
the named coverage gap.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(scope="module")
def mod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "structural_head_output_mode.clausal"
    )
    return _load_module(
        "structural_head_output_mode_mod", fixture
    ).__dict__["$module"]


def _collect(name, out_vars, *args, module):
    """Snapshot out_vars' bindings inside the solution loop (undone on resume)."""
    snapshots = []
    for _ in call(name, *args, module=module):
        snapshots.append(tuple(deref(v) for v in out_vars))
    return snapshots


def _ctor(mod, name):
    """A cell CONSTRUCTOR for a declared term functor.

    P3-2 Task 2 (THE FLIP, R6): a declared data functor's name binds its
    interned spelling, not a class -- ``mod.module_dict["point"]`` is the str
    ``"point"``, and the module's clauses build and match the cell
    ``("point", X, Y)``.  Returning a builder keeps every call site below
    reading as the term it constructs, and the equality assertions compare
    cells to cells.
    """
    assert mod.module_dict[name] == name   # R6: the binding IS the spelling
    return lambda *args: (name, *args)


class TestStructuralHeadOutputMode:
    def test_compound_head_query_as_var(self, mod):
        point = _ctor(mod, "point")
        P = Var()
        assert _collect("pt", [P], P, module=mod) == [(point(1, 2),)]

    def test_functor_instance_head_query_as_var(self, mod):
        rgb = _ctor(mod, "rgb")
        C = Var()
        assert _collect("col", [C], C, module=mod) == [(rgb(255, 0, 0),)]

    def test_nested_compound_head_query_as_var(self, mod):
        point = _ctor(mod, "point")
        line = _ctor(mod, "line")
        L = Var()
        assert _collect("seg", [L], L, "diag", module=mod) == [
            (line(point(0, 0), point(3, 4)),)
        ]

    def test_list_head_query_as_var(self, mod):
        L = Var()
        assert _collect("lst", [L], L, module=mod) == [([1, 2, 3],)]

    def test_compound_head_partial_input_couples_inner_var(self, mod):
        """Caller supplies point(1, Y) with Y unbound — the inner Var couples."""
        point = _ctor(mod, "point")
        Y = Var()
        assert _collect("pt", [Y], point(1, Y), module=mod) == [(2,)]

    def test_compound_head_relational_multiple_solutions(self, mod):
        point = _ctor(mod, "point")
        P = Var()
        assert _collect("shape", [P], P, module=mod) == [
            (point(0, 0),), (point(9, 9),)
        ]

    def test_compound_head_input_mode_still_matches(self, mod):
        """Input mode (caller supplies the ground compound) still works."""
        point = _ctor(mod, "point")
        assert sum(1 for _ in call("pt", point(1, 2), module=mod)) == 1
        # A non-matching ground compound yields no solution.
        assert sum(1 for _ in call("pt", point(9, 9), module=mod)) == 0
