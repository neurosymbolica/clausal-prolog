"""Emitter: module layout, directives, facts, comment placement."""

import pytest

from clausal.fmt import format_source
from clausal.fmt.comments import CommentLeakError


def test_directive_layout_and_blank_lines():
    src = "-module(m, [p(A)])\n-import_from(kit, [met])\nrate(1),\n"
    out = format_source(src)
    # one blank line between top-level statements
    assert out == "-module(m, [p(A)])\n\n-import_from(kit, [met])\n\nrate(1),\n"


def test_fact_table_stays_adjacent():
    src = "band(1, 100),\nband(2, 200),\n\n\nother(9),\n"
    out = format_source(src)
    # consecutive one-line facts with the SAME head functor: no blank between;
    # different functor: one blank
    assert out == "band(1, 100),\nband(2, 200),\n\nother(9),\n"


def test_comments_emit_above_then_node_then_trailing():
    src = "# above\n-module(m, [a])  # trail\n"
    assert format_source(src) == "# above\n-module(m, [a])  # trail\n"


def test_comment_groups_separated_by_one_blank():
    src = "# g1 line1\n# g1 line2\n\n\n\n# g2\n-module(m, [a])\n"
    assert format_source(src) == "# g1 line1\n# g1 line2\n\n# g2\n-module(m, [a])\n"


def test_file_edges_round_trip():
    src = "# header\n\nrate(1),\n# eof note\n"
    assert format_source(src) == "# header\nrate(1),\n\n# eof note\n"


def test_comment_above_a_fact_breaks_the_fact_table():
    src = "band(1, 100),\n# a note about the second band\nband(2, 200),\n"
    out = format_source(src)
    assert out == "band(1, 100),\n\n# a note about the second band\nband(2, 200),\n"


def test_bare_directive():
    assert format_source("-strict_atoms\nrate(1),\n") == "-strict_atoms\n\nrate(1),\n"


def test_empty_source_and_comment_only_source():
    assert format_source("") == ""
    assert format_source("# just a note\n") == "# just a note\n"


def test_exactly_one_trailing_newline():
    for src in ["rate(1),", "rate(1),\n\n\n", "# note\n\n\n"]:
        out = format_source(src)
        assert out.endswith("\n") and not out.endswith("\n\n")


def test_conservation_hard_error_on_emitter_bug(monkeypatch):
    # simulate an emitter that forgets comments: force-skip mark_emitted
    from clausal.fmt import comments as C

    monkeypatch.setattr(C.CommentTable, "mark_emitted", lambda self, node: None)
    with pytest.raises(CommentLeakError):
        format_source("# doomed\nrate(1),\n")


def test_clause_canonical_layout():
    src = "p(X, V) <- (q(X), V is 1)\n"
    out = format_source(src)
    assert out == "p(X, V) <- (\n    q(X),\n    V is 1\n)\n"


def test_single_goal_clause():
    assert format_source("p(X) <- (q(X))\n") == "p(X) <- (\n    q(X)\n)\n"


def test_goal_comments_ride_their_goal():
    src = "p(X) <- (\n# NL anchor\nq(X),  # trail\nX is 1)\n"
    out = format_source(src)
    assert out == "p(X) <- (\n    # NL anchor\n    q(X),  # trail\n    X is 1\n)\n"


def test_nested_group_layout():
    src = "p(X) <- (a(X), (b(X), c(X)) or (d(X)), e(X))\n"
    out = format_source(src)
    assert out == (
        "p(X) <- (\n    a(X),\n    (\n        b(X),\n        c(X)\n    ) or (\n"
        "        d(X)\n    ),\n    e(X)\n)\n"
    )


def test_plain_nested_group_is_its_own_block():
    src = "p(X) <- (a(X), (b(X), c(X)), e(X))\n"
    assert format_source(src) == (
        "p(X) <- (\n    a(X),\n    (\n        b(X),\n        c(X)\n    ),\n    e(X)\n)\n"
    )


