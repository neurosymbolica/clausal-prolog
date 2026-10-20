"""library(reif)'s if_/3 as a predicate, not only a written goal (todo
clausal-surface-gaps-found-moving-the-docs-2026-10-17, "if_/3").

A written ``if_(C, T, E)`` body goal is compiled in place (``iso_l3._if``);
these are the routes that never see the compiler: ``call(if_(...))``,
``G = if_(...), G``, ``call(if_, C, T, E)`` and a lambda whose body is an
``if_``.  library(reif) now also exports a runtime if_/3
(``clausal/stdlib/reif.seam``) with the same meaning, Scryer's: the
condition's truth value, (',')/3 and (;)/3 unfolded, ``instantiation_error``
for an unbound one, ``type_error(boolean, T)`` for a non-boolean one.

Also clpz's reified comparisons (#=)/3 and (#<)/3, the two Scryer's clpz
exports, so ``if_(X #= 3, ...)`` works.  What Scryer does NOT define stays an
existence_error, ISO-shaped: (>=)/3 and (#>)/3 as conditions, and the
grammar-body if_//3 (if_/5).  Every expected answer below is Scryer's
(scryer-prolog with library(reif), library(clpz), library(lambda)).

Each test runs on both surfaces of the native front end: a ``.clausal``
module and the same clauses as a ``.pl`` file.
"""
from __future__ import annotations

import textwrap

import pytest

from clausal.logic.variables import Var


SURFACES = (".clausal", ".pl")

_HEADER = """\
:- use_module(library(reif)).
:- use_module(library(clpz)).
:- use_module(library(lambda)).
:- use_module(library(lists)).
"""


def _load(native, suffix, name, body, header=_HEADER):
    text = header + textwrap.dedent(body)
    if suffix == ".clausal":
        text = f":- module({name}, []).\n" + text + f":- end_module({name}).\n"
    return native.load(name, text, suffix=suffix)


def _name(base, suffix):
    return f"{base}_{suffix.lstrip('.')}"


@pytest.fixture(params=SURFACES)
def suffix(request):
    return request.param


# ── the meta-call routes reach if_/3 ──


