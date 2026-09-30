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
from clausal.logic import clpfd as _fd


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
    # Repeated keys (domain_error(gcc_unique_key_pairs, Pairs)), counts
    # (integer or variable) and elements are checked by
    # clpfd.global_cardinality, after the units side channel has turned a
    # dimensionless quantity into its plain integer.
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


@_builtin("lex_chain", 1, fields=("lists",))
def _lex_chain(lists, trail, k):
    """lex_chain(Lists) -- each list is lexicographically less than or equal
    to the next.  Posted as the reified chain ``A1 #< B1 #\\/ (A1 #= B1
    #/\\ lex(Rest))`` (true on exhausted lists) plus ``A1 #=< B1``: the
    same solutions as Scryer's lex_le, with weaker propagation past the
    first position."""
    from clausal.logic.clpz_surface import post_connective  # noqa: PLC0415
    ls = [_items(li, "lex_chain/1") for li in _items(lists, "lex_chain/1")]
    for li in ls:                   # every element first, as Scryer checks
        for x in li:
            _integer_or_fd_var(x, "lex_chain/1")
    for a, b in zip(ls, ls[1:]):
        if len(a) != len(b):
            return                  # lists of different lengths: Scryer fails
        # A1 #=< B1 always holds for a lexicographic =<: posted plainly it
        # prunes the first position before labelling (the reified chain
        # alone would wait)
        if a and not _fd.fd_le(a[0], b[0], trail):
            return
        term = 1
        for x, y in reversed(list(zip(a, b))):
            term = ("#\\/", ("#<", x, y), ("#/\\", ("#=", x, y), term))
        if term == 1:
            continue
        if not post_connective(term[0], term[1:], trail):
            return
    yield None


def _integer_or_fd_var(x, ctx):
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    x = deref(x)
    if not (is_var(x) or type(x) is int):
        raise LogicException(type_error("integer", x, ctx))


#: chain/2's relation atoms (clpz's) -> clpfd.chain's names
_CHAIN_RELATIONS = {"#=": "eq", "#<": "lt", "#>": "gt", "#=<": "le",
                    "#>=": "ge"}


@_builtin("chain", 2, fields=("relation", "vars"))
def _chain(relation, vs, trail, k):
    """chain(Relation, Zs) -- Scryer's argument order: consecutive elements
    of Zs are related by Relation, one of ``#=``, ``#<``, ``#>``, ``#=<``,
    ``#>=``.  Checks in Scryer's order: Zs a list of integers/variables,
    then Relation ground and one of those."""
    from clausal.logic.clpfd import chain  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, domain_error, instantiation_error)
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    zs = _items(vs, "chain/2")
    for z in zs:
        _integer_or_fd_var(z, "chain/2")
    rel = deref(relation)
    if is_var(rel):
        raise LogicException(instantiation_error("chain/2"))
    name = _CHAIN_RELATIONS.get(rel) if type(rel) is str else None
    if name is None:
        raise LogicException(domain_error("chain_relation", rel, "chain/2"))
    if chain(zs, name, trail):
        yield None


@_builtin("fd_var", 1, fields=("var",))
def _fd_var(x, trail, k):
    """fd_var(X) -- X is an unbound variable with a finite-domain
    constraint (an integer, a plain variable or any other term is not)."""
    from clausal.logic.clpfd import FD_KEY  # noqa: PLC0415
    from clausal.logic.variables import deref, get_attr, is_var  # noqa: PLC0415
    x = deref(x)
    if is_var(x) and get_attr(x, FD_KEY) is not None:
        yield None


@_builtin("indomain", 1, fields=("var",))
def _indomain(x, trail, k):
    """indomain(X) -- label(X) for one variable: X takes each value of its
    (finite) domain, ascending; an integer succeeds once."""
    from clausal.logic.clpz_surface import label  # noqa: PLC0415
    yield from label([x], trail)


