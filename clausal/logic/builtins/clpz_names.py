"""clpz's predicates under Scryer's names, as engine builtins (ruling D9(a)):
``in/2``, ``ins/2``, ``labeling/2`` and the reified connectives ``#<==>/2``,
``#==>/2``, ``#<==/2``, ``#\\//2``, ``#/\\/2``, ``#\\/1`` and ``#\\/2``.

Usable from every front end and from ``query()``; from the seam in quoted
form (``'in'(X, '..'(1, 3))``, ``'#<==>'(B, '#='(X, 1))``).  The
``#=`` family (``#=``, ``#\\=``, ``#<``, ``#>``, ``#=<``, ``#>=``) is
registered in :mod:`clausal.logic.builtins.iso_compare`.  ``label/1`` keeps
the engine's first-fail meaning; Scryer's (leftmost) ``label/1`` is
``labeling([], Vs)``, which a ``.pl`` file importing library(clpz) gets
under the name ``label`` (``clausal.stdlib.clpz``).  The implementation is
:mod:`clausal.logic.clpz_surface`, over :mod:`clausal.logic.clpfd`.
"""
from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


@_builtin("in", 2, fields=("var", "domain"))
def _clpz_in(x, dom, trail, k):
    """X in Dom -- X is an element of the clpz domain Dom (``1..3``,
    ``inf..sup``, ``1..3 \\/ 5..7``, an integer)."""
    from clausal.logic.clpz_surface import clpz_in  # noqa: PLC0415
    if clpz_in(x, dom, trail):
        yield None


@_builtin("ins", 2, fields=("vars", "domain"))
def _clpz_ins(xs, dom, trail, k):
    """Xs ins Dom -- every element of the list Xs is in Dom."""
    from clausal.logic.clpz_surface import clpz_ins  # noqa: PLC0415
    if clpz_ins(xs, dom, trail):
        yield None


@_builtin("labeling", 2, fields=("options", "vars"))
def _clpz_labeling(options, xs, trail, k):
    """labeling(Options, Vars) -- Scryer's clpz labeling search."""
    from clausal.logic.clpz_surface import labeling  # noqa: PLC0415
    yield from labeling(options, xs, trail)


def _connective(name: str, arity: int):
    fields = ("p",) if arity == 1 else ("p", "q")

    def run(*args):
        from clausal.logic.clpz_surface import post_connective  # noqa: PLC0415
        trail = args[arity]
        if post_connective(name, args[:arity], trail):
            yield None
    run.__name__ = f"_clpz_{arity}_{name}"
    run.__doc__ = f"{name}/{arity} -- clpz's reified connective."
    return _builtin(name, arity, fields=fields)(run)


for _n in ("#<==>", "#==>", "#<==", "#\\/", "#/\\", "#\\"):
    _connective(_n, 2)
_connective("#\\", 1)
del _n


# ── clpz's reflection predicates and global constraints ─────────────────────
#
# fd_dom/2, fd_size/2, fd_inf/2, fd_sup/2, tuples_in/2,
# global_cardinality/2 and zcompare/3 under Scryer's names.  They were
# existence errors from every front end although the solver implements the
# constraints (clpfd.tuples_in, .global_cardinality, .zcompare).


def _fd_domain(x):
    """The FD domain of *x* as intervals, or None for a non-integer."""
    from clausal.logic.clpfd import FD_KEY  # noqa: PLC0415
    from clausal.logic.variables import deref, get_attr, is_var  # noqa: PLC0415
    x = deref(x)
    if type(x) is int:
        return ((x, x),)
    if is_var(x):
        state = get_attr(x, FD_KEY)
        if state is None:
            return ((float("-inf"), float("inf")),)
        return state.domain
    return None


def _bound_term(b):
    """A domain bound as clpz writes it: an integer, ``inf`` or ``sup``."""
    import math  # noqa: PLC0415
    if isinstance(b, float) and math.isinf(b):
        return "inf" if b < 0 else "sup"
    return int(b)


def _domain_term(dom):
    """Scryer's domain term: ``1..4 \\/ 6..9`` (left-associated), ``3..3``,
    ``inf..sup``."""
    term = None
    for lo, hi in dom:
        piece = ("..", _bound_term(lo), _bound_term(hi))
        term = piece if term is None else ("\\/", term, piece)
    return term


def _integer_or_var(x, ctx):
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    from clausal.logic.variables import deref  # noqa: PLC0415
    dom = _fd_domain(x)
    if dom is None:
        raise LogicException(type_error("integer", deref(x), ctx))
    return dom


@_builtin("fd_dom", 2, fields=("var", "dom"))
def _fd_dom(x, d, trail, k):
    """fd_dom(X, Dom) -- Dom is X's current domain (``1..4\\/6..9``)."""
    from clausal.logic.variables import unify  # noqa: PLC0415
    dom = _integer_or_var(x, "fd_dom/2")
    if dom and unify(d, _domain_term(dom), trail):
        yield None


