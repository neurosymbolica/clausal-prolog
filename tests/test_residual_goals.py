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


def _models(variables, trail):
    """The 0/1 assignments to *variables* the store on *trail* allows."""
    from itertools import product
    from clausal.logic.variables import unify
    out = []
    for values in product((0, 1), repeat=len(variables)):
        mark = trail.mark()
        if all(unify(v, n, trail) for v, n in zip(variables, values)):
            out.append(values)
        trail.undo(mark)
    return out


def test_clpb_shared_nodes_call_back_to_the_same_constraint():
    """A chain sat(A+B), sat(B+C), ... has a BDD whose nodes are shared;
    its goals spell each shared node once, as a helper variable, and
    calling them on fresh variables allows exactly the same assignments."""
    from clausal.logic.clpb import sat
    from clausal.logic.residuals import clpb_residuals
    from clausal.logic.variables import Trail, Var
    from clausal.logic.builtins.inspection import _copy_term_impl

    t = Trail()
    xs = [Var() for _ in range(7)]
    for a, b in zip(xs, xs[1:]):
        assert sat(("+", a, b), t)
    goals = [item.goal for item in clpb_residuals(xs)]
    assert any(g[1][0] == "=:=" for g in goals), goals    # a helper is used
    var_map: dict = {}
    copies = _copy_term_impl(goals, var_map)
    ys = [var_map[id(x)] for x in xs]
    for g in copies:
        assert sat(g[1], t)
    want = _models(xs, t)
    assert want and _models(ys, t) == want


def test_a_variable_no_goal_mentions_stays_boolean():
    """sat(X+Y), Y = 1 leaves X free but Boolean: sat(X=:=X), as Scryer."""
    from clausal.logic.clpb import sat
    from clausal.logic.residuals import clpb_residuals
    from clausal.logic.variables import Trail, Var, unify

    t = Trail()
    x, y = Var(), Var()
    assert sat(("+", x, y), t)
    assert unify(y, 1, t)
    goals = [item.goal for item in clpb_residuals([x])]
    assert len(goals) == 1 and goals[0][0] == "sat"
    eq, a, b = goals[0][1]
    assert eq == "=:=" and a is x and b is x


def test_clpb_chain_of_100_prints_in_linear_size(tmp_path):
    """The goals of a chain of 100 sat/1 constraints are linear in the
    BDD: the printer answers within seconds, in a few kilobytes (a tree
    spelling printed 982K characters at 24 and did not finish at 100)."""
    import time
    prog = tmp_path / "chain.clausal"
    prog.write_text("sats([]).\nsats([_]).\n"
                    "sats([A,B|T]) :- sat(A + B), sats([B|T]).\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "clausal.cli", str(prog),
         "-g", "length(L, 100), sats(L)",
         "-g", "length(L, 100), sats(L), copy_term(L, C, Gs)"],
        env=env, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - start
    assert proc.returncode == 0, proc.stderr
    first, second = proc.stdout.splitlines()
    assert first.count("sat(") == 98      # the root, 97 shared nodes
    assert len(first) < 10_000, len(first)
    assert second.count("sat(") == 2 * 98    # Gs, then the residuals
    assert len(second) < 25_000, len(second)
    assert elapsed < 60, elapsed


def test_legacy_names_unprojected_variables_after_the_answer(tmp_path):
    """Where legacy's projection gives up, the printer names its internal
    variables as legacy's dump_q does: _Q3 after two answer variables."""
    prog = tmp_path / "prog.pl"
    prog.write_text(":- use_module(library(clpq)).\n")
    child = textwrap.dedent(r'''
        import sys
        from clausal.logic.clpq import legacy
        legacy._project = lambda constraints, targets: None   # gives up
        from clausal import solve
        from clausal.cli import _answer, _goal_reader_ops, _read_goal
        from clausal.logic.solve import _deref_walk
        from clausal.testing import load_clausal_module
        mod = load_clausal_module(sys.argv[1])
        goal, shown = _read_goal("{X >= 1, Y >= X + 2, X + Y =< 9}",
                                 _goal_reader_ops(""))
        for trail in solve(("call", goal), module=mod):
            names = {id(_deref_walk(v)): n for n, v in shown}
            want = ", ".join(legacy.residual_q(
                [_deref_walk(v) for _, v in shown], trail,
                lambda v: names[id(v)]))
            got = _answer(shown, trail)
            print(got)
            sys.exit(0 if got == want and "_Q3" in got else 1)
    ''')
    env = dict(os.environ)
    env["CLAUSAL_CLPQ"] = "legacy"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c", child, str(prog)], env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
