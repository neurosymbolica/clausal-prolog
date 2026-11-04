"""Engine-driver workloads: CLP(Q) programs run through the real engine.

The bare-trail workloads (_workloads.py, _observe.py) call the port's API
on a Trail with ``defer`` False, so every hook runs inside the unification
that wakes it.  Programs loaded by the import hook run differently: the
engine's trail defers what a hook queues (``trail.defer`` True) to the next
goal boundary, other attribute hooks (freeze/2, dif/2, CLP(FD)) run on the
same unification, and control constructs undo the store (\\+, if-then-else,
catch/3 after a hook raised, findall/3 between its answers).  An engine
workload is a program with one clause ``q(V1, ..., Vk) :- Body``, loaded as
.pl or .clausal; its observation is every answer of ``q/k`` through
clausal.logic.solve.call, and its trace the port's TRACE events, as for
the bare workloads.

A workload is data: ``{"id", "driver": "engine", "surface", "program",
"shown"}``, ``shown`` the names of the clause head's arguments in order.
The templates (each from its own ``random.Random(f"engine:{template}:
{size}:{seed}")``) build a store over X0..X{size-1} that holds at a hidden
integer point (a box, a path of equations Xi + X(i+1) = c, so a binding
implies its neighbours, and inequalities), then:

* ``freeze``: freeze/2 on row variables, one goal a CLP(Q) post, woken
  when a unification binds variables the store then binds by
  export_binding (inside the CLP(Q) hook);
* ``dif``: dif/2 between row variables and against values, with a
  disjunction of bindings, some of which the store turns into a dif
  violation;
* ``fd``: CLP(FD) constraints posted before the store on a row variable
  and an FD-only one; a binding of the FD variable that the FD propagator
  passes on to the row variable inside the FD hook, or a binding the store
  passes to the row variable inside the CLP(Q) hook, which FD then
  propagates;
* ``findall``: findall/3 whose goal binds an indexed row variable to
  several values in turn and takes an optimum each time, the store
  restored between them, then the store used again;
* ``catch``: a frozen goal that throws, woken by a binding the store
  propagates, caught by catch/3, and the store used after the catch;
* ``negation``: \\+ and \\+ \\+ over bindings and optima, and (.pl only)
  if-then-else whose condition binds row variables;
* ``copy``: copy_term/2 of constrained variables, the copy bound, then the
  originals used (only the originals are shown: copy_term/2 does not copy
  CLP(Q) attributes, todo/copy-term-attributes-freeze-clpz-and-copy-term-
  3-2026-09-30.md, where Scryer copies them);
* ``nonlinear``: delayed abs/min/max/product constraints over row
  variables, woken through the engine's queue.
"""
import itertools
import pathlib
import random
import tempfile
from fractions import Fraction

from clausal.logic.clpq.residual_constraints import residual_strings
from clausal.logic.variables import Var, deref, is_var, walk

TEMPLATES = ("freeze", "dif", "fd", "findall", "catch", "negation", "copy",
             "nonlinear")

#: Templates whose program uses if-then-else, which .clausal refuses.
_PL_ONLY = ("negation",)

_HEAD = """\
:- use_module(library(clpq)).
:- use_module(library(clpz)).
:- use_module(library(freeze)).
:- use_module(library(dif)).
:- use_module(library(lists)).
"""


def _text(value):
    value = Fraction(value)
    if value.denominator == 1:
        return f"({value.numerator})" if value < 0 else str(value.numerator)
    return f"({value.numerator}/{value.denominator})"


def _linear(terms):
    """``2*X0 - (1/2)*X3 + X5``."""
    parts = []
    for index, coefficient in terms:
        coefficient = Fraction(coefficient)
        sign = "-" if coefficient < 0 else "+"
        magnitude = abs(coefficient)
        body = f"X{index}" if magnitude == 1 else f"{_text(magnitude)}*X{index}"
        parts.append((sign, body))
    text = ("-" if parts[0][0] == "-" else "") + parts[0][1]
    for sign, body in parts[1:]:
        text += f" {sign} {body}"
    return text


