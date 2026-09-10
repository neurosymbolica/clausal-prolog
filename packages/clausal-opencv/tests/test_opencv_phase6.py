"""Phase 6 — Drawing integration tests."""

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


class TestOpencvPhase6Fixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("opencv_phase6_drawing")

    @pytest.mark.parametrize("name", [
        # Shape preservation + arity variants
        "line arity 5",
        "line arity 6 with thickness",
        "line arity 7 with line_aa",
        "arrowed_line preserves shape",
        "rectangle preserves shape",
        "rectangle filled",
        "circle preserves shape",
        "circle filled with FILLED thickness",
        "ellipse with axes",
        "ellipse with thickness",
        "polylines closed square",
        "polylines with thickness",
        "fill_poly fills a polygon",
        "put_text preserves shape",
        "put_text with line_aa",
        "marker default arity 4",
        "marker with marker_type",
        "marker with size and thickness",
        # No-mutation invariant
        "no-mutation for line",
        "no-mutation for arrowed_line",
        "no-mutation for rectangle",
        "no-mutation for circle",
        "no-mutation for ellipse",
        "no-mutation for polylines",
        "no-mutation for fill_poly",
        "no-mutation for put_text",
        "no-mutation for marker",
        # Drawing happens on output
        "line actually draws on the output canvas",
        "rectangle filled actually changes pixels",
        # draw_contours with real contours
        "draw_contours with all contours preserves shape",
        "draw_contours with specific index and thickness",
        "draw_contours does not mutate source",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), \
            f"Test({name!r}) failed"
