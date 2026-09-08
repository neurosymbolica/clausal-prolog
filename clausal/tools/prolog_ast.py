"""Prolog AST — intermediate representation for bidirectional translation.

All nodes are frozen dataclasses. The module also provides:
- PrologVisitor / PrologTransformer (ast.NodeVisitor-style)
- Builder helpers (atom, var, compound, plist, fact, rule, …)
- Introspection utilities (variables, functors, is_ground, term_size, subterms)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Iterator, Union


# ── Terms ──────────────────────────────────────────────────────────────
#
# Each term node carries a `span` field: a (start_offset, end_offset)
# character-offset tuple over the source text, or None when unavailable.
# `span` is excluded from equality/repr (compare=False) so existing
# equality-based tests are unaffected, and it is always the LAST field so
# positional construction (PAtom("foo"), PCompound("f", (...,))) keeps
# working unchanged. Spans are populated by prolog_parser.py and are only
# meaningful when the underlying tokens carry real offsets (>= 0); on the
# bootstrap path (toklex spec loader), offsets are -1 and spans come out
# as garbage negative tuples — harmless since nothing reads them there.

@dataclass(frozen=True, slots=True)
class PAtom:
    """Atom: foo, 'hello world', +, =.."""
    name: str
    quoted: bool = False
    span: tuple | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PVar:
    """Variable: X, _Y, _"""
    name: str  # "_" for anonymous
    span: tuple | None = field(default=None, compare=False)
    #: Unit DISCARDED from a Clausal Quantity (`DEPOSIT(baht)` -> `_Deposit`),
    #: reported in the line's trailing `% Clausal units:` comment. Non-comparing
    #: — provenance, not identity.
    unit: str | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PNumber:
    """Integer or float literal."""
    value: int | float
    span: tuple | None = field(default=None, compare=False)
    #: Unit DISCARDED from a Clausal Quantity (`5000(euro)` -> `5000`),
    #: reported in the line's trailing `% Clausal units:` comment. Non-comparing
    #: — provenance, not identity, so an annotated 5000 equals a plain one.
    unit: str | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PString:
    """Double-quoted string (SWI: string; Scryer: char list)."""
    value: str
    span: tuple | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PCompound:
    """f(a, b, c) — also used for operators: +(1, 2)"""
    functor: str
    args: tuple[PTerm, ...]
    span: tuple | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PList:
    """[H|T] or [a, b, c]"""
    elements: tuple[PTerm, ...]
    tail: PTerm | None = None  # None means proper list
    span: tuple | None = field(default=None, compare=False)

@dataclass(frozen=True, slots=True)
class PCurly:
    """{Goal} — DCG inline goals, set notation."""
    body: PTerm
    span: tuple | None = field(default=None, compare=False)


PTerm = Union[PAtom, PVar, PNumber, PString, PCompound, PList, PCurly]


# ── Clauses & directives ──────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PClause:
    """head :- body.  (body=None for facts)"""
    head: PTerm
    body: PTerm | None = None

@dataclass(frozen=True, slots=True)
class PDCGRule:
    """head --> body."""
    head: PTerm
    body: PTerm

@dataclass(frozen=True, slots=True)
class PDirective:
    """:- directive."""
    body: PTerm

@dataclass(frozen=True, slots=True)
class PQuery:
    """?- query."""
    body: PTerm


@dataclass(frozen=True, slots=True)
class PComment:
    """Block comment — used for untranslatable construct warnings."""
    text: str

PItem = Union[PClause, PDCGRule, PDirective, PQuery, PComment]


@dataclass(frozen=True, slots=True)
class PModule:
    """A complete Prolog source file."""
    items: tuple[PItem, ...]
    source_path: str | None = None


# ── Children helper ───────────────────────────────────────────────────

def _children(node) -> list:
    """Yield direct child PTerm/PItem nodes of *node*."""
    if isinstance(node, (PAtom, PVar, PNumber, PString)):
        return []
    if isinstance(node, PCompound):
        return list(node.args)
    if isinstance(node, PList):
        children = list(node.elements)
        if node.tail is not None:
            children.append(node.tail)
        return children
    if isinstance(node, PCurly):
        return [node.body]
    if isinstance(node, PClause):
        children = [node.head]
        if node.body is not None:
            children.append(node.body)
        return children
    if isinstance(node, PDCGRule):
        return [node.head, node.body]
    if isinstance(node, (PDirective, PQuery)):
        return [node.body]
    if isinstance(node, PModule):
        return list(node.items)
    return []


# ── Visitor & Transformer ────────────────────────────────────────────

class PrologVisitor:
    """Walk a Prolog AST without modifying it.

    Subclass and override visit_PAtom, visit_PCompound, etc.
    Default visit methods recurse into children.
    """

    def visit(self, node) -> None:
        method = f"visit_{type(node).__name__}"
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node) -> None:
        for child in _children(node):
            self.visit(child)


class PrologTransformer:
    """Walk and rebuild a Prolog AST, replacing nodes.

    Return the node unchanged to keep it, or return a new node to replace it.
    Return None from a visit_PItem method to delete an item.
    """

    def visit(self, node):
        method = f"visit_{type(node).__name__}"
        transformer = getattr(self, method, self.generic_visit)
        return transformer(node)

    def generic_visit(self, node):
        if isinstance(node, (PAtom, PVar, PNumber, PString)):
            return node
        if isinstance(node, PCompound):
            new_args = tuple(self.visit(a) for a in node.args)
            if new_args == node.args:
                return node
            return dataclasses.replace(node, args=new_args)
        if isinstance(node, PList):
            new_elems = tuple(self.visit(e) for e in node.elements)
            new_tail = self.visit(node.tail) if node.tail is not None else None
            if new_elems == node.elements and new_tail == node.tail:
                return node
            return dataclasses.replace(node, elements=new_elems, tail=new_tail)
        if isinstance(node, PCurly):
            new_body = self.visit(node.body)
            if new_body is node.body:
                return node
            return dataclasses.replace(node, body=new_body)
        if isinstance(node, PClause):
            new_head = self.visit(node.head)
            new_body = self.visit(node.body) if node.body is not None else None
            if new_head is node.head and new_body is node.body:
                return node
            return dataclasses.replace(node, head=new_head, body=new_body)
        if isinstance(node, PDCGRule):
            new_head = self.visit(node.head)
            new_body = self.visit(node.body)
            if new_head is node.head and new_body is node.body:
                return node
            return dataclasses.replace(node, head=new_head, body=new_body)
        if isinstance(node, (PDirective, PQuery)):
            new_body = self.visit(node.body)
            if new_body is node.body:
                return node
            return dataclasses.replace(node, body=new_body)
        if isinstance(node, PModule):
            new_items = []
            for item in node.items:
                result = self.visit(item)
                if result is not None:
                    new_items.append(result)
            new_items = tuple(new_items)
            if new_items == node.items:
                return node
            return dataclasses.replace(node, items=new_items)
        return node


# ── Builder helpers ──────────────────────────────────────────────────

def atom(name: str) -> PAtom:
    return PAtom(name)

def var(name: str) -> PVar:
    return PVar(name)

def anon() -> PVar:
    return PVar("_")

def compound(functor: str, *args: PTerm) -> PCompound:
    return PCompound(functor, args)

def op(name: str, left: PTerm, right: PTerm) -> PCompound:
    """Binary operator as compound: op('+', a, b) -> +(a, b)"""
    return PCompound(name, (left, right))

def prefix(name: str, arg: PTerm) -> PCompound:
    """Prefix operator: prefix('\\+', g) -> \\+(g)"""
    return PCompound(name, (arg,))

def plist(*elements: PTerm, tail: PTerm | None = None) -> PList:
    return PList(elements, tail=tail)

def cons(head: PTerm, tail: PTerm) -> PList:
    """[H|T] shorthand."""
    return PList((head,), tail=tail)

def fact(head: PTerm) -> PClause:
    return PClause(head)

def rule(head: PTerm, body: PTerm) -> PClause:
    return PClause(head, body)

def dcg_rule(head: PTerm, body: PTerm) -> PDCGRule:
    return PDCGRule(head, body)

def directive(body: PTerm) -> PDirective:
    return PDirective(body)

def module(*items: PItem, source_path: str | None = None) -> PModule:
    return PModule(items, source_path=source_path)


# ── Introspection utilities ──────────────────────────────────────────

def variables(term: PTerm) -> set[str]:
    """Collect all variable names in a term (excluding '_')."""
    result: set[str] = set()

    class _Collector(PrologVisitor):
        def visit_PVar(self, node):
            if node.name != "_":
                result.add(node.name)

    _Collector().visit(term)
    return result


def functors(term: PTerm) -> set[tuple[str, int]]:
    """Collect all functor/arity pairs in a term."""
    result: set[tuple[str, int]] = set()

    class _Collector(PrologVisitor):
        def visit_PCompound(self, node):
            result.add((node.functor, len(node.args)))
            self.generic_visit(node)

    _Collector().visit(term)
    return result


def is_ground(term: PTerm) -> bool:
    """True if the term contains no variables."""
    return len(variables(term)) == 0 and not _has_anon(term)


def _has_anon(term: PTerm) -> bool:
    """Check if term contains anonymous variable."""
    found = False

    class _Checker(PrologVisitor):
        def visit_PVar(self, node):
            nonlocal found
            if node.name == "_":
                found = True

    _Checker().visit(term)
    return found


def term_size(term: PTerm) -> int:
    """Number of nodes in the term tree."""
    count = 0

    class _Counter(PrologVisitor):
        def visit(self, node):
            nonlocal count
            count += 1
            super().visit(node)

    _Counter().visit(term)
    return count


def subterms(term: PTerm) -> Iterator[PTerm]:
    """Yield all subterms in depth-first order."""
    yield term
    for child in _children(term):
        yield from subterms(child)
