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


def test_retractall_matches_the_head_whatever_the_body(tmp_path):
    """retractall(Head) removes every clause whose HEAD unifies (ISO 8.9.5).
    A seam rule's own ``X is 3`` (a unification) used to read as a head
    test, keeping ``h(X) <- (X is 3)`` out of ``retractall(h(5))``.
    Scryer, for ``h(X) :- X = 3. h(7).``: t1 [7], t2 [], t3 []."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    for name, goal, want in (("t1", "5", [7]), ("t2", "7", []),
                             ("t3", "_", [])):
        p = tmp_path / f"_retractall_{name}.clausal"
        p.write_text("-allow_singletons\n-dynamic(h/1)\nh(X) <- (X is 3)\nh(7),\n"
                     f"t(L) <- (retractall(h({goal})), findall(Y, h(Y), L))\n")
        m = _load_module(f"_retractall_{name}", str(p))
        v = Var()
        assert [_deref_walk(v) for _ in solve(("t", v), m)] == [want], name


def test_more_patterns(native, ans):
    """Scryer: a fact with a compound argument retracts by its value;
    retract(Head) of a predicate with only rules fails.  (A multi-goal rule
    body does not match yet: the engine's body term is a flat tuple, the
    Prolog pattern a ','/2 cell -- todo/conjunction-starting-with-an-atom-
    is-a-compound-2026-09-25.md.)"""
    src = (":- dynamic(f/1).\n:- dynamic(g/1).\n:- dynamic(q/1).\n"
           "f(p(1, [a])).\nf(p(2, [b])).\n"
           "g(X) :- X = 1, X > 0.\ng(5).\n"
           "q(X) :- X = 1.\n"
           "t1(L) :- retract(f(p(2, _))), findall(Y, f(Y), L).\n"
           "t2(L) :- retract((g(X) :- X = 1, X > 0)), findall(Y, g(Y), L).\n"
           "t3(L) :- findall(x, retract(q(_)), L).\n")
    for name, want in (("t1", [[("p", 1, ["a"])]]), ("t3", [[]])):
        mod = native.load(f"l3_retract_more_{name}", src)
        assert ans(mod, name) == want, name
