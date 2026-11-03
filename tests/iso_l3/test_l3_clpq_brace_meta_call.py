"""library(clpq)'s ``{}/1`` is a predicate: a brace goal the compiler never
sees -- ``call({X > 1})``, ``G = {C}, call(G)``, a variable goal,
``findall/3`` over a brace goal held in a variable, ``call({}, C)``, a
toplevel ``-g`` goal -- posts its block as a written ``{C}`` does.

A written ``{C}`` is lowered to the seam's ``clpq.rational(C)`` at load; the
meta-called one reaches ``{}/1`` from ``clausal/stdlib/clpq_braces.clausal``,
which an import of library(clpq) brings in and which posts through the same
``clpq.rational`` builtin.  Scryer (library(clpq) loaded) answers every case
the same (``test_scryer_answers_the_same``).  Without the import ``{}/1``
stays an ordinary undefined goal, as in Scryer.

Each case runs on the ``.pl`` surface (native front end) and on Clausal
Prolog, under CLAUSAL_CLPQ=legacy and holzbaur, in a subprocess (the solver
is chosen at import).  See todo/done/brace-goal-is-not-callable-2026-10-11.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from tests._oracles import SCRYER, run_scryer

_ROOT = pathlib.Path(__file__).resolve().parents[2]

PROGRAM = r"""
t_call_var(X) :- G = {X > 1, X < 3}, call(G), X = 2.
t_variable_goal(X) :- G = {X > 1}, G, X = 5.
t_findall(L) :- findall(X, (G = {X = 2}, call(G)), L).
t_findall_goal(L) :- G = {X >= 1, X =< 1}, findall(X, G, L).
t_call_n(X) :- call({}, (X >= 1, X =< 1)).
t_call_brace(X) :- call({X >= 4, X =< 4}).
t_inconsistent(X) :- G = {X > 1, X < 0}, call(G).
t_negation(X) :- \+ call({X > 1, X < 0}), X = ok.
t_propagates(Y) :- G = {X + Y = 10}, call(G), X = 3.
"""

#: The answers (findall/3 of each case), as Scryer prints them.
EXPECTED = {
    "t_call_var": "[2]",
    "t_variable_goal": "[5]",
    "t_findall": "[[2]]",
    "t_findall_goal": "[[1]]",
    "t_call_n": "[1]",
    "t_call_brace": "[4]",
    "t_inconsistent": "[]",
    "t_negation": "[ok]",
    "t_propagates": "[7]",
}

HEADER = ":- use_module(library(clpq)).\n"

_DRIVER = r"""
import importlib, json, sys
sys.path.insert(0, sys.argv[1])
import clausal
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.terms import term_str
mod = importlib.import_module(sys.argv[2])
out = {}
for name in json.loads(sys.argv[3]):
    try:
        v = Var()
        out[name] = "[" + ",".join(term_str(walk(v)).replace(" ", "")
                                   for _ in call(name, v, module=mod)) + "]"
    except Exception as exc:  # every case is reported, not the first
        out[name] = f"raised {type(exc).__name__}: {exc}"
