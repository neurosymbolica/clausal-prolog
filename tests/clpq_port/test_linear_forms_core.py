# tests/clpq_port/test_linear_forms_core.py
"""The C twins of the port's loops (_linear_forms_core, DEVIATIONS.md D24,
Low 8) are exact twins of the pure-Python reference.

Every comparison here runs with CLAUSAL_CLPQ_PYTHON_LOOPS=1, so the
reference functions (linear_forms.python_*, arithmetic.python_*,
components.python_list_elements, the Python row loops of
bounded_simplex and attribute_hooks) are pure Python all the way down: in
the default run the module names are bound to the C twins, so a
comparison there would be partly C against C.  The default run checks
that the C twins are bound and runs this file again in a subprocess with
the variable set.

The inputs: seeded random rows over constrained variables whose order
values are unbound, bound to tied ints, to Fractions, to ints past 2**64;
coefficients small, past 2**31, past 2**200, not normalised; rows with a
variable twice; factors of 1, -1 and others; shared tails and indexed
rows.  Then the cases a review found (2026-11-06), each answered as
Python answers it, never by a crash: an order value whose __eq__ empties
the list being merged or scanned, an order value that raises, a NaN
order value, a term that is a 1-tuple, keys shorter than the row, and a
member list that names a member twice, or a member and an alias of it.
"""
import os
import pathlib
import random
import subprocess
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import arithmetic, components, linear_forms
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq.attributes import put_state, state_of, with_changes
from clausal.logic.clpq.components import closed_list, open_list
from clausal.logic.clpq.variable_ordering import order_key, order_keys
from clausal.logic.variables import AttVar, Trail, Var, unify

core = pytest.importorskip("clausal.logic.clpq._linear_forms_core")

ROOT = pathlib.Path(__file__).resolve().parents[2]
PURE = os.environ.get("CLAUSAL_CLPQ_PYTHON_LOOPS", "") not in ("", "0")

#: The comparisons run only against the pure-Python reference.
pure = pytest.mark.skipif(
    not PURE, reason="runs in test_the_twins_agree_with_the_pure_python_"
                     "reference's subprocess (CLAUSAL_CLPQ_PYTHON_LOOPS=1)")


# ---------------------------------------------------------------- the two runs

@pytest.mark.skipif(PURE, reason="the default run's check")
def test_the_c_twins_are_the_ones_bound():
    assert linear_forms.USE_CORE
    assert arithmetic.add is core.add and arithmetic.multiply is core.multiply
    assert components.list_elements is core.list_elements


@pytest.mark.skipif(PURE, reason="the default run's check")
def test_the_twins_agree_with_the_pure_python_reference():
    env = dict(os.environ, CLAUSAL_CLPQ_PYTHON_LOOPS="1", PYTHONPATH=str(ROOT))
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(pathlib.Path(__file__).relative_to(ROOT))],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    summary = r.stdout.strip().splitlines()[-1]
    assert "failed" not in summary and "error" not in summary, summary


@pure
def test_the_reference_is_pure_python():
    assert not linear_forms.USE_CORE
    assert arithmetic.add is arithmetic.python_add
    assert arithmetic.multiply is arithmetic.python_multiply
    assert components.list_elements is components.python_list_elements


# ---------------------------------------------------------------- inputs

