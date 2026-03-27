"""Raw extension tests for _scryer_ext.

Tests the Rust PyO3 layer directly, without the Python Scryer wrapper.
"""
import pytest

try:
    import _scryer_ext
    HAS_EXT = True
except ImportError:
    HAS_EXT = False

needs_ext = pytest.mark.skipif(not HAS_EXT, reason="scryer extension not built")


@needs_ext
def test_raw_machine_creates():
    m = _scryer_ext.RawScryerMachine()
    assert m is not None


@needs_ext
def test_raw_query_iteration():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "parent(tom, bob).")
    results = list(m.query("parent(tom, X)."))
    assert len(results) == 1
    assert results[0]["X"] == "bob"


@needs_ext
def test_raw_arithmetic():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X is 2 + 3.")))
    assert sol["X"] == 5


@needs_ext
def test_raw_no_solutions():
    m = _scryer_ext.RawScryerMachine()
    results = list(m.query("fail."))
    assert results == []


@needs_ext
def test_raw_multiple_solutions():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "color(red). color(green). color(blue).")
    results = list(m.query("color(X)."))
    assert [r["X"] for r in results] == ["red", "green", "blue"]


@needs_ext
def test_raw_lazy_iteration():
    """Iterator is truly lazy — can break after first result."""
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "n(1). n(2). n(3).")
    it = m.query("n(X).")
    first = next(it)
    assert first["X"] == 1
    # Drop the iterator without consuming the rest
    del it
    # Machine should be available again
    second = list(m.query("n(X)."))
    assert len(second) == 3


@needs_ext
def test_raw_machine_busy_while_iterating():
    """Cannot start a second query while one is active."""
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "n(1). n(2).")
    it = m.query("n(X).")
    next(it)  # start iterating
    with pytest.raises(_scryer_ext.ScryerError, match="busy"):
        m.query("n(X).")
    # close the iterator, machine should be free
    it.close()
    results = list(m.query("n(X)."))
    assert len(results) == 2


@needs_ext
def test_raw_list():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X = [1, 2, 3].")))
    assert sol["X"] == [1, 2, 3]


@needs_ext
def test_raw_compound():
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "data(point(1, 2)).")
    sol = next(iter(m.query("data(X).")))
    from clausal.terms import Compound
    assert sol["X"] == Compound("point", (1, 2))


@needs_ext
def test_raw_large_integer():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X is 2 ^ 100.")))
    assert sol["X"] == 2**100


@needs_ext
def test_raw_exception():
    """Prolog errors become Python ScryerError exceptions."""
    m = _scryer_ext.RawScryerMachine()
    with pytest.raises(_scryer_ext.ScryerError):
        # Evaluating a non-numeric term should raise
        list(m.query("X is foo."))


@needs_ext
def test_raw_true_no_bindings():
    """A ground goal returns empty dict."""
    m = _scryer_ext.RawScryerMachine()
    results = list(m.query("true."))
    assert results == [{}]


@needs_ext
def test_raw_nested_list():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X = [[1, 2], [3, 4]].")))
    assert sol["X"] == [[1, 2], [3, 4]]


@needs_ext
def test_raw_empty_list():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X = [].")))
    assert sol["X"] == []


@needs_ext
def test_raw_float():
    m = _scryer_ext.RawScryerMachine()
    sol = next(iter(m.query("X is 1.0 + 2.5.")))
    assert abs(sol["X"] - 3.5) < 1e-10


@needs_ext
def test_raw_load_then_query_multiple_times():
    """Machine is reusable across multiple query cycles."""
    m = _scryer_ext.RawScryerMachine()
    m.load_module_string("user", "fact(a). fact(b).")
    r1 = list(m.query("fact(X)."))
    r2 = list(m.query("fact(X)."))
    assert r1 == r2
    assert len(r1) == 2
