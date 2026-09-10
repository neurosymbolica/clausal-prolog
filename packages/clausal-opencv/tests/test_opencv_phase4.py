"""Phase 4 — Thresholding and contours integration tests."""

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


class TestOpencvPhase4Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase4_thresh_contours")

    @pytest.mark.parametrize("name", [
        # Thresholding
        "threshold binary preserves the literal level",
        "threshold otsu returns the chosen level",
        "threshold binary_inv flips foreground/background",
        "adaptive_threshold preserves shape",
        "adaptive_threshold gaussian variant",
        # find_contours
        "find_contours on a thresholded shape returns one external contour",
        "find_contours retr_tree gives same one contour",
        "find_contours retr_list returns hierarchy",
        "find_contours with offset preserves contour count",
        # contour enumeration
        "contour/2 enumerates each contour",
        # measurements
        "contour_area for known rectangle approx matches 12x16",
        "contour_area oriented variant",
        "contour_perimeter closed > 0",
        # bounding shapes
        "bounding_rect decomposes to rect/4",
        "min_enclosing_circle has positive radius",
        "min_area_rect decomposes to rotated_rect",
        # hull
        "convex_hull area >= original contour area",
        "convex_hull clockwise variant",
        # approx
        "approx_poly_dp reduces or matches vertex count",
        # point_polygon_test
        "point inside the rectangle has positive distance",
        "point outside has negative distance",
        "point_polygon_test without measure_dist returns +1/0/-1",
        # moments
        "moments m00 equals contour_area on the same contour",
        "moments of binary image returns moments_t term",
        "moments_field for nu20 returns a float",
        "moments_field unknown name fails",
        # registry
        "threshold_type registry lookup otsu",
        "threshold_type findall enumerates all 7",
        "threshold_type unknown name fails",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), \
            f"Test({name!r}) failed"
