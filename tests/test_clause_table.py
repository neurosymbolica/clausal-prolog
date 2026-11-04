"""A predicate of many clauses compiles to a clause table
(``clausal/logic/compiler/clause_table.py``), not one Python function per
index bucket: its compile is linear, and its answers are the compiled
predicate's.

* scaling: the first call of a dynamic predicate after 20,000 asserted
  facts compiles no clause, and a 3,000-rule one compiles each rule once;
  a 10,000-fact ``.pl`` file loads compiling no fact.  Counted in compiler
  calls, with generous time bounds (todo/done/dynamic-predicate-first-call-
  after-many-asserts-is-super-linear-2026-11-04.md: 4.5 s at 2,000 facts,
  14 GB at 10,000);
* behaviour across the threshold: the same program and goals answer the
  same, answer for answer and in order, with the table and with the
  one-function compile (the threshold raised out of reach) -- indexing on
  either argument, facts with variables, partial lists and strings, rules
  with cut and errors, the logical update view through assertz/asserta/
  retract while a table predicate runs, clause/2, once/1, freeze/2, and
  which answers are known to be the last.
"""

from __future__ import annotations

import importlib
import itertools
import sys
import time

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
import clausal.logic.compiler.clause_table as clause_table
import clausal.logic.compiler.predicate as predicate_compiler
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve, solve_with_last
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq

N = clause_table.CLAUSE_TABLE_THRESHOLD + 44


def _program(n: int) -> str:
    """t/2 of *n* clauses: plain facts, facts with variables, a partial
    list and a string (kept compiled), rules (one with a cut, one that
    raises), a variable-headed fact; d/1 dynamic, filled by the goals."""
    lines = [":- dynamic(d/1).", ":- dynamic(t/2).",
             "t(X, any) :- atom(X).", "t(k, Z) :- Z = kz."]
    for i in range(n - 12):
        if i % 7 == 3:
            lines.append(f"t({i}, Y) :- Y is {i} * 10.")
        elif i == 200:
            lines.append("t(X, c) :- X == 500, !.")
        else:
            lines.append(f"t({i}, v({i}, W, W)).")
    lines += [
        "t(f(A), A).",
        "t(g(A, B), h(B, A)).",
        "t(l, [1, 2 | _]).",
        't(s, "str").',
        "t(s, [a, b]).",
        "t(err, Y) :- Y is foo + 1.",
        "t(500, late).",
        "t(V, var_head(V)).",
        "t(k, last_k).",
        "t(7, seven).",
    ]
    lines.append("fill(N) :- between(1, N, I), assertz(d(I)), fail.")
    lines.append("fill(_).")
    return "\n".join(lines) + "\n"


GOALS = [
    "findall(X-Y, t(X, Y), R)",
    "findall(Y, t(7, Y), R)",
    "findall(Y, t(500, Y), R)",
    "findall(Y, t(499, Y), R)",
    "findall(Y, t(31, Y), R)",
    "findall(X, t(X, v(42, _, _)), R)",
    "findall(X, t(X, seven), R)",
    "findall(Y, t(f(3), Y), R)",
    "findall(Y, t(g(1, 2), Y), R)",
    "findall(Y, t(k, Y), R)",
    "findall(Y, t(l, Y), R)",
    "findall(Y, t(s, Y), R)",
    "findall(X, t(X, \"str\"), R)",
    "findall(X-Y, t(X, v(X, Y, a)), R0), length(R0, R)",
    "catch(t(err, Y), E, (R = caught(E)))",
    "once(t(X, Y)), R = X-Y",
    "freeze(Y, Z = woke(Y)), t(9, Y), R = Z",
    "( t(500, c) -> R = yes ; R = no )",
    "clause(t(9, Y), B), R = Y-B",
    "findall(B, clause(t(10, _), B), R)",
    # the logical update view, on a predicate of N clauses
    f"fill({N}), findall(X, (d(X), X < 3, Y is X + 10000, assertz(d(Y))), L1),"
    " findall(X, (d(X), X > 9999), L2), R = L1-L2",
    f"fill({N}), findall(X, (d(X), X =< 3, asserta(d(0))), L1),"
    " aggregate_all(count, d(0), C), R = L1-C",
    f"fill({N}), findall(X, (d(X), X =< 3, Y is X + 1, retract(d(Y))), L1),"
    " findall(X, (d(X), X =< 5), L2), R = L1-L2",
    f"fill({N}), findall(X-Y, (d(X), X =< 2, retract(d(Y))), L1),"
    " aggregate_all(count, d(_), C), R = L1-C",
    f"fill({N}), retract(d(5)), findall(X, (d(X), X =< 6), R)",
    f"fill({N}), findall(X, d(X), L), length(L, R)",
]


