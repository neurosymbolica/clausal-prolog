"""The nil cell ``()`` is ``[]`` to the list builtins.

``atoms.is_nil`` names four spellings of the empty list: ``[]``, ``""``,
``b""`` and ``()``.  ``()`` reaches a program as a normalised dict key: a JSON
object key ``"[]"`` comes back from ``dict_pairs/2`` as ``()``.  Unification,
``compare/3`` and indexing already treated it as ``[]``; ``is_list/1``,
``length/2``, ``append/3`` and the rest of the list builtins failed on it.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var
from clausal.testing import load_clausal_module

_SRC = """\
-private([x, yes])
-import_from(py.json, [parse])
nil_key(K) <- (parse('{"[]": 1}', D), dict_pairs(D, [K-_]))
t_is_list(yes) <- (nil_key(K), is_list(K))
t_is_chars(yes) <- (nil_key(K), is_chars(K))
t_is_codes(yes) <- (nil_key(K), is_codes(K))
t_length(N) <- (nil_key(K), length(K, N))
t_append(R) <- (nil_key(K), append(K, [x], R))
t_append_back(R) <- (nil_key(K), append([x], K, R))
t_reverse(R) <- (nil_key(K), reverse(K, R))
t_unify(yes) <- (nil_key(K), K is [])
t_member(yes) <- (nil_key(K), member(_, K))
t_nth0(yes) <- (nil_key(K), nth0(0, K, _))
t_last(yes) <- (nil_key(K), last(K, _))
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("nilcell") / "nilcell.seam"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _answers(mod, name):
    v = Var()
    return [v.value for _ in solve((name, v), mod)]


def test_the_json_key_really_is_the_nil_cell(mod):
    assert _answers(mod, "nil_key") == [()]


@pytest.mark.parametrize("name", ["t_is_list", "t_is_chars", "t_is_codes", "t_unify"])
def test_type_checks_hold(mod, name):
    assert _answers(mod, name) == ["yes"]


def test_length_is_zero(mod):
    assert _answers(mod, "t_length") == [0]


@pytest.mark.parametrize("name", ["t_append", "t_append_back"])
def test_append(mod, name):
    assert _answers(mod, name) == [["x"]]


def test_reverse(mod):
    out = _answers(mod, "t_reverse")
    assert len(out) == 1 and not out[0], out


@pytest.mark.parametrize("name", ["t_member", "t_nth0", "t_last"])
def test_an_empty_list_has_no_elements(mod, name):
    assert _answers(mod, name) == []
