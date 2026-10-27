"""``dif/2`` on cyclic (rational-tree) and very deep terms, row by row
against Scryer.

Until 2026-10-26 any ``dif/2`` that had to SUSPEND on a pair holding a
cyclic term raised ``error(resource_error(stack), _)`` ("_collect_free_vars:
term nesting too deep"): the trial unify terminated (it reaches the
engine's rational-tree unify), but the walk that collects the variables to
attach the constraint to was a recursive descent with no cycle memo.  Even
``X = f(X), dif(Y, X)`` -- a pair that must simply suspend on ``Y`` -- raised,
and so did a goal woken by ``freeze/2`` that posts such a ``dif``.  A pair
nested deeper than the descent's cap (two 100k-deep terms) raised the same.

The trial unify was also OCCURS-CHECKED, which answers for finite trees:
``dif(X, f(X))`` succeeded with nothing to suspend on, so a later
``X = f(X)`` (which ISO 7.3.2 lets ``=/2`` build) made the two sides one
rational tree with the constraint gone.  Scryer (and SICStus) suspend
there; ``dif/2`` (and the reified ``=/3`` / ``dif/3`` of library(reif))
now trial-unify as ``=/2`` does.

Every row is one ``.pl`` clause run under BOTH engines from the same text;
``yn/2`` reifies a goal as ``yes``/``no``/``error(E)`` so an error shows up
as a wrong ANSWER.  The rows also run in a child process under the
pure-Python trampoline and the pure-Python ``dif`` twin.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Var
from clausal.terms import term_writeq

from tests._oracles import run_scryer

_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEEP_N = 100_000

_PRELUDE = """\
:- use_module(library(dif)).
:- use_module(library(freeze)).
:- use_module(library(reif)).

yn(G, R) :- ( catch(G, E, R = error(E)) -> ( var(R) -> R = yes ; true ) ; R = no ).

