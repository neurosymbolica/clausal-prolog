"""Arity conflicts between a functor's declaration and its clause heads.

``todo/done/functor-field-name-mismatch-diagnostic.md`` — the reported
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
    make_predicate,
)
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal import Var


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
        atom = make_predicate("fac_bare_atom", [])
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
        atom = make_predicate("fac_identity", [])
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

    def test_fewer_args_than_declared_is_refused_too(self, tmp_path):
        """FLIPPED (todo/same-name-two-arities-silently-merge.md).

        This test used to pin the opposite: ``f(1),`` against a declared
        ``f(A, B)`` loaded as a partial head padded with a fresh Var.  That
        padding is the silent-merge bug — the padded clause matches
        ``f(1, ANYTHING)``, which the author never wrote — so under-supply
        is now the same load error over-supply has always been.
        """
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "under", """
                -module(m, [
                    f(A, B)
                ])

                f(1),
            """)
        msg = str(exc_info.value)
        assert "f/1" in msg
        assert "f/2" in msg

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


class TestShorterHeadAfterLongerIsRefused:
    """The other direction of the arity conflict, previously a silent merge.

    ``todo/same-name-two-arities-silently-merge.md``: ``foo(a, b),`` then
    ``foo(a),`` did not refuse — ``PredicateMeta.__call__`` filled the missing
    field with a fresh ``Var()``, so ``foo/1``'s fact was absorbed into
    ``foo/2`` as ``foo(a, _)``, a clause matching ``foo(a, ANYTHING)`` that
    the author never wrote.  A clause head is not a partial term: positional
    under-supply against the bound class is now the same load-time
    ``SyntaxError`` that positional over-supply has always been.

    Keyword heads are exempt — ``f(A=1)`` names exactly which fields it binds,
    so the unnamed remainder is explicit, not an accident.  ``-edcg_pred``
    heads are measured against the VISIBLE arity (the compiler-minted
    ``_edcg_*`` accumulator fields are never written by a source head).
    """

    def _refused(self, tmp_path, name, text):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, name, text)
        return str(exc_info.value)

    def test_the_todo_repro_is_refused(self, tmp_path):
        msg = self._refused(tmp_path, "merge_fact", """
            -private([a, b])

            foo(a, b),
            foo(a),
        """)
        assert "foo/1" in msg
        assert "foo/2" in msg

    def test_a_rule_head_is_refused_too(self, tmp_path):
        msg = self._refused(tmp_path, "merge_rule", """
            -private([a, b])

            foo(a, b),
            foo(X) <- (X == a),
        """)
        assert "foo/1" in msg
        assert "foo/2" in msg

    def test_a_bare_name_fact_is_refused(self, tmp_path):
        """``foo,`` after ``foo(a, b),`` padded to a match-EVERYTHING clause."""
        msg = self._refused(tmp_path, "merge_zero", """
            -private([a, b])

            foo(a, b),
            foo,
        """)
        assert "foo/0" in msg
        assert "foo/2" in msg

    def test_a_bare_name_rule_head_is_refused(self, tmp_path):
        msg = self._refused(tmp_path, "merge_zrule", """
            -private([a, b])

            foo(a, b),
            foo <- (a == a)
        """)
        assert "foo/0" in msg
        assert "foo/2" in msg

    def test_the_message_names_both_sites_and_the_padding(self, tmp_path):
        msg = self._refused(tmp_path, "merge_sites", """
            -private([a, b])

            foo(a, b),
            foo(a),
        """)
        assert "merge_sites.clausal:3" in msg      # the arity-fixing clause
        assert "merge_sites.clausal:4" in msg      # the offending head
        flat = " ".join(msg.split())
        assert "not a partial term" in flat
        assert "different name" in flat            # the rename remedy

    def test_the_remedy_spells_the_anything_position(self, tmp_path):
        """Padding meant "anything" exactly once in a while — say how to keep it."""
        msg = self._refused(tmp_path, "merge_anon", """
            -private([a, b])

            foo(a, b),
            foo(a),
        """)
        assert "`_`" in msg

    def test_an_explicit_anonymous_argument_still_loads(self, tmp_path):
        """``foo(a, _)`` is the spelled-out form of what padding fabricated."""
        mod = _load(tmp_path, "merge_spelled", """
            -private([a, b])

            foo(a, b),
            foo(a, _),
        """)
        assert len(mod.foo._clauses) == 2

    def test_a_keyword_subset_head_still_loads(self, tmp_path):
        """``f(A=1)`` binds by NAME; the unbound remainder is explicit."""
        mod = _load(tmp_path, "merge_kw", """
            -module(m, [
                f(A, B)
            ])

            f(A=1),
        """)
        assert mod.f._fields == ("A", "B")
        assert len(mod.f._clauses) == 1

    def test_edcg_visible_arity_head_still_loads(self, tmp_path):
        """``r(1),`` against a class minted at /3 is at the VISIBLE arity."""
        mod = _load(tmp_path, "merge_edcg", """
            -edcg_acc(cnt, V_, in_, out_, {out_ is in_ + V_})
            -edcg_pred(r, 1, [cnt])

            r(1),
        """)
        assert "r" in dir(mod)

    def test_dcg_nonterminals_are_untouched(self, tmp_path):
        """A DCG rule's written arity is below its class arity by design."""
        mod = _load(tmp_path, "merge_dcg", """
            greeting >> (["hello", "world"])
        """)
        assert "greeting" in dir(mod)


