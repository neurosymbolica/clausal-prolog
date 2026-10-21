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

Re-rendering is where an atom's SPELLING is at stake.  ``'Foo'``, ``"Foo"`` and
``Foo`` are three different terms in the seam (an atom, a string, a variable)
and ``Atom("Foo")`` is one vocabulary term, so each clause is reified with an
``AtomSpellings`` table -- the quote character every atom was read with, kept
beside the term -- and a rendered goal or head is written back through it: an
atom the rule passed through keeps its quote, and one the rule built is spelled
so it reads back as that atom (``reflection._reads_back_bare``).  The output is
then PROVED to say what the rules meant: every rewritten statement is read back
out of the formatted text and compared, atom spelling included, with the term
the last rule produced for it (:func:`_assert_reads_back`).  A difference is a
driver bug and the file is refused, never written.
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
    literal_spellings,
    statement_items,
)
from clausal.fmt.emit import format_source
from clausal.import_hook import _load_module
from clausal.logic.cells import chars_text, flat_carrier, is_chars
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, is_var
from clausal.reflection import (
    _LAMBDA_ARROW_MARKER,
    Atom,
    AtomSpellings,
    Clause,
    Escape,
    FormatString,
    Goal,
    Variable,
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
    # statement index -> (the term the last rule produced for it, the
    # spellings it was rendered through, the -double_quotes mode there);
    # what ``_assert_reads_back`` holds the output to.
    intended = {}
    # The file's ``-double_quotes`` mode at the statement being reified.
    # Each clause is reified from its own SEGMENT, which never contains the
    # directive, so the mode is tracked here and handed to the reifier --
    # without it a ``-double_quotes(atom)`` file's ``"t"`` reified as a
    # string under the chars default (and a chars file's as an atom before
    # the flip), and the folded head came back respelled.
    double_quotes = None
    for index, statement in enumerate(tree.body):
        mode = _double_quotes_directive(statement)
        if mode is not None:
            double_quotes = mode
            continue
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
        spellings = AtomSpellings()
        try:
            reified = reify_ast(statement, source=segment,
                                double_quotes=double_quotes,
                                spellings=spellings)
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
            current = _splice(table, current, reified, replacement, position,
                              spellings)
            fired.append((position, rule))
            reified = replacement
            intended[index] = (reified, spellings, double_quotes, position)
        tree.body[index] = current
    text = format_source(source, (tree, table))
    _assert_reads_back(text, intended)
    return RewriteResult(text=text, fired=fired)


def _assert_reads_back(text, intended):
    """Refuse the output unless each rewritten statement reads back as the
    term the rule produced for it.

    The rendered goal and head went through a renderer, a parse, a splice and
    the emitter, and the term is compared at the far end of all four: the
    statement at the same index of the formatted *text* (the formatter keeps
    statements in place) is reified under the same ``-double_quotes`` mode
    and matched structurally, atom spellings included, against what the last
    rule said (``_reads_back_as``).  Cheap -- one reification per rewritten
    statement -- and the check that makes "the rewrite changed a term's
    class" a refusal instead of a silent edit.
    """
    if not intended:
        return
    statements = ast.parse(text).body
    for index, (term, spellings, double_quotes, position) in intended.items():
        statement = statements[index]
        segment = ast.get_source_segment(text, statement)
        reread_spellings = AtomSpellings()
        try:
            reread = reify_ast(statement, source=segment,
                               double_quotes=double_quotes,
                               spellings=reread_spellings)
        except (ReifyError, SyntaxError) as error:
            raise RewriteError(
                f"the rewritten clause at {position} does not read back: "
                f"{error}"
            ) from error
        mismatch = _reads_back_as(term, reread, spellings, reread_spellings)
        if mismatch is not None:
            meant, read = mismatch
            raise RewriteError(
                f"the rewritten clause at {position} does not read back as "
                f"the term the rule produced: the rule meant {meant!r} and "
                f"the output reads {read!r}"
            )


def _reads_back_as(meant, read, meant_spellings, read_spellings):
    """``None`` when *read* is the term *meant*, else the first differing
    pair ``(meant_part, read_part)``.

    Structural equality, with three allowances for what a re-read cannot
    reproduce: item and escape positions (the clause moved), the numbering
    of anonymous variables (per clause, by encounter -- a dropped ``_``
    renumbers the rest), and the spelling of an atom the rule BUILT.  An
    atom the rule passed through -- the very cell the reifier recorded,
    which ``_resolved`` preserves -- must come back with the quote it was
    read with, whatever the item's other spellings of that name say.
    Everything else must be the same: an atom read back as a variable, a
    Python constant or a string is exactly what this exists to catch.

    A list of one-char atoms IS a text to the engine, which hands a rule's
    answer back with such a list -- an argument list ``['t']`` included --
    promoted to the chars carrier; a carrier is read as that list here.
    """
    meant = deref(meant)
    read = deref(read)
    if is_chars(meant):
        meant = list(chars_text(meant))
    if is_chars(read):
        read = list(chars_text(read))
    if is_v(meant, Atom) or is_v(read, Atom):
        if not (is_v(meant, Atom) and is_v(read, Atom)):
            return meant, read
        if vfield(meant, "name") != vfield(read, "name"):
            return meant, read
        quote = meant_spellings.cell_quote(meant)
        if quote is not None and quote != read_spellings.cell_quote(read):
            return meant, read
        return None
    if is_v(meant, Variable) or is_v(read, Variable):
        if not (is_v(meant, Variable) and is_v(read, Variable)):
            return meant, read
        left, right = vfield(meant, "name"), vfield(read, "name")
        anonymous = left.startswith("#") and right.startswith("#")
        return None if anonymous or left == right else (meant, read)
    if is_v(meant, (Clause, Escape, FormatString)):
        if not is_v(read, (Clause, Escape, FormatString)) or meant[0] != read[0]:
            return meant, read
        # The last field is the position; everything before it is compared.
        return _parts_read_back_as(meant[1:-1], read[1:-1],
                                   meant_spellings, read_spellings)
    if isinstance(meant, (list, tuple)) and type(meant) is type(read):
        if len(meant) != len(read):
            return meant, read
        return _parts_read_back_as(meant, read, meant_spellings, read_spellings)
    if isinstance(meant, dict) and isinstance(read, dict):
        if list(meant) != list(read):
            return meant, read
        return _parts_read_back_as(list(meant.values()), list(read.values()),
                                   meant_spellings, read_spellings)
    if dataclasses.is_dataclass(meant) and type(meant) is type(read):
        # A ``pythonic_ast`` node (an operator, ``Or``/``Not``, a lambda):
        # its fields hold terms, so they are walked rather than compared
        # with ``==``, which would see through no allowance above.
        fields = [field.name for field in dataclasses.fields(meant)
                  if field.compare]
        return _parts_read_back_as(
            [getattr(meant, name) for name in fields],
            [getattr(read, name) for name in fields],
            meant_spellings, read_spellings)
    if type(meant) is not type(read) or meant != read:
        return meant, read
    return None


def _parts_read_back_as(meant, read, meant_spellings, read_spellings):
    for left, right in zip(meant, read):
        mismatch = _reads_back_as(left, right, meant_spellings, read_spellings)
        if mismatch is not None:
            return mismatch
    return None


def _head_has_keywords(clause):
    """Does this clause's head use keyword arguments, anywhere inside it?"""
    return any(
        isinstance(node, ast.Call) and node.keywords
        for node in ast.walk(clause.left)
    )


def _double_quotes_directive(statement):
    """``"atom"`` / ``"chars"`` when *statement* is ``-double_quotes(mode)``
    with a mode the loader accepts (``DOUBLE_QUOTES_MODES``, the loader's
    own list), else ``None``.  Any other argument
    (``codes``, a typo) is a load error in the compiler
    (``_handle_double_quotes_directive``); the driver does not second-guess
    it, and does not silently rewrite the file under a mode the loader
    would refuse -- it leaves the mode as it was, and the file's load will
    say what is wrong."""
    from clausal.templating.term_rewriting import DOUBLE_QUOTES_MODES  # noqa: PLC0415
    value = getattr(statement, "value", None)
    if (isinstance(statement, ast.Expr) and isinstance(value, ast.UnaryOp)
            and isinstance(value.op, ast.USub)
            and isinstance(value.operand, ast.Call)
            and isinstance(value.operand.func, ast.Name)
            and value.operand.func.id == "double_quotes"
            and len(value.operand.args) == 1
            and isinstance(value.operand.args[0], ast.Name)
            and value.operand.args[0].id in DOUBLE_QUOTES_MODES):
        return value.operand.args[0].id
    return None


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
            return _resolved(out), rule
    return None


def _resolved(term):
    """The rule's answer with every bound variable replaced by its value --
    ``solve._deref_walk``, except that a tuple nothing changed inside is
    returned AS IS.

    ``_deref_walk`` (and its C twin) rebuild every tuple, which would make
    every ``Atom`` cell the rule passed through a new object and leave the
    ``AtomSpellings`` table nothing to answer by identity for: each
    passed-through atom would fall to the by-name layer, which cannot tell
    the ``'a'`` from the ``a`` of an item that writes both.  Keeping the
    object is what makes "the rule did not touch this atom" knowable.
    """
    term = deref(term)
    if is_var(term):
        return term
    if isinstance(term, list):
        return [_resolved(item) for item in term]
    if isinstance(term, tuple):
        if is_chars(term):
            return flat_carrier(term)
        items = [_resolved(item) for item in term]
        if all(new is old for new, old in zip(items, term)):
            return term
        return tuple(items)
    if isinstance(term, dict):
        return {_resolved(key): _resolved(value) for key, value in term.items()}
    if isinstance(term, (set, frozenset)):
        return type(term)(_resolved(item) for item in term)
    hook = getattr(term, "__walk__", None)
    if hook is not None:
        return hook()
    if is_term_instance(term):
        # A ``pythonic_ast`` node (an operator, ``Or``/``Not``, a lambda):
        # rebuilt from its resolved fields, as ``_deref_walk`` does.
        return type(term)(**{
            name: _resolved(getattr(term, name)) for name in term_field_names(term)
        })
    return term


def _splice(table, old_statement, reified_in, reified_out, position, spellings):
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
            new_node = _render_goal_node(table, out_goal, position, spellings)
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
        head_node = _render_head(vfield(reified_out, "head"), position, spellings)

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


def _render_head(head, position, spellings):
    try:
        node = render_ast(head, spellings)
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


def _render_goal_node(table, goal, position, spellings):
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
        text = render_source(goal, spellings)
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
    # The same for the quote character: the renderer writes each atom with
    # the quote it was read with (``spellings``) and a string double-quoted,
    # and the emitter copies a ledgered spelling back verbatim, so the
    # rendered term is the term that comes out.
    table.literals.update(literal_spellings(node, text))
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
