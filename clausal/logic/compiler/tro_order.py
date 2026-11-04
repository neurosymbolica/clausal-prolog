"""Which tail-recursive clauses may restart in place without changing the
order of answers.

A TRO restart is taken at the END of the predicate's function: the clause
sets the restart flag (``_tro`` in loop mode, ``$tro_state`` in signal
mode), every later clause of the same function still runs, and only then
does the function start over with the tail call's arguments.  An answer of
a later clause would therefore come out before every answer of the tail
call -- clause order reversed.  A clause may restart only when no later
clause of its function can answer in that activation:

- it is the function's last clause;
- it cuts before its tail call (the cut exit skips the later clauses);
- every later clause's head cannot unify with this clause's head
  (``_may_unify``).  The restart is taken only when ``trail.commit_fresh``
  finds no variable older than the activation bound or constrained, so the
  call's arguments were already an instance of this clause's head, and a
  head that cannot unify with that head cannot match them; or
- every later clause is refuted by an arithmetic comparison this clause's
  body made before its tail (``_guard_refutes``): the comparison held on
  the very arguments the later clause would see, so a later head that
  needs two of them identical (``p(N, N)`` after ``I < N``), or a constant
  the comparison rules out, cannot match, and a later clause whose body
  starts with comparisons, one of them the other way (``N =< 0`` after
  ``N > 0``), fails before it does anything else; or
- for the later clauses whose heads might unify, all of them key one
  argument position (``arg_index.head_arg_key``) and the call's argument
  there, bound at entry, keys outside them all -- a runtime test, taken
  beside ``commit_fresh`` (``count(N) :- N > 0, ..., count(M).`` before
  ``count(0).``).

Any other eligible clause makes its tail an ordinary call, as an ISO
machine does while the clause still has an alternative.
"""
from __future__ import annotations

from typing import Any

from clausal.logic.variables import is_var
from clausal.terms import Call, LoadName, Unify
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.logic.cells import CHARS_TAG

from .arg_index import (
    _INDEX_VAR, _arg_to_index_key, _head_arg, head_arg_key,
)

#: Recursion bound of :func:`_may_unify` (deeper is "may unify").
_DEPTH = 50


def _subst(term: Any, var: Any, value: Any, depth: int = 0) -> Any:
    """*term* with the variable *var* (by identity) replaced by *value*
    inside lists, cells and star patterns; other nodes are left as they
    are (a more general head, so :func:`_may_unify` only says yes more)."""
    if term is var:
        return value
    if depth > _DEPTH:
        return term
    t = type(term)
    if t is list:
        return [_subst(x, var, value, depth + 1) for x in term]
    if t is tuple and term and type(term[0]) is str and term[0] != CHARS_TAG:
        return (term[0], *(_subst(x, var, value, depth + 1) for x in term[1:]))
    if isinstance(term, StarUnpack):
        inner = _subst(term.value, var, value, depth + 1)
        return term if inner is term.value else StarUnpack(value=inner)
    return term


def _occurs(var: Any, term: Any, depth: int = 0) -> bool:
    if term is var:
        return True
    if depth > _DEPTH:
        return True
    if type(term) is list or (type(term) is tuple and term):
        return any(_occurs(var, x, depth + 1) for x in term)
    if isinstance(term, StarUnpack):
        return _occurs(var, term.value, depth + 1)
    return False


def effective_head_args(clause, arity: int) -> list | None:
    """The head's arguments with the clause's LEADING body unifications of
    a variable folded in (the front ends write ``p(0)`` as ``p(X) :- X = 0``),
    or None when the head has no readable arguments."""
    args = [_head_arg(clause, i, arity) for i in range(arity)]
    if any(a is _INDEX_VAR for a in args):
        return None
    for goal in clause.body or ():
        sides = _unify_sides(goal)
        if sides is None:
            break
        left, right = sides
        if is_var(left) and not is_var(right):
            var, value = left, right
        elif is_var(right) and not is_var(left):
            var, value = right, left
        else:
            break
        if _occurs(var, value):
            break
        args = [_subst(a, var, value) for a in args]
    return args


def _unify_sides(goal: Any):
    """``(left, right)`` of a unification goal (``Unify``, or ISO ``=/2``
    called by name), or None."""
    if isinstance(goal, Unify):
        return goal.left, goal.right
    if (isinstance(goal, Call) and isinstance(goal.func, LoadName)
            and goal.func.name == "=" and len(goal.args) == 2
            and not goal.kwargs):
        return goal.args[0], goal.args[1]
    return None


