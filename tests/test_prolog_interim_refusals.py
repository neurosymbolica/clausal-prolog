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
        ("p(K) <- (XS is [a, b], K not in XS)\n", "\\+ member(K, XS)"),
        # (b) a variable bound clause-locally by a list-producing goal
        ("p(K) <- (findall(X, q(X), XS), K not in XS)\n", "\\+ member(K, XS)"),
        ("p(K, L) <- (msort(L, XS), K not in XS)\n", "\\+ member(K, XS)"),
        ("p(K, L) <- (sort(L, XS), K not in XS)\n", "\\+ member(K, XS)"),
        # sort/4: `@<` is not Python-parseable, so Clausal spells the order
        # argument as a string.
        ('p(K, L) <- (sort(0, "@<", L, XS), K not in XS)\n', "\\+ member(K, XS)"),
        ("p(K, G) <- (setof(X, q(X), XS), K not in XS)\n", "\\+ member(K, XS)"),
        ("p(K, G) <- (bagof(X, q(X), XS), K not in XS)\n", "\\+ member(K, XS)"),
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
        assert "member(K, PROFILE)" in out

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

class TestArrowLambdaInTermPositionLowering:
    """`<-` in term position LOWERS to library(lambda) (2026-09-14).

    It was refused outright from 2026-09-03 to 2026-09-14, and before that
    emitted as inert `</2` operator soup. The tests that pinned the refusal
    are rewritten here rather than deleted, so the file still says what
    happens at this site — the operator ruled the lowering after the two
    reference engines were measured to ship `library(lambda)`.
    """

    def test_lambda_passed_to_a_hof_lowers(self):
        out = clausal_source_to_prolog(
            "p(A, B) <- (maplist(((X, Y) <- (Y is x(X))), A, B))\n",
            strict=True)
        assert "\\ X ^ Y ^" in out, out
        assert "use_module(library(lambda), [(\\)/1," in out, out

    def test_single_parameter_lambda_lowers(self):
        out = clausal_source_to_prolog(
            "p(A) <- (maplist((X <- (X > 0)), A))\n", strict=True)
        assert "\\ X ^" in out, out

    def test_the_library_import_is_emitted_only_when_used(self):
        """A gate needs a test that it says NO: without a lambda the import
        must be absent, or its presence proves nothing."""
        out = clausal_source_to_prolog("p(A) <- (q(A))\n", strict=True)
        assert "library(lambda)" not in out, out

    def test_the_library_import_carries_an_EXPLICIT_list(self):
        """A listless `use_module(library(lambda))` is a real defect, not a
        tidier spelling, and this is the test that says so.

        A consumer deciding whether a predicate is already supplied cannot
        see inside a library, so a listless import reads as "this might
        supply anything". Measured 2026-09-14 while building the lowering: a
        single listless line silently removed the `library(dif)` import from
        a module calling `dif/2`, which then failed at CALL time with
        existence_error and never at consult time. Pinning the explicit list
        is what stops that coming back.
        """
        out = clausal_source_to_prolog(
            "p(A, B) <- (maplist(((X, Y) <- (Y is x(X))), A, B))\n",
            strict=True)
        assert "use_module(library(lambda), [" in out, out
        assert "use_module(library(lambda))." not in out, out
        # every arity both reference engines export, so a closure called at
        # any arity resolves
        for n in range(1, 9):
            assert f"(\\)/{n}" in out, out
        for n in range(3, 11):
            assert f"(^)/{n}" in out, out

    def test_a_read_only_capture_lowers(self):
        """A capture the lambda only READS behaves the same under
        copy-per-call and under sharing, so it is safe to lower."""
        out = clausal_source_to_prolog(
            "p(F, A, B) <- (maplist(((X, Y) <- (Y is f(X, F))), A, B))\n",
            strict=True)
        assert "\\ X ^ Y ^" in out, out

    def test_binding_a_capture_is_REFUSED_and_names_the_variable(self):
        """Output through a capture is an open design question (operator,
        2026-09-14), so it is refused rather than silently lowered: the
        interpreter SHARES a capture, `library(lambda)`'s `\\` copies, and
        the difference is a different answer with no error."""
        msgs = _refusals(
            "p(A, OUT) <- (maplist(((X, Y) <- (OUT is X, Y is X)), A, _Z))\n")
        assert len(msgs) == 1, msgs
        assert "binds a CAPTURED variable" in msgs[0], msgs
        assert "OUT" in msgs[0], msgs

    def test_a_lambda_LOCAL_variable_is_not_a_capture(self):
        """The discrimination the whole refusal rests on. `T` is bound inside
        the lambda but is NOT in the enclosing head, so it is lambda-local and
        must lower. A rule that refused every binding inside a lambda body
        would refuse nearly every closure in the corpus."""
        out = clausal_source_to_prolog(
            "p(A, B) <- (maplist(((X, Y) <- (T is X, Y is g(T))), A, B))\n",
            strict=True)
        assert "\\ X ^ Y ^" in out, out

    def test_non_variable_parameter_is_refused(self):
        msgs = _refusals("p(A, B) <- (maplist((f(Z) <- (Z is 1)), A, B))\n")
        assert len(msgs) == 1, msgs
        assert "non-variable parameter" in msgs[0], msgs


