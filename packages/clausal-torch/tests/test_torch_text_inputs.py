"""Text inputs accept a STRING as well as an atom (spec §9.4, "text in").

Each of these read its argument with ``str(deref(x))`` or a plain
``deref``, so a string -- the chars carrier ``('$chars', s)`` -- reached
torch as the repr ``"('$chars', '/tmp/x.pt')"`` (``save/2``, ``load/2``)
or was looked up as the tuple and matched nothing (``dtype_info/3`` key,
the ``torch_nn`` name tables).  The probe is written under
``-double_quotes(chars)`` so ``"..."`` IS a string.
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch", reason="torch not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-double_quotes(chars)
-import_from(torch, [zeros, save, load, shape, dtype_info, float32])
-import_from(torch_nn, [layer, activation, optimizer_type])

roundtrip(P, S) <- (zeros([2, 3], T), save(T, P), load(P, T2), shape(T2, S))
load_only(P, T) <- load(P, T)
bits_text(B) <- dtype_info(float32, "bits", B)
bits_atom(B) <- dtype_info(float32, 'bits', B)
layer_text() <- layer("Linear", _)
layer_atom() <- layer('Linear', _)
activation_text() <- activation("ReLU", _)
optimizer_text() <- optimizer_type("Adam", _)
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("torchtext") / f"torch_text_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("torch_text_probe", str(src)).__dict__["$module"]


def _first(module, name, *args):
    for _ in call(name, *args, module=module):
        return [_deref_walk(a) for a in args]
    return None


@pytest.mark.parametrize("spelling", ["string", "atom"])
def test_save_and_load_take_a_text_path(module, tmp_path, spelling):
    from clausal.logic.cells import chars
    path = str(tmp_path / f"t_{spelling}.pt")
    arg = chars(path) if spelling == "string" else path
    s = Var()
    got = _first(module, "roundtrip", arg, s)
    assert got is not None and list(got[1]) == [2, 3]
    assert (tmp_path / f"t_{spelling}.pt").is_file()


def test_load_of_a_compound_path_is_a_type_error(module):
    with pytest.raises(LogicException) as info:
        list(call("load_only", ("f", 1), Var(), module=module))
    assert info.value.term[1][:2] == ("type_error", "text")


@pytest.mark.parametrize("name", ["bits_text", "bits_atom"])
def test_dtype_info_key_may_be_text(module, name):
    b = Var()
    assert _first(module, name, b) == [32]


@pytest.mark.parametrize("name", ["layer_text", "layer_atom",
                                  "activation_text", "optimizer_text"])
def test_torch_nn_name_tables_accept_text(module, name):
    assert len(list(call(name, module=module))) == 1
