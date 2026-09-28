"""ISO answers, pinned against Scryer: goals whose ANSWERS used to differ.

Each table row is one goal.  The ENGINE half runs it in Clausal and the
ORACLE half runs the same goal in Scryer; both must print the expected
column, one line per answer (``writeq`` of the answer term), or the error
term the goal raises, or nothing when it fails.  Variables are compared by
their sharing, not their names: a variable written once prints ``_``, one
written more than once ``_1``, ``_2``, ... in order of first appearance.

The engine's explanatory prose is not compared.  A goal with infinitely many
answers is cut off after the row's LIMIT on both sides.
"""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
import tempfile
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq

from .conftest import SCRYER


_VAR = re.compile(r"(?<![\w'])_[A-Za-z0-9_]*")


def _normalise(line: str) -> str:
    """*line* with its variables renamed by sharing (see the module doc)."""
    names = _VAR.findall(line)
    counts = {n: names.count(n) for n in names if n != "_"}
    order: dict[str, str] = {}
    def rename(m):
        n = m.group(0)
        if n == "_" or counts.get(n, 0) < 2:
            return "_"
        if n not in order:
            order[n] = f"_{len(order) + 1}"
        return order[n]
    return _VAR.sub(rename, line)


def _engine_answers(mod, goal_name: str, limit: int) -> list[str]:
    r = Var()
    out = []
    try:
        for _ in itertools.islice(solve((goal_name, r), mod), limit):
            out.append(_normalise(term_writeq(deref(r), local_vars=True)))
    except LogicException as exc:
        out.append(_normalise(render_error_term(exc.term)))
    return out


def _scryer_answers(program: str, goals: list[tuple[str, int]]) -> list[list[str]]:
    """Run each ``(goal, limit)`` -- a goal binding ``R`` -- in Scryer after
    consulting *program*; one list of answer lines per goal."""
    driver = textwrap.dedent("""
        :- use_module(library(lists)).
        :- use_module(library(iso_ext)).
        '$lim'(N, G) :- call_nth(G, K), ( K >= N -> ! ; true ).
        '$row'(I, N, G, R) :-
            write('ROW '), write(I), nl,
            catch(( '$lim'(N, G), write('A '), writeq(R), nl, fail ; true ),
                  E, ( write('A '), writeq(E), nl )).
        """)
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "oracle.pl")
        with open(pl, "w") as fh:
            fh.write(program + "\n" + driver)
        stdin = "".join(f"'$row'({i}, {n}, ({g}), R).\n"
                        for i, (g, n) in enumerate(goals))
        proc = subprocess.run([SCRYER, pl], input=stdin, capture_output=True,
                              text=True, timeout=120)
    rows: list[list[str]] = []
    for line in proc.stdout.splitlines():
        if line.startswith("ROW "):
            rows.append([])
        elif line.startswith("A ") and rows:
            rows[-1].append(_normalise(line[2:].strip()))
    assert len(rows) == len(goals), proc.stdout[-2000:] + proc.stderr[-2000:]
    return rows


def _load_seam(tmp_path, name: str, facts: str, rows) -> object:
    src = textwrap.dedent(facts) + "".join(
        f"r{i}(R) <- ({body}),\n" for i, (_, body, _, _, _) in enumerate(rows))
    path = tmp_path / f"{name}.clausal"
    path.write_text(src)
    return _load_module(name, str(path))


def test_normalise_renames_by_sharing():
    assert _normalise("[_12,_7|_12]") == "[_1,_|_1]"
    assert _normalise("f(_G1,_,'_x')") == "f(_,_,'_x')"


# ── C2: the .pl translator's \== and \= ────────────────────────────────────
#
# ISO 8.4.1 ``\==`` and 8.2.3 ``\=`` are TESTS, run once on the terms as they
# stand.  The translator used to emit Clausal's ``!=`` (the CLP disequality,
# which delays on unbound operands) and ``is not`` (dif/2, also delayed).
# Here the SAME Prolog program is imported into the engine and consulted by
# Scryer.

_C2_PROGRAM = """\
ne(X, Y) :- X \\== Y.
nu(X, Y) :- X \\= Y.
q0(R) :- ne(A, B), A = 1, B = 1, R = [A, B].
q1(R) :- ne(A, A), R = A.
q2(R) :- ne(a, b), R = yes.
q3(R) :- nu(A, 1), A = 2, R = A.
q4(R) :- nu(1, 2), R = yes.
q5(R) :- nu([A], [B]), R = [A, B].
q6(R) :- nu([A, b], [a, A]), R = A.
q7(R) :- X = [Y], ne(X, [Y]), R = Y.
"""

#: (goal, what both print)
C2_ROWS = [
    ("q0", ["[1,1]"]),        # was: 0 answers (the CLP != delayed, then failed)
    ("q1", []),
    ("q2", ["yes"]),
    ("q3", []),               # was: [2] (dif/2 delayed, then succeeded)
    ("q4", ["yes"]),
    ("q5", []),
    ("q6", ["_"]),
    ("q7", []),
]


@pytest.fixture(scope="module")
def c2_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("c2")
    path = d / "_iso_ans_c2.pl"
    path.write_text(_C2_PROGRAM)
    sys.path.insert(0, str(d))
    try:
        return _load_prolog_module("_iso_ans_c2", str(path))
    finally:
        sys.path.remove(str(d))


