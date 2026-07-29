"""Arity conflicts between a functor's declaration and its clause heads.

``todo/functor-field-name-mismatch-diagnostic.md`` — the reported
``__init__() got an unexpected keyword argument 'arg_1'`` failure.

Two independent defects are covered here:

**Compile time.**  A functor whose ``-module``/``-private`` declaration (or
whose first clause) fixes arity N, and which is then given a clause head of
arity M > N, used to compile into a keyword construction with ``arg_N``
placeholder names for the surplus positions.  The class had already been minted
with N fields, so the module blew up at load with a bare, unattributable
``TypeError``.  A functor name has exactly one arity in Clausal, so this is now
a ``SyntaxError`` at rewrite time naming both sites.

**Run time.**  ``PredicateMeta.__call__`` silently *discarded* positional
arguments past ``len(_fields)``, so ``some_atom(A, B)`` on a zero-arity class
returned a bogus, wrong term with no error at all.  It now raises the same
attributable ``ClausalTermConstructionError`` the keyword path raises.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.predicate import (
    ClausalTermConstructionError,
    PredicateMeta,
    make_atom,
    make_predicate,
)


# ── Run time: positional overflow ──────────────────────────────────────────


class TestPositionalOverflowRaises:
    """Positional arguments past ``len(_fields)`` are an error, not silence."""

    def test_zero_arity_class_called_with_positionals_raises(self):
        cls = PredicateMeta("fac_zero", (), {"_fields": ()})
        with pytest.raises(ClausalTermConstructionError):
            cls("a", "b")

    def test_overflow_names_functor_and_both_arities(self):
        cls = make_predicate("fac_pair", ["left", "right"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(1, 2, 3)
        msg = str(exc_info.value)
        assert "fac_pair/2" in msg
        assert "3 positional" in msg
        assert "(left, right)" in msg

    def test_overflow_carries_the_same_structured_attributes(self):
        cls = make_predicate("fac_attrs", ["only"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(1, 2)
        err = exc_info.value
        assert err.functor == "fac_attrs"
        assert err.arity == 1
        assert err.registered_fields == ("only",)
        # Supplied fields are reported the way the keyword path reports them:
        # registered names for the positions that fit, arg_N for the surplus.
        assert err.supplied_fields == ("only", "arg_1")
        assert err.registered_at is not None
        assert err.constructed_at is not None

    def test_overflow_reports_both_source_locations(self):
        cls = make_predicate("fac_where", ["only"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(1, 2)
        msg = str(exc_info.value)
        assert "registered by:" in msg
        assert "constructed at:" in msg
        assert os.path.basename(__file__) in msg

    def test_overflow_on_a_zero_arity_class_names_the_shadowing_cause(self):
        """An atom called with arguments is Phenomenon A — say so."""
        atom = make_atom("fac_bare_atom")
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            atom(1, 2)
        msg = str(exc_info.value)
        assert "fac_bare_atom/0" in msg
        assert "0-arity atom" in msg

    def test_exact_arity_still_constructs(self):
        cls = make_predicate("fac_ok", ["left", "right"])
        term = cls(1, 2)
        assert term.left == 1 and term.right == 2

    def test_partial_positional_still_fills_with_vars(self):
        from clausal.logic.variables import is_var

        cls = make_predicate("fac_partial", ["left", "right"])
        term = cls(1)
        assert term.left == 1
        assert is_var(term.right)

    def test_mixed_positional_and_keyword_within_arity_still_constructs(self):
        cls = make_predicate("fac_mixed", ["left", "right"])
        term = cls(1, right=2)
        assert term.left == 1 and term.right == 2

    def test_zero_arity_no_args_still_returns_the_class_itself(self):
        atom = make_atom("fac_identity")
        assert atom() is atom


# ── Compile time: declaration/clause arity conflict ────────────────────────


def _write(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return str(path)


def _load(tmp_path, name, text):
    return _load_module(f"tests_fac_{name}", _write(tmp_path, name, text))


class TestDeclarationClauseArityConflict:
    """``-module(m, [f(A)])`` + ``f(1, 2),`` is a load-time error."""

    def test_fact_with_more_args_than_the_module_declaration(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "decl_fact", """
                -module(m, [
                    f(A)
                ])

                f(1, 2),
            """)
        msg = str(exc_info.value)
        assert "f/2" in msg
        assert "f/1" in msg
        # Both ends located, in the file that actually contains them — a load
        # failure surfaces through the *importing* file, so the message has to
        # name its own.
        assert "decl_fact.clausal:2" in msg   # the f(A) export entry
        assert "decl_fact.clausal:5" in msg   # the offending clause

    def test_rule_head_with_more_args_than_the_declaration(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "decl_rule", """
                -module(m, [
                    f(A),
                    g(B)
                ])

                g(1),

                f(X, Y) <- (
                    g(X)
                )
            """)
        msg = str(exc_info.value)
        assert "f/2" in msg
        assert "f/1" in msg

    def test_second_clause_with_a_different_arity(self, tmp_path):
        """No declaration at all — the first clause fixes the arity."""
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "clause_clause", """
                f(1),
                f(1, 2),
            """)
        msg = str(exc_info.value)
        assert "f/2" in msg
        assert "f/1" in msg

    def test_private_declaration_conflicts_too(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "priv", """
                -private([h(A, B)])

                h(1, 2, 3),
            """)
        assert "h/3" in str(exc_info.value)

    def test_error_names_the_offending_source_lines(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "snippet", """
                -module(m, [
                    threshold_bps(BPS)
                ])

                threshold_bps(2500, cite(art_52)),
            """)
        msg = str(exc_info.value)
        assert "threshold_bps" in msg
        # the offending clause text is quoted so a repair loop can locate it
        assert "threshold_bps(2500" in msg

    def test_fewer_args_than_declared_is_still_allowed(self, tmp_path):
        """A partial head binds the leading fields; the rest become Vars."""
        mod = _load(tmp_path, "under", """
            -module(m, [
                f(A, B)
            ])

            f(1),
        """)
        assert mod.f._fields == ("A", "B")

    def test_matching_arity_is_unaffected(self, tmp_path):
        mod = _load(tmp_path, "match", """
            -module(m, [
                f(A, B)
            ])

            f(1, 2),
        """)
        assert mod.f._fields == ("A", "B")

    def test_anonymous_argument_does_not_produce_a_placeholder_mismatch(
        self, tmp_path
    ):
        """The ``arg_{i}`` fallback in ``_derive_field_names`` was blamed for
        this bug (``base = arg.id.lstrip("_").lower() or f"arg_{i}"``).  It is
        not the cause: ``_`` is excluded from ``_is_logic_var_name`` before it
        ever reaches that ``or``, and a ``_`` in a *body* goal is emitted
        positionally, not as a keyword.  Both shapes load."""
        mod = _load(tmp_path, "anon", """
            -module(m, [
                verdict(STATUS, CITATIONS),
                status(S),
                ok
            ])

            verdict(ok, []),

            status(S) <- (
                verdict(S, _)
            )
        """)
        assert mod.verdict._fields == ("STATUS", "CITATIONS")

    def test_anonymous_argument_in_a_head_takes_the_declared_name(
        self, tmp_path
    ):
        """A ``_`` in the *head* does derive ``arg_i`` — but the declared
        signature overlays it by position, so nothing escapes."""
        mod = _load(tmp_path, "anonhead", """
            -module(m, [
                pair(LEFT, RIGHT)
            ])

            pair(1, _),
        """)
        assert mod.pair._fields == ("LEFT", "RIGHT")

    def test_unknown_explicit_keyword_is_reported_at_compile_time(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "kwtypo", """
                -module(m, [
                    f(A, B)
                ])

                f(A=1, C=2),
            """)
        assert "C" in str(exc_info.value)
