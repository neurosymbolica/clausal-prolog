"""``[]`` is an atom (ISO 13211-1 6.3.5; D70: ``'[]'`` and ``[]`` are one
atom), so it is callable: a Prolog text may define ``[]/0`` and ``[]/N``,
and ``[]`` may be called as a goal.

The term layer carries the empty list as the Python empty list, not as a
``str``; the predicate it names is keyed by the spelling ``"[]"``, and every
place a predicate NAME comes back out as a term (an error's predicate
indicator, ``current_predicate/1``) gives the empty list again, so ``[]``
written in the source compares equal to it.

The expected column was measured on Scryer
(``/workspace/scryer-prolog-clpq/target/release/scryer-prolog``,
v0.10.0-137-g9acba77a), 2026-10-20, on the same rows, with
``use_module(library(lists))``; every row there is ``ok``, except
``no_current``: Scryer lists a procedure that is only CALLED somewhere
(``x :- foo.`` makes ``current_predicate(foo/0)`` true there), which ISO
8.8.2 does not, so that row follows ISO.  ``clause/2`` on a STATIC ``[]/0``
is ``permission_error(access, private_procedure, []/0)`` in both.
"""
from __future__ import annotations

import pytest

# One body, both surfaces: nothing here uses cut, ``->`` or ``*->``.
DEFINED = """\
:- dynamic([]/0).
:- dynamic('[]'/1).
[].
'[]'(a).
'[]'(b).
t(fact_goal) :- [].
t(quoted_goal) :- '[]'.
t(call_literal) :- call([]).
t(call_bound) :- X = [], call(X).
t(compound_goal) :- findall(Y, [](Y), L), L == [a, b].
t(quoted_compound) :- findall(Y, '[]'(Y), L), L == [a, b].
t(call_extra) :- call([], a).
t(call_quoted) :- call('[]').
t(naf) :- \\+ [](c).
t(current_0) :- current_predicate([]/0).
t(current_1) :- current_predicate('[]'/1).
t(current_enum) :- findall(F, (current_predicate(F/0), F == []), L), L == [[]].
t(missing_arity) :- catch(call([], c, d), error(E, _), true),
    E == existence_error(procedure, []/2).
t(clause_0) :- clause([], B), B == true.
t(clause_1) :- findall(X, clause('[]'(X), true), L), L == [a, b].
t(assert_1) :- assertz('[]'(z)), [](z).
t(retract_0) :- retract([]), \\+ [].
"""

ROWS = ["fact_goal", "quoted_goal", "call_literal", "call_bound",
        "compound_goal", "quoted_compound", "call_extra", "call_quoted", "naf",
        "current_0", "current_1", "current_enum", "missing_arity", "clause_0",
        "clause_1", "assert_1", "retract_0"]

UNDEFINED = """\
u(goal, E) :- catch([], error(E, _), true).
u(quoted, E) :- catch('[]', error(E, _), true).
u(call, E) :- catch(call([]), error(E, _), true).
u(bound, E) :- X = [], catch(call(X), error(E, _), true).
u(compound, E) :- catch([](1), error(E, _), true).
u(pi_is_nil, ok) :- catch([], error(existence_error(procedure, N/0), _), true),
    N == [].
u(no_current, ok) :- \\+ current_predicate([]/0).
"""

SURFACES = [".pl", ".clausal"]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_text_may_define_and_call_the_empty_list(native, ans, suffix):
    mod = native.load("nil_defined" + suffix[1:], DEFINED, suffix=suffix)
    got = {row: len(ans(mod, "t", 1, row)) for row in ROWS}
    assert got == {row: 1 for row in ROWS}


@pytest.mark.parametrize("suffix", SURFACES)
def test_the_empty_list_with_no_clauses_is_an_existence_error(native, ans,
                                                              suffix):
    mod = native.load("nil_undefined" + suffix[1:], UNDEFINED, suffix=suffix)
    pi0 = ("existence_error", "procedure", ("/", [], 0))
    assert ans(mod, "u", 2, "goal") == [pi0]
    assert ans(mod, "u", 2, "quoted") == [pi0]
    assert ans(mod, "u", 2, "call") == [pi0]
    assert ans(mod, "u", 2, "bound") == [pi0]
    assert ans(mod, "u", 2, "compound") == [
        ("existence_error", "procedure", ("/", [], 1))]
    assert ans(mod, "u", 2, "pi_is_nil") == ["ok"]
    assert ans(mod, "u", 2, "no_current") == ["ok"]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_fact_and_a_rule_for_the_empty_list_load(native, ans, suffix):
    """The todo's two refused heads, ``[].`` and ``'[]'.``, and a rule."""
    mod = native.load("nil_heads" + suffix[1:],
                      "'[]'.\n[] :- true.\n'[]'(X) :- X = 1.\n"
                      "v(A) :- findall(x, [], A).\nw(Y) :- [](Y).\n",
                      suffix=suffix)
    assert ans(mod, "v") == [["x", "x"]]
    assert ans(mod, "w") == [1]


