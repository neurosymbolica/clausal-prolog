"""Tests for clausal.modules.py.scipy_spatial — scipy.spatial predicates.

Tests cover:
- Tier 1 distance functions: CrossDistance, PairwiseDistance, SquareForm, PointDistance
- Tier 3 KD-tree: MakeKdTree, KdTreeQuery, KdTreeQueryBall, KdTreeQueryPairs
- Tier 3 ConvexHull: MakeConvexHull, ConvexHullAttr
- Tier 3 Delaunay: MakeDelaunay, DelaunayFindSimplex
- Tier 3 Rotation: MakeRotation, RotationApply, RotationAs, RotationCompose, RotationInverse
- Lifecycle: Free
- Module exports
- .clausal fixture integration
"""

import math

import pytest

pytest.importorskip("scipy", reason="scipy not installed")
pytest.importorskip("numpy", reason="numpy not installed")

import numpy as np
import scipy.spatial
import scipy.spatial.distance as spdist
import scipy.spatial.transform as sptransform

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_spatial import (
    CrossDistance,
    PairwiseDistance,
    SquareForm,
    PointDistance,
    MakeKdTree,
    KdTreeQuery,
    KdTreeQueryBall,
    KdTreeQueryPairs,
    MakeConvexHull,
    ConvexHullAttr,
    MakeDelaunay,
    DelaunayFindSimplex,
    MakeRotation,
    RotationApply,
    RotationAs,
    RotationCompose,
    RotationInverse,
    Free,
    _SPATIAL_REGISTRY,
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

_PTS_2D = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
_PTS_SQUARE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
_PTS_3D = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


# ════════════════════════════════════════════════════════════════════════════
# TestCrossDistance
# ════════════════════════════════════════════════════════════════════════════

class TestCrossDistance:
    def test_shape_default_metric(self):
        # nv
        xa = np.array([[0.0, 0.0], [1.0, 0.0]])
        xb = np.array([[0.0, 1.0]])
        result = _drive(CrossDistance, xa, xb)
        assert result.shape == (2, 1)

    def test_euclidean_3_4_5(self):
        # nv
        xa = np.array([[0.0, 0.0]])
        xb = np.array([[3.0, 4.0]])
        result = _drive(CrossDistance, xa, xb, "euclidean")
        assert abs(float(result[0, 0]) - 5.0) < 1e-10

    def test_cityblock(self):
        # nv
        xa = np.array([[0.0, 0.0]])
        xb = np.array([[1.0, 2.0]])
        result = _drive(CrossDistance, xa, xb, "cityblock")
        assert abs(float(result[0, 0]) - 3.0) < 1e-10

    def test_with_kwargs(self):
        # nv
        xa = np.array([[0.0, 0.0]])
        xb = np.array([[1.0, 0.0], [0.0, 1.0]])
        result = _drive(CrossDistance, xa, xb, "minkowski", {"p": 1})
        assert result.shape == (1, 2)
        assert abs(float(result[0, 0]) - 1.0) < 1e-10

    def test_unification_fails_wrong_value(self):
        # nv
        xa = np.array([[0.0, 0.0]])
        xb = np.array([[3.0, 4.0]])
        assert not _fails(CrossDistance, xa, xb)

    def test_multiple_rows(self):
        # nv
        result = _drive(CrossDistance, _PTS_2D, _PTS_2D)
        assert result.shape == (3, 3)
        # Diagonal should be zero
        np.testing.assert_allclose(np.diag(result), 0.0, atol=1e-10)


# ════════════════════════════════════════════════════════════════════════════
# TestPairwiseDistance
# ════════════════════════════════════════════════════════════════════════════

class TestPairwiseDistance:
    def test_length_3_points(self):
        # nv
        result = _drive(PairwiseDistance, _PTS_2D)
        assert len(result) == 3  # n*(n-1)/2 = 3

    def test_euclidean_3_4_5(self):
        # nv
        pts = np.array([[0.0, 0.0], [3.0, 4.0]])
        result = _drive(PairwiseDistance, pts, "euclidean")
        assert abs(float(result[0]) - 5.0) < 1e-10

    def test_with_kwargs(self):
        # nv
        result = _drive(PairwiseDistance, _PTS_2D, "minkowski", {"p": 2})
        assert len(result) == 3

    def test_single_pair(self):
        # nv
        pts = np.array([[0.0, 0.0], [1.0, 0.0]])
        result = _drive(PairwiseDistance, pts)
        assert len(result) == 1
        assert abs(float(result[0]) - 1.0) < 1e-10


# ════════════════════════════════════════════════════════════════════════════
# TestSquareForm
# ════════════════════════════════════════════════════════════════════════════

class TestSquareForm:
    def test_condensed_to_square(self):
        # nv
        condensed = spdist.pdist(_PTS_2D)
        result = _drive(SquareForm, condensed)
        assert result.shape == (3, 3)

    def test_diagonal_is_zero(self):
        # nv
        condensed = spdist.pdist(_PTS_2D)
        result = _drive(SquareForm, condensed)
        np.testing.assert_allclose(np.diag(result), 0.0, atol=1e-10)

    def test_symmetric(self):
        # nv
        condensed = spdist.pdist(_PTS_2D)
        result = _drive(SquareForm, condensed)
        np.testing.assert_allclose(result, result.T, atol=1e-10)

    def test_square_to_condensed(self):
        # nv
        square = spdist.squareform(spdist.pdist(_PTS_2D))
        result = _drive(SquareForm, square)
        assert result.ndim == 1
        assert len(result) == 3


# ════════════════════════════════════════════════════════════════════════════
# TestPointDistance
# ════════════════════════════════════════════════════════════════════════════

class TestPointDistance:
    def test_euclidean_3_4_5(self):
        # nv
        result = _drive(PointDistance, "euclidean", [0.0, 0.0], [3.0, 4.0])
        assert abs(result - 5.0) < 1e-10

    def test_cityblock(self):
        # nv
        result = _drive(PointDistance, "cityblock", [0.0, 0.0], [1.0, 2.0])
        assert abs(result - 3.0) < 1e-10

    def test_cosine_identical(self):
        # nv
        result = _drive(PointDistance, "cosine", [1.0, 0.0], [1.0, 0.0])
        assert abs(result) < 1e-10

    def test_returns_float(self):
        # nv
        result = _drive(PointDistance, "euclidean", [0.0], [1.0])
        assert isinstance(result, float)


# ════════════════════════════════════════════════════════════════════════════
# TestMakeKdTree
# ════════════════════════════════════════════════════════════════════════════

class TestMakeKdTree:
    def test_returns_int_handle(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D)
        assert isinstance(h, int)
        _free(h)

    def test_handle_in_registry(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D)
        assert h in _SPATIAL_REGISTRY
        _free(h)
        assert h not in _SPATIAL_REGISTRY

    def test_with_leafsize(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D, 5)
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_kdtree(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D)
        assert isinstance(_SPATIAL_REGISTRY[h], scipy.spatial.KDTree)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestKdTreeQuery
# ════════════════════════════════════════════════════════════════════════════

class TestKdTreeQuery:
    def setup_method(self):
        self._h = _drive(MakeKdTree, _PTS_2D)

    def teardown_method(self):
        _free(self._h)

    def test_nearest_returns_dict(self):
        # nv
        q = np.array([[0.1, 0.0]])
        result = _drive(KdTreeQuery, self._h, q)
        assert isinstance(result, dict)
        assert "distances" in result
        assert "indices" in result

    def test_nearest_index_correct(self):
        # nv
        q = np.array([[0.9, 0.0]])
        result = _drive(KdTreeQuery, self._h, q)
        assert int(result["indices"][0]) == 1  # [1,0] is nearest to [0.9,0]

    def test_query_k_2(self):
        # nv
        q = np.array([[0.0, 0.0]])
        result = _drive(KdTreeQuery, self._h, q, 2)
        assert result["distances"].shape[1] == 2
        assert result["indices"].shape[1] == 2

    def test_nearest_distance_zero_for_exact(self):
        # nv
        q = np.array([[0.0, 0.0]])
        result = _drive(KdTreeQuery, self._h, q)
        assert abs(float(result["distances"][0])) < 1e-10


# ════════════════════════════════════════════════════════════════════════════
# TestKdTreeQueryBall
# ════════════════════════════════════════════════════════════════════════════

class TestKdTreeQueryBall:
    def setup_method(self):
        self._h = _drive(MakeKdTree, _PTS_2D)

    def teardown_method(self):
        _free(self._h)

    def test_returns_list(self):
        # nv
        result = _drive(KdTreeQueryBall, self._h, [0.0, 0.0], 0.5)
        assert isinstance(result, list)

    def test_small_radius_finds_origin(self):
        # Single query point → flat list of indices
        # nv
        result = _drive(KdTreeQueryBall, self._h, [0.0, 0.0], 0.5)
        assert 0 in result

    def test_large_radius_finds_all(self):
        # nv
        result = _drive(KdTreeQueryBall, self._h, [0.5, 0.5], 2.0)
        assert len(result) == 3


# ════════════════════════════════════════════════════════════════════════════
# TestKdTreeQueryPairs
# ════════════════════════════════════════════════════════════════════════════

class TestKdTreeQueryPairs:
    def setup_method(self):
        self._h = _drive(MakeKdTree, _PTS_2D)

    def teardown_method(self):
        _free(self._h)

    def test_returns_set(self):
        # nv
        result = _drive(KdTreeQueryPairs, self._h, 1.5)
        assert isinstance(result, set)

    def test_large_radius_all_pairs(self):
        # nv
        result = _drive(KdTreeQueryPairs, self._h, 10.0)
        assert len(result) == 3  # C(3,2)=3 pairs

    def test_small_radius_no_pairs(self):
        # nv
        result = _drive(KdTreeQueryPairs, self._h, 0.01)
        assert len(result) == 0


# ════════════════════════════════════════════════════════════════════════════
# TestMakeConvexHull
# ════════════════════════════════════════════════════════════════════════════

class TestMakeConvexHull:
    def test_returns_int_handle(self):
        # nv
        h = _drive(MakeConvexHull, _PTS_SQUARE)
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_convex_hull(self):
        # nv
        h = _drive(MakeConvexHull, _PTS_SQUARE)
        assert isinstance(_SPATIAL_REGISTRY[h], scipy.spatial.ConvexHull)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestConvexHullAttr
# ════════════════════════════════════════════════════════════════════════════

class TestConvexHullAttr:
    def setup_method(self):
        self._h = _drive(MakeConvexHull, _PTS_SQUARE)

    def teardown_method(self):
        _free(self._h)

    def test_vertices_is_array(self):
        # nv
        result = _drive(ConvexHullAttr, self._h, "vertices")
        assert hasattr(result, "__len__")

    def test_area_unit_square(self):
        # Unit square in 2D: ConvexHull.area = perimeter = 4.0
        # nv
        result = _drive(ConvexHullAttr, self._h, "area")
        assert abs(float(result) - 4.0) < 1e-6

    def test_volume_unit_square(self):
        # 2D ConvexHull: volume = area = 1.0
        # nv
        result = _drive(ConvexHullAttr, self._h, "volume")
        assert abs(float(result) - 1.0) < 1e-6

    def test_simplices_shape(self):
        # nv
        result = _drive(ConvexHullAttr, self._h, "simplices")
        assert result.shape[1] == 2  # 2D: each simplex is an edge (2 vertices)

    def test_equations_shape(self):
        # nv
        result = _drive(ConvexHullAttr, self._h, "equations")
        # Each row: [normal..., offset]; 2D → 3 columns
        assert result.shape[1] == 3


# ════════════════════════════════════════════════════════════════════════════
# TestMakeDelaunay
# ════════════════════════════════════════════════════════════════════════════

class TestMakeDelaunay:
    def test_returns_int_handle(self):
        # nv
        h = _drive(MakeDelaunay, _PTS_SQUARE)
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_delaunay(self):
        # nv
        h = _drive(MakeDelaunay, _PTS_SQUARE)
        assert isinstance(_SPATIAL_REGISTRY[h], scipy.spatial.Delaunay)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestDelaunayFindSimplex
# ════════════════════════════════════════════════════════════════════════════

class TestDelaunayFindSimplex:
    def setup_method(self):
        self._h = _drive(MakeDelaunay, _PTS_SQUARE)

    def teardown_method(self):
        _free(self._h)

    def test_interior_point_nonnegative(self):
        # nv
        xi = np.array([[0.5, 0.5]])
        result = _drive(DelaunayFindSimplex, self._h, xi)
        assert int(result[0]) >= 0

    def test_exterior_point_minus_one(self):
        # nv
        xi = np.array([[5.0, 5.0]])
        result = _drive(DelaunayFindSimplex, self._h, xi)
        assert int(result[0]) == -1

    def test_with_bruteforce(self):
        # nv
        xi = np.array([[0.5, 0.5]])
        result = _drive(DelaunayFindSimplex, self._h, xi, False)
        assert int(result[0]) >= 0


# ════════════════════════════════════════════════════════════════════════════
# TestMakeRotation
# ════════════════════════════════════════════════════════════════════════════

class TestMakeRotation:
    def test_from_rotvec_identity(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        assert isinstance(h, int)
        _free(h)

    def test_from_quat(self):
        # nv
        h = _drive(MakeRotation, "quat", [0.0, 0.0, 0.0, 1.0])
        assert isinstance(h, int)
        _free(h)

    def test_from_matrix(self):
        # nv
        h = _drive(MakeRotation, "matrix", np.eye(3))
        assert isinstance(h, int)
        _free(h)

    def test_from_euler(self):
        # nv
        h = _drive(MakeRotation, "euler", ("xyz", [0.0, 0.0, 0.0]))
        assert isinstance(h, int)
        _free(h)

    def test_registry_object_is_rotation(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        assert isinstance(_SPATIAL_REGISTRY[h], sptransform.Rotation)
        _free(h)

    def test_unknown_method_fails(self):
        # nv
        result = _drive(MakeRotation, "bogus_method", [0.0, 0.0, 0.0])
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# TestRotationApply
# ════════════════════════════════════════════════════════════════════════════

class TestRotationApply:
    def test_identity_preserves_vector(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        v = np.array([1.0, 2.0, 3.0])
        result = _drive(RotationApply, h, v)
        np.testing.assert_allclose(result, v, atol=1e-10)
        _free(h)

    def test_90_degree_z_rotation(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])
        v = np.array([1.0, 0.0, 0.0])
        result = _drive(RotationApply, h, v)
        np.testing.assert_allclose(result, [0.0, 1.0, 0.0], atol=1e-10)
        _free(h)

    def test_with_inverse(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])
        v = np.array([0.0, 1.0, 0.0])
        result = _drive(RotationApply, h, v, True)
        np.testing.assert_allclose(result, [1.0, 0.0, 0.0], atol=1e-10)
        _free(h)


# ════════════════════════════════════════════════════════════════════════════
# TestRotationAs
# ════════════════════════════════════════════════════════════════════════════

class TestRotationAs:
    def setup_method(self):
        self._h = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])

    def teardown_method(self):
        _free(self._h)

    def test_as_quat_length(self):
        # nv
        result = _drive(RotationAs, self._h, "quat")
        assert len(result) == 4

    def test_as_matrix_shape(self):
        # nv
        result = _drive(RotationAs, self._h, "matrix")
        assert result.shape == (3, 3)

    def test_as_rotvec_length(self):
        # nv
        result = _drive(RotationAs, self._h, "rotvec")
        assert len(result) == 3

    def test_as_euler_xyz(self):
        # nv
        result = _drive(RotationAs, self._h, "euler", "xyz")
        assert len(result) == 3
        # 90 deg around z: angles ≈ [0, 0, π/2]
        assert abs(result[2] - math.pi / 2) < 1e-10

    def test_as_euler_wrong_form_fails(self):
        # nv
        result = _drive(RotationAs, self._h, "quat", "xyz")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# TestRotationCompose
