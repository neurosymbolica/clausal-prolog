"""Phase 3 — Filtering and morphology integration tests."""

from __future__ import annotations

import os
import pytest

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


class TestOpencvPhase3Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase3_filtering")

    @pytest.mark.parametrize("name", [
        # Smoothing
        "gaussian_blur with 3x3 kernel preserves shape",
        "gaussian_blur with explicit sigma",
        "gaussian_blur with separate sigma_x, sigma_y",
        "median_blur with ksize 3",
        "box_filter preserves shape",
        "bilateral_filter preserves shape and channels",
        # Convolution
        "filter_2d with identity kernel returns input unchanged",
        "sep_filter_2d with two 1-element kernels preserves shape",
        # Edge detection
        "sobel dx=1, dy=0 preserves spatial shape",
        "sobel with explicit ksize",
        "scharr dx=1, dy=0",
        "laplacian default ksize",
        "laplacian explicit ksize",
        "canny output is single-channel uint8",
        "canny with explicit aperture size",
        # Morphology
        "get_structuring_element rect shape",
        "get_structuring_element ellipse shape",
        "get_structuring_element cross with explicit anchor",
        "erode with rect kernel preserves shape",
        "dilate with rect kernel preserves shape",
        "erode with iterations=2 preserves shape",
        "morphology_ex open equals erode-then-dilate",
        "morphology_ex close equals dilate-then-erode",
        "morphology_ex with iterations",
        # Pyramids
        "pyr_down halves the dimensions",
        "pyr_up doubles the dimensions",
        "pyr_down with explicit dstsize",
        # Registries
        "interpolation registry lookup cubic",
        "interpolation reverse lookup",
        "interpolation findall enumerates all 5",
        "border_type registry lookup reflect",
        "border_type findall enumerates 6",
        "morph_op registry lookup open",
        "morph_op findall enumerates all 8",
        "morph_shape registry lookup rect",
        "morph_shape findall enumerates all 3",
        "morph_shape unknown name fails",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), \
            f"Test({name!r}) failed"
