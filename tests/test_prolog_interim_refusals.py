"""Interim refusals from the 2026-09-03 operator decision.

Two shapes that used to translate SILENTLY WRONG now refuse (untranslatable
→ strict raises). See docs/iso-export-pilot-2026-09.md, "Operator decision —
2026-09-03 (dict-membership fail-open, class P census)", in the
clausify-executor-train repo.

1. Negated membership (`X not in XS` / `not (X in XS)`) whose RHS is not
   PROVABLY a list. Over an exported dict (an attribute-list) the old
   `\\+ member(X, Dict)` emission is always-true — silently wrong.
2. A `<-` lambda reaching TERM position, which used to emit inert operator
   soup that never runs.
"""

import pathlib

import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    UntranslatableConstructError,
)

KIT_QUERY_COMBINATORS = pathlib.Path(
    "/workspace/clausify-executor-train/kit/query_combinators.clausal"
)


def _refusals(src):
    """Return the refusal messages for *src*, or [] when it translates."""
    try:
        clausal_source_to_prolog(src, strict=True)
        return []
    except UntranslatableConstructError as exc:
        return list(exc.constructs)


# ── Refusal 1: negated membership over a non-provably-list RHS ──────────

class TestNegatedMembershipRefusal:

    @pytest.mark.parametrize("src", [
        # bare parameter — the dict/profile case the decision is about
        "p(K, PROFILE) <- (K not in PROFILE)\n",
        # the other spelling of the same thing
        "p(K, PROFILE) <- (not (K in PROFILE))\n",
        # a call result is not provably a list
        "p(K) <- (K not in profile_of(x))\n",
        # a dict literal most certainly is not
        "p(K) <- (K not in {a: 1})\n",
    ])
    def test_refuses_non_provably_list_rhs(self, src):
        msgs = _refusals(src)
        assert len(msgs) == 1, msgs
        assert "negated membership over a value not provably a list" in msgs[0]

    def test_message_names_the_remedy(self):
        """The refusal must be ACTIONABLE, not merely a rejection."""
        msg = _refusals("p(K, PROFILE) <- (K not in PROFILE)\n")[0]
        assert "profile_has" in msg          # the accessor respelling
        assert "2026-09-03" in msg           # where the decision is written
        assert "PROFILE" in msg              # which RHS is at fault

    @pytest.mark.parametrize("src, expected", [
        # (a) a list display
        ("p(K) <- (K not in [a, b, c])\n", "\\+ member(K, [a, b, c])"),
        # (b) a variable bound clause-locally from a list literal
        ("p(K) <- (XS is [a, b], K not in XS)\n", "\\+ member(K, Xs)"),
        # (b) a variable bound clause-locally by a list-producing goal
        ("p(K) <- (findall(X, q(X), XS), K not in XS)\n", "\\+ member(K, Xs)"),
        ("p(K, L) <- (msort(L, XS), K not in XS)\n", "\\+ member(K, Xs)"),
        ("p(K, L) <- (sort(L, XS), K not in XS)\n", "\\+ member(K, Xs)"),
        # sort/4: `@<` is not Python-parseable, so Clausal spells the order
        # argument as a string.
        ('p(K, L) <- (sort(0, "@<", L, XS), K not in XS)\n', "\\+ member(K, Xs)"),
        ("p(K, G) <- (setof(X, q(X), XS), K not in XS)\n", "\\+ member(K, Xs)"),
        ("p(K, G) <- (bagof(X, q(X), XS), K not in XS)\n", "\\+ member(K, Xs)"),
    ])
    def test_provably_list_rhs_still_translates(self, src, expected):
        out = clausal_source_to_prolog(src, strict=True)
        assert expected in out

    def test_partial_list_display_refuses(self):
        """`[H|T]` with an unbound tail is a PARTIAL list.

        `\\+ member/2` over one is exactly as unsound as over a dict, so a
        list display does not automatically qualify as provably-list.
        """
        assert _refusals("p(K, T) <- (K not in [a, *T])\n")

    def test_splat_tail_that_is_itself_provable_translates(self):
        src = "p(K) <- (T is [b, c], K not in [a, *T])\n"
        assert _refusals(src) == []

    def test_analysis_is_clause_local_not_cross_clause(self):
        """A list binding in a DIFFERENT clause must not license the site."""
        src = (
            "other(XS) <- (XS is [a, b])\n"
            "p(K, XS) <- (K not in XS)\n"
        )
        msgs = _refusals(src)
        assert len(msgs) == 1, msgs
        assert "negated membership" in msgs[0]