print(json.dumps(out))
"""


def _program(suffix: str, name: str) -> str:
    if suffix == ".clausal":
        exports = ", ".join(f"{n}/1" for n in EXPECTED)
        return (f":- module({name}, [{exports}]).\n{HEADER}{PROGRAM}"
                f":- end_module({name}).\n")
    return HEADER + PROGRAM


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_a_meta_called_brace_goal_posts_its_block(tmp_path, solver, suffix):
    name = f"brace_meta_{solver}_{suffix.strip('.')}"
    (tmp_path / f"{name}{suffix}").write_text(_program(suffix, name))
    env = dict(os.environ, CLAUSAL_CLPQ=solver, CLAUSAL_PL_FRONTEND="native",
               PYTHONPATH=str(_ROOT))
    proc = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", _DRIVER, str(tmp_path), name,
         json.dumps(list(EXPECTED))],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    wrong = {k: (got[k], v) for k, v in EXPECTED.items() if got[k] != v}
    assert not wrong, wrong


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_a_brace_goal_from_the_toplevel(tmp_path, solver):
    """``clausal -g "{X > 1}" lin.clausal`` raised existence_error({}/1)."""
    (tmp_path / "lin.clausal").write_text(
        ":- module(lin, [p/1]).\n" + HEADER + "p(X) :- {X >= 2}.\n"
        ":- end_module(lin).\n")
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(_ROOT))
    out = {}
    for goal in ("{X > 1, X < 3}, X = 2", "G = {Y >= 1, Y =< 1}, call(G)"):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", "-m", "clausal", "lin.clausal",
             "-g", goal], cwd=tmp_path, env=env, capture_output=True,
            text=True, timeout=300)
        out[goal] = proc.stdout + proc.stderr
    assert "X = 2" in out["{X > 1, X < 3}, X = 2"], out
    assert "Y = 1" in out["G = {Y >= 1, Y =< 1}, call(G)"], out


def test_scryer_answers_the_same(tmp_path):
    if not os.path.exists(SCRYER):
        pytest.skip(f"needs the Scryer CLP(Q) build at {SCRYER}")
    program = tmp_path / "brace_meta.pl"
    program.write_text(HEADER + PROGRAM)
    got = {}
    for name in EXPECTED:
        proc = run_scryer(str(program), f"findall(R, {name}(R), Rs).")
        found = re.search(r"Rs = (.*)\.\s*$", proc.stdout.strip())
        got[name] = found.group(1).replace(" ", "") if found else proc.stdout
    wrong = {k: (got[k], v) for k, v in EXPECTED.items() if got[k] != v}
    assert not wrong, wrong


# ── in process, under the solver CLAUSAL_CLPQ selects ──


def test_without_library_clpq_a_meta_called_brace_is_undefined(native, ans):
    """As in Scryer: ``{}/1`` exists only by the import."""
    from clausal.logic.exceptions import LogicException
    mod = native.load("bm_noimp", "t(X) :- G = {X > 1}, call(G).\n")
    with pytest.raises(LogicException, match=r"existence_error\(procedure,\{\}/1\)"):
        ans(mod, "t")


def test_an_import_list_that_does_not_name_it_still_brings_it(native, ans):
    """The written ``{C}`` is lowered whatever the import list names, so its
    meta-called twin is imported with it."""
    mod = native.load("bm_list", ":- use_module(library(clpq), [entailed/1]).\n"
                                 "t(X) :- G = {X > 1}, call(G), X = 2.\n"
                                 "u(X) :- {X > 1}, X = 3.\n")
    assert ans(mod, "t") == [2]
    assert ans(mod, "u") == [3]


def test_an_import_list_that_names_it(native, ans):
    mod = native.load("bm_named", ":- use_module(library(clpq), [{}/1]).\n"
                                  "t(X) :- G = {X > 1}, call(G), X = 2.\n")
    assert ans(mod, "t") == [2]


def test_a_module_s_own_brace_predicate_wins(native, ans):
    """As in Scryer (which warns and uses the local clauses)."""
    mod = native.load("bm_own", HEADER + "{X} :- X = mine.\n"
                                "t(X) :- G = {X}, call(G).\n")
    assert ans(mod, "t") == ["mine"]


def test_a_local_brace_predicate_at_another_arity_loads(native, ans):
    mod = native.load("bm_other", HEADER + "'{}'(A, B) :- A = B.\n"
                                  "t(X) :- {X >= 3, X =< 3}, call({}, Y, z),"
                                  " Y == z, X = 3.\n")
    assert ans(mod, "t") == [3]


@pytest.mark.parametrize("goal, formal", [
    ("call({foo})", ("type_error", "constraint", "foo")),
    ("call({_})", ("instantiation_error",)),
])
def test_a_meta_called_block_that_is_no_constraint_raises(native, ans, goal,
                                                          formal):
    """The block builtin's own error terms (tests/test_clpq_error_terms.py);
    a WRITTEN non-constraint is refused at load."""
    mod = native.load("bm_err", HEADER + f"t(E) :- catch({goal}, error(E, _), true).\n")
    [got] = ans(mod, "t")
    got = got if type(got) is tuple else (got,)
    assert got[0] == formal[0] and got[1:] == formal[1:], got
