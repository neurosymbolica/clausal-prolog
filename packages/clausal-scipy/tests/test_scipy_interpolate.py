"""Tests for clausal.modules.py.scipy_interpolate — scipy.interpolate predicates.

Tests are organised per predicate family and cover:
- correct handle returned (integer) from Make* predicates
- Eval* evaluates correctly at known points
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- free releases the handle
- spline utilities: spline_integral, spline_derivative, spline_roots
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")
pytest.importorskip("numpy", reason="numpy not installed")

import numpy as np
import scipy.interpolate as scipy_interp

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_interpolate import (
    make_spline,
    make_cubic,
    make_pchip,
    make_akima,
    make_linear1d,
    make_regular_grid,
    make_radial_basis,
    eval_spline,
    eval_regular_grid,
    eval_radial_basis,
    spline_integral,
    spline_derivative,
    spline_roots,
    free,
    _INTERP_REGISTRY,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate fails when RESULT is bound to a wrong value."""
    trail = Trail()
    result_bound = object()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


def _free(handle):
    """Release a handle via free."""
    dispatch = free._get_dispatch()
    trail = Trail()
    list(dispatch(None, None, None, None, handle, trail))


# Sample data
_XS = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
_YS = np.array([0.0, 1.0, 4.0, 9.0, 16.0])  # y = x^2


# ── TestMakeSpline ───────────────────────────────────────────────────

