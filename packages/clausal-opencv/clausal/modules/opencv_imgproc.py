"""clausal.modules.opencv_imgproc — OpenCV image-processing predicates.

Phase 3 — Filtering and Morphology.

Smoothing, convolution, edge detection, morphology, pyramids, plus
four name↔code registries: ``interpolation``, ``border_type``,
``morph_op``, ``morph_shape``.

All predicates are Tier 1 (pure). Inputs are NumPy ``ndarray`` images
or kernels; outputs are fresh ``ndarray``s.

Use::

    -import_from(opencv_imgproc, [
        gaussian_blur, median_blur, sobel, canny,
        get_structuring_element, morphology_ex,
        interpolation, border_type, morph_op, morph_shape,
    ])
    -import_from(opencv, [
        inter_cubic, border_reflect, morph_rect, morph_open,
    ])

Predicate catalogue
-------------------
Smoothing:
    gaussian_blur(IMG, KSIZE, OUT)
    gaussian_blur(IMG, KSIZE, SIGMA, OUT)
    gaussian_blur(IMG, KSIZE, SIGMA_X, SIGMA_Y, OUT)
    median_blur(IMG, KSIZE, OUT)
    box_filter(IMG, DDEPTH, KSIZE, OUT)
    bilateral_filter(IMG, D, SIGMA_COLOR, SIGMA_SPACE, OUT)

Convolution:
    filter_2d(IMG, DDEPTH, KERNEL, OUT)
    sep_filter_2d(IMG, DDEPTH, KERNEL_X, KERNEL_Y, OUT)

Edge detection:
    sobel(IMG, DDEPTH, DX, DY, OUT)
    sobel(IMG, DDEPTH, DX, DY, KSIZE, OUT)
    scharr(IMG, DDEPTH, DX, DY, OUT)
    laplacian(IMG, DDEPTH, OUT)
    laplacian(IMG, DDEPTH, KSIZE, OUT)
    canny(IMG, T1, T2, OUT)
    canny(IMG, T1, T2, APERTURE, OUT)

Morphology:
    get_structuring_element(SHAPE, KSIZE, KERNEL)
    get_structuring_element(SHAPE, KSIZE, ANCHOR, KERNEL)
    erode(IMG, KERNEL, OUT)
    erode(IMG, KERNEL, ITERATIONS, OUT)
    dilate(IMG, KERNEL, OUT)
    dilate(IMG, KERNEL, ITERATIONS, OUT)
    morphology_ex(IMG, OP, KERNEL, OUT)
    morphology_ex(IMG, OP, KERNEL, ITERATIONS, OUT)

Pyramids:
    pyr_down(IMG, OUT)
    pyr_down(IMG, DSTSIZE, OUT)
    pyr_up(IMG, OUT)
    pyr_up(IMG, DSTSIZE, OUT)

Registries:
    interpolation(NAME, CODE)            nearest, linear, cubic, area, lanczos4
    border_type(NAME, CODE)              constant, replicate, reflect, reflect_101, wrap, isolated
    morph_op(NAME, CODE)                 erode, dilate, open, close, gradient, tophat, blackhat, hitmiss
    morph_shape(NAME, CODE)              rect, ellipse, cross
"""

from __future__ import annotations

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import (
    _pred, _pure, _fact_table_2, _deep_deref, _bidir_2,
)
from clausal.modules.opencv import _cv


# ── Helpers ────────────────────────────────────────────────────────────────


def _ksize_tuple(ksize):
    """Coerce a Clausal list/tuple/int to a 2-tuple of ints for cv2."""
    if isinstance(ksize, int):
        return (ksize, ksize)
    return (int(ksize[0]), int(ksize[1]))


# ══════════════════════════════════════════════════════════════════════════
# Smoothing
# ══════════════════════════════════════════════════════════════════════════


gaussian_blur = _pred("gaussian_blur",
    (3, _pure(lambda img, ksize:
              _cv().GaussianBlur(img, _ksize_tuple(ksize), 0))),
    (4, _pure(lambda img, ksize, sigma:
              _cv().GaussianBlur(img, _ksize_tuple(ksize), float(sigma)))),
    (5, _pure(lambda img, ksize, sx, sy:
              _cv().GaussianBlur(img, _ksize_tuple(ksize),
                                   float(sx), sigmaY=float(sy)))),
)

