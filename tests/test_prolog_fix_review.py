"""Regression tests for the 2026-07-09 review of the A11 Prolog-tools fixes.

Covers the secondary bullets dropped during the original fix wave:

- F022: clausal→Prolog variable renaming must be injective per clause.
- F025/F035: ISO evaluable constants map to math.*; quoted non-identifier
  functor heads are rejected.
- F026/F041: newly-parsed operators (^, @<, =@=, ...) must not silently
  emit invalid Clausal.
- F034: _quote_atom escapes control characters (ISO 6.4.2).
- F036: Cut() in Clausal source is rejected on export.
- F033: qualified goals resolve builtins like the unqualified path.
"""

from __future__ import annotations

import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    _quote_atom,
    emit_term,
)
from clausal.tools.prolog_to_clausal import (
    prolog_to_clausal,
    PrologTranslationError,
)
from clausal.tools.prolog_ast import PAtom
from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_parser import parse


# ═══════════════════════════════════════════════════════════════════════
# F022 — clausal → Prolog variable renaming must be injective per clause
# ═══════════════════════════════════════════════════════════════════════


class TestF022VarRenameInjective:
    """F022's property outlived F022's mechanism.

    The defect: ``clausal_var_to_prolog`` was non-injective (``_result`` and
    ``RESULT`` both -> ``Result``), so two variables in one clause merged into
    one and the clause changed meaning. The fix was a per-clause rename table
    that numbered the second arrival — ``Result2``.

    Since 2026-09-10 names cross the boundary unchanged, so the mapping is
    injective by construction and the table is gone. Every assertion below
    still asks the same question — do distinct variables stay distinct? — and
    the answers changed from disambiguated spellings to the source spellings.
    They are kept, rather than deleted as "testing the identity function",
    because injectivity is the property F022 was about and a future
    reintroduced rename is exactly what they should catch.

    Distinctness is asserted by COUNTING as well as by spelling: an assertion
    that merely names the expected variables would pass on an emission that
    also invented a third.
    """

    @staticmethod
    def _vars(text):
        import re
        return re.findall(r"(?<![A-Za-z0-9_])(_[A-Za-z0-9_]*|[A-Z][A-Za-z0-9_]*)",
                          text)

    def test_distinct_vars_stay_distinct(self):
        out = clausal_source_to_prolog(
            "P(_result, RESULT) <- (_result == 1, RESULT == 2)"
        )
        # Was "p(Result, Result2)": both mapped to the base name "Result" and
        # the second had to be disambiguated. Neither is renamed now.
        assert "p(_result, RESULT)" in out
        assert len(set(self._vars(out))) == 2, out

    def test_three_way_collision(self):
        out = clausal_source_to_prolog("P(_x, X, _X) <- (Q(_x, X, _X))")
        head = out.splitlines()[0]
        # Was "p(X, X2, X3)": _x -> X, X -> X, _X -> X, three collisions
        # resolved by numbering. Three distinct names either way — the point
        # is that they are now the three the source wrote.
        assert "p(_x, X, _X)" in head
        assert len(set(self._vars(head))) == 3, head

    def test_no_translator_state_leaks_between_clauses(self):
        """Renamed from test_rename_table_resets_per_clause.

        The table it named is gone, but the property it protected is not: a
        variable name means nothing across top-level items, so the second
        clause must not see the first one's names. With no state left to leak
        this holds by construction — which is worth an assertion precisely
        because a future rename would have to reintroduce the state.
        """
        out = clausal_source_to_prolog(
            "P(_result) <- (Q(_result))\nR(RESULT) <- (Q(RESULT))"
        )
        assert "p(_result)" in out
        assert "r(RESULT)" in out
        assert "2" not in out

    def test_same_var_same_name_within_clause(self):
        """The converse of injectivity, and the reason it cannot be got by
        simply numbering every occurrence: one variable must stay ONE."""
        out = clausal_source_to_prolog("P(_head, _head) <- (Q(_head))")
        assert "p(_head, _head)" in out
        assert "q(_head)" in out

    def test_anonymous_stays_anonymous(self):
        out = clausal_source_to_prolog("P(_, _) <- (Q(_))")
        assert "p(_, _)" in out


# ═══════════════════════════════════════════════════════════════════════
# F025/F035 — evaluable constants + quoted non-identifier functor heads
# ═══════════════════════════════════════════════════════════════════════


