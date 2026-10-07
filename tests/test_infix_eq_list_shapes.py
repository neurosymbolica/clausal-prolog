"""Infix ``==`` / ``!=`` see one list as one term, whatever spelling holds it.

A list has several Python spellings: a ``list``, the chars carrier
``('$chars', s)``, a ``bytes`` code list, the nil cell ``()``.  The ground
fallback of infix ``==`` (CLP(FD) ``fd_eq``/``fd_ne`` and the reified twin)
compared them with Python ``==`` except for a char list against a list at the
TOP, so ``b"ab" == [97, 98]`` failed, ``b"ab" != [97, 98]`` succeeded, and a
char list nested in a cell or dict compared by spelling -- while ``=``, the
quoted ``'=='`` and ``compare/3`` all say these are one term.

Leaves keep Python equality: ``[1] == [1.0]`` stays true (arithmetic), as do
the other answers pinned below.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.testing import load_clausal_module

_SRC = """\
-private([a, b, c, ab, f(X), g(X, Y)])
e1 <- ("ab" == [a, b])
e2 <- ("" == [])
e3 <- (b"" == [])
e4 <- (b"ab" == [97, 98])
e5 <- ([97, 98] == b"ab")
e6 <- (f(b"ab") == f([97, 98]))
e7 <- (f("ab") == f([a, b]))
e8 <- ([b"ab"] == [[97, 98]])
e9 <- ([[a, b]] == ["ab"])
e10 <- ({a: "ab"} == {a: [a, b]})
e11 <- (g("ab", [b"a"]) == g([a, b], [[97]]))
n1 <- (b"ab" != [97, 98])
n2 <- ([97, 98] != b"ab")
n3 <- (f("ab") != f([a, b]))
ne1 <- ("ab" != [a, c])
ne2 <- (b"ab" != [97, 99])
ne3 <- (f("ab") != f([a, c]))
ne4 <- ("ab" != ab)
ne5 <- (b"ab" != "ab")
keep1 <- ([1] == [1.0])
keep2 <- (f(1) == f(1.0))
keep3 <- ([True] == [1])
keep4 <- (g(a, [b]) == g(a, [b]))
keep5 <- (f(X) == f(X))
not1 <- ("ab" == ab)
not2 <- ("a" == a)
not3 <- ([1, 2] == [1, 3])
not4 <- ([X] == [Y])
not5 <- (b"ab" == "ab")
not6 <- ([97, 98] == [a, b])
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("eqshapes") / "eqshapes.seam"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _holds(mod, name):
    return any(True for _ in solve(name, mod))


_NAMES = [line.split(" <-")[0] for line in _SRC.splitlines() if " <- " in line]


@pytest.mark.parametrize("name", [n for n in _NAMES if not n.startswith(("n1", "n2", "n3", "not"))])
def test_holds(mod, name):
    assert _holds(mod, name), name


@pytest.mark.parametrize("name", [n for n in _NAMES if n.startswith(("n1", "n2", "n3", "not"))])
def test_fails(mod, name):
    assert not _holds(mod, name), name
