"""Tests for Phase 3.3 — Prolog → Clausal translation."""

from __future__ import annotations

import pytest
from pathlib import Path

from clausal.tools.prolog_to_clausal import (
    prolog_to_clausal, prolog_ast_to_clausal,
    emit_clausal_term, emit_clausal_item,
    PrologTranslationError,
)
from clausal.tools.prolog_parser import parse
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PModule,
)
from clausal.tools.prolog_dialect import Dialect


# ═══════════════════════════════════════════════════════════════════════
# Term emission tests
# ═══════════════════════════════════════════════════════════════════════


class TestEmitTerm:
    def test_atom(self):
        # nv
        assert emit_clausal_term(PAtom("foo")) == "foo"

    def test_variable_single_letter(self):
        # nv
        assert emit_clausal_term(PVar("X")) == "X"

    def test_variable_titlecase(self):
        # nv
        assert emit_clausal_term(PVar("Head")) == "_head"

    def test_variable_anonymous(self):
        # nv
        assert emit_clausal_term(PVar("_")) == "_"

    def test_variable_named_underscore(self):
        # nv
        assert emit_clausal_term(PVar("_Ignored")) == "_ignored"

    def test_integer(self):
        # nv
        assert emit_clausal_term(PNumber(42)) == "42"

    def test_float(self):
        # nv
        assert emit_clausal_term(PNumber(3.14)) == "3.14"

    def test_string(self):
        # nv
        assert emit_clausal_term(PString("hello")) == "'hello'"

    def test_empty_list(self):
        # nv
        assert emit_clausal_term(PList((), None)) == "[]"

    def test_proper_list(self):
        # nv
        result = emit_clausal_term(PList((PNumber(1), PNumber(2)), None))
        assert result == "[1, 2]"

    def test_partial_list(self):
        # nv
        result = emit_clausal_term(PList((PVar("H"),), PVar("T")))
        assert result == "[H, *T]"

    def test_compound(self):
        # nv
        result = emit_clausal_term(PCompound("foo_bar", (PVar("X"),)))
        assert result == "FooBar(X)"

    def test_negation(self):
        # nv
        result = emit_clausal_term(PCompound("\\+", (PAtom("foo"),)))
        assert result == "not foo"

    def test_unification(self):
        # nv
        result = emit_clausal_term(PCompound("=", (PVar("X"), PNumber(1))))
        assert result == "X is 1"

    def test_arithmetic_is(self):
        # nv
        result = emit_clausal_term(PCompound("is", (PVar("Y"), PCompound("+", (PVar("X"), PNumber(1))))))
        assert result == "eval_(X + 1, Y)"


# ═══════════════════════════════════════════════════════════════════════
# Item emission tests
# ═══════════════════════════════════════════════════════════════════════


class TestEmitItem:
    def test_fact(self):
        # nv
        result = emit_clausal_item(PClause(PCompound("edge", (PNumber(1), PNumber(2)))))
        assert result == "Edge(1, 2),"

    def test_rule(self):
        # nv
        result = emit_clausal_item(PClause(
            PCompound("reach", (PVar("X"), PVar("Y"))),
            PCompound("edge", (PVar("X"), PVar("Y"))),
        ))
        assert result == "Reach(X, Y) <- (Edge(X, Y))"

    def test_rule_with_conjunction(self):
        # nv
        body = PCompound(",", (
            PCompound("edge", (PVar("X"), PVar("Z"))),
            PCompound("reach", (PVar("Z"), PVar("Y"))),
        ))
        result = emit_clausal_item(PClause(
            PCompound("reach", (PVar("X"), PVar("Y"))),
            body,
        ))
        assert result == "Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))"

    def test_dcg_rule(self):
        # nv
        result = emit_clausal_item(PDCGRule(
            PAtom("greeting"),
            PList((PString("hello"), PString("world")), None),
        ))
        assert result == "Greeting() >> (['hello', 'world'])"

    def test_directive_module(self):
        # nv
        result = emit_clausal_item(PDirective(
            PCompound("module", (PAtom("test"), PList((), None))),
        ))
        assert result == "-module(test, [])"

    def test_directive_dynamic(self):
        # nv
        result = emit_clausal_item(PDirective(
            PCompound("dynamic", (PCompound("/", (PAtom("color"), PNumber(2))),)),
        ))
        assert result == "-dynamic(Color/2)"


