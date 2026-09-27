"""The engine's own heads, facts and catchers are cells (or atoms).

A compound term is the cell ``(f, *args)`` and, at arity 0, the atom.
Answers are pinned alongside the shapes, so "the shape changed" can never
hide "the answer changed".
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Clause, Database
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
from clausal.logic.compiler.control_constructs import _catcher_to_structural
from clausal.logic.builtins import _normalize_fact_clause
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Unify, Call, LoadName


def test_lifted_cell_head_stays_a_cell():
    v, w = Var(), Var()
    clause = Clause(head=("f", v, w), body=[Unify(left=v, right=1)])
    lifted = _lift_clause_at_pos(clause, 0)
    assert type(lifted.head) is tuple
    assert lifted.head[0] == "f" and lifted.head[1] == 1 and lifted.head[2] is w
    assert lifted.body == []


# ── assertz: the normalized fact head ────────────────────────────────────────


def _answers(db, functor, arity):
    fn = compile_predicate_trampoline(
        functor, arity, db.clauses_for(functor, arity), db)
    args = [Var() for _ in range(arity)]
    sg = StepGenerator(fn, None, None, None, *args, Trail())
    return solutions(sg, lambda: tuple(deref(a) for a in args))


@pytest.mark.parametrize("hoist_all", [False, True])
def test_normalized_cell_fact_has_a_cell_head_and_the_same_answers(hoist_all):
    facts = [(1, "a"), (2, "b"), (1, "c")]
    db = Database()
    heads = []
    for fact in facts:
        clause = _normalize_fact_clause(("f", *fact), hoist_all=hoist_all)
        heads.append(clause.head)
        db.assertz(clause)
    assert all(type(h) is tuple and h[0] == "f" for h in heads)
    assert _answers(db, "f", 2) == facts


# ── catch/3: the catcher ─────────────────────────────────────────────────────


def test_catcher_is_a_cell():
    err = Call(func=LoadName(name="error"), args=[
        Call(func=LoadName(name="type_error"), args=[Var(), Var()], kwargs=[]),
        Var()], kwargs=[])
    out = _catcher_to_structural(err)
    assert type(out) is tuple and out[0] == "error"
    assert type(out[1]) is tuple and out[1][0] == "type_error"


def test_zero_argument_catcher_is_the_atom():
    assert _catcher_to_structural(
        Call(func=LoadName(name="oops"), args=[], kwargs=[])) == "oops"


# ── retract/1 against the cell heads ─────────────────────────────────────────


def _run_builtin(db, name, term):
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.solve import _drive_trampoline
    dispatch = get_builtin_dispatch(name, 1, db)
    return _drive_trampoline(dispatch, Trail(), term)


@pytest.mark.parametrize("stored", ["assertz", "db.assertz"])
def test_retract_by_cell_pattern_from_a_classless_dynamic_row(stored):
    """A classless dynamic row holds CELL heads (every argument hoisted by
    assertz/1); retract by a cell pattern finds the clause, binds the pattern
    and empties the row."""
    db = Database()
    db.mark_dynamic("r", 1)
    if stored == "assertz":
        list(_run_builtin(db, "assertz", ("r", 5)))
    else:
        db.assertz(Clause(head=("r", 5), body=[]))
    assert len(db.clauses_for("r", 1)) == 1
    x = Var()
    got = [deref(x) for _ in _run_builtin(db, "retract", ("r", x))]
    assert got == [5]
    assert db.clauses_for("r", 1) == []
