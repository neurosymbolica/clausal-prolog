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

class TestKitWitness:

    def test_kit_query_combinators_refuses_under_strict(self):
        src = KIT_QUERY_COMBINATORS.read_text()
        msgs = _refusals(src)
        assert msgs, "kit witness must now refuse"
        lambda_msgs = [m for m in msgs if "`<-` lambda in term position" in m]
        member_msgs = [m for m in msgs
                       if "negated membership" in m]
        # :165 and :224 are the include/3 sites named in the decision, plus a
        # third `<-` lambda the sweep found in the same file.
        assert len(lambda_msgs) == 3, msgs
        assert len(member_msgs) == 2, msgs

    def test_kit_witness_names_the_construct(self):
        msgs = _refusals(KIT_QUERY_COMBINATORS.read_text())
        assert any("include" in m or "D < -" in m for m in msgs), msgs
