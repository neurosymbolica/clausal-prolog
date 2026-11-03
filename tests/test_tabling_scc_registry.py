"""Completing a table does not walk the whole table store.

See ``todo/done/complete-scc-scans-whole-table-store-per-completion-2026-11-03.md``.
``_complete_scc`` looks for dormant SCC members on every leader exit.  It used
to find them by walking every entry of the store, so a program that completes
n tables in one store (tabled fib) paid O(n) per completion, O(n^2) in all.
The store now keeps a registry of candidates (``TableStore.scc_candidates``),
and ``CLAUSAL_CHECK_SCC_MEMBERS=1`` compares it with the full scan at every
use.
"""
import os

import pytest

from clausal.logic import tabling
from clausal.logic.database import TableStore
from clausal.logic.solve import call, query_wfs
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# Mutual recursion over a cycle, called with the first argument bound, so
# each call is its own variant table: SCC members go dormant and are swept
# by their root's _complete_scc.  win/1 adds negation cycles (WFS).
_SCC_PROGRAM = (
    "-table(pa/2)\n"
    "-table(pb/2)\n"
    "-table(win/1)\n"
    "\n"
    "e(0, 1),\n"
    "e(1, 2),\n"
    "e(2, 0),\n"
    "e(2, 3),\n"
    "e(3, 4),\n"
    "e(4, 3),\n"
    "\n"
    "pa(X, Y) <- e(X, Y)\n"
    "pa(X, Y) <- (\n"
    "    pb(X, Z),\n"
    "    e(Z, Y)\n"
    ")\n"
    "pb(X, Y) <- (\n"
    "    pa(X, Z),\n"
    "    e(Z, Y)\n"
    ")\n"
    "win(X) <- (e(X, Y), not win(Y))\n"
)


@pytest.fixture
def scc_module(tmp_path):
    src = tmp_path / "scc_registry.seam"
    src.write_text(_SCC_PROGRAM)
    return load_clausal_module(str(src))


_EDGES = [(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (4, 3)]


def _walks(x):
    """The oracle: pa(x, Y) iff a walk of odd length leads from x to Y; pb(x,
    Y) iff one of even length >= 2 does.  States are (node, parity, at least
    two steps taken)."""
    states, todo = set(), [(x, 0, False)]
    while todo:
        node, parity, long_ = todo.pop()
        for a, b in _EDGES:
            st = (b, 1 - parity, long_ or parity == 1)
            if a == node and st not in states:
                states.add(st)
                todo.append(st)
    odd = sorted({n for n, parity, _ in states if parity == 1})
    even = sorted({n for n, parity, long_ in states if parity == 0 and long_})
    return odd, even


def _answers(mod, name, x):
    y = Var()
    return [deref(y) for _ in call(name, x, y, module=mod.__dict__["$module"])]


def test_a_database_table_store_is_a_table_store(scc_module):
    assert isinstance(scc_module.__dict__["$module"].db.table_store, TableStore)


def test_completion_does_not_walk_the_store(monkeypatch):
    # tabled fib(300) completes ~300 tables in one store.  Walking the store
    # at each completion called values() ~300 times; now only the root exit's
    # global resolution pass (and the like) walks it.
    monkeypatch.setattr(tabling, "_CHECK_SCC_MEMBERS", False)  # it scans
    walks = []
    original = TableStore.values

    def counting(self):
        walks.append(1)
        return original(self)
    monkeypatch.setattr(TableStore, "values", counting)
    mod = load_clausal_module(os.path.join(FIXTURES, "tabled_fib.seam"))
    r = Var()
    got = [deref(r) for _ in call("fib", 300, r, module=mod.__dict__["$module"])]
    assert got == [222232244629420445529739893461909967206666939096499764990979600]
    assert len(walks) < 10, f"the store was walked {len(walks)} times"


def test_the_registry_agrees_with_the_store_scan(scc_module, monkeypatch):
    # The cross-check mode raises AssertionError on any disagreement.
    monkeypatch.setattr(tabling, "_CHECK_SCC_MEMBERS", True)
    swept = []
    original = tabling._check_scc_members

    def recording(members, store):
        swept.append(len(members))
        original(members, store)
    monkeypatch.setattr(tabling, "_check_scc_members", recording)
    for x in range(5):
        odd, even = _walks(x)
        assert sorted(_answers(scc_module, "pa", x)) == odd
        assert sorted(_answers(scc_module, "pb", x)) == even
    assert swept, "no _complete_scc ran"
    assert any(swept), "no sweep met a dormant SCC member"


def test_the_registry_leaves_no_answer_or_truth_changed(scc_module, monkeypatch):
    # Same answers, same order, same WFS truth with the cross-check on.
    monkeypatch.setattr(tabling, "_CHECK_SCC_MEMBERS", True)
    lm = scc_module.__dict__["$module"]
    got = []
    for x in range(5):
        res = query_wfs(("win", x), {}, lm)
        got.append([str(r["_truth"]) for r in res])
    # 0 -> 1 -> 2 -> 0 is an odd cycle (undefined) with an exit 2 -> 3, and
    # 3 <-> 4 is an even cycle: every win/1 here is undefined under WFS.
    assert got == [["Undefined"]] * 5


def test_abolish_all_tables_clears_the_registry(scc_module):
    db = scc_module.__dict__["$module"].db
    _answers(scc_module, "pa", 0)
    db.table_store.scc_candidates[object()] = ("x", 0, ())
    db.abolish_all_tables()
    assert not db.table_store
    assert not db.table_store.scc_candidates
