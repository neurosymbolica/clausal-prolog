"""clausal.modules.py.opencv_draw — Non-mutating OpenCV drawing predicates.

Phase 6 — Drawing.

OpenCV's drawing functions (``cv2.line``, ``cv2.rectangle`` …)
mutate the destination image in place. That breaks Clausal's
relational guarantees: a backtrack point above a draw call would
leave the canvas corrupted.

The wrapper resolves this with **copy-on-write at the predicate
boundary**: each drawing predicate ``copy()``s the source image,
invokes the mutating cv2 function on the copy, and unifies the
copy as RESULT. The original image is never touched.

Cost: one ``ndarray.copy()`` per drawing call. For tight loops over
a single canvas, a user can drop to ``++cv2.line(img, ...)``
directly, but the canonical relational form pays this cost in
exchange for backtracking safety.

Use::

    -import_from(opencv_draw, [
        line, rectangle, circle, ellipse, polylines, fill_poly,
        put_text, marker, draw_contours,
    ])
    -import_from(opencv, [
        line_aa, filled, font_hershey_simplex, marker_cross,
    ])

Predicate catalogue
-------------------
    line(IMG, P1, P2, COLOR, OUT)
    line(IMG, P1, P2, COLOR, THICKNESS, OUT)
    line(IMG, P1, P2, COLOR, THICKNESS, LINE_TYPE, OUT)

    arrowed_line(IMG, P1, P2, COLOR, OUT)            and /6, /7

    rectangle(IMG, PT1, PT2, COLOR, OUT)             and /6, /7
    circle(IMG, CENTER, RADIUS, COLOR, OUT)          and /6, /7
    ellipse(IMG, CENTER, AXES, ANGLE, START, END, COLOR, OUT)         and /9

    polylines(IMG, PTS_LIST, IS_CLOSED, COLOR, OUT)  and /6
    fill_poly(IMG, PTS_LIST, COLOR, OUT)

    put_text(IMG, TEXT, ORIGIN, FONT, SCALE, COLOR, THICKNESS, OUT)   and /9
    marker(IMG, POSITION, COLOR, OUT)                and /6, /7, /8

    draw_contours(IMG, CONTOURS, CONTOUR_IDX, COLOR, OUT)             and /6
    draw_keypoints(IMG, KEYPOINTS, COLOR, OUT)       and /5
    draw_matches(IMG1, KP1, IMG2, KP2, MATCHES, FLAGS, OUT)
"""

from __future__ import annotations

import numpy as _np

from clausal.modules.py._helpers import _pred, _pure
from clausal.modules.py.opencv import _cv


# ── Copy-on-write helper ──────────────────────────────────────────────────


def _draw(call):
    """Wrap a mutating cv2 call: copy src, call on copy, return copy.

    ``call(canvas, *params)`` mutates ``canvas`` in place. After the
    call, ``canvas`` is the result. Pair with ``_pure`` so the inputs
    are deep-deref'd before this fn runs.
    """
    def fn(src, *params):
        canvas = src.copy()
        call(canvas, *params)
        return canvas
    return fn


def _to_int32_poly_list(pts_list):
    """Convert a Clausal list-of-lists-of-pairs to cv2's expected form.

    ``cv2.polylines`` / ``cv2.fillPoly`` want a Python list of
    ``np.ndarray`` with dtype int32 and shape ``(N, 1, 2)``.
    """
    return [
        _np.asarray(p, dtype=_np.int32).reshape(-1, 1, 2)
        for p in pts_list
    ]


# ══════════════════════════════════════════════════════════════════════════
# Lines and arrows
# ══════════════════════════════════════════════════════════════════════════


line = _pred("line",
    (5, _pure(_draw(lambda canvas, p1, p2, color:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color))))),
    (6, _pure(_draw(lambda canvas, p1, p2, color, thickness:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color),
                           int(thickness))))),
    (7, _pure(_draw(lambda canvas, p1, p2, color, thickness, line_type:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color),
                           int(thickness), int(line_type))))),
)


arrowed_line = _pred("arrowed_line",
    (5, _pure(_draw(lambda canvas, p1, p2, color:
              _cv().arrowedLine(canvas, tuple(p1), tuple(p2), tuple(color))))),
    (6, _pure(_draw(lambda canvas, p1, p2, color, thickness:
              _cv().arrowedLine(canvas, tuple(p1), tuple(p2), tuple(color),
                                  int(thickness))))),
    (7, _pure(_draw(lambda canvas, p1, p2, color, thickness, line_type:
              _cv().arrowedLine(canvas, tuple(p1), tuple(p2), tuple(color),
                                  int(thickness), int(line_type))))),
)


# ══════════════════════════════════════════════════════════════════════════
# Rectangles, circles, ellipses
# ══════════════════════════════════════════════════════════════════════════


rectangle = _pred("rectangle",
    (5, _pure(_draw(lambda canvas, p1, p2, color:
              _cv().rectangle(canvas, tuple(p1), tuple(p2), tuple(color))))),
    (6, _pure(_draw(lambda canvas, p1, p2, color, thickness:
              _cv().rectangle(canvas, tuple(p1), tuple(p2), tuple(color),
                                int(thickness))))),
    (7, _pure(_draw(lambda canvas, p1, p2, color, thickness, line_type:
              _cv().rectangle(canvas, tuple(p1), tuple(p2), tuple(color),
                                int(thickness), int(line_type))))),
)


