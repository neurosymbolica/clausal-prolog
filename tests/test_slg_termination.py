"""Python-level checks on SLG tabling internals.

Behavior tests for left-recursion / mutual-recursion / same-generation
have been migrated to Test clauses inside the corresponding fixtures:
    tests/fixtures/tabled_left_rec.clausal
    tests/fixtures/tabled_mutual_rec.clausal
    tests/fixtures/tabled_same_gen.clausal

What remains here are assertions on the SLG runtime that need
Python-level access to ``Module.db.table_store`` / ``db.is_tabled``.
"""

import os

import pytest

from clausal.logic.variables import Var
from clausal.logic.solve import call


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, os.path.join(FIXTURES, f"{name}.clausal"))


def _module(mod):
    return mod.__dict__["$module"]


class TestTableStoreCompletion:
    """After a tabled query exhausts, every TableEntry must reach
    ``status == 'complete'``."""

    def test_left_rec_table_complete(self):
        lm = _module(_load("tabled_left_rec"))
        list(call("Path", 1, Var(), module=lm))
        for entry in lm.db.table_store.values():
            assert entry.status == "complete"

    def test_same_gen_table_complete(self):
        lm = _module(_load("tabled_same_gen"))
        list(call("Sg", Var(), Var(), module=lm))
        for entry in lm.db.table_store.values():
            assert entry.status == "complete"

    def test_mutual_rec_table_complete(self):
        lm = _module(_load("tabled_mutual_rec"))
        list(call("ReachA", 1, Var(), module=lm))
        for entry in lm.db.table_store.values():
            assert entry.status == "complete"


class TestIsTabled:
    """``Database.is_tabled(name, arity)`` reports the -table directive."""

    def test_mutual_rec_both_tabled(self):
        lm = _module(_load("tabled_mutual_rec"))
        assert lm.db.is_tabled("ReachA", 2)
        assert lm.db.is_tabled("ReachB", 2)
