"""Which tail-recursive clauses may restart in place without changing the
order of answers.

A TRO restart is taken at the END of the predicate's function: the clause
sets the restart flag (``_tro`` in loop mode, ``$tro_state`` and the local
``_tro_sig`` in signal mode) and the function starts over with the tail
call's arguments.  Whatever a later clause of the function did in that
activation would come before every answer of the tail call -- clause order
reversed.  A clause may restart only when no later clause of its function
can answer or act in that activation, and once it has, the later clauses
are skipped (the builder's arm guards):

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
  ``N > 0``), fails before it does anything else -- except bind what its
  head binds, which must wake nothing: each such argument ground, or
  checked at run time to wake nothing (``head_bind_checks``;
  ``w(N, 0) :- N =< 0`` with X frozen); or
- for the later clauses whose heads might unify, all of them key one
  argument position (``arg_index.head_arg_key``) and the call's argument
  there, bound at entry, keys outside them all -- a runtime test, taken
  beside ``commit_fresh`` (``count(N) :- N > 0, ..., count(M).`` before
  ``count(0).``).

Any other eligible clause makes its tail an ordinary call, as an ISO
machine does while the clause still has an alternative.

The unifications a front end puts at the start of a body for a head
argument (``p(0)`` written ``p(X) :- X = 0``, a ``Unify`` node) are read
as part of the head; a ``=/2`` written in the source is a goal of its own.
In the seam both are ``Unify``, so a seam body's leading ``X is 0`` counts
as head there.
"""
from __future__ import annotations

from typing import Any

from clausal.logic.variables import is_var
from clausal.terms import Call, LoadName, Unify
from clausal.pythonic_ast.nodes import StarUnpack, TupleLiteral
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


def effective_head_args(clause, arity: int, iso_unify: bool = True):
    """The head's arguments with the clause's LEADING body unifications of
    a variable folded in (the front ends write ``p(0)`` as ``p(X) :- X = 0``),
    or None when the head has no readable arguments.

    *iso_unify* folds a ``=/2`` goal written in the source too.  That is
    right for the restarting clause (every goal before its tail ran, binding
    nothing older), but not for a later clause, whose written ``X = 0``
    runs as a goal -- after its head, waking what it binds -- where the
    front end's ``Unify`` is part of the head (see
    :func:`folded_head_args`)."""
    return folded_head_args(clause, arity, iso_unify)[0]


def folded_head_args(clause, arity: int, iso_unify: bool = False):
    """``(args, n)``: :func:`effective_head_args` and how many leading body
    goals it folded."""
    args = [_head_arg(clause, i, arity) for i in range(arity)]
    if any(a is _INDEX_VAR for a in args):
        return None, 0
    args = [_as_cells(a) for a in args]
    n = 0
    for goal in clause.body or ():
        if isinstance(goal, Unify):
            left, right = goal.left, goal.right
        elif iso_unify and _unify_sides(goal) is not None:
            left, right = _unify_sides(goal)
        else:
            break
        if is_var(left) and not is_var(right):
            var, value = left, right
        elif is_var(right) and not is_var(left):
            var, value = right, left
        else:
            break
        value = _as_cells(value)
        if _occurs(var, value) or not any(_occurs(var, a) for a in args):
            break
        args = [_subst(a, var, value) for a in args]
        n += 1
    return args, n


def _as_cells(term: Any, depth: int = 0) -> Any:
    """*term* with the seam's tuple-literal nodes (``('f', 1)`` in a head,
    which the seam front end leaves as ``TupleLiteral``) read as the cells
    they build; lists and cells are walked, everything else is kept."""
    if depth > _DEPTH:
        return term
    if isinstance(term, TupleLiteral):
        return tuple(_as_cells(x, depth + 1) for x in term.elements)
    if type(term) is list:
        return [_as_cells(x, depth + 1) for x in term]
    if type(term) is tuple and term and type(term[0]) is str:
        return (term[0], *(_as_cells(x, depth + 1) for x in term[1:]))
    if isinstance(term, StarUnpack):
        inner = _as_cells(term.value, depth + 1)
        return term if inner is term.value else StarUnpack(value=inner)
    return term


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


def _list_tail(term: list):
    """The tail of a list pattern whose last element is a star (stars of
    list values flattened as in :func:`_list_parts`)."""
    while type(term) is list and term and isinstance(term[-1], StarUnpack):
        term = term[-1].value
    return term


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


