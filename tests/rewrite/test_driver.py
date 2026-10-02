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
from tests._suffix import SEAM


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


def test_a_comma_separated_clause_series_is_left_alone(head_fold_rules):
    """Two clauses written as one comma-separated statement are exempt.

    The driver rewrites a statement that IS one clause.  A series is one
    statement holding several, and splicing into it would have to rebuild the
    series and re-derive which comma belongs to which clause -- so it is left
    byte-stable instead.  No file in this repo's corpus writes clauses that
    way, which is why it costs nothing today.
    """
    src = "p(X) <- (X is 5), r(1),\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.fired == []
    assert result.text == src  # byte-stable, formatting included


def test_a_keyword_head_is_left_alone(head_fold_rules):
    """Reification drops a head's keyword NAMES; a rewrite would too.

    ``p(A=X, B=2)`` reifies as ``Goal("p", [X, 2], [])``, so re-rendering the
    head after a fold would emit ``p(5, 2)`` and quietly change what callers
    may write.  The driver leaves such clauses byte-stable rather than trade a
    fold for the predicate's interface.
    """
    result = rewrite_source("p(A=X, B=2) <- (X is 5)\n", head_fold_rules)
    assert result.fired == []
    assert "A=X" in result.text


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


def test_deleted_goal_comments_move_above_the_clause_marked_stale(head_fold_rules):
    # The relocated comment described a goal that no longer exists, so it is
    # flagged for the comment-repair pass (operator call, 2026-08-15).
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),\n"
        "    # the verdict is unknown when keys are missing\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert result.text == (
        "# the verdict is unknown when keys are missing (maybe stale?)\n"
        "r(K, unknown(M)) <- (\n"
        "    m(K, M)\n"
        ")\n"
    )


def test_deleted_goal_trailing_comment_is_marked_stale_too(head_fold_rules):
    # The diversity trial's lint pragmas ride as trailing comments; they move
    # to the statement and carry the marker.
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),\n"
        "    S is unknown(M)  # lint: do not fold\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "# lint: do not fold (maybe stale?)" in result.text


def test_surviving_goal_comments_are_not_marked(head_fold_rules):
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),  # stays accurate\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "# stays accurate\n" in result.text
    assert "stays accurate (maybe stale?)" not in result.text


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
    runaway = tmp_path / f"runaway{SEAM}"
    runaway.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause])

        rewrite_clause(Clause(H, G, P), Clause(H, G, P)),
        """))
    with pytest.raises(RewriteError, match="20"):
        rewrite_source("p(X) <- (m(X))\n", [runaway])


def test_a_rule_that_invents_a_goal_is_refused_loudly(tmp_path):
    """Splicing reuses nodes, so a goal with no original has no node to reuse.

    Inventing goals is a real thing to want; it needs a rendering path and a
    decision about where its comments come from.  Until then the driver says
    so rather than mis-splicing.
    """
    inventive = tmp_path / f"inventive{SEAM}"
    inventive.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [G], P), Clause(H, [G, Goal("extra", [], [])], P)),
        """))
    with pytest.raises(RewriteError, match="splice"):
        rewrite_source("p(X) <- (m(X))\n", [inventive])


def test_a_rule_that_puts_a_lambda_in_the_head_is_refused(tmp_path):
    """``render_ast`` marks a rendered lambda arrow with a sentinel.

    Only the text-level renderer strips it, and the driver splices NODES, so a
    head carrying one would be written out with ``__clausal_lambda_arrow__``
    in it.  No shipped rule can produce that -- which is exactly why the guard
    has to be tested with one that can, or it is dead code.  It was: the guard
    matched a constant that never appears.
    """
    lambda_head = tmp_path / f"lambda_head{SEAM}"
    lambda_head.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        # carry the lambda term out of the body goal and into the head
        rewrite_clause(Clause(Goal(NAME, ARGS, KW), [Goal(_, [LAM], _)], POS), Clause(Goal(NAME, [*ARGS, LAM], KW), [], POS)),
        """))
    with pytest.raises(RewriteError, match="lambda"):
        rewrite_source("p(X) <- (m(((Y) <- q(Y))))\n", [lambda_head])


def test_a_head_that_cannot_be_rendered_at_all_is_refused(tmp_path):
    """A rule may bind a head argument to something with no source form.

    An escape builds a Python callable, which the renderer refuses outright.
    That is a rule bug and is reported as one, not as a traceback escaping
    the driver.
    """
    callable_head = tmp_path / f"callable_head{SEAM}"
    callable_head.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(Goal(NAME, ARGS, KW), GOALS, POS), Clause(HEAD2, GOALS, POS)) <- (
            LAM is ((X) <- p(X)),
            HEAD2 is Goal(NAME, [*ARGS, LAM], KW)
        )
        """))
    with pytest.raises(RewriteError, match="cannot be rendered"):
        rewrite_source("p(X) <- (m(X))\n", [callable_head])


