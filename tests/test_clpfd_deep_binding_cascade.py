"""A binding that cascades down a long chain of CLP(FD) constraints.

Binding one end of ``X1 #= X0 + 1, X2 #= X1 + 1, ...`` fixes every link.
Each link used to be fixed by a nested call: the narrowing that made the
next variable a singleton bound it, the binding ran the FD attribute hook,
and the hook propagated the next link -- one level of C stack per link, so
a chain of a few thousand links overflowed the C stack and the process
died with SIGSEGV.  The cascade now runs in the propagation queue that
narrowed the variable, so its depth does not grow with the chain.

Every case runs in a child process: a regression is a crash, and a crash
must fail one test, not kill the run.
"""
import os
import subprocess
import sys
import textwrap

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code: str, tmp_path, files: dict[str, str] | None = None):
    for name, text in (files or {}).items():
        (tmp_path / name).write_text(textwrap.dedent(text))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [_ROOT, str(tmp_path)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", textwrap.dedent(code)],
        capture_output=True, text=True, timeout=600, env=env, cwd=str(tmp_path))


def _check(proc, expected: str):
    assert proc.returncode == 0, (
        f"child exited {proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}")
    assert proc.stdout.strip().splitlines()[-1] == expected, proc.stdout[-2000:]


@pytest.mark.parametrize("links", [20000])
def test_python_chain_binding_cascades_without_crashing(tmp_path, links):
    proc = _run(f"""
        import clausal
        from clausal.logic.clpfd import fd_eq
        from clausal.logic.variables import Var, Trail, unify, deref
        n = {links}
        t = Trail()
        xs = [Var() for _ in range(n + 1)]
        for i in range(n):
            assert fd_eq(xs[i + 1], ('+', xs[i], 1), t)
        print(unify(xs[0], 0, t), deref(xs[n]), deref(xs[n // 2]))
    """, tmp_path)
    _check(proc, f"True {links} {links // 2}")


def test_python_chain_cascade_still_fails_on_a_conflict(tmp_path):
    # The last link must differ from the value the cascade gives it (#\=
    # prunes nothing from an unbounded domain, so only the cascade can
    # find the conflict): the binding fails and undoes every link.
    proc = _run("""
        import clausal
        from clausal.logic.clpfd import fd_eq, fd_ne
        from clausal.logic.variables import Var, Trail, unify, deref, is_var
        n = 20000
        t = Trail()
        xs = [Var() for _ in range(n + 1)]
        for i in range(n):
            assert fd_eq(xs[i + 1], ('+', xs[i], 1), t)
        assert fd_ne(xs[n], n, t)
        ok = unify(xs[0], 0, t)
        print(ok, is_var(deref(xs[n])), is_var(deref(xs[1])))
    """, tmp_path)
    _check(proc, "False True True")


_SEAM = """\
    -module(deep_cascade_seam, [top/1])

    deep(0, 0),
    deep(N, D) <- (D > 0, N1 == N - 1, D1 == D - 1, deep(N1, D1))
    top(N) <- deep(N, 6000)
"""

_CLAUSAL = """\
    :- module(deep_cascade_cl, [top/1]).
    :- use_module(library(clpz)).
    deep(0, 0).
    deep(N, D) :- D > 0, N1 #= N - 1, D1 is D - 1, deep(N1, D1).
    top(N) :- deep(N, 6000).
    :- end_module(deep_cascade_cl).
"""

_PL = """\
    :- module(deep_cascade_pl, [top/1]).
    :- use_module(library(clpz)).
    deep(0, 0).
    deep(N, D) :- D > 0, N1 #= N - 1, D1 is D - 1, deep(N1, D1).
    top(N) :- deep(N, 6000).
"""


@pytest.mark.parametrize("module, filename, source", [
    ("deep_cascade_seam", "deep_cascade_seam.seam", _SEAM),
    ("deep_cascade_cl", "deep_cascade_cl.clausal", _CLAUSAL),
    ("deep_cascade_pl", "deep_cascade_pl.pl", _PL),
], ids=["seam", "clausal", "pl"])
def test_program_chain_cascade_on_every_surface(tmp_path, module, filename, source):
    proc = _run(f"""
        import importlib
        import clausal
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref, walk
        m = importlib.import_module({module!r})
        v = Var()
        print([walk(deref(v)) for _ in call('top', v, module=m)])
    """, tmp_path, {filename: source})
    _check(proc, "[6000]")


def test_a_nest_of_binding_hooks_past_the_stack_budget_raises(tmp_path):
    # Not CLP(FD): a user hook that binds the next variable of a chain nests
    # one attribute-hook dispatch per link.  With CPython's recursion limit
    # raised out of the way, the dispatch's own C stack budget stops it with
    # RecursionError -- resource_error(stack) to a program -- not a crash.
    proc = _run("""
        import sys
        import clausal
        sys.setrecursionlimit(10 ** 6)
        from clausal.logic.variables import (
            Var, Trail, unify, deref, put_attr, register_attr_hook)
        n = 50000
        t = Trail()
        xs = [Var() for _ in range(n + 1)]
        def hook(nxt, value, trail):
            return unify(nxt, deref(value) + 1, trail)
        register_attr_hook("chain_test", hook)
        for i in range(n):
            put_attr(xs[i], "chain_test", xs[i + 1], t)
        try:
            unify(xs[0], 0, t)
            print("no error")
        except RecursionError as e:
            print("RecursionError", "attribute hooks nested" in str(e))
    """, tmp_path)
    _check(proc, "RecursionError True")