_GOALS_OF: dict = {}


def _load(tmp_path, name: str, source: str, goals: list[str]):
    """Load *source* as the ``.pl`` module *name*, with ``q<i>(R) :-
    Goal.`` for each of *goals*."""
    source += "".join(f"q{i}(R) :- {g}.\n" for i, g in enumerate(goals))
    (tmp_path / f"{name}.pl").write_text(source)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        mod = importlib.import_module(name)
    finally:
        sys.path.remove(str(tmp_path))
    _GOALS_OF[name] = goals
    return mod


def _answers(mod, goal: str, with_last: bool = False) -> list:
    """The answers of *goal* (one of the goals *mod* was loaded with):
    its ``R`` as written, or the error; with *with_last*, each paired with
    whether it is known to be the last."""
    q = f"q{_GOALS_OF[mod.__name__].index(goal)}"
    r = Var()
    out = []
    runner = solve_with_last if with_last else solve
    try:
        for got in itertools.islice(runner((q, r), mod), 50):
            text = term_writeq(deref(r), local_vars=True)
            out.append((text, got[1]) if with_last else text)
    except LogicException as exc:
        out.append(render_error_term(exc.term))
    return out


LAST_GOALS = ["t(7, Y), R = Y", "t(31, Y), R = Y", "t(f(3), Y), R = Y",
              "t(42, Y), R = Y", "t(k, Y), R = Y"]


@pytest.fixture
def both(tmp_path, monkeypatch, request):
    """``(table module, compiled module)`` of the same program; the
    compiled one loaded with the threshold out of reach."""
    tag = "".join(c if c.isalnum() else "_" for c in request.node.name)
    src = _program(N)
    goals = GOALS + LAST_GOALS
    table = _load(tmp_path, f"ctab_t_{tag}", src, goals)
    with monkeypatch.context() as m:
        m.setattr(clause_table, "CLAUSE_TABLE_THRESHOLD", 10 ** 9)
        compiled = _load(tmp_path, f"ctab_c_{tag}", src, goals)
        # (t/2 is dynamic: a recompile of it here would stay compiled)
        assert not _is_table(compiled, "t", 2)
    assert _is_table(table, "t", 2)
    return table, compiled


def _is_table(mod, functor, arity) -> bool:
    """Is *functor*/*arity*'s dispatch the clause-table driver?"""
    from clausal.logic.solve import resolve_module  # noqa: PLC0415
    db = resolve_module(mod, None, "test").db
    fn = db.get_dispatch(functor, arity)
    driver = clause_table.build_table_dispatch(
        "x", 0, [], [], None, lambda *a: None)
    return getattr(fn, "__code__", None) is driver.__code__


@pytest.mark.parametrize("goal", GOALS)
def test_table_answers_as_the_compiled_predicate(both, goal):
    table, compiled = both
    got = _answers(table, goal)
    want = _answers(compiled, goal)
    assert got == want
    assert got  # every goal has an answer or an error


def test_the_table_knows_its_last_answers(both):
    """Which answers are known to be the last (the top level's full stop):
    the table says so wherever the compiled predicate does on these goals."""
    table, compiled = both
    for goal in LAST_GOALS:
        got = _answers(table, goal, with_last=True)
        assert got == _answers(compiled, goal, with_last=True), goal
        # never a false "last", and here the last answer is known
        assert [last for _, last in got] == [False] * (len(got) - 1) + [True]


SMALL_GOALS = ["findall(X, s(X), L), length(L, R)",
               "assertz(s(x)), findall(X, s(X), L), length(L, R)",
               "retract(s(x)), findall(X, s(X), L), length(L, R)"]


