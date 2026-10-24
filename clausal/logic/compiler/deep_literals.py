"""Deep ground data in a clause compiles as a constant, not as nested code.

The clause compiler lowers a term to Python AST one node per level -- a
cell to a tuple display of its slots, a list to a list display -- and the
head matcher to a ``match`` pattern of the same shape.  CPython refuses an
expression nested a few hundred levels deep, and the compiler's own walks
(the globals collector, the variable collector, the emitters) recurse once
per level too, so ``assertz(big(T))`` with a 100k-nested ``f(f(...))`` or
a 5000-cell improper list ``[1, 2, ...|foo]`` raised RecursionError
(todo/done/deep-and-cyclic-terms-overflow-the-recursive-walkers-2026-10-22.md).

A GROUND sub-term has nothing for the compiler to see inside it: no
variable to register, no structure a caller's argument has to be matched
against slot by slot that unification would not match as well.  So before
a predicate is compiled, every maximal ground sub-term nested past
``DEEP_LITERAL_DEPTH`` in a head argument or a body goal's argument is
replaced -- in a compile-time twin of the clause, never in the stored
clause ``clause/2`` reads -- by a :class:`DeepLiteral` leaf.  The leaf is
opaque to every walk; it compiles to a reference to the term itself,
injected into the compiled code's globals under its ``$headlit_<id>`` key
(the mechanism A02-F003 built for ground head literals with no pattern of
their own: ``date``, ``Decimal``, a ``set``), so a head argument captures
and unifies against the term and a body argument IS the term.  Nothing
about a term of ordinary depth changes: one O(n) pass per compile finds
no deep sub-term and hands the clauses back untouched.
"""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from clausal.logic.cells import is_chars
from clausal.logic.variables import deref

if TYPE_CHECKING:
    from clausal.logic.database import Clause

#: Nesting (cells and lists) past which a ground sub-term compiles as a
#: constant.  Well under CPython's own nesting limits for an expression or
#: a pattern, and deeper than any program's hand-written data.
DEEP_LITERAL_DEPTH = 200


class DeepLiteral:
    """A ground term too deep to compile structurally: a leaf to every
    compiler walk, lowered as a reference to ``.term`` by name."""

    __slots__ = ("term",)

    def __init__(self, term: Any) -> None:
        self.term = term

    def __repr__(self) -> str:
        return f"DeepLiteral(<{type(self.term).__name__} term>)"


class _Frame:
    __slots__ = ("orig", "children", "built", "i", "depth", "ground", "is_list")

    def __init__(self, orig, children, is_list):
        self.orig = orig
        self.children = children
        self.built: list = []
        self.i = 0
        self.depth = 0          # the deepest child so far
        self.ground = True
        self.is_list = is_list


def _opens(d: Any):
    """The children of a container the rewrite descends into (a cell, a
    tuple-data cell, a list), or None for a leaf.  The chars carrier is
    text: a leaf."""
    if type(d) is tuple and d and not is_chars(d):
        return list(d)
    if type(d) is list and d:
        return list(d)
    return None


def _leaf_ground(d: Any) -> bool:
    """A leaf counts as ground only when the compiler has nothing to see in
    it: a variable, a syntax node, a partial list and every other object
    keep the sub-term they sit in structural."""
    return d is None or isinstance(d, (bool, int, float, complex, str, bytes)) or (
        type(d) is tuple and is_chars(d))


def rewrite_term(term: Any) -> Any:
    """*term* with each maximal ground sub-term nested past
    ``DEEP_LITERAL_DEPTH`` replaced by a :class:`DeepLiteral`; the same
    object when there is none (containers on the way to a replaced
    sub-term are rebuilt, everything else is shared)."""
    d = deref(term)
    children = _opens(d)
    if children is None:
        return term
    frames = [_Frame(d, children, type(d) is list)]
    active = {id(d)}        # the containers on the stack: a child among them is a cycle
    result = term
    while frames:
        f = frames[-1]
        if f.i < len(f.children):
            raw = f.children[f.i]
            f.i += 1
            c = deref(raw)
            kids = _opens(c)
            if kids is None:
                f.built.append(raw)
                if not _leaf_ground(c):
                    f.ground = False
                continue
            if id(c) in active:
                # A CYCLIC term (``X = f(X)``, no occurs check) has no
                # clause.  The engine KNOWS it saw a cycle, so this is
                # resource_error(finite_memory), Scryer's idiom (ruling
                # 2026-10-24, provisional), not the stack error a mere
                # depth overflow raises; Scryer itself panics here.
                from clausal.logic.exceptions import (  # noqa: PLC0415
                    LogicException, resource_error)
                raise LogicException(resource_error(
                    "finite_memory",
                    "a cyclic term (one built with no occurs check, "
                    "X = f(X)) has no clause"))
            active.add(id(c))
            frames.append(_Frame(c, kids, type(c) is list))
        else:
            frames.pop()
            active.discard(id(f.orig))
            depth = f.depth + 1
            if f.ground and depth > DEEP_LITERAL_DEPTH:
                value = DeepLiteral(f.orig)
            elif all(new is old for new, old in zip(f.built, f.children)):
                value = f.orig
            else:
                value = f.built if f.is_list else tuple(f.built)
            if frames:
                parent = frames[-1]
                parent.built.append(value)
                if depth > parent.depth:
                    parent.depth = depth
                if not f.ground:
                    parent.ground = False
            else:
                result = value if value is not f.orig else term
    return result


def _rewrite_args(goal: Any) -> Any:
    """*goal* (a head or a body goal) with its ARGUMENTS rewritten: a cell's
    slots, a syntax node's fields.  The goal itself is never a literal."""
    g = deref(goal)
    if type(g) is tuple and g and not is_chars(g):
        args = [rewrite_term(a) for a in g[1:]]
        if all(new is old for new, old in zip(args, g[1:])):
            return goal
        return (g[0], *args)
    if dataclasses.is_dataclass(g) and not isinstance(g, type):
        changes = {}
        for field in dataclasses.fields(g):
            old = getattr(g, field.name)
            if type(deref(old)) in (tuple, list):
                new = rewrite_term(old)
                if new is not old:
                    changes[field.name] = new
        if changes:
            return dataclasses.replace(g, **changes)
    return goal


def rewrite_clauses(clauses: "list[Clause]") -> "list[Clause]":
    """The compile-time twins of *clauses*: each clause whose head or body
    holds a deep ground sub-term is replaced by a copy with
    :class:`DeepLiteral` leaves in their place; every other clause is the
    same object.  The list is the same object when nothing changed."""
    out: list[Clause] = []
    changed = False
    for clause in clauses:
        head = _rewrite_args(clause.head)
        body = [_rewrite_args(goal) for goal in clause.body]
        if head is clause.head and all(n is o for n, o in zip(body, clause.body)):
            out.append(clause)
            continue
        changed = True
        out.append(dataclasses.replace(clause, head=head, body=body))
    return out if changed else clauses

