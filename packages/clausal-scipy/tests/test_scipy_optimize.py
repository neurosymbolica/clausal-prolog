"""Tests for clausal.modules.py.scipy_optimize — scipy.optimize predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via ResultGet
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np
import scipy.optimize as opt

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_optimize import (
    minimize_scalar, minimize,
    differential_evolution, basin_hopping, dual_annealing, shgo_minimize,
    nonlinear_least_squares, curve_fit,
    root_scalar, root,
    linear_program, mixed_integer_linear_program,
    linear_constraint, bounds,
    ResultGet,
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
    """Use ResultGet to extract a field from a dict result."""
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


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is bound to a wrong value."""
    trail = Trail()
    result_bound = object()  # will not unify with any result
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── TestMinimizeScalar ────────────────────────────────────────────────────

class TestMinimizeScalar:
    def test_brent_quadratic(self):
        # nv
        r = _drive(minimize_scalar, lambda x: (x - 3.0) ** 2)
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x) - 3.0) < 1e-4

    def test_with_method(self):
        # nv
        r = _drive(minimize_scalar, lambda x: (x - 3.0) ** 2, 'brent')
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x) - 3.0) < 1e-4

    def test_bounded(self):
        # nv
        r = _drive(minimize_scalar, lambda x: (x - 3.0) ** 2, 'bounded', (1.0, 5.0))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x) - 3.0) < 1e-4

    def test_result_has_success(self):
        # nv
        r = _drive(minimize_scalar, lambda x: (x - 3.0) ** 2)
        assert r is not None
        assert r['success'] is True

    def test_result_get_x(self):
        # nv
        r = _drive(minimize_scalar, lambda x: (x - 3.0) ** 2)
        x = _drive_result_get(r, 'x')
        assert x is not None
        assert abs(float(x) - 3.0) < 1e-4

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(minimize_scalar, lambda x: (x - 3.0) ** 2)


# ── TestMinimize ──────────────────────────────────────────────────────────

class TestMinimize:
    def test_bfgs_quadratic(self):
        # nv
        r = _drive(minimize, lambda x: float(sum(xi ** 2 for xi in x)), np.array([1.0, 1.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert np.allclose(x, [0.0, 0.0], atol=1e-4)

    def test_with_method_nelder_mead(self):
        # nv
        r = _drive(minimize, lambda x: float(sum(xi ** 2 for xi in x)), np.array([1.0, 1.0]), 'Nelder-Mead')
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert np.allclose(x, [0.0, 0.0], atol=1e-3)

    def test_result_success(self):
        # nv
        r = _drive(minimize, lambda x: float(x[0] ** 2), np.array([1.0]))
        assert r is not None
        assert r['success'] is True

    def test_result_get_x(self):
        # nv
        r = _drive(minimize, lambda x: float(x[0] ** 2), np.array([1.0]))
        x = _drive_result_get(r, 'x')
        assert x is not None
        assert abs(float(x[0])) < 1e-4

    def test_result_get_fun(self):
        # nv
        r = _drive(minimize, lambda x: float(x[0] ** 2), np.array([1.0]))
        fun = _drive_result_get(r, 'fun')
        assert fun is not None
        assert abs(float(fun)) < 1e-8

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(minimize, lambda x: float(x[0] ** 2), np.array([1.0]))


# ── TestDifferentialEvolution ─────────────────────────────────────────────

class TestDifferentialEvolution:
    def test_simple(self):
        # nv
        r = _drive(differential_evolution, lambda x: (x[0] - 1.0) ** 2, [(0.0, 3.0)])
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 1.0) < 1e-3

    def test_with_seed(self):
        # nv
        r = _drive(differential_evolution, lambda x: (x[0] - 1.0) ** 2, [(0.0, 3.0)], 42)
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 1.0) < 1e-3


# ── TestBasinHopping ──────────────────────────────────────────────────────

class TestBasinHopping:
    def test_simple(self):
        # nv
        r = _drive(basin_hopping, lambda x: float(x[0] ** 2), np.array([1.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0])) < 1e-3

    def test_with_niter(self):
        # nv
        r = _drive(basin_hopping, lambda x: float(x[0] ** 2), np.array([1.0]), 20)
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0])) < 1e-3


# ── TestDualAnnealing ─────────────────────────────────────────────────────

