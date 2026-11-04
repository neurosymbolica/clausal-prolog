"""A rule asserted at run time that calls an undefined procedure: the call
raises ISO ``existence_error(procedure, Name/Arity)``, and ``catch/3``
catches it on every path that recompiles and runs the clause set.

Scryer, for the ``late`` module below::

    ?- t(A).
    A = [[1],[1,5],existence_error(procedure,nothere/1)].
    ?- w(C).
    C = caught(error(existence_error(procedure,nothere/1),nothere/1)).

``t2/1`` calls ``p/1`` once inside ``catch/3`` and once outside it, so the
second call's error leaves ``t2/1`` -- uncaught there, in Scryer too -- and
``w/1`` catches it one level up.  A Python caller of ``t2/1`` sees that
uncaught error as ``PredicateNotFoundError``, whose ``.term`` is the same
ISO term.  The ``unknown`` flag is read at the call: under ``fail`` and
``warning`` the undefined callee fails instead.

Both drive loops: the C core and the pure-Python twin (C extension blocked),
each in a child process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_LATE = """\
    :- module(late_unknown, [t/1, t2/1, w/1, paths/1, flags/1]).
    :- dynamic(p/1).
    :- dynamic(brandnew/1).
    :- dynamic(q/1).
    p(1).
    q(1).
    t(L) :- assertz((p(X) :- brandnew(X))), findall(X, p(X), A),
        assertz(brandnew(5)), findall(X, p(X), B),
        assertz((p(X) :- nothere(X))),
        catch(findall(X, p(X), C), error(E, _), C = E), L = [A, B, C].
    t2(L) :- assertz((p(X) :- later_dyn(X))),
        catch(findall(X, p(X), A), error(E, _), A = E),
        findall(X, p(X), B), L = [A, B].
    w(L) :- catch(t2(L), E, L = caught(E)).
    k(G, R) :- catch((G, R = ok), error(E, _), R = E).
    paths(L) :- assertz((q(X) :- \\+ nothere2(X))),
        findall(R, (member(G, [findall(X, p(X), _), \\+ p(9), once(p(2)),
                               forall(p(_), true), q(5), (p(Z), Z > 3),
                               bagof(X, p(X), _), setof(X, p(X), _)]),
                    k(G, R)), L).
    flags([F, W]) :-
        set_prolog_flag(unknown, fail), findall(X, p(X), F),
        set_prolog_flag(unknown, warning), findall(X, p(X), W),
        set_prolog_flag(unknown, error).
"""

_SCRIPT = r"""
import json, os, sys
sys.path.insert(0, REPO)
if BLOCK_C:
    sys.modules["clausal.logic.runtime._trampoline"] = None
os.environ["CLAUSAL_PL_FRONTEND"] = "native"
import importlib
import clausal
assert clausal.__file__.startswith(REPO), clausal.__file__
import clausal.logic.trampoline as tr
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.predicate_diagnostics import PredicateNotFoundError
sys.path.insert(1, TMP)
m = importlib.import_module("late_unknown")
out = {"drive": tr._drive_until_yield.__module__}
def ans(g):
    v = Var()
    return [repr(walk(v)) for _ in call(g, v, module=m)]
out["t"] = ans("t")
try:
    ans("t2")
    out["t2"] = "no error"
except PredicateNotFoundError as e:
    out["t2"] = repr(e.term[1])
for g in ("w", "paths", "flags"):
    out[g] = ans(g)
print("RESULT" + json.dumps(out))
"""


def _run(tmp_path, block_c):
    (tmp_path / "late_unknown.pl").write_text(textwrap.dedent(_LATE))
    code = (f"REPO = {_ROOT!r}\nTMP = {str(tmp_path)!r}\nBLOCK_C = {block_c!r}\n"
            + _SCRIPT)
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    [line] = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    return json.loads(line[len("RESULT"):])


def _exist(name):
    return repr(("existence_error", "procedure", ("/", name, 1)))


@pytest.mark.parametrize("block_c", [False, True], ids=["c-core", "python-twin"])
def test_asserted_rule_with_an_undefined_callee(tmp_path, block_c):
    out = _run(tmp_path, block_c)
    assert out.pop("drive") == ("clausal.logic._trampoline_py" if block_c
                                else "clausal.logic.runtime._trampoline")
    ex = ("existence_error", "procedure", ("/", "nothere", 1))
    assert out["t"] == [repr([[1], [1, 5], ex])]
    # the second findall of t2 is outside its catch: uncaught, ISO term
    assert out["t2"] == repr(ex)
    assert out["w"] == [repr(("caught", ("error", ex, ("/", "nothere", 1))))]
    assert out["paths"] == [repr([
        ex, ex, ex, ex,
        ("existence_error", "procedure", ("/", "nothere2", 1)),
        "ok", ex,       # p(Z), Z > 3: Z = 5, then on backtracking the bad clause
        ex, ex])], out["paths"]
    assert out["flags"] == [repr([[1, 5], [1, 5]])]