# ════════════════════════════════════════════════════════════════════════════

class TestRotationCompose:
    def test_compose_two_90_degrees(self):
        # nv
        h1 = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])
        h2 = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])
        hc = _drive(RotationCompose, h1, h2)
        v = np.array([1.0, 0.0, 0.0])
        result = _drive(RotationApply, hc, v)
        np.testing.assert_allclose(result, [-1.0, 0.0, 0.0], atol=1e-10)
        _free(h1); _free(h2); _free(hc)

    def test_returns_handle(self):
        # nv
        h1 = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        h2 = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        hc = _drive(RotationCompose, h1, h2)
        assert isinstance(hc, int)
        _free(h1); _free(h2); _free(hc)


# ════════════════════════════════════════════════════════════════════════════
# TestRotationInverse
# ════════════════════════════════════════════════════════════════════════════

class TestRotationInverse:
    def test_inverse_of_identity_is_identity(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        hinv = _drive(RotationInverse, h)
        v = np.array([1.0, 2.0, 3.0])
        result = _drive(RotationApply, hinv, v)
        np.testing.assert_allclose(result, v, atol=1e-10)
        _free(h); _free(hinv)

    def test_inverse_undoes_rotation(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, math.pi / 2])
        hinv = _drive(RotationInverse, h)
        v = np.array([0.0, 1.0, 0.0])
        result = _drive(RotationApply, hinv, v)
        np.testing.assert_allclose(result, [1.0, 0.0, 0.0], atol=1e-10)
        _free(h); _free(hinv)

    def test_returns_handle(self):
        # nv
        h = _drive(MakeRotation, "rotvec", [0.0, 0.0, 0.0])
        hinv = _drive(RotationInverse, h)
        assert isinstance(hinv, int)
        _free(h); _free(hinv)


