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
here.

v1 does not wrap long goals.  A goal too long for the line stays too long; a
line-width engine is a separate decision from comment survival, and mixing the
two would make every layout bug look like a comment bug.
"""

from __future__ import annotations

import ast

from clausal.fmt.comments import CommentTable, clause_body, goal_sequence

INDENT = "    "


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
        body = clause_body(statement)
        if body is not None:
            self._emit_clause(statement, body)
        else:
            self._write("", _statement_text(statement))
        self._append_trailing(statement)
        self.table.mark_emitted(statement)

    def _emit_clause(self, statement: ast.AST, body: ast.AST) -> None:
        head = ast.unparse(statement.value.left)
        self._write("", f"{head} <- (")
        self._emit_goals(goal_sequence(body), INDENT)
        self._write("", ")")

    def _emit_goals(self, goals: list[ast.AST], indent: str) -> None:
        for index, goal in enumerate(goals):
            last = index == len(goals) - 1
            self._emit_above(goal, indent)
            self._emit_goal(goal, indent, separator="" if last else ",")
            self.table.mark_emitted(goal)

    def _emit_goal(self, goal: ast.AST, indent: str, separator: str) -> None:
        if isinstance(goal, ast.Tuple):
            self._emit_group(goal, indent, separator)
        elif isinstance(goal, ast.BoolOp) and isinstance(goal.op, ast.Or):
            self._emit_or(goal, indent, separator)
        else:
            self._write(indent, ast.unparse(goal) + separator)
            self._append_trailing(goal)

    def _emit_group(self, group: ast.Tuple, indent: str, separator: str) -> None:
        """A nested goal-sequence: its own parenthesised block."""
        self._write(indent, "(")
        self._emit_goals(list(group.elts), indent + INDENT)
        self._write(indent, ")" + separator)
        self._append_trailing(group)

    def _emit_or(self, node: ast.BoolOp, indent: str, separator: str) -> None:
        """An or-block: ``) or (`` joins the alternatives at group indent."""
        for index, value in enumerate(node.values):
            if index:
                self._lines[-1] += " or ("
            else:
                self._write(indent, "(")
            self._emit_goals(goal_sequence(value), indent + INDENT)
            self._write(indent, ")")
        self._lines[-1] += separator
        self._append_trailing(node)


def _statement_text(statement: ast.AST) -> str:
    """A non-clause statement as one line of Clausal source."""
    directive = _directive_operand(statement)
    if directive is not None:
        return "-" + ast.unparse(directive)
    facts = _fact_terms(statement)
    if facts is not None:
        return ", ".join(ast.unparse(term) for term in facts) + ","
    return ast.unparse(statement)


def _directive_operand(statement: ast.AST) -> ast.AST | None:
    """The operand of ``-module(...)``, ``-strict_atoms`` and friends."""
    if (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.UnaryOp)
        and isinstance(statement.value.op, ast.USub)
    ):
        return statement.value.operand
    return None


def _fact_terms(statement: ast.AST) -> list[ast.AST] | None:
    """The terms of a fact statement -- a tuple, i.e. a trailing comma."""
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Tuple):
        return list(statement.value.elts)
    return None


def _fact_functor(statement: ast.AST) -> str | None:
    """The head functor of a single-term fact, for the fact-table rule."""
    terms = _fact_terms(statement)
    if terms is None or len(terms) != 1:
        return None
    term = terms[0]
    if isinstance(term, ast.Call):
        return ast.unparse(term.func)
    return None
