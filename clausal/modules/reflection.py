"""clausal.modules.reflection — match reified Clausal source from Clausal.

Phase 2 of ``implementation_plans/clausal-ast-reflection-and-structural-matching.md``.

Import the reified vocabulary and the enumeration/destructuring builtins::

    -import_from(reflection, [
        ReifiedItem, ReifiedClause, ReifiedFileItem,
        ClauseHead, ClauseBody, GoalFunctor, ReifiedSubterm,
        Clause, Goal, Variable, Atom, Escape,
    ])

Then linters and matchers are ordinary Clausal — e.g. the call-graph lint
from the feature plan::

    UndefinedCall(SRC, NAME) <- (
        ReifiedClause(SRC, CLAUSE),
        ClauseBody(CLAUSE, GOALS),
        GOAL in GOALS,
        GoalFunctor(GOAL, NAME, _),
        not DefinedName(SRC, NAME)
    )

Builtins
--------
- ``ReifiedItem(SOURCE, ITEM)`` — enumerate every reified top-level item of
  a ``.clausal`` source *text* (``ModuleDirective`` / ``Clause`` /
  ``PythonCode``).
- ``ReifiedClause(SOURCE, CLAUSE)`` — clauses only.
- ``ReifiedFileItem(PATH, ITEM)`` — like ``ReifiedItem`` over a file path.
- ``ClauseHead(CLAUSE, HEAD)`` / ``ClauseBody(CLAUSE, GOALS)`` — accessors.
- ``GoalFunctor(GOAL, NAME, ARITY)`` — functor name (string) and arity of a
  ``Goal`` term (arity counts positional plus keyword arguments).
- ``ReifiedSubterm(TERM, SUB)`` — enumerate every subterm, depth-first,
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
from clausal.logic.trampoline import DONE
from clausal.logic.variables import deref, unify
from clausal.modules.py import ModulePredicate, simple_to_trampoline
from clausal.pythonic_ast import nodes as simple_ast
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
    if not isinstance(source, str):
        yield (_fail, DONE)
        return
    yield from _yield_matches(
        _items_from_text(source), item, _proceed, _fail, trail)


def _reified_clause_2(this_generator, _proceed, _fail, _catcher,
                      source, clause, trail):
    source = deref(source)
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


# ── Registration ─────────────────────────────────────────────────────────────


ReifiedItem = ModulePredicate("ReifiedItem", module="reflection")
ReifiedItem._register(2, _reified_item_2)

ReifiedClause = ModulePredicate("ReifiedClause", module="reflection")
ReifiedClause._register(2, _reified_clause_2)

ReifiedFileItem = ModulePredicate("ReifiedFileItem", module="reflection")
ReifiedFileItem._register(2, _reified_file_item_2)

ReifiedSubterm = ModulePredicate("ReifiedSubterm", module="reflection")
ReifiedSubterm._register(2, _reified_subterm_2)

ClauseHead = ModulePredicate("ClauseHead", module="reflection")
ClauseHead._register(2, simple_to_trampoline(_clause_head_2))

ClauseBody = ModulePredicate("ClauseBody", module="reflection")
ClauseBody._register(2, simple_to_trampoline(_clause_body_2))

GoalFunctor = ModulePredicate("GoalFunctor", module="reflection")
GoalFunctor._register(3, simple_to_trampoline(_goal_functor_3))
