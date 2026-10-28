"""``Trail.attvars_since(mark)``: the attributed variables a goal touched
(what call_residue_vars/2 reports)."""

from clausal.logic.variables import AttVar, Trail, deref, put_attr


def test_lists_each_touched_attvar_once_oldest_first():
    t = Trail()
    a, b = AttVar(), AttVar()
    put_attr(a, "k", 1, t)
    put_attr(b, "k", 2, t)
    put_attr(a, "j", 3, t)
    got = t.attvars_since(0)
    assert [deref(v) for v in got] == [a, b]


def test_only_changes_after_the_mark_count():
    t = Trail()
    a, b = AttVar(), AttVar()
    put_attr(a, "k", 1, t)
    mark = t.mark()
    put_attr(b, "k", 2, t)
    assert t.attvars_since(mark) == [b]
    put_attr(a, "j", 3, t)
    assert t.attvars_since(mark) == [b, a]


def test_an_undone_change_is_gone():
    t = Trail()
    a = AttVar()
    mark = t.mark()
    put_attr(a, "k", 1, t)
    t.undo(mark)
    assert t.attvars_since(0) == []


def test_a_bad_mark_is_refused():
    import pytest
    with pytest.raises(ValueError):
        Trail().attvars_since(-1)