class TestF025EvaluableConstants:
    def test_pi_maps_to_math(self):
        out = prolog_to_clausal("f(X) :- X is pi.")
        assert "eval_(math.pi, X)" in out
        assert "-import_module(math)" in out

    def test_e_inf_nan_map_to_math(self):
        out = prolog_to_clausal("f(A, B, C) :- A is e, B is inf, C is nan.")
        assert "math.e" in out
        assert "math.inf" in out
        assert "math.nan" in out

    def test_epsilon_maps_to_literal(self):
        # math has no epsilon; emit sys.float_info.epsilon as a literal.
        out = prolog_to_clausal("f(X) :- X is epsilon.")
        assert "2.220446049250313e-16" in out

    def test_constant_inside_expression(self):
        out = prolog_to_clausal("area(R, A) :- A is pi * R * R.")
        assert "math.pi * R * R" in out

    def test_plain_atom_in_arith_still_registered(self):
        # A non-evaluable atom in arithmetic goes through _emit_atom and is
        # declared via -private like every other data atom.
        out = prolog_to_clausal("f(X) :- X is foo.")
        assert "-private([foo])" in out


class TestF035QuotedFunctorHeads:
    def test_non_identifier_functor_head_rejected(self):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("'hello world'(x).")

    def test_non_identifier_functor_goal_rejected(self):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("p(X) :- 'has space'(X).")

    def test_plain_quoted_functor_still_accepted(self):
        # 'foo' names the same atom as foo — a plain identifier head is fine.
        out = prolog_to_clausal("'foo'(x).")
        assert "foo(x)," in out


# ═══════════════════════════════════════════════════════════════════════
# F026/F041 — newly-parsed operators must not emit invalid Clausal
# ═══════════════════════════════════════════════════════════════════════


class TestF026BagofWitness:
    def test_bagof_witness_kept(self):
        # Clausal bagof/setof group by free variables like ISO's (91ef2a77),
        # so the quantifier changes the answers and must cross (2026-09-29;
        # it was stripped before, which answered one list per Y).
        out = prolog_to_clausal("q(L) :- bagof(X, Y^p(X,Y), L).")
        assert "bagof(X, Y ^ (p(X, Y)), L)" in out

    def test_setof_nested_witnesses_kept(self):
        out = prolog_to_clausal("q(L) :- setof(X, A^B^p(X, A, B), L).")
        assert "setof(X, A ^ (B ^ (p(X, A, B))), L)" in out

    def test_caret_outside_bagof_rejected(self):
        # (^)/2 in plain goal/term position has no Clausal equivalent.
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("q(X) :- Y^p(X, Y).")

    def test_arith_caret_maps_to_python_pow(self):
        # In arithmetic context (^)/2 is ISO exponentiation, emitted as the
        # quoted ISO evaluable (Python ** answered 2 ^ -1 = 0.5, not ISO's
        # type_error; 2026-09-29).
        out = prolog_to_clausal("f(X) :- X is 2 ^ 3.")
        assert "eval_('^'(2, 3), X)" in out

    def test_arith_caret_right_associative(self):
        # ISO ^ is xfy: 2^3^2 = 2^(3^2); Python ** is also right-assoc.
        out = prolog_to_clausal("f(X) :- X is 2 ^ 3 ^ 2.")
        assert "eval_('^'(2, '^'(3, 2)), X)" in out


class TestF026StandardOrderTranslated:
    @pytest.mark.parametrize("op", ["@<", "@>", "@=<", "@>="])
    def test_standard_order_comparison_is_the_quoted_builtin(self, op):
        # The engine has the quoted ISO builtins (2026-09-09); the refusal
        # this replaced was stale (2026-09-29).
        out = prolog_to_clausal(f"q(X, Y) :- X {op} Y.")
        assert f"'{op}'(X, Y)" in out


class TestF041VariantEqualityRejected:
    # ``=@=`` / ``\\=@=`` are SWI operators.  The translator reads with
    # Scryer's operator table by default (ruling R11, 2026-09-28), where
    # neither is an operator, so the infix spelling is a syntax error, as it
    # is in Scryer; the designed rejection is still what an SWI-dialect read
    # reaches.
    @pytest.mark.parametrize("op", ["=@=", "\\=@="])
    def test_variant_equality_rejected(self, op):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal(f"q(X, Y) :- X {op} Y.", dialect=Dialect.swi())

    def test_variant_equality_rejected_in_metacall(self):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("q(L) :- findall(X, (p(X), X =@= f(_)), L).",
                              dialect=Dialect.swi())

    @pytest.mark.parametrize("op", ["=@=", "\\=@="])
    def test_not_an_operator_under_the_default_scryer_table(self, op):
        from clausal.tools.prolog_parser import ParseError
        with pytest.raises(ParseError):
            prolog_to_clausal(f"q(X, Y) :- X {op} Y.")


