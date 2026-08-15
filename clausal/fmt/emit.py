"""Emission: the formatter is the sole layout authority.

The emitter never consults ``lineno``/``col_offset``.  The source's own layout
has no vote in the output -- it decided nothing but where the comments were,
and capture already extracted that.  Everything else the emitter renders from
structure and from the house style:

* one blank line between top-level statements, except between consecutive
  one-line facts with the same head functor, which form a table;
* comment groups above the node they belong to, one blank line between groups;
* trailing comments two spaces after the node's last line;
* one goal per line inside a clause body, closing paren on its own line.

Goal leaves are rendered by :func:`ast.unparse`, which is the reason the whole
approach is cheap: Clausal terms ARE Python expressions, so the stdlib already
knows how to write them back out.  What it does not know is Clausal's statement
shapes -- ``head <- (...)`` and the trailing-comma fact -- so those are written
here.  Nor does it know that ``<-`` is one token: it writes every such node as
``< -``, which is a comparison, so an inline lambda inside a goal would decay
into a less-than.  Emission repairs exactly the nodes the capture-time arrow
ledger vouches for, and leaves every other ``< -`` alone.

v1 does not wrap long goals.  A goal too long for the line stays too long; a
line-width engine is a separate decision from comment survival, and mixing the
two would make every layout bug look like a comment bug.
"""

from __future__ import annotations

import ast
import io
import tokenize

from clausal.fmt.comments import (
    CommentTable,
    arrow_candidates,
    clause_body,
    is_clause,
    statement_items,
)

INDENT = "    "


class ArrowRenderError(Exception):
    """An arrow could not be written as an arrow.

    ``<-`` and ``< -`` are one tree and two programs, so a spelling the
    emitter cannot place is a meaning it cannot preserve -- reported rather
    than written out wrong.
    """


def format_source(source: str, table_and_tree: tuple | None = None) -> str:
    """Format ``source``, or an already-captured ``(tree, table)`` pair."""
    if table_and_tree is None:
        tree, table = CommentTable.capture(source)
    else:
        tree, table = table_and_tree
    return format_tree(tree, table)


def format_tree(tree: ast.Module, table: CommentTable) -> str:
    """Emit an already-captured (and possibly transformed) tree.

    Attachment positions are derived from the tree in front of the emitter, not
    from the one that was captured, so nodes a transform built are rendered
    like any other -- they simply have no comments of their own unless a
    transform moved some onto them.
    """
    out = Emitter(table).emit_module(tree)
    table.assert_conserved()
    return out


