"""An undo is re-entrant: a finaliser that undoes the same trail mid-undo.

``trail_undo_to`` releases what each entry held, and a release can run
arbitrary Python (``__del__`` of a bound value, of a queued goal, of an
undo callback's closure; a weakref callback).  If that Python calls
``trail.undo(m)`` on the same trail, the nested undo must see only entries
the outer one has not taken yet, and the outer one must never release an
entry twice or raise the length back over entries the nested one released.
Filed as todo/done/trail-undo-is-not-re-entrant-2026-10-09.md.

Each case runs in a subprocess, so a crash is a failing test and not a dead
test run.
"""
from __future__ import annotations

import resource
import subprocess
import sys
import textwrap

import pytest


def _no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _run(*parts: str, timeout: int = 120) -> subprocess.CompletedProcess:
    src = "\n".join(textwrap.dedent(p) for p in parts)
    return subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, timeout=timeout,
                          preexec_fn=_no_core)


def _ok(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr[-2000:])
    assert proc.stdout.strip().endswith("OK"), proc.stdout


_PRELUDE = """
    import gc, sys
    from clausal.logic.variables import (
        AttVar, Trail, Var, deref, get_attr, is_var, put_attr, unify)
    t = Trail()
    fired = []

    class D:
        def __init__(self, mark):
            self.mark = mark
        def __del__(self):
            fired.append(self.mark)
            t.undo(self.mark)

    # Entries below and above the one whose release runs the finaliser, so
    # the nested undo has entries of its own to take and the outer one has
    # entries left after it.
    below = [Var() for _ in range(5)]
    above = [Var() for _ in range(5)]
"""

_EPILOGUE = """
    assert fired == [0], fired
    assert t.mark() == 0, t.mark()
    assert all(is_var(deref(v)) for v in below + above)
    t.undo(0)
    t.reset()
    del t
    gc.collect()
    print("OK")
"""

# Each case leaves exactly one reference to a D, owned by one trail entry,
# with plain bindings below and above it.
_CASES = {
    # TRAIL_BINDING: the undo DECREFs the value the variable was bound to.
    "binding": """
        for i, v in enumerate(below): assert unify(v, i, t)
        x = Var(); assert unify(x, D(0), t)
        for i, v in enumerate(above): assert unify(v, i, t)
    """,
    # TRAIL_ATTR: the undo of put_attr(k, 2) restores D into the dict and
    # the undo of put_attr(k, D) deletes it again, the last reference.
    "attr": """
        for i, v in enumerate(below): assert unify(v, i, t)
        av = AttVar(); put_attr(av, 'k', D(0), t); put_attr(av, 'k', 2, t)
        for i, v in enumerate(above): assert unify(v, i, t)
    """,
    # TRAIL_CALLBACK: the callback's closure holds the only D.
    "callback": """
        for i, v in enumerate(below): assert unify(v, i, t)
        def make(d=D(0)):
            return lambda: d
        t.record(make()); del make
        for i, v in enumerate(above): assert unify(v, i, t)
    """,
    # TRAIL_PENDING: the queue the undo of the push replaces holds the only
    # D.  The queue is taken again (a second TRAIL_PENDING entry) so the
    # bare unifies above do not drain it.
    "pending": """
        for i, v in enumerate(below): assert unify(v, i, t)
        class G:
            def __init__(self): self.d = D(0)
            def __call__(self):
                return iter(())
        t.push_pending(G()); t.take_pending()
        for i, v in enumerate(above): assert unify(v, i, t)
    """,
}


@pytest.mark.parametrize("kind", sorted(_CASES))
def test_a_finaliser_that_undoes_to_zero_mid_undo_does_not_crash(kind):
    _ok(_run(_PRELUDE, _CASES[kind], "t.undo(0)", _EPILOGUE))


@pytest.mark.parametrize("kind", sorted(_CASES))
def test_a_finaliser_that_undoes_mid_reset_does_not_crash(kind):
    _ok(_run(_PRELUDE, _CASES[kind], "t.reset()", _EPILOGUE))


def test_a_finaliser_that_undoes_to_a_higher_mark_mid_undo():
    """The nested undo's mark is above the outer one's: it takes nothing the
    outer undo has already taken, and the outer undo finishes the rest."""
    _ok(_run(_PRELUDE, """
    for i, v in enumerate(below): assert unify(v, i, t)
    x = Var(); assert unify(x, D(3), t)
    for i, v in enumerate(above): assert unify(v, i, t)
    t.undo(0)
    assert fired == [3], fired
    assert t.mark() == 0
    assert all(is_var(deref(v)) for v in below + above) and is_var(deref(x))
    print("OK")
    """))


def test_a_weakref_callback_that_undoes_mid_undo_does_not_crash():
    _ok(_run("""
        import weakref
        from clausal.logic.variables import Trail, Var, deref, is_var, unify
        t = Trail()
        class Obj: pass
        vs = [Var() for _ in range(10)]
        for i, v in enumerate(vs[:5]): assert unify(v, i, t)
        o = Obj(); r = weakref.ref(o, lambda _: t.undo(0))
        x = Var(); assert unify(x, o, t); del o
        for i, v in enumerate(vs[5:]): assert unify(v, i, t)
        t.undo(0)
        assert t.mark() == 0 and all(is_var(deref(v)) for v in vs + [x])
        print("OK")
    """))


def test_a_finaliser_that_undoes_mid_commit_fresh_does_not_crash():
    """commit_fresh releases the entries it drops; a finaliser there that
    undoes the trail must not see them."""
    _ok(_run(_PRELUDE, """
    for i, v in enumerate(below): assert unify(v, i, t)
    mark = t.mark(); floor = t.var_floor()
    av = AttVar(); put_attr(av, 'k', D(0), t); put_attr(av, 'k', 2, t)
    t.commit_fresh(mark, floor)
    assert fired == [0], fired
    assert t.mark() == 0 and all(is_var(deref(v)) for v in below)
    t.reset()
    print("OK")
    """))


def test_dropping_a_trail_releases_every_kind_of_entry_once():
    """Trail_dealloc releases each entry through trail_entry_release: every
    reference an entry of each kind held is dropped exactly once."""
    _ok(_run("""
        import sys
        from clausal.logic.variables import AttVar, Trail, Var, put_attr, unify
        val = object(); key = ''.join(['k', 'xxx']); fn = lambda: None
        goal = lambda: iter(())
        base = [sys.getrefcount(o) for o in (val, key, fn, goal)]
        t = Trail()
        x = Var(); assert unify(x, val, t); assert unify(Var(), x, t)
        av = AttVar(); put_attr(av, key, val, t); put_attr(av, key, 2, t)
        t.record(fn)
        t.push_pending(goal); t.take_pending()
        assert t.mark() >= 6
        del t, x, av
        after = [sys.getrefcount(o) for o in (val, key, fn, goal)]
        assert after == base, (base, after)
        print("OK")
    """))
