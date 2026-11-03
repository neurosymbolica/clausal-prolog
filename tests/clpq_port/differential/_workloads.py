"""Seeded CLP(Q) workloads for the differential harness, small to large.

A workload is plain data (JSON-able): ``{"id", "variables", "steps"}``.
``variables`` is how many program variables X0..X{n-1} there are, made in
that order before the first step; each step is a list whose first element
names it:

=============================================  ================================
``["post", rel, terms, constant]``             ``{sum(c*Xi) rel constant}``
``["nonlinear", rel, i, j, constant]``         ``{Xi*Xj rel constant}`` (waits)
``["bind", i, value]``                         ``Xi = value``
``["alias", i, j]``                            ``Xi = Xj``
``["mark"]`` / ``["undo"]``                    a trail mark / undo to the newest
``["sup", terms]`` / ``["inf", terms]``        sup/2, inf/2 into a fresh S
``["maximize", terms]``, ``["minimize", ...]`` maximize/1 then the optimum
``["bb_inf", ints, terms, epsilon]``           bb_inf/3 (epsilon None) or /5
``["entailed", rel, terms, constant]``         entailed/1
``["dump", indices]``                          dump/3 onto those variables
``["unify", shape, lefts, rights]``            one unification of two lists
                                               (shape "list") or of two cells
                                               f(...) (shape "f"); each
                                               element ``["x", i]`` (Xi) or
                                               ``["n", number]``
=============================================  ================================

``rel`` is one of ``=<  <  >=  >  =:=  =\\=``; ``terms`` is a list of
``[index, coefficient]`` pairs, a coefficient or constant an int or the
string ``"n/d"`` of a rational.  The families (each from its own
``random.Random(f"{family}:{size}:{seed}")``, so a workload never depends
on which others are generated):

* ``chain``: X{i+1} = a*Xi + b, bounds at the ends, optima at the far end,
  a binding under a mark, dumps of the ends;
* ``dense``: random rows of 2..6 nonzeros over a box, a few equations and
  disequations, optima of random objectives, maximize under a mark,
  bindings and aliases, dumps of subsets;
* ``degenerate``: tied optima: rows Xi + X{i+1} =< 1 over Xi >= 0 with an
  objective parallel to a face, bb_inf/5 with ties, inf of a direction the
  store does not limit;
* ``mixed``: every step kind interleaved at random, non-linear constraints
  that wait and wake when a factor is bound, nested marks and undos.

The multi-binding families bind SEVERAL variables of one store in ONE
unification (DEVIATIONS.md D3, "Several variables bound in one
unification": the order in which the bound variables' work is done):

* ``chain_bind``: a chain X0 =< X1 =< ... (some links strict, some
  equations), bound in one unification: the whole list to numbers, a
  subset in increasing, decreasing or shuffled order, a prefix and a
  suffix, numbers that break the chain (failure), lists of variables
  (aliases along the chain), mixed lists, partial overlaps; most under a
  mark, with dumps of what stays unbound, the last one kept;
* ``dense_bind``: random sparse rows that hold at a hidden integer point,
  then cells ``f(Xa, Xb, Xc) = f(1, Xd, 3)``: numbers from the point (or
  off it), variable-variable pairs, a variable on both sides;
* ``implied_bind``: equations ``Xi + X(i+1) = c`` and bounds, so binding
  some variables implies the values of others (bv.pl's export_binding/1
  fires inside the unification), with the implied variable bound in the
  same unification before or after, to its implied value or another;
  bindings after a mark and an undo.
"""
import random
from fractions import Fraction

FAMILIES = ("chain", "dense", "banded", "degenerate", "mixed",
            "chain_bind", "dense_bind", "implied_bind")

RELATIONS = ("=<", "<", ">=", ">", "=:=", "=\\=")


def number(value):
    """A Fraction as the workload spells it: an int, or ``"n/d"``."""
    value = Fraction(value)
    if value.denominator == 1:
        return int(value)
    return f"{value.numerator}/{value.denominator}"


def value_of(spelt):
    """The Fraction a workload number spells."""
    return Fraction(spelt)


