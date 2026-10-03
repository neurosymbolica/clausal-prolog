"""``_property_2`` (``clausal.modules.py._helpers``): check mode accepts
what query mode binds.  A str property crosses as TEXT, so
``p(X, V), p(X, V)`` must hold; it used to fail, because check mode compared
the bare str with the text carrier.  The bare-str (atom) spelling that check
mode always accepted is still accepted."""

from clausal.logic.cells import chars
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py._helpers import _property_2


class _Obj:
    device = "cpu:0"
    ndim = 2


_device = _property_2(lambda o: o.device)
_ndim = _property_2(lambda o: o.ndim)


def _answers(dispatch, *args):
    gen = dispatch(None, "ok", "fail", None, *args, Trail())
    return [k for k, _ in gen if k == "ok"]


def test_query_then_check_with_the_queried_value():
    obj, v = _Obj(), Var()
    gen = _device(None, "ok", "fail", None, obj, v, Trail())
    kind, _ = next(gen)
    assert kind == "ok"
    got = deref(v)
    assert got == chars("cpu:0")
    assert _answers(_device, obj, got) == ["ok"]


def test_check_mode_still_accepts_the_atom_spelling():
    assert _answers(_device, _Obj(), "cpu:0") == ["ok"]


def test_check_mode_rejects_a_different_value():
    assert _answers(_device, _Obj(), chars("cuda:0")) == []
    assert _answers(_device, _Obj(), "cuda:0") == []


def test_non_text_property_unchanged():
    assert _answers(_ndim, _Obj(), 2) == ["ok"]
    assert _answers(_ndim, _Obj(), 3) == []
