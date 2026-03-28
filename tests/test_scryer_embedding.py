"""Test the embedded Scryer Prolog engine via the Python Scryer API.

These tests verify the full pipeline: .clausal source is translated to Prolog
by the existing clausal_to_prolog machinery, loaded into an in-process Scryer
machine, queried, and results converted back to Python values.

Requires the _scryer_ext extension to be built (maturin develop --release).
"""
import textwrap
from pathlib import Path

import pytest

from clausal.scryer import AVAILABLE

needs_scryer = pytest.mark.skipif(not AVAILABLE, reason=(
    "scryer extension not built; run: cd prolog_backends/scryer && maturin develop --release"
))


# ── Basics ────────────────────────────────────────────────────────


@needs_scryer
class TestScryerBasics:
    """Core query functionality."""

    def test_true(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_bool("true.")

    def test_fail(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert not s.query_bool("fail.")
            assert s.query_one("fail.") is None

    def test_fact_and_query(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("parent(tom, bob).")
            assert s.query_one("parent(tom, X).") == {"X": "bob"}

    def test_multiple_solutions(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("color(red). color(green). color(blue).")
            results = s.query_all("color(X).")
            assert [r["X"] for r in results] == ["red", "green", "blue"]

    def test_arithmetic(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_one("X is 2 + 3.") == {"X": 5}
            assert s.query_one("X is 10 mod 3.") == {"X": 1}

    def test_list_unification(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [1, 2, 3].")
            assert sol["X"] == [1, 2, 3]

    def test_compound_term(self):
        from clausal.scryer import Scryer
        from clausal.terms import Compound
        with Scryer() as s:
            s.load_string("data(point(1, 2)).")
            sol = s.query_one("data(X).")
            assert sol["X"] == Compound("point", (1, 2))

    def test_no_bindings_goal(self):
        """A goal that succeeds with no variables returns empty dict."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            assert s.query_one("true.") == {}

    def test_iterator_protocol(self):
        """query() returns a lazy iterator, not a list."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("n(1). n(2). n(3).")
            it = s.query("n(X).")
            assert next(it)["X"] == 1
            assert next(it)["X"] == 2
            assert next(it)["X"] == 3
            with pytest.raises(StopIteration):
                next(it)

    def test_early_break(self):
        """Can break out of iteration early — machine is released."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("n(1). n(2). n(3). n(4). n(5).")
            for sol in s.query("n(X)."):
                if sol["X"] == 3:
                    break
            # Machine should be usable again after the for loop
            assert s.query_one("n(1).") == {}

    def test_machine_busy_during_iteration(self):
        """Cannot load or query while an iterator is active."""
        from clausal.scryer import Scryer
        import _scryer_ext
        with Scryer() as s:
            s.load_string("n(1). n(2).")
            it = s.query("n(X).")
            next(it)  # start iterating
            with pytest.raises(_scryer_ext.ScryerError, match="busy"):
                s.load_string("n(99).")
            with pytest.raises(_scryer_ext.ScryerError, match="busy"):
                s.query("true.")
            # Closing the iterator frees the machine
            it.close()
            assert s.query_bool("n(1).")


# ── Clausal translation ──────────────────────────────────────────


@needs_scryer
class TestClausalTranslation:
    """Loading .clausal source through the translation pipeline."""

    def test_consult_clausal_facts(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal("Foo(1, 2),\nFoo(3, 4),")
            results = s.query_all("foo(X, Y).")
            assert len(results) == 2

    def test_consult_clausal_rules(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal(textwrap.dedent("""\
                Edge(1, 2),
                Edge(2, 3),
                Edge(3, 4),
                Reach(X, Y) <- Edge(X, Y)
                Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
            """))
            assert s.query_bool("reach(1, 4).")
            results = s.query_all("reach(1, X).")
            xs = sorted(r["X"] for r in results)
            assert xs == [2, 3, 4]

    def test_consult_clausal_arithmetic(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal("Double(X, Y) <- (Y := X * 2)")
            assert s.query_one("double(5, Y).") == {"Y": 10}

    def test_consult_clausal_list_patterns(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_clausal(textwrap.dedent("""\
                MyAppend([], L, L),
                MyAppend([H, *T], L, [H, *R]) <- MyAppend(T, L, R)
            """))
            sol = s.query_one("my_append([1,2], [3,4], R).")
            assert sol["R"] == [1, 2, 3, 4]

    def test_consult_file_clausal(self, tmp_path):
        """consult_file auto-detects .clausal extension."""
        f = tmp_path / "facts.clausal"
        f.write_text("Color(red),\nColor(blue),\n")
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(f))
            results = s.query_all("color(X).")
            assert len(results) == 2

    def test_consult_file_prolog(self, tmp_path):
        """consult_file loads .pl files as raw Prolog."""
        f = tmp_path / "facts.pl"
        f.write_text("animal(cat). animal(dog).\n")
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(f))
            results = s.query_all("animal(X).")
            assert len(results) == 2


# ── Example files ─────────────────────────────────────────────────


@needs_scryer
class TestScryerExamples:
    """Load actual .clausal example files from the repo."""

    EXAMPLES = Path(__file__).parent.parent / "clausal" / "examples"

    def test_fibonacci(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_file(str(self.EXAMPLES / "fibonacci.clausal"))
            sol = s.query_one("fib(10, R).")
            assert sol is not None
            assert sol["R"] == 55

    def test_graph_reachable(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            # graph.clausal uses member/2 which needs library(lists) in Scryer
            s.consult_string(":- use_module(library(lists)).")
            s.consult_file(str(self.EXAMPLES / "graph.clausal"))
            assert s.query_bool("reachable(1, 6).")
            assert not s.query_bool("reachable(5, 1).")


# ── Session behaviour ─────────────────────────────────────────────


@needs_scryer
class TestScryerSession:
    """Verify session-like behavior: state persists across queries."""

    def test_separate_predicates_persist(self):
        """Loading different predicates in separate calls — both persist."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_string("likes(alice, bob).")
            assert s.query_bool("likes(alice, bob).")
            s.consult_string("friend(bob, carol).")
            assert s.query_bool("friend(bob, carol).")
            # Earlier predicate still present (different functor)
            assert s.query_bool("likes(alice, bob).")

    def test_dynamic_assertz_accumulates(self):
        """Dynamic predicates with assertz accumulate clauses."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.consult_string(":- dynamic(likes/2).")
            list(s.query("assertz(likes(alice, bob))."))
            list(s.query("assertz(likes(bob, carol))."))
            results = s.query_all("likes(X, Y).")
            assert len(results) == 2

    def test_multiple_queries_same_session(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("num(1). num(2). num(3).")
            assert len(s.query_all("num(X).")) == 3
            assert s.query_one("num(2).") == {}  # no bindings (ground query)
            assert not s.query_bool("num(99).")

    def test_context_manager_cleanup(self):
        """After exiting context, machine is released."""
        from clausal.scryer import Scryer
        with Scryer() as s:
            s.load_string("foo(1).")
            assert s.query_bool("foo(1).")
        assert s._machine is None

    def test_use_after_close_raises(self):
        """Using a closed session gives a clear error."""
        from clausal.scryer import Scryer
        s = Scryer()
        s.close()
        with pytest.raises(RuntimeError, match="closed"):
            s.query_one("true.")


# ── Edge cases ────────────────────────────────────────────────────


@needs_scryer
class TestScryerEdgeCases:
    """Edge cases: empty results, exceptions, large integers."""

    def test_large_integer(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X is 2 ^ 100.")
            assert sol["X"] == 2**100

    def test_float_result(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X is 1.0 + 2.5.")
            assert abs(sol["X"] - 3.5) < 1e-10

    def test_nested_list(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [[1, 2], [3, 4]].")
            assert sol["X"] == [[1, 2], [3, 4]]

    def test_empty_list(self):
        from clausal.scryer import Scryer
        with Scryer() as s:
            sol = s.query_one("X = [].")
            assert sol["X"] == []

    def test_prolog_error_raises(self):
        """Prolog errors become Python ScryerError exceptions."""
        from clausal.scryer import Scryer
        import _scryer_ext
        with Scryer() as s:
            with pytest.raises(_scryer_ext.ScryerError):
                s.query_all("X is foo.")


# ── to_prolog helper ──────────────────────────────────────────────


@needs_scryer
class TestToProlog:
    """Test the to_prolog() text-serialization helper."""

    def test_basic_types(self):
        from clausal.scryer import to_prolog
        assert to_prolog(42) == "42"
        assert to_prolog(3.14) == "3.14"
        assert to_prolog(True) == "true"
        assert to_prolog(False) == "false"
        assert to_prolog(None) == "[]"

    def test_string_quoting(self):
        from clausal.scryer import to_prolog
        assert to_prolog("hello") == "'hello'"
        assert to_prolog("it's") == "'it\\'s'"

    def test_list(self):
        from clausal.scryer import to_prolog
        assert to_prolog([1, 2, 3]) == "[1, 2, 3]"
        assert to_prolog([]) == "[]"

    def test_compound(self):
        from clausal.scryer import to_prolog
        from clausal.terms import Compound
        assert to_prolog(Compound("f", (1, 2))) == "f(1, 2)"

    def test_unsupported_type_raises(self):
        from clausal.scryer import to_prolog
        with pytest.raises(TypeError):
            to_prolog(object())
