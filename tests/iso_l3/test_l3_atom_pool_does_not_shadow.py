"""An atom in the process-wide pool must not shadow a procedure that
``assertz`` creates later (todo/assert-created-predicate-shadowed-by-a-
global-atom-2026-09-29.md).

The module dict of every loaded module is seeded from ``predicate_builtins``,
so an earlier module that declared the atom ``note`` used to bind the body
goal ``note(X)`` of a later, assert-created ``note/1`` to that atom: the call
raised ``existence_error(procedure, note/1)`` while the same file loaded in a
fresh process answered.  Each test seeds the pool FIRST, so it fails on the
old resolution whatever the suite loaded before it."""
from __future__ import annotations

import pytest

from clausal.logic.exceptions import LogicException

FRONT_ENDS = pytest.mark.parametrize("frontend", ["native", None])


@pytest.fixture
def pooled(monkeypatch):
    """Put ``name`` in the global atom pool, as an earlier module declaring
    that atom leaves it; removed again afterwards."""
    from clausal import import_hook as ih

    def seed(name):
        monkeypatch.setitem(ih.predicate_builtins, name, name)
    return seed


@FRONT_ENDS
def test_an_asserted_procedure_answers_although_the_pool_holds_its_atom(
        native, ans, pooled, frontend):
    pooled("pooled_note")
    mod = native.load(f"pool_acd_{frontend}",
                      "add(X) :- assertz(pooled_note(X)).\n"
                      "all(L) :- add(a), add(b), "
                      "findall(X, pooled_note(X), L).\n"
                      "direct(X) :- add(c), pooled_note(X).\n",
                      frontend=frontend)
    assert ans(mod, "all") == [["a", "b"]]
    assert ans(mod, "direct") == ["a", "b", "c"]


@FRONT_ENDS
def test_with_nothing_asserted_the_call_still_raises_existence_error(
        native, pooled, frontend):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    pooled("pooled_absent")
    mod = native.load(f"pool_none_{frontend}",
                      "get(X) :- pooled_absent(X).\n", frontend=frontend)
    with pytest.raises(LogicException) as ei:
        list(call("get", Var(), module=mod))
    assert "existence_error" in str(ei.value)
    assert "pooled_absent" in str(ei.value)
