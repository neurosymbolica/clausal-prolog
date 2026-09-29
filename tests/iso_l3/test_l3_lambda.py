"""library(lambda) -- (\\)/1..8, (^)/3..10, (+\\)/2..9 -- as engine builtins.

Every expected answer below is Scryer's (``scryer-prolog`` with
``use_module(library(lambda))``, measured 2026-09-29); the error culprits are
the bare goal where Scryer module-qualifies it (``user:_A^true``)."""
from __future__ import annotations

import textwrap

import pytest

from clausal.logic.variables import Var, deref, walk

LAMBDA_IMPORT = (
    ":- use_module(library(lambda), ["
    + ", ".join([f"(\\)/{n}" for n in range(1, 9)]
                + [f"(^)/{n}" for n in range(3, 11)]
                # An import list installs only the ops it names (Scryer;
                # lambda.pl exports +\ but declares no top-level op/3).
                + ["op(201, xfx, +\\)"])
    + "]).\n")

SRC = LAMBDA_IMPORT + textwrap.dedent(r"""
    :- use_module(library(lists)).
    :- use_module(library(dif)).
    f(x, y).
    gt3(ok) :- maplist(\X^(X>3), [4,5,9]).
    gt3_no(ok) :- maplist(\X^(X>3), [4,1,9]).
    double(L) :- maplist(\X^Y^(Y is 2*X), [1,2], L).
    sum(S) :- foldl(\X^A0^A^(A is A0+X), [1,2,3], 0, S).
    shared(Xs) :- Xs=[A,B], maplist(X+\Y^dif(X,Y), Xs), X=1, A=2, B=3.
    shared_no(Xs) :- Xs=[A,_], maplist(X+\Y^dif(X,Y), Xs), X=1, A=1.
    shared_cont(Xs) :- Xs=[A,_], maplist(X+\dif(X), Xs), X=1, A=1.
    eq1(A1-A2) :- call(f,A1,A2).
    eq2(A1-A2) :- call(\X^f(X),A1,A2).
    eq3(A1-A2) :- call(\X^Y^f(X,Y),A1,A2).
    eq4(A1-A2) :- call(\X^(X+\Y^f(X,Y)),A1,A2).
    local(Y) :- G = \X^(Y = X), call(G, 1), call(G, 2).
    global1(Y) :- G = Y+\X^(Y = X), call(G, 1).
    global2(Y) :- G = Y+\X^(Y = X), call(G, 1), call(G, 2).
    gen(M) :- call(\X^member(X, [a,b]), M).
    gen2(K-V) :- call(\X^Y^member(X-Y, [a-1,b-2]), K, V).
    free(ok) :- N = 5, call(N+\X^(X < N), 3).
    fresh(T) :- call(\X^(X = f(_)), T).
    nullary(ok) :- call(\true).
    nullary_free(X) :- call(X+\ (X = 1)).
    hat(V) :- '^'(V, true, 3).
    hat_cont(R) :- call(X^Y^(Y is X+1), 1, R).
    too_few(E) :- catch(call(\X^Y^true, 1), error(E, _), true).
    too_few0(E) :- catch(call(\X^true), error(E, _), true).
    too_many(E) :- catch(call(\X^true, 1, 2), error(E, _), true).
    too_many_body(E) :- catch(maplist(\X^(X > 0), [1,2], _), error(E, _), true).
    eight(E) :- catch(call(\X^Y^Z^W^V^U^T^S^true, 1,2,3,4,5,6,7), error(E, _), true).
    """)


@pytest.fixture
def lam(native):
    return native.load("lam_scryer", SRC)


@pytest.mark.parametrize("name, want", [
    ("gt3", ["ok"]),
    ("gt3_no", []),
    ("double", [[2, 4]]),
    ("sum", [6]),
    ("shared", [[2, 3]]),
    ("shared_no", []),
    ("shared_cont", []),
    ("eq1", [("-", "x", "y")]),
    ("eq2", [("-", "x", "y")]),
    ("eq3", [("-", "x", "y")]),
    ("eq4", [("-", "x", "y")]),
    ("global1", [1]),
    ("global2", []),
    ("gen", ["a", "b"]),
    ("gen2", [("-", "a", 1), ("-", "b", 2)]),
    ("free", ["ok"]),
    ("nullary", ["ok"]),
    ("nullary_free", [1]),
    ("hat", [3]),
    ("hat_cont", [2]),
    ("too_many", [("existence_error", "procedure", ("/", "true", 1))]),
    ("too_many_body", [("existence_error", "procedure", ("/", ">", 3))]),
])
def test_answers_match_scryer(lam, ans, name, want):
    assert ans(lam, name) == want


def test_a_lambda_called_twice_does_not_leak_bindings(lam, ans):
    # Scryer: G = \X^(Y = X), call(G, 1), call(G, 2) succeeds, Y unbound --
    # each call works on a fresh copy, Y included (it is local).
    [y] = ans(lam, "local")
    from clausal.logic.variables import is_var
    assert is_var(y)


def test_a_fresh_copy_leaves_local_variables_unbound(lam, ans):
    [t] = ans(lam, "fresh")
    from clausal.logic.variables import is_var
    assert t[0] == "f" and is_var(t[1])


@pytest.mark.parametrize("name", ["too_few", "too_few0", "eight"])
def test_a_missing_parameter_is_a_lambda_parameter_error(lam, ans, name):
    [e] = ans(lam, name)
    assert e[0] == "existence_error" and e[1] == "lambda_parameter"
    assert e[2][0] == "^" and e[2][2] == "true"


def test_the_plus_backslash_operator_needs_the_import(native):
    with pytest.raises(SyntaxError):
        native.load("lam_noop", "g(Y) :- call(Y+\\X^(Y = X), 1).\n")


def test_the_library_imports_without_a_list(native, ans):
    mod = native.load("lam_nolist", ":- use_module(library(lambda)).\n"
                                    "g(Y) :- call(Y+\\X^(Y = X), 1).\n")
    assert ans(mod, "g") == [1]


def test_lambdas_from_the_python_api_against_a_seam_module(native):
    """The builtins are global: a cell lambda runs through solve() in a
    ``.seam`` module too, and its goal resolves in that module."""
    from clausal import solve
    mod = native.load("lam_seam", "big(X) <- (X > 3)\n",
                      suffix=".seam", frontend=None)
    x = Var()
    lam_big = ("\\", ("^", x, ("big", x)))
    assert len(list(solve(("maplist", lam_big, [4, 5]), module=mod))) == 1
    assert list(solve(("maplist", lam_big, [4, 1]), module=mod)) == []
    y, z, out = Var(), Var(), Var()
    dbl = ("\\", ("^", y, ("^", z, ("is", z, ("*", 2, y)))))
    got = [walk(deref(out))
           for _ in solve(("maplist", dbl, [1, 2], out), module=mod)]
    assert got == [[2, 4]]
