"""Tests for clausal.modules.py.scipy_integrate — scipy.integrate predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via ResultGet
- Tier 1 direct array results
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import math
import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_integrate import (
    Quad, DoubleQuad, TripleQuad, NQuad, QuadVec,
    SolveInitialValueProblem, OdeIntegrate,
    CumulativeTrapezoid, Trapezoid, Simpson,
    ResultGet,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _drive_result_get(result_dict, field):
    """Use ResultGet to extract a field from a dict result."""
    value = Var()
    dispatch = ResultGet._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, result_dict, field, value, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(value)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is bound to a wrong value."""
    trail = Trail()
    result_bound = object()  # will not unify with any result
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── TestQuad ──────────────────────────────────────────────────────────────

class TestQuad:
    def test_sin_0_to_pi(self):
        # nv
        r = _drive(Quad, math.sin, 0.0, math.pi)
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 2.0) < 1e-8

    def test_result_has_error(self):
        # nv
        r = _drive(Quad, math.sin, 0.0, math.pi)
        assert r is not None
        error = _drive_result_get(r, 'error')
        assert error is not None
        assert float(error) < 1e-10

    def test_with_args(self):
        # integrate lambda x, a: a*x from 0 to 1, a=2 -> result=1.0
        # nv
        r = _drive(Quad, lambda x, a: a * x, 0.0, 1.0, (2.0,))
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 1.0) < 1e-8

    def test_constant_function(self):
        # nv
        r = _drive(Quad, lambda x: 1.0, 0.0, 3.0)
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 3.0) < 1e-8

    def test_result_get_value(self):
        # nv
        r = _drive(Quad, math.sin, 0.0, math.pi)
        value = _drive_result_get(r, 'value')
        assert value is not None
        assert abs(float(value) - 2.0) < 1e-8

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(Quad, math.sin, 0.0, math.pi)


# ── TestDoubleQuad ────────────────────────────────────────────────────────

class TestDoubleQuad:
    def test_unit_square(self):
        # integral of f(x,y)=1 over [0,1]x[0,1] = 1.0
        # nv
        r = _drive(DoubleQuad, lambda y, x: 1.0, 0.0, 1.0, 0.0, 1.0)
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 1.0) < 1e-8

    def test_result_has_error(self):
        # nv
        r = _drive(DoubleQuad, lambda y, x: 1.0, 0.0, 1.0, 0.0, 1.0)
        assert r is not None
        error = _drive_result_get(r, 'error')
        assert error is not None

    def test_xy_product(self):
        # integral of x*y over [0,1]x[0,1] = 0.25
        # nv
        r = _drive(DoubleQuad, lambda y, x: x * y, 0.0, 1.0, 0.0, 1.0)
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 0.25) < 1e-8

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(DoubleQuad, lambda y, x: 1.0, 0.0, 1.0, 0.0, 1.0)


# ── TestTripleQuad ────────────────────────────────────────────────────────

class TestTripleQuad:
    def test_unit_cube(self):
        # integral of f(x,y,z)=1 over unit cube = 1.0
        # nv
        r = _drive(TripleQuad, lambda z, y, x: 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 1.0) < 1e-6

    def test_result_has_error(self):
        # nv
        r = _drive(TripleQuad, lambda z, y, x: 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
        assert r is not None
        error = _drive_result_get(r, 'error')
        assert error is not None


# ── TestNQuad ─────────────────────────────────────────────────────────────

class TestNQuad:
    def test_unit_square(self):
        # 2D integration of f=1 over [[0,1],[0,1]] = 1.0
        # nv
        r = _drive(NQuad, lambda x, y: 1.0, [[0.0, 1.0], [0.0, 1.0]])
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 1.0) < 1e-8

    def test_result_has_error(self):
        # nv
        r = _drive(NQuad, lambda x, y: 1.0, [[0.0, 1.0], [0.0, 1.0]])
        assert r is not None
        error = _drive_result_get(r, 'error')
        assert error is not None

    def test_1d(self):
        # 1D integration of sin(x) over [0, pi] = 2.0
        # nv
        r = _drive(NQuad, math.sin, [[0.0, math.pi]])
        assert r is not None
        value = _drive_result_get(r, 'value')
        assert abs(float(value) - 2.0) < 1e-8

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(NQuad, lambda x, y: 1.0, [[0.0, 1.0], [0.0, 1.0]])


# ── TestQuadVec ───────────────────────────────────────────────────────────

