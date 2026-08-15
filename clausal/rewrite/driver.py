"""Apply Clausal rewrite rules to a source file, conserving comments.

Per clause: reify it -- with the ORIGINAL source segment, so the ``<-`` arrows
inside it are read as arrows -- ask each loaded rule module for a replacement,
splice that replacement into the tree the formatter captured, repeat to a
fixpoint, and emit the whole file through :mod:`clausal.fmt`.

The splice is where the comments survive.  Goals the rule kept are matched to
the goals it was given, in order and by reified equality, and the ORIGINAL
``ast`` node is reused for each -- so a comment above or beside such a goal was
never attached to anything that moved.  A goal the rule dropped has its
comments moved above the clause, which is the one place they are certain to
still make sense.  A goal the rule INVENTED has no node to reuse and no comment
story, so the driver refuses rather than guess.

Two things are registered rather than inferred.  A rebuilt clause arrow goes
into the formatter's arrow ledger, because ``head <- body`` and ``head < -body``
are the same tree and only the ledger knows which one this is.  And a rewritten
head is rendered by :func:`clausal.reflection.render_ast`, whose output is
checked for the lambda sentinel that renderer uses -- a head carrying one would
emit corrupt source, and no shipped rule can produce it.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import os

from clausal.fmt.comments import (
    CommentTable,
    clause_body,
    goal_sequence,
    is_clause,
    statement_items,
)
from clausal.fmt.emit import format_source
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var
from clausal.reflection import ReifyError, reify_ast, render_ast

FIXPOINT_BOUND = 20

_LAMBDA_SENTINEL = "_LAMBDA_ARROW"

_module_counter = itertools.count()
_loaded: dict[tuple[str, float], object] = {}


class RewriteError(Exception):
    """A rule set misbehaved -- non-termination, or a result that cannot be
    spliced without inventing source the driver has no comment story for."""


@dataclasses.dataclass
class RewriteResult:
    """``text`` is the formatted output; ``fired`` is what happened.

    Each entry of ``fired`` is ``(position, rule)``, where ``position`` is the
    rewritten statement's span in the ORIGINAL file --
    ``(lineno, col_offset, end_lineno, end_col_offset)`` -- and ``rule`` names
    the rule module that fired.  A clause folded twice appears twice.
    """

    text: str
    fired: list


def load_rules(paths):
    """Load rule modules, newest content wins; returns ``[(name, module)]``.

    Loading is cached on path and mtime: a rewrite run asks the same rules
    about every clause in a file, and a rule module reloaded per clause would
    be both slow and a fresh set of module-scoped names each time.
    """
    loaded = []
    for path in paths:
        path = str(path)
        key = (path, os.path.getmtime(path))
        module = _loaded.get(key)
        if module is None:
            name = f"_rewrite_rules_{next(_module_counter)}"
            module = _load_module(name, path).__dict__["$module"]
            _loaded[key] = module
        loaded.append((path, module))
    return loaded


def rewrite_source(source, rule_paths):
    """Rewrite every clause of ``source`` to a fixpoint, then format it."""
    rules = load_rules(rule_paths)
    tree, table = CommentTable.capture(source)
    fired = []
    for index, statement in enumerate(tree.body):
        items, _comma = statement_items(statement)
        if len(items) != 1 or not is_clause(items[0]):
            continue
        segment = ast.get_source_segment(source, statement)
        try:
            reified = reify_ast(statement, source=segment)
        except (ReifyError, SyntaxError):
            # A shape reification does not model is a shape the rules cannot
            # have an opinion about.  Leaving it byte-stable is the honest
            # answer; refusing the whole file would not be.
            continue
        position = _position(statement)
        current = statement
        for round_number in itertools.count():
            hit = _first_rewrite(rules, reified)
            if hit is None:
                break
            replacement, rule = hit
            if round_number == FIXPOINT_BOUND:
                raise RewriteError(
                    f"{rule} was still firing after {FIXPOINT_BOUND} rounds "
                    f"at {position}: the rule set does not reach a fixpoint"
                )
            current = _splice(table, current, reified, replacement, position)
            fired.append((position, rule))
            reified = replacement
        tree.body[index] = current
    return RewriteResult(text=format_source(source, (tree, table)), fired=fired)


def _position(statement):
    return (
        statement.lineno,
        statement.col_offset,
        statement.end_lineno,
        statement.end_col_offset,
    )


def _first_rewrite(rules, reified_clause):
    """The first rule with something to say about this clause."""
    for rule, module in rules:
        out = Var()
        for _ in call("RewriteClause", reified_clause, out, module=module):
            return _deref_walk(out), rule
    return None


def _splice(table, old_statement, reified_in, reified_out, position):
    """Build the replacement statement, reusing every matched goal's node."""
    old_goals = _top_level_goal_nodes(old_statement)
    if len(old_goals) != len(reified_in.goals):
        raise RewriteError(
            f"goal correspondence lost at {position}: {len(old_goals)} nodes "
            f"against {len(reified_in.goals)} reified goals"
        )

    consumed = [False] * len(reified_in.goals)
    new_goals = []
    cursor = 0
    for out_goal in reified_out.goals:
        matched = _match(reified_in.goals, consumed, cursor, out_goal)
        if matched is None:
            raise RewriteError(
                f"cannot splice the result at {position}: the rule produced a "
                f"goal that was not in the clause ({out_goal!r}), and a goal "
                f"with no original has no node to reuse and no comments to "
                f"inherit"
            )
        consumed[matched] = True
        cursor = matched + 1
        new_goals.append(old_goals[matched])

    if reified_out.head == reified_in.head:
        head_node = _head_node(old_statement)
    else:
        head_node = _render_head(reified_out.head, position)

    new_statement = _build_statement(old_statement, head_node, new_goals, table)

    # The statement's own comments ride across.  Matched goals kept their
    # nodes, so their comments never moved at all; a dropped goal's comments
    # move up to the clause.
    table.move(old_statement, new_statement)
    for index, was_consumed in enumerate(consumed):
        if not was_consumed:
            table.move(old_goals[index], new_statement)
    return new_statement