def _list_parts(term: list):
    """``(fixed elements, has a tail pattern)``, or None for a pattern
    with a star that is not the last element."""
    fixed: list = []
    while True:
        for k, x in enumerate(term):
            if isinstance(x, StarUnpack):
                if k != len(term) - 1:
                    return None
                fixed.extend(term[:k])
                tail = x.value
                break
        else:
            return fixed + list(term), False
        if type(tail) is not list:
            return fixed, True
        term = tail         # ``[A, *[B, *T]]`` is ``[A, B, *T]``


def _is_cell(term: Any) -> bool:
    return (type(term) is tuple and len(term) > 0 and type(term[0]) is str
            and term[0] != CHARS_TAG)


def _may_unify(a: Any, b: Any, env, depth: int = 0) -> bool:
    """False only when the head patterns *a* and *b* (variables renamed
    apart) can never unify; True whenever unsure."""
    if depth > _DEPTH or is_var(a) or is_var(b):
        return True
    if isinstance(a, StarUnpack) or isinstance(b, StarUnpack):
        return True
    ka = _arg_to_index_key(a, env)
    kb = _arg_to_index_key(b, env)
    if ka is not _INDEX_VAR and kb is not _INDEX_VAR:
        # Two terms keyed differently never unify (what indexing relies on).
        if ka != kb:
            return False
        if _is_cell(a) and _is_cell(b) and len(a) == len(b):
            return all(_may_unify(x, y, env, depth + 1)
                       for x, y in zip(a[1:], b[1:]))
        return True
    ta, tb = type(a), type(b)
    if ta is list and tb is list:
        pa, pb = _list_parts(a), _list_parts(b)
        if pa is None or pb is None:
            return True
        (fa, sa), (fb, sb) = pa, pb
        if not sa and not sb and len(fa) != len(fb):
            return False
        if (not sa and sb and len(fa) < len(fb)) or (
                not sb and sa and len(fb) < len(fa)):
            return False
        return all(_may_unify(x, y, env, depth + 1) for x, y in zip(fa, fb))
    # A number is never a list.
    if (ta is list and tb in (int, float)) or (tb is list and ta in (int, float)):
        return False
    return True


def heads_may_unify(args_a: list | None, args_b: list | None, env) -> bool:
    if args_a is None or args_b is None or len(args_a) != len(args_b):
        return True
    return all(_may_unify(x, y, env) for x, y in zip(args_a, args_b))


# ── Arithmetic guards ────────────────────────────────────────────────────
#
# A comparison is ``(op, left, right)`` with op one of ``<  >  =<  >=  =:=
# =\=`` and each side a canonical expression: an int, ``("$pos", k)`` for
# the head's top-level argument k, or ``("$e", name, *operands)``.  A
# comparison over anything else (a body variable, a float, an unknown
# node) is not read.

from clausal.pythonic_ast.nodes import (  # noqa: E402
    Lt, LtE, Gt, GtE, ArithEq, ArithNeq, BinOp, CmpOp,
)

_CMP_NODES = {Lt: "<", LtE: "=<", Gt: ">", GtE: ">=",
              ArithEq: "=:=", ArithNeq: "=\\="}
_CMP_NAMES = frozenset(("<", "=<", ">", ">=", "=:=", "=\\="))
_FLIP = {"<": ">", ">": "<", "=<": ">=", ">=": "=<",
         "=:=": "=:=", "=\\=": "=\\="}
#: The comparisons that cannot hold over (L, R) when the key one does.
_EXCLUDES = {
    "<": frozenset((">", ">=", "=:=")),
    ">": frozenset(("<", "=<", "=:=")),
    "=<": frozenset((">",)),
    ">=": frozenset(("<",)),
    "=:=": frozenset(("<", ">", "=\\=")),
    "=\\=": frozenset(("=:=",)),
}
#: Evaluable int operators of a ground canonical expression.
_INT_OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "Add": lambda a, b: a + b, "Sub": lambda a, b: a - b,
            "Mult": lambda a, b: a * b}