# ═══════════════════════════════════════════════════════════════════════
# Full translation tests
# ═══════════════════════════════════════════════════════════════════════


class TestFullTranslation:
    def test_edge_graph(self):
        # nv
        src = """\
edge(1, 2).
edge(2, 3).
reach(X, Y) :- edge(X, Y).
reach(X, Y) :- edge(X, Z), reach(Z, Y).
"""
        result = prolog_to_clausal(src)
        assert "Edge(1, 2)," in result
        assert "Edge(2, 3)," in result
        assert "Reach(X, Y) <- (Edge(X, Y))" in result
        assert "Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))" in result

    def test_arithmetic(self):
        # nv
        src = "double(X, Y) :- Y is X * 2."
        result = prolog_to_clausal(src)
        assert "eval_(X * 2, Y)" in result

    def test_negation(self):
        # nv
        src = "test :- \\+ member(X, [1, 2])."
        result = prolog_to_clausal(src)
        assert "not" in result

    def test_list_cons(self):
        # nv
        src = "head([H|T], H)."
        result = prolog_to_clausal(src)
        assert "[_head, *_tail]" in result or "[H, *T]" in result.replace("_head", "H").replace("_tail", "T")

    def test_unification(self):
        # nv
        src = "test :- X = foo."
        result = prolog_to_clausal(src)
        assert "X is foo" in result

    def test_disunification(self):
        # nv
        src = "test :- X \\= foo."
        result = prolog_to_clausal(src)
        assert "X is not foo" in result

    def test_comparison_leq(self):
        # nv
        src = "test :- 1 =< 2."
        result = prolog_to_clausal(src)
        assert "<=" in result

    def test_structural_equality(self):
        # nv
        src = "test :- X == 1."
        result = prolog_to_clausal(src)
        assert "X == 1" in result

    def test_structural_inequality(self):
        # nv
        src = "test :- X \\== 1."
        result = prolog_to_clausal(src)
        assert "X != 1" in result

    def test_disjunction(self):
        # nv
        src = "test :- (a = b ; c = d)."
        result = prolog_to_clausal(src)
        assert "or" in result

    def test_if_then_else_rejected(self):
        # nv
        src = "max(X, Y, Z) :- (X >= Y -> Z = X ; Z = Y)."
        with pytest.raises(PrologTranslationError, match="If-then-else"):
            prolog_to_clausal(src)

    def test_bare_if_then_rejected(self):
        # nv
        src = "foo(X) :- (X > 0 -> bar(X))."
        with pytest.raises(PrologTranslationError, match="If-then"):
            prolog_to_clausal(src)

    def test_member_to_in(self):
        # nv
        src = "test :- member(X, [1, 2, 3])."
        result = prolog_to_clausal(src)
        assert "X in [1, 2, 3]" in result

    def test_builtin_name_mapping(self):
        # nv
        src = "test :- findall(X, member(X, L), Xs)."
        result = prolog_to_clausal(src)
        assert "findall" in result

    def test_module_directive(self):
        # nv
        src = ":- module(test, [foo/2, bar/1])."
        result = prolog_to_clausal(src)
        assert "-module(test, [Foo/2, Bar/1])" in result

    def test_dynamic_directive(self):
        # nv
        src = ":- dynamic(color/2)."
        result = prolog_to_clausal(src)
        assert "-dynamic(Color/2)" in result

    def test_use_module(self):
        # nv
        src = ":- use_module(library(clpfd), [all_different/1])."
        result = prolog_to_clausal(src, dialect=Dialect.swi())
        assert "import_from" in result

    def test_dcg_rule(self):
        # nv
        src = """\
greeting --> ["hello", "world"].
"""
        result = prolog_to_clausal(src)
        assert ">>" in result

    def test_cut_rejected(self):
        # nv — A10-F001: cut cannot be translated (cut-free contract); a
        # body-position ! raises, matching term-position ! and docs/import.md.
        src = "foo(X) :- bar(X), !."
        with pytest.raises(PrologTranslationError, match="[Cc]ut"):
            prolog_to_clausal(src)

    def test_cut_fact_rejected(self):
        """A bare cut as a goal in a clause body is rejected (A10-F001)."""
        # nv
        src = "foo :- !."
        with pytest.raises(PrologTranslationError, match="[Cc]ut"):
            prolog_to_clausal(src)

    def test_op_directive_as_comment(self):
        # nv
        src = ":- op(700, xfx, <>)."
        result = prolog_to_clausal(src)
        assert "# operator:" in result


