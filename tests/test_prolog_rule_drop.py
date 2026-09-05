"""Regression tests for the 2026-09 rule-drop Critical defect.

A `<-` RULE followed by the ordinary fact-separator comma —
``rule(H) <- (\\n  body\\n),`` — used to be SILENTLY DROPPED from
translation: no output, no warning, strict mode called the file clean.

At Python-statement level that source is ``Expr(Tuple([Compare(<-rule)]))``
— the same 1-tuple wrapping every ordinary FACT statement
(``fact(a),`` = ``Expr(Tuple([Call]))``), which ``_convert_stmt`` unwrapped
for facts but not for rules: the tuple-unwrap branch checked
``isinstance(value.elts[0], python_ast.Call)`` only, so a ``Compare`` in
that same position fell through every remaining branch to a bare
``return None`` — no warning, so strict mode never raised either.

Fix: ``_convert_stmt`` now dispatches every element of a statement tuple
(1-element or multi-element) through ``_convert_clause_value``, the same
fact/rule/DCG-rule dispatch used for a bare (unwrapped) statement. Any
element — or any bare statement — that dispatch doesn't recognize is
reported with ``_add_warning`` instead of silently vanishing, so strict
mode now raises on any exit path that used to fail open.
"""

import os
import subprocess

import pytest

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    UntranslatableConstructError,
)

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"


# ── The exact reproduction from the incident report ─────────────────────

RULE_DROP_SRC = "mandatory_ground(a) <- (\n    implements(k)\n),\n"


class TestRuleDropRegression:

    def test_rule_no_longer_produces_empty_output(self):
        """RED before the fix: this used to return '' with no warning."""
        out = clausal_source_to_prolog(RULE_DROP_SRC, strict=True)
        assert out != ""

    def test_rule_translates_with_head_and_body(self):
        out = clausal_source_to_prolog(RULE_DROP_SRC, strict=True)
        assert "mandatory_ground(a) :-" in out
        assert "implements(k)" in out

    def test_wrapped_rule_matches_unwrapped_rule(self):
        """A 1-tuple-wrapped rule must translate IDENTICALLY to the same
        rule without the trailing comma (the unwrapped form already
        worked correctly before this fix — it never hit the buggy
        tuple-unwrap branch at all)."""
        unwrapped = "mandatory_ground(a) <- (\n    implements(k)\n)\n"
        wrapped = RULE_DROP_SRC
        assert (clausal_source_to_prolog(unwrapped, strict=True)
                == clausal_source_to_prolog(wrapped, strict=True))

    def test_multiple_wrapped_rules_all_survive(self):
        """Every one of several 1-tuple-wrapped rules in one file must
        appear — the bug did not merely mistranslate, it dropped the
        clause entirely, so a regression here would silently lose
        content again."""
        src = (
            "mandatory_ground(a) <- (\n    implements(k1)\n),\n"
            "mandatory_ground(b) <- (\n    implements(k2)\n),\n"
            "mandatory_ground(c) <- (\n    implements(k3)\n),\n"
        )
        out = clausal_source_to_prolog(src, strict=True)
        assert "mandatory_ground(a) :-" in out
        assert "mandatory_ground(b) :-" in out
        assert "mandatory_ground(c) :-" in out
        assert "implements(k1)" in out
        assert "implements(k2)" in out
        assert "implements(k3)" in out

    def test_single_line_delegation_rule_also_survives(self):
        """The corpus idiom is not only the multi-line-parenthesized
        body — a single-line delegation wrapper like
        ``foo(X) <- bar(X),`` is the exact same AST shape
        (Expr(Tuple([Compare]))) and must translate too."""
        src = "emir_party_status(P, A, S) <- party_status(P, A, S),\n"
        out = clausal_source_to_prolog(src, strict=True)
        assert "emir_party_status(P, A, S) :-" in out
        assert "party_status(P, A, S)" in out


# ── The fact-separator control: facts must remain unaffected ────────────

class TestFactSeparatorControl:

    def test_trailing_comma_fact_still_translates(self):
        out = clausal_source_to_prolog("edge(1, 2),\n", strict=True)
        assert "edge(1, 2)." in out

    def test_bare_fact_no_comma_still_translates(self):
        out = clausal_source_to_prolog("edge(1, 2)\n", strict=True)
        assert "edge(1, 2)." in out


