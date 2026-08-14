"""Comment capture for the Clausal formatter.

``.clausal`` source parses under Python's own :mod:`ast` -- the ``<-`` arrow
rides as ``<`` plus unary minus, directives as unary-minus calls -- so the
formatter gets a real tree for free.  What ``ast`` throws away is comments, and
comments are most of what a formatter must not lose.

This module harvests them with :mod:`tokenize` and files them in a side table
keyed by node identity.  Nothing is stuck on the nodes themselves: an
``ast.NodeTransformer`` may rebuild any subtree it likes, and the table's keys
for the untouched parts survive because those node objects survive.

The attachment convention matches how comments are actually written: a comment
is about the thing BELOW it, unless it sits at the end of the line of the node
it comments on.  The line test, not the region test, disambiguates -- a comment
on the same line as the end of a node is that node's trailing comment, never the
next node's above-comment.

Comment loss is a hard error.  :meth:`CommentTable.assert_conserved` raises
:class:`CommentLeakError` for every captured comment that was neither emitted
nor explicitly dropped, so a transform that forgets its comment obligations
fails the run rather than quietly deleting a paragraph of someone's reasoning.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field


class CommentLeakError(Exception):
    """Captured comments that were never emitted or explicitly dropped.

    ``lost`` holds ``(source_line, text)`` pairs so the report names the
    comments by their original position, which is the only handle the author
    has on them once the output no longer contains them.
    """

    def __init__(self, lost: list[tuple[int, str]]):
        self.lost = lost
        detail = "\n".join(f"  line {line}: {text}" for line, text in lost)
        super().__init__(
            f"{len(lost)} comment(s) would be lost by this format run:\n{detail}\n"
            "Every replacement node must call table.move(old, new) or "
            "table.drop(old)."
        )


@dataclass
class _Comment:
    """One captured ``#`` comment and its consumption state."""

    row: int
    col: int
    text: str
    consumed: bool = False


@dataclass
class _Slots:
    """The comments filed against a single node.

    ``above`` keeps its group structure: consecutive comment lines form a
    group, a blank source line ends one.  Multi-paragraph comment blocks come
    back out the way they went in.
    """

    above: list[list[_Comment]] = field(default_factory=list)
    trailing: list[_Comment] = field(default_factory=list)

    def all_comments(self) -> list[_Comment]:
        return [c for group in self.above for c in group] + list(self.trailing)


def _is_clause(stmt: ast.AST) -> bool:
    """Is this statement a clause -- ``head <- ( goal, ... )``?

    The arrow parses as a comparison whose right-hand side is a unary minus:
    ``Expr(Compare(left=head, ops=[Lt], comparators=[UnaryOp(USub, body)]))``.
    """
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Compare)
        and len(stmt.value.ops) == 1
        and isinstance(stmt.value.ops[0], ast.Lt)
        and len(stmt.value.comparators) == 1
        and isinstance(stmt.value.comparators[0], ast.UnaryOp)
        and isinstance(stmt.value.comparators[0].op, ast.USub)
    )


def clause_body(stmt: ast.AST) -> ast.AST | None:
    """The goal-sequence expression of a clause statement, or ``None``."""
    if not _is_clause(stmt):
        return None
    return stmt.value.comparators[0].operand


def goal_sequence(body: ast.AST) -> list[ast.AST]:
    """The goals of a body expression, in order.

    A body with one goal is that goal itself -- no tuple is built for it.
    """
    if isinstance(body, ast.Tuple):
        return list(body.elts)
    return [body]


def _goal_attachment_nodes(body: ast.AST) -> list[ast.AST]:
    """Attachment nodes inside a clause body, recursing into nested groups.

    A nested group -- a parenthesised goal-sequence, or an or-block, which
    parses as ``BoolOp(Or, values=[...])`` -- is itself an attachment node AND
    contributes its elements, so a comment can sit above the group or above any
    goal inside it.
    """
    out: list[ast.AST] = []
    for goal in goal_sequence(body):
        if isinstance(goal, ast.Tuple):
            out.append(goal)
            out.extend(_goal_attachment_nodes(goal))
        elif isinstance(goal, ast.BoolOp):
            out.append(goal)
            for value in goal.values:
                out.extend(_goal_attachment_nodes(value))
        else:
            out.append(goal)
    return out


def attachment_nodes(tree: ast.Module) -> list[ast.AST]:
    """Every node a comment may attach to, in source order.

    Those are the module-level statements -- directives, facts, clauses -- plus
    every goal position inside a clause body.  That is the granularity the
    corpus's comment register actually uses: per-clause headers and per-goal
    anchors.  A comment written anywhere else, say inside one goal's argument
    list, files against the enclosing attachment node instead.
    """
    nodes: list[ast.AST] = []
    for stmt in tree.body:
        nodes.append(stmt)
        body = clause_body(stmt)
        if body is not None:
            nodes.extend(_goal_attachment_nodes(body))
    return sorted(nodes, key=lambda n: (n.lineno, n.col_offset))