class TestDualAnnealing:
    def test_simple(self):
        # nv
        r = _drive(dual_annealing, lambda x: (x[0] - 2.0) ** 2, [(0.0, 5.0)])
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 2.0) < 1e-2

    def test_with_seed(self):
        # nv
        r = _drive(dual_annealing, lambda x: (x[0] - 2.0) ** 2, [(0.0, 5.0)], 42)
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 2.0) < 1e-2


# ── TestShgoMinimize ──────────────────────────────────────────────────────

class TestShgoMinimize:
    def test_simple(self):
        # nv
        r = _drive(shgo_minimize, lambda x: float(x[0] ** 2), [(-3.0, 3.0)])
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0])) < 1e-3


# ── TestNonlinearLeastSquares ─────────────────────────────────────────────

class TestNonlinearLeastSquares:
    def test_simple(self):
        # nv
        r = _drive(nonlinear_least_squares, lambda x: [x[0] - 3.0, x[1] - 4.0], np.array([0.0, 0.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert np.allclose(x, [3.0, 4.0], atol=1e-4)

    def test_with_bounds(self):
        # nv
        r = _drive(nonlinear_least_squares,
                   lambda x: [x[0] - 3.0, x[1] - 4.0],
                   np.array([0.0, 0.0]),
                   ([-5.0, -5.0], [5.0, 5.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert np.allclose(x, [3.0, 4.0], atol=1e-4)


# ── TestCurveFit ──────────────────────────────────────────────────────────

class TestCurveFit:
    def test_linear_fit(self):
        # nv
        xdata = np.array([0.0, 1.0, 2.0])
        ydata = np.array([1.0, 3.0, 5.0])
        r = _drive(curve_fit, lambda x, a, b: a * x + b, xdata, ydata)
        assert r is not None
        popt = _drive_result_get(r, 'popt')
        assert np.allclose(popt, [2.0, 1.0], atol=1e-4)

    def test_with_p0(self):
        # nv
        xdata = np.array([0.0, 1.0, 2.0])
        ydata = np.array([1.0, 3.0, 5.0])
        r = _drive(curve_fit, lambda x, a, b: a * x + b, xdata, ydata, np.array([1.0, 0.0]))
        assert r is not None
        popt = _drive_result_get(r, 'popt')
        assert np.allclose(popt, [2.0, 1.0], atol=1e-4)

    def test_result_has_popt_pcov(self):
        # nv
        xdata = np.array([0.0, 1.0, 2.0])
        ydata = np.array([1.0, 3.0, 5.0])
        r = _drive(curve_fit, lambda x, a, b: a * x + b, xdata, ydata)
        assert r is not None
        assert 'popt' in r
        assert 'pcov' in r


# ── TestRootScalar ────────────────────────────────────────────────────────

class TestRootScalar:
    def test_bisect(self):
        # nv
        r = _drive(root_scalar, lambda x: x ** 2 - 4.0, 'bisect', [1.0, 3.0])
        assert r is not None
        root = _drive_result_get(r, 'root')
        assert abs(float(root) - 2.0) < 1e-6

    def test_brentq(self):
        # nv
        r = _drive(root_scalar, lambda x: x ** 2 - 4.0, 'brentq', [1.0, 3.0])
        assert r is not None
        root = _drive_result_get(r, 'root')
        assert abs(float(root) - 2.0) < 1e-6

    def test_secant(self):
        # nv
        r = _drive(root_scalar, lambda x: x ** 2 - 4.0, 'secant', 1.0, 3.0)
        assert r is not None
        root = _drive_result_get(r, 'root')
        assert abs(float(root) - 2.0) < 1e-6

    def test_result_converged(self):
        # nv
        r = _drive(root_scalar, lambda x: x ** 2 - 4.0, 'bisect', [1.0, 3.0])
        assert r is not None
        assert r['converged'] is True

    def test_result_get_root(self):
        # nv
        r = _drive(root_scalar, lambda x: x ** 2 - 4.0, 'bisect', [1.0, 3.0])
        root = _drive_result_get(r, 'root')
        assert root is not None
        assert abs(float(root) - 2.0) < 1e-6


# ── TestRoot ──────────────────────────────────────────────────────────────

class TestRoot:
    def test_simple_system(self):
        # nv
        r = _drive(root, lambda x: [x[0] ** 2 - 4.0], np.array([1.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 2.0) < 1e-6

    def test_with_method(self):
        # nv
        r = _drive(root, lambda x: [x[0] ** 2 - 4.0], np.array([1.0]), 'hybr')
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 2.0) < 1e-6

    def test_result_success(self):
        # nv
        r = _drive(root, lambda x: [x[0] ** 2 - 4.0], np.array([1.0]))
        assert r is not None
        assert r['success'] is True

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(root, lambda x: [x[0] ** 2 - 4.0], np.array([1.0]))


# ── TestLinearProgram ─────────────────────────────────────────────────────

class TestLinearProgram:
    def test_simple_1d(self):
        # min -x s.t. x <= 2 → x = 2
        # nv
        r = _drive(linear_program, np.array([-1.0]), np.array([[1.0]]), np.array([2.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 2.0) < 1e-6

    def test_2d(self):
        # min [-1,-2]@x s.t. [[1,1]]@x <= 4 → x[1] = 4
        # nv
        r = _drive(linear_program,
                   np.array([-1.0, -2.0]),
                   np.array([[1.0, 1.0]]),
                   np.array([4.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[1]) - 4.0) < 1e-4

    def test_with_equality(self):
        # min -x s.t. x == 3
        # nv
        r = _drive(linear_program,
                   np.array([-1.0]),
                   np.array([]).reshape(0, 1),
                   np.array([]),
                   np.array([[1.0]]),
                   np.array([3.0]))
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 3.0) < 1e-6

    def test_result_success(self):
        # nv
        r = _drive(linear_program, np.array([-1.0]), np.array([[1.0]]), np.array([2.0]))
        assert r is not None
        assert r['success'] is True

    def test_result_get_x(self):
        # nv
        r = _drive(linear_program, np.array([-1.0]), np.array([[1.0]]), np.array([2.0]))
        x = _drive_result_get(r, 'x')
        assert x is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(linear_program, np.array([-1.0]), np.array([[1.0]]), np.array([2.0]))


# ── TestMixedIntegerLinearProgram ─────────────────────────────────────────

class TestMixedIntegerLinearProgram:
    def test_simple(self):
        # nv
        import numpy as np
        from scipy.optimize import Bounds as ScipyBounds
        c = np.array([-1.0])
        integrality = np.array([1])
        bounds = ScipyBounds(lb=np.array([0.0]), ub=np.array([3.0]))
        r = _drive(mixed_integer_linear_program, c, None, integrality, bounds)
        assert r is not None
        x = _drive_result_get(r, 'x')
        assert abs(float(x[0]) - 3.0) < 1e-6


# ── TestLinearConstraint ──────────────────────────────────────────────────

class TestLinearConstraint:
    def test_creates_object(self):
        # nv
        import scipy.optimize
        r = _drive(linear_constraint, np.array([[1.0, 0.0]]), np.array([0.0]), np.array([1.0]))
        assert isinstance(r, scipy.optimize.LinearConstraint)


# ── TestBounds ────────────────────────────────────────────────────────────

class TestBounds:
    def test_creates_object(self):
        # nv
        import scipy.optimize
        r = _drive(bounds, np.array([0.0, 0.0]), np.array([1.0, 1.0]))
        assert isinstance(r, scipy.optimize.Bounds)


# ── TestResultGet ─────────────────────────────────────────────────────────

class TestResultGet:
    def test_get_existing_field(self):
        # nv
        d = {'x': 42}
        v = _drive_result_get(d, 'x')
        assert v == 42

    def test_missing_field_fails(self):
        # nv
        d = {'x': 42}
        v = _drive_result_get(d, 'y')
        assert v is None

    def test_wrong_result_type_fails(self):
        # nv
        v = _drive_result_get("not a dict", 'x')
        assert v is None

    def test_non_string_field_fails(self):
        # nv
        value = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        field_var = Var()  # unbound var as field — should fail
        gen = dispatch(None, None, None, None, {'x': 1}, field_var, value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bind_existing_scalar_result(self):
        # nv
        d = {'rank': 2}
        value = 2
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, d, 'rank', value, trail)
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


class TestScipyOptimizeFixture:
    """Run Test predicates from tests/fixtures/scipy_optimize_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_optimize_tests")

    @pytest.mark.parametrize("name", [
        "minimize quadratic bfgs",
        "minimize scalar brent",
        "minimize scalar with method",
        "root scalar bisect",
        "root system",
        "linear program 1d",
        "curve fit linear",
        "nonlinear least squares",
        "result get success",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