def test_the_empty_list_is_not_a_control_construct(native):
    """``[]`` stays ordinary data everywhere it is not a goal: a DCG body
    ``[]`` is still the empty terminal list."""
    mod = native.load("nil_dcg", "s --> [].\nt(R) :- phrase(s, R).\n")
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    r = Var()
    assert [walk(deref(r)) for _ in call("t", r, module=mod)] == [[]]


DATABASE = """\
:- dynamic([]/0).
d(assertz) :- assertz([]), [].
d(asserta) :- asserta([]), findall(x, [], L), L == [x, x].
d(retract) :- retract(([] :- true)), findall(x, [], L), L == [x].
d(retractall) :- retractall([]), \\+ [].
d(abolish) :- assertz([]), abolish([]/0),
    catch([], error(E, _), true), E == existence_error(procedure, []/0).
"""


@pytest.mark.parametrize("suffix", SURFACES)
def test_the_database_builtins_take_the_empty_list_head(native, ans, suffix):
    mod = native.load("nil_db" + suffix[1:], DATABASE, suffix=suffix)
    rows = ["assertz", "asserta", "retract", "retractall", "abolish"]
    assert {r: len(ans(mod, "d", 1, r)) for r in rows} == {r: 1 for r in rows}


@pytest.mark.parametrize("suffix", SURFACES)
def test_clause_of_a_static_empty_list_is_a_permission_error(native, ans,
                                                             suffix):
    mod = native.load("nil_static" + suffix[1:],
                      "[].\nc(E) :- catch(clause([], _), error(E, _), true).\n",
                      suffix=suffix)
    assert ans(mod, "c") == [("permission_error", "access",
                              "private_procedure", ("/", [], 0))]


def test_solve_from_python_runs_the_empty_list_goal(native):
    """``solve([], m)`` and ``solve(chars(""), m)`` -- one term, the goal
    ``[]/0`` -- run the module's ``[]/0``, and with none defined raise the
    ISO existence error naming ``[]/0``."""
    from clausal.logic.cells import chars
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import solve
    mod = native.load("nil_solve", "[].\n")
    assert len(list(solve([], mod))) == 1
    assert len(list(solve(chars(""), mod))) == 1
    bare = native.load("nil_solve_bare", "x.\n")
    with pytest.raises(LogicException) as exc:
        list(solve([], bare))
    assert exc.value.term[1] == ("existence_error", "procedure", ("/", [], 0))


# ── A grammar rule whose head is the nonterminal ``[]`` ─────────────────────
#
# ``[] --> [a].`` defines ``[]/2`` (ISO 7.14: the head is a callable term, and
# ``[]`` is an atom).  It is the HEAD only: as phrase/2's first argument and in
# a grammar body, ``[]`` is still the empty terminal list, which consumes
# nothing -- so ``phrase([], [a])`` fails even with that rule loaded.  Every
# row was measured on Scryer (v0.10.0-137-g9acba77a), 2026-10-20, with this
# program and ``use_module(library(dcgs))``: all ``ok``.

GRAMMAR = """\
:- use_module(library(dcgs)).
[] --> [a].
'[]' --> [b].
[], [p] --> [c].
[](X) --> [X, X].
x --> [], [b].
y --> [].
z --> [](q).
t(phrase_nil_empty) :- phrase([], []).
t(phrase_nil_not_a) :- \\+ phrase([], [a]).
t(phrase3_nil) :- findall(R, phrase([], [a], R), Rs), Rs == [[a]].
t(phrase_nil_open) :- findall(L, phrase([], L), Ls), Ls == [[]].
t(direct) :- findall(S, '[]'([a], S), Ss), Ss == [[]].
t(direct_all) :- findall(S0-S, '[]'(S0, S), Ps), Ps = [_, _, _].
t(direct_quoted_rule) :- '[]'([b], []).
t(pushback) :- findall(S, '[]'([c], S), Ss), Ss == [[p]].
t(call3) :- findall(S, call([], [a,c], S), Ss), Ss == [[c]].
t(body_nil) :- phrase(x, [b]), \\+ phrase(x, [a, b]).
t(body_only_nil) :- phrase(y, []), \\+ phrase(y, [a]).
t(body_compound) :- phrase(z, [q, q]).
t(phrase_compound) :- phrase([](r), [r, r]).
"""

GRAMMAR_ROWS = ["phrase_nil_empty", "phrase_nil_not_a", "phrase3_nil",
                "phrase_nil_open", "direct", "direct_all",
                "direct_quoted_rule", "pushback", "call3", "body_nil",
                "body_only_nil", "body_compound", "phrase_compound"]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_grammar_rule_may_have_the_head_empty_list(native, ans, suffix):
    mod = native.load("nil_grammar" + suffix[1:], GRAMMAR, suffix=suffix)
    got = {row: len(ans(mod, "t", 1, row)) for row in GRAMMAR_ROWS}
    assert got == {row: 1 for row in GRAMMAR_ROWS}

