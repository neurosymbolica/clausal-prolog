"""Phase 8 — Object detection integration tests."""

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


class TestOpencvPhase8Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase8_objdetect")

    @pytest.mark.parametrize("name", [
        # Cascade classifier
        "make_cascade_classifier on bundled face XML returns a handle",
        "make_cascade_classifier fails on missing XML",
        "detect_multi_scale on scene returns a list (possibly empty)",
        "detect_multi_scale with scale_factor",
        "detect_multi_scale with scale_factor and min_neighbors",
        "detect_multi_scale with scale_factor, min_neighbors, min_size",
        # Registry
        "haar_cascade_path lookup face",
        "haar_cascade_path enumerates several cascades",
        "haar_cascade_path unknown name fails",
        "all registered cascades exist on disk",
        # HOG
        "make_hog default",
        "make_hog with custom opts",
        "hog_default_people_detector returns a vector",
        "hog_compute on properly-sized image yields a descriptor",
        # State threading via hog_set_svm_detector
        "hog_set_svm_detector returns a NEW handle",
        "hog_detect on SVM-installed HOG returns a list",
        "hog_detect with opts on SVM-installed HOG",
        "original HOG handle remains usable after set_svm_detector",
        # Lifecycle
        "free releases a cascade handle",
        "free releases a HOG handle",
        "free on the SVM-installed HOG does not invalidate the original",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod), \
            f"Test({name!r}) failed"