def _canon(term: Any, positions: dict, depth: int = 0) -> Any:
    """The canonical expression of *term*, or None."""
    if depth > _DEPTH:
        return None
    if is_var(term):
        k = positions.get(id(term))
        return None if k is None else ("$pos", k)
    if type(term) is int:
        return term
    if _is_cell(term) and len(term) in (2, 3):
        parts = [_canon(x, positions, depth + 1) for x in term[1:]]
        return None if any(p is None for p in parts) else ("$e", term[0], *parts)
    if isinstance(term, BinOp) and not isinstance(term, CmpOp):
        left = _canon(getattr(term, "left", None), positions, depth + 1)
        right = _canon(getattr(term, "right", None), positions, depth + 1)
        if left is None or right is None:
            return None
        return ("$e", type(term).__name__, left, right)
    return None


def _comparison(goal: Any, positions: dict):
    """``(op, left, right)`` for an arithmetic comparison goal, or None."""
    op = _CMP_NODES.get(type(goal))
    if op is not None:
        left, right = goal.left, goal.right
    elif (isinstance(goal, Call) and isinstance(goal.func, LoadName)
          and goal.func.name in _CMP_NAMES and len(goal.args) == 2
          and not goal.kwargs):
        op = goal.func.name
        left, right = goal.args
    else:
        return None
    left = _canon(left, positions)
    right = _canon(right, positions)
    if left is None or right is None:
        return None
    return op, left, right


def _positions(args: list) -> dict:
    """``{id(var): k}`` for the head's top-level variable arguments."""
    out: dict = {}
    for k, a in enumerate(args):
        if is_var(a) and id(a) not in out:
            out[id(a)] = k
    return out


def _evaluate(expr: Any):
    """The int value of a ground canonical expression, or None."""
    if type(expr) is int:
        return expr
    if type(expr) is tuple and expr[0] == "$e" and len(expr) == 4:
        fn = _INT_OPS.get(expr[1])
        a, b = _evaluate(expr[2]), _evaluate(expr[3])
        if fn is None or a is None or b is None:
            return None
        return fn(a, b)
    return None


def _holds(op: str, a: int, b: int) -> bool:
    return {"<": a < b, ">": a > b, "=<": a <= b, ">=": a >= b,
            "=:=": a == b, "=\\=": a != b}[op]


def _replace_positions(expr: Any, subst: dict) -> Any:
    if type(expr) is tuple and expr and expr[0] == "$pos":
        return subst.get(expr[1], expr)
    if type(expr) is tuple and expr and expr[0] == "$e":
        return (*expr[:2], *(_replace_positions(x, subst) for x in expr[2:]))
    return expr


def guard_facts(clause, arity: int) -> list:
    """The comparisons over the head's arguments that the body of the TRO
    clause *clause* makes before its tail call (every goal but the last
    runs before the restart)."""
    args = [_head_arg(clause, i, arity) for i in range(arity)]
    if any(a is _INDEX_VAR for a in args):
        return []
    positions = _positions(args)
    facts = []
    for goal in list(clause.body or ())[:-1]:
        c = _comparison(goal, positions)
        if c is not None:
            facts.append(c)
    return facts


def _guard_refutes(facts: list, later, later_args: list | None,
                   arity: int) -> bool:
    """True when the comparisons *facts* (which held on the call's
    arguments) show the clause *later* cannot answer the same call."""
    if not facts or later_args is None:
        return False
    # Its head: constants it needs at some positions, and positions it
    # needs identical to an earlier one (the same variable).
    subst: dict = {}
    first_at: dict = {}
    for k, a in enumerate(later_args):
        if type(a) is int:
            subst[k] = a
        elif is_var(a):
            if id(a) in first_at:
                subst[k] = ("$pos", first_at[id(a)])
            else:
                first_at[id(a)] = k
    for op, left, right in facts:
        l2 = _replace_positions(left, subst)
        r2 = _replace_positions(right, subst)
        lv, rv = _evaluate(l2), _evaluate(r2)
        if lv is not None and rv is not None and not _holds(op, lv, rv):
            return True
        if l2 == r2 and op in ("<", ">", "=\\="):
            return True
    # Its body, after its leading unifications: comparisons, the first of
    # them that cannot hold where the facts did refuting it.  A comparison
    # before that one must not be able to raise (or the later clause would
    # raise before the tail call's answers): each of its sides is an int
    # or a side some fact compared, evaluated without error then.
    raw = [_head_arg(later, i, arity) for i in range(arity)]
    positions = _positions(raw)
    seen = {side for _, left, right in facts for side in (left, right)}
    body = list(later.body or ())
    k = 0
    while k < len(body) and _unify_sides(body[k]) is not None:
        k += 1
    for goal in body[k:]:
        if goal is True:            # ``true``
            continue
        c = _comparison(goal, positions)
        if c is None:
            return False
        op2, l2, r2 = c
        for op, left, right in facts:
            if (left, right) == (l2, r2) and op2 in _EXCLUDES[op]:
                return True
            if (left, right) == (r2, l2) and _FLIP[op2] in _EXCLUDES[op]:
                return True
            if _interval_disjoint(op, left, right, op2, l2, r2):
                return True
        if not all(type(x) is int or x in seen for x in (l2, r2)):
            return False
    return False


