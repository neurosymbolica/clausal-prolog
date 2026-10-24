"""Cyclic (rational-tree) and very deep terms, row by row against Scryer.

ISO 7.3.2 lets ``=/2`` build a cyclic term (``X = f(X)``: no occurs check),
and Scryer then answers every later question about it as a question about a
rational tree -- ``X = f(X), X = f(f(X))`` succeeds, two cyclic terms are
``==`` when they are one tree, ``compare/3`` orders them, ``copy_term/2``
copies the cycle, ``writeq/1`` prints ``f(...)``.  Before 2026-10-24 every
one of those walks in this engine was a recursive descent with a depth cap
and raised a raw Python ``RecursionError`` where Scryer answers; see
todo/done/deep-and-cyclic-terms-overflow-the-recursive-walkers-2026-10-22.md.

Every row here is one ``.pl`` clause run under BOTH engines from the same
text: the engine tests (``run_clausal``-free: a native ``.pl`` load) assert
the expected column, the oracle tests assert Scryer prints the same column.
``yn/2`` reifies a goal as ``yes``/``no``/``error(E)`` so a raw Python
exception shows up as a wrong ANSWER, never as a crashed test.

The deep rows (a 100k-element list, a 100k-nested ``f(f(...))``) are the
other half of the same walkers: an iterative walk, not a RecursionError.
``assertz`` of such a term is engine-only (Scryer overflows its stack there),
and ``assertz`` of a CYCLIC term is engine-only too: Scryer panics, this
engine raises the ISO ``resource_error`` the test pins.
"""
from __future__ import annotations

import contextlib
import io
import os
import re

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Var
from clausal.terms import term_writeq

from tests._oracles import run_scryer

DEEP_N = 100_000

# (row name, the clause body, the expected answer both engines give)
# A yn-row binds R; an out-row prints.
_PRELUDE = """\
:- use_module(library(lists)).

same(A, A).

yn(G, R) :- ( catch(G, E, R = error(E)) -> ( var(R) -> R = yes ; true ) ; R = no ).

mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
nest(0, T, T).
nest(N, T, f(R)) :- N > 0, N1 is N-1, nest(N1, T, R).
"""

UNIFY_ROWS = [
    ("u1", "yn((X = f(X)), R)", "yes"),
    ("u2", "yn((X = f(X), X = f(f(X))), R)", "yes"),
    ("u3", "yn((X = f(X), Y = f(Y), X = Y), R)", "yes"),
    ("u4", "yn((X = f(a, X), Y = f(a, Y), X = Y), R)", "yes"),
    ("u5", "yn((X = f(X, a), Y = f(Y, b), X = Y), R)", "no"),
    ("u6", "yn((X = f(X), Y = g(Y), X = Y), R)", "no"),
    ("u7", "yn((X = f(X), Y = f(Y), same(X, Y)), R)", "yes"),
    ("u8", "yn((X = f(X), Y = f(Y), member(X, [Y])), R)", "yes"),
    ("u9", "yn((X = [1|X], Y = [1|Y], X = Y), R)", "yes"),
    ("u10", "yn((X = [1|X], Y = [1,1|Y], X = Y), R)", "yes"),
    ("u11", "yn((X = [1,2|X], Y = [1|Z], Z = [2|Y], X = Y), R)", "yes"),
    ("u12", "yn((X = f(X), Y = f(Z), Z = f(Y), X = Y), R)", "yes"),
    ("u13", "yn((X = f(X), Y = f(a), X = Y), R)", "no"),
    ("u14", "yn((X = f(X), Y = f(Y), unify_with_occurs_check(X, Y)), R)", "yes"),
    ("u15", "yn((X = f(X), Y = f(Y), X \\= Y), R)", "no"),
]

IDENTITY_ROWS = [
    ("e1", "yn((X = f(X), Y = f(Y), X == Y), R)", "yes"),
    ("e2", "yn((X = s(X), Y = s(s(Y)), X == Y), R)", "yes"),
    ("e3", "yn((X = f(X), Y = g(Y), X == Y), R)", "no"),
    ("e4", "yn((X = f(X, _A), Y = f(Y, _B), X == Y), R)", "no"),
    ("e5", "yn((X = [1|X], Y = [1|Y], X == Y), R)", "yes"),
    ("e6", "yn((X = [1|X], Y = [1,1|Y], X == Y), R)", "yes"),
    ("e7", "yn((X = f(X), Y = f(Y), X \\== Y), R)", "no"),
    ("e8", "yn((X = f(X), copy_term(X, Y), X == Y), R)", "yes"),
    ("e9", "yn((X = [1,2|X], Y = [1|Z], Z = [2|Y], X == Y), R)", "yes"),
]

