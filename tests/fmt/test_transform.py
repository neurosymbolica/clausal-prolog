"""The transform contract: a replacement must say what happens to comments."""

import ast

import pytest

from clausal.fmt import ClausalTransformer, format_tree
from clausal.fmt.comments import CommentLeakError, CommentTable

SRC = "# above p\np(X) <- (\n    q(X)\n)\n"


class RenameP(ClausalTransformer):
    """Toy transform: rename head p -> p_renamed, correctly moving comments."""

    def visit_Expr(self, node):
        new = ast.parse(SRC.replace("p(X)", "p_renamed(X)", 1)).body[0]
        return self.replace(node, new)


class LeakyRename(ClausalTransformer):
    def visit_Expr(self, node):
        return ast.parse("p_renamed(X) <- (\n    q(X)\n)\n").body[0]  # no move!


class DeleteP(ClausalTransformer):
    """A transform that removes the clause and declares its comments obsolete."""

    def visit_Expr(self, node):
        return self.replace(node, None)


def test_transform_with_move_preserves_comments():
    tree, table = CommentTable.capture(SRC)
    tree = ast.fix_missing_locations(RenameP(table).visit(tree))
    out = format_tree(tree, table)
    assert out.startswith("# above p\np_renamed(X) <- (")


def test_transform_without_move_is_a_hard_error():
    tree, table = CommentTable.capture(SRC)
    tree = ast.fix_missing_locations(LeakyRename(table).visit(tree))
    with pytest.raises(CommentLeakError):
        format_tree(tree, table)


def test_explicit_drop_satisfies_the_contract():
    tree, table = CommentTable.capture(SRC)
    tree = ast.fix_missing_locations(DeleteP(table).visit(tree))
    assert format_tree(tree, table) == ""


def test_goal_comments_survive_a_goal_level_rewrite():
    src = "p(X) <- (\n    # anchor\n    q(X),  # trail\n    r(X)\n)\n"
    tree, table = CommentTable.capture(src)
    clause = tree.body[0]
    goals = clause.value.comparators[0].operand
    old_goal = goals.elts[0]
    new_goal = ast.parse("q_prime(X)").body[0].value
    table.move(old_goal, new_goal)
    goals.elts[0] = new_goal
    out = format_tree(ast.fix_missing_locations(tree), table)
    assert out == "p(X) <- (\n    # anchor\n    q_prime(X),  # trail\n    r(X)\n)\n"
