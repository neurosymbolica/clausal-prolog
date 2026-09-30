"""clpz global constraints against Scryer's clpz (review findings,
2026-09-30).  Every expected answer and error term below is what Scryer's
clpz gives for the same goal.

- global_cardinality/2: every element is one of the keys (it counted per key
  only, so an element free to take an off-key value satisfied every count --
  silently wrong answers); counts and elements are integers or variables
  (``[1-a]`` succeeded); duplicate keys are a domain error.
- zcompare/3: a bound Order outside ``<``/``=``/``>`` is domain_error(order,
  _) (it failed silently); a non-arithmetic operand is type_error(integer, _).
- element/3: a non-integer index is type_error(integer, _) (it failed).
- scalar_product/4: the 4th argument is any clpz expression (every compound
  raised domain_error(clpz_expression, _))."""
from __future__ import annotations

GCC = """\
:- use_module(library(clpz)).
g1(R) :- findall(X, (X in 0..2, global_cardinality([X], [1-_]), label([X])), R).
g2(R) :- findall(X, (X in 0..2, global_cardinality([X], [1-0]), label([X])), R).
g3(R) :- findall(X-Y, (X in 0..3, Y in 0..3, global_cardinality([X,Y], [1-1]), label([X,Y])), R).
g4(R) :- findall(X-C, (X in 0..3, global_cardinality([X], [1-C, 2-_]), label([X])), R).
g5(R) :- findall(L, (L = [_,_], global_cardinality(L, [1-A,2-_]), A #= 1, label(L)), R).
g6(R) :- findall(D, (global_cardinality([X], [1-_, 3-_]), fd_dom(X, D)), R).
g7(R) :- findall(x, global_cardinality([5], [1-_]), R).
g8(R) :- findall(x, global_cardinality([1], [1-0]), R).
e1(E) :- catch(global_cardinality([_], [1-a]), error(E, _), true).
e2(E) :- catch(global_cardinality([1], [1-a]), error(E, _), true).
e3(E) :- catch(global_cardinality([_], [1-1.0]), error(E, _), true).
e4(E) :- catch(global_cardinality([a], [1-_]), error(E, _), true).
e5(E) :- catch(global_cardinality([_,_], [1-1,1-1]), error(E, _), true).
"""


def test_global_cardinality_keys_restrict_the_elements(native, ans):
    mod = native.load("l3_clpz_review_gcc", GCC)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    r = lambda a, b: ("..", a, b)  # noqa: E731
    assert ans(mod, "g1") == [[1]]
    assert ans(mod, "g2") == [[]]
    assert ans(mod, "g3") == [[]]
    assert ans(mod, "g4") == [[p(1, 1), p(2, 0)]]
    assert ans(mod, "g5") == [[[1, 2], [2, 1]]]
    assert ans(mod, "g6") == [[("\\/", r(1, 1), r(3, 3))]]
    assert ans(mod, "g7") == [[]]
    assert ans(mod, "g8") == [[]]
    assert ans(mod, "e1") == [("type_error", "integer", "a")]
    assert ans(mod, "e2") == [("type_error", "integer", "a")]
    assert ans(mod, "e3") == [("type_error", "integer", 1.0)]
    assert ans(mod, "e4") == [("type_error", "integer", "a")]
    assert ans(mod, "e5") == [("domain_error", "gcc_unique_key_pairs",
                               [p(1, 1), p(1, 1)])]


ZCMP = """\
:- use_module(library(clpz)).
z1(E) :- catch(zcompare(foo, 1, 2), error(E, _), true).
z2(E) :- catch(zcompare(foo, _, 2), error(E, _), true).
z3(E) :- catch(zcompare(1, 1, 2), error(E, _), true).
z4(E) :- catch(zcompare('=<', 1, 2), error(E, _), true).
z5(E) :- catch(zcompare(foo, 1, a), error(E, _), true).
z6(E) :- catch(zcompare(_, 1, a), error(E, _), true).
z7(E) :- catch(zcompare(<, 1, a), error(E, _), true).
z8(E) :- catch(zcompare(_, a, _), error(E, _), true).
z9(E) :- catch(zcompare(<, 1, foo(2)), error(E, _), true).
z10(E) :- catch(zcompare(_, 1, 1+1), error(E, _), true).
ok(R) :- findall(O, zcompare(O, 1, 2), R).
"""


