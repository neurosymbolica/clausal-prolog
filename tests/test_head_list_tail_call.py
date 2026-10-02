"""Regression tests: a bare-list literal in a ruled-clause head must bind into a
caller Var (output mode) even when the clause body ends in a dispatched call.

Bug (2026-08-07): list-literal head args compile to the two-phase list-guard
machinery — input destructuring before the body, deferred output construction
(`_head_list_unify_output`) wrapped around each solution yield. Continuation-TCO
passed the caller's own ``_proceed`` to a tail-position sub-call's
StepGenerator, so solutions bypassed the clause frame and the deferred output
guard never ran: the query SUCCEEDED but handed back an unbound Var. The TCO
gate `_head_has_deferred_pattern` only recognised star-lists (``[H, *T]``), not
star-free bare lists, which defer output-mode unification all the same.
See todo/head-list-of-local-atoms-never-binds.md.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref, is_var, unify


@pytest.fixture(scope="module")
def pymod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "head_list_tail_call.seam"
    )
    return _load_module("head_list_tail_call_mod", fixture)


@pytest.fixture(scope="module")
def mod(pymod):
    return pymod.__dict__["$module"]


def _collect(name, out_vars, *args, module):
    """Run a query and snapshot the out_vars' bindings inside the solution loop
    (bindings are undone once the generator resumes/exits)."""
    snapshots = []
    for _ in call(name, *args, module=module):
        snapshots.append(tuple(deref(v) for v in out_vars))
    return snapshots


def _count(name, *args, module):
    return sum(1 for _ in call(name, *args, module=module))


def _atoms(pymod):
    return pymod.__dict__["a"], pymod.__dict__["b"]


class TestHeadListBindsPastTailCall:
    def test_two_element_list_query_as_var(self, mod, pymod):
        a, b = _atoms(pymod)
        B = Var()
        assert _collect("tail2", [B], 1, B, module=mod) == [(chars("ab"),)]
        # ...which IS the char-atom list (spec §6.2).
        trail = Trail()
        assert unify(_collect("tail2", [B], 1, B, module=mod)[0][0],
                     [a, b], trail)

    def test_one_element_list_query_as_var(self, mod, pymod):
        a, _ = _atoms(pymod)
        B = Var()
        assert _collect("tail1", [B], 1, B, module=mod) == [(chars("a"),)]

    def test_multi_goal_body_tail_call(self, mod, pymod):
        a, b = _atoms(pymod)
        B = Var()
        assert _collect("multi", [B], 1, B, module=mod) == [(chars("ab"),)]

    def test_body_bound_var_element(self, mod, pymod):
        a, _ = _atoms(pymod)
        X, B = Var(), Var()
        assert _collect("bindv", [B], X, B, module=mod) == [([a, 7],)]

    def test_solution_is_ground_not_fresh_var(self, mod, pymod):
        # The dangerous signature: exactly one solution, but B left unbound.
        B = Var()
        sols = _collect("tail2", [B], 1, B, module=mod)
        assert len(sols) == 1
        assert not is_var(sols[0][0])


class TestInputModeStillWorks:
    def test_list_given_directly(self, mod, pymod):
        a, b = _atoms(pymod)
        assert _count("tail2", 1, [a, b], module=mod) == 1

    def test_wrong_list_fails(self, mod, pymod):
        a, b = _atoms(pymod)
        assert _count("tail2", 1, [b, a], module=mod) == 0
        assert _count("tail2", 1, [a], module=mod) == 0


class TestControlsStillWork:
    def test_inline_body_query_as_var(self, mod, pymod):
        a, b = _atoms(pymod)
        B = Var()
        assert _collect("inline", [B], 1, B, module=mod) == [(chars("ab"),)]

    def test_star_list_tail_call_query_as_var(self, mod, pymod):
        a, b = _atoms(pymod)
        B = Var()
        assert _collect("star", [B], 1, B, module=mod) == [(chars("ab"),)]
