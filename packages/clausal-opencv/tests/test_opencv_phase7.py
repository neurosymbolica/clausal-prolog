"""Phase 7 — Features and matching integration tests."""

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


class TestOpencvPhase7Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase7_features")

    @pytest.mark.parametrize("name", [
        # Detector construction
        "make_orb default returns an integer handle",
        "make_orb with opts",
        "make_sift default",
        "make_sift with opts",
        "make_akaze default",
        "make_kaze default",
        "make_brisk default",
        "make_fast default",
        "make_fast with threshold opt",
        "each detector gets a distinct handle",
        # Detection / description
        "orb detect on scene yields keypoints",
        "orb detect_and_compute yields keypoints and matching descriptors",
        "orb detect_and_compute with full-image mask",
        "compute after detect yields descriptors",
        "sift detect yields keypoints",
        "sift descriptors are 128-dim float32",
        "akaze descriptors round-trip",
        "fast detect returns keypoints (no descriptors)",
        # keypoint enum / decompose / construct
        "keypoint/2 nondet enumeration",
        "keypoint/7 decomposes a single keypoint",
        "keypoint/7 constructs a new keypoint from fields",
        # BF matcher
        "make_bf_matcher default",
        "make_bf_matcher with norm type",
        "make_bf_matcher with norm and cross-check",
        "bf matcher self-match (orb descriptors)",
        "knn_match yields k candidates per query",
        "radius_match returns matches within radius",
        # match_pair / dmatch
        "match_pair enumerates each match",
        "dmatch decomposes into 4 integers/float",
        "self-match distances are all zero",
        # FLANN
        "flann matcher with sift descriptors",
        "flann with explicit index/search params",
        # Handle lifecycle
        "free releases an ORB handle",
        "free on unknown handle fails",
        # Drawing (from Phase 6)
        "draw_keypoints overlays markers",
        "draw_keypoints with flags",
        "draw_matches builds a wide composite",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), \
            f"Test({name!r}) failed"