class _Store:
    """A store over X0..X{n-1} at a hidden point, as goal texts."""

    def __init__(self, rng, n, path=0.6):
        self.rng, self.n = rng, n
        self.point = [rng.randint(0, 5) for _ in range(n)]
        goals = []
        for i in range(n):
            low = self.point[i] - rng.randint(0, 3)
            high = self.point[i] + rng.randint(0, 3)
            goals.append(f"{{X{i} >= {_text(low)}, X{i} =< {_text(high)}}}")
        for i in range(n - 1):
            p, q = self.point[i], self.point[i + 1]
            if rng.random() < path:
                goals.append(f"{{X{i} + X{i + 1} = {p + q}}}")
            else:
                slack = rng.randint(0, 2)
                goals.append(f"{{X{i} - X{i + 1} >= {_text(p - q - slack)}}}")
        for _ in range(rng.randint(0, max(1, n // 3))):
            indices = sorted(rng.sample(range(n), min(n, rng.randint(2, 3))))
            terms = [(i, rng.choice([-2, -1, 1, 2, 3])) for i in indices]
            at = sum(c * self.point[i] for i, c in terms)
            goals.append(f"{{{_linear(terms)} =< {_text(at + rng.randint(0, 3))}}}")
        self.goals = goals

    def variable(self):
        return self.rng.randrange(self.n)

    def binding(self, indices, off=0.0):
        """One unification of the variables *indices* to their point
        values (each off the point with probability *off*), a list or a
        cell; a single variable as ``X = v``."""
        rng = self.rng
        values = [self.point[i] + (rng.choice([-1, 1]) if rng.random() < off else 0)
                  for i in indices]
        if len(indices) == 1:
            return f"X{indices[0]} = {_text(values[0])}"
        lefts = ", ".join(f"X{i}" for i in indices)
        rights = ", ".join(_text(v) for v in values)
        if rng.random() < 0.5:
            return f"[{lefts}] = [{rights}]"
        return f"f({lefts}) = f({rights})"

    def some(self, most=3):
        return sorted(self.rng.sample(range(self.n), self.rng.randint(1, min(self.n, most))))

    def objective(self):
        terms = [(i, self.rng.choice([-1, 1, 2])) for i in self.some(2)]
        return _linear(terms)


def _freeze(store):
    rng = store.rng
    a, b = store.variable(), store.variable()
    c = store.variable()
    goals = store.goals[:]
    goals.insert(rng.randint(0, len(goals)), f"freeze(X{a}, Z = woke)")
    goals.insert(rng.randint(0, len(goals)),
                 f"freeze(X{b}, {{X{c} >= {_text(store.point[c] - rng.randint(0, 1))}}})")
    goals.append(store.binding(store.some(), off=0.05))
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["Z", "S"]


def _dif(store):
    rng = store.rng
    a, b, c = store.variable(), store.variable(), store.variable()
    goals = store.goals[:]
    value = store.point[a] if rng.random() < 0.5 else store.point[a] + 1
    goals.insert(rng.randint(0, len(goals)), f"dif(X{a}, {_text(value)})")
    goals.insert(rng.randint(0, len(goals)), f"dif(X{b}, X{c})")
    branches = [store.binding(store.some(2)) for _ in range(rng.randint(1, 3))]
    goals.append("( " + " ; ".join(branches + ["true"]) + " )")
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["S"]


def _fd(store):
    rng = store.rng
    a = store.variable()
    k = rng.choice([-2, -1, 1, 2])         # not 0: clpz would alias
    c = store.point[a] - k                      # C + k = X(a) at the point
    low, high = c - rng.randint(0, 3), c + rng.randint(0, 3)
    goals = [f"C #>= {_text(low)}", f"C #=< {_text(high)}",
             f"X{a} #= C + {_text(k)}" if k >= 0 else f"X{a} #= C - {_text(-k)}"]
    goals += store.goals
    if rng.random() < 0.5:
        goals.append(f"C = {_text(c)}")             # FD binds X(a) in its hook
    else:
        neighbours = [i for i in (a - 1, a + 1) if 0 <= i < store.n] or [a]
        goals.append(store.binding([rng.choice(neighbours)]))
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["C", "S"]


def _findall(store):
    rng = store.rng
    a, b = store.variable(), store.variable()
    values = sorted({store.point[a] + d for d in rng.sample([-2, -1, 0, 1, 2], 3)})
    listed = ", ".join(_text(v) for v in values)
    goals = store.goals[:]
    goals.append(f"findall(T, (member(V, [{listed}]), X{a} = V, sup(X{b}, T)), L)")
    c, d = store.variable(), store.variable()
    goals.append(f"findall(U, (member(W, [{listed}]), X{c} = W, \\+ \\+ X{d} = {_text(store.point[d])}, inf({store.objective()}, U)), M)")
    goals.append(store.binding(store.some(2)))
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["L", "M", "S"]


def _catch(store):
    rng = store.rng
    a = store.variable()
    goals = store.goals[:]
    neighbours = [i for i in (a - 1, a, a + 1) if 0 <= i < store.n]
    bound = store.binding(sorted(rng.sample(neighbours, rng.randint(1, len(neighbours)))))
    # the freeze inside the catch: the store may have bound X(a) already
    goals.append(f"catch((freeze(X{a}, throw(boom)), {bound}, R = done), boom, R = caught)")
    goals.append(f"sup({store.objective()}, S)")
    goals.append(store.binding(store.some(2)))
    return goals, ["R", "S"]


def _negation(store):
    rng = store.rng
    goals = store.goals[:]
    goals.append(f"\\+ ({store.binding(store.some(2), off=0.7)})")
    goals.append(f"\\+ \\+ ({store.binding(store.some(2))}, sup({store.objective()}, _))")
    condition = store.binding(store.some(2), off=0.4)
    goals.append(f"( {condition} -> R = then ; R = else )")
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["R", "S"]


def _copy(store):
    rng = store.rng
    chosen = store.some(3)
    originals = ", ".join(f"X{i}" for i in chosen)
    copies = ", ".join(f"C{i}" for i in chosen)
    goals = store.goals[:]
    copy = [f"copy_term(f({originals}), f({copies}))",
            ", ".join(f"C{i} = {_text(store.point[i])}" for i in chosen)]
    goals += [store.binding(store.some(2)), f"sup({store.objective()}, S)"]
    at = rng.randint(len(store.goals) - 1, len(store.goals))
    # Scryer copies the attributes, so its answer is the program's
    # without the copy (the copy must leave the originals as they were)
    return goals[:at] + copy + goals[at:], ["S"], goals


def _nonlinear(store):
    rng = store.rng
    p = store.point
    goals = store.goals[:]
    a, b, c, d = (store.variable() for _ in range(4))
    goals.append(f"{{X{a} * X{b} = {_text(p[a] * p[b])}}}")
    at = abs(p[c] - p[d]) + min(p[a], p[c])
    goals.append(f"{{abs(X{c} - X{d}) + min(X{a}, X{c}) =< {_text(at + rng.randint(0, 2))}}}")
    goals.append(f"{{max(X{b}, X{d}) >= {_text(max(p[b], p[d]) - rng.randint(0, 1))}}}")
    goals.append(store.binding(store.some(3), off=0.05))
    goals.append(f"sup({store.objective()}, S)")
    return goals, ["S"]


_BUILDERS = {"freeze": _freeze, "dif": _dif, "fd": _fd, "findall": _findall,
             "catch": _catch, "negation": _negation, "copy": _copy,
             "nonlinear": _nonlinear}


def workload(template, size, seed, surface):
    rng = random.Random(f"engine:{template}:{size}:{seed}")
    store = _Store(rng, size)
    goals, extra, *oracle = _BUILDERS[template](store)
    shown = [f"X{i}" for i in range(size)] + extra

    def program(goals):
        return (_HEAD + f"q({', '.join(shown)}) :-\n    "
                + ",\n    ".join(goals) + ".\n")
    result = {"id": f"engine-{template}-{size}-{seed}-{surface.lstrip('.')}",
              "driver": "engine", "surface": surface,
              "program": program(goals), "shown": shown}
    if oracle:
        result["oracle_program"] = program(oracle[0])
    return result


_DEFAULT_PLAN = [(template, (4,), 1) for template in TEMPLATES]
_FULL_PLAN = [(template, (3, 5, 8, 12), 3) for template in TEMPLATES]


def corpus(full=False):
    """The engine workloads: every template on both surfaces (.pl only
    where the program needs if-then-else)."""
    seen, result = set(), []
    for plan in (_DEFAULT_PLAN, _FULL_PLAN) if full else (_DEFAULT_PLAN,):
        for template, sizes, seeds in plan:
            for size in sizes:
                for seed in range(seeds):
                    for surface in (".pl", ".clausal"):
                        if surface == ".clausal" and template in _PL_ONLY:
                            continue
                        key = (template, size, seed, surface)
                        if key not in seen:
                            seen.add(key)
                            result.append(workload(template, size, seed, surface))
    return result


# ------------------------------------------------------------------ running

_LOADS = itertools.count()


def load(workload, directory):
    """The workload's program, written to *directory* and loaded by the
    import hook under a fresh module name (the name never reaches the
    observation)."""
    from clausal.import_hook import _load_module
    path = pathlib.Path(directory) / f"clpq_engine_{next(_LOADS)}{workload['surface']}"
    path.write_text(workload["program"], encoding="utf-8")
    return _load_module(path.stem, path)


def answers(workload, found, variables=None):
    """Run ``q/k`` and call ``found(variables, trail)`` at each answer;
    the query cache is cleared around every answer (it keys by argument
    types, not values)."""
    from clausal.logic.solve import _query_cache, call
    if variables is None:
        variables = [Var() for _ in workload["shown"]]
    with tempfile.TemporaryDirectory(prefix="clpq_engine_") as directory:
        module = load(workload, directory)
        _query_cache.clear()
        try:
            for trail in call("q", *variables, module=module):
                found(variables, trail)
                _query_cache.clear()
        finally:
            _query_cache.clear()
    return variables


def shown_residual(names, variables, trail, name_of):
    """The residual on the unbound shown variables, as the Scryer oracle
    helper prints it: ``R=N`` for a variable that is the same as an
    earlier shown one, then residual_strings over one representative of
    each."""
    table, free, aliases = {}, [], []
    for name, variable in zip(names, variables):
        variable = deref(variable)
        if not is_var(variable):
            continue
        if variable._id in table:
            aliases.append(f"{table[variable._id]}={name}")
            continue
        table[variable._id] = name
        free.append(variable)
    return aliases + residual_strings(free, trail, name_of(table))


def scryer_text(value):
    """A binding as Scryer's write/1 prints it, for one that is no
    number: atoms bare, lists and compounds without blanks, rationals
    ``N rdiv D``."""
    value = deref(value)
    if is_var(value):
        return "_"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        return f"{value.numerator} rdiv {value.denominator}"
    if isinstance(value, tuple) and len(value) == 2 and all(
            type(x) is int for x in value):
        return scryer_text(Fraction(*value))
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ",".join(scryer_text(x) for x in value) + "]"
    if isinstance(value, tuple):
        return f"{value[0]}(" + ",".join(scryer_text(x) for x in value[1:]) + ")"
    return repr(value)


def scryer_comparable(workload):
    """The port's answers as tests.clpq_oracle Answers (what
    oracle_answers gives for Scryer): numbers as Fractions, other values
    as Scryer's write/1 text, the residual as its helper names it."""
    from tests.clpq_oracle import Answer
    names = workload["shown"]
    result = []

    def name_of(table):
        internal = [0]

        def name(variable):
            if variable._id not in table:
                internal[0] += 1
                table[variable._id] = f"_I{internal[0]}"
            return table[variable._id]
        return name

    def found(variables, trail):
        bindings = {}
        for name, variable in zip(names, variables):
            value = walk(variable)
            if is_var(deref(value)):
                continue
            if isinstance(value, (int, Fraction)) and type(value) is not bool:
                bindings[name] = Fraction(value)
            else:
                bindings[name] = scryer_text(value)
        result.append(Answer(bindings, shown_residual(
            names, variables, trail, name_of)))

    answers(workload, found)
    return result


def observe(workload, event_hook):
    """(observation, namer) of an engine workload: per answer, each shown
    variable's value (canonical, as _observe.canon gives it) and the
    residual on the unbound ones, variables named by the namer the
    trace uses (the shown variables by their names, others _Tk by first
    appearance).  *event_hook(namer)* gives the TRACE hook to install."""
    from clausal.logic.exceptions import LogicException
    from tests.clpq_port.differential._observe import Namer, canon
    names = workload["shown"]
    variables = [Var() for _ in names]
    namer = Namer([])
    namer.names = {v._id: name for v, name in zip(variables, names)}
    results = []

    def found(variables, trail):
        values = [canon(walk(v), namer) for v in variables]
        results.append({"bindings": values, "residual": shown_residual(
            names, variables, trail, lambda table: namer)})

    hook = event_hook(namer)
    try:
        answers(workload, found, variables)
    except LogicException as error:
        return {"answers": results,
                "raised": ["error", canon(error.term, namer)]}, hook
    return {"answers": results}, hook


__all__ = ["TEMPLATES", "answers", "corpus", "load", "observe",
           "scryer_comparable", "shown_residual", "workload"]
