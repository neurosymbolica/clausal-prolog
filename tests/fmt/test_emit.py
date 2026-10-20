"""Emitter: module layout, directives, facts, comment placement."""

import pytest

from clausal.fmt import format_source
from clausal.fmt.comments import CommentLeakError


def test_directive_layout_and_blank_lines():
    src = "-module(m, [p(A)])\n-import_from(vocab, [met])\nrate(1),\n"
    out = format_source(src)
    # one blank line between top-level statements
    assert out == "-module(m, [p(A)])\n\n-import_from(vocab, [met])\n\nrate(1),\n"


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


# ─── String literals keep their source spelling ──────────────────────────────
#
# In the seam the quote character is meaning: ``'f'`` is an atom and ``"f"``
# is a string (and never a functor, ISO 6.3.3).  ``ast.unparse`` writes every
# string with the quotes it likes, so the emitter must put the source token
# back.  todo/done/fmt-requotes-a-quoted-atom-head-as-a-string-2026-10-20.md.


def test_a_single_quoted_atom_argument_stays_single_quoted():
    src = "p(X) <- (q('text', X))\n"
    assert format_source(src) == "p(X) <- (\n    q('text', X)\n)\n"


def test_a_double_quoted_string_argument_stays_double_quoted():
    src = 'p(X) <- (q("text", X))\n'
    assert format_source(src) == 'p(X) <- (\n    q("text", X)\n)\n'


def test_a_quoted_atom_head_functor_stays_an_atom():
    src = "-private([f(_)])\n'f'(X) <- (X is 1)\n"
    assert format_source(src) == "-private([f(_)])\n\n'f'(X) <- (\n    X is 1\n)\n"


def test_a_quoted_atom_body_goal_stays_an_atom():
    src = "-private([p(_), a])\np(X) <- ('=='(X, a), '=..'(X, [f, 1]))\n"
    assert format_source(src) == (
        "-private([p(_), a])\n\np(X) <- (\n    '=='(X, a),\n    '=..'(X, [f, 1])\n)\n"
    )


def test_a_quoted_atom_in_a_directive_stays_an_atom():
    src = "-meta_predicate(tfilter(2, '?', '?'))\n"
    assert format_source(src) == src


def test_a_quoted_atom_in_a_fact_stays_an_atom():
    src = "op(700, xfx, '=='),\nop(200, xfy, '^'),\n"
    assert format_source(src) == src


@pytest.mark.parametrize(
    "literal",
    [
        "'say \"hi\"'",
        "'back\\\\slash'",
        '"it\'s"',
        "r'raw\\d+'",
        'R"raw\\d+"',
        "b'bytes'",
        'b"bytes"',
        "u'legacy'",
        "'''triple single'''",
        '"""triple double"""',
        "'a' 'b'",
        '"a" "b"',
        "f'{X} atom-ish'",
        'f"{X} string-ish"',
        "'café'",
        '"café"',
    ],
)
def test_every_string_literal_is_written_exactly_as_the_source_spelled_it(literal):
    src = f"p(X) <- (q({literal}, X))\n"
    out = format_source(src)
    assert out == f"p(X) <- (\n    q({literal}, X)\n)\n"
    assert format_source(out) == out


def test_a_multi_line_triple_quoted_string_is_kept_verbatim():
    src = 'p(X) <- (q("""first\n  second\nthird""", X))\n'
    out = format_source(src)
    assert out == 'p(X) <- (\n    q("""first\n  second\nthird""", X)\n)\n'
    assert format_source(out) == out


def test_an_implicit_concatenation_across_lines_is_kept_verbatim():
    src = "p(X) <- (q('first '\n      'second', X))\n"
    out = format_source(src)
    assert out == "p(X) <- (\n    q('first '\n      'second', X)\n)\n"
    assert format_source(out) == out