def test_call_of_an_if_term(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_call", suffix), """\
        c(X, R) :- call(if_(X = a, R = yes, R = no)).
        """)
    got = ans(mod, "c", 2)
    assert got[0] == ("a", "yes")
    assert isinstance(got[1][0], Var) and got[1][1] == "no"
    assert len(got) == 2
    assert ans(mod, "c", 2, "b") == ["no"]


def test_the_else_answer_carries_dif(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_dif", suffix), """\
        c(X, R) :- call(if_(X = a, R = yes, R = no)).
        t(ok) :- c(X, no), \\+ X = a.
        """)
    assert ans(mod, "t") == ["ok"]


def test_a_goal_bound_to_a_variable(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_var", suffix), """\
        c(X, R) :- G = if_(X = a, R = yes, R = no), G.
        """)
    assert ans(mod, "c", 2, "b") == ["no"]
    assert ans(mod, "c", 2, "a") == ["yes"]


def test_call_n_folds_onto_if(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_calln", suffix), """\
        c(X, R) :- call(if_, X = a, R = yes, R = no).
        d(X, R) :- call(if_(X = a), R = yes, R = no).
        """)
    assert ans(mod, "c", 2, "a") == ["yes"]
    assert ans(mod, "d", 2, "b") == ["no"]


def test_a_lambda_calling_if(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_lambda", suffix), """\
        c(Ks) :- maplist(\\X^K^if_(X = a, K = yes, K = no), [a, b], Ks).
        """)
    assert ans(mod, "c") == [["yes", "no"]]


def test_conjunction_and_disjunction_conditions(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_conj", suffix), """\
        c(X, Y, R) :- G = if_((X = a, Y = b), R = yes, R = no), call(G).
        d(X, R) :- call(if_((X = a ; X = b), R = yes, R = no)).
        e(R) :- call(if_((a = b ; 1 = 1), R = y, R = n)).
        """)
    got = ans(mod, "c", 3)
    assert [g[2] for g in got] == ["yes", "no", "no"]
    assert got[0][:2] == ("a", "b") and got[1][0] == "a"
    assert [r for _x, r in ans(mod, "d", 2)] == ["yes", "yes", "no"]
    assert ans(mod, "e") == ["y"]


def test_a_closure_condition_resolves_in_the_callers_module(native, ans,
                                                             suffix):
    mod = _load(native, suffix, _name("ifr_closure", suffix), """\
        small_t(X, T) :- ( X < 3, T = true ; X >= 3, T = false ).
        c(X, R) :- call(if_(small_t(X), R = small, R = big)).
        m(X, R) :- call(if_(memberd_t(X, [a, b]), R = yes, R = no)).
        """)
    assert ans(mod, "c", 2, 1) == ["small"]
    assert ans(mod, "c", 2, 7) == ["big"]
    assert ans(mod, "m", 2, "c") == ["no"]
    assert ans(mod, "m", 2, "b") == ["yes"]


def test_the_branches_run_in_the_callers_module(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_arms", suffix), """\
        here(yes).
        c(R) :- call(if_(a = a, here(R), R = no)).
        """)
    assert ans(mod, "c") == ["yes"]


def test_condition_errors_are_scryers(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_err", suffix), """\
        w(maybe).
        u(E) :- catch(call(if_(_, true, true)), error(E, _), true).
        b(E) :- catch(call(if_(w, true, true)), error(E, _), true).
        """)
    assert ans(mod, "u") == ["instantiation_error"]
    assert ans(mod, "b") == [("type_error", "boolean", "maybe")]


# ── clpz's reified comparisons ──


def test_clpz_reified_equality_as_the_condition(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_clpz_eq", suffix), """\
        c(X, R) :- if_(X #= 3, R = yes, R = no).
        d(X, R) :- call(if_(X #= 3, R = yes, R = no)).
        t(T) :- #=(1 + 2, 3, T).
        """)
    for p in ("c", "d"):
        assert ans(mod, p, 2, 3) == ["yes"]
        assert ans(mod, p, 2, 2) == ["no"]
        # Scryer's order: clpz_t's zo_t(0, false) before zo_t(1, true).
        assert [r for _x, r in ans(mod, p, 2)] == ["no", "yes"]
    assert ans(mod, "t") == [True]


def test_clpz_reified_less_than_as_the_condition(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_clpz_lt", suffix), """\
        c(X, R) :- if_(X #< 3, R = lt, R = ge).
        k(X, R) :- if_(X #< 3, R = lt, R = ge), X = 1.
        """)
    assert ans(mod, "c", 2, 2) == ["lt"]
    assert ans(mod, "c", 2, 5) == ["ge"]
    assert [r for _x, r in ans(mod, "c", 2)] == ["ge", "lt"]
    # The reification is a constraint: binding X later picks the branch.
    assert ans(mod, "k", 2) == [(1, "lt")]


def test_clpz_reified_comparison_type_errors(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_clpz_bad", suffix), """\
        c(E) :- catch(if_(1 #= a, true, true), error(E, _), true).
        """)
    assert ans(mod, "c") == [("domain_error", "clpz_expression", "a")]


# ── what Scryer does not define stays an ISO existence_error ──


@pytest.mark.parametrize("cond, pi", [
    ("X >= 3", (">=", 3)),
    ("X #> 3", ("#>", 3)),
])
def test_an_unreified_comparison_is_an_existence_error(native, ans, suffix,
                                                       cond, pi):
    base = "ifr_noreif_" + ("ge" if pi[0] == ">=" else "gt")
    mod = _load(native, suffix, _name(base, suffix), f"""\
        c(E) :- X = 4, catch(if_({cond}, true, true), error(E, _), true).
        d(E) :- X = 4, catch(call(if_({cond}, true, true)), error(E, _),
                             true).
        """)
    want = ("existence_error", "procedure", ("/",) + pi)
    assert ans(mod, "c") == [want]
    assert ans(mod, "d") == [want]


def test_a_grammar_body_if_is_scryers_undefined_if_5(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_dcg", suffix), """\
        g(R) --> [X], if_(X = a, {R = yes}, {R = no}).
        c(E) :- catch(phrase(g(_), [a]), error(E, _), true).
        """)
    assert ans(mod, "c") == [("existence_error", "procedure",
                              ("/", "if_", 5))]


# ── the import still decides whether if_/3 exists ──


def test_without_the_import_a_called_if_is_undefined(native, ans, suffix):
    mod = _load(native, suffix, _name("ifr_noimport", suffix), """\
        c(E) :- catch(call(if_(1 = 1, true, true)), error(E, _), true).
        """, header="")
    assert ans(mod, "c") == [("existence_error", "procedure",
                              ("/", "if_", 3))]


def test_an_import_list_decides_too(native, ans, suffix):
    without = _load(native, suffix, _name("ifr_list_no", suffix), """\
        c(E) :- catch(call(if_(1 = 1, true, true)), error(E, _), true).
        """, header=":- use_module(library(reif), [memberd_t/3]).\n")
    with_if = _load(native, suffix, _name("ifr_list_yes", suffix), """\
        c(R) :- call(if_(1 = 1, R = y, R = n)).
        w(R) :- if_(1 = 2, R = y, R = n).
        """, header=":- use_module(library(reif), [if_/3]).\n")
    assert ans(without, "c") == [("existence_error", "procedure",
                                  ("/", "if_", 3))]
    assert ans(with_if, "c") == ["y"]
    assert ans(with_if, "w") == ["n"]
