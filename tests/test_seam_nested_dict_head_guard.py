"""A seam head variable nested in a dict, or in a list inside a dict, or in a
dict inside a list, is the SAME variable the clause body reads.

``n({'k': {'j': X}}) <- (X == 1)`` answered True for ``{'k': {'j': 2}}``: the
head pre-pass (``_head_arg_patterns`` with no guard sink) registered only a
dict's TOP-LEVEL variable values, and the list branch walked only nested
lists, so a variable deeper inside never reached the head's variable context.
The body compiler then took the body's first ``X`` for a fresh variable and
allocated a new one after the head unify -- the guard read an unbound
variable (``X == 1`` posts a constraint on it and succeeds), and an answer
variable shared with ``X`` came back unbound.

The same root also hid two allocation defects, fixed with it: a dict value
that was already a direct match capture (``o(X, {'k': X})``) was overwritten
by a fresh ``Var()``, and a variable shared between a list guard and a dict
guard (``p([X], {'k': X})``) was allocated twice, the second after the list
guard had bound it.
"""

from __future__ import annotations

import re

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var
from clausal.testing import load_clausal_module
from tests._suffix import SEAM as SEAM_EXT


SEAM_CLAUSES = """\
a1({'k': {'j': X}}) <- (X == 1)
a2({'k': [X]}) <- (X == 1)
a3([{'k': X}]) <- (X == 1)
a4([[X]]) <- (X == 1)
a5({'k': X}) <- (X == 1)
a6({'k': {'j': {'k': X}}}) <- (X == 1)
a7([[{'k': [X]}]]) <- (X == 1)
a8({'k': pt(X)}) <- (X == 1)
a9([pt(X)]) <- (X == 1)
a10(pt({'k': X})) <- (X == 1)
a11({'k': {'j': X}}) <- (X > 5)
a12({'k': {'j': X}}) <- (X != 1)
a13({'k': [H, *T]}) <- (H == 1, T == [2])
m1({'k': {'j': X}, 'j': Y}) <- (X == 1, Y == 2)
m2({'k': [X, Y]}) <- (X == 1, Y == 2)
m3([{'k': X}, {'j': [Y]}]) <- (X == 1, Y == 2)
o1({'k': {'j': X}}, Y) <- (X == 1, Y is X)
o2(X, {'k': {'j': X}}) <- (X == 1)
o3({'k': {'j': X}}, X) <- (X == 1)
o4(X, {'k': X}) <- (X == 1)
o5({'k': X}, X) <- (X == 1)
o6([{'k': X}], X) <- (X == 1)
o7(X, [{'k': X}]) <- (X == 1)
o8({'k': {'j': X}}, Y) <- (Y is X)
o9({'k': {'j': X}, 'j': X}) <- (X == 1)
o10([X], {'k': X}) <- (X == 1)
o11({'k': X}, [X]) <- (X == 1)
o12({'k': [X]}, {'j': {'k': X}}) <- (X == 1)
ix('a', {'k': {'j': X}}) <- (X == 1)
ix('b', {'k': {'j': X}}) <- (X == 2)
ix('c', [{'k': X}]) <- (X == 3)
ld([]) <- True
ld([{'k': X}, *T]) <- (X == 1, ld(T))
"""


def _arities(text):
    """name/arity for each clause head, for the -shallow directive."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"(\w+)\((.*)\) <-", line)
        if not m or m.group(1) in out:
            continue
        depth, n = 0, 1
        for ch in m.group(2):
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                n += 1
        out[m.group(1)] = n
    return ", ".join(f"{k}/{v}" for k, v in out.items())


def _seam_source(strategy):
    head = "-module(pq, [pt(A)])\n-private([k, j])\n"
    if strategy == "shallow":
        head += f"-shallow([{_arities(SEAM_CLAUSES)}])\n"
    return head + SEAM_CLAUSES


@pytest.fixture(scope="module", params=["trampoline", "shallow"])
def mod(request, tmp_path_factory):
    p = tmp_path_factory.mktemp("nested_dict_guard") / ("pq" + SEAM_EXT)
    p.write_text(_seam_source(request.param))
    return load_clausal_module(p)


def _holds(mod, name, *args):
    return any(True for _ in solve((name, *args), mod))


def _answers(mod, name, *args):
    """Each answer's value for every Var among *args*."""
    vs = [a for a in args if isinstance(a, Var)]
    out = []
    for _ in solve((name, *args), mod):
        out.append(tuple(v.value for v in vs))
    return out


def J(x):
    return {"k": {"j": x}}


def PT(x):
    return ("pt", x)


