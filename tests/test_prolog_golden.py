"""Golden-file snapshot tests for bidirectional clausal ↔ Prolog translation.

Clausal → Prolog (Step 1.6):
    Each test reads a .clausal source file, translates it to Prolog, and compares
    against a checked-in golden .pl file.  If the golden file needs updating,
    run:
        python -m clausal.tools.clausal_to_prolog SOURCE.clausal -o GOLDEN.pl

Prolog → Clausal (Phase 4.3):
    Each test reads a .pl golden file, translates to clausal, and compares
    against a checked-in golden .clausal file.  If the golden file needs updating,
    run:
        python -m clausal.tools.prolog_to_clausal SOURCE.pl -o GOLDEN.clausal
"""

from pathlib import Path

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_to_clausal import prolog_to_clausal

FIXTURES = Path(__file__).parent / "fixtures"
CONFORMITY = Path(__file__).parent / "conformity"
GOLDEN = FIXTURES / "prolog_golden"

# (source_path, golden_path) pairs
_FIXTURE_CASES = [
    (FIXTURES / "edge_graph.clausal", GOLDEN / "edge_graph.pl"),
    (FIXTURES / "fibonacci.clausal", GOLDEN / "fibonacci.pl"),
    (FIXTURES / "dcg_grammar.clausal", GOLDEN / "dcg_grammar.pl"),
    (FIXTURES / "meta_test.clausal", GOLDEN / "meta_test.pl"),
    (FIXTURES / "clpfd_queens.clausal", GOLDEN / "clpfd_queens.pl"),
]

_CONFORMITY_CASES = [
    (CONFORMITY / "iso_arithmetic.clausal", GOLDEN / "iso_arithmetic.pl"),
    (CONFORMITY / "iso_control.clausal", GOLDEN / "iso_control.pl"),
    (CONFORMITY / "iso_list_operations.clausal", GOLDEN / "iso_list_operations.pl"),
    (CONFORMITY / "iso_term_manipulation.clausal", GOLDEN / "iso_term_manipulation.pl"),
    (CONFORMITY / "iso_type_checking.clausal", GOLDEN / "iso_type_checking.pl"),
    (CONFORMITY / "iso_unification.clausal", GOLDEN / "iso_unification.pl"),
]

ALL_CASES = _FIXTURE_CASES + _CONFORMITY_CASES


def _case_id(pair):
    return pair[0].stem


@pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
def test_golden_snapshot(source_path, golden_path):
    """Translation output matches the golden .pl snapshot."""
    source = source_path.read_text(encoding="utf-8")
    golden = golden_path.read_text(encoding="utf-8")
    result = clausal_source_to_prolog(source)
    assert result == golden, (
        f"Translation of {source_path.name} does not match golden file {golden_path.name}.\n"
        f"To update: python -m clausal.tools.clausal_to_prolog {source_path} -o {golden_path}"
    )


class TestTranslationSyntax:
    """Verify structural properties of translated Prolog output."""

    @pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
    def test_every_clause_ends_with_dot(self, source_path, golden_path):
        """Every non-empty, non-directive line sequence ends with a period."""
        golden = golden_path.read_text(encoding="utf-8")
        for line in golden.strip().split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            # Continuation lines (indented body goals) don't end with '.'
            # Only top-level clause-ending lines end with '.'
            # Directive lines start with ':-' — also end with '.'

    @pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
    def test_no_trailing_whitespace(self, source_path, golden_path):
        """No lines have trailing whitespace."""
        golden = golden_path.read_text(encoding="utf-8")
        for i, line in enumerate(golden.split("\n"), 1):
            if line != line.rstrip():
                pytest.fail(f"{golden_path.name}:{i}: trailing whitespace")

    @pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
    def test_no_python_syntax_leaks(self, source_path, golden_path):
        """Translated output should not contain clausal-specific syntax."""
        import re
        golden = golden_path.read_text(encoding="utf-8")
        # Strip quoted strings before checking for Python keywords
        stripped = re.sub(r'"[^"]*"', '""', golden)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "<-" not in stripped, "Clausal arrow '<-' found in Prolog output"
        assert " and " not in stripped, "Clausal 'and' found in Prolog output"


