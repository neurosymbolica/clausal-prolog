"""Scryer Prolog backend tests — translate clausal conformity tests to Prolog
and execute them via scryer-prolog to validate ISO compliance.

Scryer Prolog is ISO-conformant, so these tests verify that our translated
output is actually valid, runnable Prolog that produces the expected results.

Requires ``scryer-prolog`` on PATH.  All tests are skipped otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_to_clausal import prolog_to_clausal
from clausal._suffixes import SEAM_SUFFIX

SCRYER = shutil.which("scryer-prolog")
needs_scryer = pytest.mark.skipif(SCRYER is None, reason="scryer-prolog not on PATH")

CONFORMITY = Path(__file__).parent / "conformity"
FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "prolog_golden"

# Scryer dialect for all translations
_SCRYER = Dialect.scryer()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _run_scryer(prolog_source: str, query: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a Prolog query via scryer-prolog and return the result.

    Writes *prolog_source* to a temp file, appends a ``:- initialization``
    directive that runs *query*, and invokes ``scryer-prolog``.
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
            [SCRYER, f.name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def _run_scryer_file(pl_path: str | Path, query: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a query against an existing .pl file via scryer-prolog."""
    import tempfile

    source = Path(pl_path).read_text(encoding="utf-8")
    return _run_scryer(source, query, timeout=timeout)


def _translate_conformity(name: str) -> str:
    """Translate a conformity seam (.seam) file to Scryer Prolog source."""
    path = CONFORMITY / f"{name}{SEAM_SUFFIX}"
    source = path.read_text(encoding="utf-8")
    return clausal_source_to_prolog(source, dialect=_SCRYER)


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

    # Strip any existing :- module declaration's export list limitation
    # and append the harness + initialization
    # Scryer treats double-quoted strings as char code lists by default;
    # set them to atoms so test("description") works as expected.
    full_source = ':- set_prolog_flag(double_quotes, atom).\n' + prolog_source + "\n" + harness
    result = _run_scryer(full_source, "run_tests, halt", timeout=30)
    passed = []
    failed = []
    for line in result.stdout.splitlines():
        if line.startswith("PASS: "):
            passed.append(line[6:])
        elif line.startswith("FAIL: "):
            failed.append(line[6:])
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════
# Basic: can Scryer parse our translated output?
# ═══════════════════════════════════════════════════════════════════════