class NValueConstraint(_fd.Constraint):
    """``N`` is the number of distinct values among ``Vars``: N lies
    between the distinct values already taken (at least 1 when Vars is
    not empty) and the smaller of len(Vars) and the size of the union
    of their domains; once every variable is bound N is that count, and
    once N distinct values are taken the rest must repeat them."""
    __slots__ = ('n', 'vs')

    def __init__(self, n, vs):
        self.n = n
        self.vs = tuple(vs)
        super().__init__((n,) + self.vs)

    def propagate(self, trail, queue) -> bool:
        from clausal.logic.variables import deref, is_var  # noqa: PLC0415
        vs = [deref(v) for v in self.vs]
        taken = {v for v in vs if type(v) is int}
        doms = [_fd._expr_domain(v, trail) for v in vs]
        union = _fd._domain_union(list(doms))
        lo = max(len(taken), 1 if vs else 0)
        hi = min(len(vs), _fd.domain_size(union)) if vs else 0
        if all(type(v) is int for v in vs):
            lo = hi = len(taken)
        n = deref(self.n)
        nd = _fd.domain_intersection(_fd._expr_domain(n, trail),
                                     _fd.domain_from_range(lo, hi))
        if not nd:
            return False
        if is_var(n) and not _fd._narrow_if_changed(n, nd, trail, queue):
            return False
        n = deref(self.n)
        if type(n) is int and n == len(taken) and taken:
            allowed = _fd._indices_to_domain(sorted(taken))
            for v in vs:
                if is_var(v):
                    dv = _fd.domain_intersection(
                        _fd._expr_domain(v, trail), allowed)
                    if not dv or not _fd._narrow_if_changed(
                            v, dv, trail, queue):
                        return False
        return True



@_builtin("nvalue", 2, fields=("n", "vars"))
def _nvalue(n, vs, trail, k):
    """nvalue(N, Vars) -- N is the number of distinct values in Vars."""
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    items = _items(vs, "nvalue/2")
    for x in items:
        _integer_or_fd_var(x, "nvalue/2")
    _integer_or_fd_var(n, "nvalue/2")
    for x in items + [n]:
        if is_var(deref(x)):
            _fd._ensure_fd(deref(x), trail)
    c = NValueConstraint(n, items)
    if _fd._post_constraint(c, trail):
        yield None


def _cumulative(tasks, options, trail):
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, domain_error, instantiation_error, type_error)
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    ctx = "cumulative/2"
    ts = _items(tasks, ctx)
    opts = _items(options, ctx)
    if not opts:
        limit = 1
    elif (len(opts) == 1 and type(opts[0]) is tuple and len(opts[0]) == 2
          and opts[0][0] == "limit"):
        limit = _integer(opts[0][1], ctx)
    else:
        raise LogicException(domain_error(
            "cumulative_options_empty_or_limit", opts, ctx))
    triples = []
    for t in ts:
        if not (type(t) is tuple and len(t) == 6 and t[0] == "task"):
            return False            # not a task/5: Scryer fails
        s, d, e, c = (deref(a) for a in t[1:5])
        for x in (s, e):
            _integer_or_fd_var(x, ctx)
        if not (type(d) is int and type(c) is int):
            # the constraint reasons over fixed durations and consumptions
            # (Scryer accepts variables there too)
            if is_var(d) or is_var(c):
                raise LogicException(instantiation_error(
                    f"{ctx}: a task's duration and consumption must be "
                    f"integers here"))
            raise LogicException(type_error(
                "integer", d if type(d) is not int else c, ctx))
        if d <= 0 or c < 0:
            return False            # Scryer: D #> 0, C #>= 0
        # E = S + D
        if not _fd.fd_eq(e, ("+", s, d), trail):
            return False
        triples.append((s, d, c))
    return _fd.cumulative(triples, limit, trail)


