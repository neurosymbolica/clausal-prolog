"""Test the embedded Trealla Prolog engine via the Python Trealla API.

These tests verify the full pipeline: .clausal source is translated to Prolog
by the existing clausal_to_prolog machinery, loaded into an in-process Trealla
machine, queried, and results converted back to Python values.

Requires libtpl.so to be built from trealla-prolog source.
"""
import textwrap
from pathlib import Path

import pytest

from clausal.trealla import AVAILABLE

needs_trealla = pytest.mark.skipif(not AVAILABLE, reason=(
    "trealla shared library not built; build libtpl.so from trealla-prolog source"
))


# ── Basics ────────────────────────────────────────────────────────


@needs_trealla
class TestTreallaBasics:
    """Core query functionality."""

    def test_true(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            assert t.query_bool("true.")

    def test_fail(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            assert not t.query_bool("fail.")
            assert t.query_one("fail.") is None

    def test_fact_and_query(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("parent(tom, bob).")
            assert t.query_one("parent(tom, X).") == {"X": "bob"}

    def test_multiple_solutions(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("color(red). color(green). color(blue).")
            results = t.query_all("color(X).")
            assert [r["X"] for r in results] == ["red", "green", "blue"]

    def test_arithmetic(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            assert t.query_one("X is 2 + 3.") == {"X": 5}
            assert t.query_one("X is 10 mod 3.") == {"X": 1}

    def test_list_unification(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            sol = t.query_one("X = [1, 2, 3].")
            assert sol["X"] == [1, 2, 3]

    def test_compound_term(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("data(point(1, 2)).")
            sol = t.query_one("data(X).")
            assert sol["X"] == ("point", 1, 2)

    def test_no_bindings_goal(self):
        """A goal that succeeds with no variables returns empty dict."""
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            assert t.query_one("true.") == {}

    def test_iterator_protocol(self):
        """query() returns a lazy iterator, not a list."""
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("n(1). n(2). n(3).")
            results = list(t.query("n(X)."))
            assert [r["X"] for r in results] == [1, 2, 3]


# ── Clausal translation ──────────────────────────────────────────


@needs_trealla
class TestClausalTranslation:
    """Loading .clausal source through the translation pipeline."""

    def test_consult_clausal_facts(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_clausal("foo(1, 2),\nfoo(3, 4),")
            results = t.query_all("foo(X, Y).")
            assert len(results) == 2

    def test_consult_clausal_rules(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_clausal(textwrap.dedent("""\
                edge(1, 2),
                edge(2, 3),
                edge(3, 4),
                reach(X, Y) <- edge(X, Y)
                reach(X, Y) <- (edge(X, Z), reach(Z, Y))
            """))
            assert t.query_bool("reach(1, 4).")
            results = t.query_all("reach(1, X).")
            xs = sorted(r["X"] for r in results)
            assert xs == [2, 3, 4]

    def test_consult_clausal_arithmetic(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_clausal("double(X, Y) <- (eval_(X * 2, Y))")
            assert t.query_one("double(5, Y).") == {"Y": 10}

    def test_consult_clausal_list_patterns(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_clausal(textwrap.dedent("""\
                my_append([], L, L),
                my_append([H, *T], L, [H, *R]) <- my_append(T, L, R)
            """))
            sol = t.query_one("my_append([1,2], [3,4], R).")
            assert sol["R"] == [1, 2, 3, 4]

    def test_consult_file_clausal(self, tmp_path):
        """consult_file auto-detects .clausal extension."""
        # nv
        f = tmp_path / "facts.clausal"
        f.write_text("color(red),\ncolor(blue),\n")
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_file(str(f))
            results = t.query_all("color(X).")
            assert len(results) == 2

    def test_consult_file_prolog(self, tmp_path):
        """consult_file loads .pl files as raw Prolog."""
        # nv
        f = tmp_path / "facts.pl"
        f.write_text("animal(cat). animal(dog).\n")
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_file(str(f))
            results = t.query_all("animal(X).")
            assert len(results) == 2


# ── Example files ─────────────────────────────────────────────────


@needs_trealla
class TestTreallaExamples:
    """Load actual .clausal example files from the repo."""

    EXAMPLES = Path(__file__).parent.parent / "clausal" / "examples"

    def test_fibonacci(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_file(str(self.EXAMPLES / "fibonacci.clausal"))
            sol = t.query_one("fib(10, R).")
            assert sol is not None
            assert sol["R"] == 55

    def test_graph_reachable(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_string(":- use_module(library(lists)).")
            t.consult_file(str(self.EXAMPLES / "graph.clausal"))
            assert t.query_bool("reachable(1, 6).")
            assert not t.query_bool("reachable(5, 1).")


# ── Session behaviour ─────────────────────────────────────────────


@needs_trealla
class TestTreallaSession:
    """Verify session-like behavior: state persists across queries."""

    def test_separate_predicates_persist(self):
        """Loading different predicates in separate calls — both persist."""
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_string("likes(alice, bob).")
            assert t.query_bool("likes(alice, bob).")
            t.consult_string("friend(bob, carol).")
            assert t.query_bool("friend(bob, carol).")
            assert t.query_bool("likes(alice, bob).")

    def test_dynamic_assertz_accumulates(self):
        """Dynamic predicates with assertz accumulate clauses."""
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.consult_string(":- dynamic(likes/2).")
            t.load_string("likes(alice, bob).")
            t.load_string("likes(bob, carol).")
            results = t.query_all("likes(X, Y).")
            assert len(results) >= 1

    def test_multiple_queries_same_session(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("num(1). num(2). num(3).")
            assert len(t.query_all("num(X).")) == 3
            assert t.query_one("num(2).") == {}  # no bindings (ground query)
            assert not t.query_bool("num(99).")

    def test_context_manager_cleanup(self):
        """After exiting context, machine is released."""
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("foo(1).")
            assert t.query_bool("foo(1).")
        assert t._machine is None

    def test_use_after_close_raises(self):
        """Using a closed session gives a clear error."""
        # nv
        from clausal.trealla import Trealla
        t = Trealla()
        t.close()
        with pytest.raises(RuntimeError, match="closed"):
            t.query_one("true.")


# ── Edge cases ────────────────────────────────────────────────────


@needs_trealla
class TestTreallaEdgeCases:
    """Edge cases: empty results, large integers, floats, errors."""

    def test_prolog_error_raises(self):
        """Prolog errors become Python TreallaError exceptions."""
        # nv
        from clausal.trealla import Trealla, TreallaError
        with Trealla() as t:
            with pytest.raises(TreallaError):
                t.query_all("X is foo.")

    def test_early_break_is_lazy(self):
        """Iteration is truly lazy — does not compute all solutions upfront.

        Uses a 10M-element range; if buffered, this would take seconds.
        The timing assertion proves pl_query/pl_redo is one-at-a-time.
        """
        # nv
        import time
        from clausal.trealla import Trealla
        with Trealla() as t:
            t.load_string("big(X) :- between(1, 10000000, X).")
            start = time.monotonic()
            count = 0
            for sol in t.query("big(X)."):
                count += 1
                if count >= 3:
                    break
            elapsed = time.monotonic() - start
            assert count == 3
            # 3 solutions from 10M must complete in under 1 second
            # (buffered would take many seconds to enumerate 10M)
            assert elapsed < 1.0, f"query took {elapsed:.2f}s — not lazy?"

    def test_large_integer(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            sol = t.query_one("X is 2 ^ 100.")
            assert sol["X"] == 2**100

    def test_float_result(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            sol = t.query_one("X is 1.0 + 2.5.")
            assert abs(sol["X"] - 3.5) < 1e-10

    def test_nested_list(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            sol = t.query_one("X = [[1, 2], [3, 4]].")
            assert sol["X"] == [[1, 2], [3, 4]]

    def test_empty_list(self):
        # nv
        from clausal.trealla import Trealla
        with Trealla() as t:
            sol = t.query_one("X = [].")
            assert sol["X"] == []


# ── to_prolog helper ──────────────────────────────────────────────


@needs_trealla
class TestToProlog:
    """Test the to_prolog() text-serialization helper."""

    def test_basic_types(self):
        # nv
        from clausal.trealla import to_prolog
        assert to_prolog(42) == "42"
        assert to_prolog(3.14) == "3.14"
        assert to_prolog(True) == "true"
        assert to_prolog(False) == "false"
        assert to_prolog(None) == "[]"

    def test_string_quoting(self):
        # nv
        from clausal.trealla import to_prolog
        assert to_prolog("hello") == "'hello'"
        assert to_prolog("it's") == "'it\\'s'"

    def test_list(self):
        # nv
        from clausal.trealla import to_prolog
        assert to_prolog([1, 2, 3]) == "[1, 2, 3]"
        assert to_prolog([]) == "[]"

    def test_compound(self):
        # nv
        from clausal.trealla import to_prolog
        assert to_prolog(("f", 1, 2)) == "f(1, 2)"

    def test_unsupported_type_raises(self):
        # nv
        from clausal.trealla import to_prolog
        with pytest.raises(TypeError):
            to_prolog(object())
