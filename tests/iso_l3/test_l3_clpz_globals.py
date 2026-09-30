"""clpz's reflection predicates and global constraints under Scryer's
names: fd_dom/2, fd_size/2, fd_inf/2, fd_sup/2, tuples_in/2,
global_cardinality/2, zcompare/3, all_distinct/1.  Each was an
existence_error although the solver implements it.  Every answer below is
Scryer's clpz for the same goal (2026-09-30)."""
from __future__ import annotations

SRC = """\
:- use_module(library(clpz)).
c1(R) :- findall(L, (L = [A,B,C], L ins 1..3, all_distinct(L), A #> C, label(L)), R).
c5(R) :- findall(L, (L = [A,B], tuples_in([L], [[1,2],[2,3],[3,1]]), A #> 1, label(L)), R).
c6(R) :- findall(L, (L = [A,B,C], L ins 1..2, global_cardinality(L, [1-2, 2-1]), label(L)), R).
c22(R) :- findall(S, (X in 1..9, X #\\= 5, fd_size(X, S)), R).
c23(R) :- findall(D, (X in 1..9, X #\\= 5, fd_dom(X, D)), R).
c24(R) :- findall(I-S, (X in 1..3, fd_inf(X, I), fd_sup(X, S)), R).
c25(R) :- findall(D-S, (fd_dom(X, D), fd_size(X, S)), R).
c26(R) :- findall(I-S, (X #> 3, fd_inf(X, I), fd_sup(X, S)), R).
c27(R) :- findall(D, fd_dom(3, D), R).
c31(R) :- findall(X, (X in 1..4, zcompare(O, X, 2), O = (<), label([X])), R).
c32(R) :- findall(O, zcompare(O, 1, 2), R).
"""


def test_clpz_globals(native, ans):
    mod = native.load("l3_clpz_globals", SRC)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    r = lambda a, b: ("..", a, b)  # noqa: E731
    assert ans(mod, "c1") == [[[2, 3, 1], [3, 1, 2], [3, 2, 1]]]
    assert ans(mod, "c5") == [[[2, 3], [3, 1]]]
    assert ans(mod, "c6") == [[[1, 1, 2], [1, 2, 1], [2, 1, 1]]]
    assert ans(mod, "c22") == [[8]]
    assert ans(mod, "c23") == [[("\\/", r(1, 4), r(6, 9))]]
    assert ans(mod, "c24") == [[p(1, 3)]]
    assert ans(mod, "c25") == [[p(r("inf", "sup"), "sup")]]
    assert ans(mod, "c26") == [[p(4, "sup")]]
    assert ans(mod, "c27") == [[r(3, 3)]]
    assert ans(mod, "c31") == [[1]]
    assert ans(mod, "c32") == [["<"]]


ERRORS = """\
:- use_module(library(clpz)).
e1(E) :- catch(fd_dom(a, _), error(E, _), true).
e2(E) :- catch(all_distinct(_), error(E, _), true).
e3(E) :- catch(all_distinct(foo), error(E, _), true).
e4(E) :- catch(global_cardinality([_], [_]), error(E, _), true).
e5(E) :- catch(global_cardinality([_], [a-1]), error(E, _), true).
e6(E) :- catch(global_cardinality([_], [x]), error(E, _), true).
e7(E) :- catch(tuples_in([[_]], [[a]]), error(E, _), true).
e8(E) :- catch(tuples_in([[_]], [[_]]), error(E, _), true).
e9(E) :- catch(tuples_in(_, [[1]]), error(E, _), true).
f1(R) :- findall(x, tuples_in([[_, _]], [[1]]), R).
f2(R) :- findall(D, (X #< 5, fd_dom(X, D)), R).
f3(R) :- findall(D, (X in 1..2 \\/ 4..5 \\/ 7..8, fd_dom(X, D)), R).
f4(R) :- findall(O, zcompare(O, 2, 2), R).
f5(R) :- findall(O, zcompare(O, 3, 2), R).
"""