def _bound(op: str, left: Any, right: Any):
    """``(expr, op, int)`` with the constant on the right, or None."""
    if type(right) is int and type(left) is not int:
        return left, op, right
    if type(left) is int and type(right) is not int:
        return right, _FLIP[op], left
    return None


def _interval_disjoint(op1, l1, r1, op2, l2, r2) -> bool:
    """True when ``E op1 c1`` and ``E op2 c2`` cannot both hold."""
    a, b = _bound(op1, l1, r1), _bound(op2, l2, r2)
    if a is None or b is None or a[0] != b[0]:
        return False
    (_, o1, c1), (_, o2, c2) = a, b

    def interval(o, c):
        # (lo, lo_open, hi, hi_open) over the reals; None for =\=.
        return {"<": (None, False, c, True), "=<": (None, False, c, False),
                ">": (c, True, None, False), ">=": (c, False, None, False),
                "=:=": (c, False, c, False)}.get(o)
    i1, i2 = interval(o1, c1), interval(o2, c2)
    if i1 is None or i2 is None:
        return False
    lo, lo_open = i1[0], i1[1]
    if i2[0] is not None and (lo is None or i2[0] > lo or (
            i2[0] == lo and i2[1])):
        lo, lo_open = i2[0], i2[1]
    hi, hi_open = i1[2], i1[3]
    if i2[2] is not None and (hi is None or i2[2] < hi or (
            i2[2] == hi and i2[3])):
        hi, hi_open = i2[2], i2[3]
    if lo is None or hi is None:
        return False
    return lo > hi or (lo == hi and (lo_open or hi_open))


def _cuts_before_tail(clause, db) -> bool:
    from . import ir as _ir
    from .terms_to_goalop import terms_to_goalop
    body_ir = terms_to_goalop(clause.body, db=db)
    ops = body_ir.ops if isinstance(body_ir, _ir.Sequence) else [body_ir]
    return any(isinstance(op, _ir.Cut) for op in ops[:-1])


def order_safe_restarts(clauses: list, tro_indices, arity: int, db,
                        env) -> dict:
    """``{clause index: None | (pos, keys)}`` for the TRO-eligible clauses
    (*tro_indices*) of one function that may restart in place: None for an
    unconditional restart, ``(pos, keys)`` for one taken only when the
    argument at *pos*, bound at entry, keys outside *keys* (see the module
    docstring).  The other eligible clauses make the ordinary call."""
    last = len(clauses) - 1
    out: dict = {}
    heads: dict = {}

    def head(j):
        if j not in heads:
            heads[j] = effective_head_args(clauses[j], arity)
        return heads[j]

    for i in sorted(tro_indices):
        if i == last or _cuts_before_tail(clauses[i], db):
            out[i] = None
            continue
        mine = head(i)
        facts = guard_facts(clauses[i], arity)
        rest = [j for j in range(i + 1, len(clauses))
                if heads_may_unify(mine, head(j), env)
                and not _guard_refutes(facts, clauses[j], head(j), arity)]
        if not rest:
            out[i] = None
            continue
        for pos in range(arity):
            # Where this clause's own head keys the argument, a restart
            # has it keyed so, and that key is among the later ones (or
            # those heads could not unify): the test could never pass.
            if head_arg_key(clauses[i], pos, arity, env) is not _INDEX_VAR:
                continue
            keys = [head_arg_key(clauses[j], pos, arity, env) for j in rest]
            if any(k is _INDEX_VAR for k in keys):
                continue
            try:
                out[i] = (pos, frozenset(keys))
            except TypeError:
                continue
            break
    return out
