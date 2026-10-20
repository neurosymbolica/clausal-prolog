"""The verification fence: AST equivalence, idempotence, comments-only edits."""

import pytest

from clausal.fmt.verify import (
    FmtIdempotenceError,
    ast_equivalent,
    check_idempotent,
    comments_only_change,
)
from tests._suffix import SEAM


def test_ast_equivalent_ignores_layout_and_comments():
    assert ast_equivalent(
        "p(X) <- (q(X), r(X))\n", "# c\np(X) <- (\n    q(X),\n    r(X)\n)\n"
    )


def test_ast_equivalent_catches_code_change():
    assert not ast_equivalent("p(X) <- (q(X))\n", "p(X) <- (r(X))\n")


def test_ast_equivalent_sees_a_requoted_atom():
    # In the seam ``'f'`` is an atom and ``"f"`` a string; the Python tree
    # is the same Constant, so the quote character is compared from the
    # source itself.  todo/done/fmt-requotes-a-quoted-atom-head-as-a-string-
    # 2026-10-20.md.
    assert not ast_equivalent("'f'(X) <- (q(X))\n", '"f"(X) <- (q(X))\n')
    assert not ast_equivalent("p(X) <- ('=='(X, a))\n", 'p(X) <- ("=="(X, a))\n')
    assert not ast_equivalent("p(X) <- (q(X, 'a'))\n", 'p(X) <- (q(X, "a"))\n')
    assert not ast_equivalent("op(1, 'a'),\n", 'op(1, "a"),\n')
    assert ast_equivalent("p(X) <- (q(X, 'a'))\n", "p(X) <- (\n    q(X, 'a')\n)\n")
    assert ast_equivalent('p(X) <- (q(X, "a"))\n', 'p(X) <- (\n    q(X, "a")\n)\n')


def test_ast_equivalent_sees_a_requoted_concatenation_end():
    # The seam reads both ends of an implicitly concatenated literal.
    assert not ast_equivalent("p(X) <- (q('a' 'b'))\n", "p(X) <- (q('a' \"b\"))\n")


def test_ast_equivalent_ignores_spellings_the_seam_does_not_read():
    # Raw prefixes and triple quotes change no term: the quote character is
    # what the seam reads, nothing else.
    assert ast_equivalent("p(X) <- (q('a'))\n", "p(X) <- (q('''a'''))\n")
    assert ast_equivalent("p(X) <- (q('a'))\n", "p(X) <- (q(r'a'))\n")


def test_a_requoting_formatter_is_refused(monkeypatch):
    # The fence the verifier exists for: a formatter that writes "f" for 'f'
    # changes the program, and ``comments_only_change`` must say so.
    from clausal.fmt import verify as V

    def requoting(source):
        return V.format_source(source).replace("'", '"')

    before = "-private([f(_)])\n'f'(X) <- (q(X))\n"
    after = requoting(before)
    assert after == '-private([f(_)])\n\n"f"(X) <- (\n    q(X)\n)\n'
    assert not ast_equivalent(before, after)
    monkeypatch.setattr(V, "format_source", requoting)
    assert not comments_only_change(before, after)


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
        f"x{SEAM}",
        "# a\np(X) <- (\n    q(X)\n)\n",
        "# a\np(X) <- (\n    q(X),\n    r(X)\n)\n",
    )
    assert f"--- x{SEAM} (before)" in p and f"+++ x{SEAM} (after)" in p
    assert "comments only" in p.lower()
    assert f"x{SEAM}" in p


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


class TestReifiedEqual:
    """The comment-repair fence: reified term structure must match exactly."""

    def test_comment_edits_are_invisible(self):
        from clausal.fmt.verify import reified_equal
        a = "# old note\np(X) <- (\n    q(X)  # trailing\n)\n"
        b = "# reworded note, moved nothing\np(X) <- (\n    q(X)\n)\n"
        assert reified_equal(a, b)

    def test_any_code_change_is_caught(self):
        from clausal.fmt.verify import reified_equal
        a = "p(X) <- (\n    q(X)\n)\n"
        assert not reified_equal(a, "p(X) <- (\n    r(X)\n)\n")
        assert not reified_equal(a, "p(X, Y) <- (\n    q(X)\n)\n")
        assert not reified_equal(a, a + "\nextra(1),\n")

    def test_stronger_than_ast_equivalence_on_the_arrow(self):
        # `<-` vs `< -` are IDENTICAL ASTs; reification reads the spacing.
        # An LLM "comment fix" that de-spaced a lambda arrow must be caught.
        from clausal.fmt.verify import ast_equivalent, reified_equal
        a = "t(B) <- (\n    fold(((X) <- p(X)), B)\n)\n"
        b = "t(B) <- (\n    fold(((X) < - p(X)), B)\n)\n"
        assert ast_equivalent(a, b)          # the weaker fence is blind here
        assert not reified_equal(a, b)       # this one is not

    def test_unparsable_side_compares_unequal(self):
        from clausal.fmt.verify import reified_equal
        assert not reified_equal("p(X) <- (q(X))\n", "p(X) <- (q(X)\n")
