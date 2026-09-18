"""Shared Seg* normalisation helpers for runtime dispatch sites.

The runtime / compiler / builtins layer has many dispatch sites that
branch on a target term's container type (``list``, ``str``, ``SegList``,
``Var``, …) and historically only grew a ``SegList`` arm — never a
``SegString`` arm. This left every such site silently dropping
satisfiable goals on ``SegString`` inputs even when the SegString walks
to a plain ``str`` (the C3 SegString-blind-spot cluster).

The helper here is the single place to express "walk a Seg* term to its
ground form when possible; otherwise return it unchanged so the caller
can do whatever it would have done for a non-ground SegList". Dispatch
sites that previously had only a ``SegList`` arm should call
``normalize_seg_input`` before the type test so both ``SegList`` and
``SegString`` are funnelled through the same code path.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.atoms import char_atom, is_char_atom, spelling


def seq_getitem(seq: Any, i: int) -> Any:
    """Element *i* of a ``list`` / ``str`` / ``bytes`` sequence target.

    The Python twin of ``_list_unify.c``'s ``seq_getitem``: a ``str``'s
    element is a CHAR (``char_atom``), a ``list``'s element is itself, and
    a ``bytes``' element is an int code (codes model — never a char).

    Every list-machinery site that reads one element out of a possibly-str
    sequence goes through here, so the Stage B representation flip
    (2026-09-06-atoms-as-cells-strings) is a change to ``char_atom``'s body
    alone.
    """
    if type(seq) is str:
        return char_atom(seq[i])
    return seq[i]


def str_chars(s: str) -> list:
    """Split *s* into its CHARS — the char-term twin of ``list(s)``.

    Used wherever the list machinery splats a ``str`` into a char list
    (star splats, ``ConcreteSeg`` construction, ``_as_items``); the
    inverse is ``join_chars``.
    """
    return [char_atom(c) for c in s]


def join_chars(chars) -> str:
    """Join an iterable of CHARS back into a ``str`` — the char-term twin
    of ``"".join(chars)``. Joins each char's SPELLING, never the char
    object itself (under Stage A dual acceptance a char may already arrive
    as a 1-tuple)."""
    return "".join(spelling(c) for c in chars)


def normalize_seg_input(x: Any) -> Any:
    """Walk a ``SegList`` / ``SegString`` to its ground form (``list`` or
    ``str``) when possible; otherwise return the input unchanged.

    Returns:
      - The plain ``list`` if *x* is a ground ``SegList``.
      - The plain ``str`` if *x* is a ground ``SegString``.
      - The walked (possibly still-non-ground) ``SegList`` / ``SegString``
        when *x* is non-ground — callers can then dispatch on the walked
        container type for the structural-unify path.
      - The input unchanged otherwise (already a list / str / Var /
        non-Seg term).

    The walk is idempotent: calling on a plain ``list`` / ``str`` /
    ``Var`` is a cheap pass-through.
    """
    # STAGE 1 of the atoms-as-str flip: a chars carrier normalises to the
    # str it holds, so every consumer downstream of this funnel that accepts
    # a str as text keeps working unchanged (both spellings accepted until
    # the interim rule is armed).
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(x):
        return chars_text(x)
    from clausal.terms import SegList, SegString, SegBytes
    if isinstance(x, SegList):
        return x.__walk__()
    if isinstance(x, SegString):
        return x.__walk__()
    if isinstance(x, SegBytes):
        return x.__walk__()
    return x


def maybe_promote_to_bytes(result: Any) -> Any:
    """If *result* is a list of all ground ints in [0, 255], return the
    equivalent ``bytes``. Otherwise return *result* unchanged.

    The codes-model parallel of :func:`maybe_promote_to_str`. Per the
    bytes-as-lists promiscuity guard, this is called ONLY at reconstruction
    sites where a ``bytes`` / ``SegBytes`` source was present on the input
    side — never unconditionally — so a plain int-list output never
    spuriously becomes ``bytes``. Bools are excluded (``True``/``False``
    must not coerce to bytes).
    """
    if isinstance(result, list) and result and all(
        isinstance(e, int) and not isinstance(e, bool) and 0 <= e <= 255
        for e in result
    ):
        return bytes(result)
    return result


def maybe_promote_to_str(result: Any) -> Any:
    """If *result* is a list of all ground CHARS, return the equivalent
    ``str``. Otherwise return *result* unchanged.

    This implements the Liskov-substitution / strings-as-lists rule
    confirmed in the Phase 2 design review: a list whose contents are
    *provably* all chars is interchangeable with the
    corresponding str (str ⊂ list-of-chars). The default output type is
    ``list`` — we only upgrade to ``str`` when the upgrade is provable
    from the result elements themselves.

    Used at result-construction sites (head/body output reconstruction,
    star-list builders, SegList walk) to opportunistically promote
    list-of-chars outputs back to str so downstream consumers see the
    natural str shape when one is recoverable. No type-source plumbing
    is required — the property is purely a function of the result
    elements.
    """
    if isinstance(result, list) and result and all(
        is_char_atom(e) for e in result
    ):
        return join_chars(result)
    return result
