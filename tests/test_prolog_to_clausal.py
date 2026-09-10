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
        # nv — THE FLIP (spec §7): a Prolog ``PString`` emits a DOUBLE-quoted
        # clausal literal, which means a string under the
        # ``-double_quotes(chars)`` header the module emitter writes.  (A
        # quoted ``PAtom`` is what still emits ``'...'``.)
        assert emit_clausal_term(PString("hello")) == '"hello"'

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
        assert result == "foo_bar(X)"

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
        assert result == "edge(1, 2),"

    def test_rule(self):
        # nv
        result = emit_clausal_item(PClause(
            PCompound("reach", (PVar("X"), PVar("Y"))),
            PCompound("edge", (PVar("X"), PVar("Y"))),
        ))
        assert result == "reach(X, Y) <- (edge(X, Y))"

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
        assert result == "reach(X, Y) <- (edge(X, Z), reach(Z, Y))"

    def test_dcg_rule(self):
        # nv
        result = emit_clausal_item(PDCGRule(
            PAtom("greeting"),
            PList((PString("hello"), PString("world")), None),
        ))
        assert result == 'greeting() >> (["hello", "world"])'

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
        assert result == "-dynamic(color/2)"


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
        assert "edge(1, 2)," in result
        assert "edge(2, 3)," in result
        assert "reach(X, Y) <- (edge(X, Y))" in result
        assert "reach(X, Y) <- (edge(X, Z), reach(Z, Y))" in result

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
        assert "-module(test, [foo/2, bar/1])" in result

    def test_dynamic_directive(self):
        # nv
        src = ":- dynamic(color/2)."
        result = prolog_to_clausal(src)
        assert "-dynamic(color/2)" in result

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
    def test_snake_case_crosses_unchanged(self):
        # nv
        src = "all_different([1, 2, 3]).\nfoo_bar(1)."
        result = prolog_to_clausal(src)
        assert "all_different" in result
        assert "foo_bar(1)" in result
        assert "FooBar" not in result

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
        assert "edge(1, 2)," in result

    def test_iso_default(self):
        # nv
        src = "edge(1, 2)."
        result = prolog_to_clausal(src, dialect=Dialect.iso())
        assert "edge(1, 2)," in result


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


class TestCatchArity:
    """Prolog catch/3 reverse-maps by ARITY: the 3-arg ISO form is clausal
    catch/3, while catch_error stays reserved for the 2-arg form.  Name-only
    mapping produced catch_error/3, which the compiler treats as an ordinary
    call to an undefined predicate, not as exception handling (roborev job
    271 on ae703f04)."""

    def test_prolog_catch_3_maps_to_clausal_catch_3(self):
        out = prolog_to_clausal(
            "p(X) :- catch((X == a, fail), _, true).\n")
        assert "catch(" in out, out
        assert "catch_error" not in out, out

    def test_two_arg_catch_still_maps_to_catch_error(self):
        # The 2-arg form is what clausal catch_error/2 forward-translates to;
        # the reverse leg must keep round-tripping it.
        out = prolog_to_clausal("p(G, E) :- catch(G, E).\n")
        assert "catch_error(G, E)" in out, out


class TestPredicateCollidingAtomIsNotDeclaredPrivate:
    """A bare Prolog atom whose spelling is ALSO a predicate in the same module
    must not be declared ``-private``.

    In Clausal one module-level name is either the atom or the predicate, never
    both, so ``-private([subtract])`` shadows ``subtract/3`` and every call to
    it stops being a goal ("terms_to_goalop: goal shape not yet supported").
    A str literal denotes the SAME atom (R2) and carries no declaration, so it
    is the faithful spelling -- the escape hatch F025 already uses for names
    that cannot be bare.

    Reachable since a Clausal str literal became an atom: a test file now
    emits ``test(subtract) :- subtract(...)``.
    """

    def test_colliding_atom_becomes_a_str_literal(self):
        out = prolog_to_clausal(
            "test(subtract) :-\n    subtract([1,2],[2],[1]).\n")
        assert "-private([subtract])" not in out, out
        assert "test('subtract')" in out, out

    def test_non_colliding_atom_still_declared_private(self):
        # The gate must say YES too: an atom that shadows nothing is
        # untouched, so this is not a blanket disabling of -private.
        out = prolog_to_clausal("test(red) :-\n    colour(red).\n")
        assert "-private([red])" in out, out
        assert "test(red)" in out, out

    def test_functor_in_a_nested_argument_also_counts(self):
        # The sweep is every position, not just goal position.
        out = prolog_to_clausal("p(foo) :-\n    q(r(foo(1))).\n")
        assert "-private([foo])" not in out, out
        assert "p('foo')" in out, out
