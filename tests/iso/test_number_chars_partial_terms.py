"""number_chars/2 with Number bound and Chars a non-ground partial term
built at the Python level: SegString/SegBytes/SegList views and ``'.'(H, T)``
cons cells are partial (or proper) lists, never ``type_error(list)``."""
from __future__ import annotations

import threading

from clausal.terms import SegList, SegString, ConcreteSeg, VarSeg
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins.chars import _number_chars__2
from clausal.logic.exceptions import LogicException
import pytest


def _run(number, chars):
    trail = Trail()
    return [True for _ in _number_chars__2(number, chars, trail, None)]


def test_segstring_partial_list_is_filled_in():
    t = Var()
    chars = SegString(["1", VarSeg(t)])
    assert _run(12, chars) == [True]


def test_segstring_mismatch_fails_not_raises():
    t = Var()
    assert _run(12, SegString(["x", VarSeg(t)])) == []


def test_bound_hole_bad_element_raises():
    t = Var()
    chars = SegList([ConcreteSeg([Var(), []]), VarSeg(t)])
    unify(t, [], Trail())
    with pytest.raises(LogicException):
        _run(1, chars)


def test_cons_cell_with_proper_list_tail_is_a_list():
    assert _run(12, (".", "1", ["2"])) == []   # no type_error
    assert _run(1, (".", "1", [])) == []


def test_cons_cell_with_bad_tail_still_raises():
    with pytest.raises(LogicException):
        _run(1, (".", "1", 2))


def test_cyclic_cons_chain_terminates():
    v = Var()
    c = (".", "1", v)
    unify(v, c, Trail())
    out = {}

    def go():
        try:
            out["r"] = _run(1, c)
        except BaseException as e:   # RecursionError path is acceptable
            out["r"] = e
    th = threading.Thread(target=go, daemon=True)
    th.start()
    th.join(10)
    assert not th.is_alive(), "cycle guard missing: number_chars hung"


def test_dcg_built_partial_string_is_filled_in(tmp_path):
    """phrase(one, L, T) leaves L a partial string; number_chars(12, L)
    must fill in T = ['2'] (Scryer: L = ['1','2'], T = ['2'])."""
    from tests.test_chars_carrier import _mod, _first
    mod = _mod(tmp_path, 'one >> ("1")\n'
                         'pb(L, T) <- (phrase(one, L, T), number_chars(12, L))\n')
    L, T = Var(), Var()
    assert _first(mod, "pb", L, T) is not None
    assert deref(T) == ["2"]
