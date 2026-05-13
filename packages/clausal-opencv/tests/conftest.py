"""Shared pytest setup for clausal-opencv tests.

Copies tests/fixtures/*.png into /tmp before the test session so that
``.clausal`` files can reference fixed absolute paths (``/tmp/...``)
rather than computing a path relative to the test file.
"""

from __future__ import annotations

import os
import shutil

import pytest


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Pairs of (source filename in tests/fixtures, destination filename in /tmp)
_TMP_FIXTURES = [
    ("tiny_rgb.png",  "clausal_opencv_tiny_rgb.png"),
    ("tiny_gray.png", "clausal_opencv_tiny_gray.png"),
    ("shapes.png",    "clausal_opencv_shapes.png"),
    ("scene.png",     "clausal_opencv_scene.png"),
    ("tiny.mp4",      "clausal_opencv_tiny.mp4"),
    ("checkerboard.png", "clausal_opencv_checkerboard.png"),
]


@pytest.fixture(scope="session", autouse=True)
def _seed_tmp_fixtures():
    for src_name, dst_name in _TMP_FIXTURES:
        src = os.path.join(_FIXTURE_DIR, src_name)
        if not os.path.exists(src):
            continue
        dst = os.path.join("/tmp", dst_name)
        shutil.copyfile(src, dst)
    yield