# ── Multi-element statement tuple: fact(a), fact(b), styles, and a rule
#    sharing a tuple position with sibling statements ───────────────────

class TestMultiElementTuple:

    def test_two_facts_in_one_statement_tuple(self):
        """`fact(a), fact(b),` on ONE physical line parses as a single
        Expr(Tuple([Call, Call])) statement — a different shape from two
        separate one-per-line trailing-comma facts, and previously
        silently dropped in its entirety (len(elts) == 1 required)."""
        out = clausal_source_to_prolog("fact(a), fact(b),\n", strict=True)
        assert "fact(a)." in out
        assert "fact(b)." in out

    def test_fact_and_rule_share_one_statement_tuple(self):
        """A rule at a non-first position inside a multi-element tuple
        must translate exactly like it would standing alone."""
        src = "fact(a), rule(X) <- (fact(X)),\n"
        out = clausal_source_to_prolog(src, strict=True)
        assert "fact(a)." in out
        assert "rule(X) :-" in out
        assert "fact(X)" in out

    def test_rule_first_fact_second_in_one_statement_tuple(self):
        """Position independence: a rule in the FIRST slot of a
        multi-element tuple, followed by a fact."""
        src = "rule(X) <- (fact(X)), other(a),\n"
        out = clausal_source_to_prolog(src, strict=True)
        assert "rule(X) :-" in out
        assert "fact(X)" in out
        assert "other(a)." in out


# ── Fail-closed net: every unrecognized statement shape must warn ───────

class TestFailClosedNet:
    """The standing 'silence at a parsed boundary fails open' rule: after
    the fix above, every remaining _convert_stmt/_convert_clause_value
    exit path must either produce output or call _add_warning (so strict
    mode raises). These tests feed deliberately weird — but
    Python-parseable — statement shapes that are NOT facts, rules, or DCG
    rules, and assert they refuse rather than vanish.
    """

    def test_bare_string_expression_statement_refuses(self):
        with pytest.raises(UntranslatableConstructError):
            clausal_source_to_prolog('"just a string"\n', strict=True)

    def test_bare_string_statement_warns_in_lenient_mode(self):
        out = clausal_source_to_prolog('"just a string"\n')
        assert "untranslatable" in out or "unsupported" in out

    def test_python_assignment_statement_refuses(self):
        """A real Python statement shape (Assign) that a malformed or
        hand-edited .clausal file could contain — not an Expr at all,
        so it used to hit the very first `return None` with no warning."""
        with pytest.raises(UntranslatableConstructError):
            clausal_source_to_prolog("x = 1\n", strict=True)

    def test_bare_comparison_without_arrow_refuses(self):
        """A Compare node that is NOT a `<-` arrow (detect_arrow returns
        None) used to fall through to a silent `return None` even when
        NOT wrapped in a tuple."""
        with pytest.raises(UntranslatableConstructError):
            clausal_source_to_prolog("a == b\n", strict=True)

    def test_bare_strict_atoms_directive_stays_a_recognized_no_op(self):
        """-strict_atoms (no parens, no args -- UnaryOp(USub(Name)), not
        Call) is engine-only atom-resolution bookkeeping with no Prolog
        equivalent. 523 corpus sites hit this shape (2026-09 census); a
        first pass at the fail-closed net treated it as an unrecognized
        UnaryOp and started warning on all of them (census clean count
        606 -> 190). It must stay a silent, non-warning no-op — same
        category as -private(...) — not get swept into the net."""
        out = clausal_source_to_prolog(
            "-strict_atoms\nfact(a),\n", strict=True
        )
        assert "fact(a)." in out
        assert "untranslatable" not in out
        assert "strict_atoms" not in out

    def test_unrecognized_element_inside_a_tuple_refuses(self):
        """A bare atom (0-arity, no parens) inside a comma-joined
        statement tuple — the corpus shape seen in
        utilities_negotiated_without_prior_call.clausal — is not a Call,
        Compare, or DCG rule, and must warn rather than vanish, even
        though its sibling elements in the same tuple translate fine."""
        with pytest.raises(UntranslatableConstructError) as exc:
            clausal_source_to_prolog("fact(a), some_atom,\n", strict=True)
        assert any("some_atom" in c for c in exc.value.constructs)

    def test_no_placeholder_without_warning_for_weird_shapes(self):
        """Guards the fail-open class directly: nothing in the lenient
        output for these weird shapes may claim success silently — every
        one must leave a warning trace."""
        for src in ('"just a string"\n', "x = 1\n", "a == b\n"):
            out = clausal_source_to_prolog(src)
            assert "untranslatable" in out or "unsupported" in out, (
                f"{src!r} produced no output and no warning trace"
            )