nest(0, T, T).
nest(N, T, f(R)) :- N > 0, N1 is N-1, nest(N1, T, R).
"""

ROWS = [
    # The three reported repros: a dif that must suspend on a plain
    # variable against a cyclic term, and freeze waking one.
    ("v1", "yn((X = f(X), dif(_Y, X)), R)", "yes"),
    ("v2", "yn((X = f(X), dif(X, _Y)), R)", "yes"),
    ("v3", "yn((X4 = f(X4, 3), freeze(X4, (X2 = f(2, X4), dif(_X3, X2)))), R)", "yes"),
    # ... and the constraint they leave is live.
    ("v4", "yn((X = f(X), dif(Y, X), Y = f(Y)), R)", "no"),
    ("v5", "yn((X = f(X), dif(Y, X), Y = f(a)), R)", "yes"),
    ("v6", "yn((X = f(X), dif(X, Y), Y = X), R)", "no"),
    ("v7", "yn((X4 = f(X4, 3), freeze(X4, (X2 = f(2, X4), dif(X3, X2))), X3 = X2), R)", "no"),
    ("v8", "yn((X4 = f(X4, 3), freeze(X4, (X2 = f(2, X4), dif(X3, X2))), X3 = f(2, a)), R)", "yes"),
    # The todo's r1 and r2: a cyclic / a deep pair that must suspend.
    ("r1", "yn((X = f(X, _V), Y = f(Y, a), dif(X, Y)), R)", "yes"),
    ("r1a", "yn((X = f(X, V), Y = f(Y, a), dif(X, Y), V = a), R)", "no"),
    ("r1b", "yn((X = f(X, V), Y = f(Y, a), dif(X, Y), V = b), R)", "yes"),
    ("r2", f"yn((nest({DEEP_N}, _V, T1), nest({DEEP_N}, a, T2), dif(T1, T2)), R)", "yes"),
    ("r2a", f"yn((nest({DEEP_N}, V, T1), nest({DEEP_N}, a, T2), dif(T1, T2), V = a), R)", "no"),
    ("r2b", f"yn((nest({DEEP_N}, V, T1), nest({DEEP_N}, a, T2), dif(T1, T2), V = b), R)", "yes"),
    # Two cyclic terms: one rational tree (dif fails) or a ground
    # difference (dif succeeds, nothing to suspend on).
    ("t1", "yn((X = f(X), Y = f(Y), dif(X, Y)), R)", "no"),
    ("t2", "yn((X = f(X), Y = f(f(Y)), dif(X, Y)), R)", "no"),
    ("t3", "yn((X = f(X, a), Y = f(Y, b), dif(X, Y)), R)", "yes"),
    ("t4", "yn((X = f(X), Y = g(Y), dif(X, Y)), R)", "yes"),
    ("t5", "yn((X = [1|X], Y = [1, 1|Y], dif(X, Y)), R)", "no"),
    # The hook: both sides bound to cyclic terms after dif is posted.
    ("h1", "yn((dif(X, Y), X = f(X), Y = f(Y)), R)", "no"),
    ("h2", "yn((dif(X, Y), X = f(X), Y = g(Y)), R)", "yes"),
    ("h3", "yn((dif(X, Y), X = f(X), Y = f(_Z)), R)", "yes"),
    ("h4", "yn((dif(X, Y), X = f(X), Y = f(Z), Z = Y), R)", "no"),
    ("h5", "yn((dif(X, Y), X = f(X, a), Y = f(Y, B), B = a), R)", "no"),
    ("h6", "yn((dif(X, Y), X = f(X, a), Y = f(Y, B), B = b), R)", "yes"),
    # freeze waking dif on a cyclic term.
    ("f1", "yn((freeze(X, dif(_Y, X)), X = f(X)), R)", "yes"),
    ("f2", "yn((freeze(X, dif(Y, X)), X = f(X), Y = X), R)", "no"),
    ("f3", "yn((freeze(X, dif(Y, X)), X = f(X), Y = f(Y)), R)", "no"),
    # A rational tree is a solution: no occurs check in the trial.
    ("o1", "yn(dif(X, f(X)), R)", "yes"),
    ("o2", "yn((dif(X, f(X)), X = f(X)), R)", "no"),
    ("o3", "yn((X = f(X, V), dif(X, f(W, W)), W = X, V = X), R)", "no"),
    ("o4", "yn((X = f(X, V), dif(X, f(W, W)), W = X, V = a), R)", "yes"),
    ("o5", "yn((dif([X], [[X]]), X = [X]), R)", "no"),
    # \+ X = Y on the same pairs, for comparison.
    ("n1", "yn((X = f(X), \\+ X = _Y), R)", "no"),
    ("n2", "yn((X = f(X, _V), Y = f(Y, a), \\+ X = Y), R)", "no"),
    ("n3", "yn((X = f(X), Y = f(Y), \\+ X = Y), R)", "no"),
    ("n4", "yn((X = f(X, a), Y = f(Y, b), \\+ X = Y), R)", "yes"),
    ("n5", "yn((\\+ X = f(X)), R)", "no"),
    # library(reif): the reified forms trial-unify as dif does.
    ("q1", "findall(T, =(X, f(X), T), R)", "[true,false]"),
    ("q2", "findall(T, dif(X, f(X), T), R)", "[false,true]"),
    ("q3", "findall(T, (X = f(X), Y = f(Y), =(X, Y, T)), R)", "[true]"),
    ("q4", "findall(T, (X = f(X, a), Y = f(Y, b), =(X, Y, T)), R)", "[false]"),
]

_PROGRAM = _PRELUDE + "".join(f"{n}(R) :- {b}.\n" for n, b, _ in ROWS)

_VARNAME = re.compile(r"\b_[A-Za-z0-9]*\b")


def _normalise(text: str) -> str:
    return _VARNAME.sub("_", text.strip())


@pytest.fixture(scope="module")
def program_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("dif_cyclic") / "dif_cyclic_rows.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def mod(program_path):
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    try:
        return _load_module("_dif_cyclic_scryer_rows", str(program_path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


def _engine_answer(mod, name) -> str:
    r = Var()
    try:
        answers = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    except LogicException as exc:
        pytest.fail(f"{name}: uncaught {exc}")
    assert len(answers) == 1, (name, answers)
    return _normalise(answers[0])


@pytest.mark.parametrize("name,_body,expected", ROWS, ids=[r[0] for r in ROWS])
def test_dif_cyclic_engine(mod, name, _body, expected):
    assert _engine_answer(mod, name) == expected


@pytest.mark.parametrize("name,_body,expected", ROWS, ids=[r[0] for r in ROWS])
def test_dif_cyclic_scryer(scryer, program_path, name, _body, expected):
    del scryer
    proc = run_scryer(str(program_path), [f"{name}(R), writeq(R), nl, halt."], timeout=120)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines, (name, proc.stdout, proc.stderr[-500:])
    assert _normalise(lines[-1]) == expected


# ── both trampolines, and the pure-Python dif twin ──────────────────────────

_CHILD = textwrap.dedent(r'''
    import json, os, sys
    mode = sys.argv[1]
    if mode in ("py", "py_dif"):
        sys.modules["clausal.logic.runtime._trampoline"] = None
    if mode == "py_dif":
        sys.modules["clausal.logic._constraints_dif"] = None
    import clausal.import_hook
    from clausal.import_hook import _load_module
    import clausal.logic.trampoline as tr
    import clausal.logic.constraints as C
    from clausal.logic.solve import solve, _deref_walk
    from clausal.logic.variables import Var
    from clausal.terms import term_writeq
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    mod = _load_module(sys.argv[3], sys.argv[2])
    out = {"trampoline": tr.trampoline.__module__, "c_dif": C._USE_C_DIF}
    for name in json.loads(sys.argv[4]):
        r = Var()
        try:
            out[name] = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
        except Exception as exc:
            out[name] = ["raised " + type(exc).__name__ + ": " + str(exc)[:200]]
    print("RESULT", json.dumps(out))
''')


@pytest.mark.parametrize("mode", ["c", "py", "py_dif"],
                         ids=["c_trampoline", "python_trampoline", "python_dif_twin"])
def test_both_trampolines_and_the_python_twin(tmp_path, mode):
    name = f"_dif_cyclic_child_{mode}"
    path = tmp_path / f"{name}.pl"
    path.write_text(_PROGRAM, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, mode, str(path), name,
         json.dumps([r[0] for r in ROWS])],
        capture_output=True, text=True, timeout=600, env=env, cwd=str(tmp_path))
    lines = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    assert lines, (proc.stdout[-2000:], proc.stderr[-2000:])
    out = json.loads(lines[-1][len("RESULT "):])
    if mode == "c":
        assert out["trampoline"] == "clausal.logic.runtime._trampoline", out
        assert out["c_dif"] is True, out
    else:
        assert out["trampoline"] == "clausal.logic._trampoline_py", out
        assert out["c_dif"] is (mode == "py"), out
    wrong = {n: out[n] for n, _b, e in ROWS if [_normalise(a) for a in out[n]] != [e]}
    assert not wrong, wrong


# ── the residual a suspended dif leaves on an answer ────────────────────────

# Scryer's toplevel prints the same goals module-qualified and with the
# cycle unrolled to its print depth (``dif:dif(Y,f(f(f(...))))``); this
# toplevel prints a constraint unqualified (operator ruling 2026-10-24) and
# a cycle as writeq/1 writes it, which is Scryer's writeq text (``f(...)``).
RESIDUAL_ROWS = [
    ("X = f(X), dif(Y, X)", "X = f(...), dif(Y,f(...))."),
    ("X = f(X), dif(X, Y)", "X = f(...), dif(f(...),Y)."),
    ("dif(X, f(X))", "dif(X,f(X))."),
    ("X = f(X,V), Y = f(Y,a), dif(X,Y)",
     "X = f(...,V), Y = f(...,a), dif(f(...,V),f(...,a))."),
    ("dif(X,Y), X = f(X), Y = f(Z)", "X = f(...), Y = f(Z), dif(f(...),f(Z))."),
    ("X4 = f(X4,3), freeze(X4, (X2 = f(2,X4), dif(X3, X2)))",
     "X4 = f(...,3), X2 = f(2,f(...,3)), dif(X3,f(2,f(...,3)))."),
]


@pytest.mark.parametrize("goal,expected", RESIDUAL_ROWS, ids=[f"res{i}" for i in range(len(RESIDUAL_ROWS))])
def test_the_residual_text(tmp_path, goal, expected):
    path = tmp_path / "empty.pl"
    path.write_text(":- use_module(library(dif)).\n:- use_module(library(freeze)).\n",
                    encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "clausal", str(path), "-g", goal],
        capture_output=True, text=True, timeout=300, env=env, cwd=str(tmp_path))
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines and lines[-1].strip() == expected, (proc.stdout, proc.stderr[-1000:])
