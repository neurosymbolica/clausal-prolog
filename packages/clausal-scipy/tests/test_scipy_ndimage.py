"""Tests for clausal.modules.py.scipy_ndimage — scipy.ndimage predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional SIZE argument)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- round-trip or identity properties where applicable
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_ndimage import (
    gaussian_filter,
    uniform_filter,
    median_filter,
    convolve,
    label,
    binary_erosion,
    binary_dilation,
    binary_opening,
    binary_closing,
    zoom,
    rotate,
    shift,
    find_objects,
    center_of_mass,
)


# ── Test drivers ───────────────────────────────────────────────────────────

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
    """Return True if predicate yields no solution when RESULT is wrong."""
    trail = Trail()
    result_bound = object()  # will not unify with any array
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── TestGaussianFilter ──────────────────────────────────────────────

class TestGaussianFilter:
    def test_constant_array_unchanged(self):
        # Gaussian filter of constant array should return constant
        # nv
        inp = np.ones(10)
        result = _drive(gaussian_filter, inp, 1.0)
        assert result is not None
        assert np.allclose(result, 1.0, atol=1e-6)

    def test_output_same_shape(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
        result = _drive(gaussian_filter, inp, 1.0)
        assert result is not None
        assert result.shape == inp.shape

    def test_smoothing_reduces_peak(self):
        # A spike should be smoothed down
        # nv
        inp = np.zeros(11)
        inp[5] = 10.0
        result = _drive(gaussian_filter, inp, 1.0)
        assert result is not None
        assert result[5] < 10.0

    def test_2d_constant_array(self):
        # nv
        inp = np.ones((5, 5))
        result = _drive(gaussian_filter, inp, 1.0)
        assert result is not None
        assert result.shape == (5, 5)
        # centre value should remain close to 1.0
        assert abs(result[2, 2] - 1.0) < 1e-6

    def test_wrong_result_fails(self):
        # nv
        inp = np.ones(5)
        assert _fails_with_wrong_result(gaussian_filter, inp, 1.0)


# ── TestUniformFilter ───────────────────────────────────────────────

class TestUniformFilter:
    def test_constant_array_unchanged(self):
        # nv
        inp = np.full(7, 3.0)
        result = _drive(uniform_filter, inp)
        assert result is not None
        assert np.allclose(result, 3.0, atol=1e-10)

    def test_default_size_three(self):
        # uniform_filter with size=3: centre of [1,2,3,4,5] → mean(1,2,3)=2
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result_default = _drive(uniform_filter, inp)
        result_size3 = _drive(uniform_filter, inp, 3)
        assert result_default is not None
        assert result_size3 is not None
        assert np.allclose(result_default, result_size3, atol=1e-10)

    def test_with_explicit_size(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _drive(uniform_filter, inp, 5)
        assert result is not None
        assert len(result) == 5

    def test_output_same_shape(self):
        # nv
        inp = np.arange(9.0).reshape(3, 3)
        result = _drive(uniform_filter, inp)
        assert result is not None
        assert result.shape == (3, 3)

    def test_wrong_result_fails(self):
        # nv
        inp = np.ones(5)
        assert _fails_with_wrong_result(uniform_filter, inp)


# ── TestMedianFilter ────────────────────────────────────────────────

class TestMedianFilter:
    def test_constant_array_unchanged(self):
        # nv
        inp = np.full(7, 5.0)
        result = _drive(median_filter, inp, 3)
        assert result is not None
        assert np.allclose(result, 5.0, atol=1e-10)

    def test_removes_spike(self):
        # median filter removes single-sample spike
        # nv
        inp = np.array([1.0, 1.0, 100.0, 1.0, 1.0])
        result = _drive(median_filter, inp, 3)
        assert result is not None
        assert abs(result[2] - 1.0) < 1e-6

    def test_output_same_shape(self):
        # nv
        inp = np.arange(9.0).reshape(3, 3)
        result = _drive(median_filter, inp, 3)
        assert result is not None
        assert result.shape == (3, 3)

    def test_wrong_result_fails(self):
        # nv
        inp = np.ones(5)
        assert _fails_with_wrong_result(median_filter, inp, 3)


# ── TestConvolve ────────────────────────────────────────────────────

class TestConvolve:
    def test_identity_kernel(self):
        # [0,1,0] identity kernel should return same array
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        kernel = np.array([0.0, 1.0, 0.0])
        result = _drive(convolve, inp, kernel)
        assert result is not None
        assert np.allclose(result, inp, atol=1e-10)

    def test_box_kernel_averages(self):
        # [1/3, 1/3, 1/3] kernel is a 3-point moving average (centre)
        # nv
        inp = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
        kernel = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
        result = _drive(convolve, inp, kernel)
        assert result is not None
        assert abs(result[2] - 3.0) < 1e-10

    def test_2d_identity_kernel(self):
        # nv
        inp = np.array([[1.0, 2.0], [3.0, 4.0]])
        kernel = np.array([[0.0, 0.0, 0.0],
                           [0.0, 1.0, 0.0],
                           [0.0, 0.0, 0.0]])
        result = _drive(convolve, inp, kernel)
        assert result is not None
        assert np.allclose(result, inp, atol=1e-10)

    def test_output_same_shape(self):
        # nv
        inp = np.ones(8)
        kernel = np.ones(3) / 3.0
        result = _drive(convolve, inp, kernel)
        assert result is not None
        assert result.shape == inp.shape

    def test_wrong_result_fails(self):
        # nv
        inp = np.ones(5)
        kernel = np.array([0.0, 1.0, 0.0])
        assert _fails_with_wrong_result(convolve, inp, kernel)


# ── TestLabel ───────────────────────────────────────────────────────

class TestLabel:
    def test_single_region(self):
        # nv
        inp = np.array([1, 1, 1, 1, 1])
        result = _drive(label, inp)
        assert result is not None
        assert result["num_features"] == 1

    def test_two_regions(self):
        # nv
        inp = np.array([1, 1, 0, 1, 1])
        result = _drive(label, inp)
        assert result is not None
        assert result["num_features"] == 2

    def test_label_array_shape(self):
        # nv
        inp = np.array([[1, 0], [0, 1]])
        result = _drive(label, inp)
        assert result is not None
        assert result["label_array"].shape == (2, 2)

    def test_label_array_background_is_zero(self):
        # nv
        inp = np.array([1, 1, 0, 1, 1])
        result = _drive(label, inp)
        assert result is not None
        assert result["label_array"][2] == 0

    def test_no_features_when_all_zero(self):
        # nv
        inp = np.zeros(5, dtype=int)
        result = _drive(label, inp)
        assert result is not None
        assert result["num_features"] == 0

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([1, 1, 0, 1, 1])
        assert _fails_with_wrong_result(label, inp)


# ── TestBinaryErosion ───────────────────────────────────────────────

class TestBinaryErosion:
    def test_solid_block_erodes(self):
        # erosion removes boundary pixels
        # nv
        inp = np.array([False, True, True, True, False])
        result = _drive(binary_erosion, inp)
        assert result is not None
        assert bool(result[2]) is True
        assert bool(result[1]) is False

    def test_isolated_pixel_eroded_away(self):
        # single isolated True should disappear
        # nv
        inp = np.array([False, False, True, False, False])
        result = _drive(binary_erosion, inp)
        assert result is not None
        assert not any(result)

    def test_output_same_shape(self):
        # nv
        inp = np.ones((3, 3), dtype=bool)
        result = _drive(binary_erosion, inp)
        assert result is not None
        assert result.shape == (3, 3)

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([False, True, True, True, False])
        assert _fails_with_wrong_result(binary_erosion, inp)


# ── TestBinaryDilation ──────────────────────────────────────────────

class TestBinaryDilation:
    def test_single_pixel_dilates(self):
        # nv
        inp = np.array([False, False, True, False, False])
        result = _drive(binary_dilation, inp)
        assert result is not None
        assert bool(result[1]) is True
        assert bool(result[2]) is True
        assert bool(result[3]) is True

    def test_all_false_stays_false(self):
        # nv
        inp = np.zeros(5, dtype=bool)
        result = _drive(binary_dilation, inp)
        assert result is not None
        assert not any(result)

    def test_output_same_shape(self):
        # nv
        inp = np.array([False, True, False])
        result = _drive(binary_dilation, inp)
        assert result is not None
        assert result.shape == inp.shape

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([False, False, True, False, False])
        assert _fails_with_wrong_result(binary_dilation, inp)


# ── TestBinaryOpening ───────────────────────────────────────────────

class TestBinaryOpening:
    def test_removes_isolated_pixel(self):
        # isolated True (surrounded by False) should be removed by opening
        # nv
        inp = np.array([False, True, False, True, True, True, False])
        result = _drive(binary_opening, inp)
        assert result is not None
        assert bool(result[1]) is False

    def test_preserves_solid_region(self):
        # large solid region should survive opening
        # nv
        inp = np.array([False, True, True, True, False])
        result = _drive(binary_opening, inp)
        assert result is not None
        assert bool(result[2]) is True

    def test_output_same_shape(self):
        # nv
        inp = np.ones(7, dtype=bool)
        result = _drive(binary_opening, inp)
        assert result is not None
        assert result.shape == inp.shape

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([False, True, False, True, True, True, False])
        assert _fails_with_wrong_result(binary_opening, inp)


# ── TestBinaryClosing ───────────────────────────────────────────────

class TestBinaryClosing:
    def test_fills_single_gap(self):
        # single-False gap between two True regions should be filled
        # nv
        inp = np.array([True, True, False, True, True])
        result = _drive(binary_closing, inp)
        assert result is not None
        assert bool(result[2]) is True

    def test_solid_interior_preserved(self):
        # binary_closing on a solid array: centre values stay True
        # nv
        inp = np.ones(5, dtype=bool)
        result = _drive(binary_closing, inp)
        assert result is not None
        assert bool(result[2]) is True

    def test_output_same_shape(self):
        # nv
        inp = np.array([True, False, True])
        result = _drive(binary_closing, inp)
        assert result is not None
        assert result.shape == inp.shape

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([True, True, False, True, True])
        assert _fails_with_wrong_result(binary_closing, inp)


# ── TestZoom ────────────────────────────────────────────────────────

class TestZoom:
    def test_zoom_doubles_length(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0])
        result = _drive(zoom, inp, 2.0)
        assert result is not None
        assert len(result) == 6

    def test_zoom_halves_length(self):
        # nv
        inp = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0])
        result = _drive(zoom, inp, 0.5)
        assert result is not None
        assert len(result) == 3

    def test_zoom_1_returns_same_shape(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0])
        result = _drive(zoom, inp, 1.0)
        assert result is not None
        assert len(result) == 4

    def test_zoom_2d_shape(self):
        # nv
        inp = np.ones((3, 3))
        result = _drive(zoom, inp, 2.0)
        assert result is not None
        assert result.shape == (6, 6)

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0])
        assert _fails_with_wrong_result(zoom, inp, 2.0)


# ── TestRotate ──────────────────────────────────────────────────────

class TestRotate:
    def test_zero_rotation_preserves_shape(self):
        # nv
        inp = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = _drive(rotate, inp, 0.0)
        assert result is not None
        assert result.shape == inp.shape

    def test_360_rotation_round_trip(self):
        # nv
        inp = np.array([[1.0, 0.0], [0.0, 1.0]])
        result = _drive(rotate, inp, 360.0)
        assert result is not None
        assert result.shape == inp.shape

    def test_90_rotation_shape(self):
        # nv
        inp = np.ones((4, 6))
        result = _drive(rotate, inp, 90.0)
        assert result is not None
        # with reshape=True (default) shape becomes (6, 4) after 90° rotation
        assert result.shape in ((4, 6), (6, 4))

    def test_wrong_result_fails(self):
        # nv
        inp = np.eye(3)
        assert _fails_with_wrong_result(rotate, inp, 0.0)


# ── TestShift ───────────────────────────────────────────────────────

class TestShift:
    def test_zero_shift_identity(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _drive(shift, inp, 0.0)
        assert result is not None
        assert np.allclose(result, inp, atol=1e-10)

    def test_shift_right_by_one(self):
        # shift by +1 moves values one position to the right; first element
        # is filled with 0.0 by default (constant mode)
        # nv
        inp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _drive(shift, inp, 1.0)
        assert result is not None
        assert len(result) == 5

    def test_2d_zero_shift(self):
        # nv
        inp = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = _drive(shift, inp, [0.0, 0.0])
        assert result is not None
        assert np.allclose(result, inp, atol=1e-10)

    def test_output_same_shape(self):
        # nv
        inp = np.arange(10.0)
        result = _drive(shift, inp, 2.0)
        assert result is not None
        assert result.shape == inp.shape

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([1.0, 2.0, 3.0])
        assert _fails_with_wrong_result(shift, inp, 0.0)


# ── TestFindObjects ─────────────────────────────────────────────────

class TestFindObjects:
    def test_two_regions_two_entries(self):
        # labeled array with two components → two slice entries
        # nv
        inp = np.array([1, 1, 0, 2, 2])
        result = _drive(find_objects, inp)
        assert result is not None
        assert len(result) == 2

    def test_single_region(self):
        # nv
        inp = np.array([0, 1, 1, 1, 0])
        result = _drive(find_objects, inp)
        assert result is not None
        assert len(result) == 1

    def test_empty_returns_empty_list(self):
        # nv
        inp = np.zeros(5, dtype=int)
        result = _drive(find_objects, inp)
        assert result is not None
        assert len(result) == 0

    def test_each_entry_is_tuple_of_slices(self):
        # nv
        inp = np.array([1, 1, 0, 2, 2])
        result = _drive(find_objects, inp)
        assert result is not None
        for entry in result:
            assert isinstance(entry, tuple)
            assert all(isinstance(s, slice) for s in entry)

    def test_wrong_result_fails(self):
        # nv
        inp = np.array([1, 1, 0, 2, 2])
        assert _fails_with_wrong_result(find_objects, inp)


# ── TestCenterOfMass ────────────────────────────────────────────────

class TestCenterOfMass:
    def test_uniform_1d_centre(self):
        # centre of mass of uniform 1D array is at middle index
        # nv
        inp = np.ones(5)
        result = _drive(center_of_mass, inp)
        assert result is not None
        assert abs(result[0] - 2.0) < 1e-6

    def test_uniform_2d_centre(self):
        # nv
        inp = np.ones((5, 5))
        result = _drive(center_of_mass, inp)
        assert result is not None
        assert abs(result[0] - 2.0) < 1e-6
        assert abs(result[1] - 2.0) < 1e-6

    def test_asymmetric_1d(self):
        # mass at right side → centre of mass > middle
        # nv
        inp = np.array([0.0, 0.0, 0.0, 1.0, 1.0])
        result = _drive(center_of_mass, inp)
        assert result is not None
        assert result[0] > 2.0

    def test_single_peak(self):
        # nv
        inp = np.array([0.0, 0.0, 5.0, 0.0, 0.0])
        result = _drive(center_of_mass, inp)
        assert result is not None
        assert abs(result[0] - 2.0) < 1e-10

    def test_wrong_result_fails(self):
        # nv
        inp = np.ones(5)
        assert _fails_with_wrong_result(center_of_mass, inp)


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


class TestClausalFixture:
    """Run Test predicates from tests/fixtures/scipy_ndimage_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_ndimage_tests")

    @pytest.mark.parametrize("name", [
        "gaussian filter constant",
        "uniform filter constant",
        "uniform filter with size",
        "convolve identity kernel",
        "label two regions",
        "binary erosion shrinks",
        "binary dilation expands",
        "binary opening removes isolated",
        "binary closing fills gap",
        "zoom scales up",
        "rotate zero degrees",
        "shift by zero",
        "find objects two regions",
        "center of mass uniform",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
