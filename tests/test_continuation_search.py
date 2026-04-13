"""Tests for continuation_search.py"""
import pytest
from clausal.logic.continuation_search import Search, Finished


# ── Basic iteration ───────────────────────────────────────────────────────────

def test_empty():
    """A function that never emits produces no values."""
    # nv
    def fn(emit):
        pass

    assert list(Search(fn)) == []


def test_single_value():
    # nv
    def fn(emit):
        emit(42)

    assert list(Search(fn)) == [42]


def test_multiple_values():
    # nv
    def fn(emit):
        emit(1)
        emit(2)
        emit(3)

    assert list(Search(fn)) == [1, 2, 3]


def test_emission_order():
    """Values arrive in the order they were emitted."""
    # nv
    def fn(emit):
        for i in range(5):
            emit(i)

    assert list(Search(fn)) == [0, 1, 2, 3, 4]


def test_non_integer_values():
    # nv
    def fn(emit):
        emit("hello")
        emit(None)
        emit([1, 2, 3])

    assert list(Search(fn)) == ["hello", None, [1, 2, 3]]


# ── Iterator protocol ─────────────────────────────────────────────────────────

def test_for_loop():
    """Search works as the target of a for loop."""
    # nv
    def fn(emit):
        emit(10)
        emit(20)

    results = []
    for v in Search(fn):
        results.append(v)

    assert results == [10, 20]


def test_iterable_once():
    """Each iteration of a Search object runs the function fresh."""
    # nv
    def fn(emit):
        emit(1)
        emit(2)

    s = Search(fn)
    assert list(s) == [1, 2]
    assert list(s) == [1, 2]


# ── Interaction between worker and main ───────────────────────────────────────

def test_emit_during_computation():
    """Emit can be called from inside a loop in the worker."""
    # nv
    def fn(emit):
        total = 0
        for i in range(1, 6):
            total += i
            emit(total)

    assert list(Search(fn)) == [1, 3, 6, 10, 15]


def test_function_stored():
    """The wrapped function is accessible on the Search object."""
    # nv
    def fn(emit):
        pass

    s = Search(fn)
    assert s.function is fn


# ── Finished exception ────────────────────────────────────────────────────────

def test_finished_not_visible():
    """Finished is an internal signal; it must not propagate to the caller."""
    # nv
    def fn(emit):
        emit(1)

    try:
        list(Search(fn))
    except Finished:
        pytest.fail("Finished leaked out of Search.__iter__")


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_large_number_of_values():
    # nv
    n = 1000

    def fn(emit):
        for i in range(n):
            emit(i)

    assert list(Search(fn)) == list(range(n))


def test_emit_callable_is_first_arg():
    """The emit callback passed to the function must actually switch values."""
    # nv
    received_emit = []

    def fn(emit):
        received_emit.append(emit)
        emit(99)

    result = list(Search(fn))
    assert result == [99]
    assert callable(received_emit[0])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  {test.__name__} OK")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    import sys
    sys.exit(1 if failed else 0)
