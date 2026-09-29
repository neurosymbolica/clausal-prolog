"""clpz's surface under Scryer's names: ``in/2``, ``ins/2``, ``labeling/2``,
``label/1`` (Scryer's), and the reified connectives ``#<==>``, ``#==>``,
``#<==``, ``#\\/``, ``#/\\``, ``#\\`` (plan native-iso-reader-step2, ruling
D9(a)).

These are THIN wrappers over :mod:`clausal.logic.clpfd`: domains are its
interval tuples, posting is its ``_post_domain``/``propagate``, comparisons
are its ``fd_eq``/``fd_ne``/``fd_lt``/``fd_le``.  What is new here is only
what clpfd has no equivalent for:

* the DOMAIN notation (``1..3``, ``inf..sup``, ``1..3 \\/ 5..7``, a bare
  integer), parsed as Scryer's ``drep_to_domain/2`` parses it;
* Scryer's LABELING search (``leftmost``/``ff``/``ffc``/``min``/``max``,
  ``up``/``down``, ``step``/``enum``/``bisect``), whose answer ORDER is
  Scryer's -- clpfd's ``label/1`` is first-fail, a different order;
* a reified comparison propagator (:class:`ReifiedCmp`): clpfd reifies only
  inside ``if_/3``, by deciding at call time, and has no 0/1 variable that
  stays linked to a pending comparison.

Semantics and error formals are measured against Scryer's ``clpz.pl`` (ISO
first, then Scryer).  The error CONTEXT (the second argument of ``error/2``)
names the builtin's indicator; Scryer's is internal to its library
(``unknown(D)-1``, ``can_be/2``) and is not reproduced.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from clausal.logic import clpfd as _fd
from clausal.logic.clpfd import (
    FD_KEY,
    _NEG_INF,
    _POS_INF,
    Constraint,
    domain_from_range,
    domain_intersection,
    domain_max,
    domain_min,
    domain_remove,
    domain_remove_above,
    domain_remove_below,
    domain_size,
)
from clausal.logic.exceptions import (
    LogicException,
    domain_error,
    instantiation_error,
    type_error,
)
from clausal.logic.variables import (
    Trail,
    Var,
    deref,
    get_attr,
    is_var,
    unify,
    walk,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _is_int(x) -> bool:
    return type(x) is int


def _raise(term) -> None:
    raise LogicException(term)


def _proper_list(x, context: str) -> list:
    """*x* as a Python list of its elements, Scryer's ``must_be(list, X)``:
    a partial list is an instantiation_error, anything else not a list a
    type_error(list, X)."""
    x = deref(x)
    if isinstance(x, list):
        return list(x)
    if is_var(x):
        _raise(instantiation_error(context))
    from clausal.terms import SegList  # noqa: PLC0415
    if isinstance(x, SegList):
        w = walk(x)
        if isinstance(w, list):
            return list(w)
        _raise(instantiation_error(context))
    from clausal.logic.atoms import is_nil  # noqa: PLC0415
    if is_nil(x):
        return []
    _raise(type_error("list", x, context))


def _fd_variable(x, context: str) -> None:
    """Scryer's ``fd_variable/1`` (``can_be(integer, X)``): a variable or an
    integer, else type_error(integer, X)."""
    x = deref(x)
    if is_var(x) or _is_int(x):
        return
    _raise(type_error("integer", x, context))


# ── domains: Scryer's drep_to_domain/2 ───────────────────────────────────────


def _bound(b, lower: bool):
    b = deref(b)
    if _is_int(b):
        return b
    if lower and b == "inf" and type(b) is str:
        return _NEG_INF
    if not lower and b == "sup" and type(b) is str:
        return _POS_INF
    return None


def _union(d1, d2):
    """The union of two interval tuples, normalised (sorted, adjacent and
    overlapping intervals merged)."""
    ivs = sorted(list(d1) + list(d2))
    out: list = []
    for lo, hi in ivs:
        if out and lo <= out[-1][1] + 1:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return tuple(out)


def parse_domain(drep, context: str):
    """A clpz domain term -> clpfd's interval tuple.  An unbound part is an
    instantiation_error; anything else not a domain is Scryer's
    ``domain_error(clpz_domain, Drep)`` on the WHOLE term."""
    def walk_d(d):
        d = deref(d)
        if is_var(d):
            _raise(instantiation_error(context))
        if _is_int(d):
            return ((d, d),)
        if type(d) is tuple and len(d) == 3 and d[0] == "..":
            lo, hi = deref(d[1]), deref(d[2])
            if is_var(lo) or is_var(hi):
                _raise(instantiation_error(context))
            lo, hi = _bound(lo, True), _bound(hi, False)
            if lo is None or hi is None:
                raise _BadDomain
            return domain_from_range(lo, hi)
        if type(d) is tuple and len(d) == 3 and d[0] == "\\/":
            return _union(walk_d(d[1]), walk_d(d[2]))
        raise _BadDomain
    try:
        return walk_d(drep)
    except _BadDomain:
        _raise(domain_error("clpz_domain", walk(drep), context))


class _BadDomain(Exception):
    pass


def _post(targets, dom, trail: Trail) -> bool:
    queue: deque = deque()
    for t in targets:
        t = deref(t)
        if _is_int(t):
            if not _fd.domain_contains(dom, t):
                return False
            continue
        if not _fd._post_domain(t, dom, trail, queue):
            return False
    return _fd.propagate(queue, trail)


def clpz_in(x, drep, trail: Trail) -> bool:
    """``X in Dom``."""
    _fd_variable(x, "in/2")
    dom = parse_domain(drep, "in/2")
    return _post([x], dom, trail)


def clpz_ins(xs, drep, trail: Trail) -> bool:
    """``Xs ins Dom``."""
    items = _proper_list(xs, "ins/2")
    for v in items:
        _fd_variable(v, "ins/2")
    dom = parse_domain(drep, "ins/2")
    return _post(items, dom, trail)


# ── labeling/2: Scryer's search ──────────────────────────────────────────────

_SELECTION = ("leftmost", "ff", "ffc", "min", "max")
_ORDER = ("up", "down")
_CHOICE = ("step", "enum", "bisect")


def _options(options, opts_term):
    ctx = "labeling/2"
    sel = order = choice = None
    for o in _proper_list(options, ctx):
        o = deref(o)
        if is_var(o):
            _raise(instantiation_error(ctx))
        slot = None
        if o == "upto_ground" and type(o) is str:
            continue                       # Scryer's default consistency
        if (o == "upto_in" and type(o) is str) or (
                type(o) is tuple and len(o) == 2 and o[0] == "upto_in"):
            raise LogicException(domain_error(
                "labeling_option", walk(o),
                "labeling/2: the upto_in consistency options are not "
                "supported"))
        if type(o) is str:
            if o in _SELECTION:
                slot = "sel"
            elif o in _ORDER:
                slot = "order"
            elif o in _CHOICE:
                slot = "choice"
        elif type(o) is tuple and len(o) == 2 and o[0] in ("min", "max"):
            continue                       # optimisation: see _objectives
        if slot is None:
            _raise(domain_error("labeling_option", walk(o), ctx))
        cur = {"sel": sel, "order": order, "choice": choice}[slot]
        if cur is not None:
            # Scryer's override_/5: the same option twice is a different
            # domain from two options of one category.
            _raise(domain_error(
                "nonrepeating_labeling_options" if cur == o
                else "consistent_labeling_options", walk(opts_term), ctx))
        if slot == "sel":
            sel = o
        elif slot == "order":
            order = o
        else:
            choice = o
    return sel or "leftmost", order or "up", choice or "step"


def _dom(v):
    st = get_attr(v, FD_KEY)
    return None if st is None else st.domain


def _finite_or_raise(v, ctx):
    v = deref(v)
    if _is_int(v):
        return
    if not is_var(v):
        _raise(type_error("integer", v, ctx))
    d = _dom(v)
    if d is None or not d or domain_min(d) == _NEG_INF \
            or domain_max(d) == _POS_INF:
        _raise(instantiation_error(ctx))


def _select(sel, vs):
    """The variable to label next (Scryer's select_var/4), or None."""
    best = None
    best_key = None
    for v in vs:
        v = deref(v)
        if not is_var(v):
            continue
        if sel == "leftmost":
            return v
        d = _dom(v)
        if sel in ("ff", "ffc"):
            key = domain_size(d)
            if sel == "ffc":
                st = get_attr(v, FD_KEY)
                key = (key, -len(st.constraints))
        elif sel == "min":
            key = domain_min(d)
        else:  # max: the HIGHEST upper bound first
            key = -domain_max(d)
        if best_key is None or key < best_key:
            best, best_key = v, key
    return best


def _narrow_to(v, new_dom, trail) -> bool:
    queue: deque = deque()
    if not _fd._post_domain(v, new_dom, trail, queue):
        return False
    return _fd.propagate(queue, trail)


def labeling(options, vars_, trail: Trail):
    """``labeling(Options, Vars)``: a generator, one ``None`` per answer."""
    ctx = "labeling/2"
    # Scryer's order of checks: the options are a list, the variables a
    # list of finite-domain variables, and only then the options' contents.
    _proper_list(options, ctx)
    vs = _proper_list(vars_, ctx)
    for v in vs:
        _finite_or_raise(v, ctx)
    sel, order, choice = _options(options, options)
    objectives = _objectives(options)
    # A united variable is labelled through its shadow, as label/1 does.
    if _fd._label_targets is None:
        _fd._ensure_units_imports()
    vs = _fd._label_targets(vs)
    if not objectives:
        yield from _label(vs, sel, order, choice, trail)
        return
    yield from _label_optimising(vs, sel, order, choice, objectives, trail)


def _objectives(options):
    """The ``min(Expr)`` / ``max(Expr)`` options, in order, as
    ``(sign, Expr)`` (sign -1 for max); each Expr checked as a clpz
    expression up front (domain_error(clpz_expression, _) otherwise)."""
    out = []
    for o in _proper_list(options, "labeling/2"):
        o = deref(o)
        if type(o) is tuple and len(o) == 2 and o[0] in ("min", "max"):
            expr = clpz_expression(o[1], "labeling/2")
            out.append((-1 if o[0] == "max" else 1, expr))
    return out


def _post_clpz(op, l, r, trail) -> bool:
    """A clpz comparison ``l op r`` (``/`` as clpz's exact division)."""
    ops = _fd.clpz_operands(l, r, trail)
    return ops is not None and _post_cmp(op, ops[0], ops[1], trail)


def _objective_value(expr, trail):
    """The value of the objective once the variables are labelled, or None
    when it has none (``X/2`` with X odd)."""
    if _term_vars(expr):
        # Scryer: an objective over a variable the labelling leaves unbound
        _raise(instantiation_error("labeling/2"))
    v = Var()
    mark = trail.mark()
    ok = _post_clpz("eq", v, expr, trail)
    val = deref(v) if ok else None
    trail.undo(mark)
    return val if _is_int(val) else None


def _label_optimising(vs, sel, order, choice, objectives, trail):
    """Scryer's ``min(Expr)``/``max(Expr)``, by branch and bound: the best
    value of the first objective is found (each solution tightens the
    bound), the labellings with that value are answered -- ties ordered by
    the next objective, then by the other options -- and the search moves on
    to the next value."""
    if not objectives:
        yield from _label(vs, sel, order, choice, trail)
        return
    sign, expr = objectives[0]
    better = "gt" if sign < 0 else "lt"       # max: look for larger values
    beyond = None                             # values already answered
    while True:
        best = None
        while True:
            mark = trail.mark()
            ok = True
            if beyond is not None:
                # strictly past the values already answered
                ok = _post_clpz("lt" if sign < 0 else "gt", expr, beyond, trail)
            if ok and best is not None:
                ok = _post_clpz(better, expr, best, trail)
            found = None
            if ok:
                for _ in _label(vs, sel, order, choice, trail):
                    found = _objective_value(expr, trail)
                    if found is not None:
                        break
            trail.undo(mark)
            if found is None:
                break
            best = found
        if best is None:
            return
        mark = trail.mark()
        if _post_clpz("eq", expr, best, trail):
            yield from _label_optimising(vs, sel, order, choice,
                                         objectives[1:], trail)
        trail.undo(mark)
        beyond = best


def _label(vs, sel, order, choice, trail):
    var = _select(sel, vs)
    if var is None:
        yield None
        return
    d = _dom(var)
    if choice == "enum":
        values = list(_fd.domain_values(d))
        if order == "down":
            values.reverse()
        for val in values:
            mark = trail.mark()
            if unify(var, val, trail):
                yield from _label(vs, sel, order, choice, trail)
            trail.undo(mark)
        return
    if choice == "step":
        nxt = domain_min(d) if order == "up" else domain_max(d)
        mark = trail.mark()
        if unify(var, nxt, trail):
            yield from _label(vs, sel, order, choice, trail)
        trail.undo(mark)
        mark = trail.mark()
        if _narrow_to(var, domain_remove(d, nxt), trail):
            yield from _label(vs, sel, order, choice, trail)
        trail.undo(mark)
        return
    # bisect
    lo, hi = domain_min(d), domain_max(d)
    total = lo + hi
    # Scryer's (I + S) // 2 TRUNCATES toward zero; Python's // floors.
    mid = total // 2 if total >= 0 else -((-total) // 2)
    if mid == hi:
        mid -= 1
    halves = [domain_remove_above(d, mid), domain_remove_below(d, mid + 1)]
    if order == "down":
        halves.reverse()
    for half in halves:
        mark = trail.mark()
        if _narrow_to(var, half, trail):
            yield from _label(vs, sel, order, choice, trail)
        trail.undo(mark)


def label(vars_, trail: Trail):
    """Scryer's ``label/1``: ``labeling([], Vars)`` (leftmost, up, step)."""
    yield from labeling([], vars_, trail)


# ── expressions ──────────────────────────────────────────────────────────────

#: Scryer's ``parse_clpz/2`` functors, as ``(name, arity)``.
_CLPZ_FUNCTORS = frozenset({
    ("+", 2), ("*", 2), ("-", 2), ("-", 1), ("max", 2), ("min", 2),
    ("mod", 2), ("rem", 2), ("abs", 1), ("/", 2), ("//", 2), ("div", 2),
    ("^", 2), ("sign", 1), ("\\", 1), ("msb", 1), ("lsb", 1),
    ("popcount", 1), ("<<", 2), (">>", 2), ("/\\", 2), ("\\/", 2),
    ("xor", 2),
})


#: The functors clpfd's propagators understand (they have an operator node):
#: a reified comparison may use the others only over ground subterms, which
#: fold to their value.
_PROPAGATED = frozenset({
    ("+", 2), ("-", 2), ("-", 1), ("*", 2), ("/", 2), ("//", 2),
    ("div", 2), ("mod", 2), ("^", 2),
    # lifted into their own propagators (clpfd._lift_cells) before the
    # reified comparison is posted: Z = abs(A) holds whatever B is
    ("abs", 1), ("min", 2), ("max", 2), ("rem", 2), ("sign", 1),
    ("\\", 1), ("<<", 2), (">>", 2), ("/\\", 2), ("\\/", 2), ("xor", 2),
})


def clpz_expression(e, context: str, reified: bool = False):
    """*e* checked as a clpz expression and returned with the ``#X``/``?X``
    variable markers removed; anything else raises Scryer's
    ``domain_error(clpz_expression, Culprit)`` naming the offending
    subterm.  *reified*: inside a reified comparison, a functor clpfd cannot
    propagate (``abs``, ``min``, ``max``, the bitwise ones ...) over a
    non-ground subterm is refused loudly -- Scryer accepts it, and a
    silently unwatched variable would give wrong answers."""
    e = deref(e)
    if is_var(e) or _is_int(e):
        return e
    if type(e) is tuple and len(e) == 2 and e[0] in ("#", "?"):
        inner = deref(e[1])
        if is_var(inner) or _is_int(inner):
            return inner
        _raise(type_error("integer", walk(inner), context))
    if type(e) is tuple and len(e) >= 2 and type(e[0]) is str \
            and (e[0], len(e) - 1) in _CLPZ_FUNCTORS:
        out = (e[0],) + tuple(clpz_expression(a, context, reified)
                              for a in e[1:])
        if (reified and (e[0], len(e) - 1) not in _PROPAGATED
                and _term_vars(out)):
            raise LogicException(domain_error(
                "clpz_expression", walk(e),
                f"{context}: {e[0]}/{len(e) - 1} over a variable is not "
                f"supported in a reified comparison (the engine's CLP(FD) "
                f"does not propagate it)"))
        return out
    _raise(domain_error("clpz_expression", walk(e), context))


def _term_vars(t, out=None) -> list:
    """The unbound variables of a term (cells and lists), in order."""
    if out is None:
        out = []
    t = deref(t)
    if is_var(t):
        if not any(v is t for v in out):
            out.append(t)
    elif type(t) is tuple:
        for a in t[1:]:
            _term_vars(a, out)
    elif type(t) is list:
        for a in t:
            _term_vars(a, out)
    return out


# ── reification ──────────────────────────────────────────────────────────────

_CMP = {"#=": "eq", "#\\=": "ne", "#<": "lt", "#>": "gt", "#=<": "le",
        "#>=": "ge"}
_NEGATE = {"eq": "ne", "ne": "eq", "lt": "ge", "ge": "lt", "gt": "le",
           "le": "gt"}


def _post_cmp(op: str, l, r, trail) -> bool:
    if op == "eq":
        return _fd.fd_eq(l, r, trail)
    if op == "ne":
        return _fd.fd_ne(l, r, trail)
    if op == "lt":
        return _fd.fd_lt(l, r, trail)
    if op == "le":
        return _fd.fd_le(l, r, trail)
    if op == "gt":
        return _fd.fd_lt(r, l, trail)
    return _fd.fd_le(r, l, trail)


def _decide(op: str, ld, rd):
    """True/False when the domains already decide ``L op R``, else None."""
    lmin, lmax, rmin, rmax = (domain_min(ld), domain_max(ld),
                              domain_min(rd), domain_max(rd))
    if op in ("eq", "ne"):
        if lmin == lmax == rmin == rmax:
            verdict = True
        elif not domain_intersection(ld, rd):
            verdict = False
        else:
            return None
        return verdict if op == "eq" else not verdict
    if op == "gt":
        op, lmin, lmax, rmin, rmax = "lt", rmin, rmax, lmin, lmax
    elif op == "ge":
        op, lmin, lmax, rmin, rmax = "le", rmin, rmax, lmin, lmax
    if op == "lt":
        if lmax < rmin:
            return True
        if lmin >= rmax:
            return False
        return None
    if lmax <= rmin:
        return True
    if lmin > rmax:
        return False
    return None


class ReifiedCmp(Constraint):
    """``B #<==> (L op R)`` with B a 0/1 variable.

    While B is unbound the operands' domains are watched: once they decide
    the comparison, B is bound.  Once B is bound, the comparison (B = 1) or
    its negation (B = 0) is POSTED through clpfd, which propagates it from
    then on.  ``done`` is a variable bound (on the trail) when either has
    happened, so a re-run is a no-op and backtracking re-arms it."""
    __slots__ = ("b", "op", "l", "r", "done")

    def __init__(self, b, op, l, r):
        self.b, self.op, self.l, self.r = b, op, l, r
        self.done = Var()
        vs = _term_vars((",", l, r))
        vs.append(b)
        super().__init__(tuple(vs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        if not is_var(deref(self.done)):
            return True
        b = deref(self.b)
        if _is_int(b):
            unify(self.done, 1, trail)
            op = self.op if b == 1 else _NEGATE[self.op]
            return _post_cmp(op, self.l, self.r, trail)
        # Nodes are rebuilt each time: a bound variable is replaced by its
        # value, so a subterm that became ground folds.
        nl, nr = _fd._cells_as_nodes(deref(self.l), deref(self.r))
        ld = _fd._expr_domain(nl, trail)
        rd = _fd._expr_domain(nr, trail)
        if not ld or not rd:
            verdict = False      # no value: the relation has no solutions
        else:
            verdict = _decide(self.op, ld, rd)
        if verdict is None:
            return True
        unify(self.done, 1, trail)
        return unify(self.b, 1 if verdict else 0, trail)


class ReifiedIn(Constraint):
    """``B #<==> (V in Dom)``: bound B once V's domain is inside Dom (1) or
    disjoint from it (0); once B is bound, post Dom (1) or its complement
    (0) on V."""
    __slots__ = ("b", "v", "dom", "done")

    def __init__(self, b, v, dom):
        self.b, self.v, self.dom = b, v, dom
        self.done = Var()
        vs = [x for x in (deref(v), deref(b)) if is_var(x)]
        super().__init__(tuple(vs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        if not is_var(deref(self.done)):
            return True
        b = deref(self.b)
        v = deref(self.v)
        if _is_int(b):
            unify(self.done, 1, trail)
            dom = self.dom if b == 1 else _complement(self.dom)
            return _post([v], dom, trail)
        vd = ((v, v),) if _is_int(v) else _dom(v)
        if vd is None:
            vd = domain_from_range(_NEG_INF, _POS_INF)
        inter = domain_intersection(vd, self.dom)
        if not inter:
            verdict = False
        elif domain_size(inter) == domain_size(vd):
            verdict = True
        else:
            return True
        unify(self.done, 1, trail)
        return unify(self.b, 1 if verdict else 0, trail)


def _complement(dom):
    out: list = []
    lo = _NEG_INF
    for a, b in dom:
        if a != _NEG_INF:
            out.append((lo, a - 1))
        lo = b + 1 if b != _POS_INF else None
        if lo is None:
            break
    if lo is not None:
        out.append((lo, _POS_INF))
    return tuple((a, b) for a, b in out if a <= b)


def _bool_var(trail) -> Var:
    b = Var()
    _post([b], ((0, 1),), trail)
    return b


def _post_constraint(c: Constraint, trail) -> bool:
    for v in c.vars:
        v = deref(v)
        if is_var(v):
            _fd._ensure_fd(v, trail)
    return _fd._post_constraint(c, trail)


_CONNECTIVES = {("#<==>", 2), ("#==>", 2), ("#<==", 2), ("#\\/", 2),
                ("#/\\", 2), ("#\\", 2), ("#\\", 1)}


def _check_reifiable(e, whole, ctx):
    """Scryer's ``reifiable/1`` over the whole expression, BEFORE anything
    is posted: an ill-formed expression is ``domain_error(
    clpz_reifiable_expression, Whole)``; a bad arithmetic operand of a
    comparison is ``domain_error(clpz_expression, Culprit)``."""
    e = deref(e)
    if is_var(e):
        return
    if _is_int(e):
        if e in (0, 1):
            return
        _raise(domain_error("clpz_reifiable_expression", walk(whole), ctx))
    if type(e) is tuple and len(e) == 2 and e[0] in ("#", "?"):
        clpz_expression(e, ctx)
        return
    if type(e) is tuple and len(e) == 3 and e[0] in _CMP:
        clpz_expression(e[1], ctx, reified=True)
        clpz_expression(e[2], ctx, reified=True)
        return
    if type(e) is tuple and len(e) == 3 and e[0] == "in":
        _fd_variable(e[1], ctx)
        parse_domain(e[2], ctx)
        return
    if type(e) is tuple and (e[0], len(e) - 1) in _CONNECTIVES:
        for a in e[1:]:
            _check_reifiable(a, whole, ctx)
        return
    _raise(domain_error("clpz_reifiable_expression", walk(whole), ctx))


def reify(e, trail, ctx):
    """A 0/1 term (an integer or a variable in 0..1) whose value is the
    truth of the reifiable expression *e*; posts what links them.  None when
    posting already failed."""
    e = deref(e)
    if is_var(e):
        return e if _post([e], ((0, 1),), trail) else None
    if _is_int(e):
        return e
    if len(e) == 2 and e[0] in ("#", "?"):
        x = deref(e[1])
        return x if _post([x], ((0, 1),), trail) else None
    name = e[0]
    if name in _CMP:
        l = clpz_expression(e[1], ctx, reified=True)
        r = clpz_expression(e[2], ctx, reified=True)
        lifted = _lift_functional(l, r, trail)
        if lifted is None:
            return None
        l, r = lifted
        b = _bool_var(trail)
        return b if _post_constraint(ReifiedCmp(b, _CMP[name], l, r),
                                     trail) else None
    if name == "in":
        b = _bool_var(trail)
        return b if _post_constraint(
            ReifiedIn(b, e[1], parse_domain(e[2], ctx)), trail) else None
    if name == "#\\" and len(e) == 2:
        q = reify(e[1], trail, ctx)
        if q is None:
            return None
        return _reify_cmp("ne", q, 1, trail)     # B = 1 iff Q = 0
    bl = reify(e[1], trail, ctx)
    if bl is None:
        return None
    br = reify(e[2], trail, ctx)
    if br is None:
        return None
    if name == "#<==>":
        return _reify_cmp("eq", bl, br, trail)
    if name == "#\\":            # xor
        return _reify_cmp("ne", bl, br, trail)
    if name == "#==>":
        return _reify_cmp("le", bl, br, trail)
    if name == "#<==":
        return _reify_cmp("ge", bl, br, trail)
    if name == "#/\\":
        return _reify_cmp("eq", ("+", bl, br), 2, trail)
    # #\/
    return _reify_cmp("ge", ("+", bl, br), 1, trail)


def _lift_functional(l, r, trail):
    """``(l, r)`` with each abs/min/max over a variable replaced by a fresh
    variable carrying its propagator (clpfd's lifting, as in the plain
    posts), or None when posting one failed.  Sound under reification: the
    function is total, so Z = abs(A) holds whether the comparison does or
    not."""
    ok_l, lift_l = _fd._fd_int_term(l)
    ok_r, lift_r = _fd._fd_int_term(r)
    if not (ok_l and ok_r and (lift_l or lift_r)):
        return l, r
    aux: list = []
    l = _fd._lift_cells(l, aux)
    r = _fd._lift_cells(r, aux)
    for _z, key, args in aux:
        # Posted OUTSIDE the reification, so it must hold for every value of
        # its arguments: a partial function (rem by 0) or a partial operand
        # (X // Y) would prune Y = 0 for good, where the reified comparison
        # is merely false there.  Those stay refused.
        if not _total_expr((key[0],) + tuple(args)):
            raise LogicException(domain_error(
                "clpz_expression", walk((key[0],) + tuple(args)),
                f"{key[0]}/{key[1]} over a variable, with a partial function "
                f"in it, is not supported in a reified comparison"))
    if not _fd._post_lifted(aux, trail):
        return None
    return l, r


#: Integer functions defined for EVERY integer argument.
_TOTAL_KEYS = frozenset({
    ("+", 2), ("-", 2), ("*", 2), ("-", 1), ("+", 1), ("abs", 1),
    ("min", 2), ("max", 2), ("sign", 1), ("\\", 1), ("<<", 2), (">>", 2),
    ("/\\", 2), ("\\/", 2), ("xor", 2),
})


def _total_expr(t) -> bool:
    """*t* is built from integers, variables and total functions only."""
    stack = [t]
    while stack:
        x = deref(stack.pop())
        if is_var(x) or type(x) is int:
            continue
        if _fd._Add is None:
            _fd._ensure_term_imports()
        key = _fd._NODE_KEYS.get(type(x))
        if key is not None:
            args = (x.operand,) if key[1] == 1 else (x.left, x.right)
        else:
            ka = _fd._cell_key_args(x) if type(x) is tuple else None
            if ka is None:
                return False
            key, args = ka
        if key in _BY_NONZERO_CONSTANT:
            d = deref(args[1])
            if type(d) is not int or d == 0:
                return False    # a divisor that may be 0
        elif key in (("^", 2), ("$python_pow", 2)):
            e = deref(args[1])
            if type(e) is not int or e < 0:
                return False    # an exponent that may be negative
        elif key not in _TOTAL_KEYS:
            return False
        stack.extend(args)
    return True


#: Total only over a non-zero constant divisor.
_BY_NONZERO_CONSTANT = frozenset({
    ("rem", 2), ("mod", 2), ("//", 2), ("div", 2),
    ("$python_floordiv", 2), ("$python_mod", 2),
})


def _reify_cmp(op, l, r, trail):
    b = _bool_var(trail)
    return b if _post_constraint(ReifiedCmp(b, op, l, r), trail) else None


def post_connective(name: str, args: tuple, trail: Trail) -> bool:
    """A reified connective as a GOAL (Scryer's top-level definitions)."""
    ctx = f"{name}/{len(args)}"
    whole = (name,) + tuple(args)
    _check_reifiable(whole, whole, ctx)
    if name == "#\\" and len(args) == 1:
        q = reify(args[0], trail, ctx)
        return q is not None and unify_01(q, 0, trail)
    bl = reify(args[0], trail, ctx)
    if bl is None:
        return False
    br = reify(args[1], trail, ctx)
    if br is None:
        return False
    if name == "#<==>":
        return _fd.fd_eq(bl, br, trail)
    if name == "#==>":
        return _fd.fd_le(bl, br, trail)
    if name == "#<==":
        return _fd.fd_le(br, bl, trail)
    if name == "#/\\":
        return unify_01(bl, 1, trail) and unify_01(br, 1, trail)
    if name == "#\\/":
        return _fd.fd_le(1, ("+", bl, br), trail)
    # #\ (xor)
    return _fd.fd_eq(("+", bl, br), 1, trail)


def unify_01(b, value: int, trail) -> bool:
    return unify(b, value, trail)