class TestQuadVec:
    def test_sin_0_to_pi(self):
        # nv
        r = _drive(QuadVec, lambda x: np.sin(x), 0.0, math.pi)
        assert r is not None
        y = _drive_result_get(r, 'y')
        assert y is not None
        assert abs(float(y) - 2.0) < 1e-6

    def test_result_has_success(self):
        # nv
        r = _drive(QuadVec, lambda x: np.sin(x), 0.0, math.pi)
        assert r is not None
        success = _drive_result_get(r, 'success')
        assert success is True

    def test_result_has_err(self):
        # nv
        r = _drive(QuadVec, lambda x: np.sin(x), 0.0, math.pi)
        assert r is not None
        err = _drive_result_get(r, 'err')
        assert err is not None

    def test_result_has_neval(self):
        # nv
        r = _drive(QuadVec, lambda x: np.sin(x), 0.0, math.pi)
        assert r is not None
        neval = _drive_result_get(r, 'neval')
        assert neval is not None
        assert int(neval) > 0


# ── TestSolveInitialValueProblem ──────────────────────────────────────────

class TestSolveInitialValueProblem:
    def test_exponential_decay(self):
        # dy/dt = -y, y(0) = 1 → y(1) ≈ e^-1
        # nv
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0])
        assert r is not None
        t = _drive_result_get(r, 't')
        y = _drive_result_get(r, 'y')
        assert t is not None
        assert y is not None
        # y[-1, 0] should be close to exp(-1)
        assert abs(float(y[0, -1]) - math.exp(-1.0)) < 5e-4

    def test_result_success(self):
        # nv
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0])
        assert r is not None
        success = _drive_result_get(r, 'success')
        assert success is True

    def test_with_method_rk45(self):
        # nv
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0],
                   'RK45')
        assert r is not None
        success = _drive_result_get(r, 'success')
        assert success is True

    def test_with_method_rk23(self):
        # nv
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0],
                   'RK23')
        assert r is not None
        y = _drive_result_get(r, 'y')
        assert y is not None
        assert abs(float(y[0, -1]) - math.exp(-1.0)) < 2e-3

    def test_with_t_eval(self):
        # nv
        t_eval = np.linspace(0, 1, 11)
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0],
                   'RK45',
                   t_eval)
        assert r is not None
        t = _drive_result_get(r, 't')
        assert t is not None
        assert len(t) == 11

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(SolveInitialValueProblem,
                                        lambda t, y: [-y[0]],
                                        [0.0, 1.0],
                                        [1.0])

    def test_result_has_nfev(self):
        # nv
        r = _drive(SolveInitialValueProblem,
                   lambda t, y: [-y[0]],
                   [0.0, 1.0],
                   [1.0])
        assert r is not None
        nfev = _drive_result_get(r, 'nfev')
        assert nfev is not None
        assert int(nfev) > 0


# ── TestOdeIntegrate ──────────────────────────────────────────────────────

class TestOdeIntegrate:
    def test_exponential_decay(self):
        # dy/dt = -y, y(0) = 1 → y(t) = exp(-t)
        # nv
        t = np.linspace(0, 1, 11)
        r = _drive(OdeIntegrate, lambda y, t: -y, [1.0], t)
        assert r is not None
        y = _drive_result_get(r, 'y')
        assert y is not None
        # last value should be close to exp(-1)
        assert abs(float(y[-1, 0]) - math.exp(-1.0)) < 1e-4

    def test_result_has_y(self):
        # nv
        t = np.linspace(0, 1, 5)
        r = _drive(OdeIntegrate, lambda y, t: -y, [1.0], t)
        assert r is not None
        assert 'y' in r

    def test_with_args(self):
        # dy/dt = -a*y, a=2, y(0)=1 → y(1) = exp(-2)
        # nv
        t = np.linspace(0, 1, 11)
        r = _drive(OdeIntegrate, lambda y, t, a: -a * y, [1.0], t, (2.0,))
        assert r is not None
        y = _drive_result_get(r, 'y')
        assert y is not None
        assert abs(float(y[-1, 0]) - math.exp(-2.0)) < 1e-4

    def test_wrong_result_fails(self):
        # nv
        t = np.linspace(0, 1, 5)
        assert _fails_with_wrong_result(OdeIntegrate, lambda y, t: -y, [1.0], t)


# ── TestCumulativeTrapezoid ───────────────────────────────────────────────