class TestTheRemedyPrintsTheTemplateEdit:
    """The message shows the edit, not just the arity disagreement.

    A Clausal declaration prefers the TEMPLATE form
    ``predicate_name(ARGUMENT_1, ...)`` over Prolog's ``name/N`` notation, which
    leaves the argument positions to be guessed.  The old message spoke pure
    arity: it said WHAT was wrong ("give them the same number of arguments")
    without showing the declaration to write, which is the whole content of the
    repair.  The clause head is in hand at the raise site — it is already
    printed on the ``clause:`` line — so the template is printed too.

    Argument-name synthesis is deliberately dumb (``ARG_N``, or the head's own
    variable names uppercased); the value is the template form itself.
    """

    def _msg(self, tmp_path, name, text):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, name, text)
        return str(exc_info.value)

    def _loads(self, tmp_path, name, text):
        """Assert *text* loads — used to check a printed remedy really works.

        A remedy that cannot be followed is worse than none: this file's
        sibling diagnostic has ``test_the_remedy_is_advice_that_works``
        precisely because its first wording sent readers into a second copy of
        the same error.
        """
        return _load(tmp_path, name, text)

    def test_private_declaration_atom_then_predicate_compiles(self, tmp_path):
        """P3-1 §3a/§1b/R2 INVERSION: ``-private([max_retries])`` declares
        ``max_retries`` as a 0-arity atom, and the fact ``max_retries(3),``
        then constructs it as an arity-1 predicate.  Pre-pivot, atoms
        reserved their arity-0 slot in ``_seen_functors`` and this was a
        compile-time ``SyntaxError`` with a remedy message.  Atoms no longer
        reserve a functor slot at all (Phenomenon A dies outright, §3a): the
        module compiles cleanly and the predicate simply wins, exactly as it
        does for an in-file bare-atom-then-predicate collision that never
        went through ``-private`` at all.
        """
        mod = self._loads(tmp_path, "remedy_priv", """
            -private([max_retries])

            max_retries(3),
        """)
        assert isinstance(mod.max_retries, PredicateMeta)
        assert mod.max_retries._fields == ("arg_0",)
        v = Var()
        results = [
            deref(v) for _ in call(
                "max_retries", v, module=mod.__dict__["$module"],
            )
        ]
        assert results == [3]

    def test_module_export_list_gets_the_module_wording(self, tmp_path):
        msg = self._msg(tmp_path, "remedy_mod", """
            -module(m, [
                f(A)
            ])

            f(1, 2),
        """)
        assert "remedy:" in msg
        # the declared name is reused for the position that fits; only the
        # surplus position falls back to a placeholder
        assert "`f(A, ARG_1)`" in msg
        assert "-module(" in msg
        assert "-private([...])" not in msg

    def test_an_earlier_clause_is_not_called_a_declaration(self, tmp_path):
        """No declaration exists — the remedy must not invent one to edit."""
        msg = self._msg(tmp_path, "remedy_clause", """
            f(1),
            f(1, 2),
        """)
        assert "remedy:" in msg
        assert "`f(ARG_0, ARG_1)`" in msg
        assert "an earlier clause" in msg
        assert "-private([...])" not in msg
        assert "-module(" not in msg

    def test_the_template_reuses_the_head_variable_names(self, tmp_path):
        """A head written with real variables gets them back, uppercased."""
        msg = self._msg(tmp_path, "remedy_vars", """
            -private([
                verdict(STATUS)
            ])

            verdict(S, CITES) <- (S == "ok"),
        """)
        assert "`verdict(STATUS, CITES)`" in msg

    @pytest.mark.parametrize("head, arity", [
        ("f(1)", 1),
        ("f(1, 2)", 2),
        ("f(1, 2, 3)", 3),
    ])
    def test_atom_then_predicate_of_any_arity_compiles(
        self, tmp_path, head, arity,
    ):
        """P3-1 §3a/§1b/R2 INVERSION of
        ``test_the_template_is_read_off_the_head_not_hard_coded``: an atom
        declared via ``-private([f])`` followed by a clause head of any
        arity no longer conflicts (Phenomenon A dies outright) — the
        predicate simply wins, at whatever arity its head carries."""
        mod = self._loads(tmp_path, f"remedy_ar{arity}", f"""
            -private([f])

            {head},
        """)
        assert isinstance(mod.f, PredicateMeta)
        assert len(mod.f._fields) == arity

    def test_the_predicate_wins_and_is_queryable(self, tmp_path):
        """P3-1 §3a/§1b/R2 INVERSION of
        ``test_the_alternative_edit_is_offered_too``: this used to be a
        second wording check on the same conflict message (an alternative
        remedy: drop the surplus argument instead of redeclaring). With the
        conflict gone, there is nothing left to offer a remedy for — the
        module simply compiles and the fact is queryable."""
        mod = self._loads(tmp_path, "remedy_alt", """
            -private([max_retries])

            max_retries(3),
        """)
        assert isinstance(mod.max_retries, PredicateMeta)
        v = Var()
        results = [
            deref(v) for _ in call(
                "max_retries", v, module=mod.__dict__["$module"],
            )
        ]
        assert results == [3]

    def test_the_drop_alternative_names_the_declared_shape(self, tmp_path):
        """A non-zero declaration: "drop the surplus" needs a target to hit.

        The 0-arity case says "if a bare value atom was intended", which is not
        advice when the declaration has fields — there the reader is told which
        shape to drop *to*, in the same template form.
        """
        msg = self._msg(tmp_path, "remedy_drop1", """
            -module(m, [
                f(A)
            ])

            f(1, 2),
        """)
        flat = " ".join(msg.split())
        assert "drop the surplus argument from every clause head of f" in flat
        assert "to match `f(A)`" in flat
        assert "bare value atom" not in flat        # the 0-arity wording
        # and the shape it names loads
        self._loads(tmp_path, "remedy_drop1_fixed", """
            -module(m, [
                f(A)
            ])

            f(1),
        """)

    def test_the_drop_alternative_pluralises_on_the_surplus(self, tmp_path):
        """Two surplus arguments, one declared field: "arguments", "f(A)"."""
        msg = self._msg(tmp_path, "remedy_drop2", """
            -private([
                f(A)
            ])

            f(1, 2, 3),
        """)
        flat = " ".join(msg.split())
        assert "drop the surplus arguments from every clause head of f" in flat
        assert "to match `f(A)`" in flat

    def test_a_directive_with_its_own_syntax_is_not_rewritten(self, tmp_path):
        """``-edcg_pred`` is written ``-edcg_pred(name, arity, [...])``.

        Its declaration site is NOT a template-form list, so the remedy must
        not invent ``-edcg_pred(q/2)``; it names the declaration and its arity
        and leaves the directive's own spelling alone.  With no accumulators
        the visible arity IS the whole arity, so the template half is a working
        edit here — which is checked, not assumed.
        """
        msg = self._msg(tmp_path, "remedy_edcg", """
            -edcg_pred(q, 1, [])

            q(1, 2),
        """)
        assert "remedy:" in msg
        assert "`q(ARG_0, ARG_1)`" in msg
        assert "-edcg_pred directive" in msg
        assert "-edcg_pred(q/2)" not in msg
        assert "-private([...])" not in msg
        self._loads(tmp_path, "remedy_edcg_fixed", """
            -edcg_pred(q, 2, [])

            q(1, 2),
        """)

    def test_minted_accumulator_fields_suppress_the_template(self, tmp_path):
        """``-edcg_pred(r, 1, [cnt])`` mints hidden ``_edcg_cnt_in/_out``.

        Two things make the template form wrong here, and neither is visible
        without knowing how the check is fed:

        * those positions are compiler-minted and a source head never spells
          them — they reach ``all_field_names`` only because the declared tuple
          is overlaid onto the head BY POSITION, so ``r(ARG_0, _edcg_cnt_in,
          _edcg_cnt_out, ARG_3)`` puts declared names on arguments the author
          wrote as ``2`` and ``3``;
        * ``-edcg_pred`` takes a VISIBLE arity, so "give the declaration the
          same arity" as a /4 template would push the hidden fields to
          positions 4 and 5 — not where the template showed them.

        So this case drops the template and speaks visible arity.  Both halves
        of what it prints are then applied, and both load.
        """
        msg = self._msg(tmp_path, "remedy_minted", """
            -edcg_acc(cnt, V_, in_, out_, {out_ is in_ + V_})
            -edcg_pred(r, 1, [cnt])

            r(1, 2, 3, 4),
        """)
        flat = " ".join(msg.split())
        assert "remedy:" in flat
        # the misleading template is gone, in either casing
        assert "`r(ARG_0, _edcg_cnt_in, _edcg_cnt_out, ARG_3)`" not in flat
        assert "_EDCG_CNT_IN" not in flat
        # visible arity, and the minted fields named as the reason
        assert "VISIBLE arity 1" in flat
        assert "2 compiler-minted accumulator fields" in flat
        assert "_edcg_cnt_in, _edcg_cnt_out" in flat
        assert "`r(ARG_0)`" in flat              # the visible-only shape
        assert "raise the visible arity" in flat
        assert "to 4." in flat

        # both printed edits are edits that work
        self._loads(tmp_path, "remedy_minted_head", """
            -edcg_acc(cnt, V_, in_, out_, {out_ is in_ + V_})
            -edcg_pred(r, 1, [cnt])

            r(1),
        """)
        self._loads(tmp_path, "remedy_minted_decl", """
            -edcg_acc(cnt, V_, in_, out_, {out_ is in_ + V_})
            -edcg_pred(r, 4, [cnt])

            r(1, 2, 3, 4),
        """)

    def test_a_name_that_is_already_a_logic_variable_is_not_mangled(
        self, tmp_path,
    ):
        """A leading-underscore field name is a logic variable already.

        ``f(1, _x=2)`` names its surplus field ``_x``; uppercasing it to ``_X``
        would print a declaration that mints a DIFFERENT field, so the paste
        would load and then quietly not match the head.  Names that already
        read as logic variables are passed through untouched — and the printed
        declaration is loaded here to prove it is the right one.
        """
        msg = self._msg(tmp_path, "remedy_underscore", """
            -module(m, [
                f(A)
            ])

            f(1, _x=2),
        """)
        assert "`f(A, _x)`" in msg
        assert "_X" not in msg
        mod = self._loads(tmp_path, "remedy_underscore_fixed", """
            -module(m, [
                f(A, _x)
            ])

            f(1, _x=2),
        """)
        assert mod.f._fields == ("A", "_x")


class TestTheUnknownFieldRaiseIsUntouched:
    """The sibling raise is out of scope; it must not grow a bogus remedy."""

    def test_no_remedy_block_on_the_field_name_raise(self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "kwremedy", """
                -module(m, [
                    f(A, B)
                ])

                f(A=1, C=2),
            """)
        msg = str(exc_info.value)
        assert "C" in msg                      # still the field-name message
        assert "remedy:" not in msg