# ---- modified goals: the positional correspondence -------------------------
#
# When a rule keeps the goal COUNT, the correspondence is positional: each
# output goal is its input goal verbatim or modified in place.  A modified
# goal is rendered to a fresh node; its comments ride across WITHOUT the
# stale marker, because the goal survives.


def _rename_rule(tmp_path):
    """old(...) becomes new(...) -- a one-goal modification, same goal count."""
    rule = tmp_path / f"rename{SEAM}"
    rule.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -private([old, new])
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, GOALS, P), Clause(H, GOALS2, P)) <- (
            rename_goal(GOALS, GOALS2)
        )
        rename_goal([Goal(old, A, K), *GS], [Goal(new, A, K), *GS]),
        rename_goal([G, *GS], [G, *GS2]) <- rename_goal(GS, GS2)
        """))
    return [rule]


def test_modified_goal_is_spliced_in_place(tmp_path):
    src = "p(X) <- (m(X), old(X, 5))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert result.text == "p(X) <- (\n    m(X),\n    new(X, 5)\n)\n"
    assert len(result.fired) == 1


def test_modified_goal_comments_ride_across_unmarked(tmp_path):
    src = (
        "p(X) <- (\n"
        "    m(X),\n"
        "    # still describes the call\n"
        "    old(X, 5)  # and so does this\n"
        ")\n"
    )
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert result.text == (
        "p(X) <- (\n"
        "    m(X),\n"
        "    # still describes the call\n"
        "    new(X, 5)  # and so does this\n"
        ")\n"
    )
    assert "maybe stale" not in result.text


def test_modified_goal_keeps_a_surviving_inline_lambda_arrow(tmp_path):
    """The arrow route: a modified goal is rendered to TEXT and re-parsed, so
    a lambda that survives inside it must come back as ``<-``, never ``< -``.
    """
    src = "p(B) <- (old(((X, V) <- (V == X * 2)), B))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "new(((X, V) <- (V == X * 2)), B)" in result.text
    assert "< -" not in result.text


def test_modified_goal_keeps_a_genuine_less_than_negative(tmp_path):
    """The other half of the arrow rule: a real ``A < -B`` inside a modified
    goal renders spaced and is NOT registered as an arrow."""
    src = "p(A, B) <- (old(A < -B))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "new(A < -B)" in result.text
    assert "<- B" not in result.text.replace("p(A, B) <- (", "")


def test_equal_count_reorder_is_refused(tmp_path):
    """Swapping two goals keeps the count; the positional correspondence must
    not read the swap as two modifications and shuffle their comments."""
    swap = tmp_path / f"swap{SEAM}"
    swap.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause])

        rewrite_clause(Clause(H, [G1, G2], P), Clause(H, [G2, G1], P)),
        """))
    with pytest.raises(RewriteError, match="REORDER"):
        rewrite_source("p(X) <- (m(X), r(X))\n", [swap])


def test_modification_with_count_change_is_refused(tmp_path):
    """Modify one goal AND drop another: neither correspondence covers it."""
    mixed = tmp_path / f"mixed{SEAM}"
    mixed.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -private([old, new])
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [Goal(old, A, K), _], P), Clause(H, [Goal(new, A, K)], P)),
        """))
    with pytest.raises(RewriteError, match="splice"):
        rewrite_source("p(X) <- (old(X), m(X))\n", [mixed])


def test_modified_goal_that_is_not_a_goal_is_refused(tmp_path):
    """A conjunction group reifies as a bare list, which renders as a LIST
    LITERAL -- no faithful node, so the driver refuses rather than corrupt."""
    grouping = tmp_path / f"grouping{SEAM}"
    grouping.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [G], P), Clause(H, [[G, Goal("extra", [], [])]], P)),
        """))
    with pytest.raises(RewriteError, match="not a plain Goal"):
        rewrite_source("p(X) <- (m(X))\n", [grouping])