def test_a_literal_with_a_comment_inside_its_span_keeps_its_quote_character():
    # A comment between the parts of an implicit concatenation is captured
    # as a comment, so the span cannot be copied verbatim (the comment would
    # be written twice).  The literal is then respelled -- in the quote
    # character the source used, which is the part the seam reads.
    src = "p(X) <- (q('first '  # halves\n      'second', X))\n"
    out = format_source(src)
    assert "'first second'" in out
    assert out.count("# halves") == 1
    assert format_source(out) == out
    src = 'p(X) <- (q("first "  # halves\n      "second", X))\n'
    assert '"first second"' in format_source(src)


def test_a_non_ascii_line_does_not_shift_the_literal_spelling():
    # ast columns are byte offsets and tokenize columns are character
    # offsets; a literal after a non-ASCII character must still be found.
    src = "p(X) <- (q('café', 'atom', \"string\"))\n"
    assert format_source(src) == "p(X) <- (\n    q('café', 'atom', \"string\")\n)\n"


def test_a_string_in_an_exploded_dict_keeps_its_quotes():
    long_key = "k" * 40
    src = f"p(X) <- (q({{'{long_key}': 'atom', \"{long_key}\": \"string\"}}, X))\n"
    out = format_source(src)
    assert f"'{long_key}': 'atom'" in out
    assert f'"{long_key}": "string"' in out
    assert format_source(out) == out


def test_a_literal_node_built_without_source_is_written_double_quoted():
    # A transform may build a string Constant with no source spelling; the
    # emitter has no token to copy, and writes it double-quoted (a string in
    # every mode, and refused loudly if it lands in functor position).
    import ast

    from clausal.fmt import CommentTable, format_tree

    tree, table = CommentTable.capture("p(X) <- (q(X))\n")
    goal = tree.body[0].value.comparators[0].operand
    goal.args.append(ast.Constant("new"))
    assert format_tree(tree, table) == 'p(X) <- (\n    q(X, "new")\n)\n'


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
    src = "-import_from(vocab, [met, unmet])\n"
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
    # a commented element opens a section: blank line above its comment block
    assert out == (
        "-module(m, [\n"
        "    # ---- contract section\n"
        "    p(A),  # trailing note\n"
        "\n"
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


def test_wide_fixture_dict_explodes_one_key_per_line():
    # A hand-wrapped profile fixture must not collapse onto one enormous line
    # (reg-d trial, 2026-08-15): past WIDTH its dict explodes.
    src = ("q_all_fail({individual_income_y1_usd_cents: 15000000, "
           "joint_income_y1_usd_cents: 25000000, "
           "net_worth_excl_residence_usd_cents: 80000000}),\n")
    assert format_source(src) == (
        "q_all_fail({\n"
        "    individual_income_y1_usd_cents: 15000000,\n"
        "    joint_income_y1_usd_cents: 25000000,\n"
        "    net_worth_excl_residence_usd_cents: 80000000\n"
        "}),\n"
    )


def test_short_fixture_dict_stays_on_one_line():
    src = "q_cert({certifications_held: [series_65]}),\n"
    assert format_source(src) == src


def test_wide_dict_inside_a_goal_explodes_at_goal_indent():
    src = ("t(R) <- (\n"
           "    assess({individual_income_y1_usd_cents: 15000000, "
           "joint_income_y1_usd_cents: 25000000, "
           "net_worth_excl_residence_usd_cents: 80000000}, R)\n"
           ")\n")
    assert format_source(src) == (
        "t(R) <- (\n"
        "    assess({\n"
        "        individual_income_y1_usd_cents: 15000000,\n"
        "        joint_income_y1_usd_cents: 25000000,\n"
        "        net_worth_excl_residence_usd_cents: 80000000\n"
        "    }, R)\n"
        ")\n"
    )


def test_exploded_dict_is_idempotent():
    src = ("q_all_fail({individual_income_y1_usd_cents: 15000000, "
           "joint_income_y1_usd_cents: 25000000, "
           "net_worth_excl_residence_usd_cents: 80000000}),\n")
    once = format_source(src)
    assert format_source(once) == once


def test_arrow_lambda_is_idempotent():
    src = "t(B) <- (\n    fold(((X) <- p(X)), B)\n)\n"
    once = format_source(src)
    assert format_source(once) == once
