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


# ─────────────────────────────────────────────────────────────────────────────
# Cut over a tabled call (XSB's rule, ruling Q1 -- provisional)
# ─────────────────────────────────────────────────────────────────────────────

#: What a ``!`` or an if-then-else commit does when its scope holds a call to
#: a tabled predicate.  ``"refuse"`` is XSB's static rule: "cuts are allowed
#: within tabled predicates subject to the restriction that the scope of a cut
#: cannot include a call to a tabled predicate" -- the compiler checks it and
#: aborts the load (:class:`~.ir.CutOverTableError`).  ``"run"`` is Scryer's
#: behaviour: compile the cut as written (it has no observable effect on the
#: table's completion).  THE ONE SWITCH: :func:`check_cut_over_tabled` is the
#: only reader, and the only caller is ``goal_shallow._compile_body_impl``, so
#: relaxing the ruling to Scryer's is setting this to ``"run"``.
CUT_OVER_TABLED_CALL = "refuse"


def tabled_calls_in_cut_scope(ir: GoalOp, db) -> list[tuple[str, int]]:
    """Calls to tabled predicates that a ``Cut`` (or an ``IfThenElse``
    condition's commit) would cut over: every ``SubCall`` executed before
    the cut in the same barrier scope.  XSB's compile-time rule.

    A barrier (``\\+``, an ITE condition, a meta-call's goal) is a scope of
    its own: it is scanned with an empty "before" list, so a cut inside it
    is checked against the tabled calls in IT, never against the enclosing
    scope's.  ``\\+``, ``once/1`` and the other meta-calls are not cuts
    themselves (XSB's check is about ``!`` and ``->``)."""
    from .tabled_naf import _resolve_tabled_call
    from .ir import META_GOAL_POSITIONS, MetaCall, Negate, SubCall
    found: list[tuple[str, int]] = []

    def report(xs) -> None:
        found.extend(x for x in xs if x not in found)

    def scan(op: GoalOp, left: list) -> None:
        match op:
            case Sequence(ops=ops):
                for o in ops:
                    scan(o, left)
            case Alternate(ops=ops):
                before = list(left)
                for o in ops:
                    branch = list(before)
                    scan(o, branch)
                    left.extend(x for x in branch if x not in left)
            case Cut():
                report(left)
            case IfThenElse(test=t, then=th, else_=el):
                inner: list = []
                scan(t, inner)                 # the commit cuts over the test's calls
                report(inner)
                before = list(left)
                scan(th, left)
                alt = before
                scan(el, alt)
                left.extend(x for x in alt if x not in left)
            case Branch(test=t, then=th, else_=el):
                scan(t, left)
                before = list(left)
                scan(th, left)
                alt = before
                scan(el, alt)
                left.extend(x for x in alt if x not in left)
            case Negate(op=inner_op):
                scan(inner_op, [])
            case MetaCall(kind=kind, args=margs):
                from .terms_to_goalop import _convert
                for key in META_GOAL_POSITIONS.get(kind, ()):
                    if key not in margs:
                        continue
                    inner = margs[key]
                    if not isinstance(inner, GoalOp):
                        try:
                            inner = _convert(inner, db)
                        except NotImplementedError:
                            continue
                    scan(inner, [])
            case SubCall():
                pi = (op.fname, op.arity)
                if pi not in left and _resolve_tabled_call(op.fname, op.arity, db) is not None:
                    left.append(pi)
            case _:
                pass

    scan(ir, [])
    return found


def check_cut_over_tabled(ir: GoalOp, db, goals=()) -> None:
    """Raise :class:`~.ir.CutOverTableError` if a cut in *ir* would cut over
    a tabled call -- under :data:`CUT_OVER_TABLED_CALL` ``== "refuse"``.

    Only a ``.pl`` db can hold a ``Cut``/``IfThenElse`` node (the converter
    refuses them elsewhere), so every other body returns before the walk:
    cut-free code pays one attribute read."""
    if CUT_OVER_TABLED_CALL != "refuse":
        return
    from clausal.logic.builtins.call_body import cut_allowed
    if not cut_allowed(db):
        return
    over = tabled_calls_in_cut_scope(ir, db)
    if over:
        from .ir import CutOverTableError
        pos = next((p for p in (getattr(g, "position", None) for g in goals)
                    if p), None)
        raise CutOverTableError(over, line=pos[0] if pos else None)
