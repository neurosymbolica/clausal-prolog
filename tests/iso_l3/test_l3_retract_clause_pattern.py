"""retract/1 matches the clause pattern ISO 8.9.3 describes.

retract(Head) is retract((Head :- true)): it removes a FACT.  It used to
test the head plus every ``Unify`` in the body, so ``retract(r(_))``
removed the RULE ``r(X) :- X = 1`` (Scryer removes the fact ``r(2)``), and
``retract((r(X) :- X = 1))`` removed nothing.  Every answer below is
Scryer's for the same program (2026-09-30)."""
from __future__ import annotations

SRC = """\
:- dynamic(r/1).
r(X) :- X = 1.
r(2).
t1(L) :- retract(r(_)), findall(Y, r(Y), L).
t3(L) :- retract((r(X) :- X = 1)), findall(Y, r(Y), L).
t4(L) :- retract((r(_) :- _)), findall(Y, r(Y), L).
t5(L) :- retract((r(_) :- X = 1)), findall(Y, r(Y), L), L = [_|_], X = X.
"""


def test_retract_pattern(native, ans):
    for name, want in (("t1", [[1]]), ("t3", [[2]]), ("t4", [[2]]),
                       ("t5", [[2]])):
        mod = native.load(f"l3_retract_{name}", SRC)
        assert ans(mod, name) == want, name


def test_retract_of_a_rule_body_binds_it(native, ans):
    mod = native.load("l3_retract_bind",
                      ":- dynamic(r/1).\nr(X) :- X = 1.\nr(2).\n"
                      "t(B) :- retract((r(_) :- B)).\n")
    (b,) = ans(mod, "t")
    assert b[0] == "=" and b[2] == 1
