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

Between kept and dropped sits MODIFIED: when the output has exactly as many
goals as the input, the correspondence is positional -- the i-th output goal IS
the i-th input goal, either verbatim (node reused) or changed in place.  A
changed goal is rendered to a fresh node and its comments ride across without
the stale marker, because the goal survives and its comments almost certainly
still apply.  An output goal that instead equals a DIFFERENT input goal is a
reordering, which the positional correspondence does not model; refused.

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
    arrow_nodes,
    clause_body,
    goal_sequence,
    is_clause,
    statement_items,
)
from clausal.fmt.emit import format_source
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var
from clausal.reflection import (
    _LAMBDA_ARROW_MARKER,
    Goal,
    is_v,
    vfield,
    ReifyError,
    RenderError,
    reify_ast,
    render_ast,
    render_source,
)

FIXPOINT_BOUND = 20

#: Appended to a deleted goal's relocated comments: the wording described a
#: goal that no longer exists, so the repair pass must confirm or rewrite it.
STALE_MARKER = " (maybe stale?)"

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
        if _head_has_keywords(items[0]):
            # Reification does not keep a head's keyword-argument NAMES --
            # `p(A=X, B=2)` reifies as `Goal("p", [X, 2], [])` -- so a
            # rewritten head would come back positional and quietly change the
            # predicate's interface.  Leave the clause alone.
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


def _head_has_keywords(clause):
    """Does this clause's head use keyword arguments, anywhere inside it?"""
    return any(
        isinstance(node, ast.Call) and node.keywords
        for node in ast.walk(clause.left)
    )


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
        for _ in call("rewrite_clause", reified_clause, out, module=module):
            return _deref_walk(out), rule
    return None


def _splice(table, old_statement, reified_in, reified_out, position):
    """Build the replacement statement, reusing every matched goal's node."""
    old_goals = _top_level_goal_nodes(old_statement)
    # P2: a reified Clause is a CELL, so its fields are read by name through
    # the vocabulary's own accessor.  Bound once here rather than inline at
    # each of the eleven uses below, which would read worse than the
    # attribute access it replaces.
    in_goals = vfield(reified_in, "goals")
    out_goals = vfield(reified_out, "goals")
    if len(old_goals) != len(in_goals):
        raise RewriteError(
            f"goal correspondence lost at {position}: {len(old_goals)} nodes "
            f"against {len(in_goals)} reified goals"
        )

    consumed = [False] * len(in_goals)
    new_goals = []
    if len(out_goals) == len(in_goals):
        # Equal goal counts: the correspondence is positional.  Each output
        # goal is its input goal verbatim (node reused, comments never in
        # question) or a MODIFICATION of it (rendered fresh, comments ride
        # across unmarked -- the goal survives, so its comments almost
        # certainly still apply).  An output goal that equals a DIFFERENT
        # input goal is a reordering in disguise, and pairing it with the
        # goal that happens to share its position would hand it that goal's
        # comments; refused instead.
        for index, out_goal in enumerate(out_goals):
            consumed[index] = True
            if out_goal == in_goals[index]:
                new_goals.append(old_goals[index])
                continue
            if any(
                out_goal == other
                for other_index, other in enumerate(in_goals)
                if other_index != index
            ):
                raise RewriteError(
                    f"cannot splice the result at {position}: {out_goal!r} "
                    f"differs from the input goal at its position but equals "
                    f"another input goal -- the rule REORDERED goals, which "
                    f"the positional correspondence does not model"
                )
            new_node = _render_goal_node(table, out_goal, position)
            table.move(old_goals[index], new_node)
            new_goals.append(new_node)
    else:
        cursor = 0
        for out_goal in out_goals:
            matched = _match(in_goals, consumed, cursor, out_goal)
            if matched is None:
                raise RewriteError(
                    f"cannot splice the result at {position}: {out_goal!r} is "
                    f"not available at or after input goal {cursor}. Either "
                    f"the rule invented a goal -- which has no node to reuse "
                    f"and no comments to inherit -- or it REORDERED or "
                    f"modified goals while also changing their number, which "
                    f"neither correspondence models"
                )
            consumed[matched] = True
            cursor = matched + 1
            new_goals.append(old_goals[matched])

    if vfield(reified_out, "head") == vfield(reified_in, "head"):
        head_node = _head_node(old_statement)
    else:
        head_node = _render_head(vfield(reified_out, "head"), position)

    new_statement = _build_statement(old_statement, head_node, new_goals, table)

    # The statement's own comments ride across.  Matched goals kept their
    # nodes, so their comments never moved at all; a dropped goal's comments
    # move up to the clause, marked so the comment-repair pass scrutinizes
    # wording whose subject no longer exists (operator call, 2026-08-15).
    table.move(old_statement, new_statement)
    for index, was_consumed in enumerate(consumed):
        if not was_consumed:
            table.annotate(old_goals[index], STALE_MARKER)
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
    try:
        node = render_ast(head)
    except RenderError as error:
        # A rule may bind a head argument to something with no source form at
        # all -- a Python callable built by an escape, say.  That is a rule
        # bug, reported as one rather than as a traceback out of the renderer.
        raise RewriteError(
            f"the rewritten head at {position} cannot be rendered: {error}"
        ) from error
    if _LAMBDA_ARROW_MARKER in ast.unparse(node):
        raise RewriteError(
            f"the rewritten head at {position} contains a lambda: the "
            f"renderer marks a rendered lambda arrow with a sentinel that "
            f"only the text-level renderer strips, and this driver splices "
            f"nodes"
        )
    return node


def _render_goal_node(table, goal, position):
    """Render a MODIFIED goal to a fresh ``ast`` node, arrows registered.

    Rendering goes to SOURCE text and back through a parse, because that is the
    one route on which arrows are mechanically knowable: the renderer emits
    every lambda arrow it renders through the sentinel repair, so in its output
    text ``<-`` adjacency means arrow and ``< -`` spacing means comparison --
    exactly the convention the capture-time detector reads.  Running that
    detector over the re-parse teaches the ledger every arrow the rendered goal
    contains and nothing else; a genuine ``A < -B`` renders spaced, is not
    registered, and stays a comparison.

    Only a plain ``Goal`` is accepted.  A conjunction group reifies as a bare
    list, which would render as a LIST LITERAL -- same for group-carrying
    ``or``/``not`` operands -- and a goal that is not a ``Goal`` has no
    rendering this driver can vouch for.
    """
    if not is_v(goal, Goal):
        raise RewriteError(
            f"cannot splice a modified goal at {position}: {goal!r} is not a "
            f"plain Goal, and no other goal shape has a rendering this driver "
            f"can vouch for (a conjunction group reifies as a list, which "
            f"renders as a list literal, not a group)"
        )
    try:
        text = render_source(goal)
    except RenderError as error:
        raise RewriteError(
            f"the modified goal at {position} cannot be rendered: {error}"
        ) from error
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError as error:
        raise RewriteError(
            f"the modified goal at {position} rendered to unparsable source "
            f"{text!r}: {error}"
        ) from error
    table.arrows.update(arrow_nodes(node, text))
    return ast.fix_missing_locations(node)


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
