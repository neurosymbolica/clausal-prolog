"""clausal.modules.reflection — match reified Clausal source from Clausal.

Phase 2 of ``implementation_plans/clausal-ast-reflection-and-structural-matching.md``.

Import the reified vocabulary and the enumeration/destructuring builtins::

    -import_from(reflection, [
        reified_item, reified_clause, reified_file_item,
        clause_head, clause_body, goal_functor, reified_subterm,
        Clause, Goal, Variable, Atom, Escape,
    ])

Then linters and matchers are ordinary Clausal — e.g. the call-graph lint
from the feature plan::

    UndefinedCall(SRC, NAME) <- (
        reified_clause(SRC, CLAUSE),
        clause_body(CLAUSE, GOALS),
        GOAL in GOALS,
        goal_functor(GOAL, NAME, _),
        not DefinedName(SRC, NAME)
    )

Builtins
--------
- ``reified_item(SOURCE, ITEM)`` — enumerate every reified top-level item of
  a ``.clausal`` source *text* (``ModuleDirective`` / ``Clause`` /
  ``PythonCode``).
- ``reified_clause(SOURCE, CLAUSE)`` — clauses only.
- ``reified_file_item(PATH, ITEM)`` — like ``reified_item`` over a file path.
- ``clause_head(CLAUSE, HEAD)`` / ``clause_body(CLAUSE, GOALS)`` — accessors.
- ``goal_functor(GOAL, NAME, ARITY)`` — functor name (string) and arity of a
  ``Goal`` term (arity counts positional plus keyword arguments).
- ``reified_subterm(TERM, SUB)`` — enumerate every subterm, depth-first,
  starting with ``TERM`` itself; recurses through vocabulary terms, raw
  operator nodes, lists, tuples, and dict values.

Reification is cached per source text (and per file path + mtime), so
back-to-back matcher queries over the same source parse it once.
"""

from __future__ import annotations

import dataclasses
import functools
import os

from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.exceptions import LogicException, instantiation_error
from clausal.logic.trampoline import DONE
from clausal.logic.variables import deref, is_var, unify
from clausal.modules.py import ModulePredicate, simple_to_trampoline
from clausal.pythonic_ast import nodes as simple_ast
from clausal.terms import Compound, KWTerm
from clausal.reflection import (
    Atom,
    Clause,
    Escape,
    FormatString,
    Goal,
    IfThenElse,
    ModuleDirective,
    PythonCode,
    Variable,
    reify_file,
    reify_source,
    # The operator classes op_node names/builds are exactly those the renderer
    # round-trips, so the two stay bijective (see _OP_NODE_CLASSES).
    RENDER_OP_CLASS_NAMES,
)


# ── Cached reification ───────────────────────────────────────────────────────


@functools.lru_cache(maxsize=128)
def _items_from_text(text: str) -> tuple:
    return tuple(reify_source(text))


@functools.lru_cache(maxsize=128)
def _items_from_file(path: str, mtime: float) -> tuple:
    return tuple(reify_file(path))


# ── Nondeterministic enumeration ─────────────────────────────────────────────


