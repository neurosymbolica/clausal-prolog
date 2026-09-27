"""Stress tests for free-threaded Python compatibility.

These tests verify that Clausal's C extensions are safe under concurrent
access. They pass under GIL-enabled builds too (threads just serialize).
Under free-threaded builds (python3.13t+), they exercise true parallelism.
"""

import sys
import threading
import pytest

from clausal.logic.variables import (
    Var, Trail, deref, walk, is_var, unify, register_attr_hook,
    unregister_attr_hook, put_attr, get_attr,
)


def is_free_threaded():
    """True if running on a free-threaded Python build."""
    return hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()


# -- 1. Concurrent Var creation: unique IDs -----------------------------------

class TestConcurrentVarCreation:
    """Multiple threads creating Vars must get globally unique var_ids."""

    def test_unique_ids_under_contention(self):
        # nv
        NUM_THREADS = 8
        VARS_PER_THREAD = 10_000
        all_ids: list[set[int]] = [set() for _ in range(NUM_THREADS)]
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            barrier.wait()  # synchronize start for maximum contention
            for _ in range(VARS_PER_THREAD):
                v = Var()
                all_ids[idx].add(v._id)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All IDs globally unique
        merged = set()
        for s in all_ids:
            assert len(s) == VARS_PER_THREAD, "Thread lost some Var IDs"
            overlap = merged & s
            assert not overlap, f"Duplicate var IDs across threads: {overlap}"
            merged |= s

        assert len(merged) == NUM_THREADS * VARS_PER_THREAD


# -- 2. Concurrent independent unification ------------------------------------

class TestConcurrentUnification:
    """Each thread runs unification on its own Vars and Trail.
    No shared variables -- tests that the C extension doesn't corrupt
    internal state under concurrent calls."""

    def test_independent_unify_threads(self):
        # nv
        NUM_THREADS = 8
        ITERS = 5_000
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            barrier.wait()
            for i in range(ITERS):
                trail = Trail()
                x, y, z = Var(), Var(), Var()
                # unify(x, [y, z]) then unify(y, 42) then unify(z, "hello")
                assert unify(x, [y, z], trail)
                assert unify(y, 42, trail)
                assert unify(z, "hello", trail)
                assert walk(x) == [42, "hello"]
                assert deref(y) == 42
                assert deref(z) == "hello"
                # Undo and verify
                trail.undo(0)
                assert is_var(x)
                assert is_var(y)
                assert is_var(z)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_unify_shared_ground_terms(self):
        """Multiple threads unify their own Vars against the same ground list."""
        # nv
        NUM_THREADS = 8
        shared_ground = [1, 2, [3, 4], "five"]
        barrier = threading.Barrier(NUM_THREADS)
        results = [None] * NUM_THREADS

        def worker(idx):
            barrier.wait()
            trail = Trail()
            x = Var()
            assert unify(x, shared_ground, trail)
            results[idx] = deref(x)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for r in results:
            assert r == shared_ground


# -- 3. Concurrent attr hook registration -------------------------------------