def test_below_the_threshold_nothing_changes(tmp_path, monkeypatch):
    # (the tables of fact predicates, from FACT_TABLE_THRESHOLD facts or
    # once written between calls, are out of reach here: see the tests of
    # both below)
    monkeypatch.setattr(clause_table, "FACT_TABLE_THRESHOLD", 10 ** 9)
    monkeypatch.setattr(clause_table, "RECOMPILES_BEFORE_TABLE", 10 ** 9)
    src = ":- dynamic(s/1).\n" + "".join(
        f"s({i}).\n" for i in range(clause_table.CLAUSE_TABLE_THRESHOLD - 1))
    mod = _load(tmp_path, "ctab_small", src, SMALL_GOALS)
    assert _answers(mod, "findall(X, s(X), L), length(L, R)") == [
        str(clause_table.CLAUSE_TABLE_THRESHOLD - 1)]
    assert not _is_table(mod, "s", 1)
    # one more assert crosses it
    assert _answers(mod, "assertz(s(x)), findall(X, s(X), L), length(L, R)") \
        == [str(clause_table.CLAUSE_TABLE_THRESHOLD)]
    assert _is_table(mod, "s", 1)
    assert _answers(mod, "retract(s(x)), findall(X, s(X), L), length(L, R)") \
        == [str(clause_table.CLAUSE_TABLE_THRESHOLD - 1)]
    assert not _is_table(mod, "s", 1)


# ── scaling ────────────────────────────────────────────────────────────────


@pytest.fixture
def builds(monkeypatch):
    """How many clause functions the compiler builds (each costs about a
    millisecond: building them per clause per bucket was the bug)."""
    count = [0]
    orig = predicate_compiler._build_predicate_trampoline_funcdef

    def counting(*a, **k):
        count[0] += 1
        return orig(*a, **k)

    monkeypatch.setattr(predicate_compiler,
                        "_build_predicate_trampoline_funcdef", counting)
    return count


FACT_GOALS = ["fill(20000), R = ok", "findall(X, f(X, _), L), length(L, R)",
              "f(12345, Y), R = Y", "findall(X, f(X, 777), R)"]


def test_first_call_after_20000_asserted_facts(tmp_path, builds):
    mod = _load(tmp_path, "ctab_facts", (
        ":- dynamic(f/2).\n"
        "fill(N) :- between(1, N, I), assertz(f(I, I)), fail.\n"
        "fill(_).\n"), FACT_GOALS)
    assert _answers(mod, "fill(20000), R = ok") == ["ok"]
    before = builds[0]
    t0 = time.perf_counter()
    assert _answers(mod, "findall(X, f(X, _), L), length(L, R)") == ["20000"]
    elapsed = time.perf_counter() - t0
    # The query itself is compiled; no fact is (it was 2 per fact).
    assert builds[0] - before <= 3
    assert elapsed < 30, elapsed       # ~0.3 s; was minutes and 14 GB
    assert _answers(mod, "f(12345, Y), R = Y") == ["12345"]
    assert _answers(mod, "findall(X, f(X, 777), R)") == ["[777]"]


RULE_GOALS = ["fill(3000), R = ok", "findall(Y, g(_, Y), L), length(L, R)",
              "g(2999, Y), R = Y"]


def test_first_call_after_3000_asserted_rules_compiles_each_once(
        tmp_path, builds):
    mod = _load(tmp_path, "ctab_rules", (
        ":- dynamic(g/2).\n"
        "fill(N) :- between(1, N, I),"
        " assertz((g(I, Y) :- Y is I + 1)), fail.\n"
        "fill(_).\n"), RULE_GOALS)
    assert _answers(mod, "fill(3000), R = ok") == ["ok"]
    before = builds[0]
    assert _answers(mod, "findall(Y, g(_, Y), L), length(L, R)") == ["3000"]
    assert 3000 <= builds[0] - before <= 3010
    assert _answers(mod, "g(2999, Y), R = Y") == ["3000"]


STATIC_GOALS = ["p(9999, Y), R = Y", "findall(X, p(X, _), L), length(L, R)",
                "catch(assertz(p(a, b)), error(E, _), R = E)"]


def test_loading_10000_facts_compiles_no_fact(tmp_path, builds):
    src = "".join(f"p({i}, w{i}).\n" for i in range(10000))
    t0 = time.perf_counter()
    mod = _load(tmp_path, "ctab_static", src, STATIC_GOALS)
    elapsed = time.perf_counter() - t0
    assert builds[0] <= len(STATIC_GOALS)      # the goal predicates
    assert elapsed < 60, elapsed       # ~3 s of reading; was ~55 s
    assert _answers(mod, "p(9999, Y), R = Y") == ["w9999"]
    assert _answers(mod, "findall(X, p(X, _), L), length(L, R)") == ["10000"]
    assert _answers(mod, "catch(assertz(p(a, b)), error(E, _), R = E)") == [
        "permission_error(modify,static_procedure,p/2)"]


# ── constant columns, and facts asserted between calls (2026-11-04) ────────


