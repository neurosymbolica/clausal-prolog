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


# Bodies here call builtins only: clause/2 on a .pl dynamic clause whose
# body calls a user predicate raises
# ``permission_error(access, private_procedure, d/1)`` today (pre-existing,
# independent of cut; todo/clause-2-pl-dynamic-body-calling-user-predicate-
# 2026-10-14.md).
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
    # (an ISO body is the term as read, so a conjunction is its ``,`` cell)
    assert b1[0] == "," and b1[2] == "!"
    assert b1[1][0] == "=" and b1[1][2] == 1 and is_var(b1[1][1])
    assert b2[0] == ";" and b2[1][0] == "->" and b2[1][2] is True
    assert b2[1][1][2] == 2 and b2[2][2] == 3
    assert b3[0] == "->" and b3[1][2] == 4 and b3[2] is True
    assert b4[0] == "," and b4[1][2] == 5 and b4[2] is True
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


# A meta-argument goal is converted when the meta-call CALLS it (ISO 8.10.1,
# 8.15.2, 7.8.9): a variable reached through ``,``/``;``/``->`` inside it is
# bound by then, so a cut it holds is transparent to the goal's own ``;``.
# (A clause BODY is converted at consult, 7.6.2: there it is call(G).)
META_ARG_SRC = """\
p(1). p(2). p(3).
f1(L) :- G = (p(X), !), findall(X, (G ; X = 8), L).
f2(L) :- G = (p(X), !), findall(X, ((G ; X = 8), true), L).
f3(L) :- G = (p(X), !), findall(X, catch((G ; X = 8), _, true), L).
f4(L) :- G = !, findall(X, ((X = 1 ; X = 2), G), L).
f5(R) :- G = (!, fail), ( once((G ; true)) -> R = yes ; R = no ).
f6(R) :- G = (!, fail), ( catch((G ; true), _, true) -> R = yes ; R = no ).
f7(R) :- G = (p(X), !), ( forall((G ; X = 8), X < 5) -> R = yes ; R = no ).
f8(L) :- G = (p(X) -> true), findall(X, (G ; X = 8), L).
f9(L) :- G = (p(X), !), bagof(X, Y^(G ; X = 8 ; Y = 1), L).
f10(R) :- G = 1, catch((once((X = 8 ; G)), R = ok(X)), error(E, _), R = E).
f11(R) :- G = (!, fail), catch(( catch(throw(x), _, (G ; true)) -> R = yes ; R = no ), _, R = err).
f12(L) :- findall(Y, ((Y = 1 ; Y = 2), true), L).
body(X) :- G = (p(X), !), (G ; X = 8).
"""


@pytest.mark.parametrize("name,want", [
    ("f1", [[1]]), ("f2", [[1]]), ("f3", [[1]]), ("f4", [[1]]),
    ("f5", ["no"]), ("f6", ["no"]),
    # Scryer has forall/2 only as library code, ``\\+ (C, \\+ A)`` on the
    # passed term: [yes] there.
    ("f7", ["yes"]),
    ("f8", [[1]]), ("f9", [[1]]), ("f11", ["no"]),
    # cut-free meta-arguments are untouched
    ("f12", [[1, 2]]),
    # control: a clause body converts at consult -- call(G) is local
    ("body", [1, 8]),
])
def test_a_meta_argument_is_converted_when_it_is_called(native, ans, name,
                                                        want):
    mod = native.load("l3_cut_meta_arg", META_ARG_SRC)
    assert ans(mod, name) == want


def test_a_non_callable_bound_into_a_meta_argument_is_a_type_error(native, ans):
    """Scryer: type_error(callable, (X=8;1)) -- the whole goal, checked when
    once/1 converts it.  It used to answer ok(8)."""
    from clausal.logic.variables import is_var
    mod = native.load("l3_cut_meta_arg_te", META_ARG_SRC)
    [r] = ans(mod, "f10")
    assert r[0] == "type_error" and r[1] == "callable"
    culprit = r[2]
    assert culprit[0] == ";" and culprit[1][0] == "=" and is_var(culprit[1][1])
    assert culprit[1][2] == 8 and culprit[2] == 1


# An if-then-else body is ONE goal, never a conjunction: its ISO cell
# ``(";", ("->", C, T), E)`` is a 3-tuple, the same shape as the engine's
# flat conjunction of three goals.  Scryer's answers for this program.
ITE_CLAUSE_SRC = """\
:- dynamic(d/1).
d(X) :- ( X = 2 -> true ; X = 3 ).
d(X) :- X = 1, !.
d(X) :- ( X = 4 -> true ).
d(X) :- X = 5, X > 0, true.
g1(C) :- retract((d(_) :- (_ , C))).
g2(A-B) :- clause(d(_), (A ; B)).
g3(x) :- retract((d(_) :- (_ ; _))).
g4(x) :- clause(d(_), (_, _)).
g5(x) :- clause(d(_), (_, _, _)).
g6(A-B) :- clause(d(_), (A -> B)).
g7(L) :- findall(B, clause(d(_), B), L).
"""


