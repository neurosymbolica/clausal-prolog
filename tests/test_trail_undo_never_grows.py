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


# ── fix round 2: Python that PUSHES onto the trail while it is released ─────
#
# Re-review of 938db46a.  A release (an undo callback, a finaliser) can push
# a new entry.  Such an entry is live: it is never released twice, never
# read through another entry's fields, and never lost -- it stays on the
# trail above the mark, to be undone (or released) by a later undo.


def test_commit_fresh_keeps_an_entry_a_finaliser_pushes():
    """N1: the release loop read a pushed CALLBACK entry as an ATTR entry
    (a stale key/old_attr from the slot's previous entry)."""
    _ok(_run("""
        import sys
        from clausal.logic.variables import AttVar, Trail, put_attr
        t = Trail(); mark = t.mark(); floor = t.var_floor()
        key = ''.join(['k', 'xxx'])
        ran = []

        class D:
            def __del__(self):
                t.record(lambda: ran.append(1))
        v = AttVar(); put_attr(v, key, D(), t); put_attr(v, key, 2, t)
        before = sys.getrefcount(key)
        assert t.commit_fresh(mark, floor) is True
        assert sys.getrefcount(key) == before - 2, (before, sys.getrefcount(key))
        assert t.mark() == mark + 1          # the pushed callback is live
        t.undo(mark)
        assert ran == [1] and t.mark() == mark
        print("OK")
    """))


def test_an_undo_callback_that_re_records_itself_terminates():
    """A re-arming callback: undoing it records it again.  The undo releases
    the entries that were there when it started; the new one stays live."""
    _ok(_run("""
        import sys
        from clausal.logic.variables import Trail, Var, deref, is_var, unify
        t = Trail(); x = Var()
        calls = []

        def cb():
            calls.append(1)
            t.record(cb)
        t.record(cb)
        assert unify(x, 1, t)
        t.undo(0)
        assert calls == [1] and is_var(deref(x)) and t.mark() == 1
        t.undo(0)
        assert calls == [1, 1] and t.mark() == 1
        print("OK")
    """, timeout=60))


def test_an_entry_an_undo_callback_pushes_is_undone_later_not_leaked():
    _ok(_run("""
        import sys
        from clausal.logic.variables import Trail, Var, deref, is_var, unify
        t = Trail(); a, b = Var(), Var()
        log = []
        sentinel = object()
        base = sys.getrefcount(sentinel)

        def later(s=sentinel):
            log.append("later")

        def first():
            log.append("first")
            t.record(later)
        assert unify(a, 1, t)
        t.record(first)
        assert unify(b, 2, t)
        t.undo(0)
        # reverse order: b, first (pushes later), a; later stays live
        assert log == ["first"] and is_var(deref(a)) and is_var(deref(b))
        assert t.mark() == 1
        t.undo(0)
        assert log == ["first", "later"] and t.mark() == 0
        del later, first
        assert sys.getrefcount(sentinel) == base, (base, sys.getrefcount(sentinel))
        print("OK")
    """, timeout=60))


def test_clearing_a_trail_keeps_entries_a_finaliser_pushes():
    """Trail_clear (the GC's tp_clear) set length 0 and walked its own copy
    of the length; a release that pushed overwrote entries not yet reached,
    which were then released twice (and the pushed ones once too often).
    tp_clear is called directly through the type slot, as the GC calls it."""
    _ok(_run("""
        import ctypes, sys
        from clausal.logic.variables import AttVar, Trail, put_attr
        T = Trail
        word = lambda i: ctypes.c_void_p.from_address(id(T) + 8 * i).value
        # self-check of the PyTypeObject layout: word 3 tp_name, 22 tp_doc
        assert ctypes.c_char_p(word(3)).value == b'clausal.logic.variables.Trail'
        assert ctypes.c_char_p(word(22)).value.decode() == T.__doc__
        tp_clear = ctypes.PYFUNCTYPE(ctypes.c_int, ctypes.py_object)(word(24))

        t = Trail()
        pushed = []

        class D:
            def __del__(self):
                for _ in range(4):
                    cb = lambda: None
                    pushed.append(cb)
                    t.record(cb)
        keys = [''.join(['k', str(i), 'xxx']) for i in range(4)]
        v = AttVar()
        put_attr(v, 'd', D(), t)
        put_attr(v, 'd', 0, t)           # entry 1 holds the only ref to D
        for k in keys:
            put_attr(v, k, 1, t)         # entries 2.. are overwritten by a push
        before = [sys.getrefcount(k) for k in keys]
        assert tp_clear(t) == 0
        assert [sys.getrefcount(k) for k in keys] == [b - 1 for b in before]
        assert t.mark() == 4             # the four pushed callbacks are live
        # refs: the list, the comprehension's name, the argument, the trail
        counts = [sys.getrefcount(cb) for cb in pushed]
        assert counts == [4] * 4, counts
        t.undo(0)
        assert t.mark() == 0
        counts = [sys.getrefcount(cb) for cb in pushed]
        assert counts == [3] * 4, counts
        del t
        print("OK")
    """))


def test_commit_fresh_of_many_entries_keeps_a_pushed_entry():
    """The same, past commit_fresh's on-stack copy (16 entries)."""
    _ok(_run("""
        import sys
        from clausal.logic.variables import AttVar, Trail, Var, put_attr, unify
        t = Trail(); mark = t.mark(); floor = t.var_floor()
        key = ''.join(['k', 'xxx'])
        ran = []

        class D:
            def __del__(self):
                t.record(lambda: ran.append(1))
        v = AttVar(); put_attr(v, key, D(), t); put_attr(v, key, 2, t)
        for i in range(40):
            assert unify(Var(), i, t)
        before = sys.getrefcount(key)
        assert t.commit_fresh(mark, floor) is True
        assert sys.getrefcount(key) == before - 2, (before, sys.getrefcount(key))
        assert t.mark() == mark + 1
        t.undo(mark)
        assert ran == [1] and t.mark() == mark
        print("OK")
    """))
