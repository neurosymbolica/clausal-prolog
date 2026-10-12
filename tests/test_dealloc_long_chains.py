"""Freeing a very long chain of engine objects must not overflow the C stack.

A C ``tp_dealloc`` that drops its reference to another object of the same
type recurses once per link.  Without CPython's trashcan
(``Py_TRASHCAN_BEGIN``/``END``) a long enough chain runs off the end of the
C stack and the process dies with SIGSEGV, typically inside the cycle
collector ("Garbage-collecting / <no Python frame>").

Two engine chains reach this:

- StepGenerator -> ``catcher`` -> StepGenerator ...: a 1M-deep recursion
  such as ``recl(1000000, V)`` keeps one StepGenerator per level alive in
  the suspended answer.
- Var/AttVar -> ``binding`` -> Var ...: a binding chain.

Each case runs in a subprocess, since a regression kills the interpreter.
The fast cases cap the child's stack (RLIMIT_STACK) so that a modest chain
is enough to overflow it; the end-to-end cases run the real 1M programs at
the default stack and are slow, so they need CLAUSAL_SLOW_TESTS=1.
"""

import os
import resource
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

_SLOW = pytest.mark.skipif(
    os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
    reason="end-to-end 1M-element answers take ~1 min; set CLAUSAL_SLOW_TESTS=1",
)

# Small enough that the chains below overflow it without the trashcan
# (measured: 100k-link chains die at 2 MiB), large enough for the
# interpreter itself.
_CAPPED_STACK = 2 * 1024 * 1024


# Every child names the C extensions it loaded, so a test cannot pass
# against some other tree's engine (a shared venv's editable install, or a
# script directory on sys.path[0]).
_ENGINE_PRELUDE = (
    "import clausal.logic.runtime._trampoline as _t, "
    "clausal.logic.variables._variables as _v\n"
    "print('ENGINE', _t.__file__)\n"
    "print('ENGINE', _v.__file__)\n"
    "del _t, _v\n"
)


def _run(code, *, stack=None, timeout=600):
    def _cap():
        # Never leave a core file behind -- set first, so no early return
        # below can skip it.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if stack is not None:
            _soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
            if hard != resource.RLIM_INFINITY and hard < stack:
                return
            resource.setrlimit(resource.RLIMIT_STACK, (stack, hard))

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c",
         _ENGINE_PRELUDE + textwrap.dedent(code)],
        cwd=str(_ROOT), env=env, preexec_fn=_cap,
        capture_output=True, text=True, timeout=timeout)
    return proc


def _assert_clean(proc, marker):
    assert proc.returncode == 0, (
        f"exit {proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\n"
        f"stderr:\n{proc.stderr[-2000:]}")
    assert marker in proc.stdout, proc.stdout[-2000:]
    engines = [line.split(" ", 1)[1] for line in proc.stdout.splitlines()
               if line.startswith("ENGINE ")]
    assert len(engines) == 2, proc.stdout[-2000:]
    for path in engines:
        assert Path(path).resolve().is_relative_to(_ROOT), (
            f"child loaded {path}, not this tree's engine under {_ROOT}")


# ── fast: the chains themselves, capped stack ────────────────────────────────

