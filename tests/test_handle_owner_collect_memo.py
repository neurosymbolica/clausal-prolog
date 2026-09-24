"""Roborev Medium on 12fd252e: with two owners REALLY live under one module
name, the handle-owner registry ran a full ``gc.collect()`` on EVERY lookup --
question-only lookups included (``_owner_db_or_none`` swallows the refusal
and answers ``None``, so a program never stops and pays a collection each
time).  The registry now collects at most once per ambiguous CANDIDATE SET;
the answers (refusal for a dispatch, ``None`` for a question) are unchanged.
"""

from __future__ import annotations

import gc
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import predicate as predmod
from clausal.logic.atoms import mangle
from clausal.logic.cells import qualify_mangled_goal
from clausal.logic.predicate import (
    AmbiguousHandleOwnerError, _owner_db_or_none, resolve_predicate_row,
)


def _load_popped(tmp_path, name, source):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    sys.modules.pop(name, None)
    module = _load_module(name, str(path))
    sys.modules.pop(name, None)
    return module


def _db(module):
    return module.__dict__["$module"].db


@pytest.fixture
def collections(monkeypatch):
    count = [0]
    real = gc.collect

    def counting(*args, **kwargs):
        count[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(gc, "collect", counting)
    return count


def test_a_truly_ambiguous_name_is_collected_for_once_not_per_lookup(
        tmp_path, collections, monkeypatch):
    name = "q0m_amb"
    monkeypatch.delitem(predmod._HANDLE_OWNERS, name, raising=False)
    first = _load_popped(tmp_path, name, "q0m_r(1),\n")
    second = _load_popped(tmp_path, name, "q0m_r(2),\n")
    handle = mangle(name, "q0m_r")
    collections[0] = 0
    # First lookup: one collection, both survive -- still refused / None.
    assert _owner_db_or_none(name) is None
    assert collections[0] == 1
    # Every later lookup of the SAME set: no collection, same answers.
    for _ in range(5):
        assert _owner_db_or_none(name) is None
        assert resolve_predicate_row(handle, arity=1) is None
        with pytest.raises(AmbiguousHandleOwnerError, match=name):
            qualify_mangled_goal((handle, 1))
    assert collections[0] == 1, \
        "the same ambiguous set must not be collected for again"
    # One owner REALLY dropped (a collection reaps it): the survivor answers.
    survivor = _db(second)
    del first
    gc.collect()
    assert _owner_db_or_none(name) is survivor
    assert resolve_predicate_row(handle, arity=1) is survivor.row("q0m_r", 1)
    assert name not in predmod._AMBIGUOUS_AFTER_COLLECT, \
        "the reap must drop the remembered set"
    del second, survivor


def test_a_new_owner_under_the_name_re_arms_the_collection(
        tmp_path, collections, monkeypatch):
    """A different candidate set (a third load) is collected for afresh --
    and a module dropped into a cycle before that lookup is seen then."""
    name = "q0m_rearm"
    monkeypatch.delitem(predmod._HANDLE_OWNERS, name, raising=False)
    first = _load_popped(tmp_path, name, "q0m_s(1),\n")
    second = _load_popped(tmp_path, name, "q0m_s(2),\n")
    collections[0] = 0
    assert _owner_db_or_none(name) is None
    assert _owner_db_or_none(name) is None
    assert collections[0] == 1
    # No AUTOMATIC collection may reap the dropped modules before the
    # lookup, or the control below is racing the collector.
    gc.disable()
    try:
        del first, second                  # held only by their own cycles
        third = _load_popped(tmp_path, name, "q0m_s(3),\n")
        assert len(predmod._HANDLE_OWNERS[name]) == 3, \
            "control: the dropped modules must still look live before the " \
            "lookup"
        assert _owner_db_or_none(name) is _db(third)
    finally:
        gc.enable()
    assert collections[0] == 2
    del third
