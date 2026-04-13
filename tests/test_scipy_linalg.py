"""Tests for clausal.modules.py.scipy_linalg — scipy.linalg predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via ResultGet
"""

import math
import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np
import scipy.linalg as la

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_linalg import (
    Solve, LeastSquares, SolveTriangular,
    LuDecompose, QrDecompose, SingularValueDecompose,
    Cholesky, EigenDecompose, EigenDecomposeHermitian, Schur,
    Inverse, PseudoInverse, Determinant, Norm,
    MatrixExpLog, MatrixSquareRoot, MatrixFunction,
    LuFactor, LuSolve, CholeskyFactor, CholeskySolve,
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


def _drive_bwd(pred, *args):
    """Call predicate in backward direction: first arg is unbound Var, rest are ground.

    For a bidirectional predicate Pred(X, Y): binds X (result) given Y (ground).
    """
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, result, *args, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is bound to a wrong value."""
    trail = Trail()
    result_bound = object()  # will not unify with any array
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


def approx_array(a, b, rtol=1e-6):
    """True when numpy arrays a ≈ b."""
    a, b = np.asarray(a), np.asarray(b)
    return np.allclose(a, b, rtol=rtol, atol=1e-10)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def square_2x2():
    return np.array([[2.0, 1.0], [5.0, 3.0]])


@pytest.fixture
def spd_2x2():
    """Symmetric positive definite 2×2."""
    return np.array([[4.0, 2.0], [2.0, 3.0]])


@pytest.fixture
def rhs_2():
    return np.array([1.0, 2.0])


@pytest.fixture
def rect_3x2():
    return np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])


# ── Solve ─────────────────────────────────────────────────────────────────

class TestSolve:
    def test_basic(self, square_2x2, rhs_2):
        # nv
        r = _drive(Solve, square_2x2, rhs_2)
        assert approx_array(r, la.solve(square_2x2, rhs_2))

    def test_known_solution(self):
        # nv
        A = np.array([[1.0, 0.0], [0.0, 2.0]])
        b = np.array([3.0, 4.0])
        r = _drive(Solve, A, b)
        assert approx_array(r, [3.0, 2.0])

    def test_with_assume_a(self, spd_2x2, rhs_2):
        # nv
        r = _drive(Solve, spd_2x2, rhs_2, 'pos')
        expected = la.solve(spd_2x2, rhs_2, assume_a='pos')
        assert approx_array(r, expected)

    def test_wrong_result_fails(self, square_2x2, rhs_2):
        # nv
        assert _fails_with_wrong_result(Solve, square_2x2, rhs_2)


# ── LeastSquares ──────────────────────────────────────────────────────────

class TestLeastSquares:
    def test_returns_dict(self, rect_3x2):
        # nv
        b = np.array([1.0, 2.0, 3.0])
        r = _drive(LeastSquares, rect_3x2, b)
        assert isinstance(r, dict)
        assert set(r.keys()) >= {"x", "residuals", "rank", "s"}

    def test_x_field(self, rect_3x2):
        # nv
        b = np.array([1.0, 2.0, 3.0])
        r = _drive(LeastSquares, rect_3x2, b)
        x = _drive_result_get(r, "x")
        expected_x, *_ = la.lstsq(rect_3x2, b)
        assert approx_array(x, expected_x)

    def test_rank_field(self, rect_3x2):
        # nv
        b = np.array([1.0, 2.0, 3.0])
        r = _drive(LeastSquares, rect_3x2, b)
        rank = _drive_result_get(r, "rank")
        assert rank == 2

    def test_result_get_missing_field(self, rect_3x2):
        # nv
        b = np.array([1.0, 2.0, 3.0])
        r = _drive(LeastSquares, rect_3x2, b)
        v = _drive_result_get(r, "nonexistent")
        assert v is None

    def test_result_get_wrong_type(self):
        # nv
        v = _drive_result_get("not a dict", "x")
        assert v is None


# ── SolveTriangular ───────────────────────────────────────────────────────

class TestSolveTriangular:
    def test_upper(self):
        # nv
        U = np.array([[2.0, 1.0], [0.0, 3.0]])
        b = np.array([5.0, 3.0])
        r = _drive(SolveTriangular, U, b)
        assert approx_array(r, la.solve_triangular(U, b))

    def test_lower(self):
        # nv
        L = np.array([[2.0, 0.0], [1.0, 3.0]])
        b = np.array([4.0, 5.0])
        r = _drive(SolveTriangular, L, b, True)
        assert approx_array(r, la.solve_triangular(L, b, lower=True))

    def test_wrong_result_fails(self):
        # nv
        U = np.array([[1.0, 0.0], [0.0, 1.0]])
        b = np.array([1.0, 1.0])
        assert _fails_with_wrong_result(SolveTriangular, U, b)


# ── LuDecompose ───────────────────────────────────────────────────────────

class TestLuDecompose:
    def test_returns_dict(self, square_2x2):
        # nv
        r = _drive(LuDecompose, square_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"p", "l", "u"}

    def test_plu_reconstruct(self, square_2x2):
        # nv
        r = _drive(LuDecompose, square_2x2)
        p = _drive_result_get(r, "p")
        l = _drive_result_get(r, "l")
        u = _drive_result_get(r, "u")
        assert approx_array(p @ l @ u, square_2x2)

    def test_result_get_p(self, square_2x2):
        # nv
        r = _drive(LuDecompose, square_2x2)
        p = _drive_result_get(r, "p")
        assert p.shape == (2, 2)


# ── QrDecompose ───────────────────────────────────────────────────────────

class TestQrDecompose:
    def test_returns_dict(self, square_2x2):
        # nv
        r = _drive(QrDecompose, square_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"q", "r"}

    def test_qr_reconstruct(self, square_2x2):
        # nv
        r = _drive(QrDecompose, square_2x2)
        q = _drive_result_get(r, "q")
        rv = _drive_result_get(r, "r")
        assert approx_array(q @ rv, square_2x2)

    def test_q_orthogonal(self, square_2x2):
        # nv
        r = _drive(QrDecompose, square_2x2)
        q = _drive_result_get(r, "q")
        assert approx_array(q @ q.T, np.eye(2))


# ── SingularValueDecompose ────────────────────────────────────────────────

class TestSingularValueDecompose:
    def test_returns_dict(self, square_2x2):
        # nv
        r = _drive(SingularValueDecompose, square_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"u", "s", "vh"}

    def test_reconstruct(self, square_2x2):
        # nv
        r = _drive(SingularValueDecompose, square_2x2)
        u = _drive_result_get(r, "u")
        s = _drive_result_get(r, "s")
        vh = _drive_result_get(r, "vh")
        assert approx_array(u @ np.diag(s) @ vh, square_2x2)

    def test_singular_values_positive(self, square_2x2):
        # nv
        r = _drive(SingularValueDecompose, square_2x2)
        s = _drive_result_get(r, "s")
        assert all(sv > 0 for sv in s)


# ── Cholesky ──────────────────────────────────────────────────────────────

class TestCholesky:
    def test_upper_default(self, spd_2x2):
        # nv
        r = _drive(Cholesky, spd_2x2)
        expected = la.cholesky(spd_2x2, lower=False)
        assert approx_array(r, expected)

    def test_lower_explicit(self, spd_2x2):
        # nv
        r = _drive(Cholesky, spd_2x2, True)
        expected = la.cholesky(spd_2x2, lower=True)
        assert approx_array(r, expected)

    def test_reconstruct_upper(self, spd_2x2):
        # nv
        U = _drive(Cholesky, spd_2x2)
        assert approx_array(U.T @ U, spd_2x2)


# ── EigenDecompose ────────────────────────────────────────────────────────

class TestEigenDecompose:
    def test_returns_dict(self, square_2x2):
        # nv
        r = _drive(EigenDecompose, square_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"eigenvalues", "eigenvectors"}

    def test_eigenvalue_count(self, square_2x2):
        # nv
        r = _drive(EigenDecompose, square_2x2)
        vals = _drive_result_get(r, "eigenvalues")
        assert len(vals) == 2

    def test_eigenvector_shape(self, square_2x2):
        # nv
        r = _drive(EigenDecompose, square_2x2)
        vecs = _drive_result_get(r, "eigenvectors")
        assert vecs.shape == (2, 2)

    def test_av_equals_lv(self, square_2x2):
        """A @ v ≈ λ * v for each eigenpair."""
        # nv
        r = _drive(EigenDecompose, square_2x2)
        vals = _drive_result_get(r, "eigenvalues")
        vecs = _drive_result_get(r, "eigenvectors")
        for i in range(2):
            lhs = square_2x2 @ vecs[:, i]
            rhs = vals[i] * vecs[:, i]
            assert approx_array(np.real(lhs), np.real(rhs))


# ── EigenDecomposeHermitian ───────────────────────────────────────────────

class TestEigenDecomposeHermitian:
    def test_returns_dict(self, spd_2x2):
        # nv
        r = _drive(EigenDecomposeHermitian, spd_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"eigenvalues", "eigenvectors"}

    def test_eigenvalues_real_positive(self, spd_2x2):
        # nv
        r = _drive(EigenDecomposeHermitian, spd_2x2)
        vals = _drive_result_get(r, "eigenvalues")
        assert all(v > 0 for v in np.real(vals))

    def test_eigenvectors_orthonormal(self, spd_2x2):
        # nv
        r = _drive(EigenDecomposeHermitian, spd_2x2)
        vecs = _drive_result_get(r, "eigenvectors")
        assert approx_array(vecs.T @ vecs, np.eye(2))


# ── Schur ─────────────────────────────────────────────────────────────────

class TestSchur:
    def test_returns_dict(self, square_2x2):
        # nv
        r = _drive(Schur, square_2x2)
        assert isinstance(r, dict)
        assert set(r.keys()) == {"t", "z"}

    def test_schur_reconstruct(self, square_2x2):
        # nv
        r = _drive(Schur, square_2x2)
        t = _drive_result_get(r, "t")
        z = _drive_result_get(r, "z")
        assert approx_array(z @ t @ z.T, square_2x2)

    def test_complex_output(self, square_2x2):
        # nv
        r = _drive(Schur, square_2x2, 'complex')
        t = _drive_result_get(r, "t")
        assert t.dtype == complex or np.issubdtype(t.dtype, np.complexfloating)


# ── Inverse ───────────────────────────────────────────────────────────────

class TestInverse:
    def test_inverse(self, square_2x2):
        # nv
        r = _drive(Inverse, square_2x2)
        assert approx_array(square_2x2 @ r, np.eye(2))

    def test_identity_inverse(self):
        # nv
        I = np.eye(3)
        r = _drive(Inverse, I)
        assert approx_array(r, I)

    def test_wrong_result_fails(self, square_2x2):
        # nv
        assert _fails_with_wrong_result(Inverse, square_2x2)


# ── PseudoInverse ─────────────────────────────────────────────────────────

class TestPseudoInverse:
    def test_square(self, square_2x2):
        # nv
        r = _drive(PseudoInverse, square_2x2)
        expected = la.pinv(square_2x2)
        assert approx_array(r, expected)

    def test_rect(self, rect_3x2):
        # nv
        r = _drive(PseudoInverse, rect_3x2)
        # pseudoinverse: A+ @ A ≈ I_2
        assert approx_array(r @ rect_3x2, np.eye(2), rtol=1e-5)


# ── Determinant ───────────────────────────────────────────────────────────

class TestDeterminant:
    def test_identity(self):
        # nv
        r = _drive(Determinant, np.eye(3))
        assert abs(float(r) - 1.0) < 1e-10

    def test_known_det(self, square_2x2):
        # det([[2,1],[5,3]]) = 2*3 - 1*5 = 1
        # nv
        r = _drive(Determinant, square_2x2)
        assert abs(float(r) - 1.0) < 1e-10

    def test_singular_det(self):
        # nv
        A = np.array([[1.0, 2.0], [2.0, 4.0]])
        r = _drive(Determinant, A)
        assert abs(float(r)) < 1e-10


# ── Norm ──────────────────────────────────────────────────────────────────

class TestNorm:
    def test_vector_norm(self):
        # nv
        v = np.array([3.0, 4.0])
        r = _drive(Norm, v)
        assert abs(float(r) - 5.0) < 1e-10

    def test_frobenius_norm(self, square_2x2):
        # nv
        r = _drive(Norm, square_2x2)
        expected = la.norm(square_2x2)
        assert abs(float(r) - float(expected)) < 1e-10

    def test_norm_with_ord(self, square_2x2):
        # nv
        r = _drive(Norm, square_2x2, 'fro')
        expected = la.norm(square_2x2, ord='fro')
        assert abs(float(r) - float(expected)) < 1e-10

    def test_inf_norm(self, square_2x2):
        # nv
        r = _drive(Norm, square_2x2, np.inf)
        expected = la.norm(square_2x2, ord=np.inf)
        assert abs(float(r) - float(expected)) < 1e-10


# ── MatrixExponential ─────────────────────────────────────────────────────

class TestMatrixExponential:
    def test_zero_matrix(self):
        # nv
        Z = np.zeros((2, 2))
        # Forward direction of MatrixExpLog: MatrixExpLog(Z, result_var) → result_var = expm(Z)
        r = _drive(MatrixExpLog, Z)
        assert approx_array(r, np.eye(2))

    def test_diagonal(self):
        # nv
        D = np.diag([1.0, 2.0])
        r = _drive(MatrixExpLog, D)
        expected = np.diag([math.e, math.e ** 2])
        assert approx_array(r, expected, rtol=1e-6)


# ── MatrixLogarithm ───────────────────────────────────────────────────────

class TestMatrixLogarithm:
    def test_identity(self):
        # Backward direction of MatrixExpLog: MatrixExpLog(result_var, I) → result_var = logm(I)
        # nv
        r = _drive_bwd(MatrixExpLog, np.eye(2))
        assert approx_array(np.real(r), np.zeros((2, 2)))

    def test_expm_logm_roundtrip(self, spd_2x2):
        # nv
        log_m = _drive_bwd(MatrixExpLog, spd_2x2)
        r = _drive(MatrixExpLog, np.real(log_m))
        assert approx_array(np.real(r), spd_2x2, rtol=1e-5)


# ── MatrixSquareRoot ──────────────────────────────────────────────────────

class TestMatrixSquareRoot:
    def test_identity(self):
        # nv
        r = _drive(MatrixSquareRoot, np.eye(2))
        assert approx_array(np.real(r), np.eye(2))

    def test_sqrtm_squared(self, spd_2x2):
        # nv
        s = _drive(MatrixSquareRoot, spd_2x2)
        assert approx_array(np.real(s @ s), spd_2x2, rtol=1e-5)


# ── MatrixFunction ────────────────────────────────────────────────────────

class TestMatrixFunction:
    def test_exp_via_matrix_function(self, spd_2x2):
        # nv
        r = _drive(MatrixFunction, spd_2x2, np.exp)
        expected_expm = _drive(MatrixExpLog, spd_2x2)
        assert approx_array(np.real(r), np.real(expected_expm), rtol=1e-5)

    def test_identity_fn(self):
        # nv
        A = np.array([[2.0, 0.0], [0.0, 3.0]])
        r = _drive(MatrixFunction, A, lambda x: x)
        assert approx_array(np.real(r), A, rtol=1e-5)


# ── LuFactor / LuSolve ───────────────────────────────────────────────────

class TestLuFactorSolve:
    def test_factor_then_solve(self, square_2x2, rhs_2):
        # nv
        lu_piv = _drive(LuFactor, square_2x2)
        assert lu_piv is not None
        r = _drive(LuSolve, lu_piv, rhs_2)
        expected = la.solve(square_2x2, rhs_2)
        assert approx_array(r, expected)

    def test_reuse_factorisation(self, square_2x2):
        # nv
        lu_piv = _drive(LuFactor, square_2x2)
        b1 = np.array([1.0, 0.0])
        b2 = np.array([0.0, 1.0])
        x1 = _drive(LuSolve, lu_piv, b1)
        x2 = _drive(LuSolve, lu_piv, b2)
        assert approx_array(square_2x2 @ x1, b1)
        assert approx_array(square_2x2 @ x2, b2)


# ── CholeskyFactor / CholeskySolve ────────────────────────────────────────

class TestCholeskyFactorSolve:
    def test_factor_then_solve(self, spd_2x2, rhs_2):
        # nv
        c_lower = _drive(CholeskyFactor, spd_2x2)
        assert c_lower is not None
        r = _drive(CholeskySolve, c_lower, rhs_2)
        expected = la.solve(spd_2x2, rhs_2)
        assert approx_array(r, expected)

    def test_reuse_factorisation(self, spd_2x2):
        # nv
        c_lower = _drive(CholeskyFactor, spd_2x2)
        b1 = np.array([1.0, 0.0])
        b2 = np.array([0.0, 1.0])
        x1 = _drive(CholeskySolve, c_lower, b1)
        x2 = _drive(CholeskySolve, c_lower, b2)
        assert approx_array(spd_2x2 @ x1, b1)
        assert approx_array(spd_2x2 @ x2, b2)


# ── ResultGet ─────────────────────────────────────────────────────────────

class TestResultGet:
    def test_basic_extraction(self):
        # nv
        d = {"x": np.array([1.0, 2.0]), "rank": 2}
        x = _drive_result_get(d, "x")
        assert approx_array(x, [1.0, 2.0])

    def test_missing_field_fails(self):
        # nv
        d = {"x": 1}
        v = _drive_result_get(d, "y")
        assert v is None

    def test_not_a_dict_fails(self):
        # nv
        v = _drive_result_get(42, "x")
        assert v is None

    def test_non_string_field_fails(self):
        # nv
        value = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        field_var = Var()  # unbound var as field — should fail
        gen = dispatch(None, None, {"x": 1}, field_var, value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bind_existing_scalar_result(self):
        # nv
        d = {"rank": 2}
        value = 2
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, d, "rank", value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1