def test_clpz_globals_errors_and_shapes(native, ans):
    """Error terms as Scryer's (must_be's instantiation_error /
    type_error(integer, _), list_si's instantiation_error,
    domain_error(gcc_pair, _)); a relation row of another width matches
    nothing; half-bounded and three-interval domains."""
    mod = native.load("l3_clpz_globals_err", ERRORS)
    r = lambda a, b: ("..", a, b)  # noqa: E731
    assert ans(mod, "e1") == [("type_error", "integer", "a")]
    assert ans(mod, "e2") == ["instantiation_error"]
    assert ans(mod, "e3") == [("type_error", "list", "foo")]
    assert ans(mod, "e4") == ["instantiation_error"]
    assert ans(mod, "e5") == [("type_error", "integer", "a")]
    assert ans(mod, "e6") == [("domain_error", "gcc_pair", "x")]
    assert ans(mod, "e7") == [("type_error", "integer", "a")]
    assert ans(mod, "e8") == ["instantiation_error"]
    assert ans(mod, "e9") == ["instantiation_error"]
    assert ans(mod, "f1") == [[]]
    assert ans(mod, "f2") == [[r("inf", 4)]]
    assert ans(mod, "f3") == [[("\\/", ("\\/", r(1, 2), r(4, 5)), r(7, 8))]]
    assert ans(mod, "f4") == [["="]]
    assert ans(mod, "f5") == [[">"]]


OPTIMISE = """\
:- use_module(library(clpz)).
o1(R) :- findall(X-Y, (X in 0..2, Y in 0..2, X #< Y, labeling([max(X)], [X,Y])), R).
o2(R) :- findall(X-Y, (X in 0..2, Y in 0..2, X #< Y, labeling([min(X+Y)], [X,Y])), R).
o3(R) :- findall(X-Y, (X in 0..2, Y in 0..2, labeling([max(X), min(Y)], [X,Y])), R).
o4(R) :- findall(X-Y, (X in 0..2, Y in 0..2, X #\\= Y, labeling([down, max(X-Y)], [X,Y])), R).
o5(R) :- findall(X, (X in 0..3, labeling([down, min(X/2)], [X])), R).
o6(R) :- Vs = [A,B,C,D,E,F,G,H], Vs ins 0..9, S #= A+B+C+D+E+F+G+H,
         once(labeling([max(S)], Vs)), R = S.
o7(E) :- catch((X in 0..3, labeling([max(foo)], [X])), error(E, _), true).
o8(E) :- catch(findall(X, (X in 0..3, labeling([min(_)], [X])), _), error(E, _), true).
"""


def test_labeling_min_max_options(native, ans):
    """labeling/2's min(Expr)/max(Expr) options were refused
    (domain_error(labeling_option, max(_))); the answers come in the
    objectives' order, ties in labeling order -- Scryer's, row for row."""
    mod = native.load("l3_clpz_optimise", OPTIMISE)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    assert ans(mod, "o1") == [[p(1, 2), p(0, 1), p(0, 2)]]
    assert ans(mod, "o2") == [[p(0, 1), p(0, 2), p(1, 2)]]
    assert ans(mod, "o3") == [[p(2, 0), p(2, 1), p(2, 2), p(1, 0), p(1, 1),
                               p(1, 2), p(0, 0), p(0, 1), p(0, 2)]]
    assert ans(mod, "o4") == [[p(2, 0), p(2, 1), p(1, 0), p(1, 2), p(0, 1),
                               p(0, 2)]]
    # clpz's `/` (exact): an odd X has no objective value
    assert ans(mod, "o5") == [[0, 2]]
    # branch and bound: the best of 10^8 labellings without enumerating them
    assert ans(mod, "o6") == [72]
    assert ans(mod, "o7") == [("domain_error", "clpz_expression", "foo")]
    assert ans(mod, "o8") == ["instantiation_error"]