def test_comment_above_a_nested_group():
    src = "p(X) <- (\n    a(X),\n    # about the group\n    (b(X), c(X))\n)\n"
    assert format_source(src) == (
        "p(X) <- (\n    a(X),\n    # about the group\n    (\n        b(X),\n"
        "        c(X)\n    )\n)\n"
    )


def test_long_goals_are_not_wrapped():
    goal = "very_long_predicate_name(AAAA, BBBB, CCCC, DDDD, EEEE, FFFF, GGGG, HHHH)"
    src = f"p(X) <- ({goal})\n"
    assert goal in format_source(src)  # emitted on one line, untouched


def test_idempotence_over_all_emit_tests():
    for src in [
        "p(X, V) <- (q(X), V is 1)\n",
        "# above\n-module(m, [a])  # trail\nband(1, 2),\nband(2, 3),\n",
        "p(X) <- (a(X), (b(X), c(X)) or (d(X)), e(X))\n",
        "# header\n\n# above\np(X) <- (\n    # NL anchor\n    q(X)  # trail\n)\n# eof\n",
    ]:
        once = format_source(src)
        assert format_source(once) == once, src


def test_one_goal_body_written_as_a_tuple_keeps_its_comma():
    # (g,) is a one-element tuple; (g) is just g.  Dropping the comma here
    # would change the tree, so the comma is kept.
    src = "p(X) <- (\n    q(X),\n)\n"
    assert format_source(src) == src


def test_two_goal_body_drops_the_final_comma():
    assert format_source("p(X) <- (q(X), r(X),)\n") == (
        "p(X) <- (\n    q(X),\n    r(X)\n)\n"
    )


def test_one_goal_nested_group_keeps_its_comma():
    src = "p(X) <- (\n    a(X),\n    (\n        b(X),\n    )\n)\n"
    assert format_source(src) == src


def test_strings_are_written_with_double_quotes():
    src = "p(X) <- (q('text', X))\n"
    assert format_source(src) == 'p(X) <- (\n    q("text", X)\n)\n'


def test_strings_needing_escapes_keep_their_quotes():
    for literal in ["'say \"hi\"'", "'back\\\\slash'"]:
        src = f"p(X) <- (q({literal}))\n"
        out = format_source(src)
        assert format_source(out) == out  # whatever it chose, it is stable
        assert '"say \\"hi\\""' not in out


def test_clause_with_a_trailing_comma_keeps_it():
    # `head <- (...)` and `head <- (...),` are different trees: the comma makes
    # the statement a tuple.  Dropping it also un-spaces the arrow into `< -`,
    # which the engine does not accept.
    src = "p(X) <- (\n    q(X),\n    r(X)\n),\n"
    assert format_source(src) == src


def test_comma_separated_series_stays_on_one_line():
    # Splitting a series across lines would end the statement at the first
    # newline and turn one statement into several.
    src = "p(X) <- (q(X)), r(Y) <- (s(Y)),\n"
    assert format_source(src) == "p(X) <- (q(X)), r(Y) <- (s(Y)),\n"


def test_comma_separated_facts_stay_on_one_line():
    assert format_source("band(1), band(2),\n") == "band(1), band(2),\n"


def test_directive_with_a_trailing_comma():
    assert format_source("-module(m, [a]),\n") == "-module(m, [a]),\n"


def test_comment_inside_a_multiline_directive_stays_with_its_entry():
    # SUPERSEDED v1 behavior (2026-08-15): entries used to evict their notes
    # above the whole statement when the directive re-rendered on one line.
    # Directive-list elements are attachment nodes now, and a commented list
    # explodes — the note rides its entry. The optional trailing comma after
    # the last element is dropped (v1's standing comma policy).
    src = "-module(m, [\n    p(A),  # about p\n    q(B),\n])\n\nrate(1),\n"
    assert format_source(src) == (
        "-module(m, [\n    p(A),  # about p\n    q(B)\n])\n\nrate(1),\n"
    )


