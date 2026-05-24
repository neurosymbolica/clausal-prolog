"""Tests for clausal.modules.py.scipy_sparse — scipy.sparse predicates.

Tests cover:
- Construction predicates: MakeCSR, MakeCSC, MakeCOO, MakeDiagonals, MakeEye
- Conversion predicates: ToDense, FromDense
- Inspection predicates: Shape, NonzeroCount
- Linalg predicates: Solve, EigenDecomposeHermitian, SingularValueDecompose
- Lifecycle: Free
- Module exports
- .clausal fixture integration
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")
pytest.importorskip("numpy", reason="numpy not installed")

import numpy as np
import scipy.sparse

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_sparse import (
    MakeCSR,
    MakeCSC,
    MakeCOO,
    MakeDiagonals,
    MakeEye,
    ToDense,
    FromDense,
    Shape,
    NonzeroCount,
    Solve,
    EigenDecomposeHermitian,
    SingularValueDecompose,
    Free,
    _SPARSE_REGISTRY,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution or None."""
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


def _fails(pred, *args):
    """Return True if predicate yields no solutions."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, *args, result, trail)
    return all(sentinel is DONE for _, sentinel in gen)


def _free(handle):
    dispatch = Free._get_dispatch()
    trail = Trail()
    list(dispatch(None, None, None, None, handle, trail))


# ── Sample data ───────────────────────────────────────────────────────────

# Simple 3x3 sparse matrix:
# [1 0 2]
# [0 3 0]
# [4 0 5]
_DATA = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
_INDICES_CSR = np.array([0, 2, 1, 0, 2])   # column indices
_INDPTR_CSR = np.array([0, 2, 3, 5])        # row pointers
_SHAPE = (3, 3)

# COO representation of the same matrix
_ROW = np.array([0, 0, 1, 2, 2])
_COL = np.array([0, 2, 1, 0, 2])

# Dense version for round-trip tests
_DENSE = np.array([[1.0, 0.0, 2.0],
                   [0.0, 3.0, 0.0],
                   [4.0, 0.0, 5.0]])

# Simple diagonal data
_DIAG_DATA = np.array([1.0, 2.0, 3.0])


# ════════════════════════════════════════════════════════════════════════════
# TestMakeCSR
# ════════════════════════════════════════════════════════════════════════════

class TestMakeCSR:
    def test_arity4_returns_handle(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)
        assert isinstance(h, int)
        _free(h)

    def test_arity5_with_shape(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR, _SHAPE)
        assert isinstance(h, int)
        _free(h)

    def test_arity6_with_shape_dtype(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR, _SHAPE, "float64")
        assert isinstance(h, int)
        _free(h)

    def test_handle_in_registry(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)
        assert h in _SPARSE_REGISTRY
        _free(h)
        assert h not in _SPARSE_REGISTRY

    def test_registry_object_is_sparse(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)
        assert scipy.sparse.issparse(_SPARSE_REGISTRY[h])
        _free(h)

    def test_correct_nnz(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)
        assert _SPARSE_REGISTRY[h].nnz == 5
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestMakeCSC
# ════════════════════════════════════════════════════════════════════════════

class TestMakeCSC:
    def test_arity4_returns_handle(self):
        # Build CSC of the same matrix using column-compressed format
        # nv
        data = np.array([1.0, 4.0, 3.0, 2.0, 5.0])
        indices = np.array([0, 2, 1, 0, 2])  # row indices
        indptr = np.array([0, 2, 3, 5])       # col pointers
        h = _drive(MakeCSC, data, indices, indptr)
        assert isinstance(h, int)
        _free(h)

    def test_arity5_with_shape(self):
        # nv
        data = np.array([1.0, 4.0, 3.0, 2.0, 5.0])
        indices = np.array([0, 2, 1, 0, 2])
        indptr = np.array([0, 2, 3, 5])
        h = _drive(MakeCSC, data, indices, indptr, _SHAPE)
        assert isinstance(h, int)
        _free(h)

    def test_arity6_with_dtype(self):
        # nv
        data = np.array([1.0, 4.0, 3.0, 2.0, 5.0])
        indices = np.array([0, 2, 1, 0, 2])
        indptr = np.array([0, 2, 3, 5])
        h = _drive(MakeCSC, data, indices, indptr, _SHAPE, "float32")
        assert isinstance(h, int)
        obj = _SPARSE_REGISTRY[h]
        assert obj.dtype == np.float32
        _free(h)

    def test_registry_object_is_sparse(self):
        # nv
        data = np.array([1.0, 2.0])
        indices = np.array([0, 1])
        indptr = np.array([0, 1, 2])
        h = _drive(MakeCSC, data, indices, indptr)
        assert scipy.sparse.issparse(_SPARSE_REGISTRY[h])
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestMakeCOO
# ════════════════════════════════════════════════════════════════════════════

class TestMakeCOO:
    def test_arity4_returns_handle(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL)
        assert isinstance(h, int)
        _free(h)

    def test_arity5_with_shape(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL, _SHAPE)
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_sparse(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL)
        assert scipy.sparse.issparse(_SPARSE_REGISTRY[h])
        _free(h)

    def test_correct_nnz(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL)
        assert _SPARSE_REGISTRY[h].nnz == 5
        _free(h)

    def test_todense_matches_expected(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL, _SHAPE)
        dense = _drive(ToDense, h)
        np.testing.assert_allclose(dense, _DENSE, atol=1e-10)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestMakeDiagonals
# ════════════════════════════════════════════════════════════════════════════

class TestMakeDiagonals:
    def test_arity2_main_diagonal(self):
        # nv
        h = _drive(MakeDiagonals, _DIAG_DATA)
        assert isinstance(h, int)
        obj = _SPARSE_REGISTRY[h]
        assert scipy.sparse.issparse(obj)
        _free(h)

    def test_arity3_with_offset(self):
        # nv
        h = _drive(MakeDiagonals, _DIAG_DATA, 0)
        assert isinstance(h, int)
        _free(h)

    def test_arity4_with_shape(self):
        # nv
        h = _drive(MakeDiagonals, _DIAG_DATA, 0, (3, 3))
        assert isinstance(h, int)
        _free(h)

    def test_diagonal_values_correct(self):
        # nv
        h = _drive(MakeDiagonals, _DIAG_DATA)
        dense = _drive(ToDense, h)
        np.testing.assert_allclose(np.diag(dense), _DIAG_DATA, atol=1e-10)
        _free(h)

    def test_superdiagonal(self):
        # nv
        diag = np.array([1.0, 2.0])
        h = _drive(MakeDiagonals, diag, 1, (3, 3))
        dense = _drive(ToDense, h)
        # superdiagonal: [0,1]=1, [1,2]=2
        assert abs(dense[0, 1] - 1.0) < 1e-10
        assert abs(dense[1, 2] - 2.0) < 1e-10
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestMakeEye
# ════════════════════════════════════════════════════════════════════════════

class TestMakeEye:
    def test_arity2_returns_handle(self):
        # nv
        h = _drive(MakeEye, 3)
        assert isinstance(h, int)
        _free(h)

    def test_arity3_rectangular(self):
        # nv
        h = _drive(MakeEye, 3, 4)
        assert isinstance(h, int)
        obj = _SPARSE_REGISTRY[h]
        assert obj.shape == (3, 4)
        _free(h)

    def test_arity4_with_offset(self):
        # nv
        h = _drive(MakeEye, 3, 3, 1)
        assert isinstance(h, int)
        _free(h)

    def test_identity_values(self):
        # nv
        h = _drive(MakeEye, 3)
        dense = _drive(ToDense, h)
        np.testing.assert_allclose(dense, np.eye(3), atol=1e-10)
        _free(h)

    def test_nnz_identity(self):
        # nv
        h = _drive(MakeEye, 4)
        nnz = _drive(NonzeroCount, h)
        assert nnz == 4
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestToDense
# ════════════════════════════════════════════════════════════════════════════

class TestToDense:
    def setup_method(self):
        self._h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)

    def teardown_method(self):
        _free(self._h)

    def test_arity2_returns_array(self):
        # nv
        result = _drive(ToDense, self._h)
        assert isinstance(result, np.ndarray)

    def test_correct_shape(self):
        # nv
        result = _drive(ToDense, self._h)
        assert result.shape == (3, 3)

    def test_values_match(self):
        # nv
        result = _drive(ToDense, self._h)
        np.testing.assert_allclose(result, _DENSE, atol=1e-10)

    def test_arity3_order_c(self):
        # nv
        result = _drive(ToDense, self._h, "C")
        assert isinstance(result, np.ndarray)
        np.testing.assert_allclose(result, _DENSE, atol=1e-10)

    def test_arity3_order_f(self):
        # nv
        result = _drive(ToDense, self._h, "F")
        assert isinstance(result, np.ndarray)
        np.testing.assert_allclose(result, _DENSE, atol=1e-10)


# ════════════════════════════════════════════════════════════════════════════
# TestFromDense
# ════════════════════════════════════════════════════════════════════════════

class TestFromDense:
    def test_arity2_returns_handle(self):
        # nv
        h = _drive(FromDense, _DENSE)
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_sparse(self):
        # nv
        h = _drive(FromDense, _DENSE)
        assert scipy.sparse.issparse(_SPARSE_REGISTRY[h])
        _free(h)

    def test_round_trip_todense(self):
        # nv
        h = _drive(FromDense, _DENSE)
        result = _drive(ToDense, h)
        np.testing.assert_allclose(result, _DENSE, atol=1e-10)
        _free(h)

    def test_arity3_csc_format(self):
        # nv
        h = _drive(FromDense, _DENSE, "csc")
        assert isinstance(h, int)
        obj = _SPARSE_REGISTRY[h]
        assert scipy.sparse.isspmatrix_csc(obj)
        _free(h)

    def test_arity3_csr_format(self):
        # nv
        h = _drive(FromDense, _DENSE, "csr")
        assert isinstance(h, int)
        obj = _SPARSE_REGISTRY[h]
        assert scipy.sparse.isspmatrix_csr(obj)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestShape
# ════════════════════════════════════════════════════════════════════════════

class TestShape:
    def test_shape_3x3(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR, _SHAPE)
        result = _drive(Shape, h)
        assert result == (3, 3)
        _free(h)

    def test_shape_eye_4x4(self):
        # nv
        h = _drive(MakeEye, 4)
        result = _drive(Shape, h)
        assert result == (4, 4)
        _free(h)

    def test_shape_rectangular(self):
        # nv
        h = _drive(MakeEye, 3, 5)
        result = _drive(Shape, h)
        assert result == (3, 5)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestNonzeroCount
# ════════════════════════════════════════════════════════════════════════════

class TestNonzeroCount:
    def test_nnz_csr_5_elements(self):
        # nv
        h = _drive(MakeCSR, _DATA, _INDICES_CSR, _INDPTR_CSR)
        result = _drive(NonzeroCount, h)
        assert result == 5
        _free(h)

    def test_nnz_eye_3(self):
        # nv
        h = _drive(MakeEye, 3)
        result = _drive(NonzeroCount, h)
        assert result == 3
        _free(h)

    def test_nnz_coo_matches(self):
        # nv
        h = _drive(MakeCOO, _DATA, _ROW, _COL)
        result = _drive(NonzeroCount, h)
        assert result == 5
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestSolve
# ════════════════════════════════════════════════════════════════════════════

# Build a simple 3x3 diagonally dominant system: A @ x = b, x = [1, 2, 3]
_A_DATA = np.array([4.0, 1.0, 1.0, 5.0, 1.0, 1.0, 6.0])
_A_INDICES = np.array([0, 1, 0, 1, 2, 1, 2])
_A_INDPTR = np.array([0, 2, 5, 7])
_A_SHAPE = (3, 3)
_B_VEC = np.array([4.0 * 1 + 1 * 2,
                   1 * 1 + 5 * 2 + 1 * 3,
                   1 * 2 + 6 * 3])  # = [6, 14, 20]
_X_EXPECTED = np.array([1.0, 2.0, 3.0])


class TestSolve:
    def setup_method(self):
        self._h = _drive(MakeCSR, _A_DATA, _A_INDICES, _A_INDPTR, _A_SHAPE)

    def teardown_method(self):
        _free(self._h)

    def test_arity3_returns_array(self):
        # nv
        result = _drive(Solve, self._h, _B_VEC)
        assert isinstance(result, np.ndarray)

    def test_arity3_correct_solution(self):
        # nv
        result = _drive(Solve, self._h, _B_VEC)
        np.testing.assert_allclose(result, _X_EXPECTED, atol=1e-8)

    def test_arity4_with_permc_spec(self):
        # nv
        result = _drive(Solve, self._h, _B_VEC, "NATURAL")
        np.testing.assert_allclose(result, _X_EXPECTED, atol=1e-8)

    def test_arity5_with_use_umfpack(self):
        # nv
        result = _drive(Solve, self._h, _B_VEC, None, False)
        np.testing.assert_allclose(result, _X_EXPECTED, atol=1e-8)

    def test_invalid_handle_fails(self):
        # nv
        assert _fails(Solve, 999999, _B_VEC)


# ════════════════════════════════════════════════════════════════════════════
# TestEigenDecomposeHermitian
# ════════════════════════════════════════════════════════════════════════════

# Symmetric 5x5 matrix for eigendecomposition
_SYM_DENSE = np.array([
    [4.0, 1.0, 0.0, 0.0, 0.0],
    [1.0, 3.0, 1.0, 0.0, 0.0],
    [0.0, 1.0, 5.0, 1.0, 0.0],
    [0.0, 0.0, 1.0, 2.0, 1.0],
    [0.0, 0.0, 0.0, 1.0, 3.0],
], dtype=float)


class TestEigenDecomposeHermitian:
    def setup_method(self):
        self._h = _drive(FromDense, _SYM_DENSE, "csr")

    def teardown_method(self):
        _free(self._h)

    def test_arity2_returns_dict(self):
        # nv
        result = _drive(EigenDecomposeHermitian, self._h)
        assert isinstance(result, dict)
        assert "eigenvalues" in result
        assert "eigenvectors" in result

    def test_arity2_eigenvalues_count(self):
        # nv
        result = _drive(EigenDecomposeHermitian, self._h)
        # default k = min(6, n-1) = min(6, 4) = 4
        assert len(result["eigenvalues"]) >= 1

    def test_arity3_k2(self):
        # nv
        result = _drive(EigenDecomposeHermitian, self._h, 2)
        assert len(result["eigenvalues"]) == 2
        assert result["eigenvectors"].shape[1] == 2

    def test_arity3_eigenvalues_are_real(self):
        # nv
        result = _drive(EigenDecomposeHermitian, self._h, 2)
        # All eigenvalues of a real symmetric matrix are real
        assert np.all(np.isreal(result["eigenvalues"]))

    def test_invalid_handle_fails(self):
        # nv
        assert _fails(EigenDecomposeHermitian, 999999)


# ════════════════════════════════════════════════════════════════════════════
# TestSingularValueDecompose
# ════════════════════════════════════════════════════════════════════════════

# Non-symmetric sparse matrix for SVD
_SVD_DENSE = np.array([
    [1.0, 2.0, 0.0, 0.0],
    [0.0, 3.0, 1.0, 0.0],
    [0.0, 0.0, 2.0, 4.0],
    [1.0, 0.0, 0.0, 5.0],
], dtype=float)


class TestSingularValueDecompose:
    def setup_method(self):
        self._h = _drive(FromDense, _SVD_DENSE, "csr")

    def teardown_method(self):
        _free(self._h)

    def test_arity2_returns_dict(self):
        # nv
        result = _drive(SingularValueDecompose, self._h)
        assert isinstance(result, dict)
        assert "u" in result
        assert "s" in result
        assert "vt" in result

    def test_arity3_k2(self):
        # nv
        result = _drive(SingularValueDecompose, self._h, 2)
        assert len(result["s"]) == 2
        assert result["u"].shape[1] == 2
        assert result["vt"].shape[0] == 2

    def test_singular_values_positive(self):
        # nv
        result = _drive(SingularValueDecompose, self._h, 2)
        assert np.all(result["s"] > 0)

    def test_reconstruction(self):
        # nv
        result = _drive(SingularValueDecompose, self._h, 2)
        u, s, vt = result["u"], result["s"], result["vt"]
        # Low-rank approximation should have rank 2
        approx = u @ np.diag(s) @ vt
        assert approx.shape == (4, 4)

    def test_invalid_handle_fails(self):
        # nv
        assert _fails(SingularValueDecompose, 999999)


# ════════════════════════════════════════════════════════════════════════════
# TestFree
# ════════════════════════════════════════════════════════════════════════════

class TestFree:
    def test_free_removes_from_registry(self):
        # nv
        h = _drive(MakeEye, 3)
        assert h in _SPARSE_REGISTRY
        _free(h)
        assert h not in _SPARSE_REGISTRY

    def test_free_unknown_handle_succeeds(self):
        # nv
        dispatch = Free._get_dispatch()
        trail = Trail()
        results = list(dispatch(None, None, None, None, 999999, trail))
        assert any(sentinel is None for _, sentinel in results)

    def test_free_twice_succeeds(self):
        # nv
        h = _drive(MakeEye, 3)
        _free(h)
        _free(h)  # second free should not raise


# ════════════════════════════════════════════════════════════════════════════
# TestModuleExports
# ════════════════════════════════════════════════════════════════════════════

class TestModuleExports:
    def test_all_exports_present(self):
        # nv
        import clausal.modules.py.scipy_sparse as m
        for name in [
            "MakeCSR", "MakeCSC", "MakeCOO", "MakeDiagonals", "MakeEye",
            "ToDense", "FromDense",
            "Shape", "NonzeroCount",
            "Solve", "EigenDecomposeHermitian", "SingularValueDecompose",
            "Free",
        ]:
            assert hasattr(m, name), f"Missing export: {name}"

    def test_shim_exports_match(self):
        # nv
        import clausal.modules.py.scipy_sparse as shim
        import clausal.modules.py.scipy_sparse as impl
        for name in impl.__all__:
            if name.startswith("_"):
                continue
            assert hasattr(shim, name), f"Shim missing: {name}"

    def test_registry_exported(self):
        # nv
        import clausal.modules.py.scipy_sparse as m
        assert hasattr(m, "_SPARSE_REGISTRY")
        assert isinstance(m._SPARSE_REGISTRY, dict)


# ════════════════════════════════════════════════════════════════════════════
# TestFixtureIntegration
# ════════════════════════════════════════════════════════════════════════════

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


class TestSciPySparseFixture:
    """Run Test predicates from tests/fixtures/scipy_sparse_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_sparse_tests")

    @pytest.mark.parametrize("name", [
        "makecsr returns handle",
        "makecsr nnz correct",
        "makecsc returns handle",
        "makecoo returns handle",
        "makecoo todense round-trip",
        "makediags main diagonal",
        "makeeye 3x3 identity",
        "makeeye nnz equals n",
        "todense correct shape",
        "todense correct values",
        "fromdense round-trip",
        "shape returns tuple",
        "nonzerocount correct",
        "solve linear system",
        "eigendecompose hermitian k2",
        "svd k2 s positive",
        "free handle succeeds",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"