def _match(in_goals, consumed, cursor, out_goal):
    """The first unconsumed input goal at or after ``cursor`` equal to this one."""
    for index in range(cursor, len(in_goals)):
        if not consumed[index] and in_goals[index] == out_goal:
            return index
    return None


def _top_level_goal_nodes(statement):
    """The goal nodes of a clause statement -- none, if it is now a fact."""
    items, _comma = statement_items(statement)
    body = clause_body(items[0]) if items else None
    return [] if body is None else goal_sequence(body)


def _head_node(statement):
    items, _comma = statement_items(statement)
    return items[0].left if is_clause(items[0]) else items[0]


def _render_head(head, position):
    node = render_ast(head)
    if _LAMBDA_SENTINEL in ast.unparse(node):
        raise RewriteError(
            f"the rewritten head at {position} contains a lambda, which the "
            f"renderer marks with a sentinel this driver cannot strip"
        )
    return node


def _build_statement(old_statement, head_node, goal_nodes, table):
    """Rebuild ``head <- (goals)``, or the fact an emptied body leaves behind.

    The statement's own trailing comma is preserved, and the arrow this builds
    is registered: it is an arrow because of what it means here, and nothing in
    the tree it is spliced into would say so.
    """
    if not goal_nodes:
        # A fact IS the trailing comma: `p(5)` alone is an expression.
        return ast.fix_missing_locations(
            ast.Expr(value=ast.Tuple(elts=[head_node], ctx=ast.Load()))
        )
    body = goal_nodes[0] if len(goal_nodes) == 1 else ast.Tuple(
        elts=goal_nodes, ctx=ast.Load()
    )
    arrow = ast.Compare(
        left=head_node,
        ops=[ast.Lt()],
        comparators=[ast.UnaryOp(op=ast.USub(), operand=body)],
    )
    table.arrows.add(arrow)
    _items, comma = statement_items(old_statement)
    value = ast.Tuple(elts=[arrow], ctx=ast.Load()) if comma else arrow
    return ast.fix_missing_locations(ast.Expr(value=value))
