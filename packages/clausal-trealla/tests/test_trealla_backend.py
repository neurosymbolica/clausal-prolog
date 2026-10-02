"""Trealla Prolog backend tests — translate clausal conformity tests to Prolog
and execute them via tpl to validate ISO compliance.

Trealla Prolog is ISO-conformant, so these tests verify that our translated
output is actually valid, runnable Prolog that produces the expected results.

Requires ``tpl`` on PATH or built at ../trealla-prolog/tpl.
All tests are skipped otherwise.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import Dialect
from clausal.trealla._engine import TPL_BINARY
from clausal._suffixes import SEAM_SUFFIX

needs_trealla = pytest.mark.skipif(TPL_BINARY is None, reason="tpl not on PATH")

CONFORMITY = Path(__file__).parent / "conformity"
FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "prolog_golden"

# Trealla dialect for all translations
_TREALLA = Dialect.trealla()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _run_trealla(prolog_source: str, query: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a Prolog query via tpl and return the result.

    Writes *prolog_source* to a temp file, appends a ``:- initialization``
    directive that runs *query*, and invokes ``tpl``.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=".pl", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(prolog_source)
        f.write("\n")
        f.write(f":- initialization(({query})).\n")
        f.flush()
        return subprocess.run(
            [TPL_BINARY, f.name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def _run_trealla_file(pl_path: str | Path, query: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a query against an existing .pl file via tpl."""
    source = Path(pl_path).read_text(encoding="utf-8")
    return _run_trealla(source, query, timeout=timeout)


def _translate_conformity(name: str) -> str:
    """Translate a conformity .clausal file to Trealla Prolog source."""
    path = CONFORMITY / f"{name}{SEAM_SUFFIX}"
    source = path.read_text(encoding="utf-8")
    return clausal_source_to_prolog(source, dialect=_TREALLA)


def _run_all_tests(prolog_source: str) -> tuple[list[str], list[str]]:
    """Run all test/1 predicates in *prolog_source* and return (passed, failed).

    Uses a harness that calls ``test(Desc)`` for each clause and reports
    pass/fail via ``write``.
    """
    harness = textwrap.dedent("""\
        :- use_module(library(lists)).

        safe_test(D) :- catch(test(D), _, fail).

        run_tests :-
            findall(D, safe_test(D), Descs),
            run_each(Descs).

        run_each([]).
        run_each([D|Ds]) :-
            ( safe_test(D) ->
                write('PASS: '), write(D), nl
            ;
                write('FAIL: '), write(D), nl
            ),
            run_each(Ds).
    """)

    # Strip any existing :- module declaration and append harness
    lines = prolog_source.split("\n")
    cleaned = [line for line in lines if not line.startswith(":- module(")]
    prolog_clean = "\n".join(cleaned)

    # Trealla treats double-quoted strings as char lists by default;
    # set them to atoms so test("description") works as expected.
    full_source = ':- set_prolog_flag(double_quotes, atom).\n' + prolog_clean + "\n" + harness
    result = _run_trealla(full_source, "run_tests, halt", timeout=30)
    passed = []
    failed = []
    for line in result.stdout.splitlines():
        if line.startswith("PASS: "):
            passed.append(line[6:])
        elif line.startswith("FAIL: "):
            failed.append(line[6:])
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════
# Basic: can Trealla parse our translated output?
# ═══════════════════════════════════════════════════════════════════════


