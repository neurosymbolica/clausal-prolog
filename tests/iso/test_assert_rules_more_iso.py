"""Asserting rules in a ``.pl`` file (ISO 13211-1 8.9, operator ruling
2026-11-03), beyond the pinned rows of ``test_assert_rules_iso.py``:

* the logical update view (ISO 7.5.4): a running call sees the clauses as
  they were when it started, through assertz, asserta and retract made
  while it runs;
* retract/1 of rules: the body unifies, ``retract(H)`` removes a fact only,
  re-execution over the call's snapshot;
* clause/2 of an asserted rule gives the ISO body term;
* variables shared between head and body, and ISO's copy at assert time;
* cut: local to the asserted clause whoever calls it, opaque inside
  ``\\+``, ``call/1`` and findall/3;
* an asserted rule called from a Clausal Prolog module through call/N.

Every row's expected answer is Scryer's (``test_oracle``), except
``DIFFERS_FROM_SCRYER``: there ISO (and the clause the same text gives when
consulted, in both systems) is followed.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

#: (row name, body binding R, what both print)
ROWS = [
    # ── the logical update view (ISO 7.5.4) ──
    ("assertz while iterating is not seen",
     "assertz(u1(1)), assertz(u1(2)),"
     " findall(X, (u1(X), Y is X + 10, assertz(u1(Y))), L1),"
     " findall(X, u1(X), L2), R = L1-L2",
     ["[1,2]-[1,2,11,12]"]),
    ("asserta while iterating is not seen",
     "assertz(u2(1)), assertz(u2(2)),"
     " findall(X, (u2(X), asserta(u2(0))), L1), findall(X, u2(X), L2),"
     " R = L1-L2",
     ["[1,2]-[0,0,1,2]"]),
    ("a rule asserted while its predicate runs is not seen",
     "assertz((u3(X) :- X = aa)),"
     " findall(X, (u3(X), assertz((u3(Y) :- Y = bb))), L1),"
     " findall(X, u3(X), L2), R = L1-L2",
     ["[aa]-[aa,bb]"]),
    ("a clause retracted while iterating is still answered",
     "assertz(u4(1)), assertz(u4(2)), assertz(u4(3)),"
     " findall(X, (u4(X), retract(u4(3))), L1), findall(X, u4(X), L2),"
     " R = L1-L2",
     ["[1]-[1,2]"]),
    ("a rule retracted while it runs keeps running",
     "assertz((u5(X) :- member(X, [aa, bb, cc]))),"
     " findall(X, (u5(X), ( X == aa -> retract((u5(_) :- _)) ; true )), L1),"
     " findall(X, u5(X), L2), R = L1-L2",
     ["[aa,bb,cc]-[]"]),
    ("retract re-executes over its call's snapshot",
     "assertz(u6(1)), assertz(u6(2)),"
     " findall(X-Y, (u6(X), retract(u6(Y))), R)",
     ["[1-1,1-2]"]),
    ("retract re-executes over rules too",
     "assertz((u7(X) :- X = 1)), assertz((u7(X) :- X = 2)),"
     " findall(B, retract((u7(_) :- B)), L1), findall(X, u7(X), L2),"
     " R = L1-L2",
     ["[_=1,_=2]-[]"]),
    # ── retract((H :- B)) ──
    ("retract((H :- B)) binds a conjunction body",
     "assertz((v1(X) :- X = 1, true)), retract((v1(Z) :- B)), R = Z-B",
     ["_1-(_1=1,true)"]),
    ("retract(H) removes a fact, not a rule",
     "assertz((v2(X) :- a1(X))), ( retract(v2(_)) -> A = removed ; A = kept ),"
     " findall(X, v2(X), L), R = A-L",
     ["kept-[dog]"]),
    ("retract((H :- B)) with a body that does not unify fails",
     "assertz((v3(X) :- a1(X))),"
     " ( retract((v3(_) :- a2(_))) -> A = removed ; A = kept ), R = A",
     ["kept"]),
    ("retract((H :- B)) unifies the body's instance",
     "assertz((v4(X) :- a1(X))), retract((v4(_) :- a1(dog))),"
     " findall(X, v4(X), R)",
     ["[]"]),
    ("retract of one rule leaves its neighbours",
     "assertz(v5(0)), assertz((v5(X) :- X = 1)), assertz(v5(2)),"
     " retract((v5(_) :- _ = 1)), findall(X, v5(X), R)",
     ["[0,2]"]),
    # ── clause/2 of asserted rules: ISO body terms ──
    ("clause/2: disjunction, negation and if-then-else as written",
     "assertz((w1(X) :- (X = 1 ; X = 2), \\+ X = 3, ( X > 0 -> true ; fail ))),"
     " clause(w1(A), B), R = A-B",
     ["_1-((_1=1;_1=2),\\+_1=3,(_1>0->true;fail))"]),
    ("clause/2: a cut in the body",
     "assertz((w2(X) :- member(X, [1, 2]), !)), clause(w2(A), B), R = A-B",
     ["_1-(member(_1,[1,2]),!)"]),
    ("clause/2: a meta-call body",
     "assertz((w3(L) :- findall(X, member(X, [1]), L))), clause(w3(A), B),"
     " R = A-B",
     ["_1-findall(_2,member(_2,[1]),_1)"]),
    ("clause/2: a structured head argument",
     "assertz((w4(f(X), [X]) :- X > 0)), clause(w4(A, C), B), R = A-C-B",
     ["f(_1)-[_1]-(_1>0)"]),
    ("clause/2: the body pattern unifies",
     "assertz((w5(X) :- X = 1, a1(X))), clause(w5(_), (G1, _)), R = G1",
     ["_=1"]),
    # ── variables shared between head and body; ISO's copy ──
    ("a head variable used in the body",
     "assertz((x1(X, Y) :- Y is X * 2)), x1(3, R)", ["6"]),
    ("a variable shared by several body goals",
     "assertz((x2(X, Z) :- Y is X + 1, Z is Y * Y)), x2(2, R)", ["9"]),
    ("each call renames the clause",
     "assertz((x3(X, X) :- true, true)), x3(a, A), x3(b, B), R = A-B",
     ["a-b"]),
    ("the clause is a copy: later bindings do not reach it",
     "T = f(Y), assertz((x4(T) :- Y = 1)), Y = 2, x4(f(Z)), R = Z",
     ["1"]),
    ("a caller's variable is not bound by the asserted clause",
     "assertz((x5(Q) :- Q = bound)), assertz((x6 :- x5(_))), x6,"
     " ( var(Q) -> R = free ; R = Q )",
     ["free"]),
    ("the head and body share a structured term",
     "assertz((x7(p(X, Y)) :- Y = s(X))), x7(p(z, A)), R = A", ["s(z)"]),
    # ── cut: local to the asserted clause, opaque inside \\+ and call/1 ──
    ("a cut prunes the later clauses of its own predicate",
     "assertz((y1(X) :- X = 1, !)), assertz(y1(2)),"
     " findall(X, y1(X), L), ( y1(2) -> A = y ; A = n ), R = L-A",
     ["[1]-y"]),
    ("a cut does not reach the caller",
     "assertz((y2(X) :- member(X, [a, b]), !)),"
     " findall(N-X, (member(N, [1, 2]), y2(X)), R)",
     ["[1-a,2-a]"]),
    ("a cut does not reach a call/N caller",
     "assertz((y3(X) :- member(X, [a, b]), !)),"
     " findall(N-X, (member(N, [1, 2]), call(y3, X)), R)",
     ["[1-a,2-a]"]),
    ("a cut inside \\+ is local to it",
     "assertz((y4(X) :- member(X, [1, 2, 3]), \\+ (X =:= 2, !, fail))),"
     " findall(X, y4(X), R)",
     ["[1,2,3]"]),
    ("call(!) is opaque",
     "assertz((y5(X) :- member(X, [1, 2, 3]), call(!))), findall(X, y5(X), R)",
     ["[1,2,3]"]),
    ("a cut inside call/1 prunes only inside it",
     "assertz((y6(X) :- call((member(X, [1, 2, 3]), !)))),"
     " findall(X, y6(X), R)",
     ["[1]"]),
    ("a cut inside findall/3 is local to it",
     "assertz((y7(L, Y) :- findall(X, (member(X, [1, 2, 3]), !), L),"
     " member(Y, [a, b]))), findall(L-Y, y7(L, Y), R)",
     ["[[1]-a,[1]-b]"]),
    ("a cut in the then branch cuts the clause",
     "assertz((y9(X) :- ( true -> member(X, [1, 2]), ! ; true ))),"
     " assertz(y9(3)), findall(X, y9(X), R)",
     ["[1]"]),
    ("a cut in a disjunction cuts the clause",
     "assertz((y10(X) :- ( X = 1, ! ; X = 2 ))), assertz(y10(3)),"
     " findall(X, y10(X), R)",
     ["[1]"]),
    # ── a body variable goal ──
    ("a variable body goal is call/1 at run time",
     "assertz((z1(G) :- G)), findall(X, z1(member(X, [1, 2])), R)",
     ["[1,2]"]),
    ("a variable body goal, unbound when called",
     "assertz((z2(G) :- G)), catch(z2(_), error(E, _), R = E)",
     ["instantiation_error"]),
    ("a cut through a variable body goal is local (call/1)",
     "assertz((z3(G) :- G)), assertz(z3(_)), findall(xx, z3(!), R)",
     ["[xx,xx]"]),
    ("asserted rules calling asserted rules",
     "assertz((z4(X) :- z5(X))), assertz((z5(X) :- member(X, [pp, qq]))),"
     " findall(X, z4(X), R)",
     ["[pp,qq]"]),
    ("a recursive asserted rule",
     "assertz(z6(0, [])),"
     " assertz((z6(N, [N|T]) :- N > 0, M is N - 1, z6(M, T))), z6(3, R)",
     ["[3,2,1]"]),
]

#: Rows where ISO, not Scryer, is followed: (name, body, the engine's
#: answer, Scryer's).  In each the asserted clause behaves as the same
#: clause CONSULTED does, in the engine and in Scryer alike:
#:
#: * ISO 8.9.1.1 converts the body (7.6.2), so a variable goal is stored as
#:   ``call(G)`` -- as Scryer stores ``foo(X) :- X.`` when it consults it;
#:   Scryer's assertz alone keeps the bare variable.
#: * ISO 7.8.8: a cut in the condition of if-then-else is local to the
#:   condition (Trealla agrees: ``[1-t,9-last]``).  Scryer lets it cut the
#:   clause, for a consulted clause too (``y8(X, Y) :- ( member(X, [1, 2]),
#:   ! -> Y = t ; Y = e ). y8(9, last).`` gives ``[1-t]`` there).
DIFFERS_FROM_SCRYER = [
    ("clause/2 of a variable body goal is call/1",
     "assertz((ds1(G) :- G)), clause(ds1(A), B), R = A-B",
     ["_1-call(_1)"], ["_1-_1"]),
    ("a cut in the condition of if-then-else is local to it",
     "assertz((ds2(X, Y) :- ( member(X, [1, 2]), ! -> Y = t ; Y = e ))),"
     " assertz(ds2(9, last)), findall(X-Y, ds2(X, Y), R)",
     ["[1-t,9-last]"], ["[1-t]"]),
]

PROGRAM = (
    ":- use_module(library(lists)).\n"
    "a1(dog).\n"
    + "".join(f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))
    + "".join(f"d{i}(R) :- {body}.\n"
              for i, (_, body, _, _) in enumerate(DIFFERS_FROM_SCRYER)))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("assert_rules_more")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_iso_assert_rules_more_1103"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", [pytest.param(i, id=r[0])
                               for i, r in enumerate(ROWS)])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


@pytest.mark.parametrize("i", [pytest.param(i, id=r[0])
                               for i, r in enumerate(DIFFERS_FROM_SCRYER)])
def test_engine_iso_where_scryer_differs(pl_mod, i):
    assert _engine_answers(pl_mod, f"d{i}", 3) == DIFFERS_FROM_SCRYER[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    goals = ([(f"r{i}(R)", 3) for i in range(len(ROWS))]
             + [(f"d{i}(R)", 3) for i in range(len(DIFFERS_FROM_SCRYER))])
    got = _scryer_answers(PROGRAM, goals)
    want = ([r[2] for r in ROWS] + [r[3] for r in DIFFERS_FROM_SCRYER])
    bad = [(g, w, x) for (g, _), w, x in zip(goals, want, got) if w != x]
    assert not bad, bad
