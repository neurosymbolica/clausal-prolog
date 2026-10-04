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
-import_from(torch_nn, [layer, activation, optimizer_type,
                        named_parameter, named_module, named_child])
-import_module(torch)

roundtrip(P, S) <- (zeros([2, 3], T), save(T, P), load(P, T2), shape(T2, S))
load_only(P, T) <- load(P, T)
bits_text(B) <- dtype_info(float32, "bits", B)
bits_atom(B) <- dtype_info(float32, 'bits', B)
layer_text() <- layer("Linear", _)
layer_atom() <- layer('Linear', _)
activation_text() <- activation("ReLU", _)
optimizer_text() <- optimizer_type("Adam", _)
net(M) <- (M is torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.ReLU()))
param_text(S) <- (net(M), named_parameter(M, "0.weight", P), shape(P, S))
param_atom(S) <- (net(M), named_parameter(M, '0.weight', P), shape(P, S))
module_text(S) <- (net(M), named_module(M, "0", L), named_parameter(L, "bias", P), shape(P, S))
module_atom(S) <- (net(M), named_module(M, '0', L), named_parameter(L, 'bias', P), shape(P, S))
root_text(S) <- (net(M), named_module(M, "", R), named_child(R, "0", L), named_parameter(L, "weight", P), shape(P, S))
child_text(S) <- (net(M), named_child(M, "0", L), named_parameter(L, "weight", P), shape(P, S))
child_atom(S) <- (net(M), named_child(M, '0', L), named_parameter(L, 'weight', P), shape(P, S))
param_missing_text() <- (net(M), named_parameter(M, "0.nope", _))
child_names(NS) <- (net(M), findall(N, named_child(M, N, _), NS))
param_names(NS) <- (net(M), findall(N, named_parameter(M, N, _), NS))
child_number() <- (net(M), named_child(M, 0, _))
param_number() <- (net(M), named_parameter(M, 0, _))
param_bound_same() <- (net(M), named_parameter(M, "0.weight", P), named_parameter(M, "0.weight", P))
param_bound_other() <- (net(M), named_parameter(M, "0.bias", P), named_parameter(M, "0.weight", P))
child_bound_same() <- (net(M), named_child(M, "1", L), named_child(M, "1", L))
child_bound_other() <- (net(M), named_child(M, "0", L), named_child(M, "1", L))
param_name_of(N) <- (net(M), named_parameter(M, "0.bias", P), named_parameter(M, N, P))
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


# ``named_parameter/3``, ``named_module/3`` and ``named_child/3`` compared
# a bound NAME with ``unify``, so a string name (the chars carrier) never
# equalled the module path's atom and the goal failed silently.


@pytest.mark.parametrize("name,expected", [
    ("param_text", [2, 2]), ("param_atom", [2, 2]),
    ("module_text", [2]), ("module_atom", [2]),
    ("root_text", [2, 2]),
    ("child_text", [2, 2]), ("child_atom", [2, 2]),
])
def test_named_predicates_accept_a_text_name(module, name, expected):
    got = _first(module, name, Var())
    assert got is not None and list(got[0]) == expected


def test_named_parameter_text_name_still_selects(module):
    assert list(call("param_missing_text", module=module)) == []


@pytest.mark.parametrize("name,expected", [
    ("child_names", ["0", "1"]),
    ("param_names", ["0.weight", "0.bias"]),
])
def test_named_predicate_names_come_out_as_atoms(module, name, expected):
    got = _first(module, name, Var())
    # an atom IS its ``str``; a string would be the ``('$chars', s)`` carrier
    assert got is not None and got[0] == expected
    assert all(type(n) is str for n in got[0])


# A NUMBER is no name: ``0`` is not the atom ``'0'`` (ISO term comparison),
# so it does not select the child or parameter the path ``'0'`` names.
@pytest.mark.parametrize("name", ["child_number", "param_number"])
def test_named_predicates_a_number_is_no_name(module, name):
    assert list(call(name, module=module)) == []


# A string name with the VALUE already bound: the bound value is matched by
# identity, so the same object holds and another one fails (no tensor
# comparison error, no silent success).
@pytest.mark.parametrize("name,holds", [
    ("param_bound_same", True), ("param_bound_other", False),
    ("child_bound_same", True), ("child_bound_other", False),
])
def test_named_predicates_string_name_with_a_bound_value(module, name, holds):
    assert bool(list(call(name, module=module))) is holds


def test_named_parameter_bound_value_answers_its_name(module):
    # reverse lookup: the parameter is matched by identity, not by a tensor
    # ``==`` (which raised on the first non-identical parameter)
    n = Var()
    assert [_deref_walk(n) for _ in call("param_name_of", n, module=module)] == ["0.bias"]
