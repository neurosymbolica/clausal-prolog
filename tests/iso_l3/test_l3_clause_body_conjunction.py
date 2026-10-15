"""clause/2 and retract/1 read a conjunction body as the ISO term
``','(A, ','(B, C))`` in a Prolog-surface (``.pl`` / ``.clausal``) module.

The engine stores a conjunction as a FLAT goal list, and clause/2 handed it
back as the flat tuple ``(A, B, C)`` -- which, when A is an atom, is the
CELL ``A(B, C)``.  So ``d(X) :- nl, X = 1`` read back as ``nl(X = 1)``,
``functor/3`` failed on every other conjunction, and retract DELETED THE
WRONG CLAUSES: ``retract((d(_) :- (_, _)))`` removed ``d(X) :- X = 1``,
``retract((d(_) :- nl(_)))`` removed ``d(X) :- nl, X = 1``
(todo/done/clause-body-conjunction-is-a-flat-tuple-retract-deletes-wrong-
clause-2026-10-14.md).

Every expectation marked "Scryer" is Scryer's answer for the same program
(2026-10-14, stdin </dev/null).  Rows marked "ISO" are ones Scryer cannot
answer: it panics on a ``findall/3`` body pattern, and its retract misses
clause/2's own bodies when they hold ``>`` or ``;``."""
from __future__ import annotations

import pytest

SRC = """\
:- dynamic(d/1).
:- dynamic(e/1).
:- dynamic(f/1).
d(X) :- X = 1.
d(X) :- nl, X = 1.
d(X) :- X = 1, X > 0, X < 5, X =< 3.
d(X) :- \\+ X = 2.
d(X) :- (X = 1 ; X = 2).
d(X) :- findall(Y, (Y = 1, Y > 0), X).
d(7).
e(X) :- X = 1.
e(X) :- X = 2, X > 0.
e(X) :- nl, X = 3.
e(X) :- findall(Y, (Y = 4, Y > 0), X).
e(X) :- X = 5, X > 0, X < 9, X > 1.
e(6).
f(X) :- X = 1.
f(X) :- X = 2, X > 0.
f(X) :- nl, X = 3.
f(X) :- X = 5, X > 0, X < 9.
f(X) :- \\+ X = 7.
f(X) :- (X = 8 ; X = 9).
f(6).
fa(B, F/A) :- functor(B, F, A).
r01(R-N) :- findall(x, retract((d(_) :- (_, _))), R), findall(x, clause(d(_), _), N).
r02(L-N) :- findall(x, retract((d(_) :- nl(_))), L), findall(x, clause(d(_), _), N).
r03(L) :- findall(FA, (clause(e(_), B), fa(B, FA)), L).
r04(L) :- findall(x, clause(d(_), (_, _)), L).
r05(L) :- findall(x, (clause(d(_), B), B = (_, _)), L).
r06(L) :- findall(FA, (clause(d(_), (_, _, R)), fa(R, FA)), L).
r07(L) :- findall(FA, (clause(d(_), (_ = _, R)), fa(R, FA)), L).
r08(L) :- findall(x, clause(d(_), (_, (_, (_, _)))), L).
r09(L) :- findall(x, clause(d(_), ','(_, ','(_, ','(_, ','(_, _))))), L).
r10(L) :- findall(x, clause(d(_), (_ = _, (_ > _, _))), L).
r11(L) :- findall(FA, (clause(d(_), (nl, B)), fa(B, FA)), L).
r12(L) :- findall(x, clause(d(_), nl(_)), L).
r13(L) :- findall(x, (clause(d(_), B), B = nl(_)), L).
r14(L) :- findall(FA, (clause(d(_), ','(A, _)), fa(A, FA)), L).
r15(L-R) :- findall(FA, (retract((e(_) :- B)), fa(B, FA)), L), findall(x, clause(e(_), _), R).
r16(L-R) :- findall(X, retract((e(X) :- true)), L), findall(x, clause(e(_), _), R).
r17(L) :- findall(FA, (clause(e(_), (_, _, R)), fa(R, FA)), L).
r18(L) :- findall(x, clause(e(_), (_ = 5, _ > 0, _ < 9, _ > 1)), L).
r19(L) :- findall(x, clause(e(_), (_ = 5, _ > 0)), L).
r20(L) :- findall(H-R, (clause(e(H), B), findall(H, B, R)), L).
r21(L) :- findall(FA, (clause(e(_), findall(_, G, _)), fa(G, FA)), L).
r22(L) :- findall(x, clause(e(_), findall(_, (_, _), _)), L).
r23(L-N) :- findall(x, retract((e(_) :- findall(_, (_ = 4, _), _))), L), findall(x, clause(e(_), _), N).
r24(L-R) :- findall(x, (clause(f(H), B), once(retract((f(H) :- B)))), L), findall(x, clause(f(_), _), R).
r25(L) :- findall(H-R, (clause(f(H), B), findall(H, B, R)), L).
"""


def _fa(*pairs):
    return [("/", f, a) for f, a in pairs]


# (row, expected) -- Scryer's answers unless the comment says ISO.
ROWS = [
    # retract((d(_) :- (_, _))) removes the two conjunctions only
    ("r01", [("-", ["x", "x"], ["x"] * 5)]),
    # nl(_) is no conjunction: nothing is removed
    ("r02", [("-", [], ["x"] * 7)]),
    ("r03", [_fa(("=", 2), (",", 2), (",", 2), ("findall", 3), (",", 2),
                 (True, 0))]),
    ("r04", [["x", "x"]]),
    ("r05", [["x", "x"]]),
    # (_, _, R): R is the rest of the 4-goal conjunction, a ','/2 term
    ("r06", [_fa((",", 2))]),
    ("r07", [_fa((",", 2))]),
    # deeper conjunctions: exactly 4 goals, not 5
    ("r08", [["x"]]),
    ("r09", [[]]),
    # partially bound patterns
    ("r10", [["x"]]),
    ("r11", [_fa(("=", 2))]),
    # a compound goal matches only its own functor
    ("r12", [[]]),
    ("r13", [[]]),
    ("r14", [_fa(("nl", 0), ("=", 2))]),
    # retract((H :- B)), B unbound: every clause, in clause order
    ("r15", [("-", _fa(("=", 2), (",", 2), (",", 2), ("findall", 3),
                       (",", 2), (True, 0)), [])]),
    # retract((H :- true)): the facts only
    ("r16", [("-", [6], ["x"] * 5)]),
    ("r17", [_fa((",", 2))]),
    ("r18", [["x"]]),
    ("r19", [[]]),
]

# Scryer panics on a findall/3 body pattern: ISO-derived expectations.
ISO_ROWS = [
    ("r21", [_fa((",", 2))]),
    ("r22", [["x"]]),
    ("r23", [("-", ["x"], ["x"] * 5)]),
    # clause/2's own Body, as a retract pattern, removes that clause --
    # every one (Scryer removes 4 of 7: it misses its own bodies holding
    # > or ;)
    ("r24", [("-", ["x"] * 7, [])]),
]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("row,want", ROWS + ISO_ROWS,
                         ids=[r for r, _ in ROWS + ISO_ROWS])
def test_conjunction_body_rows(native, ans, row, want, suffix):
    mod = native.load(f"l3_conj_{row}_{suffix[1:]}", SRC, suffix=suffix)
    assert ans(mod, row) == want


def test_clause_body_runs_as_the_clause_does(native, ans):
    """clause(H, B), call(B) answers what H does, for every body shape
    (Scryer: e [1,2,3,[[4]],5,6], f [1,2,3,5,[],[8,9],6])."""
    mod = native.load("l3_conj_call", SRC)
    got = [r for _m, _h, r in ans(mod, "r20")[0]]
    assert got == [[1], [2], [3], [[4]], [5], [6]]
    got = [r for _m, _h, r in ans(mod, "r25")[0]]
    assert got == [[1], [2], [3], [5], [], [8, 9], [6]]