class CommentTable:
    """Comments filed by node identity, with a conservation ledger."""

    def __init__(self, module: ast.Module):
        self.module = module
        self._slots: dict[ast.AST, _Slots] = {}
        self._module_above: list[list[_Comment]] = []
        self._module_trailing: list[list[_Comment]] = []
        self._ledger: list[_Comment] = []

    # -- capture ---------------------------------------------------------

    @classmethod
    def capture(cls, source: str) -> tuple[ast.Module, "CommentTable"]:
        """Parse ``source`` and file every comment in it against a node."""
        tree = ast.parse(source)
        table = cls(tree)
        table._fill(source, tree)
        return tree, table

    def _fill(self, source: str, tree: ast.Module) -> None:
        comments = _harvest(source)
        self._ledger = list(comments)
        if not comments:
            return

        nodes = attachment_nodes(tree)
        by_end = sorted(nodes, key=lambda n: (n.end_lineno, n.end_col_offset))

        # Rows that carry nothing: the group separator inside comment blocks.
        blank_rows = {
            row
            for row, line in enumerate(source.splitlines(), start=1)
            if not line.strip()
        }

        runs: dict[ast.AST, list[_Comment]] = {}  # node -> comments above it
        after_last: list[_Comment] = []
        for comment in comments:
            owner = _trailing_owner(by_end, comment)
            if owner is not None:
                self._slot(owner).trailing.append(comment)
                continue
            below = _next_node(nodes, comment.row)
            if below is None:
                after_last.append(comment)
            else:
                runs.setdefault(below, []).append(comment)
        for node, run in runs.items():
            self._file_above(run, node, blank_rows)
        if after_last:
            self._module_trailing = _group(after_last, blank_rows)

    def _file_above(
        self, pending: list[_Comment], node: ast.AST, blank_rows: set[int]
    ) -> None:
        """File the run of comments standing above ``node``.

        For the FIRST node of a file the run may include a detached file
        header.  The group nearest the node is the node's own; anything before
        it is the header, which the formatter emits at the top of the file
        rather than as part of the first statement.
        """
        groups = _group(pending, blank_rows)
        if not groups:
            return
        first_node = self.module.body[0] if self.module.body else None
        if node is first_node and not self._module_above and len(groups) > 1:
            self._module_above = groups[:-1]
            groups = groups[-1:]
        self._slot(node).above.extend(groups)

    def _slot(self, node: ast.AST) -> _Slots:
        return self._slots.setdefault(node, _Slots())

    # -- reading ---------------------------------------------------------

    def above(self, node: ast.AST) -> list[list[str]]:
        """The comment groups standing above ``node``."""
        slots = self._slots.get(node)
        return [[c.text for c in group] for group in slots.above] if slots else []

    def trailing(self, node: ast.AST) -> list[str]:
        """The comments on the same line as the end of ``node``."""
        slots = self._slots.get(node)
        return [c.text for c in slots.trailing] if slots else []

    @property
    def module_above(self) -> list[list[str]]:
        """The file header -- comment groups detached from the first node."""
        return [[c.text for c in group] for group in self._module_above]

    @property
    def module_trailing(self) -> list[str]:
        """Comments after the last node, emitted at end of file."""
        return [c.text for group in self._module_trailing for c in group]

    @property
    def module_trailing_groups(self) -> list[list[str]]:
        return [[c.text for c in group] for group in self._module_trailing]

    def has_comments(self, node: ast.AST) -> bool:
        slots = self._slots.get(node)
        return bool(slots and (slots.above or slots.trailing))

    # -- transform obligations -------------------------------------------

    def move(self, old: ast.AST, new: ast.AST | None) -> None:
        """Transfer ``old``'s comments to ``new``; ``None`` means drop them.

        The old context frames the new content: moved above-comments prepend to
        whatever ``new`` already carries, moved trailing comments append.
        """
        if new is None:
            self.drop(old)
            return
        slots = self._slots.pop(old, None)
        if slots is None:
            return
        target = self._slot(new)
        target.above[:0] = slots.above
        target.trailing.extend(slots.trailing)

    def drop(self, node: ast.AST) -> None:
        """Declare ``node``'s comments obsolete -- an explicit discharge."""
        slots = self._slots.pop(node, None)
        if slots is None:
            return
        for comment in slots.all_comments():
            comment.consumed = True

    def mark_emitted(self, node: ast.AST) -> None:
        """Record that ``node``'s comments reached the output."""
        slots = self._slots.get(node)
        if slots is None:
            return
        for comment in slots.all_comments():
            comment.consumed = True

    def mark_module_edges_emitted(self) -> None:
        for group in self._module_above + self._module_trailing:
            for comment in group:
                comment.consumed = True

    def assert_conserved(self) -> None:
        """Fail unless every captured comment was emitted or dropped."""
        lost = [(c.row, c.text) for c in self._ledger if not c.consumed]
        if lost:
            raise CommentLeakError(lost)


def _harvest(source: str) -> list[_Comment]:
    """Every ``#`` comment in ``source``, in source order."""
    if not source.endswith("\n"):
        source += "\n"
    out: list[_Comment] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            row, col = token.start
            out.append(_Comment(row=row, col=col, text=token.string.rstrip()))
    return out


def _trailing_owner(by_end: list[ast.AST], comment: _Comment) -> ast.AST | None:
    """The node this comment trails, if it sits at the end of that node's line."""
    owner = None
    for node in by_end:
        if node.end_lineno == comment.row and node.end_col_offset <= comment.col:
            owner = node
    return owner


def _next_node(nodes: list[ast.AST], row: int) -> ast.AST | None:
    """The first attachment node beginning below ``row``."""
    for node in nodes:
        if node.lineno > row:
            return node
    return None


def _group(comments: list[_Comment], blank_rows: set[int]) -> list[list[_Comment]]:
    """Split a run of comments into groups on blank source lines."""
    groups: list[list[_Comment]] = []
    previous: _Comment | None = None
    for comment in comments:
        if previous is None or any(
            row in blank_rows for row in range(previous.row + 1, comment.row)
        ):
            groups.append([])
        groups[-1].append(comment)
        previous = comment
    return groups
