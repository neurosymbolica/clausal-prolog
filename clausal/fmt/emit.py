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
import io
import tokenize

from clausal.fmt.comments import (
    CommentTable,
    clause_body,
    directive_list,
    is_clause,
    statement_items,
)

INDENT = "    "

#: One-line renderings past this width explode (directive lists only in v1 --
#: the goal layer stays no-wrap by design; see todo's fmt style questions).
WIDTH = 88


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
        items, comma = statement_items(statement)
        suffix = "," if comma else ""
        if len(items) == 1 and is_clause(items[0]):
            self._emit_clause(items[0], suffix)
        elif (lst := directive_list(statement)) is not None:
            # Before the series branch: a directive parses as one UnaryOp item
            # and would otherwise take the one-line path with its list intact.
            self._emit_directive(statement, lst)
        elif items:
            # A comma-separated series stays on one line: splitting it across
            # lines would end the statement at the first newline and turn one
            # statement into several.
            self._write("", ", ".join(_item_text(item, self.table.arrows) for item in items) + suffix)
        else:
            self._write("", unparse(statement, self.table.arrows))
        self._append_trailing(statement)
        self.table.mark_emitted(statement)

    def _emit_directive(self, statement: ast.AST, lst: ast.List) -> None:
        """A directive with a trailing list: one line while it fits and its
        elements carry no comments; exploded one-element-per-line otherwise.
        A collapsed export list is unreadable and evicts its section comments
        (operator conventions, 2026-08-15 trial); the closing ``])`` sits on
        its own line, last element without a separator, matching the corpus."""
        one_line = unparse(statement, self.table.arrows)
        commented = any(self.table.above(e) or self.table.trailing(e)
                        for e in lst.elts)
        if len(one_line) <= WIDTH and not commented:
            for element in lst.elts:
                self.table.mark_emitted(element)
            self._write("", one_line)
            return
        call = statement.value.operand
        leading = ", ".join(unparse(a, self.table.arrows) for a in call.args[:-1])
        opener = f"-{unparse(call.func, self.table.arrows)}({leading}{', ' if leading else ''}["
        self._write("", opener)
        for i, element in enumerate(lst.elts):
            self._emit_above(element, INDENT)
            separator = "," if i < len(lst.elts) - 1 else ""
            self._write(INDENT, unparse(element, self.table.arrows) + separator)
            self._append_trailing(element)
            self.table.mark_emitted(element)
        self._write("", "])")

    def _emit_clause(self, clause: ast.AST, suffix: str) -> None:
        head = unparse(clause.left, self.table.arrows)
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
            self._write(indent, unparse(goal, self.table.arrows) + separator)
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
    """``ast.unparse`` with the house quote preference applied.

    ``ast.unparse`` writes ``'single'``; the corpus and the surrounding Python
    are written ``"double"``.  Since the formatter re-renders every term, that
    difference would otherwise rewrite the quoting of every string in the
    language on the first run.  Strings that would need escaping to change stay
    exactly as ``ast.unparse`` wrote them.

    ``arrows`` is the CommentTable's arrow ledger: Compare nodes the source
    spells ``<-``.  ``ast.unparse`` would print them ``< -``, which the engine
    reads as a genuine less-than-negative -- an inline lambda silently becomes
    a comparison.  Arrow nodes render ``(left <- operand)``, parenthesised,
    matching the corpus's inline-lambda style."""
    if arrows:
        up = _ArrowUnparser(arrows)
        return _prefer_double_quotes(up.visit(node))
    return _prefer_double_quotes(ast.unparse(node))


class _ArrowUnparser(ast._Unparser):
    """``ast._Unparser`` that preserves source-spelled arrows."""

    # ast._Unparser spawns a bare type(self)() for f-string internals, so
    # arrows must default; an arrow cannot occur inside an f-string anyway.
    def __init__(self, arrows=frozenset()):
        super().__init__()
        self._arrows = arrows

    def visit_Compare(self, node):
        if node not in self._arrows:
            return super().visit_Compare(node)
        # Precedence discipline matters on both sides: the head may be a bare
        # tuple (needs its parens back) and the body re-parses under unary-minus
        # binding — `X <- RESULT is X` would chain into Compare(Lt, Is). The
        # unparser's own precedence machinery decides both.
        precedence = ast._Precedence
        self.write("(")
        self.set_precedence(precedence.CMP.next(), node.left)
        self.traverse(node.left)
        self.write(" <- ")
        operand = node.comparators[0].operand
        self.set_precedence(precedence.FACTOR, operand)
        self.traverse(operand)
        self.write(")")


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
