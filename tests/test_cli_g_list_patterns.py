"""``clausal FILE -g GOAL`` reads ``[H|T]`` patterns and anonymous variables
the way ISO does (2026-10-12).

The ``-g`` reader handed the engine the reader's cons cells ``'.'(H, T)``
for every ``[...|T]`` in a goal, and a proper list never unifies with a
cons cell, so ``X = [1,2], X = [_|T]`` answered ``false``.  The todo that
reported it blamed ``_`` (``X = [1,_,3], X = [_,C|_]``); the reader already
gives each ``_`` its own variable.  These cases pin both: every list-tail
shape, and ``_`` used several times, inside compounds and lists, across
several ``-g`` goals, with ``_X`` still a shared named variable.

Every expected answer below is what Scryer and Trealla give for the goal.
Each runs the real command against a ``.pl`` program (translator and native
front ends) and a ``.clausal`` program.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE = "p(C) :- X = [1,_,3], X = [_,C|_].\n"

#: (file, CLAUSAL_PL_FRONTEND) -- every front end the CLI runs.
FRONT_ENDS = [("prog.pl", "translator"), ("prog.pl", "native"),
              ("prog.clausal", None)]


def _clausal(tmp_path, front, *goals):
    name, frontend = front
    (tmp_path / name).write_text(SOURCE)
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    env["CLAUSAL_ALLOW_PL"] = "1"       # a .pl file loads only with this or --prolog
    if frontend:
        env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    argv = [a for g in goals for a in ("-g", g)]
    return subprocess.run(
        [sys.executable, "-m", "clausal", *argv, name], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=120)


@pytest.fixture(params=FRONT_ENDS, ids=lambda f: f[1] or "clausal")
def front(request):
    return request.param


@pytest.mark.parametrize("goal, answer", [
    # The todo's goal: `_` three times, in two lists.
    ("X = [1,_,3], X = [_,C|_]", "X = [1,C,3]."),
    ("X = [1,2], X = [_|T]", "X = [1,2], T = [2]."),
    ("X = [1,2,3], X = [B,C|D]", "X = [1,2,3], B = 1, C = 2, D = [3]."),
    # `_` inside a compound inside a compound, and as a list's head.
    ("X = f(_,g(_,[_|T]),_), X = f(1,g(2,[3,4]),5)",
     "X = f(1,g(2,[3,4]),5), T = [4]."),
    # Two `_` are two variables: [_,_] has length 2, not 1.
    ("X = [_,_], X = [ab,cd]", "X = [ab,cd]."),
    ("X = [_,_], X = [_,_,_]", "false."),
    # `_X` is a NAMED variable: both occurrences are one variable, and it
    # is not printed.
    ("X = [_X,_X], X = [1,Y]", "X = [1,1], Y = 1."),
    ("X = [_X,_X], X = [1,2]", "false."),
    ("_ = 1, _ = 2", "true."),
    # Named variables share as before.
    ("X = Y, Y = [ab|T], T = []", "X = [ab], Y = [ab], T = []."),
])
def test_g_list_patterns_and_anonymous_variables(tmp_path, front, goal,
                                                 answer):
    r = _clausal(tmp_path, front, goal)
    assert r.stdout == answer + "\n", (r.stdout, r.stderr)
    assert r.returncode == (1 if answer == "false." else 0)


@pytest.mark.parametrize("goal, answer", [
    ("X = [x|foo]", "X = [x|foo]."),
    ("X = [x,y|f(a)], X = [_,_|T]", "X = [x,y|f(a)], T = f(a)."),
    ("X = [_,_|foo], X = [1,2|U]", "X = [1,2|foo], U = foo."),
    ("X = [x|foo], X = [x,f,o,o]", "false."),
    # A tail that can be a list still splices.
    ("L = [x|V], V = [yy]", "L = [x,yy], V = [yy]."),
    ('X = [1|"ab"]', "X = [1,a,b]."),
])
def test_g_improper_list_tails(tmp_path, front, goal, answer):
    r = _clausal(tmp_path, front, goal)
    assert r.stdout == answer + "\n", (r.stdout, r.stderr)


def test_g_anonymous_variables_across_several_goals(tmp_path, front):
    r = _clausal(tmp_path, front,
                 "X = [_,_], X = [1,2]",
                 "Y = [_|_], Y = [ab]",
                 "p(C), C == C",
                 "Z = f(_,_,_), Z = f(1,2,3)")
    assert r.returncode == 0, r.stderr
    assert r.stdout == ("X = [1,2].\nY = [ab].\ntrue.\n"
                        "Z = f(1,2,3).\n"), r.stdout
