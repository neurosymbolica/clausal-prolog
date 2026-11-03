"""The contract for entries pushed onto a trail while an undo runs.

Operator ruling 2026-11-03: the current behaviour is the contract
(docs/python_integration.md, "Entries pushed while an undo runs"):

* ``trail.undo(mark)`` releases exactly the entries above ``mark`` when it
  began; an entry pushed while it runs stays live above ``mark`` and the
  next undo past it undoes it.
* What a pushed entry did survives the backtrack; a pushed attribute
  entry's old value is the mid-undo state.
* A nested undo releases what is on the trail when it begins and keeps
  what is pushed during it; the outer undo then treats every entry still on
  the trail as its own.  So an entry pushed inside a nested undo is undone
  by the outer undo, one pushed at the outer level is not.

Filed as items 1 and 2 of
todo/trail-release-and-bare-unify-follow-ups-2026-10-12.md.
"""
from __future__ import annotations

from clausal.logic.variables import (
    AttVar, Trail, Var, deref, get_attr, is_var, put_attr, unify)


def test_a_pushed_attribute_entry_survives_and_restores_the_mid_undo_state():
    t = Trail()
    av = AttVar()
    put_attr(av, 'k', 1, t)
    t.record(lambda: put_attr(av, 'k', 'cb', t))
    put_attr(av, 'k', 2, t)
    t.undo(0)
    # 2 undone (k = 1), the callback sets k = 'cb' (a new entry whose old
    # value is 1), then the first put_attr is undone (k absent).
    assert get_attr(av, 'k') is None
    assert t.mark() == 1
    t.undo(0)
    # The pushed entry restores the value it saw: 1, although k was absent
    # before the first put_attr.
    assert get_attr(av, 'k') == 1
    assert t.mark() == 0


def test_a_binding_made_by_an_undo_callback_survives_the_undo():
    t = Trail()
    y = Var()
    x = Var()
    assert unify(x, 1, t)
    t.record(lambda: unify(y, 7, t))
    t.undo(0)
    assert is_var(deref(x))
    assert deref(y) == 7
    assert t.mark() == 1
    t.undo(0)
    assert is_var(deref(y))
    assert t.mark() == 0


def test_an_entry_pushed_at_the_outer_level_stays_live():
    t = Trail()
    log = []
    assert unify(Var(), 1, t)
    t.record(lambda: (log.append('cb'),
                      t.record(lambda: log.append('pushed'))))
    t.undo(0)
    assert log == ['cb']
    assert t.mark() == 1
    t.undo(0)
    assert log == ['cb', 'pushed']
    assert t.mark() == 0


def test_an_entry_pushed_inside_a_nested_undo_is_undone_by_the_outer_undo():
    t = Trail()
    log = []
    a = Var()
    assert unify(a, 1, t)                      # entry 0

    def inner():                               # entry 1
        log.append('inner')
        t.record(lambda: log.append('pushed in nested'))

    def outer():                               # entry 2
        log.append('outer')
        t.undo(1)                              # nested: takes entry 1
    t.record(inner)
    t.record(outer)
    t.undo(0)
    # The nested undo(1) runs inner, whose push stays above 1; the outer
    # undo(0) carries on from the shortened trail and releases it, then a.
    assert log == ['outer', 'inner', 'pushed in nested']
    assert t.mark() == 0
    assert is_var(deref(a))


def test_a_nested_undo_takes_entries_pushed_earlier_in_the_outer_undo():
    t = Trail()
    log = []
    assert unify(Var(), 1, t)                  # entry 0

    def nests():                               # entry 1
        log.append('nests')
        t.undo(1)                              # nested: takes 'pushed'

    def pushes():                              # entry 2
        log.append('pushes')
        t.record(lambda: log.append('pushed'))
    t.record(nests)
    t.record(pushes)
    t.undo(0)
    # pushes runs first and pushes; nests then undoes to 1, which releases
    # the pushed entry although it was pushed at the outer level.
    assert log == ['pushes', 'nests', 'pushed']
    assert t.mark() == 0


def test_the_ruled_contract_is_in_the_docs_and_the_c_source():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    doc = (root / 'docs' / 'python_integration.md').read_text()
    src = (root / 'clausal' / 'logic' / 'variables' / '_variables.c').read_text()
    assert 'Entries pushed while an undo runs' in doc
    assert 'operator ruling 2026-11-03' in doc
    assert 'operator ruling 2026-11-03' in src