@pytest.fixture
def arms(monkeypatch):
    """How many clause arms the compiler builds: the clauses of every
    function it builds, summed (each arm costs about 3 ms at arity 8)."""
    count = [0]
    orig = predicate_compiler._build_predicate_trampoline_funcdef

    def counting(functor, arity, clauses, *a, **k):
        count[0] += len(clauses)
        return orig(functor, arity, clauses, *a, **k)

    monkeypatch.setattr(predicate_compiler,
                        "_build_predicate_trampoline_funcdef", counting)
    return count


COLUMN_GOALS = ["q(42, A, B, C, D, E, F, G), R = [A, B, C, D, E, F, G]",
                "findall(I, q(I, 1, 2, 3, 4, 5, 6, 7), L), length(L, R)",
                "findall(I, q(I, 1, 2, 3, 4, 5, 6, 9), R)"]


def test_constant_columns_compile_each_fact_twice_whatever_the_arity(
        tmp_path, arms, monkeypatch):
    """100 facts of arity 8 whose arguments 2..8 are the same in every fact,
    compiled (not a table).  Each of those positions is an index of one
    key, whose one bucket is the whole predicate: it was compiled again per
    position, 9 arms per fact.  Now the fallback serves it: 2 arms per fact
    (the fallback and the fact's first-argument bucket), whatever the
    arity."""
    monkeypatch.setattr(clause_table, "FACT_TABLE_THRESHOLD", 10 ** 9)
    src = "".join(f"q({i}, 1, 2, 3, 4, 5, 6, 7).\n" for i in range(100))
    mod = _load(tmp_path, "ctab_columns", src, COLUMN_GOALS)
    assert not _is_table(mod, "q", 8)
    assert arms[0] <= 2 * 100 + 10, arms[0]     # was 900
    assert _answers(mod, COLUMN_GOALS[0]) == ["[1,2,3,4,5,6,7]"]
    assert _answers(mod, COLUMN_GOALS[1]) == ["100"]
    assert _answers(mod, COLUMN_GOALS[2]) == ["[]"]


def test_a_fact_predicate_loads_as_a_table_from_the_fact_threshold(
        tmp_path, arms):
    """From FACT_TABLE_THRESHOLD facts no fact is compiled (200 facts of
    arity 8 compiled 1,800 clause arms, 7 s; then 400, 2 s)."""
    n = 200
    src = "".join(f"q({i}, 1, 2, 3, 4, 5, 6, 7).\n" for i in range(n))
    mod = _load(tmp_path, "ctab_facts_small", src, COLUMN_GOALS)
    assert _is_table(mod, "q", 8)
    assert arms[0] <= 10, arms[0]               # the goal predicates
    assert _answers(mod, COLUMN_GOALS[0]) == ["[1,2,3,4,5,6,7]"]
    assert _answers(mod, COLUMN_GOALS[1]) == [str(n)]
    assert _answers(mod, COLUMN_GOALS[2]) == ["[]"]
    below = clause_table.FACT_TABLE_THRESHOLD - 1
    src = "".join(f"r({i}, 1).\n" for i in range(below))
    mod = _load(tmp_path, "ctab_facts_below", src, ["findall(I, r(I, 1), R)"])
    assert not _is_table(mod, "r", 2)


def _row(mod, functor, arity):
    from clausal.logic.solve import resolve_module  # noqa: PLC0415
    return resolve_module(mod, None, "test").db.row(functor, arity)


INTERLEAVE_GOALS = [
    "fill(200), R = ok",
    "findall(I, q(I, _, _, _, _, _, _, _), L), length(L, R)",
    "q(150, A, _, _, _, _, _, H), R = A-H",
]


def test_facts_asserted_between_calls_are_not_recompiled_each_time(
        tmp_path, arms):
    """Each assertz of a fact followed by a call recompiled the whole
    predicate at the call: O(n^2) compiled clauses for n asserts (50 facts
    of arity 8 took 30 s).  From its second recompile after a write a fact
    predicate is a clause table, and an assertz adds to the table in
    place."""
    mod = _load(tmp_path, "ctab_interleave", (
        ":- dynamic(q/8).\n"
        "q(0, 1, 2, 3, 4, 5, 6, 7).\n"
        "fill(N) :- between(1, N, I), assertz(q(I, 1, 2, 3, 4, 5, 6, 7)),"
        " q(I, _, _, _, _, _, _, _), fail.\n"
        "fill(_).\n"), INTERLEAVE_GOALS)
    before = arms[0]
    assert _answers(mod, INTERLEAVE_GOALS[0]) == ["ok"]
    # Two recompiles through the code generator (of 1 and 2 clauses), and
    # the goal itself; was 200 recompiles, about 180,000 arms.
    assert arms[0] - before <= 20, arms[0] - before
    row = _row(mod, "q", 8)
    assert row.recompiles_after_write == clause_table.RECOMPILES_BEFORE_TABLE
    assert _is_table(mod, "q", 8)
    assert _answers(mod, INTERLEAVE_GOALS[1]) == ["201"]
    assert _answers(mod, INTERLEAVE_GOALS[2]) == ["1-7"]