@pytest.mark.parametrize("i", range(len(C2_ROWS)), ids=[r[0] for r in C2_ROWS])
def test_c2_engine(c2_mod, i):
    goal, want = C2_ROWS[i]
    assert _engine_answers(c2_mod, goal, 10) == want


def test_c2_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(_C2_PROGRAM, [(f"{g}(R)", 10) for g, _ in C2_ROWS])
    assert got == [want for _, want in C2_ROWS]


# ── V1 + C3: abs/1, min/2, max/2 outside 'is' ──────────────────────────────
#
# The Scryer rows for the values are in test_arith_rulings_scryer.py.  Here:
# the same functors where the engine reaches them by other routes -- a
# runtime-built cell, and a GROUND use inside a CLP post (the posts do not
# propagate through them; a non-ground one is clpz's domain error, pinned
# below so a change is seen).

_V1_FACTS = "-allow_singletons\n"

#: (id, engine body binding R, Scryer goal binding R, limit, what both print)
V1_ROWS = [
    ("univ abs", "'=..'(E, ['abs', -3]), 'is'(R, E)",
     "E =.. [abs, -3], R is E", 3, ["3"]),
    ("univ max", "'=..'(E, ['max', 2, 5.0]), 'is'(R, E)",
     "E =.. [max, 2, 5.0], R is E", 3, ["5.0"]),
    ("clp ground max", "R == max(2, 5)", "R is max(2, 5)", 3, ["5"]),
    ("clp ground nested", "R == abs(-7) + min(1, 2)",
     "R is abs(-7) + min(1, 2)", 3, ["8"]),
    ("clp compare", "R is 4, R < max(2, 5)", "R = 4, R < max(2, 5)", 3, ["4"]),
]


@pytest.fixture(scope="module")
def v1_mod(tmp_path_factory):
    return _load_seam(tmp_path_factory.mktemp("v1"), "_iso_ans_v1",
                      _V1_FACTS, V1_ROWS)


@pytest.mark.parametrize("i", range(len(V1_ROWS)), ids=[r[0] for r in V1_ROWS])
def test_v1_engine(v1_mod, i):
    assert _engine_answers(v1_mod, f"r{i}", V1_ROWS[i][3]) == V1_ROWS[i][4]


def test_v1_oracle(scryer):
    del scryer
    got = _scryer_answers("", [(r[2], r[3]) for r in V1_ROWS])
    assert got == [r[4] for r in V1_ROWS]


def test_v1_non_ground_in_a_clp_post_is_the_clpz_domain_error(v1_mod, tmp_path):
    """Not propagated: ``X == max(Y, 3)`` raises rather than answering
    wrongly (Scryer's clpz would post it as a constraint)."""
    mod = _load_seam(tmp_path, "_iso_ans_v1b", _V1_FACTS,
                     [("", "R == max(Y, 3), Y is 5", "", 3, [])])
    got = _engine_answers(mod, "r0", 3)
    assert len(got) == 1 and got[0].startswith(
        "error(domain_error(clpz_expression,max(_,3))"), got


# ── Two open partial lists unify (F030) ────────────────────────────────────
#
# ``[1|T1] = [H|T2]`` binds ``H = 1, T1 = T2``.  Two open SegLists used to
# fail outright -- in plain unification, in a body ``is`` against a star
# pattern, and in a clause HEAD ``[H, *T]`` called with a partial list (the
# C list-pattern matcher).

_PL_FACTS = "-allow_singletons\nhp([H, *T], H, T),\n"

PL_ROWS = [
    ("two partials", "L is [1, *_], L is [H, *_], R is H",
     "L = [1|_], L = [H|_], R = H", 3, ["1"]),
    ("tails meet", "L is [1, *T], M is [H, *U], L is M, R is [H, T, U]",
     "L = [1|T], M = [H|U], L = M, R = [H, T, U]", 3, ["[1,_1,_1]"]),
    ("longer prefix", "[1, 2, *A] is [H, *B], R is [H, A, B]",
     "[1, 2|A] = [H|B], R = [H, A, B]", 3, ["[1,_1,[2|_1]]"]),
    ("mismatch", "['a', *_] is ['b', *_], R is 1",
     "[a|_] = [b|_], R = 1", 3, []),
    ("head pattern", "L is [1, 2, *_], hp(L, H, T), R is [H, T]",
     "L = [1, 2|_], L = [H|T], R = [H, T]", 3, ["[1,[2|_]]"]),
    ("head pattern short", "L is [1, *_], hp(L, H, T), R is [H, T]",
     "L = [1|_], L = [H|T], R = [H, T]", 3, ["[1,_]"]),
]


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    return _load_seam(tmp_path_factory.mktemp("pl"), "_iso_ans_pl",
                      _PL_FACTS, PL_ROWS)


@pytest.mark.parametrize("i", range(len(PL_ROWS)), ids=[r[0] for r in PL_ROWS])
def test_partial_lists_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", PL_ROWS[i][3]) == PL_ROWS[i][4]


def test_partial_lists_oracle(scryer):
    del scryer
    got = _scryer_answers("", [(r[2], r[3]) for r in PL_ROWS])
    assert got == [r[4] for r in PL_ROWS]