def _variables(count, trail, rng, mode):
    """*count* constrained variables; half of them get an order value
    bound as *mode* says (None: none bound)."""
    variables = [Var() for _ in range(count)]
    for v in variables:
        assert h.q_ge(v, 0, trail)
    if mode is None:
        return variables
    for v in rng.sample(variables, count // 2):
        if mode == 0:
            value = rng.randrange(1, 5)                         # ties
        elif mode == 1:
            value = Fraction(rng.randrange(-9, 9), rng.randrange(1, 4))
        elif mode == 2:
            value = rng.randrange(2 ** 100, 2 ** 100 + 6)
        else:
            value = rng.randrange(-3, 3)
        assert unify(state_of(v).variable_order, value, trail)
    return variables


def _coefficient(rng):
    kind = rng.random()
    if kind < 0.1:
        return (1, 1)
    if kind < 0.15:
        return (-1, 1)
    if kind < 0.2:
        return (0, 1)
    if kind < 0.3:
        return (rng.choice([1, -1]) * rng.randrange(1, 2 ** 200),
                rng.randrange(1, 2 ** 200))
    if kind < 0.4:
        return (rng.randrange(-2 ** 31, 2 ** 31),
                rng.choice([1, 2 ** 31 - 1, 2 ** 31, 2 ** 31 + 1]))
    if kind < 0.45:
        return (rng.randrange(-50, 50), -rng.randrange(1, 50))  # sign not normal
    if kind < 0.5:
        return (6, 4)                                           # gcd not 1
    return arithmetic.make_rational(rng.randrange(-9, 10), rng.randrange(1, 7))


def _row(variables, rng, size, repeat=False):
    chosen = ([rng.choice(variables) for _ in range(size)] if repeat
              else rng.sample(variables, min(size, len(variables))))
    terms = [(v, _coefficient(rng)) for v in chosen]
    terms.sort(key=lambda term: order_key(term[0]))
    return terms


def _same_terms(a, b):
    if a is None or b is None:
        return a is b
    return (len(a) == len(b)
            and all(x[0] is y[0] and x[1] == y[1]
                    and type(x[1][0]) is type(y[1][0]) for x, y in zip(a, b)))


def _same_form(a, b):
    if a is None or b is None:
        return a is b
    return (type(a) is type(b) and a.constant == b.constant
            and a.rest == b.rest and _same_terms(a.terms, b.terms))


def _same(a, b, a_names=None, b_names=None):
    """Structural equality that never calls a variable's == (it would
    unify): variables match by identity, or by name in *a_names* /
    *b_names* (id -> name) when the two sides were built apart."""
    if type(a) in (tuple, list) and type(a) is type(b):
        return len(a) == len(b) and all(
            _same(x, y, a_names, b_names) for x, y in zip(a, b))
    if a is b:
        return True
    if a_names is not None and id(a) in a_names:
        return a_names.get(id(a)) == (b_names or {}).get(id(b))
    if isinstance(a, Var) or isinstance(b, Var):
        return False
    return type(a) is type(b) and a == b


def _same_outcome(got, want, got_names=None, want_names=None):
    if got[0] != want[0]:
        return False
    if got[0] == "raise":
        return got == want
    return _same(got[1], want[1], got_names, want_names)


def _outcome(call):
    """('ok', value) or ('raise', type, message)."""
    try:
        return ("ok", call())
    except Exception as error:      # noqa: BLE001 -- compared, not swallowed
        return ("raise", type(error), str(error))


_MODES = [None, 0, 1, 2, 3]


# ---------------------------------------------------------------- seeded

@pure
@pytest.mark.parametrize("seed", range(60))
def test_the_merge_agrees(seed):
    rng = random.Random(seed)
    trail = Trail()
    variables = _variables(25, trail, rng, _MODES[seed % 5])
    for _ in range(30):
        repeat = rng.random() < 0.2
        a = _row(variables, rng, rng.randrange(0, 12), repeat)
        b = _row(variables, rng, rng.randrange(0, 12), repeat)
        factor = _coefficient(rng)
        keys = order_keys(a) if rng.random() < 0.5 else None
        want = linear_forms.python_add_homogeneous_parts_first_scaled(
            a, factor, b, keys)
        got = core.add_homogeneous_parts_first_scaled(a, factor, b, keys)
        assert _same_terms(got, want)


@pure
@pytest.mark.parametrize("seed", range(60))
def test_the_coefficient_scan_agrees(seed):
    rng = random.Random(seed)
    trail = Trail()
    variables = _variables(25, trail, rng, _MODES[seed % 5])
    for _ in range(30):
        terms = _row(variables, rng, rng.randrange(0, 15), rng.random() < 0.2)
        order = state_of(rng.choice(variables)).variable_order
        assert (core.normal_form_coefficient_homogeneous(terms, order)
                == linear_forms.python_normal_form_coefficient_homogeneous(
                    terms, order))


@pure
@pytest.mark.parametrize("seed", range(60))
def test_the_arithmetic_agrees(seed):
    rng = random.Random(seed)
    for _ in range(50):
        x, y = _coefficient(rng), _coefficient(rng)
        for c_function, python_function in (
                (core.add, arithmetic.python_add),
                (core.multiply, arithmetic.python_multiply)):
            got, want = c_function(x, y), python_function(x, y)
            assert got == want and type(got[0]) is type(want[0])


@pure
@pytest.mark.parametrize("seed", range(60))
def test_the_substitution_agrees(seed):
    rng = random.Random(seed)
    trail = Trail()
    variables = _variables(25, trail, rng, _MODES[seed % 5])
    for _ in range(30):
        repeat = rng.random() < 0.2
        definition = linear_forms.LinearForm(
            _coefficient(rng), _coefficient(rng),
            _row(variables, rng, rng.randrange(0, 8), repeat))
        terms = _row(variables, rng, rng.randrange(1, 20), repeat)
        variable = (rng.choice(terms)[0] if rng.random() < 0.8
                    else rng.choice(variables))
        keys = order_keys(definition.terms) if rng.random() < 0.5 else None
        shape = rng.random()
        constant, rest = _coefficient(rng), _coefficient(rng)
        first = rng.choice(variables)

        def row():
            if shape < 0.3:
                return linear_forms.LinearForm(constant, rest, list(terms))
            if shape < 0.6:
                return linear_forms._SharedTail(
                    constant, rest, [(first, (1, 1))] + terms, 1)
            form = linear_forms.LinearForm(constant, rest, list(terms))
            linear_forms.row_variable_ids(form)
            return form
        python_form, c_form = row(), row()
        want = linear_forms.python_normal_form_substitute(
            variable, definition, python_form, keys)
        got = core.normal_form_substitute(variable, definition, c_form, keys)
        assert _same_form(got, want)
        assert c_form.variable_ids == python_form.variable_ids


@pure
@pytest.mark.parametrize("tail_open", [False, True])
def test_list_elements_agrees(tail_open):
    trail = Trail()
    variables = _variables(12, trail, random.Random(0), None)
    items = open_list(variables)[0] if tail_open else closed_list(variables)
    assert core.list_elements(items) == components.python_list_elements(items)
    assert core.list_elements(None) == components.python_list_elements(None) == []


# ---------------------------------------------------------------- the review's cases

def _ordered(trail, value):
    """A constrained variable whose order value is bound to *value*."""
    v = Var()
    assert h.q_ge(v, 0, trail)
    assert unify(state_of(v).variable_order, value, trail)
    return v


class _Emptying:
    """An order value whose __eq__ empties a list (the one being read)."""
    def __init__(self, victim, less=False):
        self.victim = victim
        self.less = less

    def __eq__(self, other):
        self.victim.clear()
        return False

    def __lt__(self, other):
        return self.less

    __hash__ = object.__hash__


def _emptying_rows(trail, less):
    victim = []
    a = _ordered(trail, _Emptying(victim, less))
    victim[:] = [(_ordered(trail, _Emptying(victim, less)), (i, 1))
                 for i in range(2, 6)]
    return a, victim


@pure
@pytest.mark.parametrize("less", [False, True])
def test_a_merge_whose_order_empties_the_row_answers_as_python(less):
    trail = Trail()
    a, b = _emptying_rows(trail, less)
    want_names = {id(a): "a"}
    want = _outcome(lambda: linear_forms.python_add_homogeneous_parts_first_scaled(
        [(a, (1, 1))], (1, 1), b))
    a, b = _emptying_rows(trail, less)
    got_names = {id(a): "a"}
    got = _outcome(lambda: core.add_homogeneous_parts_first_scaled(
        [(a, (1, 1))], (1, 1), b))
    assert _same_outcome(got, want, got_names, want_names), (got, want)


@pure
@pytest.mark.parametrize("less", [False, True])
def test_a_scan_whose_order_empties_the_row_answers_as_python(less):
    trail = Trail()
    sought = state_of(_ordered(trail, _Emptying([], less))).variable_order
    _, terms = _emptying_rows(trail, less)
    want = _outcome(lambda: linear_forms.python_normal_form_coefficient_homogeneous(
        terms, sought))
    _, terms = _emptying_rows(trail, less)
    got = _outcome(lambda: core.normal_form_coefficient_homogeneous(terms, sought))
    assert _same_outcome(got, want), (got, want)


@pure
def test_an_order_that_raises_raises_from_both():
    class Raising:
        def __eq__(self, other):
            return False

        def __lt__(self, other):
            raise ValueError("boom")

        __hash__ = object.__hash__
    trail = Trail()
    a, b = _ordered(trail, Raising()), _ordered(trail, Raising())
    for merge in (linear_forms.python_add_homogeneous_parts_first_scaled,
                  core.add_homogeneous_parts_first_scaled):
        assert _outcome(lambda: merge([(a, (1, 1))], (1, 1), [(b, (1, 1))])) \
            == ("raise", ValueError, "boom")


@pure
def test_a_nan_order_scans_as_python():
    # NaN is neither == nor < anything: Python reads on past it.
    trail = Trail()
    a, b = _ordered(trail, float("nan")), _ordered(trail, 5)
    terms = [(a, (1, 1)), (b, (2, 1))]
    order = state_of(b).variable_order
    assert core.normal_form_coefficient_homogeneous(terms, order) == (2, 1)
    assert linear_forms.python_normal_form_coefficient_homogeneous(
        terms, order) == (2, 1)
    nan_order = state_of(a).variable_order       # the same NaN: identical
    assert (core.normal_form_coefficient_homogeneous(terms, nan_order)
            == linear_forms.python_normal_form_coefficient_homogeneous(
                terms, nan_order) == (1, 1))
    other = state_of(_ordered(trail, float("nan"))).variable_order
    assert (core.normal_form_coefficient_homogeneous(terms, other)
            == linear_forms.python_normal_form_coefficient_homogeneous(
                terms, other))


@pure
def test_a_nan_order_merges_as_python():
    trail = Trail()
    nan = float("nan")
    a = [(_ordered(trail, nan), (1, 1)), (_ordered(trail, 3), (1, 2))]
    b = [(_ordered(trail, float("nan")), (2, 1)), (_ordered(trail, 3), (1, 3))]
    for keys in (None, order_keys(a)):
        assert _same_terms(
            core.add_homogeneous_parts_first_scaled(a, (1, 1), b, keys),
            linear_forms.python_add_homogeneous_parts_first_scaled(
                a, (1, 1), b, keys))


@pure
def test_a_short_term_answers_as_python():
    trail = Trail()
    x, y = _variables(2, trail, random.Random(0), None)
    definition = linear_forms.LinearForm((1, 1), (0, 1), [(y, (1, 1))])
    cases = [
        lambda f: f["substitute"](x, definition,
                                  linear_forms.LinearForm((0, 1), (0, 1), [(x,)])),
        lambda f: f["substitute"](x, definition,
                                  linear_forms.LinearForm((0, 1), (0, 1), [()])),
        lambda f: f["merge"]([(x,)], (1, 1), [(y, (1, 1))]),
        lambda f: f["merge"]([(x, (1, 1))], (1, 1), [(y,)]),
        lambda f: f["merge"]([(x, (1, 1), 0)], (1, 1), [(y, (1, 1))]),
        lambda f: f["scan"]([(x,)], state_of(x).variable_order),
        lambda f: f["scan"]([5], state_of(x).variable_order),
        lambda f: f["merge"]([(x, (1, 1)), (y, (1, 1))], (1, 1),
                             [(y, (1, 1)), (x, (1, 1))], [order_key(x)]),
    ]
    python = {"substitute": linear_forms.python_normal_form_substitute,
              "merge": linear_forms.python_add_homogeneous_parts_first_scaled,
              "scan": linear_forms.python_normal_form_coefficient_homogeneous}
    c = {"substitute": core.normal_form_substitute,
         "merge": core.add_homogeneous_parts_first_scaled,
         "scan": core.normal_form_coefficient_homogeneous}
    for case in cases:
        want = _outcome(lambda: case(python))
        got = _outcome(lambda: case(c))
        assert _same_outcome(got, want), (got, want)
    # The 1-tuple read for its coefficient is an IndexError from both.
    assert _outcome(lambda: core.normal_form_substitute(
        x, definition, linear_forms.LinearForm((0, 1), (0, 1), [(x,)])))[1] \
        is IndexError


def _store(trail, rng, count=6):
    """Constrained variables, each with a row over the others."""
    variables = _variables(count, trail, rng, None)
    for v in variables:
        others = [w for w in variables if w is not v]
        put_state(v, with_changes(state_of(v), linear_form=linear_forms.LinearForm(
            (rng.randrange(5), 1), (0, 1), _row(others, rng, rng.randrange(1, 4)))),
            trail)
    return variables


def _name(variables, extra=None):
    """A function naming a variable by its position in *variables* (by
    identity: Var's == would unify), or by *extra* (id -> name)."""
    positions = {id(v): i for i, v in enumerate(variables)}
    extra = extra or {}
    return lambda v: extra.get(id(v), positions.get(id(v), "?"))


def _rows(variables, extra=None):
    name = _name(variables, extra)
    return [(state_of(v).linear_form.constant, state_of(v).linear_form.rest,
             [(name(t[0]), t[1]) for t in state_of(v).linear_form.terms])
            for v in variables]


@pure
@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("shape", ["twice", "alias"])
def test_a_member_named_twice_is_written_once_as_python(seed, shape):
    # The C loop writes as it goes, as the Python loop does: the second
    # visit reads the row the first wrote.
    from clausal.logic.clpq import bounded_simplex

    def run(in_c):
        rng = random.Random(seed)
        trail = Trail()
        variables = _store(trail, rng)
        target = rng.choice(variables)
        variable = rng.choice([v for v in variables if v is not target])
        if shape == "twice":
            names = [target, target]
        else:
            alias = Var()
            assert unify(alias, target, trail)
            names = [target, alias]
        members = closed_list(variables + names)
        definition = linear_forms.LinearForm(
            (2, 1), (0, 1), _row([v for v in variables if v is not variable],
                                 rng, 2))
        keys = order_keys(definition.terms)
        writes, bindings = [], []
        if in_c:
            def write(member, state, new_form):
                writes.append(_name(variables)(member))
                put_state(member, with_changes(state, linear_form=new_form), trail)
                bounded_simplex.back_substitute_collect_binding(
                    new_form, member, bindings)
            core.substitute_rows(members, variable, definition, keys, write)
        else:
            original = bounded_simplex.put_state

            def counting(member, state, t):
                writes.append(_name(variables)(member))
                original(member, state, t)
            bounded_simplex.put_state = counting
            try:
                bounded_simplex.back_substitute_collect_bindings(
                    members, variable, definition, bindings, trail)
            finally:
                bounded_simplex.put_state = original
        return writes, len(bindings), _rows(variables)
    assert run(True) == run(False)


@pure
@pytest.mark.parametrize("seed", range(20))
def test_the_stand_in_pass_writes_as_python(seed):
    from clausal.logic.clpq import attribute_hooks

    def run(in_c):
        rng = random.Random(seed)
        trail = Trail()
        variables = _store(trail, rng)
        renamed = rng.sample(variables, 2)
        stand_ins = {id(v): AttVar() for v in renamed}
        members = closed_list(variables + [variables[0], 7])
        writes = []

        def write(member, state, form):
            writes.append(_name(variables)(member))
            put_state(member, with_changes(state, linear_form=form), trail)
        if in_c:
            core.rename_rows(members, stand_ins, write)
        else:
            from clausal.logic.variables import deref, is_var
            for member in components.python_list_elements(members):
                member = deref(member)
                if not is_var(member):
                    continue
                state = state_of(member)
                if state is None or state.linear_form is None:
                    continue
                form = attribute_hooks._rename_in_form(state.linear_form, stand_ins)
                if form is not state.linear_form:
                    write(member, state, form)
        extra = {id(stand_ins[id(v)]): ("stand-in", i)
                 for i, v in enumerate(renamed)}
        return writes, _rows(variables, extra)
    assert run(True) == run(False)
    assert core.list_has_stand_in(
        closed_list([Var(), Var()]), {}) is False