# (predicate, argument builder): the guard holds for 1 and fails for 2
GUARD_EQ_ONE = [
    ("a1", lambda x: (J(x),)),
    ("a2", lambda x: ({"k": [x]},)),
    ("a3", lambda x: ([{"k": x}],)),
    ("a4", lambda x: ([[x]],)),
    ("a5", lambda x: ({"k": x},)),
    ("a6", lambda x: ({"k": {"j": {"k": x}}},)),
    ("a7", lambda x: ([[{"k": [x]}]],)),
    ("a8", lambda x: ({"k": PT(x)},)),
    ("a9", lambda x: ([PT(x)],)),
    ("a10", lambda x: (PT({"k": x}),)),
    ("m1", lambda x: ({"k": {"j": x}, "j": 2},)),
    ("m2", lambda x: ({"k": [x, 2]},)),
    ("m3", lambda x: ([{"k": x}, {"j": [2]}],)),
    ("o2", lambda x: (x, J(1))),
    ("o3", lambda x: (J(1), x)),
    ("o4", lambda x: (x, {"k": 1})),
    ("o5", lambda x: ({"k": 1}, x)),
    ("o6", lambda x: ([{"k": 1}], x)),
    ("o7", lambda x: (x, [{"k": 1}])),
    ("o9", lambda x: ({"k": {"j": x}, "j": 1},)),
    ("o10", lambda x: ([x], {"k": 1})),
    ("o11", lambda x: ({"k": 1}, [x])),
    ("o12", lambda x: ({"k": [x]}, {"j": {"k": 1}})),
]


@pytest.mark.parametrize("name, build", GUARD_EQ_ONE,
                         ids=[n for n, _ in GUARD_EQ_ONE])
def test_guard_reads_the_head_variable(mod, name, build):
    assert _holds(mod, name, *build(1))
    assert not _holds(mod, name, *build(2))


def test_guard_rejects_a_non_number(mod):
    assert not _holds(mod, "a1", J("zzz"))


@pytest.mark.parametrize("value, expected", [(6, True), (2, False), (1, False)])
def test_greater_than_guard(mod, value, expected):
    assert _holds(mod, "a11", J(value)) is expected


@pytest.mark.parametrize("value, expected", [(1, False), (2, True)])
def test_not_equal_guard(mod, value, expected):
    assert _holds(mod, "a12", J(value)) is expected


def test_second_variable_of_a_dict_guard_is_checked(mod):
    assert _holds(mod, "m1", {"k": {"j": 1}, "j": 2})
    assert not _holds(mod, "m1", {"k": {"j": 1}, "j": 3})
    assert not _holds(mod, "m2", {"k": [1, 3]})
    assert not _holds(mod, "m3", [{"k": 1}, {"j": [3]}])


def test_star_list_inside_a_dict(mod):
    assert _holds(mod, "a13", {"k": [1, 2]})
    assert not _holds(mod, "a13", {"k": [2, 2]})
    assert not _holds(mod, "a13", {"k": [1, 3]})


def test_nested_variable_reaches_the_answer(mod):
    y = Var()
    assert _answers(mod, "o1", J(1), y) == [(1,)]
    assert _answers(mod, "o1", J(2), Var()) == []
    y = Var()
    assert _answers(mod, "o8", J(7), y) == [(7,)]
    w = Var()
    assert _answers(mod, "o3", J(1), w) == [(1,)]


def test_first_argument_indexed_clauses(mod):
    assert _holds(mod, "ix", "a", J(1))
    assert not _holds(mod, "ix", "a", J(2))
    assert _holds(mod, "ix", "b", J(2))
    assert not _holds(mod, "ix", "b", J(1))
    assert _holds(mod, "ix", "c", [{"k": 3}])
    assert not _holds(mod, "ix", "c", [{"k": 1}])
    k = Var()
    assert [a[0] for a in _answers(mod, "ix", k, J(2))] == ["b"]


def test_list_dispatched_clauses(mod):
    assert _holds(mod, "ld", [])
    assert _holds(mod, "ld", [{"k": 1}, {"k": 1}])
    assert not _holds(mod, "ld", [{"k": 1}, {"k": 2}])
    assert not _holds(mod, "ld", [{"k": 2}])


# A ``.clausal`` or ``.pl`` head's ``{...}`` is a CURLY TERM, not a dict: the
# same shapes there keep answering as ISO says.
PROLOG = """\
n({k: {j: X}}) :- X == 1.
c({k: [X]}) :- X == 1.
e([{k: X}]) :- X == 1.
t1 :- n({k: {j: 1}}).
t2 :- n({k: {j: 2}}).
t3 :- c({k: [1]}).
t4 :- c({k: [2]}).
t5 :- e([{k: 1}]).
t6 :- e([{k: 2}]).
"""


@pytest.fixture(scope="module", params=["p.pl", "p.clausal"])
def prolog_mod(request, tmp_path_factory):
    p = tmp_path_factory.mktemp("nested_curly_guard") / request.param
    p.write_text(PROLOG)
    return load_clausal_module(p)


@pytest.mark.parametrize("name, expected", [
    ("t1", True), ("t2", False), ("t3", True),
    ("t4", False), ("t5", True), ("t6", False),
])
def test_prolog_curly_heads_unchanged(prolog_mod, name, expected):
    assert any(True for _ in solve(name, prolog_mod)) is expected