def test_a_left_grouped_conjunction_reads_back_as_written(native, ans):
    """``A, (B, C), D`` is the ISO term ``','(A, ','(','(B, C), D))``.  The
    compiler stores the body FLAT; clause/2 reads the body as read
    (``Clause.source_body``), so the Body is the term as written and a
    pattern of another grouping does NOT match (it used to: a wrong
    deletion).  Scryer: r1 [(',')/2], r2 []."""
    mod = native.load("l3_conj_grouping",
                      ":- dynamic(g/1).\n"
                      "g(X) :- X = 5, (X > 0, X < 9), X > 1.\n"
                      "fa(B, F/A) :- functor(B, F, A).\n"
                      "r1(L) :- findall(FA, (clause(g(_), (_, P, _)), fa(P, FA)), L).\n"
                      "r2(L) :- findall(x, clause(g(_), (_ = 5, _ > 0, _ < 9, _ > 1)), L).\n")
    assert ans(mod, "r1") == [_fa((",", 2))]
    assert ans(mod, "r2") == [[]]


SRC2 = """\
:- dynamic(c/2).
:- dynamic(a/1).
:- dynamic(b/1).
:- dynamic(n/2).
c(9,X) :- (X = 1, X > 0), X < 5.
c(19,X) :- X = 1, ((X > 0, X < 2), X > -1).
c(20,X) :- ((X = 1, X > 0), X < 2), X > -1.
c(21,X) :- X = 1, (X > 0, X < 2), X > -1.
c(5,X) :- X = 1, X > 0, X < 5.
c(6,X) :- X = 1, X > 0.
a(1) :- fail.
a(2) :- false.
a(3) :- fail, a(1).
b(1) :- fail.
b(2) :- false.
n(1,X) :- \\+ (X = 2, X = 3).
n(2,X) :- \\+ (nl, X = 1).
n(3,X) :- \\+ nl(X).
n(4,X) :- (X = 1 ; X = 2, X > 0).
n(5,X) :- X = 1, \\+ X = 2.
n(6,X) :- X = 1, (X = 2 ; X = 3).
n(7,X) :- (X = 1 ; X = 2).
fa(B, F/A) :- functor(B, F, A).
g01(L) :- findall(N, retract((c(N,_) :- (_, _, _))), L).
g02(L) :- findall(N, retract((c(N,_) :- (_ = _, _))), L).
g03(L) :- findall(N, retract((c(N,_) :- (_ = 1, _ > 0, _ < 5))), L).
g04(L) :- findall(N, retract((c(N,_) :- (_, _, _, _))), L).
g05(L) :- findall(N, retract((c(N,_) :- ((_, _), _))), L).
g06(L) :- findall(N, retract((c(N,_) :- (_, (_, _), _))), L).
g07(L) :- findall(N-FA-FB, (clause(c(N,_), ','(P, Q)), fa(P, FA), fa(Q, FB)), L).
g08(L) :- findall(N, (clause(c(N,X), B), findall(X, B, [1])), L).
g09(L) :- findall(N, (clause(c(N,H), B), once(retract((c(N,H) :- B)))), L).
f01(L) :- findall(N, retract((a(N) :- fail)), L).
f02(L) :- findall(N, retract((b(N) :- false)), L).
f03(L) :- findall(N-FA, (clause(a(N), B), fa(B, FA)), L).
f04(L) :- findall(N, retract((a(N) :- (fail, _))), L).
f05(L) :- findall(N, (clause(a(N), B), \\+ call(B)), L).
m01(L) :- findall(N, retract((n(N,_) :- \\+ (_, _))), L).
m02(L) :- findall(N, retract((n(N,_) :- \\+ nl(_))), L).
m03(L) :- findall(N, retract((n(N,_) :- (_ ; _, _))), L).
m04(L) :- findall(N, retract((n(N,_) :- (_ = _, \\+ _))), L).
m05(L) :- findall(N, retract((n(N,_) :- (_, (_ ; _)))), L).
m06(L) :- findall(N, retract((n(N,_) :- (_ ; _))), L).
m07(L) :- findall(N, retract((n(N,_) :- \\+ (nl, _))), L).
"""

# Scryer's answers (2026-10-15), except g09 (Scryer panics; ISO: every
# clause/2 Body, as a retract pattern, removes its own clause).
ROWS2 = [
    # grouping: (A, B), C and A, (B, C), D are NOT (A, B, C) / (A, B, C, D)
    ("g01", [[19, 21, 5]]),
    ("g02", [[19, 21, 5, 6]]),
    ("g03", [[5]]),
    ("g04", [[]]),
    ("g05", [[9, 20]]),
    ("g06", [[19, 21]]),
    ("g07", [[("-", ("-", 9, ("/", ",", 2)), ("/", "<", 2)),
              ("-", ("-", 19, ("/", "=", 2)), ("/", ",", 2)),
              ("-", ("-", 20, ("/", ",", 2)), ("/", ">", 2)),
              ("-", ("-", 21, ("/", "=", 2)), ("/", ",", 2)),
              ("-", ("-", 5, ("/", "=", 2)), ("/", ",", 2)),
              ("-", ("-", 6, ("/", "=", 2)), ("/", ">", 2))]]),
    ("g08", [[9, 19, 20, 21, 5, 6]]),
    ("g09", [[9, 19, 20, 21, 5, 6]]),
    # fail is not false (both run as the goal False)
    ("f01", [[1]]),
    ("f02", [[2]]),
    ("f03", [[("-", 1, ("/", "fail", 0)), ("-", 2, ("/", False, 0)),
              ("-", 3, ("/", ",", 2))]]),
    ("f04", [[3]]),
    ("f05", [[1, 2, 3]]),
    # conjunctions inside \+ and ;, and pattern operands, at any depth
    ("m01", [[1, 2]]),
    ("m02", [[3]]),
    ("m03", [[4]]),
    ("m04", [[5]]),
    ("m05", [[6]]),
    ("m06", [[4, 7]]),
    ("m07", [[2]]),
]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("row,want", ROWS2, ids=[r for r, _ in ROWS2])
def test_grouping_fail_and_nested_rows(native, ans, row, want, suffix):
    mod = native.load(f"l3_conj2_{row}_{suffix[1:]}", SRC2, suffix=suffix)
    assert ans(mod, row) == want


SRC3 = """\
:- dynamic(t/1).
:- dynamic(zd/0).
:- dynamic(zs/0).
zd.
zs.
t(1) :- zs, X = 1, X > 0.
t(2) :- zd, X = 2.
t(3) :- zu, X = 3.
t(4) :- X = 4, zs.
fa(B, F/A) :- functor(B, F, A).
z1(L) :- findall(N-FA, (clause(t(N), B), fa(B, FA)), L).
z2(L) :- findall(N-FA, (clause(t(N), ','(A, _)), fa(A, FA)), L).
z3(L) :- findall(N, retract((t(N) :- zs(_))), L).
z4(L) :- findall(N, retract((t(N) :- zd(_))), L).
z5(L) :- findall(N, retract((t(N) :- (zs, _))), L).
z6(L) :- findall(N, retract((t(N) :- (_, zs))), L).
z7(L) :- findall(N, (clause(t(N), B), once(retract((t(N) :- B)))), L).
"""

