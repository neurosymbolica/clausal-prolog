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
"""
import random
from fractions import Fraction

FAMILIES = ("chain", "dense", "banded", "degenerate", "mixed")

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


_BUILDERS = {"chain": chain, "dense": dense, "banded": banded,
             "degenerate": degenerate, "mixed": mixed}


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
