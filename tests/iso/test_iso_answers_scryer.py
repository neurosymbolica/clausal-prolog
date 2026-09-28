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


# ── V2 + B4f/g/h: append/3, length/2, member/2 on OPEN lists ───────────────
#
# The prologue defines them by recursion on the list, so an unbound or
# partial list is enumerated (infinitely, where the prologue is).  They used
# to answer nothing.  ``in_/2`` is the engine's member/2, ``in_check/2`` its
# memberchk/2.

_LO_FACTS = "-allow_singletons\n-private([a, b])\n"

LO_ROWS = [
    ("append all open", "append(X, Y, Z), R is [X, Y, Z]",
     "append(X, Y, Z), R = [X, Y, Z]", 3,
     ["[[],_1,_1]", "[[_1],_2,[_1|_2]]", "[[_1,_2],_3,[_1,_2|_3]]"]),
    ("append [1] L2 L3", "append([1], L2, L3), R is [L2, L3]",
     "append([1], L2, L3), R = [L2, L3]", 3, ["[_1,[1|_1]]"]),
    ("append X [9] Y", "append(X, [9], Y), R is [X, Y]",
     "append(X, [9], Y), R = [X, Y]", 3,
     ["[[],[9]]", "[[_1],[_1,9]]", "[[_1,_2],[_1,_2,9]]"]),
    ("append partial first", "append([1, *T], [2], L), R is [T, L]",
     "append([1|T], [2], L), R = [T, L]", 3,
     ["[[],[1,2]]", "[[_1],[1,_1,2]]", "[[_1,_2],[1,_1,_2,2]]"]),
    ("append open third", "append(X, Y, [1, *Z]), R is [X, Y, Z]",
     "append(X, Y, [1|Z]), R = [X, Y, Z]", 3,
     ["[[],[1|_1],_1]", "[[1],_1,_1]", "[[1,_1],_2,[_1|_2]]"]),
    ("append conflicting prefixes", "append([1, *T], Y, [2, *Z]), R is 1",
     "append([1|T], Y, [2|Z]), R = 1", 3, []),
    ("append conflict past the prefix", "append([1, 2, *T], Y, [1, 3, *Z]), R is 1",
     "append([1, 2|T], Y, [1, 3|Z]), R = 1", 3, []),
    ("append open both, L1 longer", "append([1, 2, *T], Y, [1, *Z]), R is [T, Y, Z]",
     "append([1, 2|T], Y, [1|Z]), R = [T, Y, Z]", 2,
     ["[[],_1,[2|_1]]", "[[_1],_2,[2,_1|_2]]"]),
    ("append split", "append(X, Y, [1, 2]), R is [X, Y]",
     "append(X, Y, [1, 2]), R = [X, Y]", 5,
     ["[[],[1,2]]", "[[1],[2]]", "[[1,2],[]]"]),
    ("length open", "length(L, N), R is [L, N]",
     "length(L, N), R = [L, N]", 3, ["[[],0]", "[[_],1]", "[[_,_],2]"]),
    ("length partial", "length([a, *L], N), R is [L, N]",
     "length([a|L], N), R = [L, N]", 3, ["[[],1]", "[[_],2]", "[[_,_],3]"]),
    ("length partial fixed", "length([a, b, *T], 3), R is T",
     "length([a, b|T], 3), R = T", 3, ["[_]"]),
    ("length partial too short", "length([a, b, *T], 1), R is T",
     "length([a, b|T], 1), R = T", 3, []),
    ("length negative", "length(L, -1), R is L",
     "length(L, -1), R = L", 3,
     ["error(domain_error(not_less_than_zero,-1),length/2)"]),
    ("length proper negative", "length(['a'], -1), R is 1",
     "length([a], -1), R = 1", 3,
     ["error(domain_error(not_less_than_zero,-1),length/2)"]),
    ("length non-integer", "length([a], 'b'), R is 1",
     "length([a], b), R = 1", 3, ["error(type_error(integer,b),length/2)"]),
    ("length self", "length(L, L), R is L", "length(L, L), R = L", 3,
     ["error(resource_error(finite_memory),length/2)"]),
    ("member 1 open", "in_(1, L), R is L", "member(1, L), R = L", 3,
     ["[1|_]", "[_,1|_]", "[_,_,1|_]"]),
    ("member X open", "in_(X, L), R is [X, L]", "member(X, L), R = [X, L]", 3,
     ["[_1,[_1|_]]", "[_1,[_,_1|_]]", "[_1,[_,_,_1|_]]"]),
    ("member partial", "in_(X, ['a', *L]), R is [X, L]",
     "member(X, [a|L]), R = [X, L]", 3,
     ["[a,_]", "[_1,[_1|_]]", "[_1,[_,_1|_]]"]),
    ("memberchk open", "in_check(1, L), R is L", "memberchk(1, L), R = L", 3,
     ["[1|_]"]),
    ("memberchk partial", "in_check(X, ['a', *L]), R is [X, L]",
     "memberchk(X, [a|L]), R = [X, L]", 3, ["[a,_]"]),
]