# A conjunction whose FIRST goal is an atom (a zero-arity call: a dynamic
# or an undefined procedure) read back as the
# compound ``zs(X = 1, X > 0)``: functor/3 gave zs/2, and
# retract((t(N) :- zd(_))) removed t(2).  Scryer's answers (2026-10-15),
# except z7 (Scryer panics; ISO: each Body removes its own clause).
ROWS3 = [
    ("z1", [[("-", n, ("/", ",", 2)) for n in (1, 2, 3, 4)]]),
    ("z2", [[("-", 1, ("/", "zs", 0)), ("-", 2, ("/", "zd", 0)),
             ("-", 3, ("/", "zu", 0)), ("-", 4, ("/", "=", 2))]]),
    ("z3", [[]]),
    ("z4", [[]]),
    ("z5", [[1]]),
    ("z6", [[4]]),
    ("z7", [[1, 2, 3, 4]]),
]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("row,want", ROWS3, ids=[r for r, _ in ROWS3])
def test_an_atom_first_conjunct_is_not_a_functor(native, ans, row, want,
                                                 suffix):
    mod = native.load(f"l3_conj3_{row}_{suffix[1:]}", SRC3, suffix=suffix)
    assert ans(mod, row) == want


SRC4 = """\
:- use_module(library(reif)).
:- dynamic(c/2).
:- dynamic(t1/2).
:- dynamic(r/1).
:- dynamic(d/2).
t1(_, true).
c(61,X) :- if_(t1(X), (X > 0, X < 5), false).
c(62,X) :- if_(t1(X), X > 0, X < 0), X = 1.
c(63,X) :- X = 1, if_(t1(X), X > 0, X < 0).
c(64,X) :- X = 1, X > 0.
r(1) :- fail, nl, false.
r(2) :- false, nl, fail.
d(1,X) :- X = false.
d(2,X) :- X = fail, false.
q01(L) :- findall(N, retract((c(N,_) :- (_, _))), L).
q02(L) :- findall(N, retract((c(N,_) :- (_, _, _))), L).
q03(L) :- findall(N, retract((c(N,_) :- ((_, _), _))), L).
q04(L) :- findall(N, retract((c(N,_) :- (_, _, _, _))), L).
q05(L) :- findall(N, retract((c(N,_) :- _)), L).
q06(L) :- findall(N, retract((r(N) :- (fail, nl, false))), L).
q07(L) :- findall(N, retract((r(N) :- (false, nl, fail))), L).
q08(L) :- findall(N, retract((d(N,_) :- _ = false)), L).
q09(L) :- findall(N, retract((d(N,_) :- (_ = fail, false))), L).
q10(L) :- findall(N, retract((d(N,_) :- (_, fail))), L).
"""

# Scryer's answers (2026-10-16) except q01, where the engine FAILS
# CLOSED by ruling: reif's if_/3 is lowered into goals the text does not
# have (call/2, must_be/2 and a reified branch: a hidden 3-goal
# conjunction), so its Body has no faithful term and no bound pattern
# takes it.  Scryer: q01 [62, 63, 64] (ISO keeps the if_ goal as written);
# the engine misses 62 and 63, and never deletes 61 by a conjunction
# pattern -- which it used to (q01 [61, 62, 63, 64], q02 [61, 63], q03
# [62], q04 [63] at 0731c12e).
ROWS4 = [
    ("q01", [[64]]),
    ("q02", [[]]),
    ("q03", [[]]),
    ("q04", [[]]),
    ("q05", [[61, 62, 63, 64]]),
    # fail / false spelling, in ORDER
    ("q06", [[1]]),
    ("q07", [[2]]),
    # the atom false as DATA is not a fail/false goal
    ("q08", [[1]]),
    ("q09", [[2]]),
    ("q10", [[]]),
]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("row,want", ROWS4, ids=[r for r, _ in ROWS4])
def test_if_and_spelling_order_rows(native, ans, row, want, suffix):
    mod = native.load(f"l3_conj4_{row}_{suffix[1:]}", SRC4, suffix=suffix)
    assert ans(mod, row) == want


def test_goal_expansion_keeps_the_fail_spelling(native, ans):
    """A body that goal-expands (a literal regex pattern) was rebuilt as a
    fresh Predicate, dropping its clause/2 data; fail read back as false,
    so retract((c(N,_) :- (_, false))) removed c(1) too.  ISO: [2] and
    [1]."""
    mod = native.load("l3_conj_gexp",
                      ":- use_module(library(re), [match/3]).\n"
                      ":- dynamic(c/2).\n"
                      "c(1, S) :- match('a+', S, _), fail.\n"
                      "c(2, S) :- match('a+', S, _), false.\n"
                      "c(3, S) :- match('a+', S, _), fail.\n"
                      "c(4, S) :- match('a+', S, _), false.\n"
                      "q1(L) :- findall(N, retract((c(N,_) :- (_, false))), L).\n"
                      "q2(L) :- findall(N, retract((c(N,_) :- (_, fail))), L).\n")
    assert ans(mod, "q1") == [[2, 4]]
    assert ans(mod, "q2") == [[1, 3]]


def test_a_rule_without_its_source_body_fails_closed(native, ans,
                                                    monkeypatch):
    """A .pl rule's Body is its body AS READ (``Clause.source_body``).  A
    rule that carries none (built outside the ISO front end, or lost on
    the way) gets the term rebuilt from its lowered goals, which is only
    approximate -- so an unbound pattern still takes it, a bound one never
    does: a miss, never a wrong deletion.  (Rebuilt, ``nl, X = 1`` is the
    flat tuple that reads as the cell ``nl(X = 1)``: q3 would match it.)"""
    from clausal.logic.builtins import clause_ops
    mod = native.load("l3_conj_nosrc",
                      ":- dynamic(g/2).\n"
                      "g(1, X) :- nl, X = 1.\n"
                      "g(2, X) :- X = 1, X > 0.\n"
                      "q1(L) :- findall(N, clause(g(N,_), (_, _)), L).\n"
                      "q2(L) :- findall(N, clause(g(N,_), _), L).\n"
                      "q3(L) :- findall(N, clause(g(N,_), nl(_)), L).\n")
    db = vars(mod)["$module"].db
    c1, _c2 = db.row("g", 2).clauses
    assert ans(mod, "q1") == [[1, 2]]
    clause_ops._BUILT_CACHE.clear()
    monkeypatch.setattr(c1, "source_body", None)
    assert ans(mod, "q1") == [[2]]
    assert ans(mod, "q2") == [[1, 2]]
    assert ans(mod, "q3") == [[]]
    clause_ops._BUILT_CACHE.clear()


def test_the_body_is_a_fresh_renaming_on_every_access(native, ans):
    """clause/2 renames the stored body together with the head, every call:
    binding one answer's variables touches neither the next answer nor the
    clause, and the head and body share theirs (ISO 8.8.1).  Scryer:
    r1 [ok], r2 [yes]."""
    mod = native.load("l3_conj_fresh",
                      ":- dynamic(g/1).\n"
                      "g(X) :- X = 1, Y = X, Y > 0.\n"
                      "r1(R) :- clause(g(_), (_, (Y1 = _, _))), Y1 = 7,\n"
                      "         clause(g(_), (_, (Y2 = _, _))), var(Y2),\n"
                      "         Y1 \\== Y2, R = ok.\n"
                      "r2(R) :- clause(g(H), (V = W, _)), H == V, W == 1,\n"
                      "         clause(g(_), (_ = Z, _)), Z == 1, R = yes.\n")
    assert ans(mod, "r1") == ["ok"]
    assert ans(mod, "r2") == ["yes"]