median_blur = _pred("median_blur",
    (3, _pure(lambda img, ksize: _cv().medianBlur(img, int(ksize)))),
)

box_filter = _pred("box_filter",
    (4, _pure(lambda img, ddepth, ksize:
              _cv().boxFilter(img, int(ddepth), _ksize_tuple(ksize)))),
)

bilateral_filter = _pred("bilateral_filter",
    (5, _pure(lambda img, d, sigma_color, sigma_space:
              _cv().bilateralFilter(img, int(d),
                                      float(sigma_color),
                                      float(sigma_space)))),
)


# ══════════════════════════════════════════════════════════════════════════
# Convolution
# ══════════════════════════════════════════════════════════════════════════


filter_2d = _pred("filter_2d",
    (4, _pure(lambda img, ddepth, kernel:
              _cv().filter2D(img, int(ddepth), kernel))),
)

sep_filter_2d = _pred("sep_filter_2d",
    (5, _pure(lambda img, ddepth, kx, ky:
              _cv().sepFilter2D(img, int(ddepth), kx, ky))),
)


# ══════════════════════════════════════════════════════════════════════════
# Edge detection
# ══════════════════════════════════════════════════════════════════════════


sobel = _pred("sobel",
    (5, _pure(lambda img, ddepth, dx, dy:
              _cv().Sobel(img, int(ddepth), int(dx), int(dy)))),
    (6, _pure(lambda img, ddepth, dx, dy, ksize:
              _cv().Sobel(img, int(ddepth), int(dx), int(dy),
                           ksize=int(ksize)))),
)

scharr = _pred("scharr",
    (5, _pure(lambda img, ddepth, dx, dy:
              _cv().Scharr(img, int(ddepth), int(dx), int(dy)))),
)

laplacian = _pred("laplacian",
    (3, _pure(lambda img, ddepth: _cv().Laplacian(img, int(ddepth)))),
    (4, _pure(lambda img, ddepth, ksize:
              _cv().Laplacian(img, int(ddepth), ksize=int(ksize)))),
)

canny = _pred("canny",
    (4, _pure(lambda img, t1, t2:
              _cv().Canny(img, float(t1), float(t2)))),
    (5, _pure(lambda img, t1, t2, aperture:
              _cv().Canny(img, float(t1), float(t2),
                           apertureSize=int(aperture)))),
)


# ══════════════════════════════════════════════════════════════════════════
# Morphology
# ══════════════════════════════════════════════════════════════════════════


get_structuring_element = _pred("get_structuring_element",
    (3, _pure(lambda shape, ksize:
              _cv().getStructuringElement(int(shape), _ksize_tuple(ksize)))),
    (4, _pure(lambda shape, ksize, anchor:
              _cv().getStructuringElement(int(shape), _ksize_tuple(ksize),
                                            tuple(anchor)))),
)

erode = _pred("erode",
    (3, _pure(lambda img, kernel: _cv().erode(img, kernel))),
    (4, _pure(lambda img, kernel, iterations:
              _cv().erode(img, kernel, iterations=int(iterations)))),
)

dilate = _pred("dilate",
    (3, _pure(lambda img, kernel: _cv().dilate(img, kernel))),
    (4, _pure(lambda img, kernel, iterations:
              _cv().dilate(img, kernel, iterations=int(iterations)))),
)

morphology_ex = _pred("morphology_ex",
    (4, _pure(lambda img, op, kernel:
              _cv().morphologyEx(img, int(op), kernel))),
    (5, _pure(lambda img, op, kernel, iterations:
              _cv().morphologyEx(img, int(op), kernel,
                                   iterations=int(iterations)))),
)


# ══════════════════════════════════════════════════════════════════════════
# Pyramids
# ══════════════════════════════════════════════════════════════════════════


pyr_down = _pred("pyr_down",
    (2, _pure(lambda img: _cv().pyrDown(img))),
    (3, _pure(lambda img, dstsize:
              _cv().pyrDown(img, dstsize=tuple(dstsize)))),
)

pyr_up = _pred("pyr_up",
    (2, _pure(lambda img: _cv().pyrUp(img))),
    (3, _pure(lambda img, dstsize:
              _cv().pyrUp(img, dstsize=tuple(dstsize)))),
)


# ══════════════════════════════════════════════════════════════════════════
# Registries (name ↔ int code)
# ══════════════════════════════════════════════════════════════════════════


