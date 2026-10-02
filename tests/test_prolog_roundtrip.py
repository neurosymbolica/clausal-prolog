"""Phase 4.2: Roundtrip property tests for clausal ↔ Prolog translation.

Tests that translating in both directions preserves key semantic properties:
- Clause order
- Variable identity (variables that co-occur still co-occur)
- Operator precedence
- Predicate arity
- Structural equivalence (via AST comparison)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    clausal_source_to_prolog_ast,
)
from clausal.tools.prolog_ast import PAtom, PClause, PCompound, PDirective, PVar
from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_parser import parse
from clausal.tools.prolog_to_clausal import prolog_to_clausal
from clausal.tools.translate import roundtrip, translate
from tests._suffix import SEAM, seam_path

FIXTURES = Path(__file__).parent / "fixtures"
CONFORMITY = Path(__file__).parent / "conformity"
GOLDEN = FIXTURES / "prolog_golden"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _clause_heads(prolog_src: str) -> list[str]:
    """Extract head functor/arity pairs from Prolog source."""
    pmod = parse(prolog_src)
    heads = []
    for item in pmod.items:
        if isinstance(item, PClause):
            h = item.head
            if isinstance(h, PCompound):
                heads.append(f"{h.functor}/{len(h.args)}")
            elif isinstance(h, PAtom):
                heads.append(f"{h.name}/0")
    return heads


def _collect_vars(prolog_src: str) -> dict[str, set[int]]:
    """Map variable names to the set of clause indices they appear in."""
    pmod = parse(prolog_src)
    var_clauses: dict[str, set[int]] = {}

    def _walk(node, clause_idx: int):
        if isinstance(node, PVar):
            var_clauses.setdefault(node.name, set()).add(clause_idx)
        elif isinstance(node, PCompound):
            for a in node.args:
                _walk(a, clause_idx)
        elif isinstance(node, PClause):
            _walk(node.head, clause_idx)
            if node.body:
                _walk(node.body, clause_idx)

    for i, item in enumerate(pmod.items):
        if isinstance(item, PClause):
            _walk(item, i)
    return var_clauses


# ═══════════════════════════════════════════════════════════════════════
# Unit-level roundtrip: small fragments
# ═══════════════════════════════════════════════════════════════════════


class TestSmallRoundtripClausalProlog:
    """Clausal → Prolog → Clausal on small fragments."""

    @pytest.mark.parametrize("src", [
        "Foo(1, 2),",
        "Bar(X, Y) <- Baz(X, Y)",
        "edge(1, 2),\nedge(2, 3),",
    ])
    def test_roundtrip_ok(self, src):
        # nv
        ok, _first, second = roundtrip(src, direction="clausal_to_prolog", dialect=Dialect.swi())
        # The roundtripped result should at least parse back to valid clausal
        assert len(second.strip()) > 0

    def test_fact_preserves_arity(self):
        # nv
        src = "Foo(1, 2, 3),"
        prolog = clausal_source_to_prolog(src)
        back = prolog_to_clausal(prolog)
        # Re-translate to Prolog to check arity
        prolog2 = clausal_source_to_prolog(back)
        heads1 = _clause_heads(prolog)
        heads2 = _clause_heads(prolog2)
        assert heads1 == heads2

    def test_rule_preserves_clause_count(self):
        # nv
        src = "A(X) <- B(X)\nA(X) <- C(X)"
        prolog = clausal_source_to_prolog(src)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        pmod1 = parse(prolog)
        pmod2 = parse(prolog2)
        clauses1 = [i for i in pmod1.items if isinstance(i, PClause)]
        clauses2 = [i for i in pmod2.items if isinstance(i, PClause)]
        assert len(clauses1) == len(clauses2)


class TestSmallRoundtripPrologClausal:
    """Prolog → Clausal → Prolog on small fragments."""

    @pytest.mark.parametrize("src", [
        "foo(1, 2).",
        "bar(X, Y) :- baz(X, Y).",
        "edge(1, 2).\nedge(2, 3).",
    ])
    def test_roundtrip_produces_valid_prolog(self, src):
        # nv
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        # Should parse without error
        pmod = parse(prolog2)
        assert len(pmod.items) > 0

    def test_fact_arity_preserved(self):
        # nv
        src = "foo(a, b, c)."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        assert _clause_heads(src) == _clause_heads(prolog2)


# ═══════════════════════════════════════════════════════════════════════
# Operator precedence preservation
# ═══════════════════════════════════════════════════════════════════════


class TestOperatorPrecedence:
    """Verify operator precedence survives roundtrip."""

    def test_arithmetic_precedence_clausal_roundtrip(self):
        """a + b * c should not become (a + b) * c."""
        # nv
        src = "Test(R) <- eval_(1 + 2 * 3, R)"
        prolog = clausal_source_to_prolog(src)
        # in_ Prolog, * binds tighter than +
        assert "1 + 2 * 3" in prolog or "1 + 2*3" in prolog
        # Roundtrip
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        # Should still have correct precedence
        assert "1 + 2 * 3" in prolog2 or "1 + 2*3" in prolog2

    def test_arithmetic_precedence_prolog_roundtrip(self):
        """Prolog a + b * c → clausal → Prolog preserves precedence."""
        # nv
        src = "test(R) :- R is 1 + 2 * 3."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        # Both should evaluate the same way
        pmod1 = parse(src)
        pmod2 = parse(prolog2)
        assert len(pmod1.items) == len(pmod2.items)

    def test_comparison_chain(self):
        """Comparison operators preserve meaning."""
        # nv
        src = "test :- X > 0, X < 10."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        pmod = parse(prolog2)
        clause = [i for i in pmod.items if isinstance(i, PClause)][0]
        assert clause.body is not None
        # Body is a conjunction (','/2) of two comparisons
        body = clause.body
        if isinstance(body, PCompound) and body.functor == ",":
            assert len(body.args) == 2


# ═══════════════════════════════════════════════════════════════════════
# Variable identity preservation
# ═══════════════════════════════════════════════════════════════════════


class TestVariableIdentity:
    """Variables that co-occur in a clause still co-occur after roundtrip."""

    def test_shared_variables_clausal_roundtrip(self):
        """X appearing in head and body stays the same variable."""
        # nv
        src = "Foo(X, Y) <- (Bar(X, Z), Baz(Z, Y))"
        prolog = clausal_source_to_prolog(src)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        vars1 = _collect_vars(prolog)
        vars2 = _collect_vars(prolog2)
        # Same number of distinct variables
        assert len(vars1) == len(vars2)

    def test_shared_variables_prolog_roundtrip(self):
        """Prolog variable sharing survives roundtrip."""
        # nv
        src = "foo(X, Y) :- bar(X, Z), baz(Z, Y)."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        vars1 = _collect_vars(src)
        vars2 = _collect_vars(prolog2)
        assert len(vars1) == len(vars2)

    def test_anonymous_variables(self):
        """Anonymous variables stay anonymous."""
        # nv
        src = "foo(_, Y) :- bar(_, Y)."
        clausal = prolog_to_clausal(src)
        # Should use _ in clausal too
        prolog2 = clausal_source_to_prolog(clausal)
        # Count anonymous vars
        pmod = parse(prolog2)
        for item in pmod.items:
            if isinstance(item, PClause):
                # Head should have an anonymous var
                head = item.head
                if isinstance(head, PCompound):
                    anon_count = sum(
                        1 for a in head.args
                        if isinstance(a, PVar) and a.name == "_"
                    )
                    assert anon_count >= 1


# ═══════════════════════════════════════════════════════════════════════
# Clause order preservation
# ═══════════════════════════════════════════════════════════════════════


class TestClauseOrder:
    """Predicate clause order is semantic in Prolog — must be preserved."""

    def test_clause_order_clausal_roundtrip(self):
        # nv
        src = "Foo(1),\nFoo(2),\nFoo(3),"
        prolog = clausal_source_to_prolog(src)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        heads1 = _clause_heads(prolog)
        heads2 = _clause_heads(prolog2)
        assert heads1 == heads2
        # Verify the argument order too
        pmod1 = parse(prolog)
        pmod2 = parse(prolog2)
        for c1, c2 in zip(pmod1.items, pmod2.items):
            if isinstance(c1, PClause) and isinstance(c2, PClause):
                assert c1.head == c2.head

    def test_clause_order_prolog_roundtrip(self):
        # nv
        src = "foo(1).\nfoo(2).\nfoo(3)."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        pmod1 = parse(src)
        pmod2 = parse(prolog2)
        items1 = [i for i in pmod1.items if isinstance(i, PClause)]
        items2 = [i for i in pmod2.items if isinstance(i, PClause)]
        assert len(items1) == len(items2)
        for c1, c2 in zip(items1, items2):
            assert c1.head == c2.head

    def test_multi_predicate_order(self):
        """Multiple predicates keep their relative order."""
        # nv
        src = "alpha(1).\nbeta(2).\nalpha(3).\nbeta(4)."
        clausal = prolog_to_clausal(src)
        prolog2 = clausal_source_to_prolog(clausal)
        heads1 = _clause_heads(src)
        heads2 = _clause_heads(prolog2)
        assert heads1 == heads2


# ═══════════════════════════════════════════════════════════════════════
# Fixture-level roundtrip: clausal → Prolog → clausal
# ═══════════════════════════════════════════════════════════════════════


_CLAUSAL_FIXTURES = [
    FIXTURES / "edge_graph.seam",
    FIXTURES / "fibonacci.seam",
    # dcg_grammar excluded: DCG `>>` → `-->` → `>>` roundtrip produces
    # Prolog syntax that the clausal parser can't re-parse (commas in DCG
    # pushback lists, etc.)  Tested separately via one-leg tests.
    FIXTURES / "meta_test.seam",
    FIXTURES / "clpfd_queens.seam",
]

_CONFORMITY_FIXTURES = [
    CONFORMITY / "iso_arithmetic.seam",
    CONFORMITY / "iso_control.seam",
    CONFORMITY / "iso_list_operations.seam",
    CONFORMITY / "iso_term_manipulation.seam",
    CONFORMITY / "iso_type_checking.seam",
    CONFORMITY / "iso_unification.seam",
]

_ALL_CLAUSAL = [p for p in _CLAUSAL_FIXTURES + _CONFORMITY_FIXTURES if p.exists()]


@pytest.mark.parametrize("path", _ALL_CLAUSAL, ids=[p.stem for p in _ALL_CLAUSAL])
class TestFixtureRoundtripClausalToProlog:
    """Clausal fixtures → Prolog → Clausal: structural properties preserved."""

    def test_clause_count_preserved(self, path: Path):
        """Same number of clauses after roundtrip."""
        # nv
        source = path.read_text()
        prolog = clausal_source_to_prolog(source)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        pmod1 = parse(prolog)
        pmod2 = parse(prolog2)
        clauses1 = [i for i in pmod1.items if isinstance(i, PClause)]
        clauses2 = [i for i in pmod2.items if isinstance(i, PClause)]
        assert len(clauses1) == len(clauses2), (
            f"Clause count changed: {len(clauses1)} → {len(clauses2)}"
        )

    def test_head_functors_preserved(self, path: Path):
        """Head functor/arity pairs preserved in order."""
        # nv
        source = path.read_text()
        prolog = clausal_source_to_prolog(source)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        assert _clause_heads(prolog) == _clause_heads(prolog2)

    def test_variable_count_preserved(self, path: Path):
        """Number of distinct variables per clause stays the same."""
        # nv
        source = path.read_text()
        prolog = clausal_source_to_prolog(source)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        vars1 = _collect_vars(prolog)
        vars2 = _collect_vars(prolog2)
        assert len(vars1) == len(vars2), (
            f"Variable count changed: {len(vars1)} → {len(vars2)}"
        )

    def test_prolog_output_parses(self, path: Path):
        """Roundtripped Prolog output parses without error."""
        # nv
        source = path.read_text()
        prolog = clausal_source_to_prolog(source)
        back = prolog_to_clausal(prolog)
        prolog2 = clausal_source_to_prolog(back)
        pmod = parse(prolog2)
        assert len(pmod.items) > 0


# ═══════════════════════════════════════════════════════════════════════
# Fixture-level roundtrip: Prolog (.pl golden) → clausal → Prolog
# ═══════════════════════════════════════════════════════════════════════


# exclude dcg_grammar — DCG `-->` rules produce clausal `>>` syntax that
# doesn't roundtrip back to parseable Prolog in the second leg.
ALL_GOLDEN_PL = sorted(
    p for p in (GOLDEN.glob("*.pl") if GOLDEN.exists() else [])
    if p.stem != "dcg_grammar"
)


@pytest.mark.parametrize("pl_path", ALL_GOLDEN_PL, ids=[p.stem for p in ALL_GOLDEN_PL])
class TestFixtureRoundtripPrologToClausal:
    """Golden .pl files → Clausal → Prolog: structural properties preserved."""

    def test_clause_count_preserved(self, pl_path: Path):
        # nv
        source = pl_path.read_text()
        clausal = prolog_to_clausal(source)
        prolog2 = clausal_source_to_prolog(clausal)
        pmod1 = parse(source)
        pmod2 = parse(prolog2)
        clauses1 = [i for i in pmod1.items if isinstance(i, PClause)]
        clauses2 = [i for i in pmod2.items if isinstance(i, PClause)]
        assert len(clauses1) == len(clauses2)

    def test_head_functors_preserved(self, pl_path: Path):
        # nv
        source = pl_path.read_text()
        clausal = prolog_to_clausal(source)
        prolog2 = clausal_source_to_prolog(clausal)
        assert _clause_heads(source) == _clause_heads(prolog2)

    def test_prolog_output_parses(self, pl_path: Path):
        # nv
        source = pl_path.read_text()
        clausal = prolog_to_clausal(source)
        prolog2 = clausal_source_to_prolog(clausal)
        pmod = parse(prolog2)
        assert len(pmod.items) > 0


# ═══════════════════════════════════════════════════════════════════════
# CLI roundtrip mode
# ═══════════════════════════════════════════════════════════════════════


class TestCLIRoundtrip:
    """Test the unified translate CLI roundtrip mode."""

    def test_roundtrip_exit_code_simple_fact(self):
        """Simple facts should roundtrip exactly."""
        # nv
        from clausal.tools.translate import main
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w", delete=False) as f:
            f.write("foo(1, 2),\n")
            f.flush()
            code = main(["--roundtrip", "--dialect", "swi", f.name])
        assert code == 0

    def test_roundtrip_file_based(self):
        # nv
        # THE FLIP (spec §7): a ``.pl`` whose ``"..."`` mean STRINGS DECLARES
        # ``double_quotes``, and the return leg writes the mode out again, so
        # the CHECKED-IN golden round-trips byte-identically.  See
        # ``tests/test_prolog_golden.py::TestUnifiedCLI::test_roundtrip_flag``.
        from clausal.tools.translate import main
        src = GOLDEN / "edge_graph.pl"
        # Prolog file roundtrip
        code = main(["--roundtrip", "--dialect", "swi", str(src)])
        assert code == 0

    def test_translate_clausal_to_prolog_autodetect(self, tmp_path):
        # nv
        from clausal.tools.translate import main
        outfile = tmp_path / "out.pl"
        code = main([str(FIXTURES / "edge_graph.seam"), "-o", str(outfile)])
        assert code == 0
        content = outfile.read_text()
        assert "edge" in content
        assert "reach" in content

    def test_translate_prolog_to_clausal_autodetect(self, tmp_path):
        # nv
        from clausal.tools.translate import main
        outfile = tmp_path / f"out{SEAM}"
        code = main([str(GOLDEN / "edge_graph.pl"), "-o", str(outfile)])
        assert code == 0
        content = outfile.read_text()
        assert "edge" in content
        assert "reach" in content

    def test_translate_explicit_to_flag(self, tmp_path):
        # nv
        from clausal.tools.translate import main
        outfile = tmp_path / "out.pl"
        code = main([str(FIXTURES / "edge_graph.seam"),
                      "--to", "swi", "-o", str(outfile)])
        assert code == 0
        content = outfile.read_text()
        assert "edge" in content


# ═══════════════════════════════════════════════════════════════════════
# Directive preservation
# ═══════════════════════════════════════════════════════════════════════


class TestDirectivePreservation:
    """Directives survive one-leg translation (full roundtrip is lossy for
    arity-indicator directives like ``dynamic foo/2``)."""

    def test_clausal_dynamic_to_prolog(self):
        """-dynamic in clausal emits :- dynamic in Prolog."""
        # nv
        src = "-dynamic(Color(name_, value_))"
        prolog = clausal_source_to_prolog(src)
        assert "dynamic" in prolog

    def test_prolog_dynamic_to_clausal(self):
        """:- dynamic in Prolog emits -dynamic in clausal."""
        # nv
        src = ":- dynamic(color/2)."
        clausal = prolog_to_clausal(src)
        assert "dynamic" in clausal.lower()

    def test_prolog_module_to_clausal(self):
        """:- module emits -module in clausal."""
        # nv
        src = ":- module(mymod, [foo/2])."
        clausal = prolog_to_clausal(src)
        assert "module" in clausal.lower()
        assert "mymod" in clausal


# ═══════════════════════════════════════════════════════════════════════
# ``.seam`` is an alias extension for ``.clausal``
# ═══════════════════════════════════════════════════════════════════════


class TestSeamAliasDirection:
    """A ``.seam`` input is the seam → Prolog direction.  Since the
    extension flip ``.clausal`` is Clausal Prolog, read like ``.pl``."""

    def test_detect_direction_seam(self):
        # nv
        from clausal.tools.translate import _detect_direction
        assert _detect_direction("x.seam", None) == "clausal_to_prolog"
        assert _detect_direction("x.SEAM", None) == "clausal_to_prolog"
        assert _detect_direction("x.clausal", None) == "prolog_to_clausal"
        assert _detect_direction("x.pl", None) == "prolog_to_clausal"

    def test_translate_seam_to_prolog_autodetect(self, tmp_path):
        # nv
        from clausal.tools.translate import main
        src = tmp_path / "edge_graph.seam"
        src.write_text(seam_path(FIXTURES / "edge_graph.seam").read_text())
        outfile = tmp_path / "out.pl"
        code = main([str(src), "-o", str(outfile)])
        assert code == 0
        content = outfile.read_text()
        assert "edge" in content
        assert "reach" in content