class Emitter:
    """Renders a module to text, consuming the comment table as it goes."""

    def __init__(self, table: CommentTable):
        self.table = table
        self._lines: list[str] = []

    # -- output primitives -----------------------------------------------

    def _write(self, indent: str, text: str) -> None:
        self._lines.append(f"{indent}{text}" if text else "")

    def _blank(self) -> None:
        """One blank line -- never two, never one at the top of the file."""
        if self._lines and self._lines[-1] != "":
            self._lines.append("")

    def _append_trailing(self, node: ast.AST) -> None:
        trailing = self.table.trailing(node)
        if trailing and self._lines:
            self._lines[-1] += "  " + "  ".join(trailing)

    def _render(self, node: ast.AST) -> str:
        """One term, house-quoted, with its registered arrows written tight."""
        return unparse(node, self.table.arrows)

    def _emit_above(self, node: ast.AST, indent: str) -> None:
        for index, group in enumerate(self.table.above(node)):
            if index:
                self._blank()
            for text in group:
                self._write(indent, text)

    def _emit_comment_groups(self, groups: list[list[str]], indent: str) -> None:
        for index, group in enumerate(groups):
            if index:
                self._blank()
            for text in group:
                self._write(indent, text)

    # -- module ----------------------------------------------------------

    def emit_module(self, tree: ast.Module) -> str:
        header = self.table.module_above
        if header:
            self._emit_comment_groups(header, "")
            if tree.body:
                self._blank()

        previous = None
        for statement in tree.body:
            if previous is not None and not self._tabled_with(previous, statement):
                self._blank()
            self.emit_statement(statement)
            previous = statement

        footer = self.table.module_trailing_groups
        if footer:
            self._blank()
            self._emit_comment_groups(footer, "")
        self.table.mark_module_edges_emitted()

        while self._lines and self._lines[-1] == "":
            self._lines.pop()
        return "".join(line + "\n" for line in self._lines)

    def _tabled_with(self, previous: ast.AST, statement: ast.AST) -> bool:
        """Do these two statements form a fact table -- no blank between?

        Consecutive one-line facts with the same head functor are a table, the
        way a rate schedule or a lookup of bands is written.  A comment above
        the second one means the author was sectioning the table, so the blank
        line comes back.
        """
        if self.table.above(statement):
            return False
        functor = _fact_functor(previous)
        return functor is not None and functor == _fact_functor(statement)

    # -- statements ------------------------------------------------------

    def emit_statement(self, statement: ast.AST) -> None:
        self._emit_above(statement, "")
        items, comma = statement_items(statement)
        suffix = "," if comma else ""
        if len(items) == 1 and is_clause(items[0]):
            self._emit_clause(items[0], suffix)
        elif items:
            # A comma-separated series stays on one line: splitting it across
            # lines would end the statement at the first newline and turn one
            # statement into several.
            rendered = ", ".join(_item_text(item, self.table.arrows) for item in items)
            self._write("", rendered + suffix)
        else:
            self._write("", self._render(statement))
        self._append_trailing(statement)
        self.table.mark_emitted(statement)

    def _emit_clause(self, clause: ast.AST, suffix: str) -> None:
        head = self._render(clause.left)
        self._write("", f"{head} <- (")
        self._emit_goals(*_goals_of(clause_body(clause)), INDENT)
        self._write("", ")" + suffix)

    def _emit_goals(
        self, goals: list[ast.AST], final_comma: bool, indent: str
    ) -> None:
        for index, goal in enumerate(goals):
            last = index == len(goals) - 1
            self._emit_above(goal, indent)
            separator = ("," if final_comma else "") if last else ","
            self._emit_goal(goal, indent, separator)
            self.table.mark_emitted(goal)

    def _emit_goal(self, goal: ast.AST, indent: str, separator: str) -> None:
        if isinstance(goal, ast.Tuple):
            self._emit_group(goal, indent, separator)
        elif isinstance(goal, ast.BoolOp) and isinstance(goal.op, ast.Or):
            self._emit_or(goal, indent, separator)
        else:
            self._write(indent, self._render(goal) + separator)
            self._append_trailing(goal)

    def _emit_group(self, group: ast.Tuple, indent: str, separator: str) -> None:
        """A nested goal-sequence: its own parenthesised block."""
        self._write(indent, "(")
        self._emit_goals(*_goals_of(group), indent + INDENT)
        self._write(indent, ")" + separator)
        self._append_trailing(group)

    def _emit_or(self, node: ast.BoolOp, indent: str, separator: str) -> None:
        """An or-block: ``) or (`` joins the alternatives at group indent."""
        for index, value in enumerate(node.values):
            if index:
                self._lines[-1] += " or ("
            else:
                self._write(indent, "(")
            self._emit_goals(*_goals_of(value), indent + INDENT)
            self._write(indent, ")")
        self._lines[-1] += separator
        self._append_trailing(node)


def _goals_of(body: ast.AST) -> tuple[list[ast.AST], bool]:
    """The goals of a body or group, and whether to keep a final comma.

    ``(g,)`` is a one-element tuple and ``(g)`` is just ``g``: the comma is
    load-bearing punctuation in the one-goal case, not decoration, so dropping
    it would change the tree.  With two or more goals the comma is optional and
    the house style leaves it off.
    """
    if isinstance(body, ast.Tuple):
        return list(body.elts), len(body.elts) == 1
    return [body], False


def unparse(node: ast.AST, arrows: set | frozenset = frozenset()) -> str:
    """``ast.unparse`` with the house quote preference and the arrows restored.

    ``ast.unparse`` writes ``'single'``; the corpus and the surrounding Python
    are written ``"double"``.  Since the formatter re-renders every term, that
    difference would otherwise rewrite the quoting of every string in the
    language on the first run.  Strings that would need escaping to change stay
    exactly as ``ast.unparse`` wrote them.

    ``arrows`` is the ledger: the nodes in it are written ``<-``, and every
    other arrow-shaped node keeps the spaced ``< -`` that means less-than.
    """
    return _tighten_arrows(_prefer_double_quotes(ast.unparse(node)), node, arrows)


