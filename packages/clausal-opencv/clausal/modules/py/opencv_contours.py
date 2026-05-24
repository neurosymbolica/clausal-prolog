"""clausal.modules.py.opencv_contours — OpenCV contour predicates.

Phase 4 — Contours.

Contour extraction and per-contour measurements (area, perimeter,
moments, convex hull, bounding rectangles, point-in-polygon test).

Three tagged-tuple term constructors are introduced:

* ``("rect", X, Y, W, H)`` — output of ``bounding_rect/2``.
* ``("rotated_rect", CENTER, SIZE, ANGLE)`` — output of
  ``min_area_rect/2``. ``CENTER`` is ``[cx, cy]``, ``SIZE`` is
  ``[w, h]``, ``ANGLE`` is degrees.
* ``("moments_t", M00, M10, M01, M20, M11, M02, M30, M21, M12,
   M03, MU20, MU11, MU02, MU30, MU21, MU12, MU03, NU20, NU11,
   NU02, NU30, NU21, NU12, NU03)`` — output of ``moments/2,3``.

For the moments record the 25-element tuple is rarely decomposed
directly; use ``moments_field(M, "m00", VALUE)`` to read a single
field by name.

Use::

    -import_from(opencv_contours, [
        find_contours, contour, contour_area, contour_perimeter,
        moments, moments_field,
        convex_hull, bounding_rect, min_enclosing_circle, min_area_rect,
        approx_poly_dp, point_polygon_test, threshold_type,
    ])

Predicate catalogue
-------------------
    find_contours(IMG, MODE, METHOD, CONTOURS, HIERARCHY)
    find_contours(IMG, MODE, METHOD, OFFSET, CONTOURS, HIERARCHY)
    contour(CONTOURS, C)                                Nondet enumeration
    contour_area(C, AREA)
    contour_area(C, ORIENTED, AREA)
    contour_perimeter(C, CLOSED, P)
    moments(C_OR_IMG, MOMENTS)
    moments(IMG, BINARY, MOMENTS)
    moments_field(MOMENTS, NAME, VALUE)
    convex_hull(POINTS, HULL)
    convex_hull(POINTS, CLOCKWISE, HULL)
    bounding_rect(POINTS, RECT)                         ``("rect", X, Y, W, H)``
    min_enclosing_circle(POINTS, CENTER, RADIUS)
    min_area_rect(POINTS, ROTATED_RECT)
    approx_poly_dp(C, EPSILON, CLOSED, APPROX)
    point_polygon_test(C, PT, MEASURE_DIST, RESULT)
    threshold_type(NAME, CODE)                          Registry
"""

from __future__ import annotations

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _fact_table_2, _deep_deref
from clausal.modules.py.opencv import _cv


# ── find_contours / contour enumeration ───────────────────────────────────


