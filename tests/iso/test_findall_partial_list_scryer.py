"""findall/3 and its kin copy a list built through its open tail, row by row
against Scryer.

``L = [a|T]`` makes a partial list; binding ``T`` later to a list that holds
a variable bound EARLIER (``kk(3, X), T = [c(X), d]``) closes it.  The copy
findall/3 keeps must read every element through its bindings:
``[[a,c(yes),d]]``.  Between 1.0.0 and the 1.2.0 release candidate the walk
of a closed partial list took a hole's list without walking its elements, so
the copy kept the live ``X`` -- unbound again once findall backtracked --
and answered ``[[a,c(_),d]]``.

Every row is one ``.pl`` clause run under BOTH engines from the same text:
the engine test asserts the expected column, the oracle test asserts Scryer
writes the same column.
"""
from __future__ import annotations

import os
import re

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Var
from clausal.terms import term_writeq

from tests._oracles import run_scryer

_PRELUDE = """\
:- use_module(library(lists)).

kk(3, yes).
kk(7, no).

g(L) :- L = [a|R], N = 3, kk(N, X), append([c(X)], [d], R).
g2(L) :- N = 3, kk(N, X), L = [a|R], append([c(X)], [d], R).
g4(L) :- L = [a|R], N = 3, kk(N, X), R = [c(X), d].
"""

# (row name, the clause body binding R, the answer both engines write)
ROWS = [
    ("append_tail", "findall(L, g(L), R)", "[[a,c(yes),d]]"),
    ("bound_before_list", "findall(L, g2(L), R)", "[[a,c(yes),d]]"),
    ("unify_tail", "findall(L, g4(L), R)", "[[a,c(yes),d]]"),
    ("pair_template",
     "findall(L-X, (L = [a|T], kk(3, X), append([c(X)], [d], T)), R)",
     "[[a,c(yes),d]-yes]"),
    ("bound_after_tail",
     "findall(L, (L = [a|T], T = [c(X)], X = yes), R)", "[[a,c(yes)]]"),
    ("deeper_nesting",
     "findall(L, (L = [a|T], X = yes, T = [c(f(X))]), R)", "[[a,c(f(yes))]]"),
    ("several_elements",
     "findall(L, (L = [a,b|T], X = 1, Y = 2, T = [X,c(Y),[X]]), R)",
     "[[a,b,1,c(2),[1]]]"),
    ("tail_in_two_steps",
     "findall(L, (L = [a|T], T = [c(X)|U], X = yes, U = [d(X)]), R)",
     "[[a,c(yes),d(yes)]]"),
    ("append_partial_list",
     "findall(L, (append([a], T, L), X = yes, T = [c(X)]), R)", "[[a,c(yes)]]"),
    ("two_answers",
     "findall(L, (kk(_, X), L = [a|T], T = [c(X)]), R)",
     "[[a,c(yes)],[a,c(no)]]"),
    ("findall_4",
     "findall(L, (L = [a|T], kk(3, X), T = [c(X)]), R, [z])",
     "[[a,c(yes)],z]"),
    ("bagof",
     "bagof(L, T^X^(L = [a|T], kk(3, X), T = [c(X)]), R)", "[[a,c(yes)]]"),
    # ``ab``, not ``a``: Scryer orders ``[a,c(yes)]`` before ``[a,c(no)]``
    # (a list opening with a one-char atom is its partial string there).
    ("setof",
     "setof(L, T^X^N^(L = [ab|T], kk(N, X), T = [c(X)]), R)",
     "[[ab,c(no)],[ab,c(yes)]]"),
    # A cyclic element: the copy is the cyclic term, not a stale variable
    # (nor a raw stack error, as the copy of [Y] with Y = f(Y) was before).
    ("cyclic_element_in_tail",
     "findall(L, (L = [a|T], Y = f(Y), T = [Y]), [[a,Z]]), Z = f(W), (nonvar(W) -> R = yes ; R = no)",
     "yes"),
    ("cyclic_element_in_head",
     "findall(L, (L = [Y|T], Y = f(Y), T = []), [[Z]]), Z = f(W), (nonvar(W) -> R = yes ; R = no)",
     "yes"),
]

_PROGRAM = _PRELUDE + "".join(f"{n}(R) :- {b}.\n" for n, b, _ in ROWS)

_VARNAME = re.compile(r"\b_[A-Za-z0-9]*\b")


def _normalise(text: str) -> str:
    return _VARNAME.sub("_", text.strip())


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("findall_pl") / "findall_partial_list_rows.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    try:
        return _load_module("_findall_partial_list_rows", str(path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


@pytest.fixture(scope="module")
def scryer_program(tmp_path_factory):
    path = tmp_path_factory.mktemp("findall_scryer") / "rows.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("name,_body,expected", ROWS, ids=[r[0] for r in ROWS])
def test_findall_partial_list_engine(mod, name, _body, expected):
    r = Var()
    answers = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    assert len(answers) == 1, (name, answers)
    assert _normalise(answers[0]) == expected


@pytest.mark.parametrize("name,_body,expected", ROWS, ids=[r[0] for r in ROWS])
def test_findall_partial_list_scryer(scryer, scryer_program, name, _body, expected):
    del scryer
    proc = run_scryer(scryer_program, [f"{name}(R), writeq(R), nl, halt."], timeout=60)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines, (name, proc.stdout, proc.stderr[-500:])
    assert _normalise(lines[-1]) == expected