def test_the_source_body_survives_the_bytecode_cache(tmp_path, monkeypatch):
    """The body as read is built by the module's own code, so a load from
    the bytecode cache carries it too: the second import below is a cache
    hit (no source is compiled) and answers exactly as the first."""
    import importlib
    import sys
    from clausal import import_hook as ih
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    (tmp_path / "l3_conj_cache.pl").write_text(
        ":- dynamic(c/1).\n"
        "c(1) :- (nl, fail), lists:member(_, [a]).\n"
        "c(2) :- nl, false.\n"
        "r(L) :- findall(N, retract((c(N) :- ((nl, fail), _))), L).\n"
        "s(L) :- findall(N, retract((c(N) :- (nl, false))), L).\n")

    def load():
        sys.modules.pop("l3_conj_cache", None)
        importlib.invalidate_caches()
        return importlib.import_module("l3_conj_cache")

    def answers(mod):
        out = []
        for name in ("r", "s"):
            v = Var()
            out.append([walk(deref(v)) for _ in call(name, v, module=mod)])
        return out

    first = answers(load())
    assert list(tmp_path.rglob("*.pyc")), "the first load wrote no cache"
    lowered = []
    real = ih.NativePrologLoader.source_to_code
    monkeypatch.setattr(ih.NativePrologLoader, "source_to_code",
                        lambda self, *a, **k: lowered.append(1)
                        or real(self, *a, **k))
    second = answers(load())
    sys.modules.pop("l3_conj_cache", None)
    assert lowered == [], "the second load was not a cache hit"
    assert first == second == [[[1]], [[2]]]


