"""The arrow ledger: which ``Compare(Lt, USub)`` nodes are really arrows.

``head <- body`` and ``head < -body`` parse to the SAME tree.  The engine tells
them apart by source spacing alone -- the ``<`` must sit immediately before the
``-`` -- so the distinction lives nowhere in the AST and cannot be recovered
from it.  ``ast.unparse`` always writes the spaced form, which means an inline
lambda passed to a higher-order predicate silently decays into a comparison the
moment anything re-renders it.

Capture therefore records which nodes were written as arrows, and emission
restores the tight spelling for exactly those.  A node a transform builds is not
in the ledger until the transform puts it there: constructing an arrow is a
claim about meaning, so it is made explicitly.
"""

import ast

import pytest

from clausal.fmt import format_source, format_tree
from clausal.fmt.comments import CommentTable

LAMBDA = "t(B) <- (\n    fold(((X) <- p(X)), B)\n)\n"
COMPARISON = "t(A, B) <- (\n    check(A < -B)\n)\n"


def test_inline_lambda_keeps_its_arrow():
    out = format_source(LAMBDA)
    assert "<- p(X)" in out
    assert "< -" not in out


def test_genuine_comparison_keeps_its_gap():
    # Same shape of tree, opposite meaning: this one must NOT be tightened.
    assert format_source(COMPARISON) == COMPARISON


def test_the_ledger_records_the_lambda_and_not_the_comparison():
    tree, table = CommentTable.capture(LAMBDA + COMPARISON)
    arrows = [node for node in ast.walk(tree) if node in table.arrows]
    # two clause arrows, one lambda arrow -- and not the comparison
    assert len(arrows) == 3
    _tree, comparison_table = CommentTable.capture(COMPARISON)
    assert len(comparison_table.arrows) == 1  # the clause arrow only


def test_arrows_survive_a_second_pass():
    once = format_source(LAMBDA)
    assert format_source(once) == once


def test_a_transform_registers_the_arrows_it_builds():
    """The contract a rewrite driver relies on: register, then emit."""
    tree, table = CommentTable.capture("t(B) <- (\n    fold(A, B)\n)\n")
    lam = ast.parse("(X) < -p(X)").body[0].value
    goal = tree.body[0].value.comparators[0].operand
    goal.args[0] = lam
    ast.fix_missing_locations(tree)

    unregistered = format_tree(tree, table)
    assert "< -" in unregistered  # a bare Compare is a comparison, as written

    tree, table = CommentTable.capture("t(B) <- (\n    fold(A, B)\n)\n")
    lam = ast.parse("(X) < -p(X)").body[0].value
    tree.body[0].value.comparators[0].operand.args[0] = lam
    ast.fix_missing_locations(tree)
    table.arrows.add(lam)
    assert "<- p(X)" in format_tree(tree, table)


@pytest.mark.parametrize(
    "source",
    [
        "p(XS, YS) <- (\n    maplist(((X, Y) <- (Y == X * 2)), XS, YS)\n)\n",
        "p(XS) <- (\n    maplist((X <- (X > 0)), XS)\n)\n",
        "p(R) <- (\n    call_goal((() <- (R is 42)))\n)\n",
        "p(X, Y) <- (\n    call_goal(((V, R) <- ((T == V + 1) and (R == T * 2))), X, Y)\n)\n",
        "p(A) <- (\n    q(A),\n    A < -1\n)\n",
    ],
)
def test_arrow_shapes_round_trip(source):
    assert _arrow_lines(format_source(source)) == _arrow_lines(source)


def _arrow_lines(text: str) -> int:
    """How many tight ``<-`` arrows the text contains, spacing-wise."""
    return text.count("<-")


def test_a_formatted_lambda_still_runs(tmp_path):
    """The end of the chain: the engine has to accept what we wrote out.

    Spacing is the whole distinction, so only loading the formatted file and
    running the predicate proves the arrow survived in the sense that matters.
    """
    from clausal.import_hook import _load_module

    source = (
        "-module(fmt_arrow_probe, [Doubles(A, B)])\n"
        "\n"
        "Doubles(XS, YS) <- (\n"
        "    maplist(((X, Y) <- (Y == X * 2)), XS, YS)\n"
        ")\n"
    )
    path = tmp_path / "fmt_arrow_probe.clausal"
    path.write_text(format_source(source))
    module = _load_module("fmt_arrow_probe", str(path))
    from clausal.logic.variables import Var, deref

    out = Var()
    solutions = list(module.Doubles([1, 2, 3], out))
    assert solutions, "the formatted lambda no longer solves"
