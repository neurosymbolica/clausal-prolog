"""The residual goals of attributed variables: the goals that, called on
fresh variables, would put back the constraints the variables carry.

One function computes them, :func:`residual_items`, and three callers read
it: the answer printers (``clausal FILE -g GOAL`` and the ``?-`` top level,
``clausal.cli._answer``), ``copy_term/3`` and the residue check of the quad
runner.  Each item is a goal TERM and the text the printers show for it, so
the printed answer and the goals ``copy_term/3`` hands back cannot drift
apart.

Goal forms are plain, as the printers show them (operator rulings
2026-10-24 and 2026-10-26: no module qualifiers):

- ``dif/2``: ``dif(X, a)``;
- CLP(Z): ``X in 1..3``, ``X #< Y``, ``all_different([X, Y])``,
  ``scalar_product(Cs, Vs, #=, C)``, ``X #= A*B``;
- ``freeze/2`` and ``when/2``: ``freeze(X, G)``, ``when(Cond, G)``;
- CLP(B): ``sat(F)``, one per Boolean network, F written with ``+``, ``*``
  and ``~`` (the syntax ``sat/1`` reads);
- CLP(R): ``in_real(X)``, ``in_real(X, Lo, Hi)``, ``X #>= Lo``,
  ``X #=< Hi``, and the constraints still pending (``X #< Y``);
- CLP(Q): ``{X >= 2}``, the projection the toplevel shows
  (``clausal.logic.clpq``'s ``residual_q_goals``).

The order is the printers': ``dif/2``, CLP(Z) domains, CLP(Z) constraints,
``freeze/2`` and ``when/2``, CLP(B), CLP(R), then CLP(Q).
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple


class Residual(NamedTuple):
    """One residual goal: the *goal* term, and *render*, which writes it as
    the printers show it: ``render(spell, name_of)``, where ``spell(term)``
    writes a term (the printers' ``writeq`` with the answer's variable
    names) and ``name_of(var)`` names one variable (CLP(Q)'s writer)."""
    goal: Any
    render: Callable[[Callable, Callable], str]


def _spelled(goal) -> Residual:
    return Residual(goal, lambda spell, _name_of: spell(goal))


# ── which variables ─────────────────────────────────────────────────────────


def residue_variables(trail, mark: int = 0, exclude=()) -> list:
    """The variables that got or lost an attribute on *trail* after *mark*
    and still carry one, unbound, each once, in the order they first got
    one: call_residue_vars/2's answer.  Those whose id is in *exclude* are
    left out."""
    from clausal.logic.variables import Var, deref  # noqa: PLC0415
    out: list = []
    seen: set = set(exclude)
    for av in trail.attvars_since(mark):
        d = deref(av)
        if isinstance(d, Var) and getattr(d, "attrs", None) \
                and id(d) not in seen:
            seen.add(id(d))
            out.append(d)
    return out


def attribute_closure(variables) -> list:
    """*variables*, and the variables their ``dif/2`` pairs and pending
    ``freeze/2``/``when/2`` goals reach, and so on: the variables whose
    constraints an answer shows, as Scryer's projection reaches them.
    ``dif(A, E), copy_term(E, F)`` leaves ``dif(_1, F)``, and ``_1`` may
    carry constraints of its own."""
    from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
    from clausal.logic.constraints import DIF_KEY  # noqa: PLC0415
    from clausal.logic.coroutining import pending_goals  # noqa: PLC0415
    from clausal.logic.variables import get_attr  # noqa: PLC0415
    out: list = []
    seen: set = set()
    queue = list(variables)
    i = 0
    while i < len(queue):
        v = queue[i]
        i += 1
        if id(v) in seen:
            continue
        seen.add(id(v))
        out.append(v)
        reached: list = []
        for pair in get_attr(v, DIF_KEY) or ():
            _collect_vars_impl(pair, reached)
        for goal in pending_goals([v]):
            _collect_vars_impl(goal, reached)
        queue.extend(x for x in reached if id(x) not in seen)
    return out


# ── dif/2 ───────────────────────────────────────────────────────────────────


def dif_residuals(variables) -> list[Residual]:
    """The ``dif/2`` goals on *variables*, each pair once."""
    from clausal.logic.constraints import DIF_KEY, reify_eq  # noqa: PLC0415
    from clausal.logic.builtins.inspection import _copy_term_impl  # noqa: PLC0415
    from clausal.logic.variables import Trail, get_attr  # noqa: PLC0415
    out: list[Residual] = []
    seen: set[int] = set()
    for v in variables:
        for pair in get_attr(v, DIF_KEY) or ():
            if id(pair) in seen:
                continue
            seen.add(id(pair))
            # A pair a later binding made true for good stays in the
            # attribute of its other variables (the wake-up hook only
            # re-checks it): ``dif(C, [a|B]), C = 1`` leaves it on B.  It
            # constrains nothing, and Scryer does not show it.
            # (Tried on a copy with plain variables: on the pair itself the
            # trial binding would run its own dif hook.)
            var_map: dict = {}
            if reify_eq(_copy_term_impl(pair[0], var_map, []),
                        _copy_term_impl(pair[1], var_map, []),
                        Trail()) is False:
                continue
            # One term, so an argument is written as an argument
            # (``dif(A,=)``, as Scryer writes it), not as the right side of
            # ``=`` (``(=)``).
            out.append(_spelled(("dif", pair[0], pair[1])))
    return out


# ── CLP(Z) ──────────────────────────────────────────────────────────────────


def _domain_term(domain):
    """A CLP(Z) domain as the term ``1..3\\/5..7`` (``inf``/``sup`` for
    open ends, a single integer for a one-value interval)."""
    def end(x, low):
        if x in (float("-inf"), float("inf")):
            return "inf" if low else "sup"
        return x
    term = None
    for lo, hi in domain:
        part = end(lo, True) if lo == hi else ("..", end(lo, True), end(hi, False))
        term = part if term is None else ("\\/", term, part)
    return term


def _domain_text(domain) -> str:
    """The domain as the printers write it: ``1..3\\/5..7``."""
    def end(x, low):
        if x in (float("-inf"), float("inf")):
            return "inf" if low else "sup"
        return str(x)
    parts = []
    for lo, hi in domain:
        parts.append(end(lo, True) if lo == hi
                     else f"{end(lo, True)}..{end(hi, False)}")
    return "\\/".join(parts)


_RELATIONS = {"EqConstraint": "#=", "NeConstraint": "#\\=",
              "LtConstraint": "#<", "LeConstraint": "#=<"}

#: clpfd_nonlinear's propagators, as the functor each one is, and the text
#: the printers put between its operands
_NONLINEAR = {"TimesConstraint": ("*", "*"), "TruncDivConstraint": ("//", "//"),
              "FloorDivConstraint": ("div", " div "),
              "ModConstraint": ("mod", " mod "),
              "RemConstraint": ("rem", " rem "), "PowConstraint": ("^", "^"),
              "MinConstraint": ("min", None), "MaxConstraint": ("max", None)}


def _fd_constraint_residual(c) -> Residual:
    """One pending CLP(Z) propagator as a goal, or ``pending(Kind, Vars)``
    for a kind not spelled yet (so an answer never claims more freedom than
    it has)."""
    kind = type(c).__name__
    if kind in _RELATIONS:
        op = _RELATIONS[kind]
        return Residual((op, c.lhs, c.rhs), lambda s, _n:
                        f"{s(c.lhs)} {op} {s(c.rhs)}")
    if kind == "AllDiffConstraint":
        return Residual(("all_different", list(c.vars)), lambda s, _n:
                        "all_different([" + ",".join(s(v) for v in c.vars) + "])")
    if kind == "SumConstraint":
        return Residual(("sum", list(c.sum_vars), "#=", c.total), lambda s, _n:
                        "sum([" + ",".join(s(v) for v in c.sum_vars)
                        + f"],#=,{s(c.total)})")
    if kind == "ScalarProductConstraint":
        return Residual(
            ("scalar_product", list(c.coeffs), list(c.sum_vars), "#=", c.total),
            lambda s, _n: ("scalar_product([" + ",".join(s(v) for v in c.coeffs)
                           + "],[" + ",".join(s(v) for v in c.sum_vars)
                           + f"],#=,{s(c.total)})"))
    if kind in _NONLINEAR and hasattr(c, "a"):
        functor, between = _NONLINEAR[kind]
        a, b = c.a, c.b

        def render(s, _n):
            rhs = (f"{functor}({s(a)},{s(b)})" if between is None
                   else f"{s(a)}{between}{s(b)}")
            return f"{s(c.z)} #= {rhs}"
        return Residual(("#=", c.z, (functor, a, b)), render)
    if kind == "LinearNeConstraint" and c.lhs is not None:
        return Residual(("#\\=", c.lhs, c.rhs), lambda s, _n:
                        f"{s(c.lhs)} #\\= {s(c.rhs)}")
    if kind == "LinearNeConstraint":
        lhs = None
        for k, v in zip(c.coeffs, c.lvars):
            term = v if abs(k) == 1 else ("*", abs(k), v)
            if lhs is None:
                lhs = term if k > 0 else (("-", v) if abs(k) == 1 else ("*", k, v))
            else:
                lhs = ("-" if k < 0 else "+", lhs, term)

        def render(s, _n):
            parts = []
            for k, v in zip(c.coeffs, c.lvars):
                term = s(v) if abs(k) == 1 else f"{abs(k)}*{s(v)}"
                parts.append(("-" if k < 0 else "+") + term)
            return "".join(parts).lstrip("+") + f" #\\= {s(c.k)}"
        return Residual(("#\\=", lhs, c.k), render)
    name = kind.removesuffix("Constraint").lower()
    pending = ("pending", name, list(getattr(c, "vars", ())))
    return Residual(pending, lambda s, _n: (
        f"pending({name},[" + ",".join(s(v) for v in getattr(c, "vars", ()))
        + "])"))


def fd_residuals(variables) -> list[Residual]:
    """The CLP(Z) goals on *variables*: their domains (one with no bound is
    not shown), then the propagators with two or more open variables (one
    with a single variable is what its domain already says)."""
    from clausal.logic.variables import deref, get_attr, is_var  # noqa: PLC0415
    out: list[Residual] = []
    inf = float("inf")
    for v in variables:
        state = get_attr(v, "fd")
        if state is None or not state.domain:
            continue
        if state.domain != ((-inf, inf),):
            domain = state.domain
            out.append(Residual(
                ("in", v, _domain_term(domain)),
                lambda s, _n, v=v, domain=domain:
                    f"{s(v)} in {_domain_text(domain)}"))
    seen: set[int] = set()
    for v in variables:
        state = get_attr(v, "fd")
        for c in (state.constraints if state is not None else ()):
            if id(c) in seen:
                continue
            seen.add(id(c))
            open_vars = {id(deref(x)) for x in getattr(c, "vars", ())
                         if is_var(deref(x))}
            if len(open_vars) >= 2:
                out.append(_fd_constraint_residual(c))
    return out


# ── freeze/2 and when/2 ─────────────────────────────────────────────────────


def coroutine_residuals(variables) -> list[Residual]:
    """The freeze/2 and when/2 goals pending on *variables*
    (``freeze(X,write(hi))``, ``when((nonvar(X);ground(Y)),g)``).  A goal
    whose variable is bound since is gone."""
    from clausal.logic.coroutining import pending_goals  # noqa: PLC0415
    return [_spelled(g) for g in pending_goals(variables)]


# ── CLP(B) ──────────────────────────────────────────────────────────────────


def _bdd_formula(bdd, var_of, memo: dict):
    """A BDD as a formula over ``+``, ``*`` and ``~``: each node ``V`` with
    branches ``H`` (V = 1) and ``L`` (V = 0) is ``V*H + ~V*L``, simplified
    where a branch is a constant."""
    from clausal.logic.clpb import BDD_TRUE, BDDNode  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415
    if not isinstance(bdd, BDDNode):
        return 1 if bdd == BDD_TRUE else 0
    key = id(bdd)
    if key in memo:
        return memo[key]
    v = var_of(bdd.var_id)
    if not is_var(v):           # bound since: its branch is the formula
        out = _bdd_formula(bdd.high if v == 1 else bdd.low, var_of, memo)
        memo[key] = out
        return out
    high = _bdd_formula(bdd.high, var_of, memo)
    low = _bdd_formula(bdd.low, var_of, memo)
    def is_(f, n):
        return type(f) is int and f == n
    if is_(high, 1) and is_(low, 0):
        out = v
    elif is_(high, 0) and is_(low, 1):
        out = ("~", v)
    elif is_(high, 1):
        out = ("+", v, low)
    elif is_(low, 1):
        out = ("+", ("~", v), high)
    elif is_(high, 0):
        out = ("*", ("~", v), low)
    elif is_(low, 0):
        out = ("*", v, high)
    else:
        out = ("+", ("*", v, high), ("*", ("~", v), low))
    memo[key] = out
    return out


def clpb_residuals(variables) -> list[Residual]:
    """``sat(F)`` for each CLP(B) network a variable of *variables* is in,
    F its BDD as a formula.  A variable that is only declared Boolean
    (its BDD is the variable itself) is ``sat(V+ ~V)``."""
    from clausal.logic.clpb import B_KEY, BDDNode, _get_var_for_id  # noqa: PLC0415
    from clausal.logic.variables import Var, deref, get_attr  # noqa: PLC0415
    out: list[Residual] = []
    seen: set[int] = set()
    for v in variables:
        state = get_attr(v, B_KEY)
        if state is None or id(state.bdd) in seen:
            continue
        seen.add(id(state.bdd))
        bdd = state.bdd
        if not isinstance(bdd, BDDNode):
            continue
        if state.sat_expr is None and type(bdd.high) is int \
                and type(bdd.low) is int:
            # declared Boolean by a sat_count/taut/labeling, no formula:
            # it still may take only 0 or 1
            formula = ("+", v, ("~", v))
        else:
            def var_of(var_id):
                found = _get_var_for_id(var_id)
                return deref(found) if found is not None else Var()
            formula = _bdd_formula(bdd, var_of, {})
            if type(formula) is int:    # every variable of it is bound
                continue
        out.append(_spelled(("sat", formula)))
    return out


# ── CLP(R) ──────────────────────────────────────────────────────────────────


_REAL_RELATIONS = {"RealEqConstraint": "#=", "RealLeConstraint": "#=<",
                   "RealLtConstraint": "#<", "RealNeConstraint": "#\\="}


def _real_term(expr):
    """A CLP(R) expression (operator nodes) as the cell ``#=`` reads."""
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    from clausal.terms import (  # noqa: PLC0415
        Add, Div, FloorDiv, Mod, Mult, Negate, Pow, Sub)
    expr = deref(expr)
    if is_var(expr):
        return expr
    binary = ((Add, "+"), (Sub, "-"), (Mult, "*"), (Div, "/"),
              (FloorDiv, "//"), (Mod, "mod"), (Pow, "^"))
    for cls, functor in binary:
        if isinstance(expr, cls):
            return (functor, _real_term(expr.left), _real_term(expr.right))
    if isinstance(expr, Negate):
        return ("-", _real_term(expr.operand))
    return expr


def _spaced(op, lhs, rhs) -> Residual:
    """``Lhs Op Rhs`` written as the printers write a CLP(Z) relation."""
    return Residual((op, lhs, rhs), lambda s, _n: f"{s(lhs)} {op} {s(rhs)}")


def clpr_residuals(variables) -> list[Residual]:
    """The CLP(R) goals on *variables*: each one's interval (``in_real(X)``
    when it is unbounded, ``in_real(X, Lo, Hi)`` when bounded both ways, a
    ``#>=``/``#=<`` bound otherwise; an end at the largest float is open:
    outward rounding moves an infinite end there), then each constraint
    still pending, once, but for a bound of one variable by a number,
    which its interval already says.  The interval is outward-rounded, so
    the goals allow at least what the store allows."""
    import sys  # noqa: PLC0415
    from clausal.logic.clpr import REAL_KEY  # noqa: PLC0415
    from clausal.logic.variables import deref, get_attr, is_var  # noqa: PLC0415
    from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
    big = sys.float_info.max
    out: list[Residual] = []
    for v in variables:
        state = get_attr(v, REAL_KEY)
        if state is None:
            continue
        lo, hi = state.lo, state.hi
        has_lo, has_hi = lo > -big, hi < big
        if has_lo and has_hi:
            out.append(_spelled(("in_real", v, lo, hi)))
        elif has_lo:
            out.append(_spaced("#>=", v, lo))
        elif has_hi:
            out.append(_spaced("#=<", v, hi))
        else:
            out.append(_spelled(("in_real", v)))
    seen: set[int] = set()
    for v in variables:
        state = get_attr(v, REAL_KEY)
        for c in (state.constraints if state is not None else ()):
            if id(c) in seen:
                continue
            seen.add(id(c))
            op = _REAL_RELATIONS.get(type(c).__name__)
            if op is None:
                continue
            lhs, rhs = _real_term(c.lhs), _real_term(c.rhs)
            found: list = []
            _collect_vars_impl((lhs, rhs), found)
            if not any(is_var(deref(x)) for x in found):
                continue
            sides = (deref(lhs), deref(rhs))
            if op != "#\\=" and any(is_var(x) for x in sides) \
                    and any(isinstance(x, (int, float))
                            and not isinstance(x, bool) for x in sides):
                continue
            out.append(_spaced(op, lhs, rhs))
    return out


# ── CLP(Q) ──────────────────────────────────────────────────────────────────


def clpq_residuals(targets, trail, attributed=()) -> list[Residual]:
    """The CLP(Q) projection the toplevel shows for *targets* (and the
    constraints of *attributed* it keeps), each relation in braces
    (``{X >= 2}``); see ``residual_q_goals`` of the selected solver."""
    from clausal.logic import clpq  # noqa: PLC0415
    from clausal.logic.clpq.residual_constraints import (  # noqa: PLC0415
        _RELATIONS as Q_RELATIONS, format_term)
    out: list[Residual] = []
    for goal in clpq.residual_q_goals(targets, trail, attributed):
        if type(goal) is tuple and len(goal) == 3 and goal[0] in Q_RELATIONS:
            out.append(Residual(("{}", goal), lambda _s, name_of, g=goal:
                                "{" + format_term(g, name_of) + "}"))
        else:
            out.append(Residual(goal, lambda _s, name_of, g=goal:
                                format_term(g, name_of)))
    return out


# ── all of them ─────────────────────────────────────────────────────────────


def residual_items(variables, trail, attributed=()) -> list[Residual]:
    """The residual goals of *variables* and of *attributed* (attributed
    variables no answer variable reaches: call_residue_vars/2), and of the
    variables their ``dif/2`` and delayed goals reach (see
    :func:`attribute_closure`), in the printers' order.  CLP(Q) projects
    onto *variables* and takes in *attributed* as the toplevel does."""
    variables = list(variables)
    attributed = list(attributed)
    reached = attribute_closure(variables + attributed)
    return (dif_residuals(reached) + fd_residuals(reached)
            + coroutine_residuals(reached) + clpb_residuals(reached)
            + clpr_residuals(reached)
            + clpq_residuals(variables, trail, attributed))


def residual_goals(variables, trail, attributed=()) -> list:
    """The goal terms of :func:`residual_items`."""
    return [item.goal for item in residual_items(variables, trail, attributed)]