class TestMakeSpline:
    def test_returns_int_handle(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        assert isinstance(h, int)
        _free(h)

    def test_handle_in_registry(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        assert h in _INTERP_REGISTRY
        _free(h)

    def test_with_k(self):
        # nv
        h = _drive(make_spline, _XS, _YS, 3)
        assert isinstance(h, int)
        _free(h)

    def test_with_k_and_bc_type(self):
        # nv
        h = _drive(make_spline, _XS, _YS, 3, None)
        assert isinstance(h, int)
        _free(h)

    def test_wrong_result_fails(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        assert _fails_with_wrong_result(make_spline, _XS, _YS)
        _free(h)

    def test_unique_handles(self):
        # nv
        h1 = _drive(make_spline, _XS, _YS)
        h2 = _drive(make_spline, _XS, _YS)
        assert h1 != h2
        _free(h1)
        _free(h2)


# ── TestMakeCubic ────────────────────────────────────────────────────

class TestMakeCubic:
    def test_returns_int_handle(self):
        # nv
        h = _drive(make_cubic, _XS, _YS)
        assert isinstance(h, int)
        _free(h)

    def test_with_bc_type(self):
        # nv
        h = _drive(make_cubic, _XS, _YS, 'not-a-knot')
        assert isinstance(h, int)
        _free(h)

    def test_handle_in_registry(self):
        # nv
        h = _drive(make_cubic, _XS, _YS)
        assert h in _INTERP_REGISTRY
        _free(h)


# ── TestMakePCHIP ────────────────────────────────────────────────────

class TestMakePCHIP:
    def test_returns_int_handle(self):
        # nv
        h = _drive(make_pchip, _XS, _YS)
        assert isinstance(h, int)
        _free(h)

    def test_with_extrapolate(self):
        # nv
        h = _drive(make_pchip, _XS, _YS, True)
        assert isinstance(h, int)
        _free(h)


# ── TestMakeAkima ────────────────────────────────────────────────────

class TestMakeAkima:
    def test_returns_int_handle(self):
        # nv
        h = _drive(make_akima, _XS, _YS)
        assert isinstance(h, int)
        _free(h)

    def test_handle_in_registry(self):
        # nv
        h = _drive(make_akima, _XS, _YS)
        assert h in _INTERP_REGISTRY
        _free(h)


# ── TestMakeLinear1D ─────────────────────────────────────────────────

class TestMakeLinear1D:
    def test_returns_int_handle(self):
        # nv
        h = _drive(make_linear1d, _XS, _YS)
        if h is None:
            pytest.skip("interp1d not available in this scipy version")
        assert isinstance(h, int)
        _free(h)

    def test_with_kind(self):
        # nv
        h = _drive(make_linear1d, _XS, _YS, 'linear')
        if h is None:
            pytest.skip("interp1d not available in this scipy version")
        assert isinstance(h, int)
        _free(h)

    def test_nearest_kind(self):
        # nv
        h = _drive(make_linear1d, _XS, _YS, 'nearest')
        if h is None:
            pytest.skip("interp1d not available in this scipy version")
        assert isinstance(h, int)
        _free(h)


# ── TestMakeRegularGrid ──────────────────────────────────────────────

class TestMakeRegularGrid:
    _POINTS = (np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0, 2.0]))
    _VALUES = np.array([[0.0, 1.0, 2.0], [1.0, 2.0, 3.0], [2.0, 3.0, 4.0]])

    def test_returns_int_handle(self):
        # nv
        h = _drive(make_regular_grid, self._POINTS, self._VALUES)
        assert isinstance(h, int)
        _free(h)

    def test_with_method(self):
        # nv
        h = _drive(make_regular_grid, self._POINTS, self._VALUES, 'linear')
        assert isinstance(h, int)
        _free(h)


# ── TestMakeRadialBasis ──────────────────────────────────────────────────────

class TestMakeRadialBasis:
    _X = np.array([[0.0], [1.0], [2.0], [3.0]])
    _Y = np.array([0.0, 1.0, 4.0, 9.0])

    def test_returns_int_handle(self):
        # nv
        h = _drive(make_radial_basis, self._X, self._Y)
        assert isinstance(h, int)
        _free(h)

    def test_with_kernel(self):
        # nv
        h = _drive(make_radial_basis, self._X, self._Y, 'linear')
        assert isinstance(h, int)
        _free(h)

    def test_with_kernel_and_smooth(self):
        # nv
        h = _drive(make_radial_basis, self._X, self._Y, 'linear', 0.0)
        assert isinstance(h, int)
        _free(h)


# ── TestEvalSpline ───────────────────────────────────────────────────

class TestEvalSpline:
    def test_eval_at_knots(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        result = _drive(eval_spline, h, _XS)
        assert result is not None
        np.testing.assert_allclose(result, _YS, atol=1e-10)
        _free(h)

    def test_eval_at_midpoint(self):
        # nv
        h = _drive(make_cubic, _XS, _YS)
        # At x=2, y should be close to 4 (x^2)
        result = _drive(eval_spline, h, np.array([2.0]))
        assert result is not None
        assert abs(float(result[0]) - 4.0) < 1e-8
        _free(h)

    def test_eval_with_nu(self):
        # derivative of x^2 at x=2 should be ~4
        # nv
        h = _drive(make_cubic, _XS, _YS)
        result = _drive(eval_spline, h, np.array([2.0]), 1)
        assert result is not None
        assert abs(float(result[0]) - 4.0) < 0.1
        _free(h)

    def test_pchip_eval_at_knots(self):
        # nv
        h = _drive(make_pchip, _XS, _YS)
        result = _drive(eval_spline, h, _XS)
        assert result is not None
        np.testing.assert_allclose(result, _YS, atol=1e-10)
        _free(h)

    def test_akima_eval_at_knots(self):
        # nv
        h = _drive(make_akima, _XS, _YS)
        result = _drive(eval_spline, h, _XS)
        assert result is not None
        np.testing.assert_allclose(result, _YS, atol=1e-8)
        _free(h)

    def test_wrong_result_fails(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        assert _fails_with_wrong_result(eval_spline, h, _XS)
        _free(h)

    def test_invalid_handle_fails(self):
        # nv
        result = _drive(eval_spline, 9999999, _XS)
        assert result is None


# ── TestEvalRegularGrid ──────────────────────────────────────────────

class TestEvalRegularGrid:
    _POINTS = (np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0, 2.0]))
    _VALUES = np.array([[0.0, 1.0, 2.0], [1.0, 2.0, 3.0], [2.0, 3.0, 4.0]])

    def test_eval_at_grid_points(self):
        # nv
        h = _drive(make_regular_grid, self._POINTS, self._VALUES)
        xi = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        result = _drive(eval_regular_grid, h, xi)
        assert result is not None
        np.testing.assert_allclose(result, [0.0, 2.0, 4.0], atol=1e-10)
        _free(h)

    def test_eval_with_method(self):
        # nv
        h = _drive(make_regular_grid, self._POINTS, self._VALUES)
        xi = np.array([[1.0, 1.0]])
        result = _drive(eval_regular_grid, h, xi, 'linear')
        assert result is not None
        assert abs(float(result[0]) - 2.0) < 1e-10
        _free(h)


# ── TestEvalRadialBasis ──────────────────────────────────────────────────────

class TestEvalRadialBasis:
    _X = np.array([[0.0], [1.0], [2.0], [3.0]])
    _Y = np.array([0.0, 1.0, 4.0, 9.0])

    def test_eval_at_known_points(self):
        # nv
        h = _drive(make_radial_basis, self._X, self._Y)
        result = _drive(eval_radial_basis, h, self._X)
        assert result is not None
        np.testing.assert_allclose(result.ravel(), self._Y, atol=1e-6)
        _free(h)

    def test_invalid_handle_fails(self):
        # nv
        result = _drive(eval_radial_basis, 9999999, self._X)
        assert result is None


# ── TestSplineIntegral ───────────────────────────────────────────────

class TestSplineIntegral:
    def test_integral_of_x_squared(self):
        # Integral of x^2 from 0 to 3 = 9.0
        # nv
        xs = np.linspace(0.0, 4.0, 20)
        ys = xs ** 2
        h = _drive(make_cubic, xs, ys)
        result = _drive(spline_integral, h, 0.0, 3.0)
        assert result is not None
        assert abs(float(result) - 9.0) < 1e-6
        _free(h)

    def test_integral_of_constant(self):
        # Integral of 1 from 0 to 5 = 5.0
        # nv
        xs = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        ys = np.ones(6)
        h = _drive(make_cubic, xs, ys)
        result = _drive(spline_integral, h, 0.0, 5.0)
        assert result is not None
        assert abs(float(result) - 5.0) < 1e-10
        _free(h)

    def test_invalid_handle_fails(self):
        # nv
        result = _drive(spline_integral, 9999999, 0.0, 1.0)
        assert result is None


# ── TestSplineDerivative ─────────────────────────────────────────────

class TestSplineDerivative:
    def test_returns_new_handle(self):
        # nv
        h = _drive(make_cubic, _XS, _YS)
        h_deriv = _drive(spline_derivative, h)
        assert isinstance(h_deriv, int)
        assert h_deriv != h
        _free(h)
        _free(h_deriv)

    def test_derivative_with_order(self):
        # nv
        h = _drive(make_cubic, _XS, _YS)
        h_deriv = _drive(spline_derivative, h, 1)
        assert isinstance(h_deriv, int)
        _free(h)
        _free(h_deriv)

    def test_derivative_evaluates(self):
        # d/dx x^2 = 2x; at x=2, value should be ~4
        # nv
        xs = np.linspace(0.0, 4.0, 20)
        ys = xs ** 2
        h = _drive(make_cubic, xs, ys)
        h_deriv = _drive(spline_derivative, h)
        result = _drive(eval_spline, h_deriv, np.array([2.0]))
        assert result is not None
        assert abs(float(result[0]) - 4.0) < 1e-6
        _free(h)
        _free(h_deriv)

    def test_invalid_handle_fails(self):
        # nv
        result = _drive(spline_derivative, 9999999)
        assert result is None


# ── TestSplineRoots ──────────────────────────────────────────────────

class TestSplineRoots:
    def test_linear_root_at_zero(self):
        # y = x - 2; root at x=2
        # nv
        xs = np.array([0.0, 2.0, 4.0])
        ys = np.array([-2.0, 0.0, 2.0])
        h = _drive(make_cubic, xs, ys)
        roots = _drive(spline_roots, h)
        assert roots is not None
        assert isinstance(roots, list)
        assert len(roots) == 1
        assert abs(float(roots[0]) - 2.0) < 1e-10
        _free(h)

    def test_multiple_roots(self):
        # y = (x-1)*(x-3); roots at 1 and 3
        # nv
        xs = np.linspace(0.0, 4.0, 20)
        ys = (xs - 1.0) * (xs - 3.0)
        h = _drive(make_cubic, xs, ys)
        roots = _drive(spline_roots, h)
        assert roots is not None
        assert isinstance(roots, list)
        assert len(roots) == 2
        roots_sorted = sorted(roots)
        assert abs(float(roots_sorted[0]) - 1.0) < 1e-6
        assert abs(float(roots_sorted[1]) - 3.0) < 1e-6
        _free(h)

    def test_invalid_handle_fails(self):
        # nv
        result = _drive(spline_roots, 9999999)
        assert result is None


# ── TestFree ─────────────────────────────────────────────────────────

class TestFree:
    def test_removes_handle_from_registry(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        assert h in _INTERP_REGISTRY
        _free(h)
        assert h not in _INTERP_REGISTRY

    def test_free_nonexistent_succeeds(self):
        # free on unknown handle should still succeed (always yields None)
        # nv
        dispatch = free._get_dispatch()
        trail = Trail()
        solutions = [(p, s) for p, s in dispatch(None, None, None, None, 9999999, trail) if s is None]
        assert len(solutions) == 1

    def test_free_prevents_eval(self):
        # nv
        h = _drive(make_spline, _XS, _YS)
        _free(h)
        result = _drive(eval_spline, h, _XS)
        assert result is None


# ── TestInterpModuleImport ─────────────────────────────────────────────────

class TestInterpModuleImport:
    def test_alias_module_exports_all(self):
        # nv
        from clausal.modules.py import scipy_interpolate as m
        for name in [
            'make_spline', 'make_cubic', 'make_pchip',
            'make_akima', 'make_linear1d',
            'make_regular_grid', 'make_radial_basis',
            'eval_spline', 'eval_regular_grid', 'eval_radial_basis',
            'spline_integral', 'spline_derivative', 'spline_roots',
            'free',
        ]:
            assert hasattr(m, name), f"Missing export: {name}"


# ── Fixture integration ────────────────────────────────────────────────────

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


class TestScipyInterpolateFixture:
    """Run Test predicates from tests/fixtures/scipy_interpolate_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_interpolate_tests")

    @pytest.mark.parametrize("name", [
        "cubic spline eval at knots",
        "make interp spline eval endpoints",
        "make interp spline with k",
        "pchip eval at endpoints",
        "akima eval at interior point",
        "spline integral of x squared",
        "spline integral of constant",
        "spline derivative of x squared",
        "spline derivative order 1",
        "spline roots linear",
        "free handle succeeds",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"


# ── Quantity / dimensional analysis ──────────────────────────────────────

from clausal.terms import Quantity, UnitsMismatch
from clausal.modules.py.units import metre, second, newton, kilogram


class TestSplineUnits:
    """Phase 5 — Interpolation with Quantity inputs."""

    def test_make_eval_spline_propagates_y_dims(self):
        """make_spline with Quantity x/y → eval_spline returns Quantity with y_dims."""
        # nv
        x = Quantity(np.array([0.0, 1.0, 2.0, 3.0]), {second: 1})
        y = Quantity(np.array([0.0, 1.0, 4.0, 9.0]), {metre: 1})
        handle = _drive(make_spline, x, y)
        assert handle is not None and isinstance(handle, int)
        # Evaluate at x=1.0 second
        result = _drive(eval_spline, handle, Quantity(1.0, {second: 1}))
        assert isinstance(result, Quantity), f"Expected Quantity, got {type(result)}"
        assert dict(result.dims) == {metre: 1}
        assert float(result.value) == pytest.approx(1.0, abs=0.1)
        _drive(free, handle)

    def test_make_eval_spline_plain_fast_path(self):
        """Plain arrays → plain result, unchanged."""
        # nv
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.array([0.0, 1.0, 4.0, 9.0])
        handle = _drive(make_spline, x, y)
        assert handle is not None
        result = _drive(eval_spline, handle, 1.0)
        assert not isinstance(result, Quantity)
        _drive(free, handle)

    def test_spline_integral_has_y_times_x_dims(self):
        """spline_integral returns Quantity with y_dims + x_dims."""
        # nv
        x = Quantity(np.array([0.0, 1.0, 2.0]), {second: 1})
        y = Quantity(np.array([1.0, 1.0, 1.0]), {metre: 1, second: -1})
        handle = _drive(make_spline, x, y, 1)  # linear
        assert handle is not None
        integral = _drive(spline_integral, handle,
                          Quantity(0.0, {second: 1}), Quantity(2.0, {second: 1}))
        assert isinstance(integral, Quantity), f"Expected Quantity, got {type(integral)}"
        # integral of (m/s) over (s) = m
        assert dict(integral.dims) == {metre: 1}
        assert float(integral.value) == pytest.approx(2.0, abs=0.1)
        _drive(free, handle)

    def test_spline_derivative_handle_has_adjusted_dims(self):
        """spline_derivative returns a handle whose y_dims = y_dims − x_dims."""
        # nv
        x = Quantity(np.array([0.0, 1.0, 2.0, 3.0]), {second: 1})
        y = Quantity(np.array([0.0, 1.0, 4.0, 9.0]), {metre: 1})
        handle = _drive(make_spline, x, y)
        assert handle is not None
        deriv_handle = _drive(spline_derivative, handle)
        assert deriv_handle is not None
        # Evaluate derivative: dy/dx has dims metre/second
        result = _drive(eval_spline, deriv_handle, Quantity(1.0, {second: 1}))
        assert isinstance(result, Quantity), f"Expected Quantity, got {type(result)}"
        assert dict(result.dims) == {metre: 1, second: -1}
        _drive(free, handle)
        _drive(free, deriv_handle)

    def test_eval_spline_nu_dims(self):
        """eval_spline(HANDLE, X, NU, RESULT) with NU=1 has derivative dims."""
        # nv
        x = Quantity(np.array([0.0, 1.0, 2.0, 3.0]), {second: 1})
        y = Quantity(np.array([0.0, 1.0, 4.0, 9.0]), {metre: 1})
        handle = _drive(make_spline, x, y)
        assert handle is not None
        result = _drive(eval_spline, handle, Quantity(1.0, {second: 1}), 1)
        assert isinstance(result, Quantity)
        assert dict(result.dims) == {metre: 1, second: -1}
        _drive(free, handle)

    def test_make_cubic_with_units(self):
        """make_cubic stores dims; eval_spline propagates them."""
        # nv
        x = Quantity(np.array([0.0, 1.0, 2.0, 3.0]), {second: 1})
        y = Quantity(np.array([0.0, 2.0, 4.0, 6.0]), {metre: 1})
        handle = _drive(make_cubic, x, y)
        assert handle is not None
        result = _drive(eval_spline, handle, Quantity(1.5, {second: 1}))
        assert isinstance(result, Quantity)
        assert dict(result.dims) == {metre: 1}
        assert float(result.value) == pytest.approx(3.0, abs=0.1)
        _drive(free, handle)