LEX = """\
:- use_module(library(clpz)).
l1(R) :- findall(X, (lex_chain([[1,X],[1,2]]), X in 0..3, label([X])), R).
l2(R) :- findall(X-Y, (lex_chain([[X,Y],[1,1]]), [X,Y] ins 0..2, label([X,Y])), R).
l3(R) :- findall(A-B-C, (lex_chain([[A],[B],[C]]), [A,B,C] ins 0..1, label([A,B,C])), R).
l4(R) :- findall(x, lex_chain([[1,2],[1]]), R).
l5(E) :- catch(lex_chain([[1],[1,2],[foo]]), error(E, _), true).
l6(R) :- findall(x, lex_chain([[],[]]), R).
l7(R) :- findall(D, (lex_chain([[X,_],[1,1]]), X in 0..2, fd_dom(X, D)), R).
"""


def test_lex_chain(native, ans):
    """lex_chain/1 did not exist; Scryer's answers (lists of different
    lengths fail)."""
    mod = native.load("l3_clpz_lex", LEX)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    assert ans(mod, "l1") == [[0, 1, 2]]
    assert ans(mod, "l2") == [[p(0, 0), p(0, 1), p(0, 2), p(1, 0), p(1, 1)]]
    assert ans(mod, "l3") == [[p(p(0, 0), 0), p(p(0, 0), 1), p(p(0, 1), 1),
                               p(p(1, 1), 1)]]
    assert ans(mod, "l4") == [[]]
    # every element is checked before any length comparison fails
    assert ans(mod, "l5") == [("type_error", "integer", "foo")]
    assert ans(mod, "l6") == [["x"]]
    # the first position is pruned before labelling, as Scryer's
    assert ans(mod, "l7") == [[("..", 0, 1)]]


CHAIN = """\
:- use_module(library(clpz)).
h1(R) :- findall(L, (L = [A,B,C], L ins 1..3, chain(#<, L), label(L)), R).
h2(R) :- findall(L, (L = [A,B], L ins 1..2, chain(#>=, L), label(L)), R).
h3(E) :- catch(chain(foo, [_]), error(E, _), true).
h4(E) :- catch(chain(_, [_]), error(E, _), true).
h5(R) :- findall(x, chain(#<, []), R).
h6(E) :- catch(chain(#<, foo), error(E, _), true).
"""


def test_chain(native, ans):
    """chain(Relation, Zs), Scryer's argument order and errors; it did not
    exist."""
    mod = native.load("l3_clpz_chain", CHAIN)
    assert ans(mod, "h1") == [[[1, 2, 3]]]
    assert ans(mod, "h2") == [[[1, 1], [2, 1], [2, 2]]]
    assert ans(mod, "h3") == [("domain_error", "chain_relation", "foo")]
    assert ans(mod, "h4") == ["instantiation_error"]
    assert ans(mod, "h5") == [["x"]]
    assert ans(mod, "h6") == [("type_error", "list", "foo")]


FDVAR = """\
:- use_module(library(clpz)).
v1(R) :- findall(x, (X in 1..3, fd_var(X)), R).
v2(R) :- findall(x, fd_var(3), R).
v3(R) :- findall(x, fd_var(_), R).
v4(R) :- findall(X, (X in 1..3, indomain(X)), R).
v5(E) :- catch(indomain(_), error(E, _), true).
v6(R) :- findall(x, indomain(3), R).
"""


def test_fd_var_and_indomain(native, ans):
    """fd_var/1 and indomain/1 did not exist; Scryer's answers."""
    mod = native.load("l3_clpz_fdvar", FDVAR)
    assert ans(mod, "v1") == [["x"]]
    assert ans(mod, "v2") == [[]]
    assert ans(mod, "v3") == [[]]
    assert ans(mod, "v4") == [[1, 2, 3]]
    assert ans(mod, "v5") == ["instantiation_error"]
    assert ans(mod, "v6") == [["x"]]


