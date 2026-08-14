"""What the formatter and its downstream passes must prove.

Three checks, each mechanical:

* :func:`ast_equivalent` -- the code did not change.  Positions are ignored,
  so layout and comments are invisible to it, which is exactly the point.
* :func:`check_idempotent` -- formatting a formatted file is a no-op.  A
  formatter that keeps changing its mind cannot be run in a pre-commit hook or
  a pipeline without churning every file it touches.
* :func:`comments_only_change` -- the fence for the LLM comment-repair pass:
  the tree is unchanged AND the result is already in canonical form, so a pass
  that edited code, or that reformatted while it was in there, is caught
  wholesale rather than reviewed line by line.
"""

from __future__ import annotations

import ast
import difflib

from clausal.fmt.comments import CommentLeakError
from clausal.fmt.emit import format_source


class FmtIdempotenceError(Exception):
    """``fmt(fmt(x)) != fmt(x)`` -- the formatter is not stable on this source."""

    def __init__(self, diff: str):
        self.diff = diff
        super().__init__(f"formatting is not idempotent:\n{diff}")


def _parse(source: str | ast.AST) -> ast.AST:
    return source if isinstance(source, ast.AST) else ast.parse(source)


def ast_equivalent(a: str | ast.AST, b: str | ast.AST) -> bool:
    """Do these two sources (or trees) hold the same code?"""
    try:
        left, right = _parse(a), _parse(b)
    except SyntaxError:
        return False
    return ast.dump(left, include_attributes=False) == ast.dump(
        right, include_attributes=False
    )


def check_idempotent(source: str) -> None:
    """Raise :class:`FmtIdempotenceError` unless a second pass changes nothing."""
    once = format_source(source)
    twice = format_source(once)
    if once != twice:
        raise FmtIdempotenceError(unified_diff(once, twice, "pass 1", "pass 2"))


def comments_only_change(before: str, after: str) -> bool:
    """Did ``after`` change nothing but comments, and stay canonically formatted?"""
    if not ast_equivalent(before, after):
        return False
    try:
        return format_source(after) == after
    except (SyntaxError, CommentLeakError):
        return False


def unified_diff(before: str, after: str, from_label: str, to_label: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=from_label,
            tofile=to_label,
        )
    )
