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

The table carries one other thing the tree cannot hold: :attr:`CommentTable
.arrows`, the set of ``Compare(Lt, [UnaryOp(USub, ...)])`` nodes that were
written as ``<-`` rather than ``< -``.  Those two spellings parse identically
and mean different things -- a clause or lambda arrow versus a less-than
against a negation -- and the engine reads the difference from the source
spacing.  Since that is not in the AST, it has to be captured alongside the
comments, for the same reason and by the same means.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field

from clausal.templating.term_rewriting import _is_arrow_adjacent


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


def is_clause(expression: ast.AST) -> bool:
    """Is this expression a clause -- ``head <- ( goal, ... )``?

    The arrow parses as a comparison whose right-hand side is a unary minus:
    ``Compare(left=head, ops=[Lt], comparators=[UnaryOp(USub, body)])``.
    """
    return (
        isinstance(expression, ast.Compare)
        and len(expression.ops) == 1
        and isinstance(expression.ops[0], ast.Lt)
        and len(expression.comparators) == 1
        and isinstance(expression.comparators[0], ast.UnaryOp)
        and isinstance(expression.comparators[0].op, ast.USub)
    )


def arrow_candidates(node: ast.AST) -> list[ast.AST]:
    """Every arrow-SHAPED node in ``node``'s subtree, in a stable order.

    Shape is all the tree offers: ``head <- body`` and ``head < -body`` are the
    same nodes.  The order is :func:`ast.walk`'s, which depends only on the
    structure -- so the list taken from a node and the list taken from a
    re-parse of that node's rendered text correspond element by element, which
    is how emission finds where to write a tight arrow.
    """
    return [child for child in ast.walk(node) if is_clause(child)]


def arrow_nodes(tree: ast.Module, source: str) -> set[ast.AST]:
    """The arrow-shaped nodes in ``tree`` that ``source`` spells ``<-``.

    The adjacency test is the engine's own :func:`_is_arrow_adjacent`, imported
    rather than reimplemented: a formatter that disagreed with the loader about
    what an arrow is would rewrite meaning while preserving the tree.
    """
    lines = source.splitlines()
    found = set()
    for node in arrow_candidates(tree):
        try:
            adjacent = _is_arrow_adjacent(node.left, node.comparators[0], lines)
        except ValueError:  # a node with no source position: not from this text
            continue
        if adjacent:
            found.add(node)
    return found


def statement_items(stmt: ast.AST) -> tuple[list[ast.AST], bool]:
    """The comma-separated items of a statement, and its trailing comma.

    A statement may be one clause, one term, or a comma-separated series of
    either, and it may end in a comma -- which is how a fact is written.  That
    comma makes the statement a tuple, so ``Head <- (...)`` and
    ``Head <- (...),`` are DIFFERENT trees holding the same clause: the comma
    has to be read here and written back out, not inferred from the shape.
    """
    if not isinstance(stmt, ast.Expr):
        return [], False
    if isinstance(stmt.value, ast.Tuple):
        return list(stmt.value.elts), True
    return [stmt.value], False


def clause_body(item: ast.AST) -> ast.AST | None:
    """The goal-sequence expression of a clause, or ``None``."""
    if not is_clause(item):
        return None
    return item.comparators[0].operand