class TestAllBindingsMustBeProvable:
    """Control-flow blindness must not be exploitable via ALIASING.

    The walk behind the provably-list analysis cannot tell a disjunct from a
    conjunct. An earlier version qualified a name on ANY list binding, which
    reopened the exact hazard this task closes: a name bound to a dict in one
    disjunct and a list in another was treated as provably-list everywhere.
    Qualification now requires EVERY binding of the name to be list-producing.
    """

    def test_mixed_disjunct_bindings_refuse(self):
        r"""Reviewer's exact reproduction — must raise under strict.

        `V` may be the dict `D` at the membership site, so `\+ member(K, V)`
        is silently always true.
        """
        src = "p(K, D) <- ((V is D) or (V is [a, b]), K not in V)\n"
        msgs = _refusals(src)
        assert len(msgs) == 1, msgs
        assert "negated membership over a value not provably a list" in msgs[0]

    def test_both_disjuncts_binding_list_literals_still_qualifies(self):
        """The widening that IS safe: every branch produces a list."""
        src = "p(K) <- ((V is [a]) or (V is [b]), K not in V)\n"
        assert _refusals(src) == []
        assert "\\+ member(K, V)" in clausal_source_to_prolog(src, strict=True)

    def test_list_producing_goal_plus_dict_alias_refuses(self):
        """One good binding (findall) does not rescue a bad one."""
        assert _refusals(
            "p(K, D) <- (findall(X, q(X), V) or (V is D), K not in V)\n")

    def test_name_with_no_binding_refuses(self):
        """A bare clause parameter is bound by the CALLER, not provable here."""
        assert _refusals("p(K, V) <- (K not in V)\n")

    def test_cyclic_binding_fails_closed(self):
        """`V is [a, *V]` must not qualify itself — least fixpoint, not greatest."""
        assert _refusals("p(K) <- (V is [a, *V], K not in V)\n")


class TestMembershipPolarityAsymmetry:
    """The operator deferred the POSITIVE polarity; the asymmetry is load-bearing.

    Positive `member/2` over a dict fails loudly (an absent derivation);
    negated `\\+ member/2` over a dict SUCCEEDS silently. Only the latter
    refuses in the interim.
    """

    SUSPECT_RHS = "PROFILE"

    def test_positive_membership_over_same_rhs_still_translates(self):
        out = clausal_source_to_prolog(
            f"p(K, {self.SUSPECT_RHS}) <- (K in {self.SUSPECT_RHS})\n",
            strict=True,
        )
        assert "member(K, Profile)" in out

    def test_negated_membership_over_same_rhs_refuses(self):
        assert _refusals(
            f"p(K, {self.SUSPECT_RHS}) <- (K not in {self.SUSPECT_RHS})\n"
        )

    def test_both_polarities_one_clause_refuses_only_the_negated_one(self):
        """The sharpest form: identical RHS, one clause, opposite verdicts."""
        src = (
            "p(K, PROFILE) <- (\n"
            "    K in PROFILE,\n"
            "    K not in PROFILE\n"
            ")\n"
        )
        msgs = _refusals(src)
        assert len(msgs) == 1, msgs
        assert "negated membership" in msgs[0]


# ── Refusal 2: `<-` lambda in term position ────────────────────────────

class TestArrowLambdaInTermPositionRefusal:

    def test_refuses_lambda_passed_to_include(self):
        src = "p(A, B) <- (include((D <- (D is delta(_, S, T))), A, B))\n"
        msgs = _refusals(src)
        assert len(msgs) == 1, msgs
        assert "`<-` lambda in term position" in msgs[0]

    def test_message_names_the_construct_and_the_design_note(self):
        msg = _refusals(
            "p(A, B) <- (include((D <- (D is x)), A, B))\n")[0]
        assert "`<-` lambda in term position" in msg
        assert "class-M" in msg
        assert "2026-09-03" in msg

    def test_tuple_param_lambda_refuses(self):
        assert _refusals(
            "p(A, B) <- (maplist(((E, K) <- (E is [K, _])), A, B))\n")