# ── End-to-end: a recovered `implements/1`-style rule actually RUNS ─────
#
# The corpus provenance mechanism is exactly this shape: a citations.clausal
# file defines `implements(CiteAtom) <- (marker_fact(CiteAtom)),` — a
# 1-tuple-wrapped rule delegating to a supporting fact. Before this fix
# every one of these was silently dropped, so `implements/1` was DECLARED
# (in -module's export list) but never DEFINED — a declared-but-undefined
# predicate RAISES existence_error the moment anything calls it. Recovering
# the rule text is necessary but not sufficient: this test also confirms
# the recovered clause actually RESOLVES a call in a real Prolog engine,
# not merely that text appears in the translator's output.

@pytest.mark.skipif(
    not os.path.exists(SCRYER),
    reason=f"Scryer binary not found at {SCRYER} -- execution check needs a real engine",
)
class TestRecoveredRuleResolvesInScryer:

    CITATIONS_STYLE_SRC = (
        "-module(citations_witness, [implements(X)])\n"
        "cite_marker(eu_dir_2014_24_art_57),\n"
        "implements(CITE) <- (\n"
        "    cite_marker(CITE)\n"
        "),\n"
    )

    def _run_scryer_query(self, tmp_path, pl_source: str, query: str):
        pl_file = tmp_path / "witness.pl"
        pl_file.write_text(pl_source)
        proc = subprocess.run(
            [SCRYER, "witness.pl"],
            cwd=tmp_path,
            input=query + "\n",
            capture_output=True,
            text=True,
            timeout=8,
        )
        return proc.stdout.strip(), proc.stderr

    def test_recovered_implements_rule_appears_in_output(self):
        out = clausal_source_to_prolog(self.CITATIONS_STYLE_SRC, strict=True)
        assert "implements(Cite) :-" in out
        assert "cite_marker(Cite)" in out

    def test_recovered_implements_rule_resolves_a_call(self, tmp_path):
        """Before the fix: implements/1 was declared-but-undefined, so
        Scryer would raise existence_error(procedure, implements/1) on
        this exact query. After the fix: the call resolves via the
        recovered clause, delegating to the marker fact and succeeding."""
        pl_source = clausal_source_to_prolog(self.CITATIONS_STYLE_SRC, strict=True)
        stdout, stderr = self._run_scryer_query(
            tmp_path, pl_source, "implements(eu_dir_2014_24_art_57)."
        )
        assert stdout == "true.", (
            f"expected the recovered implements/1 clause to resolve the call, "
            f"got stdout={stdout!r} stderr={stderr!r}"
        )

    def test_unrecovered_baseline_would_have_raised(self, tmp_path):
        """Witness the failure mode this test suite guards against: with
        the rule LITERALLY absent (simulating the pre-fix silent drop),
        the same query raises existence_error — the declared-but-
        undefined pathology the corpus's implements/1 sites were
        actually hitting."""
        src_without_rule = (
            "-module(citations_witness, [implements(X)])\n"
            "cite_marker(eu_dir_2014_24_art_57),\n"
        )
        pl_source = clausal_source_to_prolog(src_without_rule, strict=True)
        assert "implements(Cite) :-" not in pl_source
        stdout, stderr = self._run_scryer_query(
            tmp_path, pl_source, "implements(eu_dir_2014_24_art_57)."
        )
        assert stdout.startswith("error("), (
            f"expected existence_error with the rule truly absent, got "
            f"stdout={stdout!r} stderr={stderr!r}"
        )
        assert "existence_error" in stdout