def _yield_matches(candidates, pattern, _proceed, _fail, trail):
    for candidate in candidates:
        mark = trail.mark()
        if unify(pattern, candidate, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _reified_item_2(this_generator, _proceed, _fail, _catcher,
                    source, item, trail):
    source = deref(source)
    if is_var(source):
        raise LogicException(instantiation_error("reified_item/2"))
    if not isinstance(source, str):
        yield (_fail, DONE)
        return
    yield from _yield_matches(
        _items_from_text(source), item, _proceed, _fail, trail)


def _reified_clause_2(this_generator, _proceed, _fail, _catcher,
                      source, clause, trail):
    source = deref(source)
    if is_var(source):
        raise LogicException(instantiation_error("reified_clause/2"))
    if not isinstance(source, str):
        yield (_fail, DONE)
        return
    clauses = [
        candidate for candidate in _items_from_text(source)
        if isinstance(candidate, Clause)
    ]
    yield from _yield_matches(clauses, clause, _proceed, _fail, trail)


def _reified_file_item_2(this_generator, _proceed, _fail, _catcher,
                         path, item, trail):
    path = deref(path)
    if is_var(path):
        raise LogicException(instantiation_error("reified_file_item/2"))
    if not isinstance(path, str) or not os.path.exists(path):
        yield (_fail, DONE)
        return
    candidates = _items_from_file(path, os.path.getmtime(path))
    yield from _yield_matches(candidates, item, _proceed, _fail, trail)


# ── Subterm walk ─────────────────────────────────────────────────────────────


def _subterms(term):
    yield term
    if is_term_instance(term):
        for field_name in term_field_names(term):
            if field_name == "position":
                continue
            yield from _subterms(getattr(term, field_name))
    elif isinstance(term, simple_ast.Node):
        for field in dataclasses.fields(term):
            if field.name == "position":
                continue
            yield from _subterms(getattr(term, field.name))
    elif isinstance(term, (list, tuple)):
        for element in term:
            yield from _subterms(element)
    elif isinstance(term, dict):
        for value in term.values():
            yield from _subterms(value)


def _reified_subterm_2(this_generator, _proceed, _fail, _catcher,
                       term, sub, trail):
    yield from _yield_matches(
        _subterms(deref(term)), sub, _proceed, _fail, trail)


# ── Deterministic accessors ──────────────────────────────────────────────────


def _clause_head_2(clause, head, trail, k):
    clause = deref(clause)
    if isinstance(clause, Clause) and unify(head, clause.head, trail):
        yield None


def _clause_body_2(clause, goals, trail, k):
    clause = deref(clause)
    if isinstance(clause, Clause) and unify(goals, clause.goals, trail):
        yield None


def _goal_functor_3(goal, name, arity, trail, k):
    goal = deref(goal)
    if not isinstance(goal, Goal):
        return
    args = deref(goal.args)
    kwargs = deref(goal.kwargs)
    count = len(args) if isinstance(args, list) else 0
    count += len(kwargs) if isinstance(kwargs, list) else 0
    mark = trail.mark()
    if unify(name, deref(goal.name), trail) and unify(arity, count, trail):
        yield None
    else:
        trail.undo(mark)


# ── Operator-node decompose/construct ────────────────────────────────────────

# The operator classes ``op_node`` names and builds are exactly those in
# ``clausal.reflection.RENDER_OP_CLASS_NAMES``, so any node ``op_node``
# constructs re-reifies from the source the renderer emits (modulo renderer
# escape-ambiguity edges such as a nested unary ``+``).  That is the renderer's
# *operator* set, not everything it renders: node kinds whose operands are not a
# ``left``/``right`` or ``operand`` field — ``CompareChain`` (a list of links),
# ``SetLiteral``, ``DictLiteral``, ``Lambda``, … — do not fit ``op_node/3``'s
# decompose/construct shape and are excluded even though the renderer handles
# them; ``StructuralEq``/``Evaluate`` are excluded because they are unreachable
# surface.  Decompose fails cleanly on all of them rather than promise a
# round-trip it can't honour.
_OP_NODE_CLASSES = {
    name: getattr(simple_ast, name) for name in RENDER_OP_CLASS_NAMES
}


def _op_operand_fields(cls):
    """Operand field names of an operator class in dataclass field order, minus
    the non-semantic ``position`` field — ``[left, right]`` for a binary
    operator, ``[operand]`` for a unary one.  ``op`` is a ``ClassVar``, so it is
    not a field and never appears."""
    return [
        field.name for field in dataclasses.fields(cls)
        if field.name != "position"
    ]


def _op_node_3(node, class_name, args, trail, k):
    """``op_node(NODE, CLASS_NAME, ARGS)`` — the ``functor``/``unpack`` analogue
    for ``simple_ast`` operator nodes.

    - **decompose** (NODE bound to an operator node): unify CLASS_NAME with its
      ``simple_ast`` class name (a string) and ARGS with its operand list.
    - **construct** (NODE unbound, CLASS_NAME + ARGS bound): build the named
      operator node from the operands and unify it with NODE.

    A bound NODE that is not a renderable operator node, or an unknown/unbound
    CLASS_NAME in construct mode, fails cleanly (no solution).  Both NODE and
    CLASS_NAME unbound also fails cleanly (nothing to build from) — matching the
    sibling ``goal_functor/3`` rather than raising ``instantiation_error``.

    In construct mode the operands are stored as given (shallow-deref'd), so an
    operand that is *still unbound* when the built node is later rendered will
    trip the renderer — bind operands before rendering, or (the usual flow)
    reconstruct from a decomposed node whose operands are already ground."""
    node = deref(node)
    if is_var(node):
        # construct mode: class name + operands -> a fresh operator node
        name = deref(class_name)
        cls = _OP_NODE_CLASSES.get(name) if isinstance(name, str) else None
        if cls is None:
            return  # unbound or unknown class name -> fail cleanly
        operands = deref(args)
        if not isinstance(operands, list):
            return  # need a proper operand list to build
        fields = _op_operand_fields(cls)
        if len(operands) != len(fields):
            return
        built = cls(**{f: deref(o) for f, o in zip(fields, operands)})
        if unify(node, built, trail):
            yield None
        return
    # decompose mode: operator node -> class name + operand list.  Match by
    # *class identity*, not name — a foreign object that merely shares an
    # operator's name (e.g. CPython ``ast.Gt``) must fail cleanly, not crash in
    # ``_op_operand_fields`` or false-match.
    cls = _OP_NODE_CLASSES.get(type(node).__name__)
    if cls is None or type(node) is not cls:
        return  # not a renderable operator node -> fail cleanly
    operands = [getattr(node, field) for field in _op_operand_fields(cls)]
    mark = trail.mark()
    if unify(class_name, cls.__name__, trail) and unify(args, operands, trail):
        yield None
    else:
        trail.undo(mark)


# ── Single-site structural rewrite ───────────────────────────────────────────


def _rewrites(term, old, new, trail):
    """Yield each single-site rewrite of ``term`` where one subterm unifying
    ``old`` is replaced by ``new`` — depth-first, pre-order.

    Occurrence order matches ``reified_subterm/2``'s ``_subterms`` walk on the
    reified domain it targets (vocab / ``simple_ast`` nodes / lists / dicts —
    what reified ``goals``/``args`` hold).  For raw ``Compound``/``KWTerm`` the
    two diverge: this walk descends args/values position-preservingly (needed to
    rewrite ordinary compounds), whereas ``_subterms`` exposes their raw
    fields — so don't rely on cross-walk agreement off the reified domain.

    Only the spine from the root to the rewritten position is rebuilt; every
    off-path subterm is reused *by reference*, so structure and variable
    identity are preserved everywhere except the one rewritten occurrence.  The
    bindings from the occurrence match are live at yield time (so ``new`` is
    instantiated through them) and are undone on backtracking, so distinct
    occurrences don't leak bindings into one another.  ``_position`` metadata is
    carried on every rebuilt node.  Vars, scalars, atoms, segmented strings and
    native dict/list term objects (``DictTerm``/``ListTerm``) are leaves."""
    term = deref(term)
    # pre-order: replace this whole occurrence if it unifies OLD.  An unbound
    # var subterm is an opaque leaf, never a match site (so a bare TERM var is
    # preserved, not "matched" and bound).  Matching OLD against a ground-rooted
    # subterm uses full unification: OLD's own pattern vars bind, and — only for
    # a *non-ground* TERM — a var nested inside the matched subterm may bind too
    # (undone on backtracking).  The intended input is a ground reified term (a
    # clause), for which identity of unaffected positions is preserved exactly.
    if not is_var(term):
        mark = trail.mark()
        if unify(term, old, trail):
            yield new
        trail.undo(mark)
    # then descend, rebuilding only the path to each rewritten child
    if isinstance(term, list):
        for i, elem in enumerate(term):
            for rewritten in _rewrites(elem, old, new, trail):
                yield term[:i] + [rewritten] + term[i + 1:]
    elif isinstance(term, tuple):
        for i, elem in enumerate(term):
            for rewritten in _rewrites(elem, old, new, trail):
                yield term[:i] + (rewritten,) + term[i + 1:]
    elif isinstance(term, Compound):
        args = term.args
        for i, arg in enumerate(args):
            for rewritten in _rewrites(arg, old, new, trail):
                yield Compound(term.functor,
                               args[:i] + (rewritten,) + args[i + 1:],
                               _position=term._position)
    elif isinstance(term, KWTerm):
        items = list(term.items())
        for key, value in items:
            for rewritten in _rewrites(value, old, new, trail):
                kw = dict(items)
                kw[key] = rewritten
                yield KWTerm(term.functor, _position=term._position, **kw)
    elif isinstance(term, dict):
        for key, value in term.items():
            for rewritten in _rewrites(value, old, new, trail):
                rebuilt = dict(term)
                rebuilt[key] = rewritten
                yield rebuilt
    elif is_term_instance(term):
        fields = term_field_names(term)
        for fname in fields:
            if fname == "position":
                continue  # non-semantic source location — skip like _subterms
            for rewritten in _rewrites(getattr(term, fname), old, new, trail):
                kwargs = {f: getattr(term, f) for f in fields}
                kwargs[fname] = rewritten
                yield type(term)(**kwargs)
    # else: leaf (Var, scalar, atom class, Seg*) — nothing to descend into


def _replace_subterm_4(this_generator, _proceed, _fail, _catcher,
                       term, old, new, result, trail):
    """``replace_subterm(TERM, OLD, NEW, RESULT)`` — RESULT is TERM with ONE
    occurrence of a subterm unifying OLD replaced by NEW; nondeterministic over
    occurrences in depth-first order.  Zero occurrences → no solutions."""
    old = deref(old)
    new = deref(new)
    for rebuilt in _rewrites(deref(term), old, new, trail):
        mark = trail.mark()
        if unify(result, rebuilt, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Registration ─────────────────────────────────────────────────────────────


reified_item = ModulePredicate("reified_item", module="reflection")
reified_item._register(2, _reified_item_2)

reified_clause = ModulePredicate("reified_clause", module="reflection")
reified_clause._register(2, _reified_clause_2)

reified_file_item = ModulePredicate("reified_file_item", module="reflection")
reified_file_item._register(2, _reified_file_item_2)

reified_subterm = ModulePredicate("reified_subterm", module="reflection")
reified_subterm._register(2, _reified_subterm_2)

clause_head = ModulePredicate("clause_head", module="reflection")
clause_head._register(2, simple_to_trampoline(_clause_head_2))

clause_body = ModulePredicate("clause_body", module="reflection")
clause_body._register(2, simple_to_trampoline(_clause_body_2))

goal_functor = ModulePredicate("goal_functor", module="reflection")
goal_functor._register(3, simple_to_trampoline(_goal_functor_3))

op_node = ModulePredicate("op_node", module="reflection")
op_node._register(3, simple_to_trampoline(_op_node_3))

replace_subterm = ModulePredicate("replace_subterm", module="reflection")
replace_subterm._register(4, _replace_subterm_4)