def directive_list(stmt: ast.AST) -> ast.List | None:
    """The trailing ``List`` argument of a directive statement, or ``None``.

    A directive is ``Expr(UnaryOp(USub, Call))`` -- ``-module(m, [...])``,
    ``-import_from(vocab, [...])``, ``-private([...])``.  Its list elements are
    attachment nodes: the corpus writes section comments against individual
    export-list entries, and those must ride their entries through an
    explosion (emit) rather than evict to above the whole statement."""
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.UnaryOp)
            and isinstance(stmt.value.op, ast.USub)
            and isinstance(stmt.value.operand, ast.Call)):
        return None
    args = stmt.value.operand.args
    if args and isinstance(args[-1], ast.List):
        return args[-1]
    return None


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
        lst = directive_list(stmt)
        if lst is not None:
            nodes.extend(lst.elts)
            continue
        items, _comma = statement_items(stmt)
        if len(items) != 1:
            continue  # a comma-separated series is written back on one line
        body = clause_body(items[0])
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
        #: Compare nodes the source spells as the arrow ``<-`` (vs a genuine
        #: ``A < -B``); filled by capture, consulted by the emitter's unparse.
        #: A transform that BUILDS an arrow node must add it here.
        self.arrows: set[ast.AST] = set()

    # -- capture ---------------------------------------------------------

    @classmethod
    def capture(cls, source: str) -> tuple[ast.Module, "CommentTable"]:
        """Parse ``source`` and file every comment in it against a node."""
        tree = ast.parse(source)
        table = cls(tree)
        table.arrows = arrow_nodes(tree, source)
        table._fill(source, tree)
        return tree, table

    def _fill(self, source: str, tree: ast.Module) -> None:
        comments = _harvest(source)
        self._ledger = list(comments)
        if not comments:
            return

        nodes = attachment_nodes(tree)
        by_end = sorted(nodes, key=lambda n: (n.end_lineno, n.end_col_offset))

        runs: dict[ast.AST, list[_Comment]] = {}  # node -> comments above it
        after_last: list[_Comment] = []
        for comment in comments:
            owner = _trailing_owner(by_end, comment)
            if owner is not None:
                self._slot(owner).trailing.append(comment)
                continue
            owner = _above_owner(nodes, comment)
            if owner is None:
                after_last.append(comment)
            else:
                runs.setdefault(owner, []).append(comment)
        for node, run in runs.items():
            self._file_above(run, node)
        if after_last:
            self._module_trailing = _group(after_last)

    def _file_above(self, pending: list[_Comment], node: ast.AST) -> None:
        """File the run of comments standing above ``node``.

        For the FIRST node of a file the run may include a detached file
        header.  The group nearest the node is the node's own; anything before
        it is the header, which the formatter emits at the top of the file
        rather than as part of the first statement.
        """
        groups = _group(pending)
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

    def annotate(self, node: ast.AST, suffix: str) -> None:
        """Append ``suffix`` to every comment filed against ``node``.

        For a transform relocating comments whose subject no longer exists:
        the marker tells the comment-repair pass to scrutinize the wording.
        Above groups are marked on their last line only -- one flag per
        paragraph, not per line.
        """
        slots = self._slots.get(node)
        if slots is None:
            return
        for group in slots.above:
            if group:
                group[-1].text += suffix
        for comment in slots.trailing:
            comment.text += suffix

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


def _above_owner(nodes: list[ast.AST], comment: _Comment) -> ast.AST | None:
    """The node a standalone comment belongs above, or ``None`` at end of file.

    Normally that is the next node down the page -- a comment is about the
    thing below it.  The exception is a comment written INSIDE a node that the
    formatter re-renders as one line, such as a note against one entry of a
    multi-line ``-module([...])`` list: there is no line left to sit on, and
    the next node down the page belongs to a different statement entirely, so
    the comment files above the statement it was written in.
    """
    below = _next_node(nodes, comment.row)
    enclosing = _enclosing_node(nodes, comment.row)
    if enclosing is not None and (below is None or below.end_lineno > enclosing.end_lineno):
        return enclosing
    return below


def _next_node(nodes: list[ast.AST], row: int) -> ast.AST | None:
    """The first attachment node beginning below ``row``."""
    for node in nodes:
        if node.lineno > row:
            return node
    return None


def _enclosing_node(nodes: list[ast.AST], row: int) -> ast.AST | None:
    """The innermost attachment node whose span contains ``row``."""
    enclosing = None
    for node in nodes:  # source order, so the last match is the innermost
        if node.lineno <= row <= node.end_lineno:
            enclosing = node
    return enclosing


def _group(comments: list[_Comment]) -> list[list[_Comment]]:
    """Split a run of comments into groups wherever a line interrupts them.

    Consecutive comment lines are one group; anything in between -- a blank
    line, or code the formatter re-rendered elsewhere -- ends it.  That is what
    keeps a multi-paragraph comment block from being welded into one paragraph.
    """
    groups: list[list[_Comment]] = []
    previous: _Comment | None = None
    for comment in comments:
        if previous is None or comment.row != previous.row + 1:
            groups.append([])
        groups[-1].append(comment)
        previous = comment
    return groups
