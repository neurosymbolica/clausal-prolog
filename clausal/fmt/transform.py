"""The transform contract: whoever replaces a node owns its comments.

A rewrite rule -- lambda elimination, a head fold, a tell-don't-ask conversion
-- builds new nodes where it fires and leaves everything else alone.  The
untouched subtrees keep their original node objects, so their comments are
still filed against them; the REPLACED node's comments are the open question,
and the transform is the only party that knows the answer.  Only it knows
whether the deleted goal's anchor comment now belongs to the folded head, or
describes something that no longer exists.

So the contract is one call.  Use :meth:`ClausalTransformer.replace`, or call
``table.move(old, new)`` / ``table.move(old, None)`` directly.  Skip it and the
format run fails with :class:`~clausal.fmt.comments.CommentLeakError` naming
the comments you would have dropped -- there is no reattachment heuristic and
no warning mode, because a formatter that guesses is a formatter nobody can
trust with a file they have not read.
"""

from __future__ import annotations

import ast

from clausal.fmt.comments import CommentTable


class ClausalTransformer(ast.NodeTransformer):
    """An ``ast.NodeTransformer`` that carries the comment table with it."""

    def __init__(self, table: CommentTable):
        self.comments = table

    def replace(self, old: ast.AST, new: ast.AST | None) -> ast.AST | None:
        """Replace ``old`` with ``new``, moving the comments across.

        ``new=None`` deletes the node and declares its comments obsolete --
        the explicit drop, which is a decision rather than an oversight.
        """
        self.comments.move(old, new)
        return new