def _coefficient(rng, low=-5, high=5, rational=0.1):
    while True:
        if rng.random() < rational:
            value = Fraction(rng.randint(low, high), rng.randint(2, 4))
        else:
            value = Fraction(rng.randint(low, high))
        if value:
            return number(value)


def _terms(rng, n, width, rational=0.1):
    width = max(1, min(width, n))
    return [[i, _coefficient(rng, rational=rational)]
            for i in sorted(rng.sample(range(n), width))]


def _row(rng, n, width, relations=("=<", "=<", "<", ">=", ">")):
    return ["post", rng.choice(relations), _terms(rng, n, width),
            rng.randint(-10, 20)]


def _box(rng, n, low=0, high=10, strict=0.2):
    steps = []
    for i in range(n):
        steps.append(["post", ">" if rng.random() < strict else ">=",
                      [[i, 1]], rng.randint(low - 2, low)])
        steps.append(["post", "<" if rng.random() < strict else "=<",
                      [[i, 1]], rng.randint(high, high + 3)])
    return steps


def _objective(rng, n, width):
    return _terms(rng, n, width, rational=0.05)


def _subset(rng, n, most):
    return sorted(rng.sample(range(n), rng.randint(1, max(1, min(n, most)))))


#: The most variables a projection of a dense store eliminates: each
#: Fourier-Motzkin step can square the rows, and a projection past the
#: clpq_projection cap raises resource_error after seconds of work (and
#: where it raises depends on the work count, not only the algorithm).
_DENSE_ELIMINATION = 6

#: The largest dense store dumped at all: dump/3 eliminates the slack
#: variables of the store, seconds of work per dump at 30 variables.
_DENSE_DUMP = 24

#: The longest band projected onto a few of its variables.
_BANDED_PROJECTION = 40


def _projection(rng, n, most):
    """A subset to dump a dense store onto: any subset of a small store,
    all but at most a few variables of a larger one."""
    if n <= _DENSE_ELIMINATION:
        return _subset(rng, n, most)
    dropped = set(rng.sample(range(n), rng.randint(0, 1)))
    return [i for i in range(n) if i not in dropped]