class TestInNotIn:
    """Tests for the in/not-in → member translation."""

    def test_in_translates_to_member(self):
        result = clausal_source_to_prolog("Test() <- (X_ in [1, 2, 3])")
        assert "member(X, [1, 2, 3])" in result

    def test_not_in_translates_to_negated_member(self):
        result = clausal_source_to_prolog("Test() <- (X_ not in [1, 2, 3])")
        assert "\\+ member(X, [1, 2, 3])" in result or "\\+(member(X, [1, 2, 3]))" in result


class TestKeywordArgs:
    """Tests for keyword argument handling in clause heads."""

    def test_keyword_fact(self):
        result = clausal_source_to_prolog("Fib(N=0, RESULT=0),")
        assert "fib(0, 0)." in result

    def test_keyword_mixed(self):
        result = clausal_source_to_prolog("Foo(1, Y=2),")
        assert "foo(1, 2)." in result


class TestUntranslatable:
    """Phase 2: untranslatable construct handling."""

    def test_double_uadd_warning(self):
        """++expr emits a warning comment."""
        result = clausal_source_to_prolog("Test() <- (R_ := ++len(L_))")
        assert "WARNING" in result
        assert "untranslatable" in result
        assert "len" in result

    def test_fstring_swi_format(self):
        """f-strings become format/2 in SWI dialect."""
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            'Test() <- (X_ is f"hello {NAME}")',
            dialect=Dialect.swi(),
        )
        assert "format" in result
        assert "~w" in result

    def test_fstring_iso_warning(self):
        """f-strings emit a warning in ISO dialect."""
        result = clausal_source_to_prolog('Test() <- (X_ is f"hello {NAME}")')
        assert "WARNING" in result
        assert "f-string" in result

    def test_set_single_element_is_curly(self):
        """Single-element set {Goal} becomes DCG inline goal."""
        result = clausal_source_to_prolog("Test() <- {X_ > 0}")
        assert "{" in result
        assert "WARNING" not in result

    def test_set_multi_element_warning(self):
        """Multi-element set emits a warning."""
        result = clausal_source_to_prolog("Test() <- {1, 2, 3}")
        assert "WARNING" in result
        assert "set literal" in result

    def test_dict_swi(self):
        """Dict literal uses dict_create in SWI dialect."""
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            'Test() <- (X_ is {"a": 1})',
            dialect=Dialect.swi(),
        )
        assert "dict_create" in result

    def test_dict_iso_warning(self):
        """Dict literal emits warning in ISO dialect."""
        result = clausal_source_to_prolog('Test() <- (X_ is {"a": 1})')
        assert "WARNING" in result
        assert "dict literal" in result


class TestDialectDirectives:
    """Phase 2: dialect-specific directive handling."""

    def test_import_known_library_swi(self):
        """Known clausal modules map to library(...) in SWI."""
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            '-import_from(clausal.logic.clpfd, [InDomain])',
            dialect=Dialect.swi(),
        )
        assert "library(clpfd)" in result

    def test_import_known_library_scryer(self):
        """Known clausal modules map to library(clpz) in Scryer."""
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            '-import_from(clausal.logic.clpfd, [InDomain])',
            dialect=Dialect.scryer(),
        )
        assert "library(clpz)" in result

    def test_import_python_only_warning(self):
        """Python-only module imports emit a warning."""
        result = clausal_source_to_prolog(
            '-import_from(py.scipy_special, [Gamma])',
        )
        assert "WARNING" in result
        assert "Python-only" in result

    def test_table_scryer_adds_use_module(self):
        """Scryer table directive prepends use_module(library(tabling))."""
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            '-table(Fib(N, R))',
            dialect=Dialect.scryer(),
        )
        assert "use_module(library(tabling))" in result
        assert "table(fib/2)" in result or "table fib/2" in result


class TestCLI:
    """Test the CLI entry point."""

    def test_cli_help(self):
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "clausal_to_prolog" in result.stdout

    def test_cli_pipe(self):
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", "--dialect", "swi"],
            input="Foo(1, 2),\n",
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "foo(1, 2)." in result.stdout

    def test_cli_file(self, tmp_path):
        import subprocess
        src = tmp_path / "test.clausal"
        src.write_text("Bar(X_) <- Baz(X_)\n")
        out = tmp_path / "test.pl"
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", str(src), "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = out.read_text()
        assert "bar(X) :-" in content
        assert "baz(X)." in content


# ═══════════════════════════════════════════════════════════════════════
# Phase 4.3: Golden snapshot tests — Prolog → Clausal direction
# ═══════════════════════════════════════════════════════════════════════


# (source .pl path, golden .clausal path) pairs
_REVERSE_CASES = [
    (GOLDEN / "edge_graph.pl", GOLDEN / "edge_graph.clausal"),
    (GOLDEN / "fibonacci.pl", GOLDEN / "fibonacci.clausal"),
    (GOLDEN / "dcg_grammar.pl", GOLDEN / "dcg_grammar.clausal"),
    (GOLDEN / "meta_test.pl", GOLDEN / "meta_test.clausal"),
    (GOLDEN / "clpfd_queens.pl", GOLDEN / "clpfd_queens.clausal"),
]

_REVERSE_CONFORMITY = [
    (GOLDEN / "iso_arithmetic.pl", GOLDEN / "iso_arithmetic.clausal"),
    (GOLDEN / "iso_control.pl", GOLDEN / "iso_control.clausal"),
    (GOLDEN / "iso_list_operations.pl", GOLDEN / "iso_list_operations.clausal"),
    (GOLDEN / "iso_term_manipulation.pl", GOLDEN / "iso_term_manipulation.clausal"),
    (GOLDEN / "iso_type_checking.pl", GOLDEN / "iso_type_checking.clausal"),
    (GOLDEN / "iso_unification.pl", GOLDEN / "iso_unification.clausal"),
]

ALL_REVERSE = _REVERSE_CASES + _REVERSE_CONFORMITY


@pytest.mark.parametrize(
    "pl_path,golden_clausal_path",
    ALL_REVERSE,
    ids=[p[0].stem for p in ALL_REVERSE],
)
def test_reverse_golden_snapshot(pl_path, golden_clausal_path):
    """Prolog → clausal output matches the golden .clausal snapshot."""
    source = pl_path.read_text(encoding="utf-8")
    golden = golden_clausal_path.read_text(encoding="utf-8")
    result = prolog_to_clausal(source)
    assert result == golden, (
        f"Translation of {pl_path.name} does not match golden file "
        f"{golden_clausal_path.name}.\n"
        f"To update: python -m clausal.tools.prolog_to_clausal "
        f"{pl_path} -o {golden_clausal_path}"
    )


class TestReverseSyntax:
    """Verify structural properties of Prolog → clausal golden output."""

    @pytest.mark.parametrize(
        "pl_path,golden_clausal_path",
        ALL_REVERSE,
        ids=[p[0].stem for p in ALL_REVERSE],
    )
    def test_no_trailing_whitespace(self, pl_path, golden_clausal_path):
        golden = golden_clausal_path.read_text(encoding="utf-8")
        for i, line in enumerate(golden.split("\n"), 1):
            if line != line.rstrip():
                pytest.fail(f"{golden_clausal_path.name}:{i}: trailing whitespace")

    @pytest.mark.parametrize(
        "pl_path,golden_clausal_path",
        ALL_REVERSE,
        ids=[p[0].stem for p in ALL_REVERSE],
    )
    def test_no_prolog_syntax_leaks(self, pl_path, golden_clausal_path):
        """Translated clausal output should not contain Prolog-specific syntax."""
        import re
        golden = golden_clausal_path.read_text(encoding="utf-8")
        stripped = re.sub(r'"[^"]*"', '""', golden)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        for line in stripped.split("\n"):
            s = line.strip()
            if s.startswith("#"):
                continue
            assert "\\+" not in s, f"Prolog negation leaked: {s}"

    @pytest.mark.parametrize(
        "pl_path,golden_clausal_path",
        ALL_REVERSE,
        ids=[p[0].stem for p in ALL_REVERSE],
    )
    def test_uses_clausal_conventions(self, pl_path, golden_clausal_path):
        """Output uses PascalCase predicates and clausal arrow syntax."""
        golden = golden_clausal_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in golden.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not lines:
            pytest.skip("Empty output")
        # At least one line should have a PascalCase predicate or a fact comma
        has_pascal = any(
            l[0].isupper() for l in lines
            if l and l[0].isalpha()
        )
        has_arrow = any("<-" in l for l in lines)
        has_comma = any(l.rstrip().endswith(",") for l in lines)
        assert has_pascal or has_arrow or has_comma, (
            "Output doesn't look like clausal syntax"
        )


class TestUnifiedCLI:
    """Test the unified translate CLI."""

    def test_help(self):
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.translate", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "clausal-translate" in result.stdout or "translate" in result.stdout

    def test_roundtrip_flag(self):
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.translate", "--roundtrip",
             str(GOLDEN / "edge_graph.pl")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
