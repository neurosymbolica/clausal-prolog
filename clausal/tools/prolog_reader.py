"""Prolog reader — the §1c contract's data heart.

This module implements the ReaderItem IR (frozen dataclasses per the
locked §1c contract) and the P-tree -> (cell, span_tree, var_names)
transformer that is the substance of that contract.

Parser output (``clausal.tools.prolog_ast`` P-nodes) is pure data: this
module only depends on dataclasses and the P-node types (for isinstance
checks) — never on the engine (``clausal.logic.*``). Task 4 appends
``PrologReader`` (the toklex-driving item-at-a-time reader) below the
IR + transformer section defined here.

Cell mapping (locked):
    PAtom      -> .name (str; quoted flag is irrelevant to cells — mangling
                  is the compiler's job)
    PNumber    -> .value (native int/float)
    PString    -> list of 1-char strings ('' -> [])
    PCompound  -> (functor, *arg_cells)
    PList (proper)   -> Python list [cell, ...]
    PList (with tail) -> right-nested cons cells ('.', H, T), folding the
                  elements right-to-left over the transformed tail
    PCurly     -> ('{}', body_cell)
    PVar       -> VarRef(i), first-occurrence numbering; '_' always
                  allocates a fresh index

Span tree (locked, mirrors the cell shape exactly):
    leaf cell (str atom, number, VarRef, char-list-from-PString)
        -> the P-node's (start, end), or (-1, -1) when the P-node's span
           is None (e.g. hand-built P-trees in tests)
    compound tuple cell ('f', c1, ..., cN)
        -> ((start, end), span(c1), ..., span(cN))
    Python-list cell [c1, ..., cN]
        -> ((start, end), [span(c1), ..., span(cN)])
    cons chain synthesized from a PList-with-tail: each synthesized
        ('.', H, T) level gets a compound-shaped span node
        ((start_of_H, end_of_whole_remaining_list), span(H), span(T))
        — i.e. the head span at each level is the REMAINING-LIST extent,
        computed from the current element's start and the tail P-node's
        end (falling back through nested elements/tail when spans are
        None); the innermost T's span is just the tail P-node's own span.
    curly cell ('{}', body_cell)
        -> ((start, end), span(body))
"""

from __future__ import annotations

from dataclasses import dataclass

from clausal.tools.prolog_ast import (
    PAtom,
    PCompound,
    PCurly,
    PList,
    PNumber,
    PString,
    PVar,
)

# ── IR ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VarRef:
    i: int


@dataclass(frozen=True, slots=True)
class Clause:  # fact or rule; term = whole item term as read
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class Directive:  # term = directive body
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class DCGRule:  # term = ('-->', H, B)
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class Query:  # term = query body
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    span: tuple
    message: str
    resumable: bool


# ── P-tree -> (cell, span_tree, var_names) transformer ───────────────

_NO_SPAN = (-1, -1)


def _span_of(node) -> tuple:
    """The (start, end) span of a P-node, or the (-1, -1) placeholder."""
    span = getattr(node, "span", None)
    if span is None:
        return _NO_SPAN
    return span


class _Transform:
    """One transform_term() call's mutable state: name -> first-occurrence
    var index. '_' never reuses an index — every occurrence is fresh."""

    def __init__(self) -> None:
        self._index_by_name: dict[str, int] = {}
        self.var_names: dict[int, str] = {}

    def var_index(self, name: str) -> int:
        if name != "_" and name in self._index_by_name:
            return self._index_by_name[name]
        i = len(self.var_names)
        self.var_names[i] = name
        if name != "_":
            self._index_by_name[name] = i
        return i

    def cell(self, node):
        if isinstance(node, PAtom):
            return node.name
        if isinstance(node, PNumber):
            return node.value
        if isinstance(node, PString):
            return list(node.value)
        if isinstance(node, PVar):
            return VarRef(self.var_index(node.name))
        if isinstance(node, PCompound):
            return (node.functor, *(self.cell(a) for a in node.args))
        if isinstance(node, PCurly):
            return ("{}", self.cell(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return [self.cell(e) for e in node.elements]
            return self._cons_cell(node.elements, node.tail)
        raise TypeError(f"transform_term: unsupported P-node {type(node)!r}")

    def _cons_cell(self, elements, tail):
        if not elements:
            return self.cell(tail)
        head, *rest = elements
        return (".", self.cell(head), self._cons_cell(rest, tail))

    def span(self, node):
        if isinstance(node, (PAtom, PNumber, PVar)):
            return _span_of(node)
        if isinstance(node, PString):
            return _span_of(node)
        if isinstance(node, PCompound):
            return (_span_of(node), *(self.span(a) for a in node.args))
        if isinstance(node, PCurly):
            return (_span_of(node), self.span(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return (_span_of(node), [self.span(e) for e in node.elements])
            return self._cons_span(node.elements, node.tail, _span_of(node))
        raise TypeError(f"transform_term: unsupported P-node {type(node)!r}")

    def _cons_span(self, elements, tail, remaining_span):
        """One level per remaining element; head span = remaining-list
        extent (start of this element, end of the whole remaining list).
        The innermost level's tail span is just the tail P-node's span."""
        if not elements:
            return self.span(tail)
        head, *rest = elements
        head_start, _ = _span_of(head)
        _, remaining_end = remaining_span
        this_span = (head_start, remaining_end)
        return (
            this_span,
            self.span(head),
            self._cons_span(rest, tail, this_span),
        )


def transform_term(pterm) -> tuple[object, object, dict[int, str]]:
    """P-tree -> (cell, span_tree, var_names) per the locked decisions.

    A fresh numbering state is used per call: named variables are numbered
    by first occurrence, and every '_' occurrence allocates a fresh index.
    """
    xf = _Transform()
    cell = xf.cell(pterm)
    span_tree = xf.span(pterm)
    return cell, span_tree, xf.var_names