@pytest.fixture(scope="module")
def lo_mod(tmp_path_factory):
    return _load_seam(tmp_path_factory.mktemp("lo"), "_iso_ans_lo",
                      _LO_FACTS, LO_ROWS)


@pytest.mark.parametrize("i", range(len(LO_ROWS)), ids=[r[0] for r in LO_ROWS])
def test_open_lists_engine(lo_mod, i):
    assert _engine_answers(lo_mod, f"r{i}", LO_ROWS[i][3]) == LO_ROWS[i][4]


def test_open_lists_oracle(scryer):
    del scryer
    got = _scryer_answers("", [(r[2], r[3]) for r in LO_ROWS])
    assert got == [r[4] for r in LO_ROWS]


# ── R6: maplist/2,3 backtrack through every solution of each call ──────────
#
# The prologue defines maplist by call/N, so each call's solutions are
# backtracked into; it used to commit to the first.

_ML_FACTS = """\
-allow_singletons
-private([aa, bb, cc, foo])
p(1),
p(2),
p(3),
q(1, aa),
q(1, bb),
q(2, cc),
"""
_ML_PROGRAM = "p(1). p(2). p(3). q(1, aa). q(1, bb). q(2, cc).\n"

ML_ROWS = [
    ("maplist/2 two open", "maplist(p, [X, Y]), R is [X, Y]",
     "maplist(p, [X, Y]), R = [X, Y]", 20,
     ["[1,1]", "[1,2]", "[1,3]", "[2,1]", "[2,2]", "[2,3]", "[3,1]", "[3,2]",
      "[3,3]"]),
    ("maplist/2 empty", "maplist(p, []), R is 1", "maplist(p, []), R = 1", 5,
     ["1"]),
    ("maplist/2 no solution", "maplist(p, [1, 4]), R is 1",
     "maplist(p, [1, 4]), R = 1", 5, []),
    ("maplist/3 outputs", "maplist(q, [1, 2], L), R is L",
     "maplist(q, [1, 2], L), R = L", 5, ["[aa,cc]", "[bb,cc]"]),
    ("maplist/3 bound outputs", "maplist(q, [1, X], [Y, cc]), R is [X, Y]",
     "maplist(q, [1, X], [Y, cc]), R = [X, Y]", 5, ["[2,aa]", "[2,bb]"]),
    ("maplist/3 later element bound", "maplist(q, [1, 1], [bb, Y]), R is Y",
     "maplist(q, [1, 1], [bb, Y]), R = Y", 5, ["aa", "bb"]),
    ("maplist/3 Ys not a list", "maplist(q, [1, 2], 'foo'), R is 1",
     "maplist(q, [1, 2], foo), R = 1", 5, []),
    ("maplist/3 Ys partial", "maplist(q, [1, 2], ['bb', *T]), R is T",
     "maplist(q, [1, 2], [bb|T]), R = T", 5, ["[cc]"]),
    ("maplist/3 in findall", "findall([X, Y], maplist(p, [X, Y]), L), length(L, R)",
     "findall([X, Y], maplist(p, [X, Y]), L), length(L, R)", 5, ["9"]),
]


@pytest.fixture(scope="module")
def ml_mod(tmp_path_factory):
    return _load_seam(tmp_path_factory.mktemp("ml"), "_iso_ans_ml",
                      _ML_FACTS, ML_ROWS)