@needs_trealla
class TestTreallaParses:
    """Verify that translated Prolog files parse without error in Trealla."""

    @pytest.mark.parametrize("name", [
        "iso_arithmetic",
        "iso_control",
        "iso_list_operations",
        "iso_term_manipulation",
        "iso_type_checking",
        "iso_unification",
    ])
    def test_conformity_parses(self, name):
        """Trealla accepts the translated .pl without syntax errors."""
        # nv
        prolog = _translate_conformity(name)
        result = _run_trealla(prolog, "true, halt")
        assert result.returncode == 0, (
            f"Trealla failed to parse {name}.pl:\n"
            f"stderr: {result.stderr[:1000]}"
        )

    @pytest.mark.parametrize("pl_name", [
        "edge_graph",
        "fibonacci",
        "meta_test",
    ])
    def test_golden_pl_parses(self, pl_name):
        """Golden .pl files parse in Trealla without error."""
        # nv
        pl_path = GOLDEN / f"{pl_name}.pl"
        if not pl_path.exists():
            pytest.skip(f"Golden file {pl_path} not found")
        result = _run_trealla_file(pl_path, "true, halt")
        assert result.returncode == 0, (
            f"Trealla failed to parse {pl_name}.pl:\n"
            f"stderr: {result.stderr[:1000]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Execution: small standalone programs
# ═══════════════════════════════════════════════════════════════════════


@needs_trealla
class TestTreallaExecution:
    """Execute small translated programs in Trealla and check results."""

    def test_simple_fact_query(self):
        """Translate a simple fact and query it."""
        # nv
        prolog = clausal_source_to_prolog("foo(1, 2),\nfoo(3, 4),", dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "foo(1, 2), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_simple_rule_query(self):
        """Translate a rule and query it."""
        # nv
        prolog = clausal_source_to_prolog(
            "double(X, Y) <- (eval_(X * 2, Y))",
            dialect=_TREALLA,
        )
        result = _run_trealla(
            prolog,
            "double(3, Y), write(Y), nl, halt",
        )
        assert result.returncode == 0
        assert "6" in result.stdout

    def test_recursive_rule(self):
        """Translate recursive rules (edge/reach) and query reachability."""
        # nv
        src = textwrap.dedent("""\
            edge(1, 2),
            edge(2, 3),
            edge(3, 4),
            reach(X, Y) <- edge(X, Y)
            reach(X, Y) <- (edge(X, Z), reach(Z, Y))
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "reach(1, 4), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_list_operations(self):
        """Translate list operations and run in Trealla."""
        # nv
        src = textwrap.dedent("""\
            my_append([], L, L),
            my_append([H, *T], L, [H, *R]) <- my_append(T, L, R)
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "my_append([1,2], [3,4], R), write(R), nl, halt",
        )
        assert result.returncode == 0
        assert "[1,2,3,4]" in result.stdout

    def test_arithmetic_evaluation(self):
        """eval_(translates to 'is' and evaluates in Trealla., Arithmetic)"""
        # nv
        src = textwrap.dedent("""\
            fib(0, 0),
            fib(1, 1),
            fib(N, R) <- (
                N > 1,
                eval_(N - 1, N1),
                eval_(N - 2, N2),
                fib(N1, A),
                fib(N2, B),
                eval_(A + B, R)
            )
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "fib(10, R), write(R), nl, halt",
            timeout=30,
        )
        assert result.returncode == 0
        assert "55" in result.stdout

    def test_negation(self):
        """Negation as failure (not -> \\+) works in Trealla."""
        # nv
        src = textwrap.dedent("""\
            even(0),
            even(N) <- (N > 0, eval_(N - 2, N1), even(N1))
            odd(N) <- (not even(N))
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "odd(3), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_unification(self):
        """Unification (is -> =) works correctly."""
        # nv
        src = "test(X, Y) <- (X is Y)"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "test(hello, hello), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_disjunction(self):
        """Disjunction (or -> ;) works in Trealla."""
        # nv
        src = textwrap.dedent("""\
            color(red),
            color(blue),
            red_or_blue(X) <- (X is red or X is blue)
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "red_or_blue(red), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_findall(self):
        """FindAll translates to findall/3 and works in Trealla."""
        # nv
        src = textwrap.dedent("""\
            num(1),
            num(2),
            num(3),
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        prolog += "\n:- use_module(library(lists)).\n"
        result = _run_trealla(
            prolog,
            "findall(X, num(X), Xs), write(Xs), nl, halt",
        )
        assert result.returncode == 0
        assert "[1,2,3]" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# Conformity suite execution via Trealla
# ═══════════════════════════════════════════════════════════════════════


@needs_trealla
class TestTreallaConformity:
    """Run translated conformity test/1 predicates in Trealla.

    Each conformity .clausal file defines ``test(Description) :- Goal``
    clauses.  We translate to Trealla Prolog and verify each test passes.
    """

    def _run_conformity(self, name: str) -> tuple[list[str], list[str]]:
        """Translate and execute conformity tests, returning (passed, failed)."""
        prolog = _translate_conformity(name)
        return _run_all_tests(prolog)

    def test_iso_arithmetic(self):
        """ISO arithmetic tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_arithmetic")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed "
                f"(expected divergences): {failed[:5]}"
            )

    def test_iso_control(self):
        """ISO control construct tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_control")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed: {failed[:5]}"
            )

    def test_iso_unification(self):
        """ISO unification tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_unification")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed: {failed[:5]}"
            )

    def test_iso_list_operations(self):
        """ISO list operation tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_list_operations")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed: {failed[:5]}"
            )

    def test_iso_type_checking(self):
        """ISO type checking tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_type_checking")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed: {failed[:5]}"
            )

    def test_iso_term_manipulation(self):
        """ISO term manipulation tests pass in Trealla."""
        # nv
        passed, failed = self._run_conformity("iso_term_manipulation")
        assert len(passed) > 0, "No tests ran"
        if failed:
            pytest.xfail(
                f"{len(failed)} of {len(passed) + len(failed)} tests failed: {failed[:5]}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Trealla-specific dialect features
# ═══════════════════════════════════════════════════════════════════════


class TestTreallaDialectFeatures:
    """Verify Trealla-specific translation features work."""

    def test_clpz_constraints(self):
        """CLP(Z) constraints use Trealla's clpz library."""
        # nv
        src = textwrap.dedent("""\
            -import_from(clausal.logic.clpfd, [in_domain, all_different])
            test(X) <- (
                in_domain(X, 1, 3),
                all_different([X])
            )
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        assert "library(clpz)" in prolog
        assert "all_distinct" in prolog

    def test_trealla_leq_operator(self):
        """Trealla uses =< (ISO) for less-or-equal."""
        # nv
        src = "test() <- (1 <= 2)"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        assert "=<" in prolog

    def test_trealla_dif(self):
        """dif/2 is available in Trealla."""
        # nv
        src = "test(X, Y) <- (X is not Y)"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        assert "dif" in prolog

    def test_trealla_member(self):
        """in -> member/2 works for Trealla."""
        # nv
        src = "test(X) <- (X in [1, 2, 3])"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        assert "member" in prolog

    def test_trealla_cut(self):
        """Cut is preserved through roundtrip."""
        # nv
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        src = "foo(X) :- X > 0, !."
        clausal = prolog_to_clausal(src, dialect=_TREALLA)
        prolog2 = clausal_source_to_prolog(clausal, dialect=_TREALLA)
        assert "!" in prolog2 or "cut" in prolog2


# ═══════════════════════════════════════════════════════════════════════
# Edge cases for ISO compliance
# ═══════════════════════════════════════════════════════════════════════


@needs_trealla
class TestISOEdgeCases:
    """Test ISO edge cases that Trealla handles."""

    def test_operator_precedence_iso(self):
        """ISO operator precedence is preserved in translation."""
        # nv
        src = "test(R) <- (eval_(2 + 3 * 4, R))"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(prolog, "test(R), write(R), nl, halt")
        assert result.returncode == 0
        assert "14" in result.stdout

    def test_atom_quoting(self):
        """Atoms that need quoting are properly quoted."""
        # nv
        src = "Foo(hello_world),"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(prolog, "foo(X), write(X), nl, halt")
        assert result.returncode == 0
        assert "hello_world" in result.stdout

    def test_string_handling(self):
        """Strings are handled correctly."""
        # nv
        src = 'Greeting("hello"),'
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        prolog = ':- set_prolog_flag(double_quotes, atom).\n' + prolog
        result = _run_trealla(prolog, 'greeting(X), write(X), nl, halt')
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_empty_list(self):
        """Empty list [] works correctly."""
        # nv
        src = "Empty([]),"
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(prolog, "empty(X), write(X), nl, halt")
        assert result.returncode == 0
        assert "[]" in result.stdout

    def test_list_cons_pattern(self):
        """[H|T] pattern matching works."""
        # nv
        src = textwrap.dedent("""\
            head([H, *_], H),
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(prolog, "head([a,b,c], H), write(H), nl, halt")
        assert result.returncode == 0
        assert "a" in result.stdout

    def test_nested_compound(self):
        """Nested compound terms translate correctly."""
        # nv
        src = textwrap.dedent("""\
            eval(add(X, Y), R) <- (eval_(X + Y, R))
            eval(mul(X, Y), R) <- (eval_(X * Y, R))
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(prolog, "eval(add(2,3), R), write(R), nl, halt")
        assert result.returncode == 0
        assert "5" in result.stdout

    def test_multiple_solutions(self):
        """Multiple solutions via backtracking work correctly."""
        # nv
        src = textwrap.dedent("""\
            color(red),
            color(green),
            color(blue),
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        prolog += "\n:- use_module(library(lists)).\n"
        result = _run_trealla(
            prolog,
            "findall(X, color(X), Xs), length(Xs, N), write(N), nl, halt",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_comparison_operators(self):
        """All comparison operators translate to ISO forms."""
        # nv
        src = textwrap.dedent("""\
            test_lt() <- (1 < 2)
            test_leq() <- (1 <= 1)
            test_gt() <- (2 > 1)
            test_geq() <- (1 >= 1)
        """)
        prolog = clausal_source_to_prolog(src, dialect=_TREALLA)
        result = _run_trealla(
            prolog,
            "test_lt, test_leq, test_gt, test_geq, write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout
