"""Which answers a top-level knows are the LAST, against Scryer's top-level.

Scryer's top-level ends an answer with ``.`` when no choice point is left
(``X = c.`` for ``member(X, [a,b,c])``) and asks with ``;`` otherwise.  Each
row runs one query both ways:

- Clausal: the query read as the CLI reads ``-g`` text and solved as
  ``call(Goal)`` with ``solve_with_last`` (as a top-level does); each answer
  is ``f`` (last: True) or ``p``.
- Scryer: ``setup_call_cleanup(true, Goal, Det = true)``; ``Det == true``
  after an answer is ``f``, else ``p`` -- what its top-level prints.

Both columns are pinned.  Where they differ the row says why: Clausal may be
more precise (it can tell from the list itself that ``select/3`` is at its
last element) or more conservative (``catch/3``).  The soundness half -- Clausal
never says ``f`` and then finds another answer -- is checked on every row
by running the query again with FINAL disabled and comparing the answers.
"""

from __future__ import annotations

import itertools
import os
import tempfile
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.cli import _goal_reader_ops, _read_goal
from clausal.import_hook import _load_module
from clausal.logic.solve import solve_with_last
from clausal.logic.trampoline import set_final_enabled
from clausal.terms import term_writeq

from .conftest import SCRYER, run_scryer

LIMIT = 6

PROGRAM = textwrap.dedent("""\
    q(1).
    q(2).
    p(X) :- q(X).
    c(red).
    c(green).
    c(blue).
    c(cyan).
    c(white).
    last_clause(X) :- X = 1.
    last_clause(X) :- X = 2.
    two(X, Y) :- q(X), Y = X.
    one(a).
    """)

#: (query, Clausal's answers, Scryer's answers)
ROWS = [
    ("member(X, [a,b,c])", "ppf", "ppf"),
    ("member(b, [a,b,c])", "p", "p"),
    ("member(c, [a,b,c])", "f", "f"),
    ("member(X, [a,b|_])", "pppppp", "pppppp"),
    ("between(1, 3, X)", "ppf", "ppf"),
    ("between(1, 3, 3)", "f", "f"),
    # Clausal sees the end of the list; Scryer's select/3 leaves a choice.
    ("select(X, [a,b], R)", "pf", "pp"),
    ("nth0(I, [a,b], E)", "pf", "pf"),
    ("nth1(2, [a,b], E)", "f", "f"),
    ("append(X, Y, [a,b])", "ppf", "ppf"),
    ("append([a], [b], L)", "f", "f"),
    ("append(X, [b], [a,b])", "p", "p"),
    ("length(L, 2)", "f", "f"),
    ("length([a], N)", "f", "f"),
    ("length(L, N)", "pppppp", "pppppp"),
    ("X = 1", "f", "f"),
    ("X is 1 + 2", "f", "f"),
    ("atom_length(abc, N)", "f", "f"),
    ("atom_codes(abc, L)", "f", "f"),
    ("(X = 1 ; X = 2)", "pf", "pf"),
    ("member(X, [a]), Y = 1", "f", "f"),
    ("Y = 1, member(X, [a,b])", "pf", "pf"),
    ("member(X, [a,b]), Y = 1", "pf", "pf"),
    ("once(member(X, [a,b]))", "f", "f"),
    ("\\+ fail", "f", "f"),
    ("findall(X, member(X, [a,b]), L)", "f", "f"),
    ("forall(member(X, [a]), true)", "f", "f"),
    ("dif(X, a)", "f", "f"),
    ("dif(X, a), member(X, [a,b])", "f", "f"),
    # catch/3: Clausal keeps a catch frame's answers non-final.
    ("catch(member(X, [a,b]), _, true)", "pp", "pf"),
    ("sub_atom(ab, B, 1, A, S)", "pp", "pp"),
    # User predicates: the last clause, a body ending in a last answer.
    ("p(X)", "pf", "pf"),
    ("two(X, Y)", "pf", "pf"),
    ("last_clause(X)", "pf", "pf"),
    ("one(X)", "f", "f"),
    ("q(2)", "f", "f"),
    # The first clause of a two-clause table: the later clause's first
    # argument cannot match (a predicate this small is not indexed, so the
    # answer asks the later heads' first-argument keys).
    ("q(1)", "f", "f"),
    ("c(green)", "f", "f"),
    ("c(X)", "ppppf", "ppppf"),
]


@pytest.fixture(scope="module")
def program(tmp_path_factory):
    d = tmp_path_factory.mktemp("lastans")
    path = d / "lastans.pl"
    path.write_text(PROGRAM)
    return path


@pytest.fixture(scope="module")
def module(program):
    return _load_module("lastans_scryer_mod", str(program))


def _clausal(module, query, enabled=True):
    goal, shown = _read_goal(query, _goal_reader_ops(PROGRAM))
    set_final_enabled(enabled)
    try:
        out = []
        for _t, last in itertools.islice(
                solve_with_last(("call", goal), module), LIMIT):
            out.append(("f" if last else "p", term_writeq(
                [v for _n, v in shown], local_vars=True)))
        return out
    finally:
        set_final_enabled(True)


@pytest.mark.parametrize("query,want,_scryer", ROWS, ids=[r[0] for r in ROWS])
def test_clausal_marks_the_last_answer(module, query, want, _scryer):
    got = _clausal(module, query)
    assert "".join(f for f, _ in got) == want
    # Soundness: the same answers as a search that never stops early.
    plain = _clausal(module, query, enabled=False)
    assert [a for _f, a in got] == [a for _f, a in plain]


_DRIVER = textwrap.dedent("""\
    :- use_module(library(lists)).
    :- use_module(library(between)).
    :- use_module(library(iso_ext)).
    :- use_module(library(dif)).
    '$row'(I, N, G) :-
        write(row(I)), nl,
        (   call_nth(setup_call_cleanup(true, G, Det = true), K),
            ( Det == true -> write(f) ; write(p) ), nl,
            K >= N
        ->  true
        ;   true
        ).
    """)


@pytest.fixture(scope="module")
def scryer_rows(program):
    if not os.path.exists(SCRYER):
        return None
    with tempfile.TemporaryDirectory() as d:
        drv = os.path.join(d, "driver.pl")
        with open(drv, "w") as fh:
            fh.write(_DRIVER)
        goals = [f"'$row'({i}, {LIMIT}, ({q}))" for i, (q, _c, _s) in enumerate(ROWS)]
        out = run_scryer([str(program), drv], goals).stdout
    rows: dict[int, str] = {}
    cur = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("row(") and line.endswith(")"):
            cur = int(line[4:-1])
            rows[cur] = ""
        elif cur is not None and line in ("f", "p"):
            rows[cur] += line
    return rows


@pytest.mark.parametrize("i,row", list(enumerate(ROWS)), ids=[r[0] for r in ROWS])
def test_scryer_column(scryer_rows, i, row):
    if scryer_rows is None:     # tests/iso/conftest.py's policy
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    _query, _clausal_col, want = row
    assert scryer_rows.get(i) == want