NVALUE = """\
:- use_module(library(clpz)).
n1(R) :- findall(L, (L = [A,B,C], L ins 1..2, nvalue(1, L), label(L)), R).
n2(R) :- findall(N, (nvalue(N, [1,2,1])), R).
n3(R) :- findall(L-N, (L = [A,B], L ins 1..2, nvalue(N, L), label(L)), R).
n4(R) :- findall(N, nvalue(N, []), R).
n5(R) :- findall(L, (L = [A,B,C], L ins 1..3, nvalue(3, L), A #< B, B #< C, label(L)), R).
"""


def test_nvalue(native, ans):
    """nvalue/2 did not exist; Scryer's answers."""
    mod = native.load("l3_clpz_nvalue", NVALUE)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    assert ans(mod, "n1") == [[[1, 1, 1], [2, 2, 2]]]
    assert ans(mod, "n2") == [[2]]
    assert ans(mod, "n3") == [[p([1, 1], 1), p([1, 2], 2), p([2, 1], 2),
                               p([2, 2], 1)]]
    assert ans(mod, "n4") == [[0]]
    assert ans(mod, "n5") == [[[1, 2, 3]]]


NVALUE_ERR = """\
:- use_module(library(clpz)).
m1(E) :- catch(nvalue(_, foo), error(E, _), true).
m2(E) :- catch(nvalue(_, _), error(E, _), true).
m3(E) :- catch(nvalue(_, [a]), error(E, _), true).
m4(E) :- catch(nvalue(foo, [1]), error(E, _), true).
m5(R) :- findall(x, nvalue(3, [_, _]), R).
m6(E) :- catch((X #> 3, indomain(X)), error(E, _), true).
m7(E) :- catch(indomain(foo), error(E, _), true).
"""


def test_nvalue_and_indomain_errors(native, ans):
    """Scryer's error terms; an unreachable N fails."""
    mod = native.load("l3_clpz_nvalue_err", NVALUE_ERR)
    assert ans(mod, "m1") == [("type_error", "list", "foo")]
    assert ans(mod, "m2") == ["instantiation_error"]
    assert ans(mod, "m3") == [("type_error", "integer", "a")]
    assert ans(mod, "m4") == [("type_error", "integer", "foo")]
    assert ans(mod, "m5") == [[]]
    assert ans(mod, "m6") == ["instantiation_error"]
    assert ans(mod, "m7") == [("type_error", "integer", "foo")]


CUMULATIVE = """\
:- use_module(library(clpz)).
u1(R) :- findall([S1,S2,S3], (Ts = [task(S1,3,_,1,_), task(S2,2,_,1,_), task(S3,2,_,1,_)], [S1,S2,S3] ins 0..4, cumulative(Ts), label([S1,S2,S3])), R).
u2(R) :- findall([S1,S2], (Ts = [task(S1,2,_,1,_), task(S2,2,_,1,_)], [S1,S2] ins 0..1, cumulative(Ts, [limit(2)]), label([S1,S2])), R).
u3(R) :- findall(E, (cumulative([task(0,3,E,1,a)])), R).
u4(E) :- catch(cumulative([], [foo]), error(E, _), true).
u5(E) :- catch(cumulative([task(0,_,_,1,a)]), error(E, _), true).
"""


def test_cumulative(native, ans):
    """cumulative/1,2 did not exist; Scryer's answers.  A variable duration
    is refused loudly here (Scryer accepts it; the constraint reasons over
    fixed durations)."""
    mod = native.load("l3_clpz_cumulative", CUMULATIVE)
    assert ans(mod, "u1") == [[[4, 0, 2], [4, 2, 0]]]
    assert ans(mod, "u2") == [[[0, 0], [0, 1], [1, 0], [1, 1]]]
    assert ans(mod, "u3") == [[3]]
    assert ans(mod, "u4") == [("domain_error", "cumulative_options_empty_or_limit",
                               ["foo"])]
    assert ans(mod, "u5") == ["instantiation_error"]
