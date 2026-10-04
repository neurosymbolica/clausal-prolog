"""clausal.modules.py.opencv_objdetect — Classical object detectors.

Phase 8 — Object Detection.

Haar/LBP cascade classifiers and HOG descriptors. Pre-deep-learning
detectors that are still useful for small problems, embedded use,
and as classical baselines.

Statefulness
------------
- ``cv2.CascadeClassifier`` is **read-only after loading** — once an
  XML is loaded, the cascade does not change. Tier 3 handle, no
  copying.
- ``cv2.HOGDescriptor`` is mostly read-only, **except for**
  ``setSVMDetector(svm)`` which installs a new SVM vector
  in-place. The wrapper exposes this as
  ``hog_set_svm_detector(HOG0, SVM, HOG1)`` — explicit state
  threading: the input handle is unchanged, a copy of the HOG
  descriptor with the SVM installed is registered under a new
  handle, and the new handle is returned. Backtracking past the call
  abandons HOG1; HOG0 stays valid.

The standard ``free/1`` predicate (Phase 1) releases handles.

Use::

    -import_from(opencv_objdetect, [
        make_cascade_classifier, detect_multi_scale, haar_cascade_path,
        make_hog, hog_compute, hog_detect,
        hog_set_svm_detector, hog_default_people_detector,
    ])
    -import_from(opencv, [free])

Predicate catalogue
-------------------
Cascade:
    make_cascade_classifier(XML_PATH, HANDLE)
    detect_multi_scale(HANDLE, IMG, RECTS)
    detect_multi_scale(HANDLE, IMG, SCALE_FACTOR, RECTS)
    detect_multi_scale(HANDLE, IMG, SCALE_FACTOR, MIN_NEIGHBORS, RECTS)
    detect_multi_scale(HANDLE, IMG, SCALE_FACTOR, MIN_NEIGHBORS, MIN_SIZE, RECTS)
    haar_cascade_path(NAME, PATH)        Registry of bundled cascades
                                         (NAME an atom, PATH a string)

HOG:
    make_hog(HANDLE)
    make_hog(OPTS, HANDLE)
    hog_compute(HANDLE, IMG, DESCRIPTORS)
    hog_detect(HANDLE, IMG, RECTS)
    hog_detect(HANDLE, IMG, OPTS, RECTS)
    hog_set_svm_detector(HOG0, SVM, HOG1)        State-threaded
    hog_default_people_detector(SVM)
"""

from __future__ import annotations

import os as _os

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _fact_table_2, _deep_deref
from clausal.modules.py.opencv import _cv
from clausal.modules.py._opencv_handles import alloc, lookup
from clausal.modules.py import text_result


# ── Cascade classifier ───────────────────────────────────────────────────


def _make_cascade(xml_path):
    cv = _cv()
    cascade = cv.CascadeClassifier(str(xml_path))
    if cascade.empty():
        raise RuntimeError(f"Failed to load cascade: {xml_path!r}")
    return alloc(cascade)


make_cascade_classifier = _pred("make_cascade_classifier",
    (2, _pure(_make_cascade)),
)


def _rectify_detections(detections):
    """``detectMultiScale`` returns ()/[] when nothing is found, or an Nx4
    array otherwise. Convert each row to a tagged ``("rect", x, y, w, h)``."""
    rects = []
    for row in detections:
        x, y, w, h = (int(v) for v in row)
        rects.append(("rect", x, y, w, h))
    return rects


def _dms_3(handle, img):
    cascade = lookup(handle)
    return _rectify_detections(cascade.detectMultiScale(img))

def _dms_4(handle, img, sf):
    cascade = lookup(handle)
    return _rectify_detections(
        cascade.detectMultiScale(img, scaleFactor=float(sf)))

def _dms_5(handle, img, sf, mn):
    cascade = lookup(handle)
    return _rectify_detections(
        cascade.detectMultiScale(img, scaleFactor=float(sf),
                                   minNeighbors=int(mn)))

def _dms_6(handle, img, sf, mn, min_size):
    cascade = lookup(handle)
    return _rectify_detections(
        cascade.detectMultiScale(img, scaleFactor=float(sf),
                                   minNeighbors=int(mn),
                                   minSize=tuple(min_size)))


detect_multi_scale = _pred("detect_multi_scale",
    (3, _pure(_dms_3)),
    (4, _pure(_dms_4)),
    (5, _pure(_dms_5)),
    (6, _pure(_dms_6)),
)


# ── Registry of bundled Haar cascades ────────────────────────────────────