class TestConcurrentAttrHooks:
    """Tests register/unregister_attr_hook under contention."""

    def test_concurrent_register_unregister(self):
        # nv
        NUM_THREADS = 8
        ITERS = 2_000
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            key = f"test_hook_{idx}"
            barrier.wait()
            for i in range(ITERS):
                register_attr_hook(key, lambda av, bt, t: True)
                unregister_attr_hook(key)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_hook_fires_under_contention(self):
        """Register a hook, then unify AttVars from multiple threads."""
        # nv
        hook_calls = []
        lock = threading.Lock()

        def counting_hook(attr_val, bound_to, trail):
            with lock:
                hook_calls.append(attr_val)
            return True

        register_attr_hook("test_counting", counting_hook)
        try:
            NUM_THREADS = 4
            ITERS = 500
            barrier = threading.Barrier(NUM_THREADS)

            def worker(idx):
                barrier.wait()
                for i in range(ITERS):
                    trail = Trail()
                    v = Var()
                    put_attr(v, "test_counting", idx * 10000 + i, trail)
                    unify(v, 99, trail)

            threads = [threading.Thread(target=worker, args=(i,))
                       for i in range(NUM_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(hook_calls) == NUM_THREADS * ITERS
        finally:
            unregister_attr_hook("test_counting")


# -- 4. Concurrent read-only queries against shared Database ------------------

class TestConcurrentDatabaseReads:
    """Multiple threads resolve goals against the same compiled Database."""

    def test_concurrent_call(self):
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.database import Clause, Module
        from clausal.logic.solve import call
        from clausal.terms import Unify as Is

        mod = Module("test_concurrent")
        db = mod.db

        # assertz 100 facts: num(0), num(1), ..., num(99)
        for i in range(100):
            v = Var()
            db.assertz(Clause(
                head=("num", v),
                body=[Is(left=v, right=i)],
            ))
        compile_predicate_trampoline("num", 1,
                                     db.clauses_for("num", 1), db)

        NUM_THREADS = 8
        barrier = threading.Barrier(NUM_THREADS)
        results = [None] * NUM_THREADS

        def worker(idx):
            barrier.wait()
            solutions = []
            x = Var()
            for trail in call("num", x, module=mod):
                solutions.append(deref(x))
            results[idx] = sorted(solutions)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = list(range(100))
        for r in results:
            assert r == expected, f"Thread got wrong results: {r[:5]}..."


# -- 5. Trail isolation -------------------------------------------------------

class TestTrailIsolation:
    """Verify that Trail objects are independent -- undo on one
    trail doesn't affect variables bound via another trail."""

    def test_two_trails_independent(self):
        # nv
        x = Var()
        t1, t2 = Trail(), Trail()

        unify(x, 42, t1)
        assert deref(x) == 42

        t1.undo(0)
        assert is_var(x)

        unify(x, "hello", t2)
        assert deref(x) == "hello"

        t2.undo(0)
        assert is_var(x)

    def test_cross_thread_trail_raises(self):
        """Using a Trail from a different thread must raise RuntimeError."""
        # nv
        trail = Trail()
        error = [None]

        def worker():
            try:
                x = Var()
                unify(x, 42, trail)  # trail owned by main thread
                error[0] = "Expected RuntimeError but unify succeeded"
            except RuntimeError as e:
                if "different thread" in str(e):
                    error[0] = None  # expected
                else:
                    error[0] = f"Wrong error: {e}"
            except Exception as e:
                error[0] = f"Wrong exception type: {type(e).__name__}: {e}"

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert error[0] is None, error[0]

    def test_cross_thread_trail_undo_raises(self):
        """Calling undo on a Trail from a different thread must raise."""
        # nv
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        error = [None]

        def worker():
            try:
                trail.undo(0)
                error[0] = "Expected RuntimeError but undo succeeded"
            except RuntimeError as e:
                if "different thread" in str(e):
                    error[0] = None
                else:
                    error[0] = f"Wrong error: {e}"
            except Exception as e:
                error[0] = f"Wrong exception type: {type(e).__name__}: {e}"

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert error[0] is None, error[0]


# -- 6. C extension presence ---------------------------------------------------

class TestCExtensionPresence:
    """Verify that the C extensions are loaded, not the Python fallbacks."""

    def test_variables_is_c_extension(self):
        """_variables must be a C extension module."""
        # nv
        from clausal.logic.variables import _variables
        # C extension modules have a __file__ ending in .so/.pyd/.dylib
        assert hasattr(_variables, '__file__'), "_variables has no __file__"
        ext = _variables.__file__
        assert ext.endswith(('.so', '.pyd', '.dylib')), (
            f"_variables is not a C extension: {ext}"
        )

    def test_trampoline_is_c_extension(self):
        """_trampoline must be a C extension module, and trampoline.py must use it."""
        # nv
        from clausal.logic.trampoline import StepGenerator
        # If the C extension is loaded, StepGenerator's module is _trampoline
        assert StepGenerator.__module__ == '_trampoline', (
            f"StepGenerator came from {StepGenerator.__module__}, "
            f"expected _trampoline (C extension not loaded?)"
        )

    def test_trampoline_stepgen_has_continuation_slots(self):
        """C StepGenerator must expose the three continuation slots."""
        # nv
        from clausal.logic.trampoline import StepGenerator, DONE

        def dummy(this_gen, _proceed, _fail, _catcher):
            yield (_fail, DONE)

        sg = StepGenerator(dummy, None, None, None)
        for attr in ("proceed", "fail", "catcher"):
            assert hasattr(sg, attr), f"StepGenerator missing {attr!r} attribute"
            assert getattr(sg, attr) is None