def guard_facts(clause, arity: int):
    """``(facts, ground)``: the comparisons over the head's arguments that
    the body of the TRO clause *clause* makes before its tail call (every
    goal but the last runs before the restart), and the ids of the
    variables known ground whenever the clause restarts -- evaluated by an
    ISO comparison or the right side of ``is/2`` before the tail (either
    raises on an unbound one)."""
    args = [_head_arg(clause, i, arity) for i in range(arity)]
    if any(a is _INDEX_VAR for a in args):
        return [], frozenset()
    positions = _positions(args)
    facts = []
    ground: set = set()
    for goal in list(clause.body or ())[:-1]:
        c = _comparison(goal, positions)
        if c is not None:
            facts.append(c)
        if (isinstance(goal, Call) and isinstance(goal.func, LoadName)
                and len(goal.args) == 2 and not goal.kwargs):
            if goal.func.name in _CMP_NAMES:
                _vars_of(goal.args, ground)
            elif goal.func.name == "is":
                _vars_of(goal.args, ground)
    return facts, frozenset(ground)


def _vars_of(term: Any, out: set, depth: int = 0) -> None:
    """Add the ids of the variables in *term* (lists, cells, stars) to
    *out*."""
    if depth > _DEPTH:
        return
    if is_var(term):
        out.add(id(term))
    elif type(term) is list or (type(term) is tuple and term):
        for x in term:
            _vars_of(x, out, depth + 1)
    elif isinstance(term, StarUnpack):
        _vars_of(term.value, out, depth + 1)


def _is_ground(term: Any, ground: frozenset, depth: int = 0) -> bool:
    """True when *term*, a head pattern, is ground whenever the clause
    restarts: no variable in it but ones in *ground*."""
    if depth > _DEPTH:
        return False
    if is_var(term):
        return id(term) in ground
    if type(term) is list or (type(term) is tuple and term):
        return all(_is_ground(x, ground, depth + 1) for x in term)
    if isinstance(term, StarUnpack):
        return _is_ground(term.value, ground, depth + 1)
    return type(term) in (int, float, str, bytes, bool) or term is None


def _pattern_vars(term: Any, depth: int = 0) -> list:
    """The variables of a head pattern, in order, repeats included; None
    for a node this reading does not know."""
    if depth > _DEPTH:
        return None
    if is_var(term):
        return [term]
    if type(term) is list or (type(term) is tuple and term):
        out = []
        for x in term:
            sub = _pattern_vars(x, depth + 1)
            if sub is None:
                return None
            out.extend(sub)
        return out
    if isinstance(term, StarUnpack):
        return _pattern_vars(term.value, depth + 1)
    if type(term) in (int, float, str, bytes, bool) or term is None:
        return []
    return None


def _shallow(p) -> bool:
    """A cell or list pattern every element of which is a variable."""
    if _is_cell(p):
        return all(is_var(x) for x in p[1:])
    if type(p) is list:
        parts = _list_parts(p)
        if parts is None:
            return False
        fixed, star = parts
        # Exactly [H|T]: one cell.  [H] is '.'(H, []) and [H, G|T] two
        # cells deep -- against a partial list they bind its tail.
        return (len(fixed) == 1 and star and is_var(fixed[0])
                and is_var(_list_tail(p)))
    return False


