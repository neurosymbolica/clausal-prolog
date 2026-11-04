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


def test_below_the_threshold_nothing_changes(tmp_path):
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