def test_zcompare_order_and_operand_errors(native, ans):
    mod = native.load("l3_clpz_review_zcmp", ZCMP)
    assert ans(mod, "z1") == [("domain_error", "order", "foo")]
    assert ans(mod, "z2") == [("domain_error", "order", "foo")]
    assert ans(mod, "z3") == [("domain_error", "order", 1)]
    assert ans(mod, "z4") == [("domain_error", "order", "=<")]
    assert ans(mod, "z5") == [("domain_error", "order", "foo")]
    assert ans(mod, "z6") == [("type_error", "integer", "a")]
    assert ans(mod, "z7") == [("type_error", "integer", "a")]
    assert ans(mod, "z8") == [("type_error", "integer", "a")]
    assert ans(mod, "z9") == [("type_error", "integer", ("foo", 2))]
    assert ans(mod, "z10") == [("type_error", "integer", ("+", 1, 1))]
    assert ans(mod, "ok") == [["<"]]


ELEM_SP = """\
:- use_module(library(clpz)).
x1(E) :- catch(element(a, [1,2], _), error(E, _), true).
x2(E) :- catch(element(1.5, [1,2], _), error(E, _), true).
x3(E) :- catch(element(1+0, [1,2], _), error(E, _), true).
x4(R) :- findall(X, element(3, [1,2], X), R).
x5(R) :- findall(I-X, (element(I, [7,8], X), label([I])), R).
s1(R) :- findall(X, scalar_product([1],[X],#=,(2-1) rem 1), R).
s2(R) :- findall(X, scalar_product([1],[X],#=,4/2), R).
s3(R) :- findall(X-Y, (scalar_product([1],[X],#=,Y*Y), Y in 1..2, label([X,Y])), R).
s4(R) :- findall(X, (X in 0..5, scalar_product([1],[X],#<,1+1), label([X])), R).
s5(E) :- catch(scalar_product([1],[_],#=,foo), error(E, _), true).
s6(R) :- findall(X, scalar_product([2],[X],#=,3+3), R).
s7(R) :- findall(X, scalar_product([1],[X],#=,5/2), R).
s8(R) :- findall(X, (X in 0..3, scalar_product([1],[X],#>=,Z*1), Z = 2, label([X])), R).
s9(R) :- findall(X, (X in 0..4, scalar_product([1,1],[X,1],#\\=,1+1), label([X])), R).
"""


def test_element_index_and_scalar_product_expression(native, ans):
    mod = native.load("l3_clpz_review_elem_sp", ELEM_SP)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    assert ans(mod, "x1") == [("type_error", "integer", "a")]
    assert ans(mod, "x2") == [("type_error", "integer", 1.5)]
    assert ans(mod, "x3") == [("type_error", "integer", ("+", 1, 0))]
    assert ans(mod, "x4") == [[]]
    assert ans(mod, "x5") == [[p(1, 7), p(2, 8)]]
    assert ans(mod, "s1") == [[0]]
    assert ans(mod, "s2") == [[2]]
    assert ans(mod, "s3") == [[p(1, 1), p(4, 2)]]
    assert ans(mod, "s4") == [[0, 1]]
    assert ans(mod, "s5") == [("domain_error", "clpz_expression", "foo")]
    assert ans(mod, "s6") == [[3]]
    assert ans(mod, "s7") == [[]]
    assert ans(mod, "s8") == [[2, 3]]
    assert ans(mod, "s9") == [[0, 2, 3, 4]]
