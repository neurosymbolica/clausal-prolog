"""CommentTable: capture, attachment convention, move/drop, conservation."""

import ast

import pytest

from clausal.fmt.comments import CommentLeakError, CommentTable, attachment_nodes

SRC = '''# file header line one
# file header line two

# above the module directive
-module(m, [p(A)])  # trailing the directive

# above the fact
rate(2500),

# clause header group one
#
# clause header group two

# second group above clause
p(X) <- (
    # above goal q
    q(X),  # trailing goal q
    X is 1
)
# after everything
'''


def _cap():
    return CommentTable.capture(SRC)


def test_file_header_attaches_to_module_above():
    _tree, t = _cap()
    assert t.module_above[0] == ["# file header line one", "# file header line two"]


def test_directive_gets_above_and_trailing():
    tree, t = _cap()
    directive = tree.body[0]
    assert t.above(directive) == [["# above the module directive"]]
    assert t.trailing(directive) == ["# trailing the directive"]


def test_blank_source_line_splits_comment_groups():
    tree, t = _cap()
    clause = tree.body[2]
    groups = t.above(clause)
    assert len(groups) == 2  # blank line between the two headers -> two groups
    assert groups[1] == ["# second group above clause"]


def test_goal_position_attachment():
    tree, t = _cap()
    clause = tree.body[2]
    body = clause.value.comparators[0].operand  # Tuple of goals
    goal_q = body.elts[0]
    assert t.above(goal_q) == [["# above goal q"]]
    assert t.trailing(goal_q) == ["# trailing goal q"]


def test_eof_comment_attaches_to_module_trailing():
    _tree, t = _cap()
    assert t.module_trailing == ["# after everything"]


def test_single_goal_body_is_an_attachment_node():
    tree, t = CommentTable.capture("q(X) <- (\n    # only goal\n    r(X)\n)\n")
    goal = tree.body[0].value.comparators[0].operand  # Call, not Tuple
    assert t.above(goal) == [["# only goal"]]


def test_attachment_nodes_are_in_source_order():
    tree, _t = _cap()
    nodes = attachment_nodes(tree)
    positions = [(n.lineno, n.col_offset) for n in nodes]
    assert positions == sorted(positions)
    assert tree.body[0] in nodes and tree.body[2] in nodes


def test_conservation_error_lists_lost_comments():
    _tree, t = _cap()
    with pytest.raises(CommentLeakError) as e:
        t.assert_conserved()  # nothing emitted yet -> everything is "lost"
    assert any("file header" in s for (_ln, s) in e.value.lost)


def test_move_and_drop():
    tree, t = _cap()
    clause = tree.body[2]
    new = ast.parse("p2(X) <- (r(X))").body[0]
    t.move(clause, new)
    assert t.above(new)[-1] == ["# second group above clause"]
    assert t.above(clause) == []
    t.drop(new)  # explicit drop clears the obligation
    assert t.above(new) == []


def test_drop_satisfies_conservation():
    tree, t = CommentTable.capture("# doomed\nrate(1),\n")
    t.drop(tree.body[0])
    t.assert_conserved()  # explicit drop is a discharge, not a leak


def test_mark_emitted_satisfies_conservation():
    tree, t = CommentTable.capture("# kept\nrate(1),  # trail\n")
    t.mark_emitted(tree.body[0])
    t.assert_conserved()
