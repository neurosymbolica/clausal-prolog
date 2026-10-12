"""The trail survives Python that undoes it from inside a unification.

Security review of the bare-unify candidate (2026-10-12):

* F1: ``trail_undo_to`` set ``trail->length = mark`` at the end.  A hook or
  a woken goal that undid the trail BELOW the unification's mark had already
  released those entries; the unification's own undo then raised the length
  back over them, and the next undo released them a second time (a double
  DECREF, a segfault).  The undo now never grows the trail.
* F2: ``pending.drain`` nested one generator per generation of woken goals
  (``yield from drain(trail)``).  A bare unify keeps the first answer and
  drops the drain; dropping a deeply suspended chain recursed in C with no
  check, so a host that raised the recursion limit crashed.  The drain now
  keeps every generation on one explicit stack.

Each case runs in a subprocess, so a crash is a failing test and not a dead
test run.
"""
from __future__ import annotations

import resource
import subprocess
import sys
import textwrap


def _no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _run(src: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", textwrap.dedent(src)],
                          capture_output=True, text=True, timeout=timeout,
                          preexec_fn=_no_core)


def _ok(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr[-2000:])
    assert proc.stdout.strip().endswith("OK"), proc.stdout


def test_a_woken_goal_that_undoes_below_the_unify_does_not_crash():
    _ok(_run("""
        from clausal.logic.variables import (
            AttVar, Trail, Var, deref, is_var, put_attr, register_attr_hook, unify)
        import clausal.logic.pending
        t = Trail(); y = Var(); assert unify(y, 5, t)

        def h(v, b, tr):
            def g():
                tr.undo(0)
                return
                yield
            tr.push_pending(g)
            return True
        register_attr_hook('ku', h)
        x = AttVar(); put_attr(x, 'ku', 1, t)
        assert unify(x, 1, t) is False
        assert t.mark() == 0 and is_var(deref(y))
        t.undo(0)
        t.reset()
        print("OK")
    """))


def test_a_hook_that_undoes_below_the_unify_does_not_crash():
    _ok(_run("""
        from clausal.logic.variables import (
            AttVar, Trail, Var, deref, is_var, put_attr, register_attr_hook, unify)
        t = Trail(); y = Var(); assert unify(y, 5, t)

        def h(v, b, tr):
            tr.undo(0)
            return False
        register_attr_hook('ku', h)
        x = AttVar(); put_attr(x, 'ku', 1, t)
        assert unify(x, 1, t) is False
        assert t.mark() == 0 and is_var(deref(y)) and is_var(deref(x))
        t.undo(0)
        t.reset()
        print("OK")
    """))


def test_an_undo_callback_that_undoes_further_does_not_crash():
    _ok(_run("""
        from clausal.logic.variables import Trail, Var, deref, is_var, unify
        t = Trail(); a, b = Var(), Var()
        assert unify(a, 1, t)
        t.record(lambda: t.undo(0))
        assert unify(b, 2, t)
        t.undo(1)
        assert t.mark() == 0 and is_var(deref(a)) and is_var(deref(b))
        t.undo(0)
        print("OK")
    """))


_CHAIN = """
    import sys
    sys.setrecursionlimit({limit})
    from clausal.logic.coroutining import _freeze_var
    from clausal.logic.variables import Trail, Var, deref, unify
    n = {n}
    t = Trail()
    vs = [Var() for _ in range(n + 1)]
    for i in range(n):
        def g(a=vs[i], b=vs[i + 1]):
            if unify(b, deref(a), t):
                yield None
        _freeze_var(vs[i], g, t)
    assert unify(vs[0], "go", t)
    assert deref(vs[n]) == "go" and t.pending is None
    print("OK")
"""


def test_a_long_chain_of_woken_goals_under_a_raised_recursion_limit():
    _ok(_run(_CHAIN.format(limit=1_000_000, n=200_000), timeout=600))


def test_a_long_chain_of_woken_goals_at_the_default_recursion_limit():
    _ok(_run(_CHAIN.format(limit=1000, n=20_000)))
