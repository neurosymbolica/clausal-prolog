"""Native .pl: a cut or if-then-else in a goal BUILT AT RUN TIME is local to
the meta-call that runs it (ISO 7.8.3) -- in a .pl module (D59, Task 5).
A ``.clausal`` caller keeps the refusal (``test_clausal_caller_still_refuses``
below; seam callers in tests/test_meta_call_cut_refused.py).

Every expected value is Scryer's for the same program (2026-10-14), except
where a row says otherwise."""
from __future__ import annotations

import pytest

SRC = """\
p(1). p(2). p(3).
a16(L) :- G = (p(X), !), findall(X, call(G), L).
m2(X) :- G = (p(X), !), call(G).
m2(9).
m3(X) :- G = (p(X) -> true ; X = none), call(G).
m3b(X) :- G = (p(X) -> true), call(G).
m3c(X) :- G = (fail -> true), call(G).
m3c(9).
m4(L) :- findall(X, phrase((pp(X), !), [1, 2, 3], _), L).
pp(X) --> [X].
m5(X) :- G = (p(X), !), G.
m5(9).
m6(R) :- G = (p(_), '*->'(true, true)), catch(call(G), error(E, _), R = E).
m12(X) :- G = ((p(X), X > 1) -> ! ; true), call(G).
m12(9).
m13(X) :- G = ((! ; X = 2), X == 2), call(G).
m13(7).
m15(R) :- catch(call((true -> 1 ; true)), error(E, _), R = E).
m16(X) :- call((p(X) -> true ; X = none)).
"""


def test_runtime_built_cut_is_local_to_the_call(native, ans):
    mod = native.load("l3_cut_meta", SRC)
    assert ans(mod, "a16") == [[1]]
    assert ans(mod, "m2") == [1, 9]
    assert ans(mod, "m4") == [[1]]
    assert ans(mod, "m5") == [1, 9]
    # a cut in a Then is transparent to the call's own body, not past it
    assert ans(mod, "m12") == [2, 9]
    # the cut prunes the body's own ``;``, then X == 2 fails the call
    assert ans(mod, "m13") == [7]


def test_runtime_built_if_then_else(native, ans):
    mod = native.load("l3_cut_meta_ite", SRC)
    assert ans(mod, "m3") == [1]
    assert ans(mod, "m3b") == [1]
    assert ans(mod, "m3c") == [9]
    # written literally as call/1's argument: no longer refused at load
    assert ans(mod, "m16") == [1]
    # a number in the Then is checked through ``->`` before anything runs
    assert ans(mod, "m15") == [("type_error", "callable",
                                (";", ("->", True, 1), True))]


def test_soft_cut_stays_refused_at_run_time(native, ans):
    mod = native.load("l3_cut_meta_soft", SRC)
    assert ans(mod, "m6") == [("existence_error", "procedure", ("/", "*->", 2))]


def test_soft_cut_inside_call_stays_refused_at_load(native):
    with pytest.raises(SyntaxError, match=r"`\*->` \(soft-cut\) is refused"):
        native.load("l3_cut_meta_soft_load",
                    "p(1).\nm(X) :- call((p(X) -> '*->'(true, true) ; true)).\n")


# Bodies here call builtins only: a .pl dynamic clause whose body calls a
# user predicate has no term form for clause/2 today (pre-existing,
# independent of cut: ``existence_error(procedure, p/1)`` "nothing declares
# the functor").
CLAUSE_SRC = """\
:- dynamic(d/1).
d(X) :- X = 1, !.
d(X) :- ( X = 2 -> true ; X = 3 ).
d(X) :- ( X = 4 -> true ).
d(X) :- X = 5, true.
m7(L) :- findall(B, clause(d(_), B), L).
m8(N) :- retract((d(_) :- _ = 1, !)), findall(x, clause(d(_), _), L), length(L, N).
m9(N) :- retract((d(_) :- (_ = 2 -> true ; _ = 3))), findall(x, clause(d(_), _), L), length(L, N).
m10(N) :- retract((d(_) :- (_ = 4 -> true))), findall(x, clause(d(_), _), L), length(L, N).
m11(L) :- findall(X, (clause(d(X), B), call(B)), L).
"""