def test_comment_before_a_closing_body_paren_stays_with_the_clause():
    src = "p(X) <- (\n    q(X)\n    # dangling note\n)\n\nrate(1),\n"
    assert format_source(src) == (
        "# dangling note\np(X) <- (\n    q(X)\n)\n\nrate(1),\n"
    )


# ---------------------------------------------------------------------------
# Directive-list explosion (operator conventions, 2026-08-15 trial): a module
# export list collapsed onto one enormous line, and its section comments were
# evicted above the whole statement where they read as orphans. Long or
# commented directive lists explode one element per line; their comments ride
# their elements.
# ---------------------------------------------------------------------------

def test_short_directive_stays_on_one_line():
    src = "-import_from(kit, [met, unmet])\n"
    assert format_source(src) == src


def test_long_directive_list_explodes_one_element_per_line():
    src = ("-module(wt_compliance, [wt_weekly_limit_minutes(LIMIT), "
           "reference_period_max_weeks(WEEKS), "
           "avg_weekly_working_minutes(TOTAL_WORK_MINS, QUALIFYING_WEEKS, AVG), "
           "total_work_minutes, qualifying_weeks])\n")
    out = format_source(src)
    assert out == (
        "-module(wt_compliance, [\n"
        "    wt_weekly_limit_minutes(LIMIT),\n"
        "    reference_period_max_weeks(WEEKS),\n"
        "    avg_weekly_working_minutes(TOTAL_WORK_MINS, QUALIFYING_WEEKS, AVG),\n"
        "    total_work_minutes,\n"
        "    qualifying_weeks\n"
        "])\n"
    )


def test_element_comments_ride_their_elements():
    src = ("-module(m, [\n"
           "    # ---- contract section\n"
           "    p(A),  # trailing note\n"
           "    # ---- atoms section\n"
           "    key_atom\n"
           "])\n")
    out = format_source(src)
    assert out == (
        "-module(m, [\n"
        "    # ---- contract section\n"
        "    p(A),  # trailing note\n"
        "    # ---- atoms section\n"
        "    key_atom\n"
        "])\n"
    )


def test_commented_but_short_list_still_explodes():
    src = "-private([\n    # why this is local\n    helper_atom\n])\n"
    assert format_source(src) == src


def test_exploded_directive_is_idempotent():
    src = ("-module(m, [\n"
           "    # section\n"
           "    p(A),\n"
           "    q(B)\n"
           "])\n")
    once = format_source(src)
    assert format_source(once) == once


# ---------------------------------------------------------------------------
# Arrow preservation (2026-08-15 trial, vat bisect_flip lambdas): the engine
# distinguishes the arrow `<-` from a genuine less-than-negative `A < -B` BY
# SOURCE SPACING — the ASTs are identical. ast.unparse prints `< -`, which
# silently turns every inline lambda argument into a comparison. The formatter
# must carry an arrow ledger from capture to emission.
# ---------------------------------------------------------------------------

def test_inline_lambda_argument_keeps_its_arrow():
    src = ("t(B) <- (\n"
           "    bisect_flip(0, 7, ((X, V) <- reaches(X, 7, V)), B)\n"
           ")\n")
    out = format_source(src)
    assert "((X, V) <- reaches(X, 7, V))" in out
    assert "< -" not in out


def test_genuine_less_than_negative_stays_spaced():
    src = "t(A, B) <- (\n    check(A < -B)\n)\n"
    out = format_source(src)
    assert "A < -B" in out


def test_deeply_nested_arrow_survives():
    src = ("t(L) <- (\n"
           "    findall(W, wrap(((ID, S) <- req(ID, S)), W), L)\n"
           ")\n")
    out = format_source(src)
    assert "((ID, S) <- req(ID, S))" in out


def test_arrow_lambda_is_idempotent():
    src = "t(B) <- (\n    fold(((X) <- p(X)), B)\n)\n"
    once = format_source(src)
    assert format_source(once) == once