circle = _pred("circle",
    (5, _pure(_draw(lambda canvas, center, radius, color:
              _cv().circle(canvas, tuple(center), int(radius),
                             tuple(color))))),
    (6, _pure(_draw(lambda canvas, center, radius, color, thickness:
              _cv().circle(canvas, tuple(center), int(radius),
                             tuple(color), int(thickness))))),
    (7, _pure(_draw(lambda canvas, center, radius, color, thickness, line_type:
              _cv().circle(canvas, tuple(center), int(radius),
                             tuple(color), int(thickness), int(line_type))))),
)


ellipse = _pred("ellipse",
    (8, _pure(_draw(lambda canvas, center, axes, angle, start_a, end_a, color:
              _cv().ellipse(canvas, tuple(center), tuple(axes),
                              float(angle), float(start_a), float(end_a),
                              tuple(color))))),
    (9, _pure(_draw(lambda canvas, center, axes, angle, start_a, end_a, color, thickness:
              _cv().ellipse(canvas, tuple(center), tuple(axes),
                              float(angle), float(start_a), float(end_a),
                              tuple(color), int(thickness))))),
)


# ══════════════════════════════════════════════════════════════════════════
# Polylines / fill_poly
# ══════════════════════════════════════════════════════════════════════════


polylines = _pred("polylines",
    (5, _pure(_draw(lambda canvas, pts_list, is_closed, color:
              _cv().polylines(canvas, _to_int32_poly_list(pts_list),
                                bool(is_closed), tuple(color))))),
    (6, _pure(_draw(lambda canvas, pts_list, is_closed, color, thickness:
              _cv().polylines(canvas, _to_int32_poly_list(pts_list),
                                bool(is_closed), tuple(color),
                                int(thickness))))),
)


fill_poly = _pred("fill_poly",
    (4, _pure(_draw(lambda canvas, pts_list, color:
              _cv().fillPoly(canvas, _to_int32_poly_list(pts_list),
                               tuple(color))))),
)


# ══════════════════════════════════════════════════════════════════════════
# Text
# ══════════════════════════════════════════════════════════════════════════


put_text = _pred("put_text",
    (8, _pure(_draw(lambda canvas, text, origin, font, scale, color, thickness:
              _cv().putText(canvas, str(text), tuple(origin),
                              int(font), float(scale), tuple(color),
                              int(thickness))))),
    (9, _pure(_draw(lambda canvas, text, origin, font, scale, color, thickness, line_type:
              _cv().putText(canvas, str(text), tuple(origin),
                              int(font), float(scale), tuple(color),
                              int(thickness), int(line_type))))),
)


# ══════════════════════════════════════════════════════════════════════════
# Markers
# ══════════════════════════════════════════════════════════════════════════


marker = _pred("marker",
    (4, _pure(_draw(lambda canvas, position, color:
              _cv().drawMarker(canvas, tuple(position), tuple(color))))),
    (5, _pure(_draw(lambda canvas, position, color, marker_type:
              _cv().drawMarker(canvas, tuple(position), tuple(color),
                                 markerType=int(marker_type))))),
    (6, _pure(_draw(lambda canvas, position, color, marker_type, marker_size:
              _cv().drawMarker(canvas, tuple(position), tuple(color),
                                 markerType=int(marker_type),
                                 markerSize=int(marker_size))))),
    (7, _pure(_draw(lambda canvas, position, color, marker_type, marker_size, thickness:
              _cv().drawMarker(canvas, tuple(position), tuple(color),
                                 markerType=int(marker_type),
                                 markerSize=int(marker_size),
                                 thickness=int(thickness))))),
)


# ══════════════════════════════════════════════════════════════════════════
# Contours / Keypoints / Matches
# ══════════════════════════════════════════════════════════════════════════


draw_contours = _pred("draw_contours",
    (5, _pure(_draw(lambda canvas, contours, idx, color:
              _cv().drawContours(canvas, list(contours), int(idx),
                                   tuple(color))))),
    (6, _pure(_draw(lambda canvas, contours, idx, color, thickness:
              _cv().drawContours(canvas, list(contours), int(idx),
                                   tuple(color), int(thickness))))),
)


# draw_keypoints / draw_matches consume cv2.KeyPoint / cv2.DMatch lists
# that Phase 7 produces. They ship in Phase 6 alongside the other
# drawing predicates but are tested through Phase 7's fixtures (which
# have actual keypoints to draw).
draw_keypoints = _pred("draw_keypoints",
    (4, _pure(_draw(lambda canvas, kps, color:
              _cv().drawKeypoints(canvas, list(kps), canvas,
                                    color=tuple(color))))),
    (5, _pure(_draw(lambda canvas, kps, color, flags:
              _cv().drawKeypoints(canvas, list(kps), canvas,
                                    color=tuple(color),
                                    flags=int(flags))))),
)


def _draw_matches(img1, kp1, img2, kp2, matches, flags):
    return _cv().drawMatches(img1, list(kp1), img2, list(kp2),
                                list(matches), None, flags=int(flags))


draw_matches = _pred("draw_matches",
    (7, _pure(_draw_matches)),
)


__all__ = [
    "line", "arrowed_line",
    "rectangle", "circle", "ellipse",
    "polylines", "fill_poly",
    "put_text", "marker",
    "draw_contours", "draw_keypoints", "draw_matches",
]
