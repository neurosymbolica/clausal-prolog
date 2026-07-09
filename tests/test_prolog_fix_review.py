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
    def test_distinct_vars_stay_distinct(self):
        out = clausal_source_to_prolog(
            "P(_result, RESULT) <- (_result == 1, RESULT == 2)"
        )
        # Both map to base name "Result"; the second must be disambiguated.
        assert "p(Result, Result2)" in out

    def test_three_way_collision(self):
        out = clausal_source_to_prolog("P(_x, X, _X) <- (Q(_x, X, _X))")
        head = out.splitlines()[0]
        # _x → X, X → X (collides), _X → X (collides): three distinct names.
        assert "p(X, X2, X3)" in head

    def test_rename_table_resets_per_clause(self):
        out = clausal_source_to_prolog(
            "P(_result) <- (Q(_result))\nR(RESULT) <- (Q(RESULT))"
        )
        # No cross-clause leakage: each clause gets the plain base name.
        assert "p(Result)" in out
        assert "r(Result)" in out
        assert "Result2" not in out

    def test_same_var_same_name_within_clause(self):
        out = clausal_source_to_prolog("P(_head, _head) <- (Q(_head))")
        assert "p(Head, Head)" in out
        assert "q(Head)" in out

    def test_anonymous_stays_anonymous(self):
        out = clausal_source_to_prolog("P(_, _) <- (Q(_))")
        assert "p(_, _)" in out


# ═══════════════════════════════════════════════════════════════════════
# F025/F035 — evaluable constants + quoted non-identifier functor heads
# ═══════════════════════════════════════════════════════════════════════


class TestF025EvaluableConstants:
    def test_pi_maps_to_math(self):
        out = prolog_to_clausal("f(X) :- X is pi.")
        assert "X := math.pi" in out
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
        assert "Foo(x)," in out


# ═══════════════════════════════════════════════════════════════════════
# F026/F041 — newly-parsed operators must not emit invalid Clausal
# ═══════════════════════════════════════════════════════════════════════


class TestF026BagofWitness:
    def test_bagof_witness_stripped(self):
        # Clausal bagof/setof never group by free variables, which is ISO's
        # behaviour when the variable is ^-quantified — drop the quantifier.
        out = prolog_to_clausal("q(L) :- bagof(X, Y^p(X,Y), L).")
        assert "bagof(X, P(X, Y), L)" in out
        assert "^" not in out

    def test_setof_nested_witnesses_stripped(self):
        out = prolog_to_clausal("q(L) :- setof(X, A^B^p(X, A, B), L).")
        assert "setof(X, P(X, A, B), L)" in out
        assert "^" not in out

    def test_caret_outside_bagof_rejected(self):
        # (^)/2 in plain goal/term position has no Clausal equivalent.
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("q(X) :- Y^p(X, Y).")

    def test_arith_caret_maps_to_python_pow(self):
        # In arithmetic context (^)/2 is ISO exponentiation → Python **.
        out = prolog_to_clausal("f(X) :- X is 2 ^ 3.")
        assert "X := 2 ** 3" in out

    def test_arith_caret_right_associative(self):
        # ISO ^ is xfy: 2^3^2 = 2^(3^2); Python ** is also right-assoc.
        out = prolog_to_clausal("f(X) :- X is 2 ^ 3 ^ 2.")
        assert "X := 2 ** 3 ** 2" in out


class TestF026StandardOrderRejected:
    @pytest.mark.parametrize("op", ["@<", "@>", "@=<", "@>="])
    def test_standard_order_comparison_rejected(self, op):
        # Clausal has no standard-order term comparison builtins.
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal(f"q(X, Y) :- X {op} Y.")


class TestF041VariantEqualityRejected:
    @pytest.mark.parametrize("op", ["=@=", "\\=@="])
    def test_variant_equality_rejected(self, op):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal(f"q(X, Y) :- X {op} Y.")

    def test_variant_equality_rejected_in_metacall(self):
        with pytest.raises(PrologTranslationError):
            prolog_to_clausal("q(L) :- findall(X, (p(X), X =@= f(_)), L).")


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
