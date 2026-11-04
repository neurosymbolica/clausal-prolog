"""Run a workload on the port and record exactly what it did.

:func:`observe` runs one workload (``_workloads.py``) on the Holzbaur port
through the legacy-compatible API (``clausal.logic.clpq.holzbaur``, what
``CLAUSAL_CLPQ=holzbaur`` exports), on a bare trail, and returns

* the OBSERVATION: per step, its outcome (``true``, ``false``, an error
  term) and what it produced (an optimum, a vertex, a dump as the strings
  dump/3 prints, in order), then each program variable's final value
  (a typed exact number, or the canonical name of the variable it is);
* the TRACE: every decision the algorithm reported through the port's
  ``TRACE`` hooks (bounded_simplex.py, fourier_motzkin.py,
  branch_and_bound.py): pivots with the leaving and entering variable, the
  pivot coefficient and the component, bound swaps, which variable an
  equation is solved for and in which preference category, which
  variable Fourier-Motzkin eliminates, each branch and incumbent of
  bb_inf.

Variables are named canonically, never by id(): program variable i is
``Xi``; any other variable is ``_Tk``, numbered by its first appearance in
the observation stream (trace events and step results in the order they
happen).  So two runs that make the same decisions name every variable
the same, whatever ids the engine handed out.

A step that fails or raises is undone to a mark taken before it (as
``( Step -> true ; true )`` would leave the store), so the rest of the
workload still runs; ``["mark"]``/``["undo"]`` steps nest marks explicitly.
"""
import hashlib
import json
from decimal import Decimal
from fractions import Fraction

from clausal.logic.clpq import bounded_simplex, branch_and_bound, fourier_motzkin
from clausal.logic.clpq import holzbaur
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.terms import Add, Div, Mult, Sub

from tests.clpq_port.differential._workloads import value_of

TRACED_MODULES = (bounded_simplex, branch_and_bound, fourier_motzkin)

_POST = {"=<": holzbaur.q_le, "<": holzbaur.q_lt, ">=": holzbaur.q_ge,
         ">": holzbaur.q_gt, "=:=": holzbaur.q_eq, "=\\=": holzbaur.q_ne}


class Namer:
    """Canonical variable names: Xi for program variable i, then _T1,
    _T2, ... in order of first appearance."""

    def __init__(self, variables):
        self.names = {variable._id: f"X{i}" for i, variable in enumerate(variables)}
        self.internal = 0

    def __call__(self, variable):
        name = self.names.get(variable._id)
        if name is None:
            self.internal += 1
            name = self.names[variable._id] = f"_T{self.internal}"
        return name


def canon(value, namer):
    """*value* as JSON-able data with every variable named by *namer*.
    Numbers keep their kind: ``3`` (int), ``"3/2"`` (Fraction or the
    port's (n, d) rational), ``"f0.5"``, ``"d2.50"``."""
    value = deref(value)
    if is_var(value):
        return namer(value)
    kind = type(value)
    if kind is bool or value is None:
        return value
    if kind is int:
        return value
    if kind is Fraction:
        return f"{value.numerator}/{value.denominator}"
    if kind is float:
        return f"f{value!r}"
    if kind is Decimal:
        return f"d{value}"
    if kind is str:
        return value
    if kind.__name__.endswith("Var"):           # never a silent class name
        raise TypeError(f"an unnamed variable reached canon: {value!r}")
    if kind is tuple:
        if len(value) == 2 and type(value[0]) is int and type(value[1]) is int:
            return f"{value[0]}/{value[1]}"          # the port's rational
        return ["()"] + [canon(element, namer) for element in value]
    if kind is list:
        return [canon(element, namer) for element in value]
    slots = getattr(kind, "__slots__", None)
    fields = (list(slots) if isinstance(slots, (tuple, list)) else
              list(getattr(value, "__dict__", {}) or ()))
    if fields:
        return [kind.__name__] + [canon(getattr(value, f, None), namer)
                                  for f in fields]
    return kind.__name__


def expression(terms, variables):
    """``sum(c*Xi)`` as the API's operator nodes; 0 for no terms."""
    result = None
    for index, coefficient in terms:
        coefficient = value_of(coefficient)
        if coefficient.denominator == 1:
            coefficient = int(coefficient)
        term = Mult(left=coefficient, right=variables[index])
        result = term if result is None else Add(left=result, right=term)
    return 0 if result is None else result


_TREE_NODES = {"+": Add, "-": Sub, "*": Mult, "/": Div}


def tree_expression(tree, variables):
    """A ``nlpost`` expression tree as the API's terms: operator nodes for
    + - * /, compound cells ``("abs", E)``, ``("min", E, F)``, ... for the
    skeletons, as the reader hands them to ``{}/1``."""
    kind = tree[0]
    if kind == "x":
        return variables[tree[1]]
    if kind == "n":
        return _constant(tree[1])
    arguments = [tree_expression(argument, variables) for argument in tree[1:]]
    node = _TREE_NODES.get(kind)
    if node is not None:
        return node(left=arguments[0], right=arguments[1])
    return (kind, *arguments)


def _constant(spelt):
    value = value_of(spelt)
    return int(value) if value.denominator == 1 else value


