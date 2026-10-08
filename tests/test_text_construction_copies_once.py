"""Building text one char at a time copies the text, never splits it into chars.

``rec(N, [a|T]) <- ..., rec(M, T)`` binds its output list after the body
(deferred output-mode head unification), so each level prepends one char to
the finished tail ``T``.  ``append("a", T, L)`` in a loop does the same.  Both
used to split ``T``'s text into one list entry per char and join it again,
per level, which made building n chars quadratic in Python-level work.  They
now concatenate the str.  The answers are unchanged; these tests pin them,
for both twins of the head-output helper, and check that the per-char split
no longer runs.
"""
from __future__ import annotations

import pytest

from clausal.logic.cells import chars
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.solve import solve
from clausal.logic.runtime import list_unify
from clausal.logic.runtime.list_unify import _head_list_unify_output_py
from clausal.logic.builtins import lists
from clausal.testing import load_clausal_module

try:
    from clausal.logic.runtime._list_unify import (
        _head_list_unify_output as _c_output,
    )
    _TWINS = [_head_list_unify_output_py, _c_output]
except ImportError:  # pragma: no cover -- pure-Python build
    _TWINS = [_head_list_unify_output_py]


def _out(impl, before, star, after):
    """Run one twin on ``[*before, *S, *after]`` with S bound to *star*."""
    target, s = Var(), Var()
    trail = Trail()
    unify(s, star, trail)
    assert impl(target, list(before), s, list(after), trail) is True
    return deref(target)


@pytest.mark.parametrize("before, star, after, expected", [
    (["a"], chars("bc"), [], chars("abc")),
    ([], chars("bc"), ["d"], chars("bcd")),
    (["a", "b"], chars(""), ["c"], chars("abc")),
    ([], chars("xy"), [], chars("xy")),
    ([], chars(""), [], []),                     # empty stays the empty list
    ([1], chars("ab"), [], [1, "a", "b"]),       # a non-char blocks the carrier
    (["a"], chars("b"), ["cd"], ["a", "b", "cd"]),   # so does a longer atom
], ids=["prepend", "append", "empty-star", "star-only", "all-empty",
        "int-before", "atom-after"])
def test_both_twins_build_what_they_built_before(before, star, after, expected):
    outs = [_out(impl, before, star, after) for impl in _TWINS]
    assert outs == [expected] * len(_TWINS), f"twins disagree: {outs}"


def test_an_unbound_element_beside_a_text_star_keeps_the_list():
    for impl in _TWINS:
        x = Var()
        got = _out(impl, [x], chars("ab"), [])
        assert type(got) is list and len(got) == 3 and got[1:] == ["a", "b"], impl


def test_the_python_twin_does_not_split_a_text_star(monkeypatch):
    def no_split(s):
        raise AssertionError("split a text star into chars")
    monkeypatch.setattr(list_unify, "str_chars", no_split)
    assert _out(_head_list_unify_output_py, ["a"], chars("b" * 10000), []) \
        == chars("a" + "b" * 10000)


_SRC = """\
rec(0, []).
rec(N, [a|T]) :- N > 0, M is N - 1, rec(M, T).
recs(0, "").
recs(N, L) :- N > 0, M is N - 1, recs(M, T), append("a", T, L).
cat(L) :- append("ab", "cd", L).
cat_empty(L) :- append("ab", "", L).
strip(L) :- append("ab", L, "abcd").
strip_all(L) :- append("ab", L, "ab").
strip_miss(L) :- append("ab", L, "xbcd").
strip_short(L) :- append("ab", L, "a").
cat_list(X) :- append("ab", "cd", [a, b, X, d]).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("textbuild") / "textbuild.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _answers(mod, name, *args):
    v = Var()
    return [deref(v) for _ in solve((name, *args, v), mod)]


@pytest.mark.parametrize("name, expected", [
    ("cat", [chars("abcd")]),
    ("cat_empty", [chars("ab")]),
    ("strip", [chars("cd")]),
    ("strip_all", [chars("")]),
    ("strip_miss", []),
    ("strip_short", []),
    ("cat_list", ["c"]),
])
def test_append_on_text(mod, name, expected):
    assert _answers(mod, name) == expected


@pytest.mark.parametrize("name", ["rec", "recs"])
def test_text_built_one_char_at_a_time(mod, name):
    assert _answers(mod, name, 200) == [chars("a" * 200)]


def test_append_on_text_does_not_split_its_arguments(mod, monkeypatch):
    real = lists._as_items
    split = []

    def watch(val):
        if type(val) is tuple and len(val) == 2 and val[0] == "$chars" and val[1]:
            split.append(len(val[1]))
        return real(val)
    monkeypatch.setattr(lists, "_as_items", watch)
    assert _answers(mod, "recs", 200) == [chars("a" * 200)]
    assert split == [], f"split {len(split)} carriers, longest {max(split)}"