def test_modified_goal_rewrite_is_idempotent(tmp_path):
    src = "p(X) <- (m(X), old(X, 5))\n"
    rules = _rename_rule(tmp_path)
    once = rewrite_source(src, rules)
    again = rewrite_source(once.text, rules)
    assert again.text == once.text
    assert again.fired == []


def test_folds_a_single_char_atom(head_fold_rules):
    # The file pins ``-double_quotes(atom)`` explicitly: ``"t"`` is the
    # ATOM ("t",), so the folded head renders as the bare name.
    result = rewrite_source('-double_quotes(atom)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    assert result.text == '-double_quotes(atom)\n\np(t) <- (\n    m(1)\n)\n'
    assert len(result.fired) == 1


def test_the_file_mode_reaches_each_clause_segment(head_fold_rules):
    """The driver reifies each clause from its own SEGMENT, which never
    contains the file's ``-double_quotes`` directive, so the mode is tracked
    statement by statement and handed to the reifier.  Without that a
    chars file's ``"t"`` reified as an atom (before the flip) and an atom
    file's as a string (after it), and the folded head came back respelled
    -- the corpus idempotency test caught it on the first flipped run."""
    result = rewrite_source('-double_quotes(chars)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    assert result.text == '-double_quotes(chars)\n\np("t") <- (\n    m(1)\n)\n'
    result = rewrite_source('-double_quotes(atom)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    assert result.text == '-double_quotes(atom)\n\np(t) <- (\n    m(1)\n)\n'


def test_a_mid_file_directive_governs_only_the_clauses_below_it(head_fold_rules):
    """Tracked statement by statement: the clause above the directive folds
    under the default (chars), the clause below it under the declared
    atom mode."""
    src = ('p(TAG) <- (TAG is "t", m(1))\n'
           '-double_quotes(atom)\n'
           'q(TAG) <- (TAG is "u", m(2))\n')
    result = rewrite_source(src, head_fold_rules)
    assert 'p("t") <- (' in result.text
    assert 'q(u) <- (' in result.text


def test_reify_ast_reads_a_segment_under_the_mode_it_is_handed():
    """The ``double_quotes=`` parameter itself, without the driver."""
    import ast
    from clausal.reflection import reify_ast, Clause, is_v, vfield
    stmt = ast.parse('p(X) <- (X is "t")\n').body[0]
    seen = {}
    for mode in ("atom", "chars"):
        clause = reify_ast(stmt, source='p(X) <- (X is "t")', double_quotes=mode)
        assert is_v(clause, Clause)
        (unify,) = vfield(clause, "goals")
        seen[mode] = unify.right
    assert seen["atom"] == ("Atom", "t"), seen
    assert seen["chars"] == "t", seen      # the carrier reifies as its plain str


def test_an_unknown_mode_is_left_to_the_loader(head_fold_rules):
    """``-double_quotes(codes)`` is a load error; the driver neither adopts
    it nor pretends it is atom mode -- the clause below it still reads
    under the mode in force (the default)."""
    import ast
    from clausal.rewrite.driver import _double_quotes_directive
    stmt = ast.parse("-double_quotes(codes)\n").body[0]
    assert _double_quotes_directive(stmt) is None
    src = '-double_quotes(codes)\np(TAG) <- (TAG is "t", m(1))\n'
    result = rewrite_source(src, head_fold_rules)
    assert 'p("t") <- (' in result.text


def test_folds_a_single_char_string(head_fold_rules):
    # The chars twin, written as the STRING the ``is`` goal binds.  What this
    # pins is the renderer's half: a folded STRING head argument comes back
    # DOUBLE-quoted, and is not demoted to an atom.
    from clausal.reflection import Clause, Goal, render_source
    folded = Clause(Goal("p", ["t"], []), [Goal("m", [1], [])], None)
    assert render_source(folded) == 'p("t") <- (m(1))'
