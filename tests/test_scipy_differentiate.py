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
    gen = dispatch(None, None, *args, result, trail)
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
    gen = dispatch(None, None, result_dict, field, value, trail)
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
    gen = dispatch(None, None, *inputs, wrong, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── Derivative ────────────────────────────────────────────────────────────

class TestDerivative:
    def test_quadratic_at_3(self):
        # d/dx x² = 2x; at x=3 → 6
        result = _drive(Derivative, lambda x: x**2, 3.0)
        assert result is not None
        assert result["df"] == pytest.approx(6.0, abs=1e-10)

    def test_sin_at_zero(self):
        # d/dx sin(x) = cos(x); at x=0 → 1
        # scipy.differentiate passes numpy scalars so must use numpy.sin
        result = _drive(Derivative, np.sin, 0.0)
        assert result is not None
        assert result["df"] == pytest.approx(1.0, abs=1e-10)

    def test_exp_at_one(self):
        # d/dx e^x = e^x; at x=1 → e
        result = _drive(Derivative, np.exp, 1.0)
        assert result is not None
        assert result["df"] == pytest.approx(math.e, rel=1e-8)

    def test_result_dict_has_required_fields(self):
        result = _drive(Derivative, lambda x: x**3, 2.0)
        assert result is not None
        for field in ("x", "df", "error", "success", "status", "nfev", "nit"):
            assert field in result

    def test_success_flag(self):
        result = _drive(Derivative, lambda x: x**2, 1.0)
        assert result["success"] is True or result["success"] == True  # noqa: E712

    def test_with_extra_args(self):
        # f(x, a) = a * x²; d/dx = 2*a*x; at x=2, a=3 → 12
        result = _drive(Derivative, lambda x, a: a * x**2, 2.0, [3.0])
        assert result is not None
        assert result["df"] == pytest.approx(12.0, abs=1e-8)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Derivative, lambda x: x, 1.0)

    def test_x_field_echoes_input(self):
        result = _drive(Derivative, lambda x: x**2, 5.0)
        assert result["x"] == pytest.approx(5.0)


# ── Jacobian ──────────────────────────────────────────────────────────────

class TestJacobian:
    def test_linear_function(self):
        # f(x) = [x[0]*2, x[1]*3] → J = [[2,0],[0,3]]
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
        result = _drive(Jacobian, lambda x: np.array([x[0]**2]), np.array([2.0]))
        assert result is not None
        # Jacobian result has no 'x' or 'nit' fields
        for field in ("df", "error", "success", "status", "nfev"):
            assert field in result

    def test_quadratic_jacobian(self):
        # f(x) = x[0]² + x[1]² → J = [2*x[0], 2*x[1]]
        def f(x):
            return np.array([x[0]**2 + x[1]**2])

        result = _drive(Jacobian, f, np.array([1.0, 2.0]))
        assert result is not None
        j = result["df"]
        # J[0,0] ≈ 2*1=2, J[0,1] ≈ 2*2=4
        assert j[0, 0] == pytest.approx(2.0, abs=1e-7)
        assert j[0, 1] == pytest.approx(4.0, abs=1e-7)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(
            Jacobian,
            lambda x: np.array([x[0]]),
            np.array([1.0]),
        )


# ── Hessian ───────────────────────────────────────────────────────────────

class TestHessian:
    def test_quadratic_hessian_is_identity_scaled(self):
        # f(x) = x[0]² + x[1]² → H = [[2,0],[0,2]]
        def f(x):
            return x[0]**2 + x[1]**2

        result = _drive(Hessian, f, np.array([1.0, 2.0]))
        assert result is not None
        h = result["ddf"]
        assert h.shape == (2, 2)
        assert h[0, 0] == pytest.approx(2.0, abs=1e-6)
        assert h[1, 1] == pytest.approx(2.0, abs=1e-6)

    def test_result_dict_has_required_fields(self):
        def f(x):
            return x[0]**2

        result = _drive(Hessian, f, np.array([1.0]))
        assert result is not None
        # Hessian result has no 'x', 'nit', or 'nfev' fields
        for field in ("ddf", "error", "success", "status"):
            assert field in result

    def test_mixed_partial(self):
        # f(x) = x[0]*x[1] → H = [[0,1],[1,0]]
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
        r = self._get_result()
        df = _drive_result_get(r, "df")
        assert df == pytest.approx(6.0, abs=1e-10)

    def test_get_x(self):
        r = self._get_result()
        x = _drive_result_get(r, "x")
        assert x == pytest.approx(3.0)

    def test_get_success(self):
        r = self._get_result()
        ok = _drive_result_get(r, "success")
        assert ok is True or ok == True  # noqa: E712

    def test_get_error(self):
        r = self._get_result()
        err = _drive_result_get(r, "error")
        assert err >= 0.0

    def test_missing_field_fails(self):
        r = self._get_result()
        v = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, r, "nonexistent_field", v, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bound_value_unifies(self):
        r = self._get_result()
        # Bind VALUE to the correct answer → should succeed
        df_expected = r["df"]
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, r, "df", df_expected, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1

    def test_bound_wrong_value_fails(self):
        r = self._get_result()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, r, "df", object(), trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_hessian_result_get(self):
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
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"