SRC5 = """\
:- use_module(library(lists)).
:- use_module(qh_once).
:- use_module(qh_forall).
:- dynamic(mm/1).
:- meta_predicate(mm(0)).
mm(G) :- call(G).

:- dynamic(c0/1).
c0(1) :- call(false), qh_once:once(fail).
c0(2) :- maplist(false, []), qh_once:once(fail).
c0(3) :- mm(false), qh_once:once(fail).
c0(4) :- qh_once:once(fail), call(false).
c0(5) :- call((false, true)), qh_forall:forall(fail, true).
c0(6) :- lists:member(_, [1]), fail.
c0(7) :- call(fail), qh_once:once(false).
c0(8) :- qh_once:once((nl, X = 1)), X = 1.
c0(9) :- qh_once:once(nl(_)).
c0(10) :- lists:once((X = 1, X > 0)).
c0(11) :- call(\\+ (X = 1, X = 2)).
c0(12) :- call((X = 1 ; X = 2)).
c0(13) :- mm(\\+ (X = 1, X = 2)).
c0(14) :- mm((X = 1 ; X = 2)).
n00(L) :- findall(N, retract((c0(N) :- (call(fail), _))), L).
:- dynamic(c1/1).
c1(1) :- call(false), qh_once:once(fail).
c1(2) :- maplist(false, []), qh_once:once(fail).
c1(3) :- mm(false), qh_once:once(fail).
c1(4) :- qh_once:once(fail), call(false).
c1(5) :- call((false, true)), qh_forall:forall(fail, true).
c1(6) :- lists:member(_, [1]), fail.
c1(7) :- call(fail), qh_once:once(false).
c1(8) :- qh_once:once((nl, X = 1)), X = 1.
c1(9) :- qh_once:once(nl(_)).
c1(10) :- lists:once((X = 1, X > 0)).
c1(11) :- call(\\+ (X = 1, X = 2)).
c1(12) :- call((X = 1 ; X = 2)).
c1(13) :- mm(\\+ (X = 1, X = 2)).
c1(14) :- mm((X = 1 ; X = 2)).
n01(L) :- findall(N, retract((c1(N) :- (maplist(fail, _), _))), L).
:- dynamic(c2/1).
c2(1) :- call(false), qh_once:once(fail).
c2(2) :- maplist(false, []), qh_once:once(fail).
c2(3) :- mm(false), qh_once:once(fail).
c2(4) :- qh_once:once(fail), call(false).
c2(5) :- call((false, true)), qh_forall:forall(fail, true).
c2(6) :- lists:member(_, [1]), fail.
c2(7) :- call(fail), qh_once:once(false).
c2(8) :- qh_once:once((nl, X = 1)), X = 1.
c2(9) :- qh_once:once(nl(_)).
c2(10) :- lists:once((X = 1, X > 0)).
c2(11) :- call(\\+ (X = 1, X = 2)).
c2(12) :- call((X = 1 ; X = 2)).
c2(13) :- mm(\\+ (X = 1, X = 2)).
c2(14) :- mm((X = 1 ; X = 2)).
n02(L) :- findall(N, retract((c2(N) :- (mm(fail), _))), L).
:- dynamic(c3/1).
c3(1) :- call(false), qh_once:once(fail).
c3(2) :- maplist(false, []), qh_once:once(fail).
c3(3) :- mm(false), qh_once:once(fail).
c3(4) :- qh_once:once(fail), call(false).
c3(5) :- call((false, true)), qh_forall:forall(fail, true).
c3(6) :- lists:member(_, [1]), fail.
c3(7) :- call(fail), qh_once:once(false).
c3(8) :- qh_once:once((nl, X = 1)), X = 1.
c3(9) :- qh_once:once(nl(_)).
c3(10) :- lists:once((X = 1, X > 0)).
c3(11) :- call(\\+ (X = 1, X = 2)).
c3(12) :- call((X = 1 ; X = 2)).
c3(13) :- mm(\\+ (X = 1, X = 2)).
c3(14) :- mm((X = 1 ; X = 2)).
n03(L) :- findall(N, retract((c3(N) :- (_, call(fail)))), L).
:- dynamic(c4/1).
c4(1) :- call(false), qh_once:once(fail).
c4(2) :- maplist(false, []), qh_once:once(fail).
c4(3) :- mm(false), qh_once:once(fail).
c4(4) :- qh_once:once(fail), call(false).
c4(5) :- call((false, true)), qh_forall:forall(fail, true).
c4(6) :- lists:member(_, [1]), fail.
c4(7) :- call(fail), qh_once:once(false).
c4(8) :- qh_once:once((nl, X = 1)), X = 1.
c4(9) :- qh_once:once(nl(_)).
c4(10) :- lists:once((X = 1, X > 0)).
c4(11) :- call(\\+ (X = 1, X = 2)).
c4(12) :- call((X = 1 ; X = 2)).
c4(13) :- mm(\\+ (X = 1, X = 2)).
c4(14) :- mm((X = 1 ; X = 2)).
n04(L) :- findall(N, retract((c4(N) :- (call((fail, true)), _))), L).
:- dynamic(c5/1).
c5(1) :- call(false), qh_once:once(fail).
c5(2) :- maplist(false, []), qh_once:once(fail).
c5(3) :- mm(false), qh_once:once(fail).
c5(4) :- qh_once:once(fail), call(false).
c5(5) :- call((false, true)), qh_forall:forall(fail, true).
c5(6) :- lists:member(_, [1]), fail.
c5(7) :- call(fail), qh_once:once(false).
c5(8) :- qh_once:once((nl, X = 1)), X = 1.
c5(9) :- qh_once:once(nl(_)).
c5(10) :- lists:once((X = 1, X > 0)).
c5(11) :- call(\\+ (X = 1, X = 2)).
c5(12) :- call((X = 1 ; X = 2)).
c5(13) :- mm(\\+ (X = 1, X = 2)).
c5(14) :- mm((X = 1 ; X = 2)).
n05(L) :- findall(N, retract((c5(N) :- (member(_, _), fail))), L).
:- dynamic(c6/1).
c6(1) :- call(false), qh_once:once(fail).
c6(2) :- maplist(false, []), qh_once:once(fail).
c6(3) :- mm(false), qh_once:once(fail).
c6(4) :- qh_once:once(fail), call(false).
c6(5) :- call((false, true)), qh_forall:forall(fail, true).
c6(6) :- lists:member(_, [1]), fail.
c6(7) :- call(fail), qh_once:once(false).
c6(8) :- qh_once:once((nl, X = 1)), X = 1.
c6(9) :- qh_once:once(nl(_)).
c6(10) :- lists:once((X = 1, X > 0)).
c6(11) :- call(\\+ (X = 1, X = 2)).
c6(12) :- call((X = 1 ; X = 2)).
c6(13) :- mm(\\+ (X = 1, X = 2)).
c6(14) :- mm((X = 1 ; X = 2)).
n06(L) :- findall(N, retract((c6(N) :- (call(false), _))), L).
:- dynamic(c7/1).
c7(1) :- call(false), qh_once:once(fail).
c7(2) :- maplist(false, []), qh_once:once(fail).
c7(3) :- mm(false), qh_once:once(fail).
c7(4) :- qh_once:once(fail), call(false).
c7(5) :- call((false, true)), qh_forall:forall(fail, true).
c7(6) :- lists:member(_, [1]), fail.
c7(7) :- call(fail), qh_once:once(false).
c7(8) :- qh_once:once((nl, X = 1)), X = 1.
c7(9) :- qh_once:once(nl(_)).
c7(10) :- lists:once((X = 1, X > 0)).
c7(11) :- call(\\+ (X = 1, X = 2)).
c7(12) :- call((X = 1 ; X = 2)).
c7(13) :- mm(\\+ (X = 1, X = 2)).
c7(14) :- mm((X = 1 ; X = 2)).
n07(L) :- findall(N, retract((c7(N) :- (_, once(fail)))), L).
:- dynamic(c8/1).
c8(1) :- call(false), qh_once:once(fail).
c8(2) :- maplist(false, []), qh_once:once(fail).
c8(3) :- mm(false), qh_once:once(fail).
c8(4) :- qh_once:once(fail), call(false).
c8(5) :- call((false, true)), qh_forall:forall(fail, true).
c8(6) :- lists:member(_, [1]), fail.
c8(7) :- call(fail), qh_once:once(false).
c8(8) :- qh_once:once((nl, X = 1)), X = 1.
c8(9) :- qh_once:once(nl(_)).
c8(10) :- lists:once((X = 1, X > 0)).
c8(11) :- call(\\+ (X = 1, X = 2)).
c8(12) :- call((X = 1 ; X = 2)).
c8(13) :- mm(\\+ (X = 1, X = 2)).
c8(14) :- mm((X = 1 ; X = 2)).
n08(L) :- findall(N, retract((c8(N) :- (_, forall(fail, _)))), L).
:- dynamic(c9/1).
c9(1) :- call(false), qh_once:once(fail).
c9(2) :- maplist(false, []), qh_once:once(fail).
c9(3) :- mm(false), qh_once:once(fail).
c9(4) :- qh_once:once(fail), call(false).
c9(5) :- call((false, true)), qh_forall:forall(fail, true).
c9(6) :- lists:member(_, [1]), fail.
c9(7) :- call(fail), qh_once:once(false).
c9(8) :- qh_once:once((nl, X = 1)), X = 1.
c9(9) :- qh_once:once(nl(_)).
c9(10) :- lists:once((X = 1, X > 0)).
c9(11) :- call(\\+ (X = 1, X = 2)).
c9(12) :- call((X = 1 ; X = 2)).
c9(13) :- mm(\\+ (X = 1, X = 2)).
c9(14) :- mm((X = 1 ; X = 2)).
n09(L) :- findall(N, retract((c9(N) :- (once(nl(_)), _))), L).
:- dynamic(c10/1).
c10(1) :- call(false), qh_once:once(fail).
c10(2) :- maplist(false, []), qh_once:once(fail).
c10(3) :- mm(false), qh_once:once(fail).
c10(4) :- qh_once:once(fail), call(false).
c10(5) :- call((false, true)), qh_forall:forall(fail, true).
c10(6) :- lists:member(_, [1]), fail.
c10(7) :- call(fail), qh_once:once(false).
c10(8) :- qh_once:once((nl, X = 1)), X = 1.
c10(9) :- qh_once:once(nl(_)).
c10(10) :- lists:once((X = 1, X > 0)).
c10(11) :- call(\\+ (X = 1, X = 2)).
c10(12) :- call((X = 1 ; X = 2)).
c10(13) :- mm(\\+ (X = 1, X = 2)).
c10(14) :- mm((X = 1 ; X = 2)).
n10(L) :- findall(N, retract((c10(N) :- once(nl(_)))), L).
:- dynamic(c11/1).
c11(1) :- call(false), qh_once:once(fail).
c11(2) :- maplist(false, []), qh_once:once(fail).
c11(3) :- mm(false), qh_once:once(fail).
c11(4) :- qh_once:once(fail), call(false).
c11(5) :- call((false, true)), qh_forall:forall(fail, true).
c11(6) :- lists:member(_, [1]), fail.
c11(7) :- call(fail), qh_once:once(false).
c11(8) :- qh_once:once((nl, X = 1)), X = 1.
c11(9) :- qh_once:once(nl(_)).
c11(10) :- lists:once((X = 1, X > 0)).
c11(11) :- call(\\+ (X = 1, X = 2)).
c11(12) :- call((X = 1 ; X = 2)).
c11(13) :- mm(\\+ (X = 1, X = 2)).
c11(14) :- mm((X = 1 ; X = 2)).
n11(L) :- findall(N, retract((c11(N) :- (qh_once:once((_, _)), _))), L).
:- dynamic(c12/1).
c12(1) :- call(false), qh_once:once(fail).
c12(2) :- maplist(false, []), qh_once:once(fail).
c12(3) :- mm(false), qh_once:once(fail).
c12(4) :- qh_once:once(fail), call(false).
c12(5) :- call((false, true)), qh_forall:forall(fail, true).
c12(6) :- lists:member(_, [1]), fail.
c12(7) :- call(fail), qh_once:once(false).
c12(8) :- qh_once:once((nl, X = 1)), X = 1.
c12(9) :- qh_once:once(nl(_)).
c12(10) :- lists:once((X = 1, X > 0)).
c12(11) :- call(\\+ (X = 1, X = 2)).
c12(12) :- call((X = 1 ; X = 2)).
c12(13) :- mm(\\+ (X = 1, X = 2)).
c12(14) :- mm((X = 1 ; X = 2)).
n12(L) :- findall(N, retract((c12(N) :- qh_once:once(nl(_)))), L).
:- dynamic(c13/1).
c13(1) :- call(false), qh_once:once(fail).
c13(2) :- maplist(false, []), qh_once:once(fail).
c13(3) :- mm(false), qh_once:once(fail).
c13(4) :- qh_once:once(fail), call(false).
c13(5) :- call((false, true)), qh_forall:forall(fail, true).
c13(6) :- lists:member(_, [1]), fail.
c13(7) :- call(fail), qh_once:once(false).
c13(8) :- qh_once:once((nl, X = 1)), X = 1.
c13(9) :- qh_once:once(nl(_)).
c13(10) :- lists:once((X = 1, X > 0)).
c13(11) :- call(\\+ (X = 1, X = 2)).
c13(12) :- call((X = 1 ; X = 2)).
c13(13) :- mm(\\+ (X = 1, X = 2)).
c13(14) :- mm((X = 1 ; X = 2)).
n13(L) :- findall(N, retract((c13(N) :- once((_, _)))), L).
:- dynamic(c14/1).
c14(1) :- call(false), qh_once:once(fail).
c14(2) :- maplist(false, []), qh_once:once(fail).
c14(3) :- mm(false), qh_once:once(fail).
c14(4) :- qh_once:once(fail), call(false).
c14(5) :- call((false, true)), qh_forall:forall(fail, true).
c14(6) :- lists:member(_, [1]), fail.
c14(7) :- call(fail), qh_once:once(false).
c14(8) :- qh_once:once((nl, X = 1)), X = 1.
c14(9) :- qh_once:once(nl(_)).
c14(10) :- lists:once((X = 1, X > 0)).
c14(11) :- call(\\+ (X = 1, X = 2)).
c14(12) :- call((X = 1 ; X = 2)).
c14(13) :- mm(\\+ (X = 1, X = 2)).
c14(14) :- mm((X = 1 ; X = 2)).
n14(L) :- findall(N, retract((c14(N) :- lists:once((_, _)))), L).
:- dynamic(c15/1).
c15(1) :- call(false), qh_once:once(fail).
c15(2) :- maplist(false, []), qh_once:once(fail).
c15(3) :- mm(false), qh_once:once(fail).
c15(4) :- qh_once:once(fail), call(false).
c15(5) :- call((false, true)), qh_forall:forall(fail, true).
c15(6) :- lists:member(_, [1]), fail.
c15(7) :- call(fail), qh_once:once(false).
c15(8) :- qh_once:once((nl, X = 1)), X = 1.
c15(9) :- qh_once:once(nl(_)).
c15(10) :- lists:once((X = 1, X > 0)).
c15(11) :- call(\\+ (X = 1, X = 2)).
c15(12) :- call((X = 1 ; X = 2)).
c15(13) :- mm(\\+ (X = 1, X = 2)).
c15(14) :- mm((X = 1 ; X = 2)).
n15(L) :- findall(N, retract((c15(N) :- call(\\+ (_, _)))), L).
:- dynamic(c16/1).
c16(1) :- call(false), qh_once:once(fail).
c16(2) :- maplist(false, []), qh_once:once(fail).
c16(3) :- mm(false), qh_once:once(fail).
c16(4) :- qh_once:once(fail), call(false).
c16(5) :- call((false, true)), qh_forall:forall(fail, true).
c16(6) :- lists:member(_, [1]), fail.
c16(7) :- call(fail), qh_once:once(false).
c16(8) :- qh_once:once((nl, X = 1)), X = 1.
c16(9) :- qh_once:once(nl(_)).
c16(10) :- lists:once((X = 1, X > 0)).
c16(11) :- call(\\+ (X = 1, X = 2)).
c16(12) :- call((X = 1 ; X = 2)).
c16(13) :- mm(\\+ (X = 1, X = 2)).
c16(14) :- mm((X = 1 ; X = 2)).
n16(L) :- findall(N, retract((c16(N) :- call((_ ; _)))), L).
:- dynamic(c17/1).
c17(1) :- call(false), qh_once:once(fail).
c17(2) :- maplist(false, []), qh_once:once(fail).
c17(3) :- mm(false), qh_once:once(fail).
c17(4) :- qh_once:once(fail), call(false).
c17(5) :- call((false, true)), qh_forall:forall(fail, true).
c17(6) :- lists:member(_, [1]), fail.
c17(7) :- call(fail), qh_once:once(false).
c17(8) :- qh_once:once((nl, X = 1)), X = 1.
c17(9) :- qh_once:once(nl(_)).
c17(10) :- lists:once((X = 1, X > 0)).
c17(11) :- call(\\+ (X = 1, X = 2)).
c17(12) :- call((X = 1 ; X = 2)).
c17(13) :- mm(\\+ (X = 1, X = 2)).
c17(14) :- mm((X = 1 ; X = 2)).
n17(L) :- findall(N, retract((c17(N) :- mm(\\+ (_, _)))), L).
:- dynamic(c18/1).
c18(1) :- call(false), qh_once:once(fail).
c18(2) :- maplist(false, []), qh_once:once(fail).
c18(3) :- mm(false), qh_once:once(fail).
c18(4) :- qh_once:once(fail), call(false).
c18(5) :- call((false, true)), qh_forall:forall(fail, true).
c18(6) :- lists:member(_, [1]), fail.
c18(7) :- call(fail), qh_once:once(false).
c18(8) :- qh_once:once((nl, X = 1)), X = 1.
c18(9) :- qh_once:once(nl(_)).
c18(10) :- lists:once((X = 1, X > 0)).
c18(11) :- call(\\+ (X = 1, X = 2)).
c18(12) :- call((X = 1 ; X = 2)).
c18(13) :- mm(\\+ (X = 1, X = 2)).
c18(14) :- mm((X = 1 ; X = 2)).
n18(L) :- findall(N, retract((c18(N) :- mm((_ ; _)))), L).
:- dynamic(c19/1).
c19(1) :- call(false), qh_once:once(fail).
c19(2) :- maplist(false, []), qh_once:once(fail).
c19(3) :- mm(false), qh_once:once(fail).
c19(4) :- qh_once:once(fail), call(false).
c19(5) :- call((false, true)), qh_forall:forall(fail, true).
c19(6) :- lists:member(_, [1]), fail.
c19(7) :- call(fail), qh_once:once(false).
c19(8) :- qh_once:once((nl, X = 1)), X = 1.
c19(9) :- qh_once:once(nl(_)).
c19(10) :- lists:once((X = 1, X > 0)).
c19(11) :- call(\\+ (X = 1, X = 2)).
c19(12) :- call((X = 1 ; X = 2)).
c19(13) :- mm(\\+ (X = 1, X = 2)).
c19(14) :- mm((X = 1 ; X = 2)).
n19(L) :- findall(N, retract((c19(N) :- (lists:member(_, _), fail))), L).
"""

