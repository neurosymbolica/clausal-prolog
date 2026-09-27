"""The engine's own heads and goals are cells or atoms, never ``Compound``.

Compound retirement slice 3 (plan
``implementation_plans/compound-retirement-plan-2026-09-27.md`` §3).  Each
site below used to BUILD a ``Compound``; it now builds the cell ``(f, *args)``
-- or, at arity 0, the atom -- which the 2026-09-26 ruling already made the
same term (``compound_as_cell``).  A ``Compound`` handed in from Python is
still READ (until slice 8); what these pin is that the engine does not make
new ones.  Answers are pinned alongside, so "the shape changed" can never
hide "the answer changed".
"""

from __future__ import annotations

import contextlib

import pytest

import clausal.terms as T
from clausal.logic.database import Clause, Database
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
from clausal.logic.compiler.control_constructs import _catcher_to_structural
from clausal.logic.builtins import _normalize_fact_clause
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, Unify, Call, LoadName, compound_with_args


@contextlib.contextmanager
def _counting_compound_constructions():
    """Count ``Compound`` constructions made inside the block.  The count
    covers C constructions too (they go through ``tp_init``)."""
    seen = []
    orig = T.Compound.__init__

    def wrapped(self, *a, **k):
        seen.append(a)
        orig(self, *a, **k)

    T.Compound.__init__ = wrapped
    try:
        yield seen
    finally:
        T.Compound.__init__ = orig


def test_the_counter_sees_a_construction():
    """Positive control: without it a zero below could mean a blind counter."""
    with _counting_compound_constructions() as seen:
        Compound("f", (1,))
    assert len(seen) == 1


# ── compound_with_args: the one rebuild ──────────────────────────────────────


def test_compound_with_args_is_the_cell_when_there_is_one():
    c = Compound("f", (1, 2))
    assert compound_with_args(c, (3, 4)) == ("f", 3, 4)
    assert type(compound_with_args(c, (3, 4))) is tuple


def test_compound_with_args_copies_a_compound_with_no_cell():
    """foo(), a Var functor and '$chars' have no cell: copied, not changed."""
    g = Var()
    for term, args in ((Compound("foo", ()), ()),
                       (Compound(g, (1,)), (2,)),
                       (Compound("$chars", ("ab",)), ("cd",))):
        out = compound_with_args(term, args)
        assert isinstance(out, Compound)
        assert out.functor is term.functor and out.args == args


def test_compound_with_args_refuses_a_different_arity():
    with pytest.raises(ValueError):
        compound_with_args(Compound("f", (1,)), (1, 2))


# ── list_dispatch: the lifted head ──────────────────────────────────────────


def test_lifted_compound_head_is_a_cell():
    v, w = Var(), Var()
    clause = Clause(head=Compound("f", (v, w)), body=[Unify(left=v, right=1)])
    with _counting_compound_constructions() as seen:
        lifted = _lift_clause_at_pos(clause, 0)
    assert seen == []
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


def test_normalized_compound_fact_has_a_cell_head_and_the_same_answers():
    facts = [(1, "a"), (2, "b"), (1, "c")]
    db = Database()
    heads = []
    for fact in facts:
        term = Compound("f", fact)
        with _counting_compound_constructions() as seen:
            clause = _normalize_fact_clause(term)
        assert seen == []
        heads.append(clause.head)
        db.assertz(clause)
    assert all(type(h) is tuple and h[0] == "f" for h in heads)
    assert _answers(db, "f", 2) == facts


def test_normalized_zero_arity_compound_fact_is_still_copied():
    """foo() has no cell (the arity-0 cell is reserved); slice 8 retires it."""
    clause = _normalize_fact_clause(Compound("foo", ()))
    assert isinstance(clause.head, Compound) and clause.head.args == ()


# ── catch/3: the catcher ─────────────────────────────────────────────────────


def test_catcher_is_a_cell():
    err = Call(func=LoadName(name="error"), args=[
        Call(func=LoadName(name="type_error"), args=[Var(), Var()], kwargs=[]),
        Var()], kwargs=[])
    with _counting_compound_constructions() as seen:
        out = _catcher_to_structural(err)
    assert seen == []
    assert type(out) is tuple and out[0] == "error"
    assert type(out[1]) is tuple and out[1][0] == "type_error"


def test_zero_argument_catcher_is_the_atom():
    assert _catcher_to_structural(
        Call(func=LoadName(name="oops"), args=[], kwargs=[])) == "oops"


# ── solve(): the query's dummy head ──────────────────────────────────────────


def test_a_query_builds_no_compound(tmp_path, monkeypatch):
    """The dummy head of every compiled query was ``Compound('_query', ())``,
    the one ``foo()`` the engine made itself; it is the atom now."""
    import importlib
    import clausal.logic.solve as S
    (tmp_path / "slice3_q.clausal").write_text(
        "p(1),\np(2),\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module("slice3_q")
    S._query_cache.clear()
    x = Var()
    with _counting_compound_constructions() as seen:
        got = [deref(x) for _ in S.solve(("p", x), module=mod)]
    assert got == [1, 2]
    assert seen == []


# ── retract/1 against the cell heads ─────────────────────────────────────────


def _run_builtin(db, name, term):
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.solve import _drive_trampoline
    dispatch = get_builtin_dispatch(name, 1, db)
    return _drive_trampoline(dispatch, Trail(), term)


@pytest.mark.parametrize("stored", ["cell", "compound_fact", "compound_clause"])
def test_retract_by_cell_pattern_from_a_classless_dynamic_row(stored):
    """A classless dynamic row now holds CELL heads (every argument hoisted);
    retract by a cell pattern still finds the clause, binds the pattern and
    empties the row.  ``compound_clause`` is a ``Compound`` head stored
    directly from Python, which is still read (until slice 8)."""
    db = Database()
    db.mark_dynamic("r", 1)
    if stored == "cell":
        list(_run_builtin(db, "assertz", ("r", 5)))
    elif stored == "compound_fact":
        list(_run_builtin(db, "assertz", Compound("r", (5,))))
    else:
        db.assertz(Clause(head=Compound("r", (5,)), body=[]))
    assert len(db.clauses_for("r", 1)) == 1
    x = Var()
    got = [deref(x) for _ in _run_builtin(db, "retract", ("r", x))]
    assert got == [5]
    assert db.clauses_for("r", 1) == []
