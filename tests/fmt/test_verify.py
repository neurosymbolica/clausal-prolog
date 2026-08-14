"""The verification fence: AST equivalence, idempotence, comments-only edits."""

import pytest

from clausal.fmt.verify import (
    FmtIdempotenceError,
    ast_equivalent,
    check_idempotent,
    comments_only_change,
)


def test_ast_equivalent_ignores_layout_and_comments():
    assert ast_equivalent(
        "p(X) <- (q(X), r(X))\n", "# c\np(X) <- (\n    q(X),\n    r(X)\n)\n"
    )


def test_ast_equivalent_catches_code_change():
    assert not ast_equivalent("p(X) <- (q(X))\n", "p(X) <- (r(X))\n")


def test_check_idempotent_passes_on_formatted_source():
    check_idempotent("p(X) <- (q(X), r(X))\n")


def test_check_idempotent_reports_the_unstable_source(monkeypatch):
    from clausal.fmt import verify as V

    unstable = iter(["one\n", "two\n"])
    monkeypatch.setattr(V, "format_source", lambda src: next(unstable))
    with pytest.raises(FmtIdempotenceError):
        check_idempotent("rate(1),\n")


def test_comments_only_change_accepts_comment_edit():
    before = "# old wording\np(X) <- (\n    q(X)\n)\n"
    after = "# new wording\np(X) <- (\n    q(X)\n)\n"
    assert comments_only_change(before, after)


def test_comments_only_change_rejects_code_edit():
    before = "p(X) <- (\n    q(X)\n)\n"
    after = "p(X) <- (\n    r(X)\n)\n"
    assert not comments_only_change(before, after)


def test_comments_only_change_rejects_unformatted_result():
    before = "# a\np(X) <- (\n    q(X)\n)\n"
    after = "# a\np(X) <- (q(X))\n"  # same code, but not fmt-stable
    assert not comments_only_change(before, after)


def test_comments_only_change_allows_a_deleted_comment():
    # The fence guards the CODE.  A repair pass that deletes a comment made a
    # comment change, which is the thing it is licensed to do; whether the
    # deletion was wise is a review question, not a mechanical one.
    before = "# a\np(X) <- (\n    q(X)\n)\n"
    after = "p(X) <- (\n    q(X)\n)\n"
    assert comments_only_change(before, after)


def test_comments_only_change_rejects_unparsable_result():
    assert not comments_only_change("rate(1),\n", "rate(1,\n")


def test_build_repair_prompt_contains_diff_and_rules():
    from clausal.fmt.repair_prompt import build_repair_prompt

    p = build_repair_prompt(
        "x.clausal",
        "# a\np(X) <- (\n    q(X)\n)\n",
        "# a\np(X) <- (\n    q(X),\n    r(X)\n)\n",
    )
    assert "--- x.clausal (before)" in p and "+++ x.clausal (after)" in p
    assert "comments only" in p.lower()
    assert "x.clausal" in p


def test_accept_repair_rejects_code_edits():
    from clausal.fmt.repair_prompt import RepairRejected, accept_repair

    pre = "# a\np(X) <- (\n    q(X)\n)\n"
    good = "# better wording\np(X) <- (\n    q(X)\n)\n"
    bad = "# a\np(X) <- (\n    r(X)\n)\n"
    assert accept_repair(pre, good) == good
    with pytest.raises(RepairRejected):
        accept_repair(pre, bad)


def test_accept_repair_rejects_a_reformatted_pass():
    from clausal.fmt.repair_prompt import RepairRejected, accept_repair

    pre = "# a\np(X) <- (\n    q(X)\n)\n"
    reflowed = "# a\np(X) <- (q(X))\n"  # same code, layout no longer canonical
    with pytest.raises(RepairRejected):
        accept_repair(pre, reflowed)
