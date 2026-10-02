"""Tests for clausal.modules.py.scipy_cluster — scipy.cluster predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via result_get
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_cluster import (
    linkage, flat_cluster, dendrogram, cophenet, inconsistent,
    k_means2, k_means, vector_quantize, whiten,
    result_get,
)
from clausal._suffixes import SEAM_SUFFIX


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
    """Use result_get to extract a field from a dict result."""
    value = Var()
    dispatch = result_get._get_dispatch()
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
    result_bound = object()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── Sample data ───────────────────────────────────────────────────────────

# 6 points in 2-D arranged in two clear clusters
_POINTS = np.array([
    [1.0, 1.0], [1.2, 0.9], [0.8, 1.1],
    [5.0, 5.0], [5.1, 4.9], [4.9, 5.1],
], dtype=float)


# ── TestLinkage ───────────────────────────────────────────────────────────

class TestLinkage:
    def test_returns_matrix(self):
        # nv
        z = _drive(linkage, _POINTS)
        assert z is not None
        assert z.shape == (5, 4)  # n-1 rows for 6 points

    def test_with_method(self):
        # nv
        z = _drive(linkage, _POINTS, 'ward')
        assert z is not None
        assert z.shape == (5, 4)

    def test_with_method_and_metric(self):
        # nv
        z = _drive(linkage, _POINTS, 'single', 'euclidean')
        assert z is not None
        assert z.shape == (5, 4)

    def test_with_optimal_ordering(self):
        # nv
        z = _drive(linkage, _POINTS, 'single', 'euclidean', True)
        assert z is not None
        assert z.shape == (5, 4)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(linkage, _POINTS)

    def test_distances_are_non_negative(self):
        # nv
        z = _drive(linkage, _POINTS)
        assert np.all(z[:, 2] >= 0)


# ── TestFlatCluster ───────────────────────────────────────────────────────

class TestFlatCluster:
    @pytest.fixture
    def linkage_matrix(self):
        from scipy.cluster.hierarchy import linkage
        return linkage(_POINTS, method='ward')

    def test_returns_labels(self, linkage_matrix):
        # nv
        labels = _drive(flat_cluster, linkage_matrix, 2, 'maxclust')
        assert labels is not None
        assert len(labels) == 6

    def test_two_clusters_split_correctly(self, linkage_matrix):
        # nv
        labels = _drive(flat_cluster, linkage_matrix, 2, 'maxclust')
        assert labels is not None
        # first three and last three should be in different clusters
        assert labels[0] == labels[1] == labels[2]
        assert labels[3] == labels[4] == labels[5]
        assert labels[0] != labels[3]

    def test_with_depth(self, linkage_matrix):
        # nv
        labels = _drive(flat_cluster, linkage_matrix, 2, 'maxclust', 2)
        assert labels is not None
        assert len(labels) == 6

    def test_default_criterion(self, linkage_matrix):
        # inconsistent criterion, threshold 1.5
        # nv
        labels = _drive(flat_cluster, linkage_matrix, 1.5)
        assert labels is not None
        assert len(labels) == 6

    def test_wrong_result_fails(self, linkage_matrix):
        # nv
        assert _fails_with_wrong_result(flat_cluster, linkage_matrix, 2, 'maxclust')


# ── TestDendrogram ────────────────────────────────────────────────────────

class TestDendrogram:
    @pytest.fixture
    def linkage_matrix(self):
        from scipy.cluster.hierarchy import linkage
        return linkage(_POINTS, method='ward')

    def test_returns_dict(self, linkage_matrix):
        # nv
        result = _drive(dendrogram, linkage_matrix)
        assert result is not None
        assert isinstance(result, dict)

    def test_has_required_keys(self, linkage_matrix):
        # nv
        result = _drive(dendrogram, linkage_matrix)
        assert 'icoord' in result
        assert 'dcoord' in result
        assert 'ivl' in result
        assert 'leaves' in result
        assert 'color_list' in result

    def test_leaves_count(self, linkage_matrix):
        # nv
        result = _drive(dendrogram, linkage_matrix)
        # all 6 leaves present by default
        assert len(result['leaves']) == 6

    def test_wrong_result_fails(self, linkage_matrix):
        # nv
        assert _fails_with_wrong_result(dendrogram, linkage_matrix)

    def test_result_get_leaves(self, linkage_matrix):
        # nv
        result = _drive(dendrogram, linkage_matrix)
        leaves = _drive_result_get(result, 'leaves')
        assert leaves is not None
        assert len(leaves) == 6


# ── TestCophenet ──────────────────────────────────────────────────────────

class TestCophenet:
    @pytest.fixture
    def linkage_matrix(self):
        from scipy.cluster.hierarchy import linkage
        return linkage(_POINTS, method='ward')

    def test_returns_distance_array(self, linkage_matrix):
        # cophenet(Z, RESULT) → condensed cophenetic distance array
        # nv
        d = _drive(cophenet, linkage_matrix)
        assert d is not None
        import numpy as np
        assert isinstance(d, np.ndarray)
        # 6 points → n*(n-1)/2 = 15 pairwise distances
        assert len(d) == 15

    def test_distances_non_negative(self, linkage_matrix):
        # nv
        d = _drive(cophenet, linkage_matrix)
        assert np.all(d >= 0)

    def test_with_y_returns_dict(self, linkage_matrix):
        # nv
        from scipy.spatial.distance import pdist
        y = pdist(_POINTS)
        result = _drive(cophenet, linkage_matrix, y)
        assert result is not None
        assert isinstance(result, dict)
        assert 'c' in result
        assert 'd' in result

    def test_with_y_high_correlation(self, linkage_matrix):
        # nv
        from scipy.spatial.distance import pdist
        y = pdist(_POINTS)
        result = _drive(cophenet, linkage_matrix, y)
        # clear two-cluster structure should have high cophenetic correlation
        assert result['c'] > 0.9

    def test_with_y_d_matches_no_y(self, linkage_matrix):
        # nv
        from scipy.spatial.distance import pdist
        y = pdist(_POINTS)
        result = _drive(cophenet, linkage_matrix, y)
        d_standalone = _drive(cophenet, linkage_matrix)
        assert np.allclose(result['d'], d_standalone)

    def test_wrong_result_fails(self, linkage_matrix):
        # nv
        assert _fails_with_wrong_result(cophenet, linkage_matrix)


# ── TestInconsistent ──────────────────────────────────────────────────────

class TestInconsistent:
    @pytest.fixture
    def linkage_matrix(self):
        from scipy.cluster.hierarchy import linkage
        return linkage(_POINTS, method='ward')

    def test_returns_array(self, linkage_matrix):
        # nv
        result = _drive(inconsistent, linkage_matrix)
        assert result is not None
        assert result.shape == (5, 4)  # (n-1) x 4

    def test_with_depth(self, linkage_matrix):
        # nv
        result = _drive(inconsistent, linkage_matrix, 3)
        assert result is not None
        assert result.shape == (5, 4)

    def test_values_are_numeric(self, linkage_matrix):
        # nv
        result = _drive(inconsistent, linkage_matrix)
        assert np.all(np.isfinite(result))

    def test_wrong_result_fails(self, linkage_matrix):
        # nv
        assert _fails_with_wrong_result(inconsistent, linkage_matrix)


# ── TestKMeans2 ───────────────────────────────────────────────────────────

class TestKMeans2:
    def test_returns_dict(self):
        # nv
        result = _drive(k_means2, _POINTS, 2)
        assert result is not None
        assert isinstance(result, dict)
        assert 'centroid' in result
        assert 'label' in result

    def test_correct_cluster_count(self):
        # nv
        result = _drive(k_means2, _POINTS, 2)
        assert result['centroid'].shape == (2, 2)
        assert len(result['label']) == 6

    def test_with_iterations(self):
        # nv
        result = _drive(k_means2, _POINTS, 2, 20)
        assert result is not None

    def test_with_seed(self):
        # nv
        result = _drive(k_means2, _POINTS, 2, 10, 42)
        assert result is not None
        assert 'centroid' in result

    def test_result_get_centroid(self):
        # nv
        result = _drive(k_means2, _POINTS, 2)
        centroid = _drive_result_get(result, 'centroid')
        assert centroid is not None
        assert centroid.shape == (2, 2)

    def test_result_get_label(self):
        # nv
        result = _drive(k_means2, _POINTS, 2)
        label = _drive_result_get(result, 'label')
        assert label is not None
        assert len(label) == 6

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(k_means2, _POINTS, 2)


# ── TestKMeans ────────────────────────────────────────────────────────────

class TestKMeans:
    def test_returns_dict(self):
        # nv
        result = _drive(k_means, _POINTS, 2)
        assert result is not None
        assert isinstance(result, dict)
        assert 'codebook' in result
        assert 'distortion' in result

    def test_correct_codebook_shape(self):
        # nv
        result = _drive(k_means, _POINTS, 2)
        assert result['codebook'].shape == (2, 2)

    def test_distortion_is_float(self):
        # nv
        result = _drive(k_means, _POINTS, 2)
        assert isinstance(result['distortion'], float)
        assert result['distortion'] >= 0.0

    def test_with_iterations(self):
        # nv
        result = _drive(k_means, _POINTS, 2, 20)
        assert result is not None

    def test_result_get_codebook(self):
        # nv
        result = _drive(k_means, _POINTS, 2)
        codebook = _drive_result_get(result, 'codebook')
        assert codebook is not None
        assert codebook.shape == (2, 2)

    def test_result_get_distortion(self):
        # nv
        result = _drive(k_means, _POINTS, 2)
        distortion = _drive_result_get(result, 'distortion')
        assert distortion is not None
        assert distortion >= 0.0

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(k_means, _POINTS, 2)


# ── TestVectorQuantize ────────────────────────────────────────────────────

class TestVectorQuantize:
    @pytest.fixture
    def codebook(self):
        result = _drive(k_means, _POINTS, 2)
        return result['codebook']

    def test_returns_dict(self, codebook):
        # nv
        result = _drive(vector_quantize, _POINTS, codebook)
        assert result is not None
        assert isinstance(result, dict)
        assert 'code' in result
        assert 'dist' in result

    def test_code_shape(self, codebook):
        # nv
        result = _drive(vector_quantize, _POINTS, codebook)
        assert len(result['code']) == 6

    def test_dist_shape(self, codebook):
        # nv
        result = _drive(vector_quantize, _POINTS, codebook)
        assert len(result['dist']) == 6

    def test_dist_non_negative(self, codebook):
        # nv
        result = _drive(vector_quantize, _POINTS, codebook)
        assert np.all(result['dist'] >= 0)

    def test_result_get_code(self, codebook):
        # nv
        result = _drive(vector_quantize, _POINTS, codebook)
        code = _drive_result_get(result, 'code')
        assert code is not None
        assert len(code) == 6

    def test_wrong_result_fails(self, codebook):
        # nv
        assert _fails_with_wrong_result(vector_quantize, _POINTS, codebook)


# ── TestWhiten ────────────────────────────────────────────────────────────

class TestWhiten:
    def test_returns_array(self):
        # nv
        result = _drive(whiten, _POINTS)
        assert result is not None
        assert result.shape == _POINTS.shape

    def test_unit_variance_columns(self):
        # nv
        result = _drive(whiten, _POINTS)
        # each column should have standard deviation ~1.0
        std = np.std(result, axis=0)
        assert np.allclose(std, 1.0, atol=1e-10)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(whiten, _POINTS)


# ── TestResultGet ─────────────────────────────────────────────────────────

class TestResultGet:
    def test_extracts_known_key(self):
        # nv
        d = {'centroid': np.array([[1.0, 1.0]]), 'label': np.array([0])}
        val = _drive_result_get(d, 'centroid')
        assert val is not None
        assert np.allclose(val, [[1.0, 1.0]])

    def test_missing_key_fails(self):
        # nv
        d = {'centroid': np.array([[1.0, 1.0]])}
        val = _drive_result_get(d, 'nonexistent')
        assert val is None

    def test_non_string_field_fails(self):
        # nv
        d = {'centroid': np.array([[1.0, 1.0]])}
        value = Var()
        dispatch = result_get._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, d, 42, value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── Fixture integration ───────────────────────────────────────────────────

import os
from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}{SEAM_SUFFIX}")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestClausalFixture:
    """Run Test predicates from tests/fixtures/scipy_cluster_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_cluster_tests")

    @pytest.mark.parametrize("name", [
        "linkage ward produces matrix",
        "flat cluster two groups",
        "kmeans2 centroid count",
        "kmeans codebook shape",
        "vector quantize assigns codes",
        "whiten unit variance",
        "cophenet with y high correlation",
        "inconsistent array shape",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
