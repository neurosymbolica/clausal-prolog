"""Phase 9 — Camera calibration and 3D geometry integration tests."""

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


class TestOpencvPhase9Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase9_calib3d")

    @pytest.mark.parametrize("name", [
        # Homography
        "find_homography on 4 corner correspondences returns 3x3",
        "find_homography with explicit RANSAC method",
        "find_homography_mask returns H and inlier mask",
        "find_homography_mask with explicit RANSAC threshold",
        # Fundamental / essential
        "find_fundamental_mat from 8 point pairs",
        "find_essential_mat with intrinsics K",
        # Rodrigues
        "rodrigues forward yields a 3x3 matrix",
        "rodrigues backward (-RVEC, +RMAT)",
        "rodrigues round-trip is identity",
        # PnP
        "solve_pnp from coplanar points",
        "solve_pnp with explicit flags",
        "solve_pnp_ransac returns tagged pnp_ransac result",
        # Calibration
        "calibrate_camera from two synthetic views",
        "calibrate_camera tagged result has matching list lengths",
        # Projection / undistortion
        "project_points returns image points and jacobian",
        "undistort with zero distortion is identity-ish",
        "undistort with new camera matrix",
        "init_undistort_rectify_map yields two maps",
        # Chessboard / corner refinement
        "find_chessboard_corners finds 7x6 grid on synthetic board",
        "find_chessboard_corners with flags",
        "find_chessboard_corners returns empty list when no board",
        "corner_sub_pix refines detected corners",
        "corner_sub_pix with explicit criteria",
        # recover_pose
        "recover_pose from essential matrix returns tagged pose result",
        "recover_pose pose fields have expected shapes",
        # Decompose / recover
        "decompose_homography_mat returns a non-empty solution list",
        # DFT
        "dft forward yields a complex-channel output",
        "dft forward then inverse round-trips",
        "dft with explicit forward-only flags",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), \
            f"Test({name!r}) failed"