class TestNamingConventions:
    def test_snake_to_pascal(self):
        # nv
        src = "all_different([1, 2, 3])."
        result = prolog_to_clausal(src)
        assert "all_different" in result

    def test_variable_conversion(self):
        # nv
        src = "foo(Head, Tail)."
        result = prolog_to_clausal(src)
        assert "_head" in result
        assert "_tail" in result

    def test_single_letter_var(self):
        # nv
        src = "foo(X, Y)."
        result = prolog_to_clausal(src)
        assert "X" in result
        assert "Y" in result

    def test_anonymous_var(self):
        # nv
        src = "foo(_, X)."
        result = prolog_to_clausal(src)
        assert "_" in result


class TestDialects:
    def test_swi_default(self):
        # nv
        src = "edge(1, 2)."
        result = prolog_to_clausal(src, dialect=Dialect.swi())
        assert "Edge(1, 2)," in result

    def test_iso_default(self):
        # nv
        src = "edge(1, 2)."
        result = prolog_to_clausal(src, dialect=Dialect.iso())
        assert "Edge(1, 2)," in result


# ═══════════════════════════════════════════════════════════════════════
# Golden file roundtrip tests
# ═══════════════════════════════════════════════════════════════════════


GOLDEN_DIR = Path(__file__).parent / "fixtures" / "prolog_golden"

GOLDEN_CASES = [
    "edge_graph",
    "fibonacci",
]


@pytest.mark.parametrize("case", GOLDEN_CASES)
class TestGoldenRoundtrip:
    """Parse golden .pl files and verify they produce valid clausal output."""

    def test_parses_without_error(self, case: str):
        # nv
        pl_path = GOLDEN_DIR / f"{case}.pl"
        if not pl_path.exists():
            pytest.skip(f"Golden file {pl_path} not found")
        source = pl_path.read_text()
        # Should parse without error
        pmodule = parse(source)
        assert len(pmodule.items) > 0

    def test_emits_clausal_output(self, case: str):
        # nv
        pl_path = GOLDEN_DIR / f"{case}.pl"
        if not pl_path.exists():
            pytest.skip(f"Golden file {pl_path} not found")
        source = pl_path.read_text()
        result = prolog_to_clausal(source)
        # Should produce non-empty output
        assert len(result.strip()) > 0
        # Should not contain Prolog-specific syntax
        assert ":-" not in result
        assert "\\+" not in result

    def test_no_prolog_syntax_leaks(self, case: str):
        # nv
        pl_path = GOLDEN_DIR / f"{case}.pl"
        if not pl_path.exists():
            pytest.skip(f"Golden file {pl_path} not found")
        source = pl_path.read_text()
        result = prolog_to_clausal(source)
        # Check no Prolog-specific tokens leaked
        lines = result.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # comments are OK
            assert "\\+" not in stripped, f"Prolog negation leaked: {stripped}"


# ═══════════════════════════════════════════════════════════════════════
# All golden .pl files should parse
# ═══════════════════════════════════════════════════════════════════════


ALL_GOLDEN = list(GOLDEN_DIR.glob("*.pl")) if GOLDEN_DIR.exists() else []


@pytest.mark.parametrize("pl_path", ALL_GOLDEN, ids=[p.stem for p in ALL_GOLDEN])
def test_golden_pl_parses(pl_path: Path):
    """Every golden .pl file should parse without error."""
    # nv
    source = pl_path.read_text()
    pmodule = parse(source)
    assert len(pmodule.items) > 0


@pytest.mark.parametrize("pl_path", ALL_GOLDEN, ids=[p.stem for p in ALL_GOLDEN])
def test_golden_pl_translates(pl_path: Path):
    """Every golden .pl file should translate to non-empty clausal output."""
    # nv
    source = pl_path.read_text()
    result = prolog_to_clausal(source)
    assert len(result.strip()) > 0


class TestIsImportsAsEval:
    """Prolog is/2 imports as the eval_/2 builtin (not the deprecated :=)."""

    def test_is_imports_as_eval(self):
        # nv
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        out = prolog_to_clausal("add_one(X, Y) :- Y is X + 1.\n")
        assert "eval_(X + 1, Y)" in out, out
        assert ":=" not in out, out
