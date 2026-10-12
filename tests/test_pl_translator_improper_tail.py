"""The default ``.pl`` translator keeps an improper list's tail as the tail
(2026-10-12).

``q(L) :- L = [x|foo].`` was emitted as the seam ``[x, *foo]``, which reads
the atom as one more element: ``L = [x,foo]``.  ISO, Scryer and Trealla give
``[x|foo]``, the cons cells ``'.'(x, foo)`` (D50), which is what the native
front end builds.  A tail that can be a list -- a variable, a list, a
``"..."`` read as chars or codes -- still splices.

Every expected line is what Scryer and Trealla print for the same program
(``writeq/1``).  Both front ends run the same program; they must agree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = """\
:- set_prolog_flag(double_quotes, {dq}).
a(L) :- L = [x|foo].
b(L) :- L = [x,y|foo].
c(L) :- L = [x|f(a)].
d(L) :- L = [x|1].
e(L) :- L = [x|Y], Y = [y,z].
f(L) :- L = [x|[y|foo]].
g(L) :- L = [x|[]].
h([x|foo]).
i(T) :- h([_|T]).
j(L) :- L = [x|"ab"].
k(L) :- L = [x|Y], Y = [y|Z], Z = [].
show(G) :- call(G, L), writeq(L), nl.
proper([]).
proper([_|T]) :- proper(T).
say(G, Yes, _) :- call(G), writeq(Yes), nl.
say(G, _, No) :- \\+ call(G), writeq(No), nl.
main :-
    show(a), show(b), show(c), show(d), show(e), show(f), show(g),
    show(h), show(i), show(j), show(k),
    a(A), say(proper(A), proper, improper),
    e(E), say(proper(E), proper, improper),
    say((a(X), X == [x|foo]), same, different),
    say((a(Y), Y = [x,foo]), two_elements, not_two_elements),
    say(length(A, _), has_length, no_length).
"""

EXPECTED_COMMON = [
    "[x|foo]", "[x,y|foo]", "[x|f(a)]", "[x|1]", "[x,y,z]", "[x,y|foo]",
    "[x]", "[x|foo]", "foo",
]
EXPECTED_J = {"chars": "[x,a,b]", "codes": "[x,97,98]", "atom": "[x|ab]"}
EXPECTED_TAIL = ["[x,y]", "improper", "proper", "same", "not_two_elements",
                 "no_length"]


def _run(tmp_path, dq, frontend):
    (tmp_path / "tails.pl").write_text(PROGRAM.format(dq=dq))
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "clausal", "tails.pl"], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("frontend", ["translator", "native"])
@pytest.mark.parametrize("dq", ["chars", "codes", "atom"])
def test_an_improper_tail_stays_the_tail(tmp_path, dq, frontend):
    r = _run(tmp_path, dq, frontend)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == (
        EXPECTED_COMMON + [EXPECTED_J[dq]] + EXPECTED_TAIL), r.stdout
