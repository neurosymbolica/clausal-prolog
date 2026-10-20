"""A tabled answer row that leaves a variable unbound is renamed apart on
every replay, as a stored clause is: each replay gets fresh variables, and a
binding made through one replay is never seen by the next (ISO/XSB variant
tabling).  It used to be shared: ``freeze_args`` is a deref-walk, so the row
kept the derivation's own ``Var`` objects, and every replay unified the
caller's arguments with those same objects
(todo/done/tabled-answer-rows-share-their-unbound-variables-2026-10-16.md).

The row's INTERNAL sharing is kept: ``v(f(X, X))`` replays as ``f(A, A)``.
An answer that carries a constraint is still handed over live (the A12
limitation: the table cannot store the constraint), so its first delivery
keeps the constraint and a replay from the completed table does not."""
from __future__ import annotations

import pytest

from clausal.logic.variables import is_var
from clausal.terms import ConcreteSeg, SegList, VarSeg


def _parts(term):
    """The sub-terms of a list, a cell or a partial list (``[1|T]`` walks to
    a ``SegList``: its elements, then its open tail)."""
    if isinstance(term, SegList):
        out = []
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                out.extend(seg.elements)
            elif isinstance(seg, VarSeg):
                out.append(seg.var)
            else:
                out.append(seg)
        return out
    return list(term)


def shape(term):
    """A term with every unbound variable shown as ``"_"``; a partial list
    as ``("|", elements..., tail)``."""
    if is_var(term):
        return "_"
    if isinstance(term, SegList):
        return ("|", *(shape(e) for e in _parts(term)))
    if isinstance(term, list):
        return [shape(e) for e in term]
    if isinstance(term, tuple):
        return tuple(shape(e) for e in term)
    return term


def variables(term, out=None):
    """The distinct unbound variables of *term*, in order (identity)."""
    if out is None:
        out = []
    if is_var(term):
        if all(term is not v for v in out):
            out.append(term)
    elif isinstance(term, (list, tuple, SegList)):
        for e in _parts(term):
            variables(e, out)
    return out


V = """\
:- table(v/1).
v(_).
v(1).
rebinds(L) :- v(X), var(X), X = b, findall(Y, v(Y), L).
pairs(L) :- findall(X-Y, (v(X), v(Y)), L).
"""


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_binding_through_one_replay_is_not_seen_by_the_next(native, ans, suffix):
    """The todo's first repro: L = [_, 1], not [b, 1]."""
    mod = native.load("l3_rows_rebinds" + suffix[1:], V, suffix=suffix)
    assert [shape(l) for l in ans(mod, "rebinds")] == [["_", 1]]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_two_calls_of_one_table_pair_fresh_variables(native, ans, suffix):
    """The todo's second repro: [_A-_B, _C-1, 1-_D, 1-1], four distinct
    variables -- not [_A-_A, _B-1, 1-1, 1-1]."""
    mod = native.load("l3_rows_pairs" + suffix[1:], V, suffix=suffix)
    [l] = ans(mod, "pairs")
    assert shape(l) == [("-", "_", "_"), ("-", "_", 1), ("-", 1, "_"), ("-", 1, 1)]
    assert len(variables(l)) == 4


def test_the_same_from_python(native):
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    mod = native.load("l3_rows_pairs_py", V)
    x, y = Var(), Var()
    rows = [(r["X"], r["Y"]) for r in query((",", ("v", x), ("v", y)),
                                             {"X": x, "Y": y}, mod)]
    assert shape(rows) == [("_", "_"), ("_", 1), (1, "_"), (1, 1)]
    # An unbound answer is reported as the query's own variable, so X and
    # Y recur across the rows; within the first row they are two.
    assert rows[0][0] is not rows[0][1]


REPEATED = """\
:- table(w/1).
w(f(X, X)).
w(g(X, Y, X)).
shares(A, B) :- w(f(A, B)).
twice(T1, T2) :- w(T1), w(T2).
all(L) :- findall(T, w(T), L).
"""


def test_a_rows_internal_sharing_is_kept_within_one_replay(native, ans):
    mod = native.load("l3_rows_repeated", REPEATED)
    [(a, b)] = ans(mod, "shares", 2)
    assert is_var(a) and a is b
    [l] = ans(mod, "all")
    assert shape(l) == [("f", "_", "_"), ("g", "_", "_", "_")]
    f, g = l
    assert f[1] is f[2]
    assert g[1] is g[3] and g[1] is not g[2]
    assert len(variables(l)) == 3


def test_two_replays_of_one_row_do_not_share(native, ans):
    mod = native.load("l3_rows_twice", REPEATED)
    rows = ans(mod, "twice", 2)
    assert shape(rows) == [
        (("f", "_", "_"), ("f", "_", "_")),
        (("f", "_", "_"), ("g", "_", "_", "_")),
        (("g", "_", "_", "_"), ("f", "_", "_")),
        (("g", "_", "_", "_"), ("g", "_", "_", "_")),
    ]
    for t1, t2 in rows:
        assert not set(map(id, variables(t1))) & set(map(id, variables(t2)))