# ═══════════════════════════════════════════════════════════════════════
# F034 — _quote_atom must escape control characters (ISO 6.4.2)
# ═══════════════════════════════════════════════════════════════════════


class TestF034QuoteAtomEscapes:
    @pytest.mark.parametrize("raw,expected", [
        ("a\nb", r"'a\nb'"),
        ("a\tb", r"'a\tb'"),
        ("a\rb", r"'a\rb'"),
        ("a\bb", r"'a\bb'"),
        ("a\fb", r"'a\fb'"),
        ("a\vb", r"'a\vb'"),
        ("a\ab", r"'a\ab'"),
        ("a\0b", "'a\\0\\b'"),      # NUL: octal escape with closing backslash
        ("a\x01b", "'a\\x1\\b'"),   # other control chars: \xHH\ fallback
        ("a\x1bb", "'a\\x1b\\b'"),
        ("a\x7fb", "'a\\x7f\\b'"),
        ("it's", r"'it\'s'"),
        ("a\\b", r"'a\\b'"),
    ])
    def test_control_chars_escaped(self, raw, expected):
        assert _quote_atom(raw) == expected

    @pytest.mark.parametrize("raw", [
        "a\nb", "tab\there", "bell\a", "nul\0end", "\x01\x02", "mixed'\n\\",
    ])
    def test_roundtrips_through_own_tokenizer(self, raw):
        text = emit_term(PAtom(raw, quoted=True),
                         Dialect.swi().operator_table)
        module = parse(f"p({text}).", dialect=Dialect.swi())
        atom = module.items[0].head.args[0]
        assert isinstance(atom, PAtom)
        assert atom.name == raw

    def test_no_raw_control_chars_in_output(self):
        out = _quote_atom("a\n\t\r\x02b")
        assert all(ord(c) >= 32 for c in out)


# ═══════════════════════════════════════════════════════════════════════
# F036 — Cut() in Clausal source must be rejected on export
# ═══════════════════════════════════════════════════════════════════════


class TestF036CutRejected:
    def test_cut_call_in_body_rejected(self):
        # Clausal has no Cut predicate; exporting it as an undefined `cut`
        # goal (or worse, as !) would launder cut through cut-free Clausal.
        with pytest.raises(PrologTranslationError):
            clausal_source_to_prolog("P() <- (Q(), Cut())")

    def test_cut_call_in_metacall_rejected(self):
        with pytest.raises(PrologTranslationError):
            clausal_source_to_prolog("P(L) <- findall(X, (Q(X), Cut()), L)")

    def test_cut_snake_case_predicate_unaffected(self):
        # A user predicate that merely contains "cut" is fine.
        out = clausal_source_to_prolog("P(X) <- (CutList(X))")
        assert "cut_list(X)" in out


# ═══════════════════════════════════════════════════════════════════════
# F033 — qualified goals must resolve builtin names like the unqualified path
# ═══════════════════════════════════════════════════════════════════════


class TestF033QualifiedBuiltinNames:
    """`lists:member(X, L)` must emit `lists.in_(X, L)` (the documented
    mapping); `lists.member` does not exist on the Clausal side.  The
    unqualified path already special-cases `member/2` into infix `X in L`,
    so the reverse builtin map's `member` entry must point at `in_`.
    """

    def test_qualified_member_maps_to_in_(self):
        import ast

        out = prolog_to_clausal("r(X, L) :- lists:member(X, L).\n")
        ast.parse(out)
        assert "lists.in_(X, L)" in out
        assert "lists.member" not in out

    def test_qualified_memberchk_maps_to_in_check(self):
        out = prolog_to_clausal("r(X, L) :- lists:memberchk(X, L).\n")
        assert "lists.in_check(X, L)" in out

    def test_qualified_nth0_keeps_its_iso_name(self):
        # nth0/3 is a builtin under its own name since 2026-09-30, so the
        # reverse map no longer renames it to list_item/3.
        out = prolog_to_clausal("r(L, X) :- lists:nth0(0, L, X).\n")
        assert "lists.nth0(0, L, X)" in out

    def test_unqualified_member_still_infix_in(self):
        # Guard: the infix special case must survive the reverse-map change.
        out = prolog_to_clausal("r(X, L) :- member(X, L).\n")
        assert "X in L" in out

    def test_member_in_metacall_position_maps_to_in_(self):
        # member/2 inside findall goes through _emit_term, not the infix
        # special case; it must also land on a predicate that exists.
        out = prolog_to_clausal("r(L, Xs) :- findall(X, member(X, L), Xs).\n")
        assert "in_(X, L)" in out