def head_bind_checks(later_args: list, mine: list, ground: frozenset):
    """What unifying the later head *later_args* with a call that is an
    instance of the restarting head *mine* binds, as the run-time checks
    under which none of it wakes a goal; None when that cannot be shown.

    A check is ``("plain", k)`` -- the argument at k atomic or an unbound
    variable without attributes (``plain_arg``) --, ``("noatt", k)`` -- not
    an unbound variable with attributes (``not_attvar``) --, ``("pair",
    k, q)`` -- binding the arguments at k and q to each other wakes nothing
    (``safe_pair``) -- or ``("subnoatt", k, path)`` -- the subterm of
    argument k at *path* is no attributed variable (``sub_not_attvar``).  Where *mine* has a ground term (``ground``: the
    variables a comparison or ``is/2`` evaluated), the argument IS that
    term, and the later pattern binds only its own fresh variables there."""
    # id(var) -> "ground" | ("top", k) | ("nested", k, path): the value the
    # later variable was bound to -- ground, argument k itself, or the
    # subterm of argument k at *path* (cell argument indices; None when the
    # way to it is not through cells only).
    seen: dict = {}
    checks: set = set()

    def bind_values(a, b):
        """A later variable met again: its value *a* and the subterm *b*
        are unified.  True when the checks added show it wakes nothing."""
        if a == "ground" and b == "ground":
            return True
        if a == "ground" or b == "ground":
            other = b if a == "ground" else a
            if other[0] != "top":
                return False
            checks.add(("plain", other[1]))
            return True
        if a[0] == "top" and b[0] == "top":
            if a[1] != b[1]:
                checks.add(("pair", min(a[1], b[1]), max(a[1], b[1])))
            return True
        # One argument and one subterm of an argument: the argument atomic
        # or a plain variable, and the subterm no attributed variable (of
        # two variables the newer is bound).
        top, nested = (a, b) if a[0] == "top" else (b, a)
        if top[0] != "top" or nested[2] is None:
            return False
        checks.add(("plain", top[1]))
        checks.add(("subnoatt", nested[1], nested[2]))
        return True

    def meet(var, value):
        if id(var) in seen:
            return bind_values(seen[id(var)], value)
        seen[id(var)] = value
        return True

    def match(p, r, k, path):
        """Unify later pattern *p* with the argument subterm the restarting
        pattern *r* describes: argument k itself when *path* is (), else
        its subterm at *path* (None: not reachable through cells)."""
        top = path == ()
        value = "ground" if _is_ground(r, ground) else (
            ("top", k) if top else ("nested", k, path))
        if is_var(p):
            return meet(p, value)
        pv = _pattern_vars(p)
        if pv is None:
            return False
        if value == "ground":
            # The argument is that ground term: the pattern's variables are
            # bound to ground subterms, nothing of the call is bound.
            return all(meet(v, "ground") for v in pv)
        if is_var(r):
            if not top:
                return False
            ids = [id(v) for v in pv]
            if (_shallow(p) and len(set(ids)) == len(ids)
                    and not any(i in seen for i in ids)):
                # One functor over distinct fresh variables (``s(A)``,
                # ``[H|T]``): binds only them -- unless the argument is
                # itself an attributed variable.  A constant or a deeper
                # pattern inside would bind into the argument.
                checks.add(("noatt", k))
                cell = _is_cell(p)
                for j, v in enumerate(p[1:] if cell else pv, 1):
                    seen[id(v)] = ("nested", k, (j,) if cell else None)
                return True
            # An argument that is atomic or a plain variable: the pattern
            # fails, or the variable is bound to a copy of it.
            checks.add(("plain", k))
            for v in pv:
                seen.setdefault(id(v), ("nested", k, None))
            return True
        # Both structured: follow the shape the call already has.
        if _is_cell(p) and _is_cell(r) and len(p) == len(r) and p[0] == r[0]:
            return all(match(x, y, k, None if path is None else path + (j,))
                       for j, (x, y) in enumerate(zip(p[1:], r[1:]), 1))
        if type(p) is list and type(r) is list:
            pp, rp = _list_parts(p), _list_parts(r)
            if pp is None or rp is None:
                return False
            (fp, sp), (fr, sr) = pp, rp
            if len(fp) != len(fr) or sp != sr:
                return False
            if not all(match(x, y, k, None) for x, y in zip(fp, fr)):
                return False
            return not sp or match(_list_tail(p), _list_tail(r), k, None)
        return False

    if mine is None or later_args is None or len(mine) != len(later_args):
        return None
    for k, (p, r) in enumerate(zip(later_args, mine)):
        if not match(p, r, k, ()):
            return None
    return frozenset(checks)


def _guard_refutes(facts: list, ground, later, arity: int, mine=None):
    """None when the comparisons *facts* (which held on the call's
    arguments) do not show the clause *later* cannot answer the same call;
    otherwise the argument positions that must hold no attributed variable
    for it to be passed over without a trace (empty: none).

    Passed over, the later clause must also do nothing ISO would let it do
    before it fails.  A head that cannot unify does nothing (goals woken by
    a head unification run only once it has succeeded).  A head that
    unifies and then fails a comparison has bound what it binds first, and
    an attributed variable bound wakes its goals -- so what it binds must be
    shown to wake nothing (``head_bind_checks`` against the restarting head
    *mine*), statically or by run-time checks.  Returns the checks."""
    later_args, folded = folded_head_args(later, arity)
    if not facts or later_args is None:
        return None
    # Its head: constants it needs at some positions, and positions it
    # needs identical to an earlier one (the same variable).
    subst: dict = {}
    first_at: dict = {}
    for k, a in enumerate(later_args):
        if is_var(a):
            if id(a) in first_at:
                subst[k] = ("$pos", first_at[id(a)])
            else:
                first_at[id(a)] = k
        elif type(a) is int:
            subst[k] = a
    for op, left, right in facts:
        l2 = _replace_positions(left, subst)
        r2 = _replace_positions(right, subst)
        lv, rv = _evaluate(l2), _evaluate(r2)
        if lv is not None and rv is not None and not _holds(op, lv, rv):
            return frozenset()
        if l2 == r2 and op in ("<", ">", "=\\="):
            return frozenset()
    # Its body, after the unifications that are part of its head:
    # comparisons, the first of them that cannot hold where the facts did
    # refuting it.  A comparison before that one must not be able to raise
    # (or the later clause would raise before the tail call's answers):
    # each of its sides is an int or a side some fact compared, evaluated
    # without error then.
    raw = [_head_arg(later, i, arity) for i in range(arity)]
    positions = _positions(raw)
    seen = {side for _, left, right in facts for side in (left, right)}
    for goal in list(later.body or ())[folded:]:
        if goal is True:            # ``true``
            continue
        c = _comparison(goal, positions)
        if c is None:
            return None
        op2, l2, r2 = c
        for op, left, right in facts:
            if ((left, right) == (l2, r2) and op2 in _EXCLUDES[op]) or (
                    (left, right) == (r2, l2) and _FLIP[op2] in _EXCLUDES[op]) or (
                    _interval_disjoint(op, left, right, op2, l2, r2)):
                return head_bind_checks(later_args, mine, ground)
        if not all(type(x) is int or x in seen for x in (l2, r2)):
            return None
    return None