class TestCumulativeTrapezoid:
    def test_uniform_1_2_3(self):
        # [1, 2, 3] dx=1 → cumulative trapezoids: [1.5, 4.0]
        # nv
        r = _drive(CumulativeTrapezoid, [1.0, 2.0, 3.0])
        assert r is not None
        assert abs(float(r[0]) - 1.5) < 1e-10
        assert abs(float(r[1]) - 4.0) < 1e-10

    def test_with_x(self):
        # same but with explicit x=[0,1,2]
        # nv
        r = _drive(CumulativeTrapezoid, [1.0, 2.0, 3.0], [0.0, 1.0, 2.0])
        assert r is not None
        assert abs(float(r[0]) - 1.5) < 1e-10
        assert abs(float(r[1]) - 4.0) < 1e-10

    def test_constant_function(self):
        # [2, 2, 2] dx=1 → [2.0, 4.0]
        # nv
        r = _drive(CumulativeTrapezoid, [2.0, 2.0, 2.0])
        assert r is not None
        assert abs(float(r[0]) - 2.0) < 1e-10
        assert abs(float(r[1]) - 4.0) < 1e-10

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(CumulativeTrapezoid, [1.0, 2.0, 3.0])


# ── TestTrapezoid ─────────────────────────────────────────────────────────

class TestTrapezoid:
    def test_uniform_1_2_3(self):
        # [1, 2, 3] dx=1 → 4.0
        # nv
        r = _drive(Trapezoid, [1.0, 2.0, 3.0])
        assert r is not None
        assert abs(float(r) - 4.0) < 1e-10

    def test_with_x(self):
        # nv
        r = _drive(Trapezoid, [1.0, 2.0, 3.0], [0.0, 1.0, 2.0])
        assert r is not None
        assert abs(float(r) - 4.0) < 1e-10

    def test_constant(self):
        # [1, 1, 1] dx=1 → 2.0
        # nv
        r = _drive(Trapezoid, [1.0, 1.0, 1.0])
        assert r is not None
        assert abs(float(r) - 2.0) < 1e-10

    def test_single_interval(self):
        # [0, 1] dx=1 → 0.5
        # nv
        r = _drive(Trapezoid, [0.0, 1.0])
        assert r is not None
        assert abs(float(r) - 0.5) < 1e-10

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(Trapezoid, [1.0, 2.0, 3.0])


# ── TestSimpson ───────────────────────────────────────────────────────────

class TestSimpson:
    def test_three_points_1_4_1(self):
        # [1, 4, 1] with dx=1, h=1 → h/3*(y0+4*y1+y2) = 1/3*(1+16+1) = 6.0
        # nv
        r = _drive(Simpson, [1.0, 4.0, 1.0])
        assert r is not None
        assert abs(float(r) - 6.0) < 1e-10

    def test_with_x(self):
        # nv
        r = _drive(Simpson, [1.0, 4.0, 1.0], [0.0, 1.0, 2.0])
        assert r is not None
        assert abs(float(r) - 6.0) < 1e-10

    def test_constant(self):
        # [1, 1, 1] → 2.0
        # nv
        r = _drive(Simpson, [1.0, 1.0, 1.0])
        assert r is not None
        assert abs(float(r) - 2.0) < 1e-10

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(Simpson, [1.0, 4.0, 1.0])


# ── TestResultGet ─────────────────────────────────────────────────────────

