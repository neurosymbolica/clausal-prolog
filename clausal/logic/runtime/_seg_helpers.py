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
    from clausal.terms import SegList, SegString
    if isinstance(x, SegList):
        return x.__walk__()
    if isinstance(x, SegString):
        return x.__walk__()
    return x