def _find_contours_5(this_generator, _proceed, _fail, _catcher,
                     img_v, mode_v, method_v, contours_v, hier_v, trail):
    img = _deep_deref(img_v)
    mode = int(deref(mode_v))
    method = int(deref(method_v))
    try:
        contours, hierarchy = _cv().findContours(img, mode, method)
    except Exception:
        yield (_fail, DONE)
        return
    if (unify(contours_v, list(contours), trail)
            and unify(hier_v, hierarchy, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


def _find_contours_6(this_generator, _proceed, _fail, _catcher,
                     img_v, mode_v, method_v, offset_v,
                     contours_v, hier_v, trail):
    img = _deep_deref(img_v)
    mode = int(deref(mode_v))
    method = int(deref(method_v))
    offset = tuple(_deep_deref(offset_v))
    try:
        contours, hierarchy = _cv().findContours(img, mode, method,
                                                   offset=offset)
    except Exception:
        yield (_fail, DONE)
        return
    if (unify(contours_v, list(contours), trail)
            and unify(hier_v, hierarchy, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


find_contours = _pred("find_contours",
    (5, _find_contours_5),
    (6, _find_contours_6),
)


def _contour_enum(this_generator, _proceed, _fail, _catcher,
                  contours_v, c_v, trail):
    contours = _deep_deref(contours_v)
    if not isinstance(contours, (list, tuple)):
        yield (_fail, DONE)
        return
    for c in contours:
        mark = trail.mark()
        if unify(c_v, c, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


contour = _pred("contour", (2, _contour_enum))


# ── Per-contour measurements ──────────────────────────────────────────────


contour_area = _pred("contour_area",
    (2, _pure(lambda c: float(_cv().contourArea(c)))),
    (3, _pure(lambda c, oriented:
              float(_cv().contourArea(c, oriented=bool(oriented))))),
)


contour_perimeter = _pred("contour_perimeter",
    (3, _pure(lambda c, closed:
              float(_cv().arcLength(c, bool(closed))))),
)


convex_hull = _pred("convex_hull",
    (2, _pure(lambda points: _cv().convexHull(points))),
    (3, _pure(lambda points, clockwise:
              _cv().convexHull(points, clockwise=bool(clockwise)))),
)


def _bounding_rect(points):
    x, y, w, h = _cv().boundingRect(points)
    return ("rect", int(x), int(y), int(w), int(h))


bounding_rect = _pred("bounding_rect",
    (2, _pure(_bounding_rect)),
)


def _min_enclosing_circle_dispatch(this_generator, _proceed, _fail, _catcher,
                                    points_v, center_v, radius_v, trail):
    points = _deep_deref(points_v)
    try:
        (cx, cy), r = _cv().minEnclosingCircle(points)
    except Exception:
        yield (_fail, DONE)
        return
    if (unify(center_v, [float(cx), float(cy)], trail)
            and unify(radius_v, float(r), trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


min_enclosing_circle = _pred("min_enclosing_circle",
    (3, _min_enclosing_circle_dispatch),
)


def _min_area_rect(points):
    (cx, cy), (w, h), angle = _cv().minAreaRect(points)
    return ("rotated_rect",
            [float(cx), float(cy)],
            [float(w), float(h)],
            float(angle))


min_area_rect = _pred("min_area_rect",
    (2, _pure(_min_area_rect)),
)


approx_poly_dp = _pred("approx_poly_dp",
    (4, _pure(lambda c, epsilon, closed:
              _cv().approxPolyDP(c, float(epsilon), bool(closed)))),
)


point_polygon_test = _pred("point_polygon_test",
    (4, _pure(lambda c, pt, measure_dist:
              float(_cv().pointPolygonTest(c, tuple(pt),
                                              bool(measure_dist))))),
)


# ── Moments ───────────────────────────────────────────────────────────────


_MOMENT_KEYS = (
    "m00", "m10", "m01", "m20", "m11", "m02",
    "m30", "m21", "m12", "m03",
    "mu20", "mu11", "mu02", "mu30", "mu21", "mu12", "mu03",
    "nu20", "nu11", "nu02", "nu30", "nu21", "nu12", "nu03",
)


def _moments_term(arg, binary_image=False):
    m = _cv().moments(arg, binaryImage=bool(binary_image))
    return ("moments_t",) + tuple(float(m[k]) for k in _MOMENT_KEYS)


moments = _pred("moments",
    (2, _pure(lambda arg: _moments_term(arg))),
    (3, _pure(lambda img, binary: _moments_term(img, binary))),
)


def _moments_field(m_term, name):
    if not (isinstance(m_term, tuple) and m_term and m_term[0] == "moments_t"):
        raise ValueError("Expected moments_t term")
    name_s = str(name)
    if name_s not in _MOMENT_KEYS:
        raise KeyError(name_s)
    idx = _MOMENT_KEYS.index(name_s) + 1
    return float(m_term[idx])


moments_field = _pred("moments_field",
    (3, _pure(_moments_field)),
)


# ── Registry ──────────────────────────────────────────────────────────────


def _threshold_type_facts():
    cv = _cv()
    return [
        ("binary",     cv.THRESH_BINARY),
        ("binary_inv", cv.THRESH_BINARY_INV),
        ("trunc",      cv.THRESH_TRUNC),
        ("tozero",     cv.THRESH_TOZERO),
        ("tozero_inv", cv.THRESH_TOZERO_INV),
        ("otsu",       cv.THRESH_OTSU),
        ("triangle",   cv.THRESH_TRIANGLE),
    ]


threshold_type = _pred("threshold_type",
    (2, _fact_table_2(_threshold_type_facts)),
)


__all__ = [
    "find_contours", "contour",
    "contour_area", "contour_perimeter",
    "moments", "moments_field",
    "convex_hull", "bounding_rect",
    "min_enclosing_circle", "min_area_rect",
    "approx_poly_dp", "point_polygon_test",
    "threshold_type",
]
