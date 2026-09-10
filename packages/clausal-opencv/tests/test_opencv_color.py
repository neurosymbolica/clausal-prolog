"""Phase 2 — Color conversion integration tests."""

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


class TestOpencvPhase2Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase2_color")

    @pytest.mark.parametrize("name", [
        # cvt_color by integer code
        "bgr to grayscale by code",
        "gray to bgr replicates a single channel",
        "gray2bgr produces three equal channels",
        "bgr2rgb then rgb2bgr is identity",
        # cvt_color_named
        "bgr to grayscale by name",
        "named matches the int-code result",
        "cvt_color_named fails on unknown code",
        # color_code registry
        "color_code lookup name to int",
        "color_code reverse lookup int to name",
        "color_code findall enumerates many names",
        "color_code unknown name fails",
        # channels
        "channels split then merge is identity",
        "channels of grayscale yields single-element list",
        "channels forward shape preserved per channel",
        # HSV roundtrip
        "HSV roundtrip is approximately identity",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), \
            f"Test({name!r}) failed"
