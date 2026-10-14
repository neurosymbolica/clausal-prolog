"""Where a cut lands (ISO 7.8.4 scope rules on the GoalOp IR)."""
from __future__ import annotations

from .ir import Alternate, Branch, Cut, GoalOp, IfThenElse, Sequence


def cut_reaches_scope(ir: GoalOp) -> bool:
    """True iff a ``Cut`` in *ir* cuts the scope *ir* is lowered in: cut is
    transparent to conjunction, disjunction and the then/else of an
    if-then-else; everything else (an ITE condition, ``\\+``, a
    meta-call's goal) is a barrier of its own.

    ``Branch`` (the seam's ``if_/3``) lowers its then/else in the enclosing
    scope too, so they are descended as well: a false True only costs a
    sub-generator, a false False would reach a scope with no cut exit."""
    match ir:
        case Cut():
            return True
        case Sequence(ops=ops) | Alternate(ops=ops):
            return any(cut_reaches_scope(op) for op in ops)
        case IfThenElse(then=th, else_=el) | Branch(then=th, else_=el):
            return cut_reaches_scope(th) or cut_reaches_scope(el)
        case _:
            return False