# ════════════════════════════════════════════════════════════════════════════
# TestFree
# ════════════════════════════════════════════════════════════════════════════

class TestFree:
    def test_free_removes_from_registry(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D)
        assert h in _SPATIAL_REGISTRY
        _free(h)
        assert h not in _SPATIAL_REGISTRY

    def test_free_unknown_handle_succeeds(self):
        # Freeing a nonexistent handle should not raise
        # nv
        dispatch = Free._get_dispatch()
        trail = Trail()
        results = list(dispatch(None, None, None, None, 999999, trail))
        assert any(sentinel is None for _, sentinel in results)

    def test_free_twice_succeeds(self):
        # nv
        h = _drive(MakeKdTree, _PTS_2D)
        _free(h)
        _free(h)  # second free should not raise


# ════════════════════════════════════════════════════════════════════════════
# TestModuleExports
# ════════════════════════════════════════════════════════════════════════════

class TestModuleExports:
    def test_all_exports_present(self):
        # nv
        import clausal.modules.py.scipy_spatial as m
        for name in [
            "CrossDistance", "PairwiseDistance", "SquareForm", "PointDistance",
            "MakeKdTree", "KdTreeQuery", "KdTreeQueryBall", "KdTreeQueryPairs",
            "MakeConvexHull", "ConvexHullAttr",
            "MakeDelaunay", "DelaunayFindSimplex",
            "MakeRotation", "RotationApply", "RotationAs",
            "RotationCompose", "RotationInverse",
            "Free",
        ]:
            assert hasattr(m, name), f"Missing export: {name}"

    def test_shim_exports_match(self):
        # nv
        import clausal.modules.py.scipy_spatial as shim
        import clausal.modules.py.scipy_spatial as impl
        for name in impl.__all__:
            if name.startswith("_"):
                continue
            assert hasattr(shim, name), f"Shim missing: {name}"


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


class TestSciPySpatialFixture:
    """Run Test predicates from tests/fixtures/scipy_spatial_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_spatial_tests")

    @pytest.mark.parametrize("name", [
        "cross distance shape",
        "cross distance euclidean known value",
        "cross distance with kwargs",
        "pairwise distance length",
        "pairwise distance euclidean 3-4-5",
        "squareform round-trip",
        "point distance euclidean 3-4-5",
        "point distance cityblock",
        "kdtree make returns handle",
        "kdtree query nearest neighbour",
        "kdtree query k=2",
        "kdtree query ball finds neighbours in radius",
        "convex hull make returns handle",
        "convex hull vertices count",
        "convex hull area unit square",
        "delaunay make returns handle",
        "delaunay find simplex interior point",
        "delaunay find simplex exterior point returns -1",
        "rotation from rotvec apply identity",
        "rotation as quat from identity rotvec",
        "rotation as matrix from identity",
        "rotation inverse of identity is identity",
        "rotation compose two 90 degree z rotations",
        "free handle succeeds",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
