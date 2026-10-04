"""clausal.modules.py.opencv — OpenCV (cv2) predicates for Clausal.

Phase 1 — Core, I/O, Properties, Arithmetic.

Provides the central image data type (``numpy.ndarray`` with BGR
layout) along with I/O, properties, arithmetic, and bitwise operations
as importable predicate objects for use in ``.clausal`` files via::

    -import_from(opencv, [imread, shape, add, IMREAD_COLOR, ...])

Conventions
-----------
- **BGR not RGB.** ``imread`` returns BGR-ordered arrays. Convert with
  ``cvt_color(IMG, COLOR_BGR2RGB, RGB)`` (Phase 2) before feeding
  matplotlib or PIL.
- **shape vs size.** ``shape/2`` returns NumPy ``[H, W, C]`` (or
  ``[H, W]`` for grayscale); ``size/2`` returns OpenCV ``[W, H]``.

Predicate catalogue
-------------------
I/O (Tier 4):
    imread(PATH, IMG)
    imread(PATH, FLAG, IMG)
    imwrite(PATH, IMG)
    imwrite(PATH, IMG, PARAMS)
    image_encoded(IMG, EXT, BUF)            bidirectional encode/decode

Properties (Tier 1, multi-mode):
    shape(IMG, SHAPE)                       (+,-) query or (+,+) check
    dtype(IMG, D)                           (+,-) query or (+,+) check
    channels_count(IMG, N)                  (+,-) query or (+,+) check
    size(IMG, [W, H])                       (+,-) query or (+,+) check
    element_count(IMG, N)                   (+,-) query
    is_grayscale(IMG)                       check
    is_color(IMG)                           check
    is_uint8(IMG)                           check

Arithmetic (Tier 1, pure):
    add(A, B, C)                            saturated
    subtract(A, B, C)                       saturated
    multiply(A, B, C) / multiply(A, B, SCALE, C)
    divide(A, B, C)   / divide(A, B, SCALE, C)
    absdiff(A, B, C)
    bitwise_and(A, B, C) / bitwise_and(A, B, MASK, C)
    bitwise_or(A, B, C)  / bitwise_or(A, B, MASK, C)
    bitwise_xor(A, B, C) / bitwise_xor(A, B, MASK, C)
    bitwise_not(A, C)    / bitwise_not(A, MASK, C)
    min(A, B, C)                            element-wise
    max(A, B, C)                            element-wise

Reductions (Tier 1, pure):
    mean(IMG, M) / mean(IMG, MASK, M)       4-tuple per channel
    min_max_loc(IMG, R) / min_max_loc(IMG, MASK, R)
        R = ("min_max", MIN_VAL, MAX_VAL, MIN_LOC, MAX_LOC)

Whole-image transforms (Tier 1, pure):
    flip(IMG, CODE, OUT)                    code: 0/1/-1
    transpose(IMG, OUT)
    copy_image(IMG, COPY)

Handle lifecycle (Tier 3):
    free(HANDLE)

Constants (re-exports of ``cv2.*``, importable by name):
    IMREAD_*           image read flags
    IMWRITE_*          image write params
    CV_8U/CV_8S/...    OpenCV data type constants
    NORM_*             norm types (used by Phase 7 matchers)
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

import numpy as _np

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import require_text
from clausal.modules.py._helpers import (
    _pred, _pure, _bidir_3_mid, _check_1, _deep_deref, _values_equal,
)


# ── Local property dispatch ───────────────────────────────────────────────
#
# ``clausal.modules.py._helpers._property_2`` uses ``==`` for check mode,
# which fails when the bound value contains unbound vars inside a list
# (e.g. ``shape(IMG, [_, _, 3])``). The opencv wrapper queries naturally
# include partial-pattern checks, so the dispatch here uses ``unify`` in
# both modes — the unifier recursively matches list elements and binds
# vars on the way. The bool/array fallback path mirrors ``_bidir_2`` in
# ``_helpers.py``.

def _property_2(getter):
    def dispatch(this_generator, _proceed, _fail, _catcher,
                 x_var, value_var, trail):
        x = deref(x_var)
        try:
            actual = getter(x)
        except Exception:
            yield (_fail, DONE)
            return
        mark = trail.mark()
        try:
            ok = bool(unify(value_var, actual, trail))
        except (ValueError, TypeError):
            trail.undo(mark)
            ok = _values_equal(actual, deref(value_var))
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


# ── Lazy cv2 import ────────────────────────────────────────────────────────

_cv2 = None
_cv2_lock = _threading.Lock()


def _ensure_cv2():
    global _cv2
    if _cv2 is not None:
        return
    with _cv2_lock:
        if _cv2 is not None:
            return
        from clausal.modules.py import _import_stdlib
        _cv2 = _import_stdlib("cv2")


def _cv():
    _ensure_cv2()
    return _cv2


# ── Constant re-exports via __getattr__ ───────────────────────────────────
#
# Each Phase may extend ``_CONSTANTS`` to surface additional cv2
# attributes under ``clausal.modules.py.opencv`` so users can write
# ``-import_from(opencv, [color_bgr2gray])`` without an ``++()`` escape.
#
# CONVENTION: names are **lowercase** in the wrapper, not the
# upstream ``IMREAD_COLOR`` form. This is forced — Clausal treats
# ALL-CAPS identifiers as logic variables (see
# ``clausal/templating/term_rewriting.py:_is_logic_var_name``), so
# ``IMREAD_COLOR`` in a goal body is parsed as a fresh variable, not a
# name lookup. The lowercase aliases preserve the cv2 mapping
# unambiguously (``imread_color`` ↔ ``cv2.IMREAD_COLOR``).

# Mapping: clausal lowercase name → cv2 attribute name.
_CONSTANTS: dict[str, str] = {
    # Image read flags
    "imread_color":              "IMREAD_COLOR",
    "imread_grayscale":          "IMREAD_GRAYSCALE",
    "imread_unchanged":          "IMREAD_UNCHANGED",
    "imread_anydepth":           "IMREAD_ANYDEPTH",
    "imread_anycolor":           "IMREAD_ANYCOLOR",
    "imread_reduced_grayscale_2": "IMREAD_REDUCED_GRAYSCALE_2",
    "imread_reduced_color_2":     "IMREAD_REDUCED_COLOR_2",
    "imread_reduced_grayscale_4": "IMREAD_REDUCED_GRAYSCALE_4",
    "imread_reduced_color_4":     "IMREAD_REDUCED_COLOR_4",
    "imread_reduced_grayscale_8": "IMREAD_REDUCED_GRAYSCALE_8",
    "imread_reduced_color_8":     "IMREAD_REDUCED_COLOR_8",
    # Image write params
    "imwrite_jpeg_quality":   "IMWRITE_JPEG_QUALITY",
    "imwrite_png_compression": "IMWRITE_PNG_COMPRESSION",
    "imwrite_webp_quality":   "IMWRITE_WEBP_QUALITY",
    "imwrite_tiff_compression": "IMWRITE_TIFF_COMPRESSION",
    # Data types
    "cv_8u":  "CV_8U",  "cv_8s":  "CV_8S",
    "cv_16u": "CV_16U", "cv_16s": "CV_16S",
    "cv_32s": "CV_32S", "cv_32f": "CV_32F", "cv_64f": "CV_64F",
    # Norm types
    "norm_inf":     "NORM_INF",
    "norm_l1":      "NORM_L1",
    "norm_l2":      "NORM_L2",
    "norm_l2sqr":   "NORM_L2SQR",
    "norm_hamming": "NORM_HAMMING",
    "norm_hamming2": "NORM_HAMMING2",
    "norm_minmax":  "NORM_MINMAX",
    # Color conversion codes (Phase 2) — most commonly used pairs.
    # Hundreds more are reachable via the color_code/2 registry.
    "color_bgr2gray":   "COLOR_BGR2GRAY",
    "color_gray2bgr":   "COLOR_GRAY2BGR",
    "color_bgr2rgb":    "COLOR_BGR2RGB",
    "color_rgb2bgr":    "COLOR_RGB2BGR",
    "color_bgr2hsv":    "COLOR_BGR2HSV",
    "color_hsv2bgr":    "COLOR_HSV2BGR",
    "color_bgr2hls":    "COLOR_BGR2HLS",
    "color_hls2bgr":    "COLOR_HLS2BGR",
    "color_bgr2lab":    "COLOR_BGR2LAB",
    "color_lab2bgr":    "COLOR_LAB2BGR",
    "color_bgr2luv":    "COLOR_BGR2LUV",
    "color_luv2bgr":    "COLOR_LUV2BGR",
    "color_bgr2ycrcb":  "COLOR_BGR2YCRCB",
    "color_ycrcb2bgr":  "COLOR_YCRCB2BGR",
    "color_bgr2xyz":    "COLOR_BGR2XYZ",
    "color_xyz2bgr":    "COLOR_XYZ2BGR",
    "color_bgr2yuv":    "COLOR_BGR2YUV",
    "color_yuv2bgr":    "COLOR_YUV2BGR",
    "color_bgra2bgr":   "COLOR_BGRA2BGR",
    "color_bgr2bgra":   "COLOR_BGR2BGRA",
    "color_rgba2rgb":   "COLOR_RGBA2RGB",
    "color_rgb2rgba":   "COLOR_RGB2RGBA",
    # Bayer demosaic (cameras)
    "color_bayer_bg2bgr": "COLOR_BAYER_BG2BGR",
    "color_bayer_gb2bgr": "COLOR_BAYER_GB2BGR",
    "color_bayer_rg2bgr": "COLOR_BAYER_RG2BGR",
    "color_bayer_gr2bgr": "COLOR_BAYER_GR2BGR",
    # Interpolation flags (Phase 3 / 5)
    "inter_nearest":  "INTER_NEAREST",
    "inter_linear":   "INTER_LINEAR",
    "inter_cubic":    "INTER_CUBIC",
    "inter_area":     "INTER_AREA",
    "inter_lanczos4": "INTER_LANCZOS4",
    # Border types (Phase 3 / 5)
    "border_constant":    "BORDER_CONSTANT",
    "border_replicate":   "BORDER_REPLICATE",
    "border_reflect":     "BORDER_REFLECT",
    "border_reflect_101": "BORDER_REFLECT_101",
    "border_default":     "BORDER_DEFAULT",
    "border_wrap":        "BORDER_WRAP",
    "border_isolated":    "BORDER_ISOLATED",
    # Morphology operations (Phase 3)
    "morph_erode":    "MORPH_ERODE",
    "morph_dilate":   "MORPH_DILATE",
    "morph_open":     "MORPH_OPEN",
    "morph_close":    "MORPH_CLOSE",
    "morph_gradient": "MORPH_GRADIENT",
    "morph_tophat":   "MORPH_TOPHAT",
    "morph_blackhat": "MORPH_BLACKHAT",
    "morph_hitmiss":  "MORPH_HITMISS",
    # Morphology kernel shapes (Phase 3)
    "morph_rect":    "MORPH_RECT",
    "morph_ellipse": "MORPH_ELLIPSE",
    "morph_cross":   "MORPH_CROSS",
    # Thresholding (Phase 4)
    "thresh_binary":      "THRESH_BINARY",
    "thresh_binary_inv":  "THRESH_BINARY_INV",
    "thresh_trunc":       "THRESH_TRUNC",
    "thresh_tozero":      "THRESH_TOZERO",
    "thresh_tozero_inv":  "THRESH_TOZERO_INV",
    "thresh_mask":        "THRESH_MASK",
    "thresh_otsu":        "THRESH_OTSU",
    "thresh_triangle":    "THRESH_TRIANGLE",
    # Adaptive thresholding methods (Phase 4)
    "adaptive_thresh_mean_c":     "ADAPTIVE_THRESH_MEAN_C",
    "adaptive_thresh_gaussian_c": "ADAPTIVE_THRESH_GAUSSIAN_C",
    # Contour retrieval modes (Phase 4)
    "retr_external":   "RETR_EXTERNAL",
    "retr_list":       "RETR_LIST",
    "retr_ccomp":      "RETR_CCOMP",
    "retr_tree":       "RETR_TREE",
    "retr_floodfill":  "RETR_FLOODFILL",
    # Contour approximation methods (Phase 4)
    "chain_approx_none":      "CHAIN_APPROX_NONE",
    "chain_approx_simple":    "CHAIN_APPROX_SIMPLE",
    "chain_approx_tc89_l1":   "CHAIN_APPROX_TC89_L1",
    "chain_approx_tc89_kcos": "CHAIN_APPROX_TC89_KCOS",
    # Whole-image rotate codes (Phase 5)
    "rotate_90_clockwise":        "ROTATE_90_CLOCKWISE",
    "rotate_180":                 "ROTATE_180",
    "rotate_90_counterclockwise": "ROTATE_90_COUNTERCLOCKWISE",
    # Warp flags (Phase 5)
    "warp_inverse_map":   "WARP_INVERSE_MAP",
    "warp_fill_outliers": "WARP_FILL_OUTLIERS",
    "warp_polar_linear":  "WARP_POLAR_LINEAR",
    "warp_polar_log":     "WARP_POLAR_LOG",
    # Line types (Phase 6)
    "line_4":  "LINE_4",
    "line_8":  "LINE_8",
    "line_aa": "LINE_AA",
    "filled":  "FILLED",
    # Hershey fonts (Phase 6)
    "font_hershey_simplex":        "FONT_HERSHEY_SIMPLEX",
    "font_hershey_plain":          "FONT_HERSHEY_PLAIN",
    "font_hershey_duplex":         "FONT_HERSHEY_DUPLEX",
    "font_hershey_complex":        "FONT_HERSHEY_COMPLEX",
    "font_hershey_triplex":        "FONT_HERSHEY_TRIPLEX",
    "font_hershey_complex_small":  "FONT_HERSHEY_COMPLEX_SMALL",
    "font_hershey_script_simplex": "FONT_HERSHEY_SCRIPT_SIMPLEX",
    "font_hershey_script_complex": "FONT_HERSHEY_SCRIPT_COMPLEX",
    "font_italic":                 "FONT_ITALIC",
    # Markers (Phase 6)
    "marker_cross":         "MARKER_CROSS",
    "marker_tilted_cross":  "MARKER_TILTED_CROSS",
    "marker_star":          "MARKER_STAR",
    "marker_diamond":       "MARKER_DIAMOND",
    "marker_square":        "MARKER_SQUARE",
    "marker_triangle_up":   "MARKER_TRIANGLE_UP",
    "marker_triangle_down": "MARKER_TRIANGLE_DOWN",
    # Keypoint/match draw flags (Phase 6)
    "draw_matches_flags_default":               "DRAW_MATCHES_FLAGS_DEFAULT",
    "draw_matches_flags_draw_over_outimg":      "DRAW_MATCHES_FLAGS_DRAW_OVER_OUTIMG",
    "draw_matches_flags_not_draw_single_points":"DRAW_MATCHES_FLAGS_NOT_DRAW_SINGLE_POINTS",
    "draw_matches_flags_draw_rich_keypoints":   "DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS",
    # Robust-estimator methods (Phase 9)
    "ransac": "RANSAC",
    "lmeds":  "LMEDS",
    "rho":    "RHO",
    # Fundamental matrix methods (Phase 9)
    "fm_7point": "FM_7POINT",
    "fm_8point": "FM_8POINT",
    "fm_ransac": "FM_RANSAC",
    "fm_lmeds":  "FM_LMEDS",
    # PnP methods (Phase 9)
    "solvepnp_iterative":   "SOLVEPNP_ITERATIVE",
    "solvepnp_epnp":        "SOLVEPNP_EPNP",
    "solvepnp_p3p":         "SOLVEPNP_P3P",
    "solvepnp_dls":         "SOLVEPNP_DLS",
    "solvepnp_upnp":        "SOLVEPNP_UPNP",
    "solvepnp_ap3p":        "SOLVEPNP_AP3P",
    "solvepnp_ippe":        "SOLVEPNP_IPPE",
    "solvepnp_ippe_square": "SOLVEPNP_IPPE_SQUARE",
    "solvepnp_sqpnp":       "SOLVEPNP_SQPNP",
    # Calibration flags (Phase 9)
    "calib_use_intrinsic_guess":  "CALIB_USE_INTRINSIC_GUESS",
    "calib_fix_principal_point":  "CALIB_FIX_PRINCIPAL_POINT",
    "calib_fix_aspect_ratio":     "CALIB_FIX_ASPECT_RATIO",
    "calib_zero_tangent_dist":    "CALIB_ZERO_TANGENT_DIST",
    "calib_fix_k1": "CALIB_FIX_K1",
    "calib_fix_k2": "CALIB_FIX_K2",
    "calib_fix_k3": "CALIB_FIX_K3",
    "calib_fix_k4": "CALIB_FIX_K4",
    "calib_fix_k5": "CALIB_FIX_K5",
    "calib_fix_k6": "CALIB_FIX_K6",
    "calib_rational_model": "CALIB_RATIONAL_MODEL",
    # Chessboard (Phase 9)
    "calib_cb_adaptive_thresh":  "CALIB_CB_ADAPTIVE_THRESH",
    "calib_cb_normalize_image":  "CALIB_CB_NORMALIZE_IMAGE",
    "calib_cb_filter_quads":     "CALIB_CB_FILTER_QUADS",
    "calib_cb_fast_check":       "CALIB_CB_FAST_CHECK",
    # DFT flags (Phase 9)
    "dft_inverse":        "DFT_INVERSE",
    "dft_scale":          "DFT_SCALE",
    "dft_rows":           "DFT_ROWS",
    "dft_complex_output": "DFT_COMPLEX_OUTPUT",
    "dft_real_output":    "DFT_REAL_OUTPUT",
    "dft_complex_input":  "DFT_COMPLEX_INPUT",
}


def __getattr__(name):
    cv2_attr = _CONSTANTS.get(name)
    if cv2_attr is not None:
        try:
            return getattr(_cv(), cv2_attr)
        except AttributeError as exc:
            raise AttributeError(
                f"cv2 has no attribute {cv2_attr!r} (build mismatch?)"
            ) from exc
    raise AttributeError(
        f"module 'clausal.modules.py.opencv' has no attribute {name!r}"
    )


# ══════════════════════════════════════════════════════════════════════════
# I/O — Tier 4
# ══════════════════════════════════════════════════════════════════════════


def _imread(path):
    img = _cv().imread(str(path))
    if img is None:
        raise FileNotFoundError(f"imread failed: {path!r}")
    return img


def _imread_with_flag(path, flag):
    img = _cv().imread(str(path), int(flag))
    if img is None:
        raise FileNotFoundError(f"imread failed: {path!r}")
    return img


imread = _pred("imread",
    (2, _pure(_imread)),
    (3, _pure(_imread_with_flag)),
)


def _imwrite_dispatch_2(this_generator, _proceed, _fail, _catcher,
                        path_var, img_var, trail):
    path = require_text(path_var, "imwrite/2", arg=1)
    img = _deep_deref(img_var)
    try:
        ok = _cv().imwrite(path, img)
    except Exception:
        yield (_fail, DONE)
        return
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


def _imwrite_dispatch_3(this_generator, _proceed, _fail, _catcher,
                        path_var, img_var, params_var, trail):
    path = require_text(path_var, "imwrite/3", arg=1)
    img = _deep_deref(img_var)
    params = _deep_deref(params_var)
    try:
        ok = _cv().imwrite(path, img, [int(p) for p in params])
    except Exception:
        yield (_fail, DONE)
        return
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


imwrite = _pred("imwrite",
    (2, _imwrite_dispatch_2),
    (3, _imwrite_dispatch_3),
)


def _encode(img, ext):
    ok, buf = _cv().imencode(str(ext), img)
    if not ok:
        raise RuntimeError(f"imencode failed for ext={ext!r}")
    return bytes(buf.tobytes())


def _decode(buf, ext):
    # ``ext`` is unused by the decoder itself (cv2 sniffs the format)
    # but is required as input so the predicate stays symmetric.
    del ext
    if isinstance(buf, (bytes, bytearray, memoryview)):
        arr = _np.frombuffer(buf, dtype=_np.uint8)
    else:
        arr = _np.asarray(buf, dtype=_np.uint8)
    img = _cv().imdecode(arr, _cv().IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("imdecode failed")
    return img


image_encoded = _pred("image_encoded",
    (3, _bidir_3_mid(_encode, _decode)),
)


# ══════════════════════════════════════════════════════════════════════════
# Properties — Tier 1, multi-mode
# ══════════════════════════════════════════════════════════════════════════


shape = _pred("shape",
    (2, _property_2(lambda img: list(img.shape))),
)

dtype = _pred("dtype",
    (2, _property_2(lambda img: img.dtype)),
)

channels_count = _pred("channels_count",
    (2, _property_2(lambda img: 1 if img.ndim == 2 else img.shape[2])),
)

size = _pred("size",
    (2, _property_2(lambda img: [int(img.shape[1]), int(img.shape[0])])),
)

element_count = _pred("element_count",
    (2, _pure(lambda img: int(img.size))),
)

is_grayscale = _pred("is_grayscale",
    (1, _check_1(lambda img: img.ndim == 2)),
)

is_color = _pred("is_color",
    (1, _check_1(lambda img: img.ndim == 3 and img.shape[2] == 3)),
)

is_uint8 = _pred("is_uint8",
    (1, _check_1(lambda img: img.dtype == _np.uint8)),
)


# ══════════════════════════════════════════════════════════════════════════
# Arithmetic — Tier 1, pure
# ══════════════════════════════════════════════════════════════════════════


add = _pred("add",
    (3, _pure(lambda a, b: _cv().add(a, b))),
)

subtract = _pred("subtract",
    (3, _pure(lambda a, b: _cv().subtract(a, b))),
)

multiply = _pred("multiply",
    (3, _pure(lambda a, b: _cv().multiply(a, b))),
    (4, _pure(lambda a, b, scale: _cv().multiply(a, b, scale=float(scale)))),
)

divide = _pred("divide",
    (3, _pure(lambda a, b: _cv().divide(a, b))),
    (4, _pure(lambda a, b, scale: _cv().divide(a, b, scale=float(scale)))),
)

absdiff = _pred("absdiff",
    (3, _pure(lambda a, b: _cv().absdiff(a, b))),
)

bitwise_and = _pred("bitwise_and",
    (3, _pure(lambda a, b: _cv().bitwise_and(a, b))),
    (4, _pure(lambda a, b, mask: _cv().bitwise_and(a, b, mask=mask))),
)

bitwise_or = _pred("bitwise_or",
    (3, _pure(lambda a, b: _cv().bitwise_or(a, b))),
    (4, _pure(lambda a, b, mask: _cv().bitwise_or(a, b, mask=mask))),
)

bitwise_xor = _pred("bitwise_xor",
    (3, _pure(lambda a, b: _cv().bitwise_xor(a, b))),
    (4, _pure(lambda a, b, mask: _cv().bitwise_xor(a, b, mask=mask))),
)

bitwise_not = _pred("bitwise_not",
    (2, _pure(lambda a: _cv().bitwise_not(a))),
    (3, _pure(lambda a, mask: _cv().bitwise_not(a, mask=mask))),
)

# ``min`` and ``max`` shadow Python builtins; module-scoped imports
# prevent collisions in user code.
min = _pred("min",
    (3, _pure(lambda a, b: _cv().min(a, b))),
)

max = _pred("max",
    (3, _pure(lambda a, b: _cv().max(a, b))),
)


# ══════════════════════════════════════════════════════════════════════════
# Reductions — Tier 1, pure
# ══════════════════════════════════════════════════════════════════════════


mean = _pred("mean",
    (2, _pure(lambda img: [float(v) for v in _cv().mean(img)])),
    (3, _pure(lambda img, mask:
              [float(v) for v in _cv().mean(img, mask=mask)])),
)


def _min_max_loc(img):
    min_val, max_val, min_loc, max_loc = _cv().minMaxLoc(img)
    return ("min_max", float(min_val), float(max_val),
            [int(v) for v in min_loc], [int(v) for v in max_loc])


def _min_max_loc_masked(img, mask):
    min_val, max_val, min_loc, max_loc = _cv().minMaxLoc(img, mask=mask)
    return ("min_max", float(min_val), float(max_val),
            [int(v) for v in min_loc], [int(v) for v in max_loc])


min_max_loc = _pred("min_max_loc",
    (2, _pure(_min_max_loc)),
    (3, _pure(_min_max_loc_masked)),
)


# ══════════════════════════════════════════════════════════════════════════
# Whole-image transforms — Tier 1, pure
# ══════════════════════════════════════════════════════════════════════════


flip = _pred("flip",
    (3, _pure(lambda img, code: _cv().flip(img, int(code)))),
)

transpose = _pred("transpose",
    (2, _pure(lambda img: _cv().transpose(img))),
)

copy_image = _pred("copy_image",
    (2, _pure(lambda img: img.copy())),
)


# ══════════════════════════════════════════════════════════════════════════
# Handle lifecycle — Tier 3
# ══════════════════════════════════════════════════════════════════════════


def _free_dispatch(this_generator, _proceed, _fail, _catcher,
                   handle_var, trail):
    from clausal.modules.py._opencv_handles import lookup, release
    handle = deref(handle_var)
    try:
        obj = lookup(handle)
    except KeyError:
        yield (_fail, DONE)
        return
    if hasattr(obj, "release"):
        try:
            obj.release()
        except Exception:
            pass
    release(handle)
    yield (_proceed, None)
    yield (_fail, DONE)


free = _pred("free", (1, _free_dispatch))


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # I/O
    "imread", "imwrite", "image_encoded",
    # Properties
    "shape", "dtype", "channels_count", "size", "element_count",
    "is_grayscale", "is_color", "is_uint8",
    # Arithmetic
    "add", "subtract", "multiply", "divide", "absdiff",
    "bitwise_and", "bitwise_or", "bitwise_xor", "bitwise_not",
    "min", "max",
    # Reductions
    "mean", "min_max_loc",
    # Whole-image transforms
    "flip", "transpose", "copy_image",
    # Lifecycle
    "free",
    # Constants — lowercase aliases of cv2 attributes.
    # ALL-CAPS names are not exported because Clausal parses them as
    # logic variables (e.g. ``IMREAD_COLOR`` would be a fresh Var in
    # a goal body, not a constant lookup).
    "imread_color", "imread_grayscale", "imread_unchanged",
    "imread_anydepth", "imread_anycolor",
    "imread_reduced_grayscale_2", "imread_reduced_color_2",
    "imread_reduced_grayscale_4", "imread_reduced_color_4",
    "imread_reduced_grayscale_8", "imread_reduced_color_8",
    "imwrite_jpeg_quality", "imwrite_png_compression",
    "imwrite_webp_quality", "imwrite_tiff_compression",
    "cv_8u", "cv_8s", "cv_16u", "cv_16s", "cv_32s",
    "cv_32f", "cv_64f",
    "norm_inf", "norm_l1", "norm_l2", "norm_l2sqr",
    "norm_hamming", "norm_hamming2", "norm_minmax",
    # Color conversion codes (Phase 2) — common pairs only
    "color_bgr2gray", "color_gray2bgr",
    "color_bgr2rgb", "color_rgb2bgr",
    "color_bgr2hsv", "color_hsv2bgr",
    "color_bgr2hls", "color_hls2bgr",
    "color_bgr2lab", "color_lab2bgr",
    "color_bgr2luv", "color_luv2bgr",
    "color_bgr2ycrcb", "color_ycrcb2bgr",
    "color_bgr2xyz", "color_xyz2bgr",
    "color_bgr2yuv", "color_yuv2bgr",
    "color_bgra2bgr", "color_bgr2bgra",
    "color_rgba2rgb", "color_rgb2rgba",
    "color_bayer_bg2bgr", "color_bayer_gb2bgr",
    "color_bayer_rg2bgr", "color_bayer_gr2bgr",
    # Interpolation flags (Phase 3 / 5)
    "inter_nearest", "inter_linear", "inter_cubic",
    "inter_area", "inter_lanczos4",
    # Border types (Phase 3 / 5)
    "border_constant", "border_replicate", "border_reflect",
    "border_reflect_101", "border_default", "border_wrap", "border_isolated",
    # Morphology operations (Phase 3)
    "morph_erode", "morph_dilate", "morph_open", "morph_close",
    "morph_gradient", "morph_tophat", "morph_blackhat", "morph_hitmiss",
    # Morphology kernel shapes (Phase 3)
    "morph_rect", "morph_ellipse", "morph_cross",
    # Thresholding (Phase 4)
    "thresh_binary", "thresh_binary_inv", "thresh_trunc",
    "thresh_tozero", "thresh_tozero_inv", "thresh_mask",
    "thresh_otsu", "thresh_triangle",
    "adaptive_thresh_mean_c", "adaptive_thresh_gaussian_c",
    # Contour retrieval / approximation (Phase 4)
    "retr_external", "retr_list", "retr_ccomp", "retr_tree", "retr_floodfill",
    "chain_approx_none", "chain_approx_simple",
    "chain_approx_tc89_l1", "chain_approx_tc89_kcos",
    # Whole-image rotate / warp flags (Phase 5)
    "rotate_90_clockwise", "rotate_180", "rotate_90_counterclockwise",
    "warp_inverse_map", "warp_fill_outliers",
    "warp_polar_linear", "warp_polar_log",
    # Drawing (Phase 6)
    "line_4", "line_8", "line_aa", "filled",
    "font_hershey_simplex", "font_hershey_plain",
    "font_hershey_duplex", "font_hershey_complex",
    "font_hershey_triplex", "font_hershey_complex_small",
    "font_hershey_script_simplex", "font_hershey_script_complex",
    "font_italic",
    "marker_cross", "marker_tilted_cross", "marker_star",
    "marker_diamond", "marker_square",
    "marker_triangle_up", "marker_triangle_down",
    "draw_matches_flags_default",
    "draw_matches_flags_draw_over_outimg",
    "draw_matches_flags_not_draw_single_points",
    "draw_matches_flags_draw_rich_keypoints",
    # Robust estimators / fundamental matrix / PnP (Phase 9)
    "ransac", "lmeds", "rho",
    "fm_7point", "fm_8point", "fm_ransac", "fm_lmeds",
    "solvepnp_iterative", "solvepnp_epnp", "solvepnp_p3p",
    "solvepnp_dls", "solvepnp_upnp", "solvepnp_ap3p",
    "solvepnp_ippe", "solvepnp_ippe_square", "solvepnp_sqpnp",
    # Calibration / chessboard / DFT (Phase 9)
    "calib_use_intrinsic_guess", "calib_fix_principal_point",
    "calib_fix_aspect_ratio", "calib_zero_tangent_dist",
    "calib_fix_k1", "calib_fix_k2", "calib_fix_k3",
    "calib_fix_k4", "calib_fix_k5", "calib_fix_k6",
    "calib_rational_model",
    "calib_cb_adaptive_thresh", "calib_cb_normalize_image",
    "calib_cb_filter_quads", "calib_cb_fast_check",
    "dft_inverse", "dft_scale", "dft_rows",
    "dft_complex_output", "dft_real_output", "dft_complex_input",
]