class TestArrowSpacingDiscrimination:
    """`<-` and `< -` parse to an IDENTICAL AST.

    Compare(Lt, UnaryOp(USub, ...)) either way — `ast.unparse` even renders
    both as `D < -1`. Only the SOURCE SPACING separates the lambda arrow from
    a genuine comparison against a negated term, so the refusal must consult
    the original spelling. These two tests are the whole point of Refusal 2:
    if the rule were AST-based, one of them would have to fail.
    """

    def test_tight_arrow_is_a_lambda_and_refuses(self):
        msgs = _refusals("p(A, B) <- (g(D <-1, A, B))\n")
        assert len(msgs) == 1, msgs
        assert "`<-` lambda in term position" in msgs[0]

    def test_spaced_arrow_is_a_comparison_and_is_untouched(self):
        out = clausal_source_to_prolog("p(A, B) <- (g(D < -1, A, B))\n",
                                       strict=True)
        assert "-1" in out and "A, B" in out

    def test_spaced_arrow_against_a_variable_is_untouched(self):
        out = clausal_source_to_prolog("p(A, B, X) <- (g(D < -X, A, B))\n",
                                       strict=True)
        assert "- X" in out or "-X" in out

    def test_plain_less_than_is_untouched(self):
        out = clausal_source_to_prolog("p(A, B) <- (g(D < 1, A, B))\n",
                                       strict=True)
        assert "< 1" in out

    def test_the_two_spellings_have_the_same_ast(self):
        """Guards the premise: prove the AST cannot tell these apart."""
        import ast
        tight = ast.parse("g(D <-1)")
        spaced = ast.parse("g(D < -1)")
        assert ast.dump(tight) == ast.dump(spaced)
        # ...and yet the translator gives them opposite verdicts.
        assert _refusals("p(A) <- (g(D <-1, A))\n")
        assert _refusals("p(A) <- (g(D < -1, A))\n") == []


# ── The kit witness: the RED fixture named by the decision ─────────────

# The witness is SYNTHETIC (tests/fixtures/lambda_in_term_position_witness.clausal):
# three `<-` lambdas in term position written for this test. Its predecessor was
# a verbatim 706-line snapshot of a closed-side kit file (c7f29564); closed-side
# source does not enter this tree, so it was replaced (operator ruling
# 2026-09-08). The shapes are the same three the class docstring names.
KIT_QUERY_COMBINATORS_PRE_MIGRATION = (
    pathlib.Path(__file__).parent / "fixtures"
    / "lambda_in_term_position_witness.clausal"
)


class TestKitWitness:
    """The live kit file this class originally witnessed against has since
    been migrated to strict-clean (clausify-executor-train commit
    76afe6d, "kit: hand-lift the last 10 class-(c) `<-` closures"). Two
    tests, two different responses to that drift:

    * ``test_kit_query_combinators_is_strict_clean`` (previously
      ``test_kit_query_combinators_refuses_under_strict`` — renamed
      because asserting refusal under a name that now means "asserts no
      refusal" would be self-contradictory) re-points at the LIVE file
      and pins its NEW status: strict-clean. This is a real, current
      cross-repo fact worth pinning — if kit's query_combinators.clausal
      ever regresses to refusing again, this goes red.
    * ``test_kit_witness_names_the_construct`` needs an actual refusal to
      assert the construct-naming shape against, which the live file no
      longer has. Re-pointed at a FROZEN in-repo fixture (a vendored
      snapshot of the pre-migration source, see the fixture file's own
      header) instead of being deleted — this also starts fixing the
      cross-repo-witness fragility itself: a test that reads a live file
      from a sibling repo has its pass/fail depend on that repo's
      current state, not on anything this translator controls.
    """

    def test_kit_query_combinators_is_strict_clean(self):
        src = KIT_QUERY_COMBINATORS.read_text()
        assert _refusals(src) == [], (
            "kit/query_combinators.clausal is expected to be "
            "strict-translate clean as of clausify-executor-train "
            "commit 76afe6d -- if this fails, either the live file "
            "regressed or the translator broke something that used "
            "to translate"
        )

    def test_kit_witness_names_the_construct(self):
        """Frozen fixture, not the live file (see class docstring) — pins
        the `<-`-lambda-in-term-position refusal MESSAGE SHAPE against a
        source snapshot that is guaranteed to still contain it."""
        msgs = _refusals(KIT_QUERY_COMBINATORS_PRE_MIGRATION.read_text())
        assert len(msgs) == 3, msgs
        assert all("`<-` lambda in term position" in m for m in msgs), msgs
        assert any("D < -" in m for m in msgs), msgs