class TestResultGet:
    def test_get_existing_field(self):
        # nv
        d = {'value': 2.0, 'error': 1e-10}
        v = _drive_result_get(d, 'value')
        assert v == 2.0

    def test_get_error_field(self):
        # nv
        d = {'value': 2.0, 'error': 1e-10}
        e = _drive_result_get(d, 'error')
        assert abs(float(e) - 1e-10) < 1e-20

    def test_missing_field_fails(self):
        # nv
        d = {'value': 2.0}
        v = _drive_result_get(d, 'error')
        assert v is None

    def test_wrong_result_type_fails(self):
        # nv
        v = _drive_result_get("not a dict", 'value')
        assert v is None

    def test_non_string_field_fails(self):
        # nv
        value = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        field_var = Var()  # unbound var as field — should fail
        gen = dispatch(None, None, {'value': 1}, field_var, value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bind_scalar_value(self):
        # nv
        d = {'success': True}
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, d, 'success', True, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1


# ── Fixture integration ───────────────────────────────────────────────────

import os
from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestClausalFixture:
    """Run Test predicates from tests/fixtures/scipy_integrate_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_integrate_tests")

    @pytest.mark.parametrize("name", [
        "quad sin 0 to pi",
        "solve ivp exponential decay",
        "trapezoid uniform",
        "simpson parabola",
        "cumulative trapezoid",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


class TestClausalUnitsFixture:
    """Run Test predicates from tests/fixtures/scipy_integrate_units_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_integrate_units_tests")

    @pytest.mark.parametrize("name", [
        "trapezoid plain arrays returns plain",
        "quad no units fast path",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ── Quantity / dimensional analysis ──────────────────────────────────────

from clausal.terms import Quantity, UnitsMismatch
from clausal.modules.py.units import Metre, Second, Newton, Kilogram


class TestTrapezoidUnits:
    """Phase 4 — Trapezoid/Simpson/CumulativeTrapezoid with Quantity inputs."""

    def test_trapezoid_velocity_times_time(self):
        """velocity (m/s) over time (s) → displacement (m)."""
        # nv
        y = Quantity(np.array([0.0, 10.0, 20.0]), {Metre: 1, Second: -1})
        x = Quantity(np.array([0.0, 1.0, 2.0]), {Second: 1})
        result = _drive(Trapezoid, y, x)
        assert result is not None
        assert isinstance(result, Quantity), f"Expected Quantity, got {type(result)}"
        assert result.value == pytest.approx(20.0)
        assert dict(result.dims) == {Metre: 1}

    def test_trapezoid_plain_fast_path(self):
        """Plain arrays → plain result, unchanged."""
        # nv
        result = _drive(Trapezoid, np.array([1.0, 2.0, 3.0]))
        assert result is not None
        assert not isinstance(result, Quantity)
        assert float(result) == pytest.approx(4.0)

    def test_simpson_with_units(self):
        """Simpson with Quantity y and x."""
        # nv
        y = Quantity(np.array([1.0, 4.0, 1.0]), {Newton: 1})
        x = Quantity(np.array([0.0, 1.0, 2.0]), {Metre: 1})
        result = _drive(Simpson, y, x)
        assert result is not None
        assert isinstance(result, Quantity)
        assert dict(result.dims) == {Newton: 1, Metre: 1}

    def test_cumulative_trapezoid_with_units(self):
        """CumulativeTrapezoid with Quantity y and x."""
        # nv
        y = Quantity(np.array([0.0, 10.0, 20.0]), {Metre: 1, Second: -1})
        x = Quantity(np.array([0.0, 1.0, 2.0]), {Second: 1})
        result = _drive(CumulativeTrapezoid, y, x)
        assert result is not None
        assert isinstance(result, Quantity)
        assert dict(result.dims) == {Metre: 1}
        np.testing.assert_allclose(result.value, [5.0, 20.0])

    def test_trapezoid_y_only_with_units(self):
        """Trapezoid(y) with Quantity y and no x → dims = y_dims."""
        # nv
        y = Quantity(np.array([1.0, 2.0, 3.0]), {Newton: 1})
        result = _drive(Trapezoid, y)
        assert result is not None
        assert isinstance(result, Quantity)
        assert dict(result.dims) == {Newton: 1}


class TestQuadUnits:
    """Phase 4 — Quad with Quantity inputs."""

    def test_quad_units_propagated(self):
        """f: Metre→Newton, bounds in Metre → integral in Newton·Metre."""
        # nv
        k = Quantity(9.8, {Newton: 1, Metre: -1})
        f = lambda x: x * k  # returns Newton
        result = _drive(Quad, f, Quantity(0.0, {Metre: 1}), Quantity(1.0, {Metre: 1}))
        assert result is not None
        v = result['value']
        assert isinstance(v, Quantity), f"Expected Quantity, got {type(v)}"
        # integral of (9.8 N/m * x) from 0 to 1 m = 4.9 N·m
        # but f returns N, so f_dims = {N:1}, x_dims = {M:1}, out = N·M... wait
        # Actually f(x) = x * k. x is Quantity(val, {M:1}), k is Quantity(9.8, {N:1,M:-1})
        # f(x) = Quantity(val*9.8, {N:1}). So f_dims = {N:1}.
        # out_dims = f_dims + x_dims = {N:1, M:1}
        assert dict(v.dims) == {Newton: 1, Metre: 1}

    def test_quad_plain_function(self):
        """f returns plain float → result value is plain."""
        # nv
        f = lambda x: x.value if isinstance(x, Quantity) else x
        result = _drive(Quad, f, Quantity(0.0, {Metre: 1}), Quantity(1.0, {Metre: 1}))
        assert result is not None
        v = result['value']
        assert not isinstance(v, Quantity)
        assert float(v) == pytest.approx(0.5, abs=1e-6)

    def test_quad_no_units_fast_path(self):
        """Plain bounds → plain result, unchanged."""
        # nv
        result = _drive(Quad, lambda x: x, 0.0, 1.0)
        assert result is not None
        v = result['value']
        assert not isinstance(v, Quantity)
        assert float(v) == pytest.approx(0.5, abs=1e-9)

    def test_quad_error_has_same_units(self):
        """Error estimate has same dims as value."""
        # nv
        k = Quantity(1.0, {Newton: 1, Metre: -1})
        f = lambda x: x * k
        result = _drive(Quad, f, Quantity(0.0, {Metre: 1}), Quantity(1.0, {Metre: 1}))
        assert result is not None
        err = result['error']
        assert isinstance(err, Quantity)
        assert dict(err.dims) == {Newton: 1, Metre: 1}
