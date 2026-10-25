"""findall/3, bagof/3, setof/3 and aggregate_all/3 copy a list built through
its open tail with every element read through its bindings.

``L = [a|R], kk(3, X), R = [c(X), d]``: ``L`` is a partial list whose hole
``R`` is bound, later, to a list holding ``X``.  The walk that closes the
partial list (``SegList._walk_raw``) took the hole's list as it stood and did
not walk its elements, so the copy findall/3 keeps held the live ``X``,
unbound again once findall backtracked: ``[[a,c(_),d]]`` where 1.0.0 and
Scryer answer ``[[a,c(yes),d]]``.  Calling ``g(L)`` directly was right
(the answer walk walks the elements it is handed).

The ``.pl`` rows against Scryer are in
tests/iso/test_findall_partial_list_scryer.py; this file pins the ``.clausal``
surface, both trampolines, and the Python entry (``solve`` + ``Var.value`` /
``_deref_walk``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.terms import term_writeq

_ROOT = Path(__file__).resolve().parent.parent

_PROGRAM = """\
kk(3, yes).
kk(7, no).

g(L) :- L = [a|R], N = 3, kk(N, X), append([c(X)], [d], R).
g4(L) :- L = [a|R], N = 3, kk(N, X), R = [c(X), d].

r_findall(R) :- findall(L, g(L), R).
r_unify_tail(R) :- findall(L, g4(L), R).
r_pair(R) :- findall(L-X, (L = [a|T], kk(3, X), append([c(X)], [d], T)), R).
r_deeper(R) :- findall(L, (L = [a|T], X = yes, T = [c(f(X))]), R).
r_several(R) :- findall(L, (L = [a,b|T], X = 1, Y = 2, T = [X,c(Y),[X]]), R).
r_two_steps(R) :- findall(L, (L = [a|T], T = [c(X)|U], X = yes, U = [d(X)]), R).
r_append_partial(R) :- findall(L, (append([a], T, L), X = yes, T = [c(X)]), R).
r_bagof(R) :- bagof(L, T^X^(L = [a|T], kk(3, X), T = [c(X)]), R).
r_setof(R) :- setof(L, T^X^N^(L = [a|T], kk(N, X), T = [c(X)]), R).
r_aggregate_bag(R) :- aggregate_all(bag(L), g(L), R).
r_aggregate_set(R) :- aggregate_all(set(L), (kk(_, X), L = [a|T], T = [c(X)]), R).
r_cyclic_tail(R) :- findall(L, (L = [a|T], Y = f(Y), T = [Y]), [[a,Z]]), Z = f(W), functor(W, R, _).
r_cyclic_head(R) :- findall(L, (L = [Y|T], Y = f(Y), T = []), [[Z]]), Z = f(W), functor(W, R, _).
"""

ROWS = [
    ("r_findall", "[[a,c(yes),d]]"),
    ("r_unify_tail", "[[a,c(yes),d]]"),
    ("r_pair", "[[a,c(yes),d]-yes]"),
    ("r_deeper", "[[a,c(f(yes))]]"),
    ("r_several", "[[a,b,1,c(2),[1]]]"),
    ("r_two_steps", "[[a,c(yes),d(yes)]]"),
    ("r_append_partial", "[[a,c(yes)]]"),
    ("r_bagof", "[[a,c(yes)]]"),
    ("r_setof", "[[a,c(no)],[a,c(yes)]]"),
    ("r_aggregate_bag", "[[a,c(yes),d]]"),
    ("r_aggregate_set", "[[a,c(no)],[a,c(yes)]]"),
    # A cyclic element: copied as the cyclic term (the iterative walk).
    ("r_cyclic_tail", "f"),
    ("r_cyclic_head", "f"),
]

_SUFFIXES = [".pl", ".clausal"]


def _load(tmp_dir: Path, suffix: str):
    name = "_findall_partial_list_" + suffix.lstrip(".")
    path = tmp_dir / f"{name}{suffix}"
    path.write_text(_PROGRAM, encoding="utf-8")
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    try:
        return _load_module(name, str(path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


@pytest.fixture(scope="module", params=_SUFFIXES, ids=lambda s: s.lstrip("."))
def mod(request, tmp_path_factory):
    return _load(tmp_path_factory.mktemp("findall_snapshot"), request.param)


def _answer(mod, name):
    r = Var()
    answers = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    assert len(answers) == 1, (name, answers)
    return answers[0]


@pytest.mark.parametrize("name,expected", ROWS, ids=[r[0] for r in ROWS])
def test_the_copy_follows_the_bindings_inside_a_closed_partial_list(mod, name, expected):
    assert _answer(mod, name) == expected


def test_the_python_entry_reads_the_snapshot(mod):
    """``solve`` from Python: the findall list through ``Var.value`` and
    ``_deref_walk``, and the direct call through ``_deref_walk``, are plain
    data with ``yes`` in.  (``Var.value`` of the direct call is one step:
    the partial list itself, as in 1.0.0.)"""
    ls, l = Var(), Var()
    sols = []
    for _ in solve(("findall", l, ("g", l), ls), mod):
        sols.append((ls.value, _deref_walk(ls)))
    assert sols == [([["a", ("c", "yes"), "d"]], [["a", ("c", "yes"), "d"]])]
    l = Var()
    direct = [_deref_walk(l) for _ in solve(("g", l), mod)]
    assert direct == [["a", ("c", "yes"), "d"]]


_CHILD = textwrap.dedent(r'''
    import json, os, sys
    if sys.argv[1] == "py":
        # The pure-Python trampoline and the Python _deref_walk twin.
        sys.modules["clausal.logic.runtime._trampoline"] = None
        sys.modules["clausal.logic._tabling_core"] = None
    import clausal.import_hook
    from clausal.import_hook import _load_module
    import clausal.logic.trampoline as tr
    from clausal.logic.solve import solve, _deref_walk
    from clausal.logic.variables import Var
    from clausal.terms import term_writeq
    os.environ["CLAUSAL_PL_FRONTEND"] = "native"
    mod = _load_module(sys.argv[3], sys.argv[2])
    out = {"trampoline": tr.trampoline.__module__,
           "walk": getattr(_deref_walk, "__module__", None) or "c"}
    for name in json.loads(sys.argv[4]):
        r = Var()
        out[name] = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    print("RESULT", json.dumps(out))
''')


@pytest.mark.parametrize("mode", ["c", "py"], ids=["c_trampoline", "python_trampoline"])
@pytest.mark.parametrize("suffix", _SUFFIXES, ids=lambda s: s.lstrip("."))
def test_both_trampolines(tmp_path, mode, suffix):
    name = f"_findall_partial_list_child_{suffix.lstrip('.')}"
    path = tmp_path / f"{name}{suffix}"
    path.write_text(_PROGRAM, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, mode, str(path), name,
         json.dumps([r[0] for r in ROWS])],
        capture_output=True, text=True, timeout=300, env=env, cwd=str(tmp_path))
    lines = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    assert lines, (proc.stdout[-2000:], proc.stderr[-2000:])
    out = json.loads(lines[-1][len("RESULT "):])
    if mode == "py":
        assert out["trampoline"] == "clausal.logic._trampoline_py", out
        assert out["walk"] == "clausal.logic.solve", out
    else:
        assert out["trampoline"] == "clausal.logic.runtime._trampoline", out
    for name, expected in ROWS:
        assert out[name] == [expected], (name, out[name])
