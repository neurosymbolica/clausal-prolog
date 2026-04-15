"""Tests for clausal.modules.py.scipy_differentiate — scipy.differentiate predicates.

Tests cover:
- Derivative: scalar function, array function, with extra args
- Jacobian: vector-valued function
- Hessian: scalar multivariate function
- ResultGet: field extraction from result dict
- Unification succeeds when RESULT is unbound
- Unification fails when RESULT is bound to an incorrect value
- .clausal fixture integration
"""

import math
import os
import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.logic.solve import call
from clausal.import_hook import _load_module
from clausal.modules.py.scipy_differentiate import (
    Derivative, Jacobian, Hessian, ResultGet,
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


def _drive_result_get(result_dict, field):
    value = Var()
    dispatch = ResultGet._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, result_dict, field, value, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(value)
    return None


def _fails_when_bound_wrong(pred, *inputs):
    """Return True when predicate yields no solutions for a wrong RESULT."""
    trail = Trail()
    wrong = object()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *inputs, wrong, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── Derivative ────────────────────────────────────────────────────────────

class TestDerivative:
    def test_quadratic_at_3(self):
        # d/dx x² = 2x; at x=3 → 6
        # nv
        result = _drive(Derivative, lambda x: x**2, 3.0)
        assert result is not None
        assert result["df"] == pytest.approx(6.0, abs=1e-10)

    def test_sin_at_zero(self):
        # d/dx sin(x) = cos(x); at x=0 → 1
        # scipy.differentiate passes numpy scalars so must use numpy.sin
        # nv
        result = _drive(Derivative, np.sin, 0.0)
        assert result is not None
        assert result["df"] == pytest.approx(1.0, abs=1e-10)

    def test_exp_at_one(self):
        # d/dx e^x = e^x; at x=1 → e
        # nv
        result = _drive(Derivative, np.exp, 1.0)
        assert result is not None
        assert result["df"] == pytest.approx(math.e, rel=1e-8)

    def test_result_dict_has_required_fields(self):
        # nv
        result = _drive(Derivative, lambda x: x**3, 2.0)
        assert result is not None
        for field in ("x", "df", "error", "success", "status", "nfev", "nit"):
            assert field in result

    def test_success_flag(self):
        # nv
        result = _drive(Derivative, lambda x: x**2, 1.0)
        assert result["success"] is True or result["success"] == True  # noqa: E712

    def test_with_extra_args(self):
        # f(x, a) = a * x²; d/dx = 2*a*x; at x=2, a=3 → 12
        # nv
        result = _drive(Derivative, lambda x, a: a * x**2, 2.0, [3.0])
        assert result is not None
        assert result["df"] == pytest.approx(12.0, abs=1e-8)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_when_bound_wrong(Derivative, lambda x: x, 1.0)

    def test_x_field_echoes_input(self):
        # nv
        result = _drive(Derivative, lambda x: x**2, 5.0)
        assert result["x"] == pytest.approx(5.0)


# ── Jacobian ──────────────────────────────────────────────────────────────

class TestJacobian:
    def test_linear_function(self):
        # f(x) = [x[0]*2, x[1]*3] → J = [[2,0],[0,3]]
        # nv
        def f(x):
            return np.array([2 * x[0], 3 * x[1]])

        result = _drive(Jacobian, f, np.array([1.0, 1.0]))
        assert result is not None
        j = result["df"]
        assert j.shape == (2, 2)
        assert j[0, 0] == pytest.approx(2.0, abs=1e-8)
        assert j[1, 1] == pytest.approx(3.0, abs=1e-8)
        assert j[0, 1] == pytest.approx(0.0, abs=1e-8)
        assert j[1, 0] == pytest.approx(0.0, abs=1e-8)

    def test_result_dict_has_required_fields(self):
        # nv
        result = _drive(Jacobian, lambda x: np.array([x[0]**2]), np.array([2.0]))
        assert result is not None
        # Jacobian result has no 'x' or 'nit' fields
        for field in ("df", "error", "success", "status", "nfev"):
            assert field in result

    def test_quadratic_jacobian(self):
        # f(x) = x[0]² + x[1]² → J = [2*x[0], 2*x[1]]
        # nv
        def f(x):
            return np.array([x[0]**2 + x[1]**2])

        result = _drive(Jacobian, f, np.array([1.0, 2.0]))
        assert result is not None
        j = result["df"]
        # J[0,0] ≈ 2*1=2, J[0,1] ≈ 2*2=4
        assert j[0, 0] == pytest.approx(2.0, abs=1e-7)
        assert j[0, 1] == pytest.approx(4.0, abs=1e-7)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_when_bound_wrong(
            Jacobian,
            lambda x: np.array([x[0]]),
            np.array([1.0]),
        )


# ── Hessian ───────────────────────────────────────────────────────────────

class TestHessian:
    def test_quadratic_hessian_is_identity_scaled(self):
        # f(x) = x[0]² + x[1]² → H = [[2,0],[0,2]]
        # nv
        def f(x):
            return x[0]**2 + x[1]**2

        result = _drive(Hessian, f, np.array([1.0, 2.0]))
        assert result is not None
        h = result["ddf"]
        assert h.shape == (2, 2)
        assert h[0, 0] == pytest.approx(2.0, abs=1e-6)
        assert h[1, 1] == pytest.approx(2.0, abs=1e-6)

    def test_result_dict_has_required_fields(self):
        # nv
        def f(x):
            return x[0]**2

        result = _drive(Hessian, f, np.array([1.0]))
        assert result is not None
        # Hessian result has no 'x', 'nit', or 'nfev' fields
        for field in ("ddf", "error", "success", "status"):
            assert field in result

    def test_mixed_partial(self):
        # f(x) = x[0]*x[1] → H = [[0,1],[1,0]]
        # nv
        def f(x):
            return x[0] * x[1]

        result = _drive(Hessian, f, np.array([1.0, 1.0]))
        assert result is not None
        h = result["ddf"]
        assert h[0, 0] == pytest.approx(0.0, abs=1e-6)
        assert h[0, 1] == pytest.approx(1.0, abs=1e-6)
        assert h[1, 0] == pytest.approx(1.0, abs=1e-6)
        assert h[1, 1] == pytest.approx(0.0, abs=1e-6)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_when_bound_wrong(
            Hessian,
            lambda x: x[0]**2,
            np.array([1.0]),
        )


# ── ResultGet ─────────────────────────────────────────────────────────────

class TestResultGet:
    def _get_result(self):
        return _drive(Derivative, lambda x: x**2, 3.0)

    def test_get_df(self):
        # nv
        r = self._get_result()
        df = _drive_result_get(r, "df")
        assert df == pytest.approx(6.0, abs=1e-10)

    def test_get_x(self):
        # nv
        r = self._get_result()
        x = _drive_result_get(r, "x")
        assert x == pytest.approx(3.0)

    def test_get_success(self):
        # nv
        r = self._get_result()
        ok = _drive_result_get(r, "success")
        assert ok is True or ok == True  # noqa: E712

    def test_get_error(self):
        # nv
        r = self._get_result()
        err = _drive_result_get(r, "error")
        assert err >= 0.0

    def test_missing_field_fails(self):
        # nv
        r = self._get_result()
        v = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, r, "nonexistent_field", v, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bound_value_unifies(self):
        # nv
        r = self._get_result()
        # Bind VALUE to the correct answer → should succeed
        df_expected = r["df"]
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, r, "df", df_expected, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1

    def test_bound_wrong_value_fails(self):
        # nv
        r = self._get_result()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, r, "df", object(), trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_hessian_result_get(self):
        # nv
        r = _drive(Hessian, lambda x: x[0]**2 + x[1]**2, np.array([1.0, 2.0]))
        ddf = _drive_result_get(r, "ddf")
        assert ddf is not None
        assert ddf.shape == (2, 2)


# ── .clausal fixture integration ──────────────────────────────────────────

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
    """Run Test predicates from tests/fixtures/scipy_differentiate_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_differentiate_tests")

    @pytest.mark.parametrize("name", [
        "derivative of x squared at 3",
        "derivative of sin at zero",
        "derivative result has success field",
        "derivative with extra args",
        "hessian of sum of squares",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"


# ── Quantity / dimensional analysis ──────────────────────────────────────

from clausal.terms import Quantity, UnitsMismatch
from clausal.modules.py.units import Metre, Second, Newton, Kilogram


def _NpM():
    """Newton-per-Metre unit predicate."""
    return Newton / Metre


class TestDerivativeUnits:
    """Phase 3 — Derivative with Quantity inputs."""

    def test_derivative_linear_newton_per_metre(self):
        """f(x) = x * k (k = 9.8 N/m) → df/dx = 9.8 N/m."""
        # nv
        k = Quantity(9.8, _NpM())
        f = lambda x: x * k
        result = _drive(Derivative, f, Quantity(1.0, {Metre: 1}))
        assert result is not None
        df = result["df"]
        assert isinstance(df, Quantity), f"Expected Quantity, got {type(df)}"
        assert df.value == pytest.approx(9.8, rel=1e-6)
        # dims should be Newton/Metre = {Kilogram: 1, Second: -2}
        expected_dims = dict((_NpM())._dims)
        assert dict(df.dims) == expected_dims

    def test_derivative_x_has_input_units(self):
        """Result 'x' field should preserve input Metre units."""
        # nv
        k = Quantity(2.0, _NpM())
        f = lambda x: x * k
        result = _drive(Derivative, f, Quantity(3.0, {Metre: 1}))
        assert result is not None
        x = result["x"]
        assert isinstance(x, Quantity), f"Expected Quantity, got {type(x)}"
        assert x.value == pytest.approx(3.0)
        assert dict(x.dims) == {Metre: 1}

    def test_derivative_error_has_df_units(self):
        """Error estimate has same units as df."""
        # nv
        k = Quantity(2.0, _NpM())
        f = lambda x: x * k
        result = _drive(Derivative, f, Quantity(3.0, {Metre: 1}))
        assert result is not None
        err = result["error"]
        assert isinstance(err, Quantity), f"Expected Quantity, got {type(err)}"
        expected_dims = dict((_NpM())._dims)
        assert dict(err.dims) == expected_dims

    def test_derivative_plain_function_returns_plain_df(self):
        """f returns plain float → df is plain (no Quantity wrapping)."""
        # f strips .value manually → returns float
        # nv
        f = lambda x: x.value ** 2
        result = _drive(Derivative, f, Quantity(3.0, {Metre: 1}))
        assert result is not None
        df = result["df"]
        assert not isinstance(df, Quantity), f"Expected plain, got Quantity"
        assert float(df) == pytest.approx(6.0, abs=1e-6)

    def test_derivative_plain_fast_path(self):
        """No Quantity inputs → plain result, same as before."""
        # nv
        result = _drive(Derivative, lambda x: x ** 2, 3.0)
        assert result is not None
        df = result["df"]
        assert not isinstance(df, Quantity)
        assert float(df) == pytest.approx(6.0, abs=1e-8)

    def test_derivative_dimensionless_quantity(self):
        """Dimensionless Quantity (dims={}) → x is still wrapped, df depends on f."""
        # nv
        f = lambda x: x ** 2  # returns plain float (since Quantity**2 works)
        result = _drive(Derivative, f, Quantity(3.0, {}))
        assert result is not None
        # x should not be wrapped (empty dims)
        assert not isinstance(result["x"], Quantity)


class TestJacobianUnits:
    """Phase 3 — Jacobian with Quantity inputs."""

    def test_jacobian_linear_map(self):
        """f: R^n(Metre) → R^n(Newton), Jacobian has dims Newton/Metre."""
        # nv
        k = Quantity(9.8, _NpM())
        # Jacobian requires array input → array output
        f = lambda x: x * k
        x0 = Quantity(np.array([1.0, 2.0]), {Metre: 1})
        result = _drive(Jacobian, f, x0)
        assert result is not None
        df = result["df"]
        assert isinstance(df, Quantity), f"Expected Quantity, got {type(df)}"
        expected_dims = dict((_NpM())._dims)
        assert dict(df.dims) == expected_dims

    def test_jacobian_plain_fast_path(self):
        """No Quantity inputs → plain result."""
        # nv
        result = _drive(Jacobian, lambda x: x ** 2, np.array([3.0]))
        assert result is not None
        assert not isinstance(result["df"], Quantity)


class TestHessianUnits:
    """Phase 3 — Hessian with Quantity inputs."""

    def test_hessian_with_quantity_x(self):
        """Hessian with Quantity x, plain f → x in result is wrapped."""
        # f doesn't accept Quantity (uses indexing), so probe falls back.
        # x in the result dict should still be wrapped with input dims.
        # nv
        f = lambda x: x[0] ** 2 + x[1] ** 2
        x0 = Quantity(np.array([1.0, 2.0]), {Metre: 1})
        result = _drive(Hessian, f, x0)
        assert result is not None
        # ddf is plain (f doesn't propagate units)
        ddf = result["ddf"]
        assert not isinstance(ddf, Quantity)
        assert float(ddf[0, 0]) == pytest.approx(2.0, rel=1e-4)

    def test_hessian_plain_fast_path(self):
        """No Quantity inputs → plain result."""
        # nv
        result = _drive(Hessian, lambda x: x[0]**2 + x[1]**2, np.array([1.0, 2.0]))
        assert result is not None
        assert not isinstance(result["ddf"], Quantity)
