"""Phase 10 — Video I/O integration tests."""

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


class TestOpencvPhase10Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase10_video")

    @pytest.mark.parametrize("name", [
        # Capture open / close / properties
        "make_video_capture on tiny.mp4 returns an integer handle",
        "make_video_capture fails on missing file",
        "is_open succeeds for an open capture",
        "is_open fails after release",
        "video_property frame_count is 2",
        "video_property fps is positive",
        "video_property width is 120",
        "video_property unknown name fails",
        # Frame iteration
        "read_frame returns a single frame",
        "video_frame enumerates all frames",
        "video_frame yields frames with shape (H, W, 3)",
        "after video_frame exhausts, read_frame fails",
        "explicit rewind via video_property_set allows re-reading",
        "video_property_set returns the same handle",
        # Registry
        "video_prop_name lookup frame_count",
        "video_prop_name enumerates many properties",
        "video_prop_name unknown name fails",
        # fourcc
        "fourcc forward: chars to int",
        "fourcc backward: int to chars",
        "fourcc round-trip",
        "fourcc rejects wrong-length string",
        # Write + read back
        "write a 2-frame video then read it back",
        "make_video_writer with is_color flag",
        "make_video_writer with grayscale (is_color False)",
        # Lifecycle
        "free releases a capture handle",
        "release is idempotent — second call fails cleanly",
        "free on a writer also works",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), \
            f"Test({name!r}) failed"
