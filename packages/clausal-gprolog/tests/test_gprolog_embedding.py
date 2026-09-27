"""Test the embedded GNU Prolog engine via the Python GnuProlog API.

These tests verify the full pipeline: .clausal source is translated to Prolog
by the existing clausal_to_prolog machinery, loaded into an in-process GNU
Prolog engine, queried, and results converted back to Python values.

Requires the _gprolog_ext extension to be built (maturin develop --release).

IMPORTANT: GNU Prolog only allows one engine per process lifetime.  All tests
share a single GnuProlog session via a session-scoped fixture.  Do NOT close
the session in tests.
"""
import textwrap

import pytest

from clausal.gprolog import AVAILABLE

needs_gprolog = pytest.mark.skipif(not AVAILABLE, reason=(
    "gprolog extension not built; see implementation_plans/GPROLOG_EMBEDDING.md"
))


@pytest.fixture(scope="session")
def g():
    """Session-wide GnuProlog instance.  Never closed."""
    if not AVAILABLE:
        pytest.skip("gprolog extension not built")
    from clausal.gprolog import GnuProlog
    return GnuProlog()


# ── Basics ────────────────────────────────────────────────────────


@needs_gprolog
class TestGnuPrologBasics:
    """Core query functionality."""

    def test_true(self, g):
        # nv
        assert g.query_bool("true.")

    def test_fail(self, g):
        # nv
        assert not g.query_bool("fail.")
        assert g.query_one("fail.") is None

    def test_fact_and_query(self, g):
        # nv
        g.consult_string("parent_e(tom, bob).")
        assert g.query_one("parent_e(tom, X).") == {"X": "bob"}

    def test_multiple_solutions(self, g):
        # nv
        g.consult_string("color_e(red). color_e(green). color_e(blue).")
        results = g.query_all("color_e(X).")
        assert [r["X"] for r in results] == ["red", "green", "blue"]

    def test_arithmetic(self, g):
        # nv
        assert g.query_one("X is 2 + 3.") == {"X": 5}
        assert g.query_one("X is 10 mod 3.") == {"X": 1}

    def test_list_unification(self, g):
        # nv
        sol = g.query_one("X = [1, 2, 3].")
        assert sol["X"] == [1, 2, 3]

    def test_compound_term(self, g):
        # nv
        g.consult_string("data_e(point(1, 2)).")
        sol = g.query_one("data_e(X).")
        assert sol["X"] == ("point", 1, 2)

    def test_no_bindings_goal(self, g):
        """A goal that succeeds with no variables returns empty dict."""
        # nv
        assert g.query_one("true.") == {}

    def test_iterator_protocol(self, g):
        """query() returns a lazy iterator, not a list."""
        # nv
        g.consult_string("ne(1). ne(2). ne(3).")
        it = g.query("ne(X).")
        assert next(it)["X"] == 1
        assert next(it)["X"] == 2
        assert next(it)["X"] == 3
        with pytest.raises(StopIteration):
            next(it)

    def test_early_break(self, g):
        """Can break out of iteration early — machine is released."""
        # nv
        g.consult_string("ne2(1). ne2(2). ne2(3). ne2(4). ne2(5).")
        for sol in g.query("ne2(X)."):
            if sol["X"] == 3:
                break
        # Machine should be usable again after the for loop
        assert g.query_one("ne2(1).") == {}


# ── Rules and recursion ──────────────────────────────────────────


@needs_gprolog
class TestGnuPrologRules:
    """Rules, recursion, and multi-clause predicates."""

    def test_simple_rule(self, g):
        # nv
        g.consult_string(textwrap.dedent("""\
            parent_r(tom, bob).
            parent_r(bob, ann).
            grandparent_r(X, Z) :- parent_r(X, Y), parent_r(Y, Z).
        """))
        assert g.query_one("grandparent_r(tom, X).") == {"X": "ann"}

    def test_recursive_rule(self, g):
        # nv
        g.consult_string(textwrap.dedent("""\
            edge_r(a, b). edge_r(b, c). edge_r(c, d).
            path_r(X, Y) :- edge_r(X, Y).
            path_r(X, Y) :- edge_r(X, Z), path_r(Z, Y).
        """))
        results = g.query_all("path_r(a, X).")
        assert set(r["X"] for r in results) == {"b", "c", "d"}

    def test_append(self, g):
        # nv
        sol = g.query_one("append([1, 2], [3, 4], X).")
        assert sol["X"] == [1, 2, 3, 4]

    def test_member(self, g):
        # nv
        results = g.query_all("member(X, [a, b, c]).")
        assert [r["X"] for r in results] == ["a", "b", "c"]

    def test_length(self, g):
        # nv
        sol = g.query_one("length([a, b, c], N).")
        assert sol["N"] == 3


