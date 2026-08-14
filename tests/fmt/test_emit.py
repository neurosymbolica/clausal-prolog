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
