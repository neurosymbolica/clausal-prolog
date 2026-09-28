"""R4 (2026-09-28): the pair builtins are Scryer's ``library(pairs)``.

A pair is ``K-V`` -- the cell ``('-', K, V)``.  Each ROW is one goal, run in
the engine and (ORACLE half) in Scryer with ``:- use_module(library(pairs)).``
The oracle half pins what Scryer prints; the engine half pins the same answer
as engine data.  Variables are compared by SHAPE: a row's engine expectation
is a function of the answer, so fresh variables need not be named.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var, is_var

from .conftest import SCRYER


def P(k, v):
    return ("-", k, v)


def _is_pair_of_vars(t):
    return type(t) is tuple and t[0] == "-" and is_var(t[1]) and is_var(t[2])


#: (name, engine goal cell with Var() slots, Scryer goal, Scryer's answer,
#:  engine check over the list of answers -- each a tuple of the Var() slots)
def _rows():
    A, B, C = Var(), Var(), Var()
    return [
        ("pkv_decompose",
         ("pairs_keys_values", [P("a", 1), P("b", 2)], A, B), (A, B),
         "pairs_keys_values([a-1,b-2], K, V).", "K = \"ab\", V = [1,2].",  # [a,b] prints as a string
         lambda sols: sols == [(["a", "b"], [1, 2])]),
        ("pkv_construct",
         ("pairs_keys_values", A, ["a", "b"], [1, 2]), (A,),
         "pairs_keys_values(P, [a,b], [1,2]).", "P = [a-1,b-2].",
         lambda sols: sols == [([P("a", 1), P("b", 2)],)]),
        ("pkv_keys_fix_length",
         ("pairs_keys_values", A, ["a", "b"], B), (A, B),
         "pairs_keys_values(P, [a,b], V).", "P = [a-_A,b-_B], V = [_A,_B].",
         lambda sols: len(sols) == 1 and [p[1] for p in sols[0][0]] == ["a", "b"]
         and [p[2] for p in sols[0][0]] == sols[0][1]),
        ("pkv_non_pair_fails",
         ("pairs_keys_values", [P("a", 1), "x"], A, B), (A, B),
         "pairs_keys_values([a-1,x], K, V).", "false.",
         lambda sols: sols == []),
        ("pkv_old_list_shape_fails",
         ("pairs_keys_values", [["a", 1]], A, B), (A, B),
         "pairs_keys_values([[a,1]], K, V).", "false.",
         lambda sols: sols == []),
        ("pkv_non_list_fails",
         ("pairs_keys_values", "foo", A, B), (A, B),
         "pairs_keys_values(foo, K, V).", "false.",
         lambda sols: sols == []),
        ("pkv_unbound_element_becomes_pair",
         ("pairs_keys_values", [C, P("b", 2)], A, B), (C, A, B),
         "pairs_keys_values([X,b-2], K, V).",
         'X = _A-_B, K = [_A|"b"], V = [_B,2].',
         lambda sols: len(sols) == 1 and _is_pair_of_vars(sols[0][0])
         and sols[0][1][1] == "b" and sols[0][2][1] == 2),
        ("pkv_length_mismatch_fails",
         ("pairs_keys_values", A, ["a"], [1, 2]), (A,),
         "pairs_keys_values(P, [a], [1,2]).", "false.",
         lambda sols: sols == []),
        ("pairs_keys",
         ("pairs_keys", [P("a", 1), P("b", 2)], A), (A,),
         "pairs_keys([a-1,b-2], K).", "K = \"ab\".",
         lambda sols: sols == [(["a", "b"],)]),
        ("pairs_values",
         ("pairs_values", [P("a", 1), P("b", 2)], A), (A,),
         "pairs_values([a-1,b-2], V).", "V = [1,2].",
         lambda sols: sols == [([1, 2],)]),
        ("group_adjacent",
         ("group_pairs_by_key", [P("a", 1), P("b", 2), P("a", 3)], A), (A,),
         "group_pairs_by_key([a-1,b-2,a-3], G).", "G = [a-[1],b-[2],a-[3]].",
         lambda sols: sols == [([P("a", [1]), P("b", [2]), P("a", [3])],)]),
        ("group_run",
         ("group_pairs_by_key", [P("a", 1), P("a", 2), P("b", 3)], A), (A,),
         "group_pairs_by_key([a-1,a-2,b-3], G).", "G = [a-[1,2],b-[3]].",
         lambda sols: sols == [([P("a", [1, 2]), P("b", [3])],)]),
        ("group_non_pair_fails",
         ("group_pairs_by_key", [P("a", 1), "b"], A), (A,),
         "group_pairs_by_key([a-1,b], G).", "false.",
         lambda sols: sols == []),
        ("group_bound_groups_split_a_run",
         ("group_pairs_by_key", [P("a", 1), P("a", 2)], [P("a", [1]), P("a", [2])]), (),
         "group_pairs_by_key([a-1,a-2], [a-[1],a-[2]]).", "true.",
         lambda sols: sols == [()]),
    ]


ROWS = _rows()


@pytest.mark.parametrize("row", ROWS, ids=[r[0] for r in ROWS])
def test_engine(row):
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__
    _name, goal, slots, _sg, _sa, check = row
    from clausal.logic.database import Module
    sols = [tuple(_deref_walk(s) for s in slots)
            for _ in solve(goal, Module("_pairs_rows"), Trail())]
    assert check(sols), sols


def _scryer(goal: str) -> str:
    d = tempfile.mkdtemp()
    pl = os.path.join(d, "w.pl")
    with open(pl, "w") as fh:
        fh.write(":- use_module(library(pairs)).\n")
    proc = subprocess.run([SCRYER, pl], input=goal + "\n", capture_output=True,
                          text=True, timeout=30)
    lines = [ln.strip() for ln in proc.stdout.splitlines()
             if ln.strip() and "put_attr TRACE" not in ln]
    return lines[0] if lines else ""


@pytest.mark.parametrize("row", ROWS, ids=[r[0] for r in ROWS])
def test_scryer_oracle(scryer, row):
    _name, _goal, _slots, scryer_goal, scryer_answer, _check = row
    assert _scryer(scryer_goal) == scryer_answer
