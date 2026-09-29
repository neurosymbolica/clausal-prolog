"""``true`` as a clause body, written in Prolog source.

A fact's body is the goal ``true``: the engine holds it as ``True``, a
Prolog term spells it with the atom ``true``.  ``clause(s(Y), true)`` found
nothing (the atom never unified with ``True``), even for a procedure
created by assertz, and a ``Head :- Body`` clause term was taken as a fact
of ``(:-)/2``: ``assertz((k(1) :- true))`` stored an uncallable clause and
``retract((u(1) :- true))`` removed nothing.  Every answer and error term
below is Scryer's for the same goal (2026-09-30), except the runtime rule
refusal (Clausal asserts no rule at runtime; it used to be silent)."""
from __future__ import annotations

SRC = """\
:- dynamic(dd/1).
dd(0).
dd(5).
t1(L) :- assertz(s(1)), assertz(s(2)), findall(Y, clause(s(Y), true), L).
t2(L) :- findall(Y, clause(dd(Y), true), L).
t3(L) :- assertz(u(1)), assertz(u(2)), retract((u(1) :- true)), findall(Z, u(Z), L).
t4(L) :- assertz((k(1) :- true)), asserta((k(0) :- true)), findall(X, k(X), L).
t5(E) :- catch(assertz((foo :- 4)), E, true).
t6(E) :- catch(assertz((_ :- true)), E, true).
t7(E) :- catch(assertz((4 :- true)), E, true).
t8(E) :- catch(retract((_ :- true)), E, true).
t9(E) :- catch(assertz((foo(X) :- X = 1)), error(E, _), true).
t10(B) :- assertz(v(1)), retract((v(1) :- B)).
t11(L) :- assertz(w(1)), assertz(w(2)), retract((w(X) :- _)), findall(X-Y, w(Y), L).
"""


def test_true_body_in_prolog_source(native, ans):
    mod = native.load("l3_clause_true", SRC)
    assert ans(mod, "t1") == [[1, 2]]
    assert ans(mod, "t2") == [[0, 5]]
    assert ans(mod, "t3") == [[2]]
    assert ans(mod, "t4") == [[0, 1]]
    assert ans(mod, "t5") == [("error", ("type_error", "callable", 4), ("/", "assertz", 1))]
    assert ans(mod, "t6") == [("error", "instantiation_error", ("/", "assertz", 1))]
    assert ans(mod, "t7") == [("error", ("type_error", "callable", 4), ("/", "assertz", 1))]
    assert ans(mod, "t8") == [("error", "instantiation_error", ("/", "retract", 1))]
    (e,) = ans(mod, "t9")
    assert e[0] == "permission_error" and e[1:3] == ("assert", "rule")
    # an unbound body is `true` for a fact (the engine's True)
    assert ans(mod, "t10") == [True]
    assert ans(mod, "t11") == [[("-", 1, 2)]]