def not_attvar(d) -> bool:
    """Runtime: *d* is not an unbound variable with attributes."""
    return not is_var(d) or getattr(d, "attrs", None) is None


def sub_not_attvar(d, path) -> bool:
    """Runtime: the subterm of the dereferenced argument *d* at *path*
    (cell argument indices) exists and is not an unbound variable with
    attributes."""
    from clausal.logic.variables import deref
    t = d
    for i in path:
        t = deref(t)
        if type(t) is not tuple or len(t) <= i:
            return False
        t = t[i]
    return not_attvar(deref(t))


def safe_pair(a, b) -> bool:
    """Runtime: unifying the dereferenced arguments *a* and *b* wakes no
    goal.  A variable without attributes bound to a term wakes nothing;
    of two variables the newer is bound, so both must be plain; two
    non-variables bind nothing when one is atomic."""
    av, bv = is_var(a), is_var(b)
    a_plain = av and getattr(a, "attrs", None) is None
    b_plain = bv and getattr(b, "attrs", None) is None
    if av and bv:
        return a_plain and b_plain
    if av:
        return a_plain
    if bv:
        return b_plain
    return type(a) in (int, str, float) or type(b) in (int, str, float)


def plain_arg(d) -> bool:
    """Runtime: binding the dereferenced argument *d* in a head wakes no
    goal -- it is an int, float or atom, or an unbound variable without
    attributes.  (Anything else may hold an attributed variable.)"""
    t = type(d)
    if t is int or t is str or t is float:
        return True
    return is_var(d) and getattr(d, "attrs", None) is None


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
    """``{clause index: condition}`` for the TRO-eligible clauses
    (*tro_indices*) of one function that may restart in place, the others
    making the ordinary call (see the module docstring).  The condition is
    None for an unconditional restart, else ``(keys, checks)``: *keys* None
    or ``(pos, key set)`` -- the argument at *pos*, bound at entry, keys
    outside the set -- and *checks* those of ``head_bind_checks``.  When a clause restarts, no later clause of its function
    can answer or act, and the function skips them."""
    last = len(clauses) - 1
    out: dict = {}
    heads: dict = {}

    def head(j):
        if j not in heads:
            heads[j] = effective_head_args(clauses[j], arity, iso_unify=False)
        return heads[j]

    for i in sorted(tro_indices):
        if i == last or _cuts_before_tail(clauses[i], db):
            out[i] = None
            continue
        mine = effective_head_args(clauses[i], arity)
        facts, ground = guard_facts(clauses[i], arity)
        rest = []
        plain: set = set()
        for j in range(i + 1, len(clauses)):
            if not heads_may_unify(mine, head(j), env):
                continue
            need = _guard_refutes(facts, ground, clauses[j], arity, mine)
            if need is None:
                rest.append(j)
            else:
                plain |= need
        keys = None
        if rest:
            for pos in range(arity):
                # Where this clause's own head keys the argument, a restart
                # has it keyed so, and that key is among the later ones (or
                # those heads could not unify): the test could never pass.
                if head_arg_key(clauses[i], pos, arity, env) is not _INDEX_VAR:
                    continue
                ks = [head_arg_key(clauses[j], pos, arity, env) for j in rest]
                if any(k is _INDEX_VAR for k in ks):
                    continue
                try:
                    keys = (pos, frozenset(ks))
                except TypeError:
                    continue
                break
            if keys is None:
                continue
        out[i] = None if keys is None and not plain else (
            keys, frozenset(plain))
    return out
