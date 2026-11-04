"""clausal.logic.residuals: the one computation of an answer's residual
goals, which the answer printers and copy_term/3 both read.

The CLP(Q) goals are terms now, and the printers write them; the text must
be what ``residual_q`` writes, under either solver.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CLPQ_GOALS = [
    "{X >= 2}",
    "{X > 2}",
    "{X < 3}",
    "{X =\\= 2}",
    "{X + Y = 3}",
    "{2*X + Y =< 16, X >= 0, Y >= 0}",
    "{X - Y > 1/2}",
    "{-X - Y >= -4}",
    "{3*X - 5/2*Y = 7}",
    "{X >= 2, X =< 3}",
    "{X + Y + Z = 10, X - Y >= 1}",
    "{X = 2*Y}, {Y >= 1}",
]

_CHILD = textwrap.dedent(r'''
    import sys
    from clausal import solve
    from clausal.cli import _goal_reader_ops, _read_goal, _term_vars
    from clausal.logic import clpq
    from clausal.logic.residuals import clpq_residuals
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Var
    from clausal.testing import load_clausal_module
    path = sys.argv[1]
    mod = load_clausal_module(path)
    ops = _goal_reader_ops(open(path).read())
    bad = []
    for text in sys.argv[2:]:
        goal, shown = _read_goal(text, ops)
        for trail in solve(("call", goal), module=mod):
            names, free = {}, {}
            for name, v in shown:
                w = _deref_walk(v)
                if isinstance(w, Var):
                    names[id(w)] = name
                _term_vars(w, free)
            name_of = lambda v: names[id(v)]
            want = clpq.residual_q(list(free.values()), trail, name_of)
            got = [r.render(None, name_of)
                   for r in clpq_residuals(list(free.values()), trail)]
            if got != want or not want:
                bad.append((text, want, got))
            break
    print(bad)
    sys.exit(1 if bad else 0)
''')


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_clpq_goals_print_as_residual_q_writes_them(tmp_path, solver):
    prog = tmp_path / "prog.pl"
    prog.write_text(":- use_module(library(clpq)).\n")
    env = dict(os.environ)
    env["CLAUSAL_CLPQ"] = solver
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(prog), *CLPQ_GOALS],
        env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_clpb_formula_reads_back_as_the_same_network():
    """The sat/1 goal of a network is a formula over +, * and ~ that sat/1
    reads, with the same models."""
    from clausal.logic.clpb import sat
    from clausal.logic.residuals import clpb_residuals
    from clausal.logic.variables import Trail, Var
    from clausal.logic.builtins.inspection import _copy_term_impl
    from itertools import product

    t = Trail()
    x, y, z = Var(), Var(), Var()
    assert sat(("+", ("*", x, y), ("#", y, z)), t)
    [item] = clpb_residuals([x, y, z])
    functor, formula = item.goal
    assert functor == "sat"
    var_map: dict = {}
    copy = _copy_term_impl(formula, var_map)
    a, b, c = (var_map[id(v)] for v in (x, y, z))
    assert sat(copy, t)

    def models(vs):
        out = []
        for values in product((0, 1), repeat=3):
            mark = t.mark()
            from clausal.logic.variables import unify
            if all(unify(v, n, t) for v, n in zip(vs, values)):
                out.append(values)
            t.undo(mark)
        return out
    assert models([x, y, z]) == models([a, b, c]) == [
        v for v in product((0, 1), repeat=3)
        if (v[0] and v[1]) or (v[1] ^ v[2])]


def test_sat_reads_library_clpb_connectives():
    """sat/1 takes the connectives of library(clpb) written as terms, as a
    .pl or .clausal program writes them: + * # ~ =:= =\\= =< >= < >."""
    from clausal.logic.clpb import sat
    from clausal.logic.variables import Trail, Var, deref
    cases = [
        (("*", "X", "Y"), (1, 1)),
        (("~", ("+", "X", "Y")), (0, 0)),
        (("<", "X", "Y"), (0, 1)),
        ((">", "X", "Y"), (1, 0)),
        (("*", ("=:=", "X", 1), ("=\\=", "X", "Y")), (1, 0)),
        (("*", ("=<", 1, "X"), (">=", 0, "Y")), (1, 0)),
        (("*", ("#", "X", 1), ("#", "Y", 0)), (0, 1)),
    ]
    bad = []
    for formula, want in cases:
        t = Trail()
        x, y = Var(), Var()

        def fill(f):
            if f == "X":
                return x
            if f == "Y":
                return y
            if type(f) is tuple:
                return (f[0], *map(fill, f[1:]))
            return f
        if not sat(fill(formula), t) or (deref(x), deref(y)) != want:
            bad.append((formula, want, (deref(x), deref(y))))
    assert not bad, bad