@_builtin("fd_size", 2, fields=("var", "size"))
def _fd_size(x, s, trail, k):
    """fd_size(X, Size) -- the number of values X can take, ``sup`` if
    unbounded."""
    from clausal.logic.clpfd import domain_size  # noqa: PLC0415
    from clausal.logic.variables import unify  # noqa: PLC0415
    if unify(s, _bound_term(domain_size(_integer_or_var(x, "fd_size/2"))),
             trail):
        yield None


@_builtin("fd_inf", 2, fields=("var", "inf"))
def _fd_inf(x, i, trail, k):
    """fd_inf(X, Inf) -- X's smallest value, ``inf`` if unbounded below."""
    from clausal.logic.variables import unify  # noqa: PLC0415
    dom = _integer_or_var(x, "fd_inf/2")
    if dom and unify(i, _bound_term(dom[0][0]), trail):
        yield None


@_builtin("fd_sup", 2, fields=("var", "sup"))
def _fd_sup(x, s, trail, k):
    """fd_sup(X, Sup) -- X's largest value, ``sup`` if unbounded above."""
    from clausal.logic.variables import unify  # noqa: PLC0415
    dom = _integer_or_var(x, "fd_sup/2")
    if dom and unify(s, _bound_term(dom[-1][1]), trail):
        yield None


def _items(x, ctx):
    from clausal.logic.builtins.lists import _as_items  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error)
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    d = deref(x)
    items = _as_items(d)
    if items is None:
        if is_var(d):
            raise LogicException(instantiation_error(ctx))
        raise LogicException(type_error("list", d, ctx))
    return [deref(i) for i in items]


def _integer(x, ctx):
    """*x* (dereferenced), which must be an integer: instantiation_error
    when unbound, type_error(integer, X) otherwise (Scryer's must_be)."""
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error)
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    x = deref(x)
    if is_var(x):
        raise LogicException(instantiation_error(ctx))
    if type(x) is not int:
        raise LogicException(type_error("integer", x, ctx))
    return x


@_builtin("tuples_in", 2, fields=("tuples", "relation"))
def _tuples_in(tuples, relation, trail, k):
    """tuples_in(Tuples, Relation) -- each tuple (a list of integers or
    variables) is one of Relation's rows (lists of integers)."""
    from clausal.logic.clpfd import tuples_in  # noqa: PLC0415
    tups = [_items(t, "tuples_in/2") for t in _items(tuples, "tuples_in/2")]
    rows = [tuple(_integer(e, "tuples_in/2") for e in _items(r, "tuples_in/2"))
            for r in _items(relation, "tuples_in/2")]
    # a row of another length matches no tuple (Scryer fails)
    rows = [r for r in rows if all(len(r) == len(t) for t in tups)]
    if tups and not rows:
        return
    if tuples_in(tups, rows, trail):
        yield None


@_builtin("global_cardinality", 2, fields=("vars", "pairs"))
def _global_cardinality(vs, pairs, trail, k):
    """global_cardinality(Vs, Pairs) -- each Key-Count of Pairs: Count of
    Vs equal Key, and every element of Vs is one of the Keys."""
    from clausal.logic.clpfd import global_cardinality  # noqa: PLC0415
    from clausal.pythonic_ast.nodes import Sub  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    from clausal.logic.exceptions import instantiation_error  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415
    kc = []
    for p in _items(pairs, "global_cardinality/2"):
        if is_var(p):
            raise LogicException(instantiation_error("global_cardinality/2"))
        if type(p) is tuple and len(p) == 3 and p[0] == "-":
            parts = (p[1], p[2])
        elif type(p) is Sub:
            parts = (p.left, p.right)
        else:
            parts = None
        if parts is None:
            # Scryer: domain_error(gcc_pair, P)
            from clausal.logic.exceptions import domain_error  # noqa: PLC0415
            raise LogicException(domain_error("gcc_pair", p,
                                              "global_cardinality/2"))
        kc.append((_integer(parts[0], "global_cardinality/2"), parts[1]))
    if global_cardinality(_items(vs, "global_cardinality/2"), kc, trail):
        yield None


@_builtin("zcompare", 3, fields=("order", "x", "y"))
def _zcompare(order, x, y, trail, k):
    """zcompare(Order, X, Y) -- Order is the order of X and Y (``<``, ``=``
    or ``>``), as a constraint."""
    from clausal.logic.clpfd import zcompare  # noqa: PLC0415
    if zcompare(order, x, y, trail):
        yield None


@_builtin("all_distinct", 1, fields=("vars",))
def _all_distinct(vs, trail, k):
    """all_distinct(Vs) -- clpz's name for all_different/1 (the same
    solutions; clpz's all_distinct propagates harder)."""
    from clausal.logic.clpfd import all_different  # noqa: PLC0415
    if all_different(_items(vs, "all_distinct/1"), trail):
        yield None