def chain(rng, n):
    steps = [["post", ">=", [[0, 1]], 0], ["post", "=<", [[0, 1]], rng.randint(1, 9)]]
    for i in range(n - 1):
        a = rng.choice([1, 1, 2, -1, "1/2", "2/3", 3])
        b = rng.randint(-3, 3)
        # X{i+1} - a*Xi = b
        steps.append(["post", "=:=", [[i, number(-value_of(a))], [i + 1, 1]], b])
        if rng.random() < 0.15:
            steps.append(["post", rng.choice(["=<", "<"]), [[i + 1, 1]],
                          rng.randint(5, 40)])
    last = n - 1
    steps += [["sup", [[last, 1]]], ["inf", [[last, 1]]],
              ["dump", [0, last]],
              ["mark"], ["bind", 0, rng.randint(0, 3)], ["dump", [last]],
              ["undo"], ["dump", sorted({0, n // 2, last})]]
    return steps


def dense(rng, n):
    steps = _box(rng, n)
    rows = n + rng.randint(0, n)
    for _ in range(rows):
        k = rng.random()
        if k < 0.08:
            steps.append(["post", "=:=", _terms(rng, n, rng.randint(2, 4)),
                          rng.randint(0, 10)])
        elif k < 0.12:
            steps.append(["post", "=\\=", _terms(rng, n, rng.randint(1, 3)),
                          rng.randint(0, 10)])
        else:
            steps.append(_row(rng, n, rng.randint(2, 6)))
    for _ in range(rng.randint(1, 3)):
        objective = _objective(rng, n, rng.randint(1, 5))
        steps += [["sup", objective], ["inf", objective]]
    early, objective, later = (_projection(rng, n, 6), _objective(rng, n, 3),
                               _projection(rng, n, 4))
    dumps = n <= _DENSE_DUMP
    steps += [["dump", early]] if dumps else []
    steps += [["mark"], ["maximize", objective]]
    steps += [["dump", later]] if dumps else []
    steps.append(["undo"])
    for _ in range(rng.randint(1, 3)):
        if rng.random() < 0.5:
            steps.append(["bind", rng.randrange(n), rng.randint(0, 10)])
        else:
            i, j = rng.sample(range(n), 2)
            steps.append(["alias", i, j])
        steps.append(["entailed", rng.choice(RELATIONS[:4]),
                      _terms(rng, n, 2), rng.randint(-5, 15)])
    if n <= _DENSE_DUMP:
        steps.append(["dump", _projection(rng, n, 6)])
        steps.append(["dump", list(range(n))])
    return steps


def banded(rng, n):
    """Sparse rows over neighbours (a band of width 2..4): a store that
    stays cheap to project at 200 variables."""
    width = rng.randint(2, 4)
    steps = _box(rng, n, low=0, high=20, strict=0.1)
    for i in range(n - 1):
        span = list(range(i, min(n, i + width)))
        terms = [[j, _coefficient(rng, -3, 3)] for j in span]
        relation = "=:=" if rng.random() < 0.1 else rng.choice(["=<", ">=", "<"])
        steps.append(["post", relation, terms, rng.randint(0, 25)])
    for _ in range(2):
        objective = _objective(rng, n, rng.randint(2, 6))
        steps += [["sup", objective], ["inf", objective]]
    # A projection onto a few variables of a long band derives rows past
    # the clpq_projection cap from about 100 variables on.
    projections = n <= _BANDED_PROJECTION
    steps += [["mark"], ["minimize", _objective(rng, n, 4)]]
    steps += [["dump", [0, n - 1]]] if projections else []
    steps += [["undo"], ["bind", rng.randrange(n), rng.randint(0, 5)]]
    subset = sorted(rng.sample(range(n), min(n, 3)))
    steps += [["dump", subset]] if projections else []
    steps.append(["dump", list(range(n))])
    return steps


def degenerate(rng, n):
    steps = [["post", ">=", [[i, 1]], 0] for i in range(n)]
    for i in range(n - 1):
        steps.append(["post", "=<", [[i, 1], [i + 1, 1]], 1])
    if n > 2:
        steps.append(["post", "=<", [[0, 1], [n - 1, 1]], 1])
    everything = [[i, 1] for i in range(n)]
    steps += [["sup", everything], ["inf", [[i, -1] for i in range(n)]]]
    ints = _subset(rng, n, 6)
    steps.append(["bb_inf", ints, [[i, -1] for i in ints],
                  rng.choice([None, 0, "1/1000"])])
    steps.append(["bb_inf", ints, [[i, 1] for i in ints], None])
    # a direction the store does not limit from below: inf fails
    steps.append(["inf", [[0, 1], [1, -1]] if n > 1 else [[0, -1]]])
    steps += [["mark"], ["maximize", [[i, 2] for i in range(n)]],
              ["dump", list(range(min(n, 6)))], ["undo"]]
    steps += [["mark"], ["minimize", [[0, 1], [n - 1, -1]] if n > 1 else [[0, 1]]],
              ["dump", [0, n - 1]], ["undo"]]
    steps.append(["dump", list(range(n))])
    return steps


def mixed(rng, n):
    steps = _box(rng, n, low=-5, high=5, strict=0.3)
    depth = 0
    for _ in range(2 * n + rng.randint(5, 15)):
        k = rng.random()
        if k < 0.30:
            steps.append(_row(rng, n, rng.randint(1, 4),
                              relations=("=<", "<", ">=", ">", "=:=", "=\\=")))
        elif k < 0.38 and n > 1:
            i, j = rng.sample(range(n), 2)
            steps.append(["nonlinear", rng.choice(["=:=", "=<"]), i, j,
                          rng.randint(-6, 6)])
        elif k < 0.46:
            steps.append(["bind", rng.randrange(n),
                          number(Fraction(rng.randint(-6, 6), rng.choice([1, 1, 2])))])
        elif k < 0.52 and n > 1:
            i, j = rng.sample(range(n), 2)
            steps.append(["alias", i, j])
        elif k < 0.60:
            steps.append(["mark"])
            depth += 1
        elif k < 0.68 and depth:
            steps.append(["undo"])
            depth -= 1
        elif k < 0.76:
            steps.append([rng.choice(["sup", "inf"]), _objective(rng, n, 3)])
        elif k < 0.80:
            steps.append([rng.choice(["maximize", "minimize"]),
                          _objective(rng, n, 2)])
        elif k < 0.84:
            ints = _subset(rng, n, 3)
            steps.append(["bb_inf", ints, _objective(rng, n, 2),
                          rng.choice([None, 0])])
        elif k < 0.90:
            steps.append(["entailed", rng.choice(RELATIONS),
                          _terms(rng, n, 2), rng.randint(-5, 5)])
        else:
            steps.append(["dump", _subset(rng, n, 5)])
    steps.append(["dump", list(range(n))])
    return steps


# ---------------------------------------------------------- multi-binding

def _var(i):
    return ["x", i]


def _num(value):
    return ["n", number(value)]


def _unify(rng, pairs, shape=None):
    """One ``unify`` step over *pairs* of element specs, each pair's two
    sides swapped at random (``X = 1`` or ``1 = X``: the same binding)."""
    lefts, rights = [], []
    for left, right in pairs:
        if rng.random() < 0.25:
            left, right = right, left
        lefts.append(left)
        rights.append(right)
    return ["unify", shape or rng.choice(["list", "f"]), lefts, rights]


def _orders(rng, indices):
    """*indices* in one of: increasing, decreasing, shuffled."""
    k = rng.random()
    indices = sorted(indices)
    if k < 0.35:
        return indices
    if k < 0.65:
        return indices[::-1]
    rng.shuffle(indices)
    return indices


def chain_bind(rng, n):
    """X0 =< X1 =< ... with a few strict links and equations, and a
    hidden point on it; then multi-variable unifications."""
    point, value = [], rng.randint(-3, 3)
    steps = []
    for i in range(n):
        point.append(value)
        if i + 1 < n:
            k = rng.random()
            if k < 0.08:                        # X(i+1) = Xi + c
                step = rng.randint(0, 2)
                steps.append(["post", "=:=", [[i, -1], [i + 1, 1]], step])
            elif k < 0.2:                       # Xi < X(i+1)
                step = rng.randint(1, 3)
                steps.append(["post", "<", [[i, 1], [i + 1, -1]], 0])
            else:                               # Xi =< X(i+1)
                step = rng.randint(0, 2)
                steps.append(["post", "=<", [[i, 1], [i + 1, -1]], 0])
            value += step
    if rng.random() < 0.5:
        steps.append(["post", ">=", [[0, 1]], point[0] - rng.randint(0, 2)])
    if rng.random() < 0.5:
        steps.append(["post", "=<", [[n - 1, 1]], point[-1] + rng.randint(0, 2)])
    everything = list(range(n))
    shown = sorted({0, n // 3, n // 2, n - 1})
    episodes = [
        # the whole chain to the point, first to last
        lambda: [_unify(rng, [(_var(i), _num(point[i])) for i in everything],
                        "list")],
        # a subset in some order
        lambda: [_unify(rng, [(_var(i), _num(point[i]))
                              for i in _orders(rng, _subset(rng, n, max(2, n // 2)))])],
        # a prefix, or a suffix
        lambda: [_unify(rng, [(_var(i), _num(point[i]))
                              for i in _orders(rng, range(rng.randint(1, n)))])],
        lambda: [_unify(rng, [(_var(i), _num(point[i]))
                              for i in _orders(rng, range(rng.randint(0, n - 1), n))])],
        # numbers that break the chain somewhere
        lambda: [_unify(rng, [(_var(i), _num(point[i] - (3 if i == n - 1 else 0)))
                              for i in _orders(rng, _subset(rng, n, n))])],
        # variables to variables (aliases along the chain), some numbers
        lambda: [_unify(rng, [(_var(i), _var(j) if rng.random() < 0.7
                               else _num(point[i]))
                              for i, j in _alias_pairs(rng, n, point)])],
        # a variable on both sides: [Xi, Xj] = [Xj, c]
        lambda: [_unify(rng, _overlap(rng, n, point), "list")],
    ]
    for _ in range(rng.randint(3, 6)):
        steps.append(["mark"])
        steps += rng.choice(episodes)()
        steps += [["dump", shown], ["undo"]]
    steps += rng.choice(episodes)()
    steps += [["sup", [[n - 1, 1]]], ["inf", [[0, 1]]]]
    if n <= 120:
        steps.append(["dump", shown])
    return steps


def _alias_pairs(rng, n, point):
    """Pairs (i, j), i != j, with equal point values where the chain has
    them, else neighbours (which may make the store fail)."""
    pairs = []
    for i in _orders(rng, _subset(rng, n, max(2, n // 3))):
        same = [j for j in range(max(0, i - 3), min(n, i + 4))
                if j != i and point[j] == point[i]]
        if same:
            pairs.append((i, rng.choice(same)))
        elif n > 1:
            pairs.append((i, i + 1 if i + 1 < n else i - 1))
    return pairs


def _overlap(rng, n, point):
    """[Xi, Xj, ...] = [Xj, c, ...]: Xi is bound to Xj and Xj to a number
    in the same unification; or Xi twice."""
    if n < 2:
        return [(_var(0), _num(point[0])), (_var(0), _num(point[0]))]
    i, j = sorted(rng.sample(range(n), 2))
    if rng.random() < 0.5:
        i, j = j, i
    pairs = [(_var(i), _var(j)), (_var(j), _num(point[j]))]
    if rng.random() < 0.5:
        k = rng.randrange(n)
        pairs.append((_var(k), _num(point[k])))
    if rng.random() < 0.3:
        pairs.append((_var(i), _num(point[j])))
    return pairs


def _rows_at(rng, n, point, rows, width):
    """*rows* sparse rows over *n* variables that hold at *point*."""
    steps = []
    for _ in range(rows):
        terms = _terms(rng, n, rng.randint(2, width), rational=0.05)
        at = sum(value_of(c) * point[i] for i, c in terms)
        k = rng.random()
        if k < 0.1:
            steps.append(["post", "=:=", terms, number(at)])
        elif k < 0.15:
            steps.append(["post", "=\\=", terms, number(at + rng.choice([-1, 1]))])
        else:
            relation = rng.choice(["=<", "<", ">=", ">", "=<"])
            slack = rng.randint(0, 3) + (1 if relation in ("<", ">") else 0)
            steps.append(["post", relation, terms,
                          number(at + (slack if relation in ("=<", "<") else -slack))])
    return steps


def dense_bind(rng, n):
    point = [rng.randint(0, 6) for _ in range(n)]
    steps = []
    for i in range(n):
        if rng.random() < 0.8:
            steps.append(["post", ">=", [[i, 1]], rng.randint(-2, 0)])
            steps.append(["post", "=<", [[i, 1]], rng.randint(6, 9)])
    steps += _rows_at(rng, n, point, n + rng.randint(0, n), 4)
    shown_most = 6 if n > _DENSE_ELIMINATION else n

    def element(i):
        k = rng.random()
        if k < 0.65:
            return _num(point[i])
        if k < 0.75:
            return _num(point[i] + rng.choice([-1, 1]))
        twins = [j for j in range(n) if j != i and point[j] == point[i]]
        if twins and k < 0.9:
            return _var(rng.choice(twins))
        return _var(rng.randrange(n))

    for _ in range(rng.randint(2, 5)):
        chosen = _orders(rng, _subset(rng, n, min(n, 8)))
        steps.append(["mark"])
        steps.append(_unify(rng, [(_var(i), element(i)) for i in chosen]))
        steps.append(["dump", _projection(rng, n, shown_most)])
        steps.append(["undo"])
    chosen = _orders(rng, _subset(rng, n, max(1, n // 2)))
    steps.append(_unify(rng, [(_var(i), element(i)) for i in chosen]))
    objective = _objective(rng, n, 3)
    steps += [["sup", objective], ["inf", objective]]
    return steps


def implied_bind(rng, n):
    """Xi + X(i+1) = c_i (a path of equations, so every variable is a
    function of X0), bounds on some, and a few free rows; binding a few
    variables in one unification implies the others."""
    point = [rng.randint(0, 5) for _ in range(n)]
    steps = []
    for i in range(n - 1):
        if rng.random() < 0.6:
            steps.append(["post", "=:=", [[i, 1], [i + 1, 1]],
                          point[i] + point[i + 1]])
        else:
            steps.append(["post", ">=", [[i, 1], [i + 1, -1]],
                          point[i] - point[i + 1] - rng.randint(0, 1)])
    for i in range(n):
        if rng.random() < 0.4:
            steps.append(["post", ">=", [[i, 1]], point[i] - rng.randint(0, 2)])
        if rng.random() < 0.4:
            steps.append(["post", "=<", [[i, 1]], point[i] + rng.randint(0, 2)])
    shown = sorted(set(_subset(rng, n, 5)) | {0, n - 1})

    def episode():
        chosen = _orders(rng, _subset(rng, n, min(n, 6)))
        pairs = []
        for i in chosen:
            k = rng.random()
            if k < 0.75:
                pairs.append((_var(i), _num(point[i])))
            elif k < 0.85:
                pairs.append((_var(i), _num(point[i] + 1)))
            elif n > 1:
                pairs.append((_var(i), _var(rng.choice([j for j in range(n) if j != i]))))
        return _unify(rng, pairs or [(_var(0), _num(point[0]))])

    for _ in range(rng.randint(2, 4)):
        steps += [["mark"], episode(), ["dump", shown], ["undo"]]
    steps.append(["mark"])
    steps.append(["bind", rng.randrange(n), point[rng.randrange(n)]])
    steps.append(["undo"])
    steps.append(episode())
    steps.append(["dump", shown])
    return steps


_BUILDERS = {"chain": chain, "dense": dense, "banded": banded,
             "degenerate": degenerate, "mixed": mixed,
             "chain_bind": chain_bind, "dense_bind": dense_bind,
             "implied_bind": implied_bind}


def workload(family, size, seed):
    rng = random.Random(f"{family}:{size}:{seed}")
    return {"id": f"{family}-{size}-{seed}", "variables": size,
            "steps": _BUILDERS[family](rng, size),
            # the observation's closing dump of every variable
            "final_dump": not (family == "dense" and size > _DENSE_DUMP)}


#: (family, sizes, seeds per size).  The default corpus runs in a few
#: seconds; ``CLPQ_DIFFERENTIAL=full`` adds the full one.
_DEFAULT_PLAN = [
    ("chain", (2, 5, 12, 40, 120), 2),
    ("dense", (2, 3, 4, 6, 8, 12), 6),
    ("dense", (20,), 1),
    ("banded", (10, 40), 1),
    ("degenerate", (2, 3, 5, 8, 13, 30), 3),
    ("mixed", (2, 3, 4, 5, 6, 8), 12),
    ("mixed", (12, 20), 2),
    ("chain_bind", (2, 3, 6, 12, 40), 3),
    ("dense_bind", (3, 5, 8, 12), 3),
    ("implied_bind", (2, 4, 8, 20), 3),
]

_FULL_PLAN = [
    ("chain", (2, 3, 5, 8, 12, 20, 40, 80, 120, 200), 6),
    ("dense", (2, 3, 4, 5, 6, 8, 10, 12, 16), 30),
    ("dense", (20, 24), 4),
    ("dense", (30, 40, 60), 2),
    ("dense", (100,), 1),
    ("banded", (5, 10, 20, 40), 10),
    ("banded", (60, 100, 150, 200), 3),
    ("degenerate", (2, 3, 4, 5, 6, 8, 10, 13, 20, 30), 8),
    ("mixed", (2, 3, 4, 5, 6, 8, 10), 60),
    ("mixed", (12, 16, 20, 30, 40), 12),
    ("mixed", (60, 100), 3),
    ("chain_bind", (2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 30, 40), 12),
    ("chain_bind", (60, 100, 150, 200), 3),
    ("dense_bind", (2, 3, 4, 5, 6, 8, 10, 12), 15),
    ("dense_bind", (16, 20, 24), 3),
    ("implied_bind", (2, 3, 4, 5, 6, 8, 10, 12, 20, 30), 12),
    ("implied_bind", (60, 100, 200), 3),
]


def corpus(full=False):
    """The workloads of the default corpus, then (when *full*) the rest of
    the full one; ids are unique."""
    seen = set()
    result = []
    for plan in (_DEFAULT_PLAN, _FULL_PLAN) if full else (_DEFAULT_PLAN,):
        for family, sizes, seeds in plan:
            for size in sizes:
                for seed in range(seeds):
                    key = (family, size, seed)
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append(workload(family, size, seed))
    return result