def _haar_facts():
    base = _cv().data.haarcascades
    entries = [
        ("face",          "haarcascade_frontalface_default.xml"),
        ("face_alt",      "haarcascade_frontalface_alt.xml"),
        ("face_alt2",     "haarcascade_frontalface_alt2.xml"),
        ("profile_face",  "haarcascade_profileface.xml"),
        ("eye",           "haarcascade_eye.xml"),
        ("eye_tree_eyeglasses", "haarcascade_eye_tree_eyeglasses.xml"),
        ("smile",         "haarcascade_smile.xml"),
        ("body",          "haarcascade_fullbody.xml"),
        ("upper_body",    "haarcascade_upperbody.xml"),
        ("lower_body",    "haarcascade_lowerbody.xml"),
        ("license_plate", "haarcascade_russian_plate_number.xml"),
    ]
    # Drop entries whose XML isn't shipped in this opencv build.  The NAME
    # is a key and stays an atom; the PATH is free-form text, a string
    # ('$chars', p) (ruled 2026-10-04).
    return [(name, text_result(_os.path.join(base, fname)))
            for name, fname in entries
            if _os.path.exists(_os.path.join(base, fname))]


haar_cascade_path = _pred("haar_cascade_path",
    (2, _fact_table_2(_haar_facts)),
)


# ── HOG descriptor ────────────────────────────────────────────────────────
#
# HOGDescriptor is constructed by *positional* args:
#   HOGDescriptor(winSize, blockSize, blockStride, cellSize, nbins)
# Defaults match cv2's documented defaults for pedestrian detection.


_HOG_DEFAULTS = {
    "win_size":     (64, 128),
    "block_size":   (16, 16),
    "block_stride": (8, 8),
    "cell_size":    (8, 8),
    "nbins":        9,
}


def _hog_from_opts(opts):
    cv = _cv()
    win    = tuple(opts.get("win_size",     _HOG_DEFAULTS["win_size"]))
    block  = tuple(opts.get("block_size",   _HOG_DEFAULTS["block_size"]))
    stride = tuple(opts.get("block_stride", _HOG_DEFAULTS["block_stride"]))
    cell   = tuple(opts.get("cell_size",    _HOG_DEFAULTS["cell_size"]))
    nbins  = int(opts.get("nbins",          _HOG_DEFAULTS["nbins"]))
    return cv.HOGDescriptor(win, block, stride, cell, nbins)


def _make_hog_default():
    return alloc(_cv().HOGDescriptor())


def _make_hog_with_opts(opts):
    return alloc(_hog_from_opts(opts))


make_hog = _pred("make_hog",
    (1, _pure(_make_hog_default)),
    (2, _pure(_make_hog_with_opts)),
)


def _hog_compute(handle, img):
    return lookup(handle).compute(img)


hog_compute = _pred("hog_compute",
    (3, _pure(_hog_compute)),
)


def _hog_detect_3(handle, img):
    hog = lookup(handle)
    rects, _weights = hog.detectMultiScale(img)
    return [("rect", int(x), int(y), int(w), int(h))
            for x, y, w, h in rects]


def _hog_detect_4(handle, img, opts):
    hog = lookup(handle)
    kwargs = {}
    if "win_stride" in opts: kwargs["winStride"] = tuple(opts["win_stride"])
    if "padding"    in opts: kwargs["padding"]   = tuple(opts["padding"])
    if "scale"      in opts: kwargs["scale"]     = float(opts["scale"])
    rects, _weights = hog.detectMultiScale(img, **kwargs)
    return [("rect", int(x), int(y), int(w), int(h))
            for x, y, w, h in rects]


hog_detect = _pred("hog_detect",
    (3, _pure(_hog_detect_3)),
    (4, _pure(_hog_detect_4)),
)


def _copy_hog_descriptor(hog):
    """Construct a fresh HOGDescriptor with the same parameters as *hog*.

    Used by ``hog_set_svm_detector`` to install an SVM on a copy
    rather than mutating the input handle's underlying object.
    """
    return _cv().HOGDescriptor(
        hog.winSize, hog.blockSize, hog.blockStride,
        hog.cellSize, hog.nbins,
    )


def _hog_set_svm(handle0, svm):
    hog0 = lookup(handle0)
    new_hog = _copy_hog_descriptor(hog0)
    new_hog.setSVMDetector(svm)
    return alloc(new_hog)


hog_set_svm_detector = _pred("hog_set_svm_detector",
    (3, _pure(_hog_set_svm)),
)


def _default_people_svm():
    return _cv().HOGDescriptor_getDefaultPeopleDetector()


hog_default_people_detector = _pred("hog_default_people_detector",
    (1, _pure(_default_people_svm)),
)


__all__ = [
    # Cascade
    "make_cascade_classifier", "detect_multi_scale", "haar_cascade_path",
    # HOG
    "make_hog", "hog_compute", "hog_detect",
    "hog_set_svm_detector", "hog_default_people_detector",
]
