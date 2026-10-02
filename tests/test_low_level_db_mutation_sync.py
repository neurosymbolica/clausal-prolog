"""Regression test: the low-level ``Database.assertz/asserta/retract`` API must
keep the predicate class in sync so ``solve()`` sees the mutation.

Background
----------
There are two parallel clause stores: ``Database._clauses`` (+ ``_dispatch``)
and ``PredicateMeta._clauses`` (+ ``_dispatch_fn``). ``solve()`` resolves a
predicate call through the *class*. The ``assertz/1`` *builtin* syncs both, but
the low-level ``Database.assertz()`` Python API only updated the DB store — so
an embedder that called ``db.assertz(...)`` and then ran ``solve()`` of that
predicate saw stale results (the clause was invisible).

See class C in ``todo/fix-audit-2026-06-24.md``.
"""

from __future__ import annotations

import clausal.import_hook  # noqa: F401  (installs the import hook)
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic.cells import cell_functor, make_cell
from clausal.logic.database import Clause
from tests._suffix import SEAM


def _make_dynamic_module(tmp_path, name):
    src = tmp_path / f"{name}{SEAM}"
    src.write_text("-dynamic(p/2)\np(1, 10),\np(2, 20),\n")
    mod = _load_module(name, str(src))
    return mod, mod.__dict__["$module"]


def _solutions(pred, a, lm):
    """*pred* is the predicate's NAME: the goal is the cell ``(pred, a, V)``
    run in *lm* (W4b-2d: ``mod.p`` is a handle, not a callable class)."""
    out = []
    V = Var()
    for _ in solve((pred, a, V), module=lm):
        out.append(V.value)
    return out


def _head_maker(lm):
    """A builder for a head shaped like the ones already stored.

    P2: a stored head is a CELL, so ``type(head)`` is ``tuple`` and there is
    no class to reconstruct from -- the functor and the arguments ARE the
    head.  Reading the functor off a stored clause keeps this test asking
    what it always asked: build a head the way the module's own heads are
    built, then assert it through the low-level API."""
    head = lm.db.clauses_for("p", 2)[0].head
    functor = cell_functor(head)
    return lambda *args: make_cell(functor, *args)


def test_db_assertz_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_assertz")
    head = _head_maker(lm)
    assert _solutions("p", 3, lm) == []
    lm.db.assertz(Clause(head=head(3, 30), body=[]))
    assert _solutions("p", 3, lm) == [30]


def test_db_asserta_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_asserta")
    head = _head_maker(lm)
    lm.db.asserta(Clause(head=head(4, 40), body=[]))
    assert _solutions("p", 4, lm) == [40]


def test_db_retract_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_retract")
    head = _head_maker(lm)
    # Assert a literal-headed clause (not Var+Is-normalized) so the structural
    # match in Database.retract can find it; this isolates the sync behaviour.
    lm.db.assertz(Clause(head=head(3, 30), body=[]))
    assert _solutions("p", 3, lm) == [30]
    removed = lm.db.retract(head(3, 30))
    assert removed is True
    assert _solutions("p", 3, lm) == []
