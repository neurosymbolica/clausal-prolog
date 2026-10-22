"""Follow-ups to "the .pl translator builds operator terms in data position"
(2026-10-22): the remaining pre-existing gaps, compared between the
translator, the native front end and Scryer.

1. A comparison (``<``, ``=:=``, ...) or a clpz relation (``#=``, ``#<``,
   ...) in DATA position was emitted unparenthesised, so ``G = (1+1 < 3)``
   became the seam's chained comparison ``G is 1 + 1 < 3`` and ``call(G)``
   raised type_error(callable, 1+1); ``#\\=``, ``#<``, ``#>``, ``#=<``,
   ``#>=`` and the reification connectives were refused outright ("not a
   valid Python identifier").  Now the ISO cell ``'<'('+'(1, 1), 3)``.
2. ``assertz((H :- B))`` with a non-call body emitted ``H <- Y is ...``
   unparenthesised, a seam load error.  Now the cell ``':-'(H, B)``, which
   assertz/1 refuses at run time as on the native front end (a rule body
   cannot be asserted, A09-F005; ``Head :- true`` is the fact).
3. ``X = (a :- b, c)`` raised domain_error(clpz_expression, b(c)): the
   seam's ``a <- (b, c)`` after ``X is`` read as ``X is a < -(b, c)``, and a
   parenthesised ``(b, c)`` in argument position as the call ``b(c)``.  A
   clause, grammar rule, conjunction, disjunction or negation in data
   position is now its ISO cell, and so is a unification ``X = (A = b)``
   (it was the chained comparison ``X is A is b``) and a univ ``A =.. L``
   (it was the term ``unpack(A, L)``).
4. ``X in 1..(N-1)`` / ``Xs ins 0..(1+1)`` ended in a raw Python TypeError
   (in_domain/3) on the translator.  clpz does not evaluate a bound: Scryer
   raises domain_error(clpz_domain, 1..(3-1)), and instantiation_error for
   any unbound part (``must_be(ground, Drep)``), which the native front end
   gave as domain_error.
5. The translator's reader never had the clpz operators: ``#=``/``in``
   were syntax errors after ``:- use_module(library(clpz))``.

The program's expected lines are what Scryer prints (``writeq/1``); both
front ends run it and must agree.  ``assert_rule`` passes on Scryer because
the assert succeeds there, and on Clausal because the refusal is caught.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = """\
:- use_module(library(clpz)).
:- use_module(library(lists)).
:- dynamic(h/2).
:- dynamic(h2/2).
r(G) :- catch(call(G), E, (writeq(G), write(' raised '), writeq(E), nl, fail)),
    writeq(G-yes), nl.
r(G) :- \\+ catch(call(G), _, fail), writeq(G-no), nl.