STRUCTURED = """\
:- table(s/1).
s([X, "ab", f(X, Y), [1|T]]).
s(p("xyz", Z)).
s([]).
later(L) :- s(A), A = [1, _, _, _], findall(B, s(B), L).
"""


def test_rows_holding_lists_compounds_and_strings(native, ans):
    """A variable inside a list, a compound, a partial list's tail: fresh
    per replay, and the ground parts (a string, []) come back as they are."""
    mod = native.load("l3_rows_structured", STRUCTURED)
    [l] = ans(mod, "later")
    assert shape(l) == [["_", ("$chars", "ab"), ("f", "_", "_"), ("|", 1, "_")],
                        ("p", ("$chars", "xyz"), "_"), []]
    first = l[0]
    assert first[0] is first[2][1]                  # X shared inside the row
    assert len(variables(first)) == 3               # X, Y, T


CONSTRAINED = """\
:- table(cd/1).
cd(X) :- dif(X, a).
cd(1).
complete :- findall(_, cd(_), _).
live(X) :- cd(X), X = a.
after(L) :- complete, cd(X), X = b, findall(Y, cd(Y), L).
"""


def test_a_constrained_answer_is_handed_over_live_and_replayed_fresh(native, ans):
    """The A12 limitation stands: the FIRST delivery of a constrained
    answer carries its constraint (``live`` fails), while a replay from the
    completed table does not.  What changes: the replay's variable is a
    fresh one, so binding it (``X = b``) leaves the next replay unbound."""
    mod = native.load("l3_rows_constrained", CONSTRAINED)
    assert ans(mod, "live") == []
    assert [shape(l) for l in ans(mod, "after")] == [["_", 1]]


WFS = """\
:- table(u/0).
:- table(w/0).
u :- \\+ w.
w :- \\+ u.
:- table(p/1).
p(_) :- u.
p(1).
later(L) :- p(X), var(X), X = 2, findall(Y, p(Y), L).
"""


def test_a_conditional_answers_variable_is_fresh_per_replay(native, ans):
    """A WFS-undefined answer (conditional on the u/w negation cycle) is a
    row like any other: replayed with a fresh variable, its condition kept."""
    from clausal.logic.solve import query_wfs
    from clausal.logic.variables import Var
    from clausal.terms import Undefined
    mod = native.load("l3_rows_wfs", WFS)
    x = Var()
    rows = [(shape(r["X"]), r["_truth"]) for r in query_wfs(("p", x), {"X": x}, mod)]
    assert len(rows) == 2 and ("_", Undefined) in rows and (1, True) in rows
    assert [shape(l) for l in ans(mod, "later")] == [["_", 1]]


def test_a_stored_row_holds_no_derivation_variable():
    """At the table: ``add_answer`` keeps a ground row as given (an interned
    cell stays the object it was) and stores a non-ground row renamed apart,
    so a later binding of the derivation's variable never reaches it; and
    every ``row(i)`` of a non-ground row is a fresh copy."""
    from clausal.logic.tabling import TableEntry
    from clausal.logic.variables import Trail, Var, deref, unify
    e = TableEntry()
    cell = ("point", 1, 2)
    x = Var()
    assert e.add_answer((cell,)) == 0
    assert e.add_answer((("f", x, x), 3)) == 1
    assert e.answers[0][0] is cell
    assert e.row(0) is e.answers[0]
    stored = e.answers[1]
    assert is_var(stored[0][1]) and stored[0][1] is stored[0][2]
    assert stored[0][1] is not x
    trail = Trail()
    assert unify(x, 7, trail)
    assert is_var(deref(stored[0][1]))
    r1, r2 = e.row(1), e.row(1)
    assert shape(r1) == shape(r2) == (("f", "_", "_"), 3)
    assert r1[0][1] is r1[0][2]
    assert r1[0][1] is not r2[0][1] and r1[0][1] is not stored[0][1]


CHAIN = """\
:- table(path/2).
edge(X, Y) :- between(1, {n}, X), Y is X + 1.
path(X, Y) :- edge(X, Y).
path(X, Y) :- path(X, Z), edge(Z, Y).
"""


def test_a_left_recursive_closure_reads_rows_appended_mid_pass(native, ans, monkeypatch):
    """The consumer of an evaluating ancestor's table hands over the rows
    the ancestor's pass appends WHILE it is iterating (SLG: every answer
    found so far), so an N-chain left-recursive closure is derived in one
    pass plus a confirming one: 2N add_answer calls.  A loop over a
    snapshot of the length read one level per pass: O(N) passes, 31,624
    calls for N = 250 (the review of the fresh-row fix)."""
    from clausal.logic import tabling
    n = 250
    calls = 0
    original = tabling.TableEntry.add_answer

    def counting(self, answer, delay_set=None):
        nonlocal calls
        calls += 1
        return original(self, answer, delay_set)

    monkeypatch.setattr(tabling.TableEntry, "add_answer", counting)
    mod = native.load("l3_rows_chain", CHAIN.format(n=n))
    assert ans(mod, "path", 2, 1) == list(range(2, n + 2))
    assert calls <= 3 * n, calls
