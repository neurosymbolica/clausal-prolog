"""Quads -- *queries using answer descriptions* (Ulrich Neumerkel): a
``?- Query.`` in a source file, followed by the toplevel answers it gives
(``X = 1 ; X = 2.``), written as terms.  A compiler ignores them (the query
is not a clause, nor the answer descriptions after it); a runner treats each
pair as a test (:mod:`clausal.quad_runner`).

This module is the pure syntax half: what an answer description is, and the
quads of a text.  It does not import the engine.

The grammar is the one of Trealla issue #1063 plus the annotations
``library(quads)`` of Trealla accepts, and a labelled quad
(``name ?- Query.``).
"""
from __future__ import annotations

from dataclasses import dataclass

from clausal.tools.prolog_reader import VarRef

#: Atoms that are answer descriptions by themselves.
DESCRIPTION_ATOMS = frozenset({
    "true", "false", "loops", "...", "ad_infinitum", "sto", "maybe", "waits",
    "unexpected", "inattendue", "other_answer_sequence",
    "instantiation_error"})

#: Compounds (name, arity) that are answer descriptions: the ISO error
#: terms of Neumerkel's grammar, ``throw/1``, ``error/2`` and the stream
#: annotations.
DESCRIPTION_COMPOUNDS = frozenset({
    ("throw", 1), ("error", 2), ("type_error", 2), ("domain_error", 2),
    ("syntax_error", 1), ("representation_error", 1),
    ("resource_error", 1), ("uninstantiation_error", 1),
    ("existence_error", 2), ("permission_error", 3),
    ("evaluation_error", 1), ("outputs", 1), ("inputs", 1), ("peeks", 1)})

#: ``_V = _T``, ``V ~~ T`` (an approximate float), and the connectives.
_CONNECTIVES = frozenset({",", ";", "|"})


def is_answer_description(t) -> bool:
    """True when the reader term *t* is an answer description: ``true``,
    ``false``, ``V = T`` (V a variable), an error term, an annotation, or
    those joined by ``,``, ``;`` and ``|``."""
    if type(t) is str:
        return t in DESCRIPTION_ATOMS
    if type(t) is not tuple or not t or type(t[0]) is not str:
        return False
    name, arity = t[0], len(t) - 1
    if arity == 2 and name in _CONNECTIVES:
        return is_answer_description(t[1]) and is_answer_description(t[2])
    if arity == 2 and name in ("=", "~~"):
        return isinstance(t[1], VarRef)
    return (name, arity) in DESCRIPTION_COMPOUNDS


def is_labelled_query(item) -> bool:
    """A reader item that is ``label ?- Goal.``: the clause ``?-(label,
    Goal)`` (``?-`` is read as an infix operator too)."""
    t = getattr(item, "term", None)
    return (type(item).__name__ == "Clause" and type(t) is tuple
            and len(t) == 3 and t[0] == "?-" and type(t[1]) is str)


@dataclass(frozen=True, slots=True)
class Quad:
    """One quad: the query's term and variable names, and the answer
    description items that followed it (each a ``(term, var_names)``)."""
    line: int
    query: object
    names: dict
    descriptions: tuple
    label: "str | None" = None


def extract_quads(source: str, op_table=None) -> list[Quad]:
    """The quads of *source*, in order.  A query with no description after
    it is a quad with an empty description list (documentation)."""
    from clausal.tools.iso_l3 import _Positions, _item_span, iter_iso  # noqa: PLC0415

    positions = _Positions(source)
    items, _table = iter_iso(source, op_table)
    quads: list[Quad] = []
    open_query = None
    descs: list = []

    def close():
        nonlocal open_query, descs
        if open_query is not None:
            it, line = open_query
            label = None
            term = it.term
            if is_labelled_query(it):
                _, label, term = term
            quads.append(Quad(line, term, dict(it.var_names), tuple(descs),
                              label))
        open_query, descs = None, []

    for it in items:
        kind = type(it).__name__
        if kind == "Query" or is_labelled_query(it):
            close()
            line = positions.line(_item_span(it)) or 0
            open_query = (it, line)
        elif (open_query is not None and kind == "Clause"
              and is_answer_description(it.term)):
            descs.append((it.term, dict(it.var_names)))
        else:
            close()
    close()
    return quads