# ── FD Constraints ───────────────────────────────────────────────


@needs_gprolog
class TestGnuPrologFD:
    """GNU Prolog's built-in finite domain constraint solver."""

    def test_fd_domain_and_labeling(self, g):
        # nv
        g.consult_string(
            "solve_fd1(X) :- fd_domain(X, 1, 3), fd_labeling([X])."
        )
        results = g.query_all("solve_fd1(X).")
        assert [r["X"] for r in results] == [1, 2, 3]

    def test_fd_constraint_operators(self, g):
        # nv
        g.consult_string(textwrap.dedent("""\
            solve_fd2(X) :-
                fd_domain(X, 1, 10),
                X #> 7,
                fd_labeling([X]).
        """))
        results = g.query_all("solve_fd2(X).")
        assert [r["X"] for r in results] == [8, 9, 10]

    def test_fd_equality_constraint(self, g):
        # nv
        g.consult_string(textwrap.dedent("""\
            solve_fd3(X, Y) :-
                fd_domain([X, Y], 1, 5),
                X + Y #= 5,
                X #< Y,
                fd_labeling([X, Y]).
        """))
        results = g.query_all("solve_fd3(X, Y).")
        assert results == [{"X": 1, "Y": 4}, {"X": 2, "Y": 3}]

    def test_fd_all_different(self, g):
        # nv
        g.consult_string(textwrap.dedent("""\
            solve_fd4(X, Y, Z) :-
                fd_domain([X, Y, Z], 1, 3),
                fd_all_different([X, Y, Z]),
                X #< Y, Y #< Z,
                fd_labeling([X, Y, Z]).
        """))
        results = g.query_all("solve_fd4(X, Y, Z).")
        assert results == [{"X": 1, "Y": 2, "Z": 3}]


# ── Clausal source translation ───────────────────────────────────


@needs_gprolog
class TestGnuPrologClausal:
    """Loading .clausal source through the translation pipeline."""

    def test_consult_clausal_fact(self, g):
        # nv
        g.consult_clausal("ParentC(tom, bob),")
        assert g.query_one("parent_c(tom, X).") == {"X": "bob"}

    def test_consult_clausal_rule(self, g):
        # nv
        g.consult_clausal(textwrap.dedent("""\
            parent_c2(tom, bob)
            parent_c2(bob, ann)
            grandparent_c2(X, _z) <- (parent_c2(X, _y), parent_c2(_y, _z))
        """))
        assert g.query_one("grandparent_c2(tom, X).") == {"X": "ann"}


# ── to_prolog helper ─────────────────────────────────────────────


@needs_gprolog
class TestGnuPrologBridge:
    """Test the to_prolog() value serializer."""

    def test_to_prolog_int(self):
        # nv
        from clausal.gprolog import to_prolog
        assert to_prolog(42) == "42"

    def test_to_prolog_str(self):
        # nv
        from clausal.gprolog import to_prolog
        assert to_prolog("hello") == "'hello'"

    def test_to_prolog_list(self):
        # nv
        from clausal.gprolog import to_prolog
        assert to_prolog([1, 2, 3]) == "[1, 2, 3]"

    def test_to_prolog_bool(self):
        # nv
        from clausal.gprolog import to_prolog
        assert to_prolog(True) == "true"
        assert to_prolog(False) == "false"

    def test_to_prolog_none(self):
        # nv
        from clausal.gprolog import to_prolog
        assert to_prolog(None) == "[]"

    def test_to_prolog_in_query(self, g):
        # nv
        from clausal.gprolog import to_prolog
        g.consult_string("double_e(X, Y) :- Y is X * 2.")
        result = g.query_one(f"double_e({to_prolog(21)}, Y).")
        assert result == {"Y": 42}
