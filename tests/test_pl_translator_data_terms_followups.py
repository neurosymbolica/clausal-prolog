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
#: runs).  aggregate_all over member/2, phrase/2 of a control construct
#: and catch(fail, _, true) are test_member_and_phrase_bodies_in_meta_and_
#: data_positions' rows; ignore/1 is no engine predicate on either front
#: end (todo/done/translator-meta-call-goal-gaps-2026-10-22.md).
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


#: The rows todo/translator-meta-call-goal-gaps-2026-10-22.md recorded
#: (2026-10-22), each failing on the translator only:
#:
#: - ``member/2`` was renamed to the seam's ``in_``, which is also the class
#:   of the seam's ``in`` operator node (fields position/left/right): as DATA
#:   (``t(l13, X, member(X, L))``) or in a goal argument a builtin receives
#:   as a term (aggregate_all/3's) the file did not load ("functor in_/3 was
#:   constructed with 2 positional argument(s)").  Every other rename of the
#:   reverse builtin map did the same harm as data: ``memberchk(a, L)``
#:   printed ``in_check(a, L)``, ``time(foo)`` ``time_goal(foo)``,
#:   ``zip(a, b)`` raised existence_error(procedure, zip_/2).  As data a
#:   term keeps its own name now; ``member`` keeps it everywhere (the engine
#:   has member/2).
#: - phrase/2,3's first argument was emitted in the seam's GOAL spelling,
#:   which phrase does not read as a grammar body: ``phrase((g, [c]), L)``
#:   raised existence_error(procedure, g/3), ``phrase(([x] ; [y], []), L)``
#:   type_error(callable, <class Or>), and ``|`` did not translate.  It is
#:   the ISO body term now, as on the native front end.
#: - A variable in the goal argument of a meta-call (``G = p(X),
#:   findall(X, G, L)``, ``\\+ G``, ``forall(G, ...)``, ``once(G)``) or as a
#:   body goal was emitted bare, which the seam refuses at load
#:   (BareGoalVariableError).  It is call(G) now.
#: - A grammar rule with a pushback and an atom head (``pb, [p] --> [q]``)
#:   wrote the head as the atom ``'pb'``, which the seam's ``>>`` did not
#:   read ("unsupported operand type(s) for >>").
#: - In a grammar RULE body, an atom nonterminal (``r5 --> g``) was the
#:   quoted atom ``'g'``, which a seam grammar body reads as the terminals
#:   of its characters (``phrase(r5, L)`` gave ``L = [g]``); and a branch of
#:   ``;`` went through the goal emitter, so ``[]`` there was the goal
#:   ``[]/2`` and ``|`` did not translate.
#: - ``catch(fail, _, true)`` did not load on either front end ("empty body
#:   on Try"): the goal ``fail`` lowers to no statements, and the inline
#:   catch put that empty list into a Python ``try`` body
#:   (todo/done/catch-fail-goal-compiles-to-an-empty-try-2026-10-16.md).
#: - library(clpz)'s ``X in 1..2 \\/ 5`` (no in_domain/3 fold) took the
#:   keyword rename to ``in_`` too: list membership as a goal (``[]``), a
#:   load error as a term.  And a qualified ``m:g`` as data was the call
#:   ``m.g()``, and ``M:P`` with a variable module was refused.
#:
#: The expected lines are Scryer's (writeq/1), which both front ends match.
META_GAPS_PROGRAM = """\
:- use_module(library(dcgs)).
:- use_module(library(lists)).
:- use_module(library(iso_ext)).
:- use_module(library(clpz)).
w(T) :- writeq(T), nl.
g --> [a], [b].
k2(X) --> [X].
pb, [p] --> [q].
r1 --> [x] ; [y], [].
r2 --> ([x] | [y]), {true}.
r3 --> {X = 1 ; X = 2}, {X > 1}.
r5 --> g.
r6 --> call(g), k2(c).
t(l13, X, member(X, [a, b, c])).
p(1). p(2).
kc(X) :- catch(fail, _, true), X = 1.
d01 :- phrase((g, [c]), [a,b,c]), w(d01).
d02 :- phrase(([x] ; [y], []), [y]), w(d02).
d03 :- phrase(([x] | [y]), [y]), w(d03).
d04 :- phrase(({X = 1}, [a]), [a]), w(X).
d05 :- phrase((call(k2, z), g), [z,a,b]), w(d05).
d06 :- phrase(("ab", [c]), [a,b,c]), w(d06).
d07 :- phrase((pb, [p]), [q]), w(d07).
d08 :- phrase(([], g ; []), [a, b]), w(d08).
d09 :- phrase(((g ; [x]), {true}), [x], R), w(R).
d10 :- findall(L, phrase(([a] ; [b]), L), Ls), w(Ls).
d11 :- phrase(({X = 1 ; X = 2}, {X > 1}), []), w(X).
d12 :- findall(X, phrase(({member(X, [a,b])}, [X]), [b]), L), w(L).
d13 :- findall(X-Y, phrase((k2(X), k2(Y) ; [X]), [1, 2]), L), w(L).
d14 :- phrase([], []), phrase("", []), w(d14).
m01 :- w(member(a, [a, b, c])).
m02 :- w(f(memberchk(a, [a]), time(foo), zip(a, b), fd_domain(a, b, c))).
m03 :- G = member(Q, [1, 2]), findall(Q, G, L), w(L).
m04 :- lists:member(a, [a]), w(m04).
m05 :- findall(X, member(X, [1,2]), L), w(L).
m06 :- findall(X, (member(X, [1,2,3]), \\+ memberchk(X, [2])), L), w(L).
m07 :- X = [member(A, [b]), memberchk(A, [b])], A = b, w(X).
m08 :- t(l13, X, G), findall(X, G, L), w(L).
v01 :- G = p(Q), findall(Q, G, L), w(L).
v02 :- G = p(1), \\+ \\+ G, w(v02).
v03 :- G = p(Q), forall(G, Q > 0), w(v03).
v04 :- G = p(Q), bagof(Q, G, L), w(L).
v05 :- G = p(Q), G, w(Q).
v06 :- G = p(Q), (G, Q > 1), w(Q).
v07 :- G = member(Q, [a]), once(G), w(Q).
v08 :- G = p(Q), catch(G, _, true), w(Q).
v09 :- C = p, maplist(C, [1, 2]), w(v09).
v10 :- G = p(Q), (fail ; G), w(Q).
e01 :- phrase(r1, [y]), phrase(r2, [y]), phrase(r3, []), w(e01).
e02 :- phrase(r5, L), w(L).
e03 :- phrase(r6, L), w(L).
c01 :- catch(fail, _, true) ; w(c01).
c02 :- \\+ kc(_), w(c02).
c03 :- catch((fail, w(no)), _, w(no)) ; catch(fail, e, true) ; w(c03).
q01 :- findall(X, (X in 1..2 \\/ 5, label([X])), L), w(L).
q02 :- G = (X in 1..2), call(G), findall(X, label([X]), L), w(L).
q03 :- T = t(mm:append, m:f(x)), T = t(M:P, Q), w(M/P/Q).
main :- d01, d02, d03, d04, d05, d06, d07, d08, d09, d10, d11, d12, d13, d14,
    m01, m02, m03, m04, m05, m06, m07, m08,
    v01, v02, v03, v04, v05, v06, v07, v08, v09, v10, e01, e02, e03,
    c01, c02, c03, q01, q02, q03.
"""