@_builtin("cumulative", 2, fields=("tasks", "options"))
def _cumulative_2(tasks, options, trail, k):
    """cumulative(Tasks, Options) -- each task(S, D, E, C, T) runs from S
    to E = S + D consuming C; at every moment the running tasks consume at
    most the limit (``[limit(L)]``; 1 by default).  Durations and
    consumptions must be integers here."""
    if _cumulative(tasks, options, trail):
        yield None


@_builtin("cumulative", 1, fields=("tasks",))
def _cumulative_1(tasks, trail, k):
    """cumulative(Tasks) -- cumulative(Tasks, [limit(1)])."""
    if _cumulative(tasks, [], trail):
        yield None


@_builtin("serialized", 2, fields=("starts", "durations"))
def _serialized(starts, durations, trail, k):
    """serialized(Starts, Durations) -- the tasks (Start, Duration) do not
    overlap: for each pair, ``Si + Di #=< Sj #\\/ Sj + Dj #=< Si``.
    Durations are non-negative integers (Scryer's must_be(list(integer)))."""
    from clausal.logic.clpz_surface import post_connective  # noqa: PLC0415
    ctx = "serialized/2"
    ds = [_integer(d, ctx) for d in _items(durations, ctx)]
    ss = _items(starts, ctx)
    if len(ss) != len(ds) or any(d < 0 for d in ds):
        return
    for s in ss:
        _integer_or_fd_var(s, ctx)
    for i in range(len(ss)):
        for j in range(i + 1, len(ss)):
            if not post_connective("#\\/", (
                    ("#=<", ("+", ss[i], ds[i]), ss[j]),
                    ("#=<", ("+", ss[j], ds[j]), ss[i])), trail):
                return
    yield None


@_builtin("disjoint2", 1, fields=("rectangles",))
def _disjoint2(rects, trail, k):
    """disjoint2(Rectangles) -- each F(X, W, Y, H) is a rectangle and no two
    overlap; Scryer's decomposition, pair by pair and both ways::

        AX #=< BX #/\\ BX #< AX + AW #==> AY + AH #=< BY #\\/ BY + BH #=< AY
        AY #=< BY #/\\ BY #< AY + AH #==> AX + AW #=< BX #\\/ BX + BW #=< AX
    """
    from clausal.logic.clpz_surface import post_connective  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    from clausal.logic.exceptions import instantiation_error  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415
    ctx = "disjoint2/1"
    rs = []
    for r in _items(rects, ctx):
        if is_var(r):
            raise LogicException(instantiation_error(ctx))   # Scryer's =..
        rs.append(r)
    if len(rs) < 2:
        yield None                  # no pair to compare: Scryer succeeds
        return
    for i, r in enumerate(rs):
        if not (type(r) is tuple and len(r) == 5 and type(r[0]) is str):
            return                  # not F(X, W, Y, H): no pattern matches
        for a in r[1:]:
            _integer_or_fd_var(a, ctx)
        rs[i] = r[1:]

    def a_not_in_b(a, b):
        ax, aw, ay, ah = a
        bx, bw, by, bh = b
        return (post_connective("#==>", (
                    ("#/\\", ("#=<", ax, bx), ("#<", bx, ("+", ax, aw))),
                    ("#\\/", ("#=<", ("+", ay, ah), by),
                     ("#=<", ("+", by, bh), ay))), trail)
                and post_connective("#==>", (
                    ("#/\\", ("#=<", ay, by), ("#<", by, ("+", ay, ah))),
                    ("#\\/", ("#=<", ("+", ax, aw), bx),
                     ("#=<", ("+", bx, bw), ax))), trail))

    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            if not (a_not_in_b(rs[i], rs[j]) and a_not_in_b(rs[j], rs[i])):
                return
    yield None