lt :- G = (1+1 < 3), call(G).
gt :- G = (1+1 > 3), call(G).
le :- G = (1+1 =< 3), call(G).
ge :- G = (1+1 >= 3), call(G).
aeq :- G = (1+1 =:= 2), call(G).
ane :- G = (1+1 =\\= 2), call(G).
cmp_cell :- D = (1 < 2+0), D =.. L, writeq(L), nl.
ceq :- G = (X #= 1+1), call(G), writeq(X), nl.
cne :- G = (X #\\= 1+1), X in 1..3, call(G), findall(X, label([X]), L), writeq(L), nl.
clt :- G = (X #< 1+1), X in 0..5, call(G), findall(X, label([X]), L), writeq(L), nl.
cgt :- G = (X #> 1+1), X in 0..3, call(G), X == 3.
cle :- G = (X #=< 1+1), X in 2..5, call(G), X == 2.
cge :- G = (X #>= 1+1), X in 0..2, call(G), X == 2.
ceq_cell :- D = (1 #= 1+0), D = (A #= B), A == 1, B == 1+0.
creif_cell :- D = (_ #<==> _), functor(D, F, 2), F == (#<==>).
goal_clt :- X in 0..5, X #< 1+1, X #> 0, writeq(X), nl.
meta_clt :- findall(X, (member(X, [1,2,3]), X #> 1, X #< 3), L), writeq(L), nl.
assert_rule :- catch(assertz((h(X, Y) :- Y = X+1)),
                     error(permission_error(assert, rule, _), _), true).
assert_fact :- assertz((h2(1, 2) :- true)), h2(1, R), writeq(R), nl.
clause_cell :- C = (a :- b, c), writeq(C), nl, C = (H :- B), writeq(H/B), nl.
rule_cell :- C = (a --> b), writeq(C), nl.
conj_arg :- X = f((b, c)), writeq(X), nl, X = f(','(P, Q)), writeq(P/Q), nl.
disj_cell :- X = (a ; b), writeq(X), nl, X = (P ; Q), writeq(P/Q), nl,
    G = (fail ; true), call(G).
neg_cell :- X = (\\+ a), writeq(X), nl, G = (\\+ fail), call(G).
unify_cell :- G = (X = 1), call(G), writeq(X), nl,
    C = (p, Y = f(Z)), C = (_, (A = B)), A == Y, B == f(Z).
univ_cell :- G = (_ =.. [f, a]), call(G), writeq(G), nl, G =.. L, writeq(L), nl.
in_expr_bound :- N = 3, catch(X in 1..(N-1), error(E, _), true),
    var(X), E == domain_error(clpz_domain, 1..(3-1)).
ins_expr_bound :- catch([_, _] ins 0..(1+1), error(E, _), true),
    E == domain_error(clpz_domain, 0..(1+1)).
in_unbound_bound :- catch(_ in 1..(_-1), error(E, _), true),
    E == instantiation_error.
in_atom_bound :- catch(_ in 1..foo, error(E, _), true),
    E == domain_error(clpz_domain, 1..foo).
in_sup :- X in 1..sup, X #< 3, X #\\= 1, writeq(X), nl.

main :- r(lt), r(gt), r(le), r(ge), r(aeq), r(ane), r(cmp_cell),
    r(ceq), r(cne), r(clt), r(cgt), r(cle), r(cge), r(ceq_cell),
    r(creif_cell), r(goal_clt), r(meta_clt), r(assert_rule), r(assert_fact),
    r(clause_cell), r(rule_cell), r(conj_arg), r(disj_cell), r(neg_cell), r(unify_cell),
    r(univ_cell),
    r(in_expr_bound), r(ins_expr_bound), r(in_unbound_bound),
    r(in_atom_bound), r(in_sup).
"""

EXPECTED = [
    'lt-yes',
    'gt-no',
    'le-yes',
    'ge-no',
    'aeq-yes',
    'ane-no',
    '[<,1,2+0]',
    'cmp_cell-yes',
    '2',
    'ceq-yes',
    '[1,3]',
    'cne-yes',
    '[0,1]',
    'clt-yes',
    'cgt-yes',
    'cle-yes',
    'cge-yes',
    'ceq_cell-yes',
    'creif_cell-yes',
    '1',
    'goal_clt-yes',
    '[2]',
    'meta_clt-yes',
    'assert_rule-yes',
    '2',
    'assert_fact-yes',
    'a:-b,c',
    'a/(b,c)',
    'clause_cell-yes',
    'a-->b',
    'rule_cell-yes',
    'f((b,c))',
    'b/c',
    'conj_arg-yes',
    'a;b',
    'a/b',
    'disj_cell-yes',
    '\\+a',
    'neg_cell-yes',
    '1',
    'unify_cell-yes',
    'f(a)=..[f,a]',
    '[=..,f(a),[f,a]]',
    'univ_cell-yes',
    'in_expr_bound-yes',
    'ins_expr_bound-yes',
    'in_unbound_bound-yes',
    'in_atom_bound-yes',
    '2',
    'in_sup-yes',
]


def _run(tmp_path, frontend):
    (tmp_path / "datafollow.pl").write_text(PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "clausal", "datafollow.pl"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_data_position_terms_match_scryer(tmp_path, frontend):
    r = _run(tmp_path, frontend)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == EXPECTED, r.stdout


def _translate(source):
    from clausal.tools.prolog_dialect import Dialect
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    return prolog_to_clausal(source, dialect=Dialect.scryer_reader())


_CLPZ = ":- use_module(library(clpz)).\n"


@pytest.mark.parametrize("source, emitted", [
    # data: the ISO cell
    ("t :- G = (1+1 < 3), call(G).", "G is '<'('+'(1, 1), 3)"),
    ("t :- G = (1 =:= 2), call(G).", "G is '=:='(1, 2)"),
    (_CLPZ + "t :- G = (X #= 1+1), call(G).", "G is '#='(X, '+'(1, 1))"),
    (_CLPZ + "t :- G = (X #\\= 1), call(G).", "G is '#\\\\='(X, 1)"),
    (_CLPZ + "t :- p(X #<==> B).", "p('#<==>'(X, B))"),
    ("t :- X = (a :- b, c), p(X).", "X is ':-'(a, ','(b, c))"),
    ("t :- X = f((b, c)), p(X).", "f(','(b, c))"),
    ("t :- X = (a ; b), p(X).", "X is ';'(a, b)"),
    ("t :- X = (\\+ a), p(X).", "X is '\\\\+'(a)"),
    ("t :- X = (A = b), p(X, A).", "X is '='(A, b)"),
    ("t :- X = (A =.. L), p(X, A, L).", "X is '=..'(A, L)"),
    ("t :- A =.. L, p(A, L).", "unpack(A, L)"),
    ("t :- assertz((h(X, Y) :- Y = X+1)).",
     "assertz(':-'(h(X, Y), '='(Y, '+'(X, 1))))"),
    # goals and meta-call goal arguments keep the seam's spelling
    ("t :- A+1 =:= B, p(A, B).", "A + 1 == B"),
    ("t :- findall(X, (p(X), X > 1+1), L), q(L).", "X > 1 + 1"),
    ("t :- findall(X, (p(X) ; q(X)), L), r(L).", "p(X) or q(X)"),
    (_CLPZ + "t :- X #= 1+1, p(X).", "X == 1 + 1"),
    (_CLPZ + "t :- X #< 1+1, p(X).", "'#<'(X, '+'(1, 1))"),
    ("t :- {X > 1, Y < X}, p(X, Y).", "{X > 1, Y < X}"),
    ("t :- maplist(=(1), L), p(L).", "maplist('='(1), L)"),
    ("t :- include(>(2), [1], L), p(L).", "include('>'(2), [1], L)"),
])
def test_the_translator_text(source, emitted):
    text = _translate(source)
    assert emitted in text, text


@pytest.mark.parametrize("directive", [
    ":- use_module(library(clpz)).",
    ":- use_module(library(clpz), [label/1]).",
    ":- use_module(library(clpz), [(#=)/2, op(700, xfx, #=)]).",
])
def test_use_module_clpz_brings_its_operators_to_the_reader(directive):
    text = _translate(directive + "\nt(X, Y) :- X #= Y + 1, X in 1..3, Y #< X.")
    assert "X == Y + 1" in text, text
    assert "in_domain(X, 1, 3)" in text, text
    assert "'#<'(Y, X)" in text, text


def test_without_clpz_the_operators_are_not_read():
    from clausal.tools.prolog_parser import ParseError
    with pytest.raises(ParseError):
        _translate("t(X, Y) :- X #= Y + 1.")


def test_a_library_import_list_brings_only_the_named_non_sticky_ops():
    from clausal.tools.iso_l3_directives import library_reader_ops
    assert library_reader_ops("lambda", []) == []
    assert library_reader_ops("lambda", [(201, "xfx", "+\\")]) == [
        (201, "xfx", "+\\")]
    assert (700, "xfx", "#=") in library_reader_ops("clpz", [])
    assert library_reader_ops("lists", None) == []


class TestInDomainBounds:
    """clpfd's in_domain/3 (the translator's ``in``/``ins``) reads a bound
    as clpz reads ``Lo..Hi``: never a raw Python exception."""

    def _post(self, lo, hi):
        from clausal.logic.clpfd import in_domain
        from clausal.logic.variables import Trail, Var
        x = Var()
        return x, in_domain(x, lo, hi, Trail())

    def _formal(self, lo, hi):
        from clausal.logic.exceptions import LogicException
        from clausal.logic.variables import walk
        with pytest.raises(LogicException) as ei:
            self._post(lo, hi)
        return walk(ei.value.term)[1]

    def test_an_expression_bound_is_a_domain_error(self):
        assert self._formal(1, ("-", 3, 1)) == (
            "domain_error", "clpz_domain", ("..", 1, ("-", 3, 1)))

    def test_an_atom_bound_is_a_domain_error(self):
        assert self._formal(1, "foo") == (
            "domain_error", "clpz_domain", ("..", 1, "foo"))

    def test_an_unbound_part_is_an_instantiation_error(self):
        from clausal.logic.variables import Var
        assert self._formal(1, ("-", Var(), 1)) == "instantiation_error"

    def test_inf_and_sup_are_the_open_ends(self):
        from clausal.logic.clpfd import FD_KEY
        from clausal.logic.variables import get_attr
        x, ok = self._post("inf", "sup")
        assert ok and get_attr(x, FD_KEY) is not None


def test_quoted_iso_punctuation_builds_cells_in_the_seam(tmp_path):
    """The seam spelling the translator emits: ``':-'(a, b)``, ``';'(a,
    b)``, ``'..'(1, 3)`` ... in term position build the ISO cell (they
    raised existence_error(procedure, (:-)/2) / NameError)."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, walk
    from tests._suffix import SEAM
    path = tmp_path / f"quoted_punct{SEAM}"
    path.write_text(
        "-private([a, b])\n\n"
        "t(X) <- (X is [':-'(a, b), '-->'(a, b), ';'(a, b), '|'(a, b), "
        "'\\\\+'(a), ','(a, b), '..'(1, 3)])\n")
    mod = _load_module("quoted_punct", str(path))
    x = Var()
    answers = [walk(x) for _ in call(mod.t, x)]
    assert answers == [[(":-", "a", "b"), ("-->", "a", "b"), (";", "a", "b"),
                        ("|", "a", "b"), ("\\+", "a"), (",", "a", "b"),
                        ("..", 1, 3)]]


#: Comparison, unification and clpz relation CLOSURES applied by call/N
#: (2026-10-22): the translator refused ``maplist(=(1), L)``,
#: ``call(>(2), 1)``, ``include(>(2), Xs, Ys)`` as "Prolog functor '>'
#: cannot be translated", and the seam could not build the arity-1 cell
#: ``'>'(2)`` (existence_error(procedure, (>)/1)).  Lines t1..t10 are what
#: Scryer prints; t11 is not run there (this Scryer build has no
#: include/3), its answer is the one native gives.
CLOSURE_PROGRAM = """\
:- use_module(library(clpz)).
:- use_module(library(lists)).
t1 :- length(L, 2), maplist(=(1), L), writeq(L), nl.
t2 :- maplist(<(0), [1,2]), \\+ maplist(<(1), [1,2]), write(ok2), nl.
t3 :- call(>(2), 1), \\+ call(>(2), 3), write(ok3), nl.
t4 :- maplist(==(a), [a,a]), \\+ maplist(\\==(a), [a]), write(ok4), nl.
t5 :- maplist(=<(2), [2,3]), maplist(>=(2), [1,2]), write(ok5), nl.
t6 :- maplist(=:=(2), [2, 1+1]), maplist(=\\=(2), [1,3]), write(ok6), nl.
t7 :- maplist(\\=(a), [b,c]), maplist(@<(a), [b,c]), write(ok7), nl.
t8 :- G = >(2), call(G, 1), writeq(G), nl.
t9 :- X in 0..5, maplist(#<(3), [X]), X #< 5, writeq(X), nl.
t10 :- maplist(#=(X), [2]), writeq(X), nl.
t11 :- include(>(2), [1,2,3], L), exclude(>=(2), [1,2,3], M), writeq(L/M), nl.
main :- t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11.
"""

CLOSURE_EXPECTED = [
    '[1,1]',
    'ok2',
    'ok3',
    'ok4',
    'ok5',
    'ok6',
    'ok7',
    '>(2)',
    '4',
    '2',
    '[1]/[3]',
]


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_relation_closures_run_under_call_n(tmp_path, frontend):
    (tmp_path / "closures.pl").write_text(CLOSURE_PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [sys.executable, "-m", "clausal", "closures.pl"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == CLOSURE_EXPECTED, r.stdout


#: A conjunction, disjunction or unification in each GOAL position of each
#: meta-predicate the translator knows stays a goal (2026-10-22): if_/3's
#: three arguments, call/N, findall/bagof/setof, forall, catch/3's goal
#: and recovery, once, \+, (;), freeze/2, when/2, setup_call_cleanup/3,
#: call_cleanup/2, the closures of maplist/foldl/tfilter/tpartition and
#: reif's =/3 and dif/3 conditions.  Emitting a data-position cell there
#: made the seam call ``','/2`` (``Predicate ,/2 not found`` in if_/3's
#: else branch).  The translator has if_/3 built in and knows no
#: library(reif); the native front end imports it, as ISO code must.  The
#: expected lines are the native front end's (Scryer agrees on the rows it
#: runs).  Not here, failing the same way before this branch: aggregate_all
#: over member/2 and phrase/2 of a control construct on the translator,
#: catch(fail, _, true) inside a disjunction and ignore/1 on both
#: (todo/translator-meta-call-goal-gaps-2026-10-22.md).
AUDIT_PROGRAM = """\
:- use_module(library(lists)).
w(T) :- writeq(T), nl.
g --> [a], [b].
k(X, Y) :- Y is X * 10.

k3(X, A0, A) :- A is A0 + X.
m01 :- if_(1 = 1, (A = 1, B = 2), (A = 3, B = 4)), w(A/B).
m02 :- if_(1 = 2, (A = 1, B = 2), (A = 3, B = 4)), w(A/B).
m03 :- if_(dif(a, b), (A = 1 ; A = 2), A = 3), w(A).
m04 :- call((A = 1, B = A)), w(B).
m05 :- call((A = 1 ; A = 2)), w(A).
m06 :- findall(A-B, (member(A, [1,2]), B = A), L), w(L).
m07 :- bagof(A, (member(A, [2,1]), A > 0), L), w(L).
m08 :- setof(A, (member(A, [2,1,2]), \\+ A = 3), L), w(L).
m10 :- forall((member(A, [1,2]), B = A), (B > 0, A =:= B)), w(ok).
m11 :- catch((A = 1, throw(e(A))), e(E), (F = E, G = F)), w(G).
m12 :- once((member(A, [1,2]), A > 1)), w(A).
m14 :- \\+ (A = 1, A = 2), w(ok14).
m15 :- ( A = 1, B = 2 ; A = 3, B = 4 ), w(A/B).
m18 :- freeze(V, (W = V, w(W))), V = 7.
m19 :- when(nonvar(V), (W = V, w(W))), V = 8.
m20 :- setup_call_cleanup((A = 1, B = A), (C = B, w(C)), (true, true)).
m21 :- call_cleanup((A = 2, w(A)), (true, true)).
m22 :- maplist(k, [1,2], L), foldl(k3, [1,2], 0, S), w(L/S).
m23 :- tfilter(=(a), [a,b,a], L), w(L).
m24 :- tpartition(=(a), [a,b], I, E), w(I/E).
m25 :- if_((X = 1), Y = yes, Y = no), w(X/Y).
m26 :- findall(X, (member(X, [1,2,3]), if_(X = 2, true, fail)), L), w(L).
m27 :- call(k, 3, R), w(R).
main :- m01, m02, m03, m04, m05, m06, m07, m08, m10, m11, m12, m14, m15, m18, m19, m20, m21, m22, m23, m24, m25, m26, m27.
"""

AUDIT_EXPECTED = [
    '1/2',
    '3/4',
    '1',
    '1',
    '1',
    '[1-1,2-2]',
    '[2,1]',
    '[1,2]',
    'ok',
    '1',
    '2',
    'ok14',
    '1/2',
    '7',
    '8',
    '1',
    '2',
    '[10,20]/3',
    '[a,a]',
    '[a]/[b]',
    '1/yes',
    '[2]',
    '30',
]


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_goal_positions_of_meta_predicates_stay_goals(tmp_path, frontend):
    header = ":- use_module(library(reif)).\n" if frontend == "native" else ""
    (tmp_path / "audit.pl").write_text(header + AUDIT_PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [sys.executable, "-m", "clausal", "audit.pl"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == AUDIT_EXPECTED, r.stdout


@pytest.mark.parametrize("source, emitted", [
    ("t :- if_(X = 1, (a, b), (c ; d)), p(X).", "if_(X is 1, (a, b), c or d)"),
    ("t :- freeze(V, (a, b)), p(V).", "freeze(V, ('a', 'b'))"),
    ("t :- phrase((a, b), L), p(L).", "phrase(('a', 'b'), L)"),
    ("t :- phrase([], L), p(L).", "phrase([], L)"),
    # a clause argument is a clause TERM, built as data
    ("t :- assertz((h :- a, b)).", "assertz(':-'('h', ','('a', 'b')))"),
])
def test_goal_arguments_keep_the_goal_spelling(source, emitted):
    text = _translate(source)
    assert emitted in text, text