COMPARE_ROWS = [
    ("c1", "X = f(X), Y = f(Y), compare(R, X, Y)", "="),
    ("c2", "X = f(X), Y = f(f(Y)), compare(R, X, Y)", "="),
    ("c3", "X = f(X), Y = g(Y), compare(R, X, Y)", "<"),
    ("c4", "X = f(X), Y = f(a), compare(R, X, Y)", ">"),
    ("c5", "X = f(X, a), Y = f(Y, b), compare(R, X, Y)", "<"),
    ("c6", "X = f(a, X), Y = f(b, Y), compare(R, X, Y)", "<"),
    ("c7", "X = f(a, X), Y = f(a, b), compare(R, X, Y)", ">"),
    ("c8", "X = [1|X], Y = [1|Y], compare(R, X, Y)", "="),
    ("c9", "X = f(1, X), Y = f(1.0, Y), compare(R, X, Y)", ">"),
    ("c10", "yn((X = f(X), Y = f(Y), X @< Y), R)", "no"),
    ("c11", "X = f(X), Y = f(Y), sort([X, Y], S), length(S, R)", "1"),
    ("c12", "X = f(X), Y = f(Y), Y = f(f(Y)), compare(R, X, Y)", "="),
]

WALK_ROWS = [
    ("g1", "yn((X = f(X), ground(X)), R)", "yes"),
    ("g2", "yn((X = f(X, _A), ground(X)), R)", "no"),
    ("g3", "X = f(X), term_variables(X, R)", "[]"),
    ("g4", "X = f(X, _A), term_variables(g(X, _B, X), Vs), length(Vs, R)", "2"),
    ("g5", "yn((X = f(X), findall(X, true, [Y]), Y = f(Y)), R)", "yes"),
    ("g6", "yn((X = f(X), copy_term(X, Y), Y = f(Y)), R)", "yes"),
    ("g7", "X = f(X), X =.. [R|_]", "f"),
    ("g8", "X = f(X), functor(X, N, A), R = N/A", "f/1"),
    ("g9", "yn((X = f(X), Y = g(X), copy_term(Y, Z), Z = g(W), W = f(W2), W == W2), R)", "yes"),
]

WRITE_ROWS = [
    ("w1", "X = f(X), writeq(X)", "f(...)"),
    ("w2", "X = [a|X], writeq(X)", "[a|...]"),
    ("w3", "X = f(X, _Y), writeq(X)", "f(...,_)"),
    ("w4", "X = f(Y), Y = f(X), writeq(X)", "f(f(...))"),
    ("w5", "X = f(X), writeq(g(X, X))", "g(f(...),f(...))"),
    ("w6", "X = f(X), Y = f(X), writeq(g(X, Y))", "g(f(...),f(f(...)))"),
    ("w7", "X = f(X), write_canonical(X)", "f(...)"),
    ("w8", "X = f(X), write(X)", "f(...)"),
    ("w9", "X = [a,X], writeq(X)", "[a,...]"),
    ("w10", "X = [a|X], Y = [a|Y], writeq(g(X, Y))", "g([a|...],[a|...])"),
    ("w11", "X = f(X, Y), Y = g(Y), writeq(X)", "f(...,g(...))"),
    ("w12", "X = f(X), findall(X, true, L), writeq(L)", "[f(...)]"),
]

# ``numlist/3`` builds the 100k-element list as one flat list; ``mk/3``
# builds a list through its open tail, one partial-list link per element,
# whose pairwise walks are quadratic in this engine today (32k elements take
# 20 s), so the improper-list row -- the one shape that needs ``mk`` -- is
# shorter.  Both nest far past the walkers' recursion threshold (1000).
IMPROPER_N = 5_000

DEEP_ROWS = [
    ("d1", f"yn((numlist(1, {DEEP_N}, L), numlist(1, {DEEP_N}, L2), L = L2), R)", "yes"),
    ("d2", f"yn((numlist(1, {DEEP_N}, L), numlist(1, {DEEP_N}, L2), L == L2), R)", "yes"),
    ("d3", f"numlist(1, {DEEP_N}, L), numlist(1, {DEEP_N}, L2), compare(R, L, L2)", "="),
    ("d4", f"yn((numlist(1, {DEEP_N}, L), copy_term(L, L2), L == L2), R)", "yes"),
    ("d6", f"yn((nest({DEEP_N}, a, T), nest({DEEP_N}, a, T2), T = T2), R)", "yes"),
    ("d7", f"yn((nest({DEEP_N}, a, T), nest({DEEP_N}, a, T2), T == T2), R)", "yes"),
    ("d8", f"nest({DEEP_N}, a, T), nest({DEEP_N}, a, T2), compare(R, T, T2)", "="),
    ("d9", f"yn((nest({DEEP_N}, a, T), copy_term(T, T2), T == T2), R)", "yes"),
    ("d11", f"mk({IMPROPER_N}, foo, L), mk({IMPROPER_N}, foo, L2), L = L2, L == L2, compare(R, L, L2)", "="),
    ("d12", f"nest({DEEP_N}, a, T), ground(T), term_variables(T, R)", "[]"),
    ("d13", f"yn((mk({IMPROPER_N}, foo, L), copy_term(L, L2), L == L2), R)", "yes"),
]