class _Run:
    def __init__(self, workload):
        self.workload = workload
        self.trail = Trail()
        self.trail.defer = False
        self.variables = [Var() for _ in range(workload["variables"])]
        self.namer = Namer(self.variables)
        self.trace = []
        self.marks = []

    def event(self, *event):
        self.trace.append(canon(list(event), self.namer))

    def term(self, shape, elements):
        """The list or the cell f(...) of a ``unify`` step's elements."""
        items = [self.variables[e[1]] if e[0] == "x" else _constant(e[1])
                 for e in elements]
        return items if shape == "list" else ("f", *items)

    # ---- one step: (ok, data)
    def step(self, step):
        kind = step[0]
        trail, xs = self.trail, self.variables
        if kind == "post":
            _, relation, terms, constant = step
            return _POST[relation](expression(terms, xs), _constant(constant),
                                   trail), None
        if kind == "nonlinear":
            _, relation, i, j, constant = step
            return _POST[relation](Mult(left=xs[i], right=xs[j]),
                                   _constant(constant), trail), None
        if kind == "nlpost":
            _, relation, tree, constant = step
            return _POST[relation](tree_expression(tree, xs),
                                   _constant(constant), trail), None
        if kind == "bind":
            return unify(xs[step[1]], _constant(step[2]), trail), None
        if kind == "alias":
            return unify(xs[step[1]], xs[step[2]], trail), None
        if kind == "unify":
            _, shape, lefts, rights = step
            left, right = self.term(shape, lefts), self.term(shape, rights)
            return unify(left, right, trail), None
        if kind in ("sup", "inf"):
            result = Var()
            optimum = holzbaur.sup if kind == "sup" else holzbaur.inf
            ok = optimum(expression(step[1], xs), result, trail)
            return ok, canon(result, self.namer) if ok else None
        if kind in ("maximize", "minimize"):
            result = Var()
            optimum = holzbaur.maximize if kind == "maximize" else holzbaur.minimize
            ok = optimum(expression(step[1], xs), result, trail)
            return ok, canon(result, self.namer) if ok else None
        if kind == "bb_inf":
            _, ints, terms, epsilon = step
            result = Var()
            integers = [xs[i] for i in ints]
            if epsilon is None:
                ok = holzbaur.bb_inf(integers, expression(terms, xs), result,
                                     trail)
                return ok, canon(result, self.namer) if ok else None
            vertex = Var()
            ok = holzbaur.bb_inf(integers, expression(terms, xs), result,
                                 trail, vertex, _constant(epsilon))
            return ok, ([canon(result, self.namer), canon(vertex, self.namer)]
                        if ok else None)
        if kind == "entailed":
            _, relation, terms, constant = step
            return holzbaur.entailed(relation, expression(terms, xs),
                                     _constant(constant), trail), None
        if kind == "dump":
            targets = [xs[i] for i in step[1]]
            return True, holzbaur.dump_q(
                targets, trail, lambda v: canon(v, self.namer))
        raise ValueError(f"unknown step {step!r}")

    def run(self):
        results = []
        for step in self.workload["steps"]:
            kind = step[0]
            if kind == "mark":
                self.marks.append(self.trail.mark())
                results.append("mark")
                continue
            if kind == "undo":
                if self.marks:
                    self.trail.undo(self.marks.pop())
                    results.append("undo")
                else:
                    results.append("undo-nothing")
                continue
            self.trace.append(["step", len(results)])
            mark = self.trail.mark()
            try:
                ok, data = self.step(step)
            except LogicException as error:
                self.trail.undo(mark)
                results.append(["error", canon(error.term, self.namer)])
                continue
            except (RecursionError, ValueError, TypeError, ZeroDivisionError,
                    AttributeError, KeyError, IndexError) as error:
                self.trail.undo(mark)
                results.append(["raised", type(error).__name__,
                                str(error)[:200]])
                continue
            if not ok:
                self.trail.undo(mark)
                results.append(False)
            elif data is None:
                results.append(True)
            else:
                results.append([True, data])
        final = [canon(variable, self.namer) for variable in self.variables]
        if not self.workload.get("final_dump", True):
            return {"steps": results, "final": final}
        try:
            residual = holzbaur.dump_q(self.variables, self.trail,
                                       lambda v: canon(v, self.namer))
        except LogicException as error:
            residual = ["error", canon(error.term, self.namer)]
        return {"steps": results, "final": final, "residual": residual}


def _install(hook):
    previous = [module.TRACE for module in TRACED_MODULES]
    for module in TRACED_MODULES:
        module.TRACE = hook
    return previous


def _restore(previous):
    for module, hook in zip(TRACED_MODULES, previous):
        module.TRACE = hook


def observe(workload):
    """(observation, trace) of *workload* on the port; see the module
    docstring.  An engine workload (``"driver": "engine"``) runs through
    the engine instead (_engine.py)."""
    if workload.get("driver") == "engine":
        return _observe_engine(workload)
    run = _Run(workload)
    previous = _install(run.event)
    try:
        observation = run.run()
    finally:
        _restore(previous)
    return observation, run.trace


def _observe_engine(workload):
    from tests.clpq_port.differential import _engine
    trace = []
    previous = []

    def event_hook(namer):
        def event(*event):
            trace.append(canon(list(event), namer))
        previous.append(_install(event))
        return event

    try:
        observation, _ = _engine.observe(workload, event_hook)
    finally:
        if previous:
            _restore(previous[0])
    return observation, trace


def canonical_json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def record(workload):
    """The golden record of one workload: the observation, its sha256, the
    trace's sha256 and length, and the number of pivots (pivot/3 and
    pivot/2) in the trace."""
    observation, trace = observe(workload)
    pivots = sum(1 for event in trace
                 if event[0] in ("pivot", "pivot_ignoring_bounds"))
    return {"observation": observation, "observation_sha256": digest(observation),
            "trace_sha256": digest(trace), "trace_events": len(trace),
            "pivots": pivots}, trace