@_builtin("automaton", 3, fields=("vars", "nodes", "arcs"))
def _automaton_3(vs, nodes, arcs, trail, k):
    """automaton(Vs, Nodes, Arcs) -- the sequence Vs is accepted by the
    automaton: Nodes lists source(N) and sink(N), Arcs arc(From, Label, To)
    with integer labels.  Scryer's decomposition: a state variable between
    each pair of elements, the first in the sources, the last in the sinks,
    and each step [S0, V, S1] in the arcs relation (tuples_in/2)."""
    from clausal.logic.clpfd import tuples_in  # noqa: PLC0415
    from clausal.logic.clpz_surface import _post  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException, instantiation_error  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    ctx = "automaton/3"
    seq = _items(vs, ctx)
    for x in seq:
        _integer_or_fd_var(x, ctx)
    numbers: dict = {}

    def num(node):
        # a node is named by a ground term (its walked value is the key)
        key = _deref_walk(node)
        try:
            hash(key)
        except TypeError:
            key = repr(key)
        if _has_var(key):
            raise LogicException(instantiation_error(ctx))
        if key not in numbers:
            numbers[key] = len(numbers)
        return numbers[key]

    relation = []
    for a in _items(arcs, ctx):
        # arc(From, Label, To), or arc/4 with no counter expressions;
        # anything else has no clause in Scryer's arc_normalized_: fail
        if type(a) is tuple and len(a) == 4 and a[0] == "arc":
            relation.append((num(a[1]), _integer(a[2], ctx), num(a[3])))
        elif (type(a) is tuple and len(a) == 5 and a[0] == "arc"
              and _items(a[4], ctx) == []):
            relation.append((num(a[1]), _integer(a[2], ctx), num(a[3])))
        else:
            return
    sources, sinks = [], []
    for n in _items(nodes, ctx):
        # Scryer picks out source/1 and sink/1 and ignores the rest
        if type(n) is tuple and len(n) == 2 and n[0] == "source":
            sources.append(num(n[1]))
        elif type(n) is tuple and len(n) == 2 and n[0] == "sink":
            sinks.append(num(n[1]))
    if not sources or not sinks:
        return
    states = [Var() for _ in range(len(seq) + 1)]
    src = tuple((s, s) for s in sorted(set(sources)))
    snk = tuple((s, s) for s in sorted(set(sinks)))
    if not (_post([states[0]], _fd._domain_union([src]), trail)
            and _post([states[-1]], _fd._domain_union([snk]), trail)):
        return
    if not seq:
        yield None
        return
    if not relation:
        return
    rows = [[states[i], seq[i], states[i + 1]] for i in range(len(seq))]
    if tuples_in(rows, relation, trail):
        yield None


def _has_var(t) -> bool:
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    stack = [t]
    while stack:
        x = deref(stack.pop())
        if is_var(x):
            return True
        if type(x) in (tuple, list):
            stack.extend(x)
    return False


# ── library(clpz) additions: global_cardinality/3 and sum/3 ───────────────


@_builtin("global_cardinality", 3, fields=("vars", "pairs", "options"))
def _global_cardinality_3(vs, pairs, options, trail, k):
    """global_cardinality(Vs, Pairs, Options) -- as global_cardinality/2,
    with Scryer's options ``consistency(value)`` and ``cost(Cost,
    Matrix)``."""
    from clausal.logic.clpz_surface import clpz_global_cardinality  # noqa: PLC0415
    if clpz_global_cardinality(vs, pairs, options, trail):
        yield None


@_builtin("$clpz_sum", 3, fields=("vars", "op", "value"))
def _clpz_sum(vs, op, value, trail, k):
    """library(clpz)'s sum(Vs, Op, Value) (Scryer's).  NOT a global
    ``sum/3``: a global would shadow Python's ``sum`` inside a seam ``++``
    escape, so ``clausal.stdlib.clpz`` defines ``sum/3`` over this and only
    a ``.pl`` file that imports library(clpz) gets the name."""
    from clausal.logic.clpz_surface import clpz_sum  # noqa: PLC0415
    if clpz_sum(vs, op, value, trail):
        yield None
