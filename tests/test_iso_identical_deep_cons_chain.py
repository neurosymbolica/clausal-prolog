"""``==``/2 and ``\\==``/2 on a long improper list do not overflow the stack
(2026-10-12).

An improper list is a chain of cons cells ``'.'(H, T)`` -- one nested tuple
per element -- and ``==``'s numeric-type check walked it recursively in
Python: ``X == Y`` raised RecursionError at a few hundred cells.  Scryer
answers ``true`` (two 500-cell chains ``[1, ..., 500|foo]``).  The
check must still tell ``1`` from ``1.0`` inside the chain.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = """\
:- use_module(library(lists)).
upto(I, N, []) :- I > N.
upto(I, N, [I|T]) :- I =< N, J is I + 1, upto(J, N, T).
mk(N, End, X) :- upto(1, N, L), append(L, End, X).
eq(N) :- mk(N, foo, X), mk(N, foo, Y), X == Y.
ne(N) :- mk(N, foo, X), mk(N, bar, Y), X \\== Y.
float_tail(N) :- mk(N, [1|foo], X), mk(N, [1.0|foo], Y), X \\== Y.
"""


@pytest.mark.parametrize("frontend", ["translator", "native"])
@pytest.mark.parametrize("goal", [
    "eq(500)", "eq(20000)", "ne(500)", "float_tail(500)",
])
def test_identity_on_a_long_cons_chain(tmp_path, frontend, goal):
    (tmp_path / "chain.pl").write_text(PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [sys.executable, "-m", "clausal", "-g", goal, "chain.pl"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert (r.returncode, r.stdout) == (0, "true.\n"), r.stderr