# The body AS READ keeps what a rebuild from the lowered goals lost: the
# fail/false spelling of each goal wherever it sits (call/1, maplist,
# a user meta argument, a qualified call), a module qualifier (a user
# module's or a builtin library's: lists:member), and \\+ / ; inside a
# call's argument.  Each procedure c<k> holds the 14 clauses; row n<k>
# retracts with pattern k.  Expected: pure unification against the bodies
# as written, in Scryer (2026-10-16) -- its own retract cannot run this
# program (it refuses a module defining once/1).
ROWS5 = [
    ("n00", [7]),
    ("n01", []),
    ("n02", []),
    ("n03", []),
    ("n04", []),
    ("n05", []),
    ("n06", [1]),
    ("n07", []),
    ("n08", []),
    ("n09", []),
    ("n10", []),
    ("n11", [8]),
    ("n12", [9]),
    ("n13", []),
    ("n14", [10]),
    ("n15", [11]),
    ("n16", [12]),
    ("n17", [13]),
    ("n18", [14]),
    ("n19", [6])
]

HELPERS = {
    "qh_once": ":- module(qh_once, [once/1]).\nonce(G) :- call(G).\n"
               ":- end_module(qh_once).\n",
    "qh_forall": ":- module(qh_forall, [forall/2]).\n"
                 "forall(C, A) :- \\+ (C, \\+ A).\n"
                 ":- end_module(qh_forall).\n",
}


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_qualifiers_spellings_and_meta_arguments_are_kept(native, ans,
                                                          suffix):
    import sys
    for name, text in HELPERS.items():
        sys.modules.pop(name, None)     # a helper of the other suffix
        native._names.append(name)      # dropped again at teardown
        (native.tmp / (name + suffix)).write_text(text, encoding="utf-8")
    mod = native.load(f"l3_conj5_{suffix[1:]}", SRC5, suffix=suffix)
    got = {row: ans(mod, row) for row, _ in ROWS5}
    assert got == {row: [want] for row, want in ROWS5}