# Engine-only: Scryer overflows its own stack (deep) or panics (cyclic) here.
DEEP_ENGINE_ONLY_ROWS = [
    ("d5", f"yn((numlist(1, {DEEP_N}, L), assertz(big(L)), big(X), X == L), R)", "yes"),
    ("d10", f"yn((nest({DEEP_N}, a, T), assertz(bign(T)), bign(X), X == T), R)", "yes"),
    ("d14", f"yn((mk({IMPROPER_N}, foo, L), assertz(bigi(L)), bigi(X), X == L), R)", "yes"),
]

ERROR_ROWS = [
    # The one cyclic operation that stays undefined: a cyclic term has no
    # clause.  ISO-shaped (resource_error), never a raw RecursionError.
    ("x1", "X = f(X), catch(assertz(cyc(X)), error(R, _), true)",
     "resource_error(stack)"),
]

YN_ROWS = UNIFY_ROWS + IDENTITY_ROWS + COMPARE_ROWS + WALK_ROWS
ALL_ROWS = YN_ROWS + WRITE_ROWS + DEEP_ROWS + DEEP_ENGINE_ONLY_ROWS + ERROR_ROWS


_WRITE_NAMES = frozenset(r[0] for r in WRITE_ROWS)


def _clause(name, body):
    """A writer row prints (``w1 :- ...``); every other row answers in R."""
    if name in _WRITE_NAMES:
        return f"{name} :- {body}.\n"
    return f"{name}(R) :- {body}.\n"


_PROGRAM = _PRELUDE + "".join(_clause(n, b) for n, b, _ in ALL_ROWS)

_VARNAME = re.compile(r"\b_[A-Za-z0-9]*\b")


def _normalise(text: str) -> str:
    return _VARNAME.sub("_", text.strip())


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("cyclic") / "cyclic_terms_scryer_rows.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    try:
        return _load_module("_cyclic_terms_scryer_rows", str(path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


def _engine_answer(mod, name) -> str:
    """The engine's answer for a ``yn``/answer row: R written as Scryer's
    ``writeq`` writes it (variables normalised)."""
    r = Var()
    try:
        answers = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    except LogicException as exc:
        pytest.fail(f"{name}: uncaught {exc}")
    assert len(answers) == 1, (name, answers)
    return _normalise(answers[0])


def _engine_output(mod, name) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        answers = list(solve(name, mod))
    assert len(answers) == 1, (name, answers)
    return _normalise(buf.getvalue())


def _scryer_answer(program_path, goal) -> str:
    proc = run_scryer(program_path, [goal], timeout=120)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines, (goal, proc.stdout, proc.stderr[-500:])
    return _normalise(lines[-1])


@pytest.fixture(scope="module")
def scryer_program(tmp_path_factory):
    path = tmp_path_factory.mktemp("cyclic_scryer") / "rows.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    return str(path)


# ── the answer rows ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,_body,expected", YN_ROWS, ids=[r[0] for r in YN_ROWS])
def test_cyclic_answer_engine(mod, name, _body, expected):
    assert _engine_answer(mod, name) == expected


@pytest.mark.parametrize("name,_body,expected", YN_ROWS, ids=[r[0] for r in YN_ROWS])
def test_cyclic_answer_scryer(scryer, scryer_program, name, _body, expected):
    del scryer
    assert _scryer_answer(scryer_program, f"{name}(R), writeq(R), nl, halt.") == expected


# ── the writer rows ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,_body,expected", WRITE_ROWS, ids=[r[0] for r in WRITE_ROWS])
def test_cyclic_write_engine(mod, name, _body, expected):
    assert _engine_output(mod, name) == expected


@pytest.mark.parametrize("name,_body,expected", WRITE_ROWS, ids=[r[0] for r in WRITE_ROWS])
def test_cyclic_write_scryer(scryer, scryer_program, name, _body, expected):
    del scryer
    assert _scryer_answer(scryer_program, f"{name}, nl, halt.") == expected


# ── deep terms ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,_body,expected", DEEP_ROWS + DEEP_ENGINE_ONLY_ROWS,
                         ids=[r[0] for r in DEEP_ROWS + DEEP_ENGINE_ONLY_ROWS])
def test_deep_answer_engine(mod, name, _body, expected):
    assert _engine_answer(mod, name) == expected


@pytest.mark.parametrize("name,_body,expected", DEEP_ROWS, ids=[r[0] for r in DEEP_ROWS])
def test_deep_answer_scryer(scryer, scryer_program, name, _body, expected):
    del scryer
    assert _scryer_answer(scryer_program, f"{name}(R), writeq(R), nl, halt.") == expected


# ── no raw RecursionError ever reaches the program ──────────────────────────

@pytest.mark.parametrize("name,_body,expected", ERROR_ROWS, ids=[r[0] for r in ERROR_ROWS])
def test_undefined_cyclic_operation_raises_an_iso_error(mod, name, _body, expected):
    assert _engine_answer(mod, name) == expected


def test_the_program_text_is_one_clause_per_row():
    """The row table and the program are built from the same list, so a row
    cannot run under one engine and not the other."""
    for name, _body, _ in ALL_ROWS:
        assert re.search(rf"^{name}\b", _PROGRAM, re.M), name