@needs_scryer
class TestScryerParses:
    """Verify that translated Prolog files parse without error in Scryer."""

    @pytest.mark.parametrize("name", [
        "iso_arithmetic",
        "iso_control",
        "iso_list_operations",
        "iso_term_manipulation",
        "iso_type_checking",
        "iso_unification",
    ])
    def test_conformity_parses(self, name):
        """Scryer accepts the translated .pl without syntax errors."""
        # nv
        prolog = _translate_conformity(name)
        # Remove module declaration (Scryer may not support all our module features)
        # and just check the file parses
        result = _run_scryer(prolog, "true, halt")
        assert result.returncode == 0, (
            f"Scryer failed to parse {name}.pl:\n"
            f"stderr: {result.stderr[:1000]}"
        )

    @pytest.mark.parametrize("pl_name", [
        "edge_graph",
        "fibonacci",
        "clpfd_queens",
        "meta_test",
    ])
    def test_golden_pl_parses(self, pl_name):
        """Golden .pl files parse in Scryer without error."""
        # nv
        pl_path = GOLDEN / f"{pl_name}.pl"
        if not pl_path.exists():
            pytest.skip(f"Golden file {pl_path} not found")
        result = _run_scryer_file(pl_path, "true, halt")
        assert result.returncode == 0, (
            f"Scryer failed to parse {pl_name}.pl:\n"
            f"stderr: {result.stderr[:1000]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Execution: small standalone programs
# ═══════════════════════════════════════════════════════════════════════


@needs_scryer
class TestScryerExecution:
    """Execute small translated programs in Scryer and check results."""

    def test_simple_fact_query(self):
        """Translate a simple fact and query it."""
        # nv
        prolog = clausal_source_to_prolog("foo(1, 2),\nfoo(3, 4),", dialect=_SCRYER)
        result = _run_scryer(
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
            dialect=_SCRYER,
        )
        result = _run_scryer(
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
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "reach(1, 4), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_list_operations(self):
        """Translate list operations and run in Scryer."""
        # nv
        src = textwrap.dedent("""\
            my_append([], L, L),
            my_append([H, *T], L, [H, *R]) <- my_append(T, L, R)
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "my_append([1,2], [3,4], R), write(R), nl, halt",
        )
        assert result.returncode == 0
        assert "[1,2,3,4]" in result.stdout

    def test_arithmetic_evaluation(self):
        """eval_(translates to 'is' and evaluates in Scryer., Arithmetic)"""
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
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "fib(10, R), write(R), nl, halt",
            timeout=30,
        )
        assert result.returncode == 0
        assert "55" in result.stdout

    def test_negation(self):
        """Negation as failure (not → \\+) works in Scryer."""
        # nv
        src = textwrap.dedent("""\
            even(0),
            even(N) <- (N > 0, eval_(N - 2, N1), even(N1))
            odd(N) <- (not even(N))
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "odd(3), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_unification(self):
        """Unification (is → =) works correctly."""
        # nv
        src = "test(X, Y) <- (X is Y)"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "test(hello, hello), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_disjunction(self):
        """Disjunction (or → ;) works in Scryer."""
        # nv
        src = textwrap.dedent("""\
            color(red),
            color(blue),
            red_or_blue(X) <- (X is red or X is blue)
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "red_or_blue(red), write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_findall(self):
        """findall translates to findall/3 and works in Scryer."""
        # nv
        src = textwrap.dedent("""\
            num(1),
            num(2),
            num(3),
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        prolog += "\n:- use_module(library(lists)).\n"
        result = _run_scryer(
            prolog,
            "findall(X, num(X), Xs), write(Xs), nl, halt",
        )
        assert result.returncode == 0
        assert "[1,2,3]" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# Conformity suite execution via Scryer
# ═══════════════════════════════════════════════════════════════════════


@needs_scryer
class TestScryerConformity:
    """Run translated conformity test/1 predicates in Scryer.

    Each conformity .clausal file defines ``test(Description) :- Goal``
    clauses.  We translate to Scryer Prolog and verify each test passes.
    """

    def _run_conformity(self, name: str) -> tuple[list[str], list[str]]:
        """Translate and execute conformity tests, returning (passed, failed)."""
        prolog = _translate_conformity(name)
        # Remove module declaration for standalone execution —
        # Scryer module system may conflict with our harness
        lines = prolog.split("\n")
        cleaned = []
        for line in lines:
            if line.startswith(":- module("):
                continue
            cleaned.append(line)
        prolog_clean = "\n".join(cleaned)
        return _run_all_tests(prolog_clean)

    def test_iso_arithmetic(self):
        """ISO arithmetic tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_arithmetic")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"

    def test_iso_control(self):
        """ISO control construct tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_control")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"

    def test_iso_unification(self):
        """ISO unification tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_unification")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"

    def test_iso_list_operations(self):
        """ISO list operation tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_list_operations")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"

    def test_iso_type_checking(self):
        """ISO type checking tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_type_checking")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"

    def test_iso_term_manipulation(self):
        """ISO term manipulation tests pass in Scryer."""
        # nv
        passed, failed = self._run_conformity("iso_term_manipulation")
        assert len(passed) > 0, "No tests ran"
        assert not failed, f"{len(failed)} tests failed: {failed}"


# ═══════════════════════════════════════════════════════════════════════
# Conformity roundtrip execution via Scryer
# ═══════════════════════════════════════════════════════════════════════


_CONFORMITY_NAMES = [
    "iso_arithmetic",
    "iso_control",
    "iso_list_operations",
    "iso_term_manipulation",
    "iso_type_checking",
    "iso_unification",
]


@needs_scryer
class TestScryerConformityRoundtrip:
    """Roundtrip: clausal → Prolog → clausal → Prolog, then execute in Scryer.

    Verifies that the translator roundtrip does not break semantics: the
    final Prolog output must still parse, and all test/1 predicates must
    still pass in Scryer.
    """

    def _roundtrip_conformity(self, name: str) -> tuple[list[str], list[str]]:
        """Translate conformity file through a full roundtrip and execute."""
        # Leg 1: clausal → Prolog (Scryer dialect)
        path = CONFORMITY / f"{name}{SEAM_SUFFIX}"
        source = path.read_text(encoding="utf-8")
        pl1 = clausal_source_to_prolog(source, dialect=_SCRYER)

        # Leg 2: Prolog → clausal
        rt_clausal = prolog_to_clausal(pl1, dialect=_SCRYER)

        # Leg 3: clausal → Prolog again (Scryer dialect)
        pl2 = clausal_source_to_prolog(rt_clausal, dialect=_SCRYER)

        prolog_clean = self._strip_module_directives(pl2)
        return _run_all_tests(prolog_clean)

    @staticmethod
    def _strip_module_directives(prolog: str) -> str:
        """Remove module/use_module directives that break standalone execution."""
        return "\n".join(
            l for l in prolog.split("\n")
            if not l.startswith(":- module(")
            and not l.startswith(":- use_module(")
        )

    @pytest.mark.parametrize("name", _CONFORMITY_NAMES)
    def test_roundtrip_parses(self, name):
        """Roundtripped Prolog output parses in Scryer without errors."""
        # nv
        path = CONFORMITY / f"{name}{SEAM_SUFFIX}"
        source = path.read_text(encoding="utf-8")
        pl1 = clausal_source_to_prolog(source, dialect=_SCRYER)
        rt_clausal = prolog_to_clausal(pl1, dialect=_SCRYER)
        pl2 = clausal_source_to_prolog(rt_clausal, dialect=_SCRYER)
        pl2_clean = self._strip_module_directives(pl2)
        result = _run_scryer(pl2_clean, "true, halt")
        assert result.returncode == 0, (
            f"Scryer failed to parse roundtripped {name}:\n"
            f"stderr: {result.stderr[:1000]}"
        )

    @pytest.mark.parametrize("name", _CONFORMITY_NAMES)
    def test_roundtrip_execution(self, name):
        """All test/1 predicates still pass after roundtrip through translator."""
        # nv
        passed, failed = self._roundtrip_conformity(name)
        assert len(passed) > 0, f"No tests ran for {name}"
        assert not failed, (
            f"{len(failed)} of {len(passed) + len(failed)} tests failed "
            f"after roundtrip: {failed}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Scryer-specific dialect features
# ═══════════════════════════════════════════════════════════════════════


class TestScryerDialectFeatures:
    """Verify Scryer-specific translation features work."""

    def test_clpz_constraints(self):
        """CLP(Z) constraints use Scryer's clpz library."""
        # nv
        src = textwrap.dedent("""\
            -import_from(clausal.logic.clpfd, [in_domain, all_different])
            test(X) <- (
                in_domain(X, 1, 3),
                all_different([X])
            )
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        assert "library(clpz)" in prolog
        assert "all_distinct" in prolog  # Scryer uses all_distinct, not all_different

    def test_scryer_leq_operator(self):
        """Scryer uses =< (ISO) for less-or-equal."""
        # nv
        src = "test() <- (1 <= 2)"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        assert "=<" in prolog

    def test_scryer_tabling(self):
        """Scryer tabling uses use_module(library(tabling))."""
        # nv
        src = "-table(Fib(N, R))"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        assert "use_module(library(tabling))" in prolog
        assert "table" in prolog

    def test_scryer_dif(self):
        """dif/2 is available in Scryer."""
        # nv
        src = "test(X, Y) <- (X is not Y)"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        assert "dif" in prolog

    def test_scryer_member(self):
        """in → member/2 works for Scryer."""
        # nv
        src = "test(X) <- (X in [1, 2, 3])"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        assert "member" in prolog

    def test_scryer_cut(self):
        """Cut is preserved through roundtrip (as ! or cut)."""
        # nv
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        src = "foo(X) :- X > 0, !."
        clausal = prolog_to_clausal(src, dialect=_SCRYER)
        prolog2 = clausal_source_to_prolog(clausal, dialect=_SCRYER)
        assert "!" in prolog2 or "cut" in prolog2


# ═══════════════════════════════════════════════════════════════════════
# Edge cases for ISO compliance
# ═══════════════════════════════════════════════════════════════════════


@needs_scryer
class TestISOEdgeCases:
    """Test ISO edge cases that Scryer handles strictly."""

    def test_operator_precedence_iso(self):
        """ISO operator precedence is preserved in translation."""
        # nv
        src = "test(R) <- (eval_(2 + 3 * 4, R))"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        # Should evaluate to 14, not 20
        result = _run_scryer(prolog, "test(R), write(R), nl, halt")
        assert result.returncode == 0
        assert "14" in result.stdout

    def test_atom_quoting(self):
        """Atoms that need quoting are properly quoted."""
        # nv
        src = "Foo(hello_world),"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(prolog, "foo(X), write(X), nl, halt")
        assert result.returncode == 0
        assert "hello_world" in result.stdout

    def test_string_handling(self):
        """Strings are handled correctly."""
        # nv
        src = 'Greeting("hello"),'
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        # Scryer treats "hello" as a char list by default; use atom flag
        prolog = ':- set_prolog_flag(double_quotes, atom).\n' + prolog
        result = _run_scryer(prolog, 'greeting(X), write(X), nl, halt')
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_empty_list(self):
        """Empty list [] works correctly."""
        # nv
        src = "Empty([]),"
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(prolog, "empty(X), write(X), nl, halt")
        assert result.returncode == 0
        assert "[]" in result.stdout

    def test_list_cons_pattern(self):
        """[H|T] pattern matching works."""
        # nv
        src = textwrap.dedent("""\
            head([H, *_], H),
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(prolog, "head([a,b,c], H), write(H), nl, halt")
        assert result.returncode == 0
        assert "a" in result.stdout

    def test_nested_compound(self):
        """Nested compound terms translate correctly."""
        # nv
        src = textwrap.dedent("""\
            eval(add(X, Y), R) <- (eval_(X + Y, R))
            eval(mul(X, Y), R) <- (eval_(X * Y, R))
        """)
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(prolog, "eval(add(2,3), R), write(R), nl, halt")
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
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        prolog += "\n:- use_module(library(lists)).\n"
        result = _run_scryer(
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
        prolog = clausal_source_to_prolog(src, dialect=_SCRYER)
        result = _run_scryer(
            prolog,
            "test_lt, test_leq, test_gt, test_geq, write(ok), nl, halt",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout
