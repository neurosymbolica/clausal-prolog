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
from tests._suffix import SEAM

FIXTURES = Path(__file__).parent / "fixtures"
CONFORMITY = Path(__file__).parent / "conformity"
GOLDEN = FIXTURES / "prolog_golden"

# (source_path, golden_path) pairs
_FIXTURE_CASES = [
    (FIXTURES / "edge_graph.seam", GOLDEN / "edge_graph.pl"),
    (FIXTURES / "fibonacci.seam", GOLDEN / "fibonacci.pl"),
    (FIXTURES / "dcg_grammar.seam", GOLDEN / "dcg_grammar.pl"),
    (FIXTURES / "meta_test.seam", GOLDEN / "meta_test.pl"),
    (FIXTURES / "clpfd_queens.seam", GOLDEN / "clpfd_queens.pl"),
]

_CONFORMITY_CASES = [
    (CONFORMITY / "iso_arithmetic.seam", GOLDEN / "iso_arithmetic.pl"),
    (CONFORMITY / "iso_control.seam", GOLDEN / "iso_control.pl"),
    (CONFORMITY / "iso_list_operations.seam", GOLDEN / "iso_list_operations.pl"),
    (CONFORMITY / "iso_term_manipulation.seam", GOLDEN / "iso_term_manipulation.pl"),
    (CONFORMITY / "iso_type_checking.seam", GOLDEN / "iso_type_checking.pl"),
    (CONFORMITY / "iso_unification.seam", GOLDEN / "iso_unification.pl"),
]

ALL_CASES = _FIXTURE_CASES + _CONFORMITY_CASES


def _case_id(pair):
    return pair[0].stem


@pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
def test_golden_snapshot(source_path, golden_path):
    """Translation output matches the golden .pl snapshot."""
    # nv
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
        """Every emitted clause is terminated.

        A continuation line (an indented body goal) does not end with '.', so
        the unit is the CLAUSE, not the line: the emitter separates clauses --
        facts, rules, DCG rules and directives alike -- with a blank line, so a
        run of consecutive non-blank lines is one clause and its LAST line
        carries the terminator.

        This assertion is the whole test. It previously consisted of a loop
        whose body was three comments, so all 11 parametrisations passed
        against any output whatsoever, including output with no terminators at
        all; the group count is asserted below so it cannot go hollow that way
        again by the groups silently becoming empty.
        """
        # nv
        golden = golden_path.read_text(encoding="utf-8")
        groups, cur = [], []
        for line in golden.split("\n"):
            if line.strip():
                cur.append(line)
            elif cur:
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)

        assert groups, f"{golden_path.name}: no clauses found -- nothing was checked"
        for group in groups:
            last = group[-1].strip()
            assert last.endswith("."), (
                f"{golden_path.name}: clause beginning {group[0].strip()!r} "
                f"is not terminated; its last line is {last!r}"
            )

    @pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
    def test_no_trailing_whitespace(self, source_path, golden_path):
        """No lines have trailing whitespace."""
        # nv
        golden = golden_path.read_text(encoding="utf-8")
        for i, line in enumerate(golden.split("\n"), 1):
            if line != line.rstrip():
                pytest.fail(f"{golden_path.name}:{i}: trailing whitespace")

    @pytest.mark.parametrize("source_path,golden_path", ALL_CASES, ids=[_case_id(c) for c in ALL_CASES])
    def test_no_python_syntax_leaks(self, source_path, golden_path):
        """Translated output should not contain clausal-specific syntax."""
        # nv
        import re
        golden = golden_path.read_text(encoding="utf-8")
        # Strip COMMENTS first. The subject of this test is emitted Prolog
        # CODE; a `/* ... */` block is prose -- the translator's own warning
        # channel -- and English prose may legitimately contain the word
        # "and". Without this the check false-positives on any warning that
        # happens to use it (the `"[]"` literal warning does).
        stripped = re.sub(r"/\*.*?\*/", "", golden, flags=re.DOTALL)
        stripped = re.sub(r"(?m)%.*$", "", stripped)
        # Then strip quoted strings before checking for Python keywords
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "<-" not in stripped, "Clausal arrow '<-' found in Prolog output"
        assert " and " not in stripped, "Clausal 'and' found in Prolog output"


class TestInNotIn:
    """Tests for the in/not-in → member translation."""

    def test_in_translates_to_member(self):
        # nv
        # _x crosses unchanged. It occurs once, so the singleton post-pass
        # would underscore-prefix it -- but it is already underscore-led and
        # is left alone. (These read `_X` while the exporter titlecased `_x`
        # to `X` and the singleton pass then put an underscore back.)
        result = clausal_source_to_prolog("Test() <- (_x in [1, 2, 3])")
        assert "member(_x, [1, 2, 3])" in result

    def test_not_in_translates_to_negated_member(self):
        # nv
        result = clausal_source_to_prolog("Test() <- (_x not in [1, 2, 3])")
        assert "\\+ member(_x, [1, 2, 3])" in result or "\\+(member(_x, [1, 2, 3]))" in result

    # The PREDICATE spelling of membership. Clausal registers ``in_/2`` in
    # exactly one place -- clausal/logic/builtins/lists.py, ``_member__2`` --
    # and it is member/2, so the ISO name has to be member/2 too. It used to
    # resolve to a bare ``in/2`` (see prolog_dialect.BUILTIN_NAME_MAP), which
    # no ISO engine defines: every downstream library that spells membership as a
    # call (three downstream helper libraries) exported a
    # program that died with existence_error(procedure, in/2) on first use.

    def test_in_call_form_translates_to_member(self):
        # nv
        result = clausal_source_to_prolog("Test() <- in_(_x, [1, 2, 3])")
        assert "member(_x, [1, 2, 3])" in result

    def test_in_call_form_does_not_emit_bare_in(self):
        # nv
        result = clausal_source_to_prolog("Test() <- in_(_x, [1, 2, 3])")
        assert "in(_x" not in result.replace("member(_x", "")

    def test_negated_in_call_form_matches_the_operator_form(self):
        """``not in_(X, L)`` and ``X not in L`` must lower the same way.

        Clausal's ``not in`` is NEGATION AS FAILURE, not a dif-family
        constraint: MemberIn(negate=True) scans the collection and UNDOES the
        trail mark on both branches (clausal/logic/compiler/
        _lower_goalop_shared.py), so nothing is posted and an unbound element
        FAILS rather than suspending -- measured on the live engine, where
        ``X not in [1,2,3]`` with X unbound yields no solutions while
        ``X is not 1`` succeeds with a residual. ``\\+ member/2`` is therefore
        the faithful ISO form for both spellings; a pure dif-chain companion
        would succeed where the engine fails.
        """
        # nv
        # Parenthesised because `<-` parses as Lt+USub, and Python refuses a
        # bare `not` directly after an operator (downstream spells it the same
        # way, inside a parenthesised body).
        call_form = clausal_source_to_prolog(
            "Test() <- (not in_(_x, [1, 2, 3]))")
        assert ("\\+ member(_x, [1, 2, 3])" in call_form
                or "\\+(member(_x, [1, 2, 3]))" in call_form)

    def test_in_check_call_form_still_memberchk(self):
        """The sibling entry is unchanged: in_check/2 is memberchk/2, not
        member/2 -- pinned so the in_ repair cannot smear across it."""
        # nv
        result = clausal_source_to_prolog("Test() <- in_check(_x, [1, 2, 3])")
        assert "memberchk(_x, [1, 2, 3])" in result


class TestKeywordArgs:
    """Tests for keyword argument handling in clause heads."""

    def test_keyword_fact(self):
        # nv
        result = clausal_source_to_prolog("Fib(N=0, RESULT=0),")
        assert "fib(0, 0)." in result

    def test_keyword_mixed(self):
        # nv
        result = clausal_source_to_prolog("Foo(1, Y=2),")
        assert "foo(1, 2)." in result


class TestUntranslatable:
    """Phase 2: untranslatable construct handling."""

    def test_double_uadd_warning(self):
        """++expr emits a warning comment."""
        # nv
        result = clausal_source_to_prolog("Test() <- (_r is ++len(_l))")
        assert "WARNING" in result
        assert "untranslatable" in result
        assert "len" in result

    def test_fstring_swi_format(self):
        """f-strings become format/2 in SWI dialect."""
        # nv
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            'Test() <- (_x is f"hello {NAME}")',
            dialect=Dialect.swi(),
        )
        assert "format" in result
        assert "~w" in result

    def test_fstring_iso_warning(self):
        """f-strings emit a warning in ISO dialect."""
        # nv
        result = clausal_source_to_prolog('Test() <- (_x is f"hello {NAME}")')
        assert "WARNING" in result
        assert "f-string" in result

    def test_set_single_element_is_curly(self):
        """Single-element set {Goal} becomes DCG inline goal."""
        # nv
        result = clausal_source_to_prolog("Test() <- {_x > 0}")
        assert "{" in result
        assert "WARNING" not in result

    def test_set_multi_element_warning(self):
        """Multi-element set emits a warning."""
        # nv
        result = clausal_source_to_prolog("Test() <- {1, 2, 3}")
        assert "WARNING" in result
        assert "set literal" in result

    def test_dict_swi(self):
        """Dict literal uses dict_create in SWI dialect."""
        # nv
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            'Test() <- (_x is {"a": 1})',
            dialect=Dialect.swi(),
        )
        assert "dict_create" in result

    def test_dict_iso_lowers_to_attribute_list(self):
        """Dict literal lowers to an attribute-list in ISO dialect (no warning)."""
        # nv
        result = clausal_source_to_prolog('-double_quotes(atom)\nTest() <- (_x is {"a": 1})')
        assert "WARNING" not in result
        # The dict KEY is a str literal, so it lowers to an atom like any
        # other (R2). Both sides of a profile_get/tri_get/attrs_put
        # comparison migrate together, so lookups still match.
        assert "attribute(a, 1)" in result

    def test_dict_splat_iso_warning(self):
        """Dict splat not in first position still emits a warning in ISO
        dialect (task 2 only lowers the splat-FIRST `is`-RHS shape)."""
        # nv
        result = clausal_source_to_prolog('Test() <- (_x is {a: 1, **base()})')
        assert "WARNING" in result
        assert "dict splat" in result


