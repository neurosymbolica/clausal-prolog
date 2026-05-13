"""clausal.modules.opencv_features — Feature detectors and matchers.

Phase 7 — Features and Matching.

Six classical feature detectors (ORB, SIFT, AKAZE, KAZE, BRISK,
FAST), two matchers (Brute Force, FLANN), and the corresponding
``cv2.KeyPoint`` / ``cv2.DMatch`` decomposition predicates.

Detectors and matchers are **handle-based (Tier 3)**. They are
**read-only after construction** — `cv2.ORB.detect` and
`cv2.BFMatcher.match` do not mutate the detector or matcher object,
so backtracking over detector/matcher operations is safe without
copying or restoring state. See ``_opencv_handles.py``.

Use::

    -import_from(opencv_features, [
        make_orb, make_sift, make_akaze,
        detect, compute, detect_and_compute,
        make_bf_matcher, make_flann_matcher,
        match, knn_match, radius_match,
        keypoint, match_pair, dmatch,
    ])
    -import_from(opencv, [norm_hamming, norm_l2, free])

Predicate catalogue
-------------------
Detector/extractor handles:
    make_orb(HANDLE) / make_orb(OPTS, HANDLE)
    make_sift(...) / make_akaze(...) / make_kaze(...) /
      make_brisk(...) / make_fast(...)

Detection / description:
    detect(HANDLE, IMG, KEYPOINTS)
    detect(HANDLE, IMG, MASK, KEYPOINTS)
    compute(HANDLE, IMG, KEYPOINTS, DESCRIPTORS)
    detect_and_compute(HANDLE, IMG, KEYPOINTS, DESCRIPTORS)
    detect_and_compute(HANDLE, IMG, MASK, KEYPOINTS, DESCRIPTORS)

Matcher handles:
    make_bf_matcher(HANDLE)
    make_bf_matcher(NORM_TYPE, HANDLE)
    make_bf_matcher(NORM_TYPE, CROSS_CHECK, HANDLE)
    make_flann_matcher(HANDLE)
    make_flann_matcher(INDEX_PARAMS, SEARCH_PARAMS, HANDLE)

Matching:
    match(MATCHER, QUERY_DESC, TRAIN_DESC, MATCHES)
    knn_match(MATCHER, QUERY_DESC, TRAIN_DESC, K, MATCHES)
    radius_match(MATCHER, QUERY_DESC, TRAIN_DESC, MAX_DIST, MATCHES)

Term enumeration / decomposition:
    keypoint(KP_LIST, KP)                              Nondet enum
    keypoint(KP, PT, SIZE, ANGLE, RESPONSE, OCTAVE, CLASS_ID)   Bidirectional
    match_pair(MATCH_LIST, M)                          Nondet enum
    dmatch(M, QUERY_IDX, TRAIN_IDX, IMG_IDX, DISTANCE) Decompose
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _deep_deref
from clausal.modules.opencv import _cv
from clausal.modules._opencv_handles import alloc, lookup


# ── Detector option-dict to cv2-kwarg mapping ─────────────────────────────
#
# Users write snake_case opts dicts (Clausal style). cv2 takes
# camelCase kwargs. The mapping is small and per-detector, so each
# is spelled out explicitly rather than meta-programmed.


_ORB_OPTS = {
    "n_features":     "nfeatures",
    "scale_factor":   "scaleFactor",
    "n_levels":       "nlevels",
    "edge_threshold": "edgeThreshold",
    "first_level":    "firstLevel",
    "wta_k":          "WTA_K",
    "score_type":     "scoreType",
    "patch_size":     "patchSize",
    "fast_threshold": "fastThreshold",
}

_SIFT_OPTS = {
    "n_features":           "nfeatures",
    "n_octave_layers":      "nOctaveLayers",
    "contrast_threshold":   "contrastThreshold",
    "edge_threshold":        "edgeThreshold",
    "sigma":                "sigma",
}

_AKAZE_OPTS = {
    "descriptor_type":     "descriptor_type",
    "descriptor_size":     "descriptor_size",
    "descriptor_channels": "descriptor_channels",
    "threshold":           "threshold",
    "n_octaves":           "nOctaves",
    "n_octave_layers":     "nOctaveLayers",
    "diffusivity":         "diffusivity",
}

_KAZE_OPTS = {
    "extended":         "extended",
    "upright":          "upright",
    "threshold":        "threshold",
    "n_octaves":        "nOctaves",
    "n_octave_layers":  "nOctaveLayers",
    "diffusivity":      "diffusivity",
}

_BRISK_OPTS = {
    "thresh":           "thresh",
    "octaves":          "octaves",
    "pattern_scale":    "patternScale",
}

_FAST_OPTS = {
    "threshold":           "threshold",
    "nonmax_suppression":  "nonmaxSuppression",
    "type":                "type",
}


def _kwargs(mapping, opts):
    return {mapping[k]: v for k, v in opts.items() if k in mapping}


# ── Detector constructors ─────────────────────────────────────────────────


def _make_factory(create, opts_mapping):
    """Return a 2-tuple of (no-opts, opts) factory functions."""
    def _no_opts():
        return alloc(create())
    def _with_opts(opts):
        return alloc(create(**_kwargs(opts_mapping, opts)))
    return _no_opts, _with_opts


def _orb():       return _cv().ORB_create()
def _orb_o(opts): return _cv().ORB_create(**_kwargs(_ORB_OPTS, opts))

make_orb = _pred("make_orb",
    (1, _pure(lambda: alloc(_orb()))),
    (2, _pure(lambda opts: alloc(_orb_o(opts)))),
)


def _sift():       return _cv().SIFT_create()
def _sift_o(opts): return _cv().SIFT_create(**_kwargs(_SIFT_OPTS, opts))

make_sift = _pred("make_sift",
    (1, _pure(lambda: alloc(_sift()))),
    (2, _pure(lambda opts: alloc(_sift_o(opts)))),
)


def _akaze():       return _cv().AKAZE_create()
def _akaze_o(opts): return _cv().AKAZE_create(**_kwargs(_AKAZE_OPTS, opts))

make_akaze = _pred("make_akaze",
    (1, _pure(lambda: alloc(_akaze()))),
    (2, _pure(lambda opts: alloc(_akaze_o(opts)))),
)


def _kaze():       return _cv().KAZE_create()
def _kaze_o(opts): return _cv().KAZE_create(**_kwargs(_KAZE_OPTS, opts))

make_kaze = _pred("make_kaze",
    (1, _pure(lambda: alloc(_kaze()))),
    (2, _pure(lambda opts: alloc(_kaze_o(opts)))),
)


def _brisk():       return _cv().BRISK_create()
def _brisk_o(opts): return _cv().BRISK_create(**_kwargs(_BRISK_OPTS, opts))

make_brisk = _pred("make_brisk",
    (1, _pure(lambda: alloc(_brisk()))),
    (2, _pure(lambda opts: alloc(_brisk_o(opts)))),
)


def _fast():       return _cv().FastFeatureDetector_create()
def _fast_o(opts): return _cv().FastFeatureDetector_create(**_kwargs(_FAST_OPTS, opts))

make_fast = _pred("make_fast",
    (1, _pure(lambda: alloc(_fast()))),
    (2, _pure(lambda opts: alloc(_fast_o(opts)))),
)


# ── Detector / extractor operations ───────────────────────────────────────


def _detect(handle, img):
    return list(lookup(handle).detect(img))

def _detect_mask(handle, img, mask):
    return list(lookup(handle).detect(img, mask=mask))


detect = _pred("detect",
    (3, _pure(_detect)),
    (4, _pure(_detect_mask)),
)


def _compute(handle, img, kps):
    kps_out, descs = lookup(handle).compute(img, list(kps))
    return descs


compute = _pred("compute",
    (4, _pure(_compute)),
)


def _detect_and_compute_4(this_generator, _proceed, _fail, _catcher,
                           handle_v, img_v, kps_v, descs_v, trail):
    handle = deref(handle_v)
    img = _deep_deref(img_v)
    try:
        kps, descs = lookup(handle).detectAndCompute(img, None)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(kps_v, list(kps), trail) and unify(descs_v, descs, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


def _detect_and_compute_5(this_generator, _proceed, _fail, _catcher,
                           handle_v, img_v, mask_v, kps_v, descs_v, trail):
    handle = deref(handle_v)
    img = _deep_deref(img_v)
    mask = _deep_deref(mask_v)
    try:
        kps, descs = lookup(handle).detectAndCompute(img, mask)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(kps_v, list(kps), trail) and unify(descs_v, descs, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


detect_and_compute = _pred("detect_and_compute",
    (4, _detect_and_compute_4),
    (5, _detect_and_compute_5),
)


# ── Matchers ──────────────────────────────────────────────────────────────


def _bf_default():
    return _cv().BFMatcher()

def _bf_norm(norm_type):
    return _cv().BFMatcher(int(norm_type))

def _bf_norm_cross(norm_type, cross_check):
    return _cv().BFMatcher(int(norm_type), bool(cross_check))


make_bf_matcher = _pred("make_bf_matcher",
    (1, _pure(lambda: alloc(_bf_default()))),
    (2, _pure(lambda norm_type: alloc(_bf_norm(norm_type)))),
    (3, _pure(lambda norm_type, cross_check:
              alloc(_bf_norm_cross(norm_type, cross_check)))),
)


def _flann_default():
    # Defaults from cv2 tutorial: KDTree, 5 trees, 50 checks.
    index_params = dict(algorithm=1, trees=5)
    search_params = dict(checks=50)
    return _cv().FlannBasedMatcher(index_params, search_params)

def _flann(index_params, search_params):
    return _cv().FlannBasedMatcher(dict(index_params), dict(search_params))


make_flann_matcher = _pred("make_flann_matcher",
    (1, _pure(lambda: alloc(_flann_default()))),
    (3, _pure(lambda ip, sp: alloc(_flann(ip, sp)))),
)


# ── Matching operations ───────────────────────────────────────────────────


def _match(matcher, query, train):
    return list(lookup(matcher).match(query, train))


def _knn_match(matcher, query, train, k):
    return [list(m) for m in lookup(matcher).knnMatch(query, train, int(k))]


def _radius_match(matcher, query, train, max_dist):
    return [list(m) for m in lookup(matcher).radiusMatch(query, train,
                                                            float(max_dist))]


match = _pred("match",
    (4, _pure(_match)),
)

knn_match = _pred("knn_match",
    (5, _pure(_knn_match)),
)

radius_match = _pred("radius_match",
    (5, _pure(_radius_match)),
)


# ══════════════════════════════════════════════════════════════════════════
# Term enumeration / decomposition
# ══════════════════════════════════════════════════════════════════════════


def _enum_dispatch(this_generator, _proceed, _fail, _catcher,
                   list_v, item_v, trail):
    lst = _deep_deref(list_v)
    if not isinstance(lst, (list, tuple)):
        yield (_fail, DONE)
        return
    for item in lst:
        mark = trail.mark()
        if unify(item_v, item, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _kp_decompose(kp):
    return (
        [float(kp.pt[0]), float(kp.pt[1])],
        float(kp.size),
        float(kp.angle),
        float(kp.response),
        int(kp.octave),
        int(kp.class_id),
    )


def _kp_construct(pt, size, angle, response, octave, class_id):
    return _cv().KeyPoint(
        float(pt[0]), float(pt[1]),
        float(size), float(angle), float(response),
        int(octave), int(class_id),
    )


def _keypoint_7(this_generator, _proceed, _fail, _catcher,
                kp_v, pt_v, size_v, angle_v, resp_v, octave_v, class_id_v,
                trail):
    """Bidirectional: decompose if KP is bound, construct if all fields bound."""
    kp = deref(kp_v)
    fields = [deref(v) for v in
              (pt_v, size_v, angle_v, resp_v, octave_v, class_id_v)]
    kp_unbound = is_var(kp)
    fields_bound = [not is_var(f) for f in fields]

    if not kp_unbound:
        # Decompose
        try:
            pt, size, angle, resp, octave, class_id = _kp_decompose(kp)
        except Exception:
            yield (_fail, DONE)
            return
        if (unify(pt_v, pt, trail)
                and unify(size_v, size, trail)
                and unify(angle_v, angle, trail)
                and unify(resp_v, resp, trail)
                and unify(octave_v, octave, trail)
                and unify(class_id_v, class_id, trail)):
            yield (_proceed, None)
    elif all(fields_bound):
        # Construct
        try:
            pt_d = _deep_deref(pt_v)
            new_kp = _kp_construct(pt_d, *fields[1:])
        except Exception:
            yield (_fail, DONE)
            return
        if unify(kp_v, new_kp, trail):
            yield (_proceed, None)
    yield (_fail, DONE)


keypoint = _pred("keypoint",
    (2, _enum_dispatch),
    (7, _keypoint_7),
)


match_pair = _pred("match_pair",
    (2, _enum_dispatch),
)


def _dmatch_decompose(m):
    return (
        int(m.queryIdx),
        int(m.trainIdx),
        int(m.imgIdx),
        float(m.distance),
    )


def _dmatch_5(this_generator, _proceed, _fail, _catcher,
              m_v, qidx_v, tidx_v, iidx_v, dist_v, trail):
    m = deref(m_v)
    try:
        qidx, tidx, iidx, dist = _dmatch_decompose(m)
    except Exception:
        yield (_fail, DONE)
        return
    if (unify(qidx_v, qidx, trail)
            and unify(tidx_v, tidx, trail)
            and unify(iidx_v, iidx, trail)
            and unify(dist_v, dist, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


dmatch = _pred("dmatch", (5, _dmatch_5))


__all__ = [
    # Detector constructors
    "make_orb", "make_sift", "make_akaze", "make_kaze",
    "make_brisk", "make_fast",
    # Detection / description
    "detect", "compute", "detect_and_compute",
    # Matchers
    "make_bf_matcher", "make_flann_matcher",
    # Matching
    "match", "knn_match", "radius_match",
    # Term enumeration / decomposition
    "keypoint", "match_pair", "dmatch",
]