def test_a_seam_callers_flat_tuple_pattern_is_a_conjunction(tmp_path,
                                                            monkeypatch):
    """A seam caller spells a conjunction pattern as the flat tuple; against
    a .pl procedure it is the right-nested ','/2 term.  ``(_, _, _)``
    deleted BOTH conjunctions below (the 3-tuple unified with
    ``(',', A, B)``) and ``(_, _)`` deleted ``h(X) :- nl(X)`` (a cell).
    ISO: u1 removes the two conjunctions, u2 only the 3-goal one.  The
    same holds INSIDE a goal argument (once/1, findall/3) and under
    ``not``: each 3-tuple matches only the 3-goal conjunction (u3-u5; the
    2-goal one was removed too, since a80165ff)."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    from tests._suffix import SEAM
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    (tmp_path / "xplm_conj.pl").write_text(
        ":- module(xplm_conj, [h1/1, h2/1, h3/1, h4/1, h5/1]).\n"
        ":- dynamic(h1/1).\n:- dynamic(h2/1).\n"
        "h1(X) :- X = 1, X > 0.\nh1(X) :- X = 1, X > 0, X < 5.\n"
        "h1(X) :- nl(X).\nh1(2).\n"
        "h2(X) :- X = 1, X > 0.\nh2(X) :- X = 1, X > 0, X < 5.\n"
        "h2(X) :- nl(X).\nh2(2).\n"
        ":- dynamic(h3/1).\n:- dynamic(h4/1).\n:- dynamic(h5/1).\n"
        "h3(X) :- once((X = 1, X > 0)).\n"
        "h3(X) :- once((X = 1, X > 0, X < 5)).\n"
        "h4(X) :- findall(Y, (Y = 1, Y > 0), X).\n"
        "h4(X) :- findall(Y, (Y = 1, Y > 0, Y < 5), X).\n"
        "h5(X) :- \\+ (X = 1, X > 0).\n"
        "h5(X) :- \\+ (X = 1, X > 0, X < 5).\n")
    p = tmp_path / f"_xseam_conj{SEAM}"
    p.write_text("-allow_singletons\n"
                 "-import_from(xplm_conj, [h1, h2, h3, h4, h5])\n"
                 "u1(D) <- findall(1, retract(':-'(h1(_), (_, _))), D)\n"
                 "u2(D) <- findall(1, retract(':-'(h2(_), (_, _, _))), D)\n"
                 "u3(D) <- findall(1, retract(':-'(h3(_), once((_, _, _)))), D)\n"
                 "u4(D) <- findall(1, retract(':-'(h4(_), "
                 "findall(_, (_, _, _), _))), D)\n"
                 "u5(D) <- findall(1, retract(':-'(h5(_), not (_, _, _))), D)\n")
    m = _load_module("_xseam_conj", str(p))
    for goal, want in (("u1", [1, 1]), ("u2", [1]), ("u3", [1]),
                       ("u4", [1]), ("u5", [1])):
        v = Var()
        assert [_deref_walk(v) for _ in solve((goal, v), m)] == [want], goal


def test_a_seam_procedure_keeps_the_flat_tuple(tmp_path):
    """A seam body is the term the seam builds from the same text: the flat
    tuple, unchanged -- and a Prolog ','/2 pattern still matches it."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    from tests._suffix import SEAM
    p = tmp_path / f"_conj_seam{SEAM}"
    p.write_text("-allow_singletons\n-dynamic(h/1)\n"
                 "h(X) <- (X is 1, X > 0)\nh(2),\n"
                 "t(B) <- clause(h(_), B)\n"
                 "u(L) <- (retract(':-'(h(_), ','(_, _))), findall(Y, h(Y), L))\n")
    m = _load_module("_conj_seam", str(p))
    v = Var()
    bodies = [_deref_walk(v) for _ in solve(("t", v), m)]
    assert type(bodies[0]) is tuple and len(bodies[0]) == 2
    assert type(bodies[0][1]).__name__ == "Gt" and bodies[1] is True
    v = Var()
    assert [_deref_walk(v) for _ in solve(("u", v), m)] == [[2]]


# ── a variable goal is call(X) (ISO 7.6.2) ──────────────────────────────────
#
# Fix round 4.  The body as read kept a variable goal as the bare variable,
# so ``p(X) :- X`` unified with EVERY retract pattern:
# ``retract((p(_) :- foo))`` deleted it.  ISO 7.6.2's body conversion (and
# Scryer) store it as ``call(X)`` at every goal position of a control
# construct -- the body itself and the operands of ``,`` ``;`` ``\+`` -- and
# nowhere else (a meta-argument such as findall's goal keeps the variable).
# Each row runs on its own copy c<k> of the ten clauses: r<k>(M, L), M the
# clauses clause/2 finds, L the clauses retract deletes.  Every expectation
# is Scryer's (2026-10-16).

VG_CLAUSES = [
    "c(1, X) :- X.",
    "c(2, X) :- foo, X.",
    "c(3, X) :- \\+ X.",
    "c(4, X) :- (X ; foo).",
    "c(5, X) :- \\+ \\+ X.",
    "c(6, X) :- call(X).",
    "c(7, X) :- findall(_, X, _).",
    "c(8, _) :- foo, bar.",
    "c(9, X) :- (foo, X), bar.",
    "c(10, X) :- foo, (X ; bar).",
]