def test_stepgenerator_catcher_chain_frees_by_refcount():
    # An acyclic chain (the body returns a non-generator), so ``del`` frees
    # it link by link through StepGen_dealloc with the collector off.
    proc = _run("""
        import gc
        gc.disable()
        from clausal.logic.runtime._trampoline import StepGenerator
        body = lambda this, proceed, fail, catcher: 0
        head = None
        for _ in range(200_000):
            head = StepGenerator(body, None, None, head)
        del head
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


def test_stepgenerator_proceed_chain_frees_by_refcount():
    proc = _run("""
        import gc
        gc.disable()
        from clausal.logic.runtime._trampoline import StepGenerator
        body = lambda this, proceed, fail, catcher: 0
        head = None
        for _ in range(200_000):
            head = StepGenerator(body, head, None, None)
        del head
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


def test_stepgenerator_catcher_chain_freed_by_collector():
    # The crash's shape: the chain hangs off a reference cycle (here the
    # leaf's own generator result holds the leaf), so only the cycle
    # collector frees it; its tp_clear on the leaf then drops the whole
    # acyclic catcher chain behind it in one cascade.  The collector
    # clears in allocation order, so the leaf is allocated FIRST: cleared
    # last, it would find every ancestor already cleared and nothing would
    # cascade.
    proc = _run("""
        import gc
        gc.disable()
        from clausal.logic.runtime._trampoline import StepGenerator
        plain = lambda this, proceed, fail, catcher: 0
        cyclic = lambda this, proceed, fail, catcher: [this]
        head = StepGenerator.__new__(StepGenerator)
        root = None
        for _ in range(200_000):
            root = StepGenerator(plain, None, None, root)
        head.__init__(cyclic, None, None, root)
        del root
        del head
        gc.collect()
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


def test_stepgenerator_instances_release_their_heap_type():
    # StepGenerator is a heap type: every instance owns a reference to its
    # type (PyType_GenericAlloc takes it), which its tp_dealloc must give
    # back, and its tp_traverse must visit.  subtype_dealloc/traverse leave
    # both to a heap base.  Otherwise each freed instance leaks one type
    # reference, and a Python subclass is never collected.
    proc = _run("""
        import gc, sys, weakref
        from clausal.logic.runtime._trampoline import StepGenerator
        body = lambda this, proceed, fail, catcher: 0

        class Sub(StepGenerator):
            pass

        for cls in (StepGenerator, Sub):
            gc.collect()
            before = sys.getrefcount(cls)
            for _ in range(100_000):
                cls(body, None, None, None)
            gc.collect()
            delta = sys.getrefcount(cls) - before
            assert delta == 0, (cls.__name__, delta)

        def make():
            class Dyn(StepGenerator):
                pass
            keep = [Dyn(body, None, None, None) for _ in range(10)]
            # A cycle through the instance's generator result, so freeing
            # it goes through the collector and tp_traverse as well.
            cyc = Dyn(lambda this, p, f, c: [this], None, None, None)
            # A cycle THROUGH the type (class -> instance -> its type): only
            # tp_traverse visiting Py_TYPE(self) lets the collector see it.
            Dyn.instance = Dyn(body, None, None, None)
            del keep, cyc
            return weakref.ref(Dyn)

        ref = make()
        gc.collect()
        assert ref() is None, "dynamic StepGenerator subclass never collected"
        print("TYPEREF_OK")
    """)
    _assert_clean(proc, "TYPEREF_OK")


@pytest.mark.parametrize("kind", ["Var", "AttVar"])
def test_var_binding_chain_frees_by_refcount(kind):
    # unify() binds through the deref'd root, so binding in reverse order is
    # what builds a deep chain: v[n-1] -> v[n-2] -> ... -> v[0].
    proc = _run(f"""
        import gc
        gc.disable()
        from clausal.logic.variables import Var, AttVar, Trail, unify, deref
        n = 200_000
        vs = [{kind}() for _ in range(n)]
        trail = Trail()
        for i in reversed(range(n - 1)):
            assert unify(vs[i], vs[i + 1], trail)
        ends = (vs[0], vs[-1])
        def depth(v):
            d = 0
            while True:
                nxt = [r for r in gc.get_referents(v) if isinstance(r, Var)]
                if not nxt:
                    return d
                v, d = nxt[0], d + 1
        keep = max(ends, key=depth)
        assert depth(keep) == n - 1, depth(keep)
        del vs, trail, ends
        del keep
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


# ── slow: the reported programs, default stack ───────────────────────────────

_PROGRAM = """\
recl(0, []).
recl(N, [f(N)|T]) :- N > 0, M is N - 1, recl(M, T).
rec(0, []).
rec(N, [a|T]) :- N > 0, M is N - 1, rec(M, T).
"""


def _solve_and_exit(tmp_path, goal, n):
    src = tmp_path / "long_answer.clausal"
    src.write_text(_PROGRAM)
    return _run(f"""
        from clausal.logic.solve import solve
        from clausal.logic.variables import Var
        from clausal.testing import load_clausal_module
        m = load_clausal_module({str(src)!r})
        v = Var()
        assert next(solve(({goal!r}, {n}, v), m), None) is not None
        print("SOLVED")
    """)


@_SLOW
def test_million_element_answer_exits_cleanly(tmp_path):
    _assert_clean(_solve_and_exit(tmp_path, "recl", 1_000_000), "SOLVED")


@_SLOW
def test_half_million_char_text_answer_exits_cleanly(tmp_path):
    _assert_clean(_solve_and_exit(tmp_path, "rec", 500_000), "SOLVED")
