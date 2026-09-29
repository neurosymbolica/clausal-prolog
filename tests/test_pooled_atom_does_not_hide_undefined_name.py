"""An atom in the process-wide pool must not stand in for an UNDECLARED name
in a later seam module (todo/done/pooled-atom-hides-an-undefined-seam-name-
2026-09-30.md).

Every module namespace was seeded from the whole ``predicate_builtins`` pool,
so once any module had declared ``cite``, a later module using ``cite``
without declaring or importing it resolved the atom str: ``REF = cite(a)``
failed with ``'str' object is not callable``, a data ``cite(a)`` with
``existence_error(procedure, cite/1)``, and a goal ``cite(X)`` with "atom
'cite' is not callable" -- where a fresh process raises NameError (and the
sibling-export diagnostic) or the plain procedure-not-found error.  Each test
seeds the pool FIRST, so it fails on the old seeding whatever ran before."""
from __future__ import annotations

import itertools

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.predicate_diagnostics import PredicateNotFoundError

_N = itertools.count()


@pytest.fixture
def load(tmp_path, monkeypatch):
    from clausal import import_hook as ih
    monkeypatch.setitem(ih.predicate_builtins, "pooled_cite", "pooled_cite")

    def _load(src):
        name = f"_pooled_undef_{next(_N)}"
        p = tmp_path / f"{name}.seam"
        p.write_text(src)
        return _load_module(name, str(p))
    return _load


def test_module_level_call_is_a_name_error(load):
    with pytest.raises(NameError) as ei:
        load("-private([a])\nREF = pooled_cite(a)\nk(REF),\n")
    assert "pooled_cite" in str(ei.value)


def test_data_term_in_a_body_is_a_name_error(load):
    m = load("-private([a])\nh(D) <- (D is {'k': pooled_cite(a)})\n")
    with pytest.raises(NameError) as ei:
        list(solve(("h", Var()), m))
    assert str(ei.value).startswith("name 'pooled_cite' is not defined")


def test_goal_is_the_fresh_process_procedure_error(load):
    m = load("g(X) <- pooled_cite(X)\n")
    with pytest.raises(PredicateNotFoundError):
        list(solve(("g", Var()), m))


def test_a_declared_name_still_resolves_to_the_pool_atom(load):
    m = load("-private([pooled_cite])\nk(pooled_cite),\n")
    v = Var()
    assert [_deref_walk(v) for _ in solve(("k", v), m)] == ["pooled_cite"]