def _interpolation_facts():
    cv = _cv()
    return [
        ("nearest",  cv.INTER_NEAREST),
        ("linear",   cv.INTER_LINEAR),
        ("cubic",    cv.INTER_CUBIC),
        ("area",     cv.INTER_AREA),
        ("lanczos4", cv.INTER_LANCZOS4),
    ]


def _border_facts():
    cv = _cv()
    return [
        ("constant",    cv.BORDER_CONSTANT),
        ("replicate",   cv.BORDER_REPLICATE),
        ("reflect",     cv.BORDER_REFLECT),
        ("reflect_101", cv.BORDER_REFLECT_101),
        ("wrap",        cv.BORDER_WRAP),
        ("isolated",    cv.BORDER_ISOLATED),
    ]


def _morph_op_facts():
    cv = _cv()
    return [
        ("erode",    cv.MORPH_ERODE),
        ("dilate",   cv.MORPH_DILATE),
        ("open",     cv.MORPH_OPEN),
        ("close",    cv.MORPH_CLOSE),
        ("gradient", cv.MORPH_GRADIENT),
        ("tophat",   cv.MORPH_TOPHAT),
        ("blackhat", cv.MORPH_BLACKHAT),
        ("hitmiss",  cv.MORPH_HITMISS),
    ]


def _morph_shape_facts():
    cv = _cv()
    return [
        ("rect",    cv.MORPH_RECT),
        ("ellipse", cv.MORPH_ELLIPSE),
        ("cross",   cv.MORPH_CROSS),
    ]


interpolation = _pred("interpolation",
    (2, _fact_table_2(_interpolation_facts)),
)

border_type = _pred("border_type",
    (2, _fact_table_2(_border_facts)),
)

morph_op = _pred("morph_op",
    (2, _fact_table_2(_morph_op_facts)),
)

morph_shape = _pred("morph_shape",
    (2, _fact_table_2(_morph_shape_facts)),
)


# ══════════════════════════════════════════════════════════════════════════
# Thresholding (Phase 4)
# ══════════════════════════════════════════════════════════════════════════
#
# ``threshold/6`` returns *both* the binary output and the level used —
# with ``THRESH_OTSU`` / ``THRESH_TRIANGLE`` the level is computed
# inside cv2 rather than coming from the THRESH argument. Custom
# dispatch because ``_pure`` only unifies a single result.

