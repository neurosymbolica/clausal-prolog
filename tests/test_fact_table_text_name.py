"""``_helpers._fact_table_2``: a STRING name matches the fact of that
spelling, as an atom name does (spec §9.4, "text in").

The table read the bound name with a plain ``deref``, so the chars carrier
``('$chars', 'relu')`` was looked up as itself and matched nothing: every
adapter fact table (activation, optimizer, colour-code, ... names) failed
for ``"relu"`` while answering for ``relu``.
"""

from __future__ import annotations

from clausal.logic.cells import chars
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py._helpers import _fact_table_2

_VALUE = object()
_FACTS = [("relu", _VALUE), ("tanh", 2)]


def _answers(name, value):
    dispatch = _fact_table_2(lambda: list(_FACTS))
    proceed, fail = object(), object()
    trail = Trail()
    out = []
    for step in dispatch(None, proceed, fail, None, name, value, trail):
        if step[0] is proceed:
            out.append((deref(name), deref(value)))
        elif step == (fail, DONE):
            break
    return out


def test_atom_name_looks_up_its_value():
    v = Var()
    assert _answers("relu", v) == [("relu", _VALUE)]


def test_string_name_looks_up_its_value():
    v = Var()
    assert _answers(chars("relu"), v) == [(chars("relu"), _VALUE)]


def test_string_name_in_check_mode():
    assert len(_answers(chars("relu"), _VALUE)) == 1
    assert _answers(chars("tanh"), _VALUE) == []


def test_unbound_name_still_enumerates_atoms():
    n, v = Var(), Var()
    assert [a for a, _ in _answers(n, v)] == ["relu", "tanh"]


def test_reverse_lookup_answers_the_atom():
    n = Var()
    assert _answers(n, _VALUE) == [("relu", _VALUE)]


def test_text_arg_leaves_a_pair_of_arrays_alone():
    # A 2-tuple whose first item has an elementwise ``==`` (numpy) must not
    # be compared with the chars tag.
    np = __import__("pytest").importorskip("numpy")
    from clausal.modules.py._helpers import _text_arg
    pair = (np.array([1, 2]), np.array([3, 4]))
    assert _text_arg(pair) is pair
    assert _text_arg(chars("x")) == "x"
    assert _text_arg("x") == "x"
