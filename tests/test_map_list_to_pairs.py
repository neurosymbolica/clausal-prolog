"""map_list_to_pairs/3 (Scryer's library(pairs)), and the Key-Value pairs
dict_pairs/2, dict_put_pairs/3 and zip_/3 read and build (RULED 2026-09-28:
they used [Key, Value] lists).  The expected rows are Scryer's answers
(checked 2026-09-28)."""

from __future__ import annotations

import itertools
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, is_var
from clausal.terms import DictTerm
from tests._suffix import SEAM

_SRC = """\
-allow_singletons
-private([a, b, x])
q(_, 1),
q(_, 2),
by_length(PS) <- map_list_to_pairs(length, [[1, 2, 3], [4], [5, 6]], PS)
each(PS) <- map_list_to_pairs(q, ['a', 'b'], PS)
open_ls(L, PS) <- map_list_to_pairs(q, L, PS)
bad_pair(PS) <- map_list_to_pairs(length, [[1]], ['-'(1, [1]), 'x'])
bound_pairs(L) <- map_list_to_pairs(length, L, ['-'(K, [1, 2])])
zip(PS) <- zip_([1, 2, 3], ['a', 'b'], PS)
zip_check(Z) <- (zip_([1], ['a'], [1 - 'a']), Z is 1)
dict_check(Z) <- (dict_pairs({'a': 1}, ['a' - 1]), Z is 1)
bound_key(X) <- map_list_to_pairs(length, [X], ['-'(2, X)])
dict_round_trip(D, PS) <- (dict_pairs(D, ['-'('b', 2), '-'('a', 1)]), dict_pairs(D, PS))
old_shape(D) <- dict_pairs(D, [['a', 1]])
put(D) <- dict_put_pairs(['-'('b', 2), 'b' - 3], {'a': 1}, D)
"""


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_map_list_to_pairs", path)
    finally:
        os.unlink(path)


def _shape(t):
    t = _deref_walk(t)
    if is_var(t):
        return "_"
    if isinstance(t, list):
        return [_shape(e) for e in t]
    if isinstance(t, tuple):
        return tuple(_shape(e) for e in t)
    return t


def _answers(mod, name, n=1, limit=6):
    vs = [Var() for _ in range(n)]
    out = []
    for _ in itertools.islice(solve((name, *vs), mod), limit):
        got = tuple(_shape(v) for v in vs)
        out.append(got[0] if n == 1 else got)
    return out


# Scryer: [3-[1,2,3], 1-[4], 2-[5,6]]
def test_pairs_each_element_with_its_key(mod):
    assert _answers(mod, "by_length") == [
        [("-", 3, [1, 2, 3]), ("-", 1, [4]), ("-", 2, [5, 6])]]


# Scryer: [1-a,1-b], [1-a,2-b], [2-a,1-b], [2-a,2-b]
def test_every_solution_of_each_call(mod):
    assert _answers(mod, "each") == [
        [("-", 1, "a"), ("-", 1, "b")], [("-", 1, "a"), ("-", 2, "b")],
        [("-", 2, "a"), ("-", 1, "b")], [("-", 2, "a"), ("-", 2, "b")]]


# Scryer: L = [], P = [] ; L = [_A], P = [1-_A] ; L = [_A, _B], ...
def test_open_lists_enumerate(mod):
    got = _answers(mod, "open_ls", 2, limit=3)
    assert got == [([], []), (["_"], [("-", 1, "_")]),
                   (["_", "_"], [("-", 1, "_"), ("-", 1, "_")])]


def test_a_non_pair_fails(mod):
    assert _answers(mod, "bad_pair") == []


def test_bound_pairs_give_the_list(mod):
    assert _answers(mod, "bound_pairs") == [[[1, 2]]]


def test_zip_builds_pairs(mod):
    assert _answers(mod, "zip") == [[("-", 1, "a"), ("-", 2, "b")]]


def test_dict_pairs_round_trip(mod):
    [(d, ps)] = _answers(mod, "dict_round_trip", 2)
    assert d == DictTerm({"a": 1, "b": 2})
    assert ps == [("-", "a", 1), ("-", "b", 2)]


def test_dict_pairs_no_longer_reads_a_two_element_list(mod):
    assert _answers(mod, "old_shape") == []


def test_dict_put_pairs_reads_both_spellings_of_a_pair(mod):
    assert _answers(mod, "put") == [DictTerm({"a": 1, "b": 3})]


def test_source_pair_spelling_checks(mod):
    assert _answers(mod, "zip_check") == [1]
    assert _answers(mod, "dict_check") == [1]


# Scryer: map_list_to_pairs(length, [X], [2-X]) -> X = [_, _], deterministic
def test_a_bound_key_reaches_the_call(mod):
    assert _answers(mod, "bound_key", limit=5) == [["_", "_"]]