def test_clause_tells_an_if_then_else_body_from_a_conjunction(native, ans):
    mod = native.load("l3_cut_meta_ite_clause", ITE_CLAUSE_SRC)
    [(_, a, b)] = ans(mod, "g2")
    assert a[0] == "->" and a[1][2] == 2 and a[2] is True and b[2] == 3
    assert ans(mod, "g4") == ["x", "x"]      # X = 1, ! and the 3-goal body
    assert ans(mod, "g5") == ["x"]           # the 3-goal body only
    [(_, c, t)] = ans(mod, "g6")
    assert c[2] == 4 and t is True


def test_retract_never_takes_an_if_then_else_for_a_conjunction(native, ans):
    mod = native.load("l3_cut_meta_ite_retract", ITE_CLAUSE_SRC)
    # Scryer: [!, (_>0, true)] -- the ITE clause is NOT one of them
    first, second = ans(mod, "g1")
    assert first == "!"
    assert second[0] == "," and second[1][0] == ">" and second[2] is True
    [left] = ans(mod, "g7")
    assert [b[0] for b in left] == [";", "->"]


def test_retract_of_a_disjunction_pattern_takes_the_if_then_else(native, ans):
    mod = native.load("l3_cut_meta_ite_retract_or", ITE_CLAUSE_SRC)
    assert ans(mod, "g3") == ["x"]
    [left] = ans(mod, "g7")
    assert len(left) == 3 and left[1][0] == "->"


# ``\+`` is the built-in predicate 8.15.1, true iff call(Term) fails: its
# argument is converted when it RUNS, like any meta-argument's.
NEG_SRC = """\
p(1). p(2).
n1(R) :- G = (!, fail), ( \\+ (G ; true) -> R = yes ; R = no ).
n8(R) :- G = (!, fail), findall(x, \\+ (G ; true), R).
n9(R) :- G = 1, catch(( \\+ (fail, G) -> R = yes ; R = no ), error(E, _), R = E).
n10(R) :- ( \\+ (fail ; true) -> R = yes ; R = no ).
n11(R) :- G = (!, fail), ( once((G ; true)) -> R = yes ; R = no ).
"""


@pytest.mark.parametrize("name,want", [
    # Scryer, Trealla and ISO: [[x]]
    ("n8", [["x"]]),
    ("n9", [("type_error", "callable", (",", "fail", 1))]),
    ("n10", ["no"]),
    # once/1 and \\+ agree: the goal fails under once, so \\+ succeeds
    ("n11", ["no"]),
    # DELIBERATE divergence from Scryer's clause body ([no]): ISO 8.15.1
    # makes \\+ a predicate that calls its argument, and Scryer itself
    # answers yes for the same \\+ inside findall (n8), for
    # ``\\+ call((G ; true))`` and for ``H = (G ; true), \\+ H`` -- its [no]
    # here is an artefact of compiling \\+ inline.
    ("n1", ["yes"]),
])
def test_negation_converts_its_argument_when_it_runs(native, ans, name, want):
    mod = native.load("l3_cut_meta_neg", NEG_SRC)
    assert ans(mod, name) == want


# A conjunction pattern nested inside a construct must never match a single
# compound goal (the stored body's flat tuple ``("=", X, 2)``): that deleted
# clauses Scryer keeps.  Scryer's answers for this program.
NESTED_SRC = """\
:- dynamic(d/2).
d(1, X) :- ( X = 1 -> X = 2 ; true ).
d(4, X) :- ( X = 1 -> true ; X = 2 ).
d(7, X) :- X = 0, ( X = 1 -> true ; X = 2 ).
d(8, X) :- ( X = 1 -> true ; X = 2, X = 3 ).
v3(L) :- findall(N, retract((d(N, _) :- (_ ; (_, _)))), L).
v6(L) :- findall(N, retract((d(N, _) :- (_, (_ ; (_, _))))), L).
v10(L) :- findall(N, retract((d(N, _) :- (_ ; (_, _, _)))), L).
y1(L) :- findall(N, retract((d(N, _) :- (_ -> (_, _, 2) ; _))), L).
y2(L) :- findall(N, retract((d(N, _) :- (_ ; (_, _, 2)))), L).
k1(L) :- findall(N, clause(d(N, _), (_ -> _ ; (_, _))), L).
k2(L) :- findall(N, clause(d(N, _), (_, (_ -> _ ; _))), L).
k3(L) :- findall(N, clause(d(N, _), (_ -> _ ; (_ = 2, _ = 3))), L).
"""


@pytest.mark.parametrize("name,want", [
    ("v3", [[8]]), ("v6", [[]]), ("v10", [[]]), ("y1", [[]]), ("y2", [[]]),
    ("k1", [[8]]), ("k2", [[7]]), ("k3", [[8]]),
])
def test_a_nested_conjunction_pattern_never_matches_one_goal(native, ans, name,
                                                             want):
    mod = native.load(f"l3_cut_meta_nested_{name}", NESTED_SRC)
    assert ans(mod, name) == want