def _tighten_arrows(text: str, node: ast.AST, arrows: set | frozenset) -> str:
    """Rewrite ``< -`` to ``<-`` for the ledger's nodes, and only those.

    The rendered text is re-parsed to find out WHERE each arrow landed:
    ``ast.unparse`` reports no positions, and the node's own positions describe
    the source it came from, not the line being written.  Structure survives
    the round trip, so the arrow-shaped nodes of the re-parse correspond one
    for one with the node's own, and the ledger's membership carries across by
    index.

    The arithmetic runs on BYTES.  ``col_offset`` counts utf-8 bytes, not
    characters, so a non-ascii character earlier on the line shifts every
    character-based index past the ``-`` -- and this function splices at that
    index, so it would silently eat source instead of failing.  The engine's
    own adjacency test encodes for the same reason.

    Anything that would leave a registered arrow spelled ``< -`` raises.  That
    spelling is a comparison, so returning it quietly would change the program
    -- the same class of loss that comment conservation refuses to make quiet.
    """
    candidates = arrow_candidates(node)
    marked = [index for index, child in enumerate(candidates) if child in arrows]
    if not marked:
        return text
    try:
        reparsed = arrow_candidates(ast.parse(text))
    except SyntaxError as error:  # pragma: no cover - unparse emits parsable text
        raise ArrowRenderError(f"cannot re-parse rendered term: {text!r}") from error
    if len(reparsed) != len(candidates):
        raise ArrowRenderError(
            f"{len(candidates)} arrow-shaped nodes went in and {len(reparsed)} "
            f"came back out of {text!r}: the arrows cannot be located"
        )

    raw = text.encode("utf-8")
    starts, running = [], 0
    for line in raw.splitlines(keepends=True):
        starts.append(running)
        running += len(line)
    edits = []
    for index in marked:
        usub = reparsed[index].comparators[0]
        minus = starts[usub.lineno - 1] + usub.col_offset
        opening = raw.rfind(b"<", 0, minus)
        if opening == -1:  # pragma: no cover - an arrow always has its '<'
            raise ArrowRenderError(
                f"no '<' before the arrow at byte {minus} of {text!r}"
            )
        edits.append((opening, minus + 1))
    for opening, end in sorted(edits, reverse=True):
        raw = raw[:opening] + b"<- " + raw[end:]
    return raw.decode("utf-8")


def _prefer_double_quotes(text: str) -> str:
    """Re-quote single-quoted string literals where that costs no escapes."""
    if "'" not in text:
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return text
    lines = text.splitlines(keepends=True)
    edits = []
    for token in tokens:
        if token.type != tokenize.STRING or token.start[0] != token.end[0]:
            continue
        requoted = _requote(token.string)
        if requoted != token.string:
            edits.append((token.start, token.end, requoted))
    for (row, start), (_end_row, end), replacement in reversed(edits):
        line = lines[row - 1]
        lines[row - 1] = line[:start] + replacement + line[end:]
    return "".join(lines)


def _requote(literal: str) -> str:
    """``'text'`` -> ``"text"`` when the body holds no quote and no backslash."""
    prefix = literal[: len(literal) - len(literal.lstrip("bBfFrRuU"))]
    rest = literal[len(prefix) :]
    for quote in ("'''", "'"):
        if rest.startswith(quote) and rest.endswith(quote) and len(rest) >= 2 * len(quote):
            body = rest[len(quote) : -len(quote)]
            if '"' in body or "\\" in body:
                return literal
            double = '"' * len(quote)
            return f"{prefix}{double}{body}{double}"
    return literal


def _item_text(item: ast.AST, arrows: set | frozenset = frozenset()) -> str:
    """One item of a comma-separated statement, on one line.

    A clause in that position renders inline -- ``head <- (g1, g2)`` -- because
    the series has to stay on a single line to remain a single statement.
    """
    body = clause_body(item)
    if body is None:
        return unparse(item, arrows)
    goals, comma = _goals_of(body)
    rendered = ", ".join(unparse(goal, arrows) for goal in goals)
    return f"{unparse(item.left, arrows)} <- ({rendered}{',' if comma else ''})"


def _fact_functor(statement: ast.AST) -> str | None:
    """The head functor of a single-term fact, for the fact-table rule."""
    items, comma = statement_items(statement)
    if not comma or len(items) != 1:
        return None
    term = items[0]
    if isinstance(term, ast.Call):
        return unparse(term.func)
    return None