def _threshold_6(this_generator, _proceed, _fail, _catcher,
                 img_v, thresh_v, maxval_v, type_v,
                 used_v, out_v, trail):
    img = _deep_deref(img_v)
    thresh = deref(thresh_v)
    maxval = deref(maxval_v)
    type_ = deref(type_v)
    try:
        used, out = _cv().threshold(img, float(thresh), float(maxval),
                                      int(type_))
    except Exception:
        yield (_fail, DONE)
        return
    if unify(used_v, float(used), trail) and unify(out_v, out, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


threshold = _pred("threshold", (6, _threshold_6))


adaptive_threshold = _pred("adaptive_threshold",
    (7, _pure(lambda img, maxval, am, tt, bs, c:
              _cv().adaptiveThreshold(img, float(maxval),
                                        int(am), int(tt),
                                        int(bs), float(c)))),
)


# ══════════════════════════════════════════════════════════════════════════
# Geometric transformations (Phase 5)
# ══════════════════════════════════════════════════════════════════════════
#
# OpenCV uses ``(W, H)`` order for ``dsize`` arguments — opposite of
# numpy's ``(H, W)`` shape. The wrapper takes ``dsize`` as a 2-list
# ``[W, H]`` (Clausal idiom) and coerces to a tuple for cv2.


resize = _pred("resize",
    (3, _pure(lambda img, dsize: _cv().resize(img, tuple(dsize)))),
    (4, _pure(lambda img, dsize, interp:
              _cv().resize(img, tuple(dsize), interpolation=int(interp)))),
)

resize_factor = _pred("resize_factor",
    (4, _pure(lambda img, fx, fy:
              _cv().resize(img, (0, 0), fx=float(fx), fy=float(fy)))),
    (5, _pure(lambda img, fx, fy, interp:
              _cv().resize(img, (0, 0), fx=float(fx), fy=float(fy),
                             interpolation=int(interp)))),
)


def _warp_affine_4(img, M, dsize):
    return _cv().warpAffine(img, M, tuple(dsize))

def _warp_affine_5(img, M, dsize, flags):
    return _cv().warpAffine(img, M, tuple(dsize), flags=int(flags))

def _warp_affine_6(img, M, dsize, flags, border_mode):
    return _cv().warpAffine(img, M, tuple(dsize),
                              flags=int(flags),
                              borderMode=int(border_mode))

def _warp_affine_7(img, M, dsize, flags, border_mode, border_value):
    return _cv().warpAffine(img, M, tuple(dsize),
                              flags=int(flags),
                              borderMode=int(border_mode),
                              borderValue=tuple(border_value))

warp_affine = _pred("warp_affine",
    (4, _pure(_warp_affine_4)),
    (5, _pure(_warp_affine_5)),
    (6, _pure(_warp_affine_6)),
    (7, _pure(_warp_affine_7)),
)


def _warp_perspective_4(img, M, dsize):
    return _cv().warpPerspective(img, M, tuple(dsize))

def _warp_perspective_5(img, M, dsize, flags):
    return _cv().warpPerspective(img, M, tuple(dsize), flags=int(flags))

def _warp_perspective_6(img, M, dsize, flags, border_mode):
    return _cv().warpPerspective(img, M, tuple(dsize),
                                    flags=int(flags),
                                    borderMode=int(border_mode))

def _warp_perspective_7(img, M, dsize, flags, border_mode, border_value):
    return _cv().warpPerspective(img, M, tuple(dsize),
                                    flags=int(flags),
                                    borderMode=int(border_mode),
                                    borderValue=tuple(border_value))

warp_perspective = _pred("warp_perspective",
    (4, _pure(_warp_perspective_4)),
    (5, _pure(_warp_perspective_5)),
    (6, _pure(_warp_perspective_6)),
    (7, _pure(_warp_perspective_7)),
)


rotate = _pred("rotate",
    (3, _pure(lambda img, code: _cv().rotate(img, int(code)))),
)


get_rotation_matrix_2d = _pred("get_rotation_matrix_2d",
    (4, _pure(lambda center, angle, scale:
              _cv().getRotationMatrix2D(tuple(center),
                                          float(angle), float(scale)))),
)

get_affine_transform = _pred("get_affine_transform",
    (3, _pure(lambda src, dst: _cv().getAffineTransform(src, dst))),
)

get_perspective_transform = _pred("get_perspective_transform",
    (3, _pure(lambda src, dst: _cv().getPerspectiveTransform(src, dst))),
)


# ``invertAffineTransform`` is its own inverse: M -> M_inv -> M (modulo
# floating-point error). Bidirectional via ``_bidir_2``.

def _inv_affine(M):
    return _cv().invertAffineTransform(M)

affine_inverse = _pred("affine_inverse",
    (2, _bidir_2(_inv_affine, _inv_affine)),
)


remap = _pred("remap",
    (5, _pure(lambda img, map1, map2, interp:
              _cv().remap(img, map1, map2, int(interp)))),
    (6, _pure(lambda img, map1, map2, interp, border_mode:
              _cv().remap(img, map1, map2, int(interp),
                            borderMode=int(border_mode)))),
)


copy_make_border = _pred("copy_make_border",
    (7, _pure(lambda img, top, bot, left, right, border_type:
              _cv().copyMakeBorder(img, int(top), int(bot),
                                       int(left), int(right),
                                       int(border_type)))),
    (8, _pure(lambda img, top, bot, left, right, border_type, value:
              _cv().copyMakeBorder(img, int(top), int(bot),
                                       int(left), int(right),
                                       int(border_type),
                                       value=tuple(value)))),
)


__all__ = [
    # Smoothing
    "gaussian_blur", "median_blur", "box_filter", "bilateral_filter",
    # Convolution
    "filter_2d", "sep_filter_2d",
    # Edge detection
    "sobel", "scharr", "laplacian", "canny",
    # Morphology
    "get_structuring_element", "erode", "dilate", "morphology_ex",
    # Pyramids
    "pyr_down", "pyr_up",
    # Registries
    "interpolation", "border_type", "morph_op", "morph_shape",
    # Thresholding (Phase 4)
    "threshold", "adaptive_threshold",
    # Geometric transformations (Phase 5)
    "resize", "resize_factor",
    "warp_affine", "warp_perspective", "rotate",
    "get_rotation_matrix_2d", "get_affine_transform",
    "get_perspective_transform", "affine_inverse",
    "remap", "copy_make_border",
]