class TestArrowSpacingDiscrimination:
    """`<-` and `< -` parse to an IDENTICAL AST.

    Compare(Lt, UnaryOp(USub, ...)) either way — `ast.unparse` even renders
    both as `D < -1`. Only the SOURCE SPACING separates the lambda arrow from
    a genuine comparison against a negated term, so the refusal must consult
    the original spelling. These two tests are the whole point of Refusal 2:
    if the rule were AST-based, one of them would have to fail.
    """

    def test_tight_arrow_is_a_lambda_and_lowers(self):
        """A tight arrow is a lambda: it lowers, and `-1` does NOT survive as
        a negated number. `D` is the parameter and `1` the body."""
        out = clausal_source_to_prolog("p(A, B) <- (g(D <-1, A, B))\n",
                                       strict=True)
        # The real emission, not a guess at it: `D` occurs once so it carries
        # the translator's singleton mangling, and `1` is the BODY rather than
        # a negated number — which is the whole discrimination.
        assert "g(\\ _D ^ 1, A, B)" in out, out
        assert "use_module(library(lambda), [(\\)/1," in out, out

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
        # ...and yet the translator gives them opposite verdicts: the tight
        # spelling becomes a closure, the spaced one stays a comparison.
        tight_out = clausal_source_to_prolog("p(A) <- (g(D <-1, A))\n",
                                             strict=True)
        spaced_out = clausal_source_to_prolog("p(A) <- (g(D < -1, A))\n",
                                              strict=True)
        assert "library(lambda)" in tight_out, tight_out
        assert "library(lambda)" not in spaced_out, spaced_out


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

    * the live-file pin (``test_kit_query_combinators_is_strict_clean``)
      was RELOCATED 2026-09-08 to the repository that ships the kit
      library, and is pinned there: reading a sibling repository by
      absolute path fails on any other machine and tied this open tree
      to source it does not ship.
    * ``test_kit_witness_names_the_construct`` needs an actual refusal to
      assert the construct-naming shape against, which the live file no
      longer has. Re-pointed at a FROZEN in-repo fixture (a vendored
      snapshot of the pre-migration source, see the fixture file's own
      header) instead of being deleted — this also starts fixing the
      cross-repo-witness fragility itself: a test that reads a live file
      from a sibling repo has its pass/fail depend on that repo's
      current state, not on anything this translator controls.
    """

    def test_kit_witness_lowers_all_three_closures(self):
        """Frozen fixture, not the live file (see class docstring). It held
        the three shapes the refusal was written for; all three now LOWER,
        which is what makes it a witness for the 2026-09-14 change rather
        than a stale pin."""
        source = KIT_QUERY_COMBINATORS_PRE_MIGRATION.read_text()
        assert _refusals(source) == [], _refusals(source)
        out = clausal_source_to_prolog(source, strict=True)
        assert out.count("\\ ") >= 3, out
        assert "use_module(library(lambda), [(\\)/1," in out, out
