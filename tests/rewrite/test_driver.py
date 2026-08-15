"""The rewrite driver: fixpoint application, node-reuse splicing, comment
conservation, arrow safety.

The comment tests are the point of the whole design.  A rewriter that works on
text has to guess where a comment went; this one does not rewrite text at all.
Goals the rule kept are the SAME ``ast`` nodes they were, so their comments were
never in question, and a goal the rule deleted has to be given somewhere for its
comments to go or the format run fails.
"""

import textwrap

import pytest

from clausal.fmt import format_source
from clausal.rewrite.driver import RewriteError, rewrite_source


def test_folds_and_reformats(head_fold_rules):
    src = "r(K, S) <- (m(K, M), S is unknown(M))\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "r(K, unknown(M)) <- (\n    m(K, M)\n)\n"
    assert len(result.fired) == 1


def test_untouched_file_is_exactly_fmt_output(head_fold_rules):
    src = "p(X) <- (m(X), r(X))\n\nband(1, 2),\nband(2, 3),\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == format_source(src)
    assert result.fired == []


def test_clause_folds_to_fact_with_trailing_comma(head_fold_rules):
    result = rewrite_source("p(X) <- (X is 5)\n", head_fold_rules)
    assert result.text == "p(5),\n"


def test_fixpoint_folds_two_variables_in_one_clause(head_fold_rules):
    src = "r(A, B) <- (m(K), A is tag(K), B is ok)\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "r(tag(K), ok) <- (\n    m(K)\n)\n"
    assert len(result.fired) == 2


def test_a_directive_is_left_alone(head_fold_rules):
    src = "-module(m, [p(A)])\n\np(X) <- (X is 5)\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "-module(m, [p(A)])\n\np(5),\n"


def test_comments_on_surviving_goals_stay_put(head_fold_rules):
    src = (
        "# the requirement clause\n"
        "r(K, S) <- (\n"
        "    # look up the missing keys\n"
        "    m(K, M),  # trailing note\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert result.text == (
        "# the requirement clause\n"
        "r(K, unknown(M)) <- (\n"
        "    # look up the missing keys\n"
        "    m(K, M)  # trailing note\n"
        ")\n"
    )


def test_deleted_goal_comments_move_above_the_clause(head_fold_rules):
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),\n"
        "    # the verdict is unknown when keys are missing\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert result.text == (
        "# the verdict is unknown when keys are missing\n"
        "r(K, unknown(M)) <- (\n"
        "    m(K, M)\n"
        ")\n"
    )


def test_inline_lambda_in_a_surviving_goal_keeps_its_arrow(head_fold_rules):
    src = (
        "t(B, S) <- (\n"
        "    maplist(((X, V) <- (V == X * 2)), B),\n"
        "    S is found(B)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "((X, V) <- (V == X * 2))" in result.text or "(X, V) <- (V == X * 2)" in result.text
    assert "< -" not in result.text
    assert "found(B)" in result.text.splitlines()[0]


def test_runaway_rule_hits_the_bound(tmp_path, head_fold_rules):
    runaway = tmp_path / "runaway.clausal"
    runaway.write_text(textwrap.dedent("""\
        -import_from(reflection, [Clause])

        RewriteClause(Clause(H, G, P), Clause(H, G, P)),
        """))
    with pytest.raises(RewriteError, match="20"):
        rewrite_source("p(X) <- (m(X))\n", [runaway])


def test_a_rule_that_invents_a_goal_is_refused_loudly(tmp_path):
    """Splicing reuses nodes, so a goal with no original has no node to reuse.

    Inventing goals is a real thing to want; it needs a rendering path and a
    decision about where its comments come from.  Until then the driver says
    so rather than mis-splicing.
    """
    inventive = tmp_path / "inventive.clausal"
    inventive.write_text(textwrap.dedent("""\
        -import_from(reflection, [Clause, Goal])

        RewriteClause(Clause(H, [G], P), Clause(H, [G, Goal("extra", [], [])], P)),
        """))
    with pytest.raises(RewriteError, match="splice"):
        rewrite_source("p(X) <- (m(X))\n", [inventive])
