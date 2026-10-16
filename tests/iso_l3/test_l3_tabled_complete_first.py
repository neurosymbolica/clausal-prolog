"""D68 (operator ruling 2026-10-16, option B): a tabled call that does not
depend on a table still being computed COMPLETES its table before it hands
back its first answer (XSB's local scheduling), and then answers in table
order.

Two things follow.  A cut or commit over the first answer of a fresh table
prunes a complete table, so it runs (it raised permission_error(cut,
incomplete_table, F/N) before).  And a second call of the same table in the
first call's continuation no longer joins against a partial table: it used
to lose answers silently (todo/done/tabled-findall-over-two-calls-loses-
pairs-2026-10-16.md).  Recursive and mutually recursive calls inside an SCC
still see incomplete tables, as SLG needs; a cut over one of those is the
refusal pinned in test_l3_cut_tabling.py."""
from __future__ import annotations

import pytest

NINE = [("-", x, y) for x in (1, 2, 3) for y in (1, 2, 3)]

PAIRS = """\
:- table(t/1).
t(1). t(2). t(3).
pairs(L) :- findall(X-Y, (t(X), t(Y)), L).
:- table(tp/1).
tp(L) :- findall(X-Y, (t(X), t(Y)), L).
"""


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_findall_over_two_calls_of_one_table_gives_every_pair(native, ans, suffix):
    """The todo's repro: 9 pairs, as without tabling.  It gave 6 (1-2, 1-3
    and 2-3 missing): the inner t(Y) consumed t/1's table while the outer
    t(X) was still filling it."""
    mod = native.load("l3_cf_pairs" + suffix[1:], PAIRS, suffix=suffix)
    assert ans(mod, "pairs") == [NINE]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_the_same_findall_inside_a_tabled_predicate_has_one_answer(native, ans, suffix):
    """Inside another table's evaluation t/1 is a fresh call that does not
    depend on tp/1, so it completes first too.  Before D68 tp/1's fixpoint
    tabled BOTH the 6-pair list (first pass, t/1 incomplete) and the 9-pair
    list (second pass): two answers for a deterministic predicate."""
    mod = native.load("l3_cf_tp" + suffix[1:], PAIRS, suffix=suffix)
    assert ans(mod, "tp") == [NINE]


SEAM_PAIRS = """\
-table(t/1)

t(1),
t(2),
t(3),

pairs(L) <- findall((X, Y), (t(X), t(Y)), L)
"""


def test_findall_over_two_calls_of_one_table_in_the_seam(native, ans):
    mod = native.load("l3_cf_pairs_seam", SEAM_PAIRS, suffix=".seam")
    [got] = ans(mod, "pairs")
    assert len(got) == 9
    assert sorted(tuple(p) for p in got) == [(x, y) for x in (1, 2, 3)
                                             for y in (1, 2, 3)]


def test_findall_over_two_calls_from_python(native):
    """solve()/query() from Python: the same root-call path."""
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    mod = native.load("l3_cf_pairs_py", PAIRS)
    x, y = Var(), Var()
    rows = [(r["X"], r["Y"]) for r in query((",", ("t", x), ("t", y)),
                                             {"X": x, "Y": y}, mod)]
    assert rows == [(a, b) for a in (1, 2, 3) for b in (1, 2, 3)]


# A cut / commit over the FIRST answer of a fresh, non-recursive table.  The
# static XSB rule (D61 Q1) refuses one whose scope holds the tabled call
# directly, so these reach t/1 through the untabled tq/1, as a program that
# loads would.
COMMIT = """\
:- table(t/1).
t(2). t(1). t(3).
tq(X) :- t(X).
c(X) :- tq(X), !.
i(X) :- ( tq(X) -> true ; X = none ).
o(X) :- once(tq(X)).
:- table(tc/1).
tc(X) :- c(X).
:- table(ti/1).
ti(X) :- i(X).
"""


def _t_table(mod):
    [entry] = [e for (f, _a, _k), e in mod.__dict__["$module"].db.table_store.items()
               if f == "t"]
    return entry


@pytest.mark.parametrize("name", ["c", "i", "o"])
def test_a_commit_over_a_fresh_tables_first_answer_runs(native, ans, name):
    """The first answer in table order (t(2), the first clause), and the
    table is complete afterwards, with every answer in it."""
    mod = native.load("l3_cf_commit_" + name, COMMIT)
    assert ans(mod, name) == [2]
    entry = _t_table(mod)
    assert entry.status == "complete"
    assert [a[0] for a in entry.answers] == [2, 1, 3]


