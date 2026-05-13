"""Tests for clausal.modules.opencv — Phase 1 core, I/O, properties, arithmetic.

Integration tests run .clausal fixture files. Unit tests live in
``test_opencv_infra.py`` and cover the handle registry, lazy import,
and ``__getattr__`` constant export.
"""

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


# ════════════════════════════════════════════════════════════════════════════
# .clausal integration tests — Phase 1
# ════════════════════════════════════════════════════════════════════════════


class TestOpencvPhase1Fixture:
    """Run Test predicates from opencv_phase1_core.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase1_core")

    @pytest.mark.parametrize("name", [
        # imread / shape / properties
        "imread color produces 3-D shape",
        "imread grayscale produces 2-D shape",
        "imread unchanged on rgb fixture is uint8",
        "imread default flag returns color image",
        "shape check mode succeeds with concrete shape",
        "shape check mode fails with wrong shape",
        "size returns [W, H] swapped from shape",
        "element_count matches product of dims",
        "channels_count check mode 3",
        "imread fails on missing file",
        # image_encoded
        "image_encoded forward yields bytes",
        "image_encoded round-trip preserves shape",
        # imwrite
        "imwrite roundtrip png",
        # arithmetic (grayscale for min_max_loc compatibility)
        "absdiff with self is zero on grayscale",
        "add saturates at 255 for uint8 grayscale",
        "subtract self gives zero on grayscale",
        "min(A,A) equals A",
        "max(A,A) equals A",
        # bitwise
        "bitwise_not is involutive on grayscale",
        "bitwise_not on color preserves shape",
        "bitwise_and with self equals self",
        "bitwise_xor with self is zero on grayscale",
        # whole-image transforms
        "flip code 0 vertical is involutive",
        "flip code 1 horizontal is involutive",
        "flip code -1 both axes is involutive",
        "transpose swaps H and W of a color image",
        "transpose of grayscale swaps dims",
        "copy_image produces an equal but independent array",
        # mean
        "mean of grayscale returns 4-tuple with zero in unused channels",
        "mean of color returns 4-tuple",
        # Additional arithmetic / dtype coverage
        "multiply element-wise preserves shape",
        "multiply with scale factor",
        "divide with self is uniform 1",
        "divide with scale",
        "bitwise_or with zero is identity",
        "bitwise_or with mask",
        "dtype query returns numpy dtype",
        "dtype check mode succeeds for uint8 fixture",
        # min_max_loc
        "min_max_loc on uint8 grayscale returns sensible values",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), \
            f"Test({name!r}) failed"