META_GAPS_EXPECTED = [
    'd01', 'd02', 'd03', '1', 'd05', 'd06', 'd07', 'd08', '[]',
    '[[a],[b]]', '2', '[b]', '[1-2]', 'd14',
    'member(a,[a,b,c])',
    'f(memberchk(a,[a]),time(foo),zip(a,b),fd_domain(a,b,c))',
    '[1,2]', 'm04', '[1,2]', '[1,3]',
    '[member(b,[b]),memberchk(b,[b])]',
    '[a,b,c]',
    '[1,2]', 'v02', 'v03', '[1,2]', '1', '2', 'a', '1', 'v09', '1',
    'e01', '[a,b]', '[a,b,c]',
    'c01', 'c02', 'c03',
    '[1,2,5]', '[1,2]', 'mm/append/(m:f(x))',
]


#: Rows with no Scryer answer to compare: Scryer has no aggregate_all/3
#: (no library(aggregate)), and refuses ``\+`` in a grammar body
#: (representation_error(dcg_body)) where Clausal's phrase runs it as
#: ``\+ phrase(B, S0, _), S0 = S``.  The expected lines are the native
#: front end's.
META_GAPS_NATIVE_PROGRAM = """\
:- use_module(library(dcgs)).
:- use_module(library(lists)).
w(T) :- writeq(T), nl.
a1 :- aggregate_all(count, (member(A, [1,2,3]), A > 1), N), w(N).
a2 :- aggregate_all(count, member(_, [a, b]), N), w(N).
a3 :- phrase((\\+ [a], [b]), [b]), w(a3).
main :- a1, a2, a3.
"""

META_GAPS_NATIVE_EXPECTED = ['2', '2', 'a3']


@pytest.mark.parametrize("frontend", ["translator", "native"])
@pytest.mark.parametrize("program, expected", [
    (META_GAPS_PROGRAM, META_GAPS_EXPECTED),
    (META_GAPS_NATIVE_PROGRAM, META_GAPS_NATIVE_EXPECTED),
], ids=["scryer", "native"])
def test_member_and_phrase_bodies_in_meta_and_data_positions(
        tmp_path, frontend, program, expected):
    (tmp_path / "gaps.pl").write_text(program)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [sys.executable, "-m", "clausal", "gaps.pl"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == expected, r.stdout


@pytest.mark.parametrize("source, emitted", [
    ("t :- if_(X = 1, (a, b), (c ; d)), p(X).", "if_(X is 1, (a, b), c or d)"),
    ("t :- freeze(V, (a, b)), p(V).", "freeze(V, ('a', 'b'))"),
    # phrase/2's grammar body is the ISO body term the runtime phrase
    # translates, not the seam's goal spelling (2026-10-22)
    ("t :- phrase((a, b), L), p(L).", "phrase(','('a', 'b'), L)"),
    ("t :- phrase(({a}, [b] ; [c]), L), p(L).",
     "phrase(';'(','('{}'(a), [b]), [c]), L)"),
    # a variable called as a goal is call(G) (the seam refuses a bare one)
    ("t :- G = p(X), findall(X, G, L), q(L).", "findall(X, call(G), L)"),
    ("t :- G = p, G.", "call(G)"),
    ("t :- maplist(C, [1]), q(C).", "maplist(C, [1])"),
    ("t :- phrase([], L), p(L).", "phrase([], L)"),
    # a clause argument is a clause TERM, built as data
    ("t :- assertz((h :- a, b)).", "assertz(':-'('h', ','('a', 'b')))"),
])
def test_goal_arguments_keep_the_goal_spelling(source, emitted):
    text = _translate(source)
    assert emitted in text, text
