"""Raw extension tests for _gprolog_ext.

Tests the Rust PyO3 layer directly, without the Python GnuProlog wrapper.

IMPORTANT: GNU Prolog only allows one engine per process lifetime (it
cannot be restarted after Pl_Stop_Prolog).  All tests share a single
machine via a session-scoped fixture.  Do NOT call close() on the
machine in tests — that would kill the engine for all subsequent tests.
"""
import pytest

try:
    import _gprolog_ext
    HAS_EXT = True
except ImportError:
    HAS_EXT = False

needs_ext = pytest.mark.skipif(not HAS_EXT, reason="gprolog extension not built")


@pytest.fixture(scope="session")
def machine():
    """Session-wide GNU Prolog machine.  Never closed."""
    if not HAS_EXT:
        pytest.skip("gprolog extension not built")
    try:
        return _gprolog_ext.RawGnuPrologMachine()
    except _gprolog_ext.GnuPrologError:
        pytest.skip("GNU Prolog singleton engine already in use by another test module")


@needs_ext
def test_raw_machine_creates(machine):
    # nv
    assert machine is not None


@needs_ext
def test_raw_singleton_enforcement(machine):
    """Cannot create a second engine while one exists."""
    # nv
    with pytest.raises(_gprolog_ext.GnuPrologError, match="cannot be restarted"):
        _gprolog_ext.RawGnuPrologMachine()


@needs_ext
def test_raw_consult_string(machine):
    # nv
    machine.consult_string("parent_raw(tom, bob).")
    results = list(machine.query("parent_raw(tom, X)."))
    assert len(results) == 1
    assert results[0]["X"] == "bob"


@needs_ext
def test_raw_arithmetic(machine):
    # nv
    sol = next(iter(machine.query("X is 2 + 3.")))
    assert sol["X"] == 5


@needs_ext
def test_raw_no_solutions(machine):
    # nv
    results = list(machine.query("fail."))
    assert results == []


@needs_ext
def test_raw_multiple_solutions(machine):
    # nv
    machine.consult_string("color_raw(red). color_raw(green). color_raw(blue).")
    results = list(machine.query("color_raw(X)."))
    assert [r["X"] for r in results] == ["red", "green", "blue"]


@needs_ext
def test_raw_lazy_iteration(machine):
    """Iterator is truly lazy — can close after first result."""
    # nv
    machine.consult_string("nr(1). nr(2). nr(3).")
    it = machine.query("nr(X).")
    first = next(it)
    assert first["X"] == 1
    # Close the iterator without consuming the rest
    it.close()
    # Machine should be available again
    second = list(machine.query("nr(X)."))
    assert len(second) == 3


@needs_ext
def test_raw_machine_busy_while_iterating(machine):
    """Cannot start a second query while one is active."""
    # nv
    machine.consult_string("nr2(1). nr2(2).")
    it = machine.query("nr2(X).")
    next(it)  # start iterating
    with pytest.raises(_gprolog_ext.GnuPrologError, match="busy"):
        machine.query("nr2(X).")
    # close the iterator, machine should be free
    it.close()
    results = list(machine.query("nr2(X)."))
    assert len(results) == 2


@needs_ext
def test_raw_list_term(machine):
    # nv
    sol = next(iter(machine.query("X = [1, 2, 3].")))
    assert sol["X"] == [1, 2, 3]


@needs_ext
def test_raw_compound_term(machine):
    # nv
    machine.consult_string("data_raw(point(1, 2)).")
    sol = next(iter(machine.query("data_raw(X).")))
    assert sol["X"] == ("point", 1, 2)


@needs_ext
def test_raw_float_term(machine):
    # nv
    sol = next(iter(machine.query("X is 1.5 + 2.5.")))
    assert sol["X"] == 4.0


@needs_ext
def test_raw_fd_constraint(machine):
    """GNU Prolog's built-in FD constraint solver."""
    # nv
    machine.consult_string(
        "solve_raw(X) :- fd_domain(X, 1, 5), X #> 3, fd_labeling([X])."
    )
    results = list(machine.query("solve_raw(X)."))
    values = [r["X"] for r in results]
    assert values == [4, 5]


@needs_ext
def test_raw_no_bindings(machine):
    """A ground goal returns an empty dict."""
    # nv
    sol = next(iter(machine.query("true.")))
    assert sol == {}