@pytest.mark.parametrize("name", ["tc", "ti"])
def test_a_commit_inside_another_tables_evaluation_runs_when_it_does_not_recurse(native, ans, name):
    """tc/1 and ti/1 are tabled; the commit over t/1 runs inside their
    evaluation, but t/1 does not depend on them, so it completes first and
    the commit is allowed."""
    mod = native.load("l3_cf_commit_in_" + name, COMMIT)
    assert ans(mod, name) == [2]
    assert _t_table(mod).status == "complete"


def test_a_commit_from_python_on_a_held_iterator_sees_a_complete_table(native):
    """Taking the first answer from Python and stopping (once-style) leaves
    the table complete, not dropped half-built."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    mod = native.load("l3_cf_first_py", COMMIT)
    x = Var()
    it = iter(call("t", x, module=mod))
    next(it)
    assert deref(x) == 2
    assert _t_table(mod).status == "complete"


# SLG semantics where tables really are incomplete: unchanged.
RECURSIVE = """\
:- table(path/2).
e(a, b). e(b, c). e(c, a).
path(X, Y) :- path(X, Z), e(Z, Y).
path(X, Y) :- e(X, Y).
:- table(rpath/2).
rpath(X, Y) :- e(X, Y).
rpath(X, Y) :- e(X, Z), rpath(Z, Y).
:- table(even/1).
:- table(odd/1).
even(0).
even(N) :- odd(M), M < 6, N is M + 1.
odd(N) :- even(M), M < 6, N is M + 1.
all(L) :- findall(X-Y, path(X, Y), L).
"""


def test_left_and_right_recursion_terminate_with_every_answer(native, ans):
    mod = native.load("l3_cf_rec", RECURSIVE)
    assert sorted(ans(mod, "path", 2, "a")) == ["a", "b", "c"]
    assert sorted(ans(mod, "rpath", 2, "a")) == ["a", "b", "c"]
    assert len(ans(mod, "all")[0]) == 9


def test_mutual_recursion_completes_with_every_answer(native, ans):
    mod = native.load("l3_cf_mutual", RECURSIVE)
    assert sorted(ans(mod, "even")) == [0, 2, 4, 6]
    assert sorted(ans(mod, "odd")) == [1, 3, 5]


# The one exception to complete-first: an answer that carries a constraint
# (an attributed variable) is still handed over as it is derived, since the
# table cannot store the constraint (todo/audit-2026-07-05/investigate-A12-
# tabling-answer-constraints.md).  It comes from an incomplete table, so a
# cut over it raises, and the message says why.
CONSTRAINED = """\
:- table(cd/1).
cd(X) :- dif(X, 1).
cq(X) :- cd(X).
first(X) :- once(cq(X)).
keeps(X) :- cq(X), X = 2.
"""


def test_a_constrained_answer_keeps_its_constraint(native, ans):
    mod = native.load("l3_cf_constrained", CONSTRAINED)
    assert ans(mod, "keeps") == [2]
    from clausal.logic.solve import call
    mod = native.load("l3_cf_constrained_neg", CONSTRAINED + "bad :- cq(X), X = 1.\n")
    assert list(call("bad", module=mod)) == []


def test_a_cut_over_a_constrained_answer_raises_and_says_why(native):
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    mod = native.load("l3_cf_constrained_cut", CONSTRAINED)
    with pytest.raises(LogicException) as e:
        list(call("first", Var(), module=mod))
    msg = str(e.value)
    assert "permission_error(cut,incomplete_table,cd/1)" in msg
    assert "its answers carry constraints (dif/2, CLP, freeze/2)" in msg


# A leader whose pass read only complete tables runs no confirming pass (D68
# review F3).  The one body that could tell: one that reads its OWN side
# effects.  Ruled here: the single pass stands -- the answers are the
# untabled program's, and the assertz runs once per answer (a second pass
# would add 11 and 12 and assert both again).  Tabling with side effects is
# undefined in XSB too.
SIDE_EFFECT = """\
:- dynamic(seen/1).
:- table(p/1).
p(X) :- seen(X).
p(X) :- member(X, [1, 2]), Y is X + 10, assertz(seen(Y)).
untabled(X) :- seen(X).
untabled(X) :- member(X, [1, 2]), Y is X + 10, assertz(seen(Y)).
count(N) :- findall(x, seen(_), L), length(L, N).
"""


def test_a_side_effect_runs_once_and_is_not_reread(native, ans):
    mod = native.load("l3_cf_side_effect", SIDE_EFFECT)
    assert ans(mod, "p") == [1, 2]
    assert ans(mod, "count") == [2]
    mod = native.load("l3_cf_side_effect_untabled", SIDE_EFFECT)
    assert ans(mod, "untabled") == [1, 2]