@pytest.mark.parametrize("i", range(len(ML_ROWS)), ids=[r[0] for r in ML_ROWS])
def test_maplist_engine(ml_mod, i):
    assert _engine_answers(ml_mod, f"r{i}", ML_ROWS[i][3]) == ML_ROWS[i][4]


def test_maplist_oracle(scryer):
    del scryer
    got = _scryer_answers(_ML_PROGRAM, [(r[2], r[3]) for r in ML_ROWS])
    assert got == [r[4] for r in ML_ROWS]


# ── R5: bagof/3 and setof/3 group by the free variables; ``V^G`` ───────────
#
# ISO 8.10.2/8.10.3: one bag per binding of the goal's free variables (those
# in neither the template nor a leading ``V^``), answered on backtracking
# in the standard order of that binding, as Scryer orders them.  They used to
# answer ONE bag with the free variables left unbound, and ``V^G`` was a
# load-time NotImplementedError.

_BG_FACTS = """\
-allow_singletons
-private([peter, ann, pat, tom, mike, aa, bb, gg])
age(peter, 7),
age(ann, 11),
age(pat, 8),
age(tom, 5),
age(mike, 11),
klass(ann, aa),
klass(mike, bb),
klass(pat, bb),
klass(peter, aa),
klass(tom, aa),
p(1),
p(2),
p(3),
kv(1, aa),
kv(2, bb),
kv(1, gg),
"""
_BG_PROGRAM = """\
age(peter, 7). age(ann, 11). age(pat, 8). age(tom, 5). age(mike, 11).
klass(ann, aa). klass(mike, bb). klass(pat, bb). klass(peter, aa).
klass(tom, aa).
p(1). p(2). p(3).
kv(1, aa). kv(2, bb). kv(1, gg).
"""

BG_ROWS = [
    ("bagof groups by the free variable", "bagof(N, age(N, A), L), R is [A, L]",
     "bagof(N, age(N, A), L), R = [A, L]", 10,
     ["[5,[tom]]", "[7,[peter]]", "[8,[pat]]", "[11,[ann,mike]]"]),
    ("bagof ^", "bagof(N, A ^ age(N, A), L), R is L",
     "bagof(N, A^age(N, A), L), R = L", 10, ["[peter,ann,pat,tom,mike]"]),
    ("setof pairs", "setof(C - N, klass(N, C), L), R is L",
     "setof(C-N, klass(N, C), L), R = L", 10,
     ["[aa-ann,aa-peter,aa-tom,bb-mike,bb-pat]"]),
    ("setof groups", "setof(N, klass(N, C), L), R is [C, L]",
     "setof(N, klass(N, C), L), R = [C, L]", 10,
     ["[aa,[ann,peter,tom]]", "[bb,[mike,pat]]"]),
    ("anonymous is free", "bagof(N, age(N, _), L), R is L",
     "bagof(N, age(N, _), L), R = L", 10,
     ["[tom]", "[peter]", "[pat]", "[ann,mike]"]),
    ("keys", "bagof(V, kv(K, V), L), R is [K, L]",
     "bagof(V, kv(K, V), L), R = [K, L]", 10, ["[1,[aa,gg]]", "[2,[bb]]"]),
    ("no solutions", "bagof(X, (p(X), X is 9), L), R is L",
     "bagof(X, (p(X), X = 9), L), R = L", 10, []),
    ("setof no solutions", "setof(X, (p(X), X > 5), L), R is L",
     "setof(X, (p(X), X > 5), L), R = L", 10, []),
    ("setof sorts and dedups", "setof(X, in_(X, [3, 1, 2, 1]), L), R is L",
     "setof(X, member(X, [3, 1, 2, 1]), L), R = L", 10, ["[1,2,3]"]),
    ("bagof keeps order and duplicates", "bagof(X, in_(X, [3, 1, 2, 1]), L), R is L",
     "bagof(X, member(X, [3, 1, 2, 1]), L), R = L", 10, ["[3,1,2,1]"]),
    ("variant witnesses share a bag",
     "bagof(X, (X is 1 or Y is 2 or X is 3), L), R is [Y, L]",
     "bagof(X, (X = 1 ; Y = 2 ; X = 3), L), R = [Y, L]", 10,
     ["[_,[1,3]]", "[2,[_]]"]),
    ("^ over a disjunction", "bagof(X, Y ^ (X is 1 or Y is 2 or X is 3), L), R is L",
     "bagof(X, Y^(X = 1 ; Y = 2 ; X = 3), L), R = L", 10, ["[1,_,3]"]),
    ("a free variable bound outside", "X is 1, bagof(Y, (Y is X or Y is 2), L), R is L",
     "X = 1, bagof(Y, (Y = X ; Y = 2), L), R = L", 10, ["[1,2]"]),
    ("free variable in a compound",
     "bagof(X, (p(X), Z is f(W)), L), R is [Z, L]",
     "bagof(X, (p(X), Z = f(W)), L), R = [Z, L]", 10, ["[f(_),[1,2,3]]"]),
    ("runtime-built goal with ^", "G is (Y ^ p(Y)), call(bagof(X, G, L)), R is L",
     "G = (Y^p(Y)), bagof(X, G, L), R = L", 10, ["[_,_,_]"]),
    ("variable goal with ^", "G is (Y ^ p(Y)), bagof(X, call(G), L), R is L",
     "G = (Y^p(Y)), bagof(X, G, L), R = L", 10, ["[_,_,_]"]),
    ("variable goal, free variable", "G is p(Y), bagof(Y, call(G), L), R is L",
     "G = p(Y), bagof(Y, G, L), R = L", 10, ["[1,2,3]"]),
    ("variable goal groups", "G is kv(K, V), bagof(V, call(G), L), R is [K, L]",
     "G = kv(K, V), bagof(V, G, L), R = [K, L]", 10, ["[1,[aa,gg]]", "[2,[bb]]"]),
    ("unbound goal", "call(bagof(X, G, L)), R is L",
     "bagof(X, G, L), R = L", 10, ["error(instantiation_error,_)"]),
    ("non-callable goal", "call(bagof(X, 1, L)), R is L",
     "bagof(X, 1, L), R = L", 10, ["error(type_error(callable,1),_)"]),
    ("bag not a list", "call(bagof(X, p(X), 'foo')), R is 1",
     "bagof(X, p(X), foo), R = 1", 10, ["error(type_error(list,foo),_)"]),
]


