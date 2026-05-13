"""Phase 5 — Geometric transformation integration tests."""

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


class TestOpencvPhase5Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase5_geometric")

    @pytest.mark.parametrize("name", [
        # resize
        "resize to explicit [W, H]",
        "resize with explicit interpolation",
        "resize_factor halves both dims",
        "resize_factor with nearest interpolation",
        # rotate
        "rotate 90 clockwise then 90 counter-clockwise is identity",
        "rotate 180 twice is identity",
        "rotate 90 clockwise swaps W and H for color image",
        # get_rotation_matrix_2d
        "get_rotation_matrix_2d returns a 2x3 matrix",
        "get_rotation_matrix_2d with zero angle and scale 1 is identity-affine",
        # affine_inverse (bidirectional)
        "affine_inverse forward then forward is identity (self-inverse)",
        "affine_inverse backward mode (-M, +M_INV)",
        # warp_affine
        "warp_affine identity-matrix preserves the image",
        "warp_affine with explicit interpolation flag",
        "warp_affine with border mode",
        "warp_affine with border value",
        # warp_perspective
        "warp_perspective with 3x3 identity is identity",
        "warp_perspective with flags arg",
        # transform builders
        "get_affine_transform from 3 point pairs",
        "get_perspective_transform from 4 corner pairs",
        # remap
        "remap with identity maps returns input",
        "remap with border_mode arg",
        # copy_make_border
        "copy_make_border replicate adds 2-pixel margin",
        "copy_make_border constant with explicit value",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), \
            f"Test({name!r}) failed"