def test_clause_spells_the_cut_and_if_then_else(native, ans):
    from clausal.logic.variables import is_var
    mod = native.load("l3_cut_meta_clause", CLAUSE_SRC)
    [bodies] = ans(mod, "m7")
    # the cut is the atom ``!``; ``->`` the ISO cell, inside ``;`` with an else
    # (Scryer: [(_=1,!), (_=2->true;_=3), (_=4->true), (_=5,true)])
    b1, b2, b3, b4 = bodies
    assert b1[1] == "!" and b1[0][0] == "=" and b1[0][2] == 1 and is_var(b1[0][1])
    assert b2[0] == ";" and b2[1][0] == "->" and b2[1][2] is True
    assert b2[1][1][2] == 2 and b2[2][2] == 3
    assert b3[0] == "->" and b3[1][2] == 4 and b3[2] is True
    assert b4[0][2] == 5
    # the Body clause/2 hands back is callable, and its cut is local to call/1
    assert ans(mod, "m11") == [[1, 2, 4, 5]]


def test_retract_matches_the_cut_and_if_then_else(native, ans):
    for name, want in (("m8", [3]), ("m9", [3]), ("m10", [3])):
        mod = native.load(f"l3_cut_meta_retract_{name}", CLAUSE_SRC)
        assert ans(mod, name) == want, name


def test_solve_from_python_runs_cut_in_a_pl_module(native):
    """Ruling Q2: a Python entry point runs cut when the module is .pl."""
    mod = native.load("l3_cut_meta_solve", SRC)
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    x = Var()
    assert [r["X"] for r in query((",", ("p", x), "!"), {"X": x}, mod)] == [1]
    y = Var()
    assert [r["Y"] for r in query(
        (";", ("->", ("p", y), "true"), ("=", y, "none")), {"Y": y}, mod)] == [1]


def test_clausal_caller_still_refuses(native, ans):
    """S39: the CALLER's db decides -- a .clausal module stays cut-free."""
    mod = native.load("l3_cut_meta_cl",
                      "p(1). p(2).\n"
                      "m(R) :- G = (p(_), !), catch(call(G), error(E, _), R = E).\n",
                      suffix=".clausal")
    assert ans(mod, "m") == [("existence_error", "procedure", ("/", "!", 0))]


PHRASE_SRC = """\
p(1). p(2). p(3).
pp(X) --> [X].
t1(L) :- findall(R, phrase(([a] -> [b] ; [c]), [a,b], R), L).
t2(L) :- findall(R, phrase(([a] -> [b] ; [c]), [c], R), L).
t3(L) :- findall(R, phrase(([a] -> [b] ; [c]), [a,c], R), L).
t4(L) :- findall(R, phrase(([a] -> [b]), [a,b,d], R), L).
t5(L) :- findall(X, phrase(((pp(X), {X > 1}) -> [] ; []), [1,2,3], _), L).
t6(L) :- findall(X-R, phrase((pp(X), !, pp(_)), [1,2,3], R), L).
t7(L) :- findall(X, phrase(({p(X)}, {!}), []), L).
"""


def test_phrase_body_runs_cut_and_if_then_else(native, ans):
    """A grammar body handed to phrase/2,3 at run time (ISO 7.14.2: ``!`` is
    ``!, S0 = S``; ``( C -> T ; E )`` threads the state through C then T)."""
    from clausal.logic.variables import is_var
    mod = native.load("l3_cut_meta_phrase", PHRASE_SRC)
    assert ans(mod, "t1") == [[[]]]
    assert ans(mod, "t2") == [[[]]]
    assert ans(mod, "t3") == [[]]
    # No else: the loader's own DCG translation accepts it too (Scryer's
    # library(dcgs) raises representation_error(dcg_body) here).
    assert ans(mod, "t4") == [[["d"]]]
    [[x]] = ans(mod, "t5")
    assert is_var(x)
    assert ans(mod, "t6") == [[("-", 1, [3])]]
    # ``{!}`` is not local to the braces: it prunes ``{p(X)}``
    assert ans(mod, "t7") == [[1]]