def _bg_line(line: str) -> str:
    """The error term's context argument differs by convention (Scryer puts
    the innermost call there); compare the formal term only."""
    if line.startswith("error("):
        return re.sub(r",[^,()]*(\([^()]*\))?(/\d+)?\)$", ",_)", line)
    return line


@pytest.fixture(scope="module")
def bg_mod(tmp_path_factory):
    src = _BG_FACTS.replace("-private([peter", "-private([foo, f(X), peter")
    return _load_seam(tmp_path_factory.mktemp("bg"), "_iso_ans_bg", src,
                      BG_ROWS)


@pytest.mark.parametrize("i", range(len(BG_ROWS)), ids=[r[0] for r in BG_ROWS])
def test_bagof_engine(bg_mod, i):
    got = [_bg_line(x) for x in _engine_answers(bg_mod, f"r{i}", BG_ROWS[i][3])]
    assert got == BG_ROWS[i][4]


def test_bagof_oracle(scryer):
    del scryer
    got = _scryer_answers(_BG_PROGRAM, [(r[2], r[3]) for r in BG_ROWS])
    assert [[_bg_line(x) for x in rows] for rows in got] == [r[4] for r in BG_ROWS]


#: Where the engine follows ISO and Scryer does not (engine column only).
#: ISO 7.1.1.4: the free variables of ``Y^p(Y)`` with template ``Y`` are
#: none, so there is ONE bag.  Scryer answers [1]; [2]; [3]: its
#: ``findall_with_existential`` makes the existential variable the witness
#: when the template already holds it.
BG_DEVIATIONS = [
    ("template variable under ^", "bagof(Y, Y ^ p(Y), L), R is L", ["[1,2,3]"]),
]


def test_bagof_deviations(tmp_path):
    mod = _load_seam(tmp_path, "_iso_ans_bgd", _BG_FACTS,
                     [(n, b, "", 10, w) for n, b, w in BG_DEVIATIONS])
    for i, (_, _, want) in enumerate(BG_DEVIATIONS):
        assert _engine_answers(mod, f"r{i}", 10) == want