UPDATE_GOALS = [
    "assertz(p(4)), findall(X, p(X), R)",
    "assertz(p(5)), findall(X, p(X), R)",
    "findall(X, (p(X), assertz(p(9))), R)",
    "findall(X, p(X), R)",
    "findall(x, (p(9), assertz(p(9))), L), length(L, R)",
    "p(X), R = X",
    "asserta(p(0)), findall(X, p(X), L), length(L, R)",
    "once(retract(p(9))), findall(X, p(X), L), length(L, R)",
]


def test_a_fact_appended_in_place_keeps_the_logical_update_view(
        tmp_path, builds):
    mod = _load(tmp_path, "ctab_update", (
        ":- dynamic(p/1).\np(1).\np(2).\np(3).\n"), UPDATE_GOALS)
    assert _answers(mod, UPDATE_GOALS[0]) == ["[1,2,3,4]"]
    assert not _is_table(mod, "p", 1)        # the first recompile: compiled
    assert _answers(mod, UPDATE_GOALS[1]) == ["[1,2,3,4,5]"]
    assert _is_table(mod, "p", 1)
    recompiles = _row(mod, "p", 1).recompiles_after_write
    before = builds[0]
    # A call running while facts are appended sees the clauses it began
    # with, through the full scan and through an index bucket that grows.
    assert _answers(mod, UPDATE_GOALS[2]) == ["[1,2,3,4,5]"]
    assert _answers(mod, UPDATE_GOALS[3]) == ["[1,2,3,4,5,9,9,9,9,9]"]
    assert _answers(mod, UPDATE_GOALS[4]) == ["5"]
    # The last answer is known as the last one, over the grown table.
    got = _answers(mod, UPDATE_GOALS[5], with_last=True)
    assert [x for x, _ in got] == ["1", "2", "3", "4", "5"] + ["9"] * 10
    assert [last for _, last in got] == [False] * 14 + [True]
    # Nothing was recompiled for those 10 asserts (the goals are compiled).
    assert _row(mod, "p", 1).recompiles_after_write == recompiles
    assert builds[0] - before <= len(UPDATE_GOALS)
    # asserta and retract still invalidate, and the recompile reads them.
    assert _answers(mod, UPDATE_GOALS[6]) == ["16"]
    assert _answers(mod, UPDATE_GOALS[7]) == ["15"]
    assert _row(mod, "p", 1).recompiles_after_write == recompiles + 2


LAST_RULE_GOALS = ["findall(X, r(X), R)",
                   "assertz(r(new)), findall(X, r(X), R)",
                   "r(X), R = X"]


def test_no_append_after_a_compiled_last_clause(tmp_path, monkeypatch):
    """A table whose last clause is compiled (a rule) gave that clause's
    answers as FINAL: a fact after it is recompiled, not appended, so they
    are not FINAL any more."""
    monkeypatch.setattr(clause_table, "CLAUSE_TABLE_THRESHOLD", 4)
    mod = _load(tmp_path, "ctab_last_rule", (
        ":- dynamic(r/1).\nr(a).\nr(b).\nr(c).\nr(X) :- X = rule.\n"),
        LAST_RULE_GOALS)
    assert _answers(mod, LAST_RULE_GOALS[0]) == ["[a,b,c,rule]"]
    assert _is_table(mod, "r", 1)
    recompiles = _row(mod, "r", 1).recompiles_after_write
    assert _answers(mod, LAST_RULE_GOALS[1]) == ["[a,b,c,rule,new]"]
    assert _row(mod, "r", 1).recompiles_after_write == recompiles + 1
    got = _answers(mod, LAST_RULE_GOALS[2], with_last=True)
    assert got == [("a", False), ("b", False), ("c", False),
                   ("rule", False), ("new", True)]
