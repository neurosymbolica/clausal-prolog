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
from clausal.logic.database import Clause


def _make_dynamic_module(tmp_path, name):
    src = tmp_path / f"{name}.clausal"
    src.write_text("-dynamic(p/2)\np(1, 10),\np(2, 20),\n")
    mod = _load_module(name, str(src))
    return mod, mod.__dict__["$module"]


def _solutions(pred, a, lm):
    out = []
    V = Var()
    for _ in solve(pred(a, V), module=lm):
        out.append(V.value)
    return out


def _head_class(lm):
    return type(lm.db.clauses_for("p", 2)[0].head)


def test_db_assertz_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_assertz")
    cls = _head_class(lm)
    assert _solutions(mod.p, 3, lm) == []
    lm.db.assertz(Clause(head=cls(arg_0=3, arg_1=30), body=[]))
    assert _solutions(mod.p, 3, lm) == [30]


def test_db_asserta_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_asserta")
    cls = _head_class(lm)
    lm.db.asserta(Clause(head=cls(arg_0=4, arg_1=40), body=[]))
    assert _solutions(mod.p, 4, lm) == [40]


def test_db_retract_visible_to_solve(tmp_path):
    mod, lm = _make_dynamic_module(tmp_path, "lvl_retract")
    cls = _head_class(lm)
    # Assert a literal-headed clause (not Var+Is-normalized) so the structural
    # match in Database.retract can find it; this isolates the sync behaviour.
    lm.db.assertz(Clause(head=cls(arg_0=3, arg_1=30), body=[]))
    assert _solutions(mod.p, 3, lm) == [30]
    removed = lm.db.retract(cls(arg_0=3, arg_1=30))
    assert removed is True
    assert _solutions(mod.p, 3, lm) == []