class TestDialectDirectives:
    """Phase 2: dialect-specific directive handling."""

    def test_import_known_library_swi(self):
        """Known clausal modules map to library(...) in SWI."""
        # nv
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            '-import_from(clausal.logic.clpfd, [in_domain])',
            dialect=Dialect.swi(),
        )
        assert "library(clpfd)" in result

    def test_import_known_library_scryer(self):
        """Known clausal modules map to library(clpz) in Scryer."""
        # nv
        from clausal.tools.prolog_dialect import Dialect
        result = clausal_source_to_prolog(
            '-import_from(clausal.logic.clpfd, [in_domain])',
            dialect=Dialect.scryer(),
        )
        assert "library(clpz)" in result

    def test_import_python_only_warning(self):
        """Python-only module imports emit a warning."""
        # nv
        result = clausal_source_to_prolog(
            '-import_from(py.scipy_special, [Gamma])',
        )
        assert "WARNING" in result
        assert "Python-only" in result

    def test_table_scryer_adds_use_module(self):
        """Scryer table directive prepends use_module(library(tabling))."""
        # nv
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
        # nv
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "clausal_to_prolog" in result.stdout

    def test_cli_pipe(self):
        # nv
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", "--dialect", "swi"],
            input="Foo(1, 2),\n",
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "foo(1, 2)." in result.stdout

    def test_cli_file(self, tmp_path):
        # nv
        import subprocess
        src = tmp_path / f"test{SEAM}"
        src.write_text("Bar(_x) <- Baz(_x)\n")
        out = tmp_path / "test.pl"
        result = subprocess.run(
            ["python", "-m", "clausal.tools.clausal_to_prolog", str(src), "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = out.read_text()
        # Was bar(X)/baz(X): _x used to be uppercased on export.
        assert "bar(_x) :-" in content
        assert "baz(_x)." in content


# ═══════════════════════════════════════════════════════════════════════
# Phase 4.3: Golden snapshot tests — Prolog → Clausal direction
# ═══════════════════════════════════════════════════════════════════════


# (source .pl path, golden .clausal path) pairs
_REVERSE_CASES = [
    (GOLDEN / "edge_graph.pl", GOLDEN / "edge_graph.seam"),
    (GOLDEN / "fibonacci.pl", GOLDEN / "fibonacci.seam"),
    (GOLDEN / "dcg_grammar.pl", GOLDEN / "dcg_grammar.seam"),
    (GOLDEN / "meta_test.pl", GOLDEN / "meta_test.seam"),
    (GOLDEN / "clpfd_queens.pl", GOLDEN / "clpfd_queens.seam"),
]

_REVERSE_CONFORMITY = [
    (GOLDEN / "iso_arithmetic.pl", GOLDEN / "iso_arithmetic.seam"),
    (GOLDEN / "iso_control.pl", GOLDEN / "iso_control.seam"),
    (GOLDEN / "iso_list_operations.pl", GOLDEN / "iso_list_operations.seam"),
    (GOLDEN / "iso_term_manipulation.pl", GOLDEN / "iso_term_manipulation.seam"),
    (GOLDEN / "iso_type_checking.pl", GOLDEN / "iso_type_checking.seam"),
    (GOLDEN / "iso_unification.pl", GOLDEN / "iso_unification.seam"),
]

ALL_REVERSE = _REVERSE_CASES + _REVERSE_CONFORMITY


@pytest.mark.parametrize(
    "pl_path,golden_clausal_path",
    ALL_REVERSE,
    ids=[p[0].stem for p in ALL_REVERSE],
)
def test_reverse_golden_snapshot(pl_path, golden_clausal_path):
    """Prolog → clausal output matches the golden .clausal snapshot."""
    # nv
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
        # nv
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
        # nv
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
        """Output uses lowercase predicates and clausal arrow syntax."""
        # nv
        golden = golden_clausal_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in golden.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not lines:
            pytest.skip("Empty output")
        # No clause line starts with a TitleCase name: that spelling does not
        # load, so the translator must never emit it.
        titlecase = [
            l for l in lines
            if l[0].isupper() and any(c.islower() for c in l.split("(")[0])
        ]
        assert not titlecase, titlecase
        has_arrow = any("<-" in l for l in lines)
        has_comma = any(l.rstrip().endswith(",") for l in lines)
        assert has_arrow or has_comma, (
            "Output doesn't look like clausal syntax"
        )


class TestUnifiedCLI:
    """Test the unified translate CLI."""

    def test_help(self):
        # nv
        import subprocess
        result = subprocess.run(
            ["python", "-m", "clausal.tools.translate", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "clausal-translate" in result.stdout or "translate" in result.stdout

    def test_roundtrip_flag(self):
        # nv
        # THE FLIP (spec §7): a ``.pl`` whose ``"..."`` mean STRINGS DECLARES
        # that mode -- the clausal side spells it ``-double_quotes(chars)``
        # and the return leg writes it back out, so the checked-in golden
        # carries ``:- double_quotes(chars).`` and the trip is byte-identical.
        # The CHECKED-IN fixture is the subject on purpose: a synthetic file
        # written by the test would only round-trip itself.
        import subprocess
        src = GOLDEN / "edge_graph.pl"
        result = subprocess.run(
            ["python", "-m", "clausal.tools.translate", "--roundtrip", str(src)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


# ═══════════════════════════════════════════════════════════════════════
# Round-trip fidelity of variable names (2026-09-10)
# ═══════════════════════════════════════════════════════════════════════

#: The cases whose variables survive a full round trip intact. The other
#: fixtures are excluded for reasons that have nothing to do with naming and
#: were true before it changed:
#:
#:  - dcg_grammar declares the DCG state arguments `_s`/`_s0` explicitly and
#:    the export writes `-->`, which hides them.
#:  - the iso_* conformity files contain constructs the translator refuses
#:    (if-then-else and friends), so the clauses holding some of their
#:    variables never reach the golden at all.
#:
#: Narrow on purpose: a check that passed because it excluded everything
#: interesting would be worse than none.
_ROUND_TRIP_CASES = [
    (FIXTURES / "edge_graph.seam", GOLDEN / "edge_graph.seam"),
    (FIXTURES / "fibonacci.seam", GOLDEN / "fibonacci.seam"),
    (FIXTURES / "meta_test.seam", GOLDEN / "meta_test.seam"),
    (FIXTURES / "clpfd_queens.seam", GOLDEN / "clpfd_queens.seam"),
]


def _logic_var_names(text: str) -> set[str]:
    """Every logic-variable name in some Clausal text.

    Classification is delegated to the loader's own predicate rather than
    guessed from the case of the first letter -- that rule has changed twice
    and the test should follow it, not restate it.
    """
    import re
    from clausal.templating.term_rewriting import _is_logic_var_name
    body = re.sub(r"(?m)#.*$", "", text)
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body)
            if _is_logic_var_name(t)}


@pytest.mark.parametrize(
    "source_path,round_trip_path",
    _ROUND_TRIP_CASES,
    ids=[p[0].stem for p in _ROUND_TRIP_CASES],
)
def test_variable_names_survive_the_round_trip(source_path, round_trip_path):
    """Clausal -> .pl -> Clausal returns the source's own variable names.

    The two goldens either side of this are snapshots: they pin what the
    translator emits, but a snapshot cannot tell a correct regeneration from
    a wrong one -- it agrees with whatever produced it. This asserts a
    PROPERTY across the pair instead, so regenerating both goldens from
    broken code fails here.

    It could not have been written before 2026-09-10: names were mangled
    outbound and mangled differently inbound, so `NUMBERS` left as `Numbers`
    and came back as `_numbers`, and the round trip lost every spelling.

    One transformation is legitimate and is spelled out rather than waved
    through: a variable occurring exactly once is underscore-prefixed on
    export to silence the ISO singleton warning, so `X_UNUSED` returns as
    `_X_UNUSED`. Everything else must come back identical.
    """
    source = _logic_var_names(source_path.read_text(encoding="utf-8"))
    back = _logic_var_names(round_trip_path.read_text(encoding="utf-8"))

    unchanged = source & back
    prefixed = {name for name in source - back if "_" + name in back}
    assert source - unchanged - prefixed == set(), (
        f"variables lost in the round trip: "
        f"{sorted(source - unchanged - prefixed)}")
    assert back - unchanged - {"_" + n for n in prefixed} == set(), (
        f"variables invented by the round trip: "
        f"{sorted(back - unchanged - {'_' + n for n in prefixed})}")

    # Positive control: this fixture must actually exercise the identity
    # branch. Without it the test would pass on a translator that prefixed
    # EVERY variable, since every name would land in `prefixed`.
    assert unchanged, f"{source_path.name} exercises nothing"