# (head pattern, body pattern, Scryer's clause/2 ids == its retract ids)
VG_ROWS = [
    ("c(N, _)", "foo", []),
    ("c(N, _)", "(foo, bar)", [8]),
    ("c(N, _)", "call(_)", [1, 6]),
    ("c(N, _)", "(foo, call(_))", [2]),
    ("c(N, _)", "\\+ call(_)", [3]),
    ("c(N, _)", "\\+ foo", []),
    ("c(N, _)", "(foo ; foo)", []),
    ("c(N, _)", "(call(_) ; foo)", [4]),
    ("c(N, _)", "\\+ \\+ foo", []),
    ("c(N, _)", "\\+ \\+ call(_)", [5]),
    ("c(N, _)", "findall(_, foo, _)", [7]),
    ("c(N, _)", "(foo, foo)", []),
    ("c(N, _)", "(_, _)", [2, 8, 9, 10]),
    ("c(N, _)", "_", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
    ("c(N, _)", "((foo, call(_)), bar)", [9]),
    ("c(N, _)", "((foo, foo), bar)", []),
    ("c(N, foo)", "foo", []),
    ("c(N, foo)", "call(foo)", [1, 6]),
    ("c(N, foo)", "(foo, foo)", []),
    ("c(N, foo)", "\\+ foo", []),
    ("c(N, _)", "(foo, (bar ; bar))", []),
    ("c(N, _)", "(foo, (call(_) ; bar))", [10]),
    ("c(N, X)", "(foo, X)", [2, 8, 10]),
    ("c(N, (a, b))", "(foo, (a, b))", []),
]


def _vg_source() -> str:
    lines = ["foo.", "bar."]
    for k, (head, body, _want) in enumerate(VG_ROWS, 1):
        ck = f"c{k}"
        lines.append(f":- dynamic({ck}/2).")
        lines += [c.replace("c(", ck + "(", 1) for c in VG_CLAUSES]
        h = head.replace("c(", ck + "(", 1)
        lines.append(f"r{k}(M, L) :- findall(N, clause({h}, {body}), M), "
                     f"findall(N, retract(({h} :- {body})), L).")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_variable_goal_is_stored_as_call(native, ans, suffix):
    """All 24 rows, both surfaces: clause/2 and retract agree with Scryer,
    clause for clause and in order."""
    mod = native.load(f"l3_conj_vg_{suffix[1:]}", _vg_source(),
                      suffix=suffix)
    got = {k: ans(mod, f"r{k}", 2)
           for k in range(1, len(VG_ROWS) + 1)}
    want = {k: [(ids, ids)] for k, (_h, _b, ids) in enumerate(VG_ROWS, 1)}
    assert got == want


def test_a_variable_goal_reads_back_as_call(native, ans):
    """The minimal case: clause/2 shows call(X) at every goal position,
    and the bare variable nowhere (Scryer: call(_) ; (foo, call(_)) ;
    \\+call(_) ; (call(_) ; foo) ; findall(_, _, _))."""
    mod = native.load("l3_conj_vg_min",
                      ":- dynamic(p/1).\n"
                      "p(X) :- X.\n"
                      "p(X) :- foo, X.\n"
                      "p(X) :- \\+ X.\n"
                      "p(X) :- (X ; foo).\n"
                      "p(X) :- findall(_, X, _).\n"
                      "foo.\n"
                      "q(L) :- findall(F/A-S, (clause(p(_), B),\n"
                      "        functor(B, F, A), shape(B, S)), L).\n"
                      "shape(B, S) :- B =.. [_|As],\n"
                      "        findall(C, (member(T, As), kind(T, C)), S).\n"
                      "kind(T, v) :- var(T).\n"
                      "kind(T, C) :- nonvar(T), functor(T, C, _).\n"
                      "r(L) :- findall(x, retract((p(_) :- foo)), L).\n")
    assert ans(mod, "q") == [[
        ("-", ("/", "call", 1), ["v"]),
        ("-", ("/", ",", 2), ["foo", "call"]),
        ("-", ("/", "\\+", 1), ["call"]),
        ("-", ("/", ";", 2), ["call", "foo"]),
        ("-", ("/", "findall", 3), ["v", "v", "v"]),
    ]]
    assert ans(mod, "r") == [[]]


# ── constant/1 and other compile-time expansions: the expanded term ─────────
#
# constant(Name) is a term expansion (D8): the clause's body holds the
# VALUE.  The body as read held the lowering's internal PyThunk instead, so
# clause/2 handed an engine object out, ``clause(H, B), call(B)`` raised,
# and retract with the value missed.  The same held for a partial list's
# StarUnpack node and ``undefined``'s LoadName node.

CONST_SRC = """\
:- use_module(library(units), [second]).
:- constant_number_units(one_second, 1, second).
:- constant_value(three, 3).
:- dynamic(c/2).
c(4, X) :- X = constant(one_second).
c(5, X) :- X is constant(three) + 1.
c(6, X) :- X = constant(three).
c(7, X) :- X = 3.
b(L) :- findall(N-B, clause(c(N, _), B), L).
run(L) :- findall(N-X, (clause(c(N, X), B), call(B)), L).
direct(L) :- findall(N-X, c(N, X), L).
r3(L) :- findall(N, retract((c(N, _) :- _ = 3)), L).
r4(L) :- findall(N, retract((c(N, _) :- _ is 3 + 1)), L).
r5(L) :- findall(N, retract((c(N, _) :- _ is 4 + 1)), L).
r6(L) :- findall(N, retract((c(N, _) :- _ is constant(three) + 1)), L).
"""


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_constant_in_a_body_reads_back_as_its_value(native, ans, suffix):
    from clausal.logic.variables import Var
    from clausal.terms import PyThunk
    from clausal.pythonic_ast import nodes
    mod = native.load(f"l3_conj_const_{suffix[1:]}", CONST_SRC,
                      suffix=suffix)
    [bodies] = ans(mod, "b")
    by_n = {n: b for _m, n, b in bodies}
    assert sorted(by_n) == [4, 5, 6, 7]
    assert by_n[5][0] == "is" and by_n[5][2] == ("+", 3, 1)
    assert by_n[6][0] == "=" and by_n[6][2] == 3
    one_second = by_n[4][2]
    assert not isinstance(one_second, (PyThunk, nodes.Node, Var))

    def no_engine_object(t):
        if isinstance(t, (PyThunk, nodes.Node)):
            return False
        return all(no_engine_object(e) for e in t) \
            if type(t) in (list, tuple) else True
    assert all(no_engine_object(b) for b in by_n.values())
    # calling the Body clause/2 hands back answers what the clause does
    assert ans(mod, "run") == ans(mod, "direct")
    assert [(n, x) for _m, n, x in ans(mod, "run")[0]] == [
        (4, one_second), (5, 4), (6, 3), (7, 3)]
    # retract with the VALUE deletes the clause written with the constant
    assert ans(mod, "r5") == [[]]
    assert ans(mod, "r4") == [[5]]
    assert ans(mod, "r3") == [[6, 7]]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_retract_with_the_constant_spelling_deletes_the_clause(native, ans,
                                                               suffix):
    mod = native.load(f"l3_conj_const2_{suffix[1:]}", CONST_SRC,
                      suffix=suffix)
    assert ans(mod, "r6") == [[5]]
    assert [n for _m, n, _b in ans(mod, "b")[0]] == [4, 6, 7]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_partial_list_in_a_body_is_a_list_term(native, ans, suffix):
    """``k([1|T])`` reads back as the partial list, never a StarUnpack node
    (Scryer: t1 [T-k([1|T])], t2 [k([1,2])], t3 [1], t4 [1], t5 [1,2])."""
    mod = native.load(f"l3_conj_plist_{suffix[1:]}",
                      "k(_).\n"
                      ":- dynamic(c/2).\n:- dynamic(d/2).\n"
                      ":- dynamic(e/2).\n"
                      "c(1, T) :- k([1|T]).\nc(2, _) :- k([1, 2]).\n"
                      "d(1, T) :- k([1|T]).\nd(2, _) :- k([1, 2]).\n"
                      "e(1, T) :- k([1|T]).\ne(2, _) :- k([1, 2]).\n"
                      "t1(L) :- findall(x, (clause(c(1, T), B),\n"
                      "         B = k([1|T0]), T0 == T), L).\n"
                      "t2(L) :- findall(B, clause(c(1, [2]), B), L).\n"
                      "t3(L) :- findall(N, retract((c(N, _) :- k([1]))), L).\n"
                      "t4(L) :- findall(N, retract((d(N, _) :- k([1, _, _]))), L).\n"
                      "t5(L) :- findall(N, retract((e(N, _) :- k([1, 2]))), L).\n",
                      suffix=suffix)
    assert ans(mod, "t1") == [["x"]]
    assert ans(mod, "t2") == [[("k", [1, 2])]]
    assert ans(mod, "t3") == [[1]]
    assert ans(mod, "t4") == [[1]]
    assert ans(mod, "t5") == [[1, 2]]


def test_undefined_in_a_body_is_the_truth_value(native, ans):
    """``undefined`` in a data position is the engine's Undefined (D35):
    clause/2 hands back that value, not the LoadName node naming it."""
    from clausal.terms import Undefined
    mod = native.load("l3_conj_undef",
                      ":- dynamic(c/1).\n"
                      "c(X) :- X = undefined.\n"
                      "b(B) :- clause(c(_), B).\n"
                      "r(L) :- findall(X, (clause(c(X), B), call(B)), L).\n")
    [body] = ans(mod, "b")
    assert body[0] == "=" and body[2] is Undefined
    assert ans(mod, "r") == [[Undefined]]


# ── Predicate.source_body is opaque by an explicit marker ───────────────────


def test_an_opaque_field_is_never_visited_or_transformed():
    """``node_class`` skips a field marked ``opaque_field`` -- not because it
    is annotated ``Any`` (an ``Any`` field is still a node).  So the body
    as read, a term that may hold anything, is never walked as a node."""
    from typing import Any
    from clausal.pythonic_ast import nodes
    from clausal.pythonic_ast.node_class import (
        OPAQUE, _field_kind, node_class, opaque_field)

    kinds = {f.name: _field_kind(f)
             for f in nodes.Predicate.__dataclass_fields__.values()}
    assert kinds["source_body"] == "plain"
    assert nodes.Predicate.__dataclass_fields__["source_body"] \
        .metadata[OPAQUE] is True

    @node_class
    class Probe(nodes.Node):
        marked: Any = opaque_field(default=None)
        unmarked: Any = None

    probe_fields = Probe.__dataclass_fields__
    assert _field_kind(probe_fields["marked"]) == "plain"
    assert _field_kind(probe_fields["unmarked"]) == "node"

    inner = nodes.LoadName(name="x")
    pred = nodes.Predicate(head=nodes.LoadName(name="h"), body=True,
                           source_body=inner)
    seen = []
    pred.visit_children(seen.append)
    assert all(v is not inner for v in seen)
    out = pred.transform_children(
        lambda n: nodes.LoadName(name="y") if n is inner else n)
    assert out.source_body is inner
