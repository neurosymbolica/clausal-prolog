"""clausal.modules.py.scipy_ndimage — scipy.ndimage predicates for Clausal.

Provides N-dimensional image processing routines from scipy.ndimage as
importable predicate objects for use in .clausal files via::

    -import_from(scipy_ndimage, [GaussianFilter, Label, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_ndimage, [GaussianFilter, ...])

All predicates are **Tier 1 — pure functions**: accept NumPy arrays and return
results directly in ``RESULT``.

Predicate catalogue
-------------------
Smoothing filters:
    GaussianFilter(INPUT, SIGMA, RESULT)
    UniformFilter(INPUT, RESULT)
    UniformFilter(INPUT, SIZE, RESULT)
    MedianFilter(INPUT, SIZE, RESULT)

Convolution:
    Convolve(INPUT, WEIGHTS, RESULT)

Morphological operations (binary):
    BinaryErosion(INPUT, RESULT)
    BinaryDilation(INPUT, RESULT)
    BinaryOpening(INPUT, RESULT)
    BinaryClosing(INPUT, RESULT)

Connected-component labelling:
    Label(INPUT, RESULT)
        RESULT: dict with keys 'label_array' and 'num_features'

Geometric transforms:
    Zoom(INPUT, ZOOM, RESULT)
    Rotate(INPUT, ANGLE, RESULT)
    Shift(INPUT, SHIFT, RESULT)

Measurement:
    FindObjects(INPUT, RESULT)
        RESULT: list of slice-tuple regions per labelled component
    CenterOfMass(INPUT, RESULT)
        RESULT: (row, col, ...) centroid tuple for the whole array
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Lazy scipy.ndimage import ──────────────────────────────────────────────

_scipy_ndimage = None
_ndimage_lock = _threading.Lock()


def _ensure_ndimage():
    global _scipy_ndimage
    if _scipy_ndimage is not None:
        return
    with _ndimage_lock:
        if _scipy_ndimage is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_ndimage = _import_stdlib("scipy.ndimage")


def _ndi():
    _ensure_ndimage()
    return _scipy_ndimage


# ── Dispatch function factory ──────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: dereference inputs, call scipy, unify RESULT."""
    def dispatch(this_generator, parent, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Smoothing filters ──────────────────────────────────────────────────────

GaussianFilter = _pred("GaussianFilter",
    (3, _dispatch_fn(lambda inp, sigma:
        _ndi().gaussian_filter(inp, sigma))),
)

UniformFilter = _pred("UniformFilter",
    (2, _dispatch_fn(lambda inp:
        _ndi().uniform_filter(inp))),
    (3, _dispatch_fn(lambda inp, size:
        _ndi().uniform_filter(inp, size=size))),
)

MedianFilter = _pred("MedianFilter",
    (3, _dispatch_fn(lambda inp, size:
        _ndi().median_filter(inp, size=size))),
)


# ── Convolution ────────────────────────────────────────────────────────────

Convolve = _pred("Convolve",
    (3, _dispatch_fn(lambda inp, weights:
        _ndi().convolve(inp, weights))),
)


# ── Connected-component labelling ──────────────────────────────────────────

def _label_fn(this_generator, parent, inp, result_var, trail):
    inp = deref(inp)
    try:
        labeled_array, num_features = _ndi().label(inp)
    except Exception:
        yield (parent, DONE)
        return
    out = {"label_array": labeled_array, "num_features": num_features}
    try:
        ok = bool(unify(result_var, out, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (parent, None)
    yield (parent, DONE)


Label = ModulePredicate("Label")
Label._register(2, _label_fn)


# ── Morphological operations ───────────────────────────────────────────────

BinaryErosion = _pred("BinaryErosion",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_erosion(inp))),
)

BinaryDilation = _pred("BinaryDilation",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_dilation(inp))),
)

BinaryOpening = _pred("BinaryOpening",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_opening(inp))),
)

BinaryClosing = _pred("BinaryClosing",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_closing(inp))),
)


# ── Geometric transforms ───────────────────────────────────────────────────

Zoom = _pred("Zoom",
    (3, _dispatch_fn(lambda inp, zoom:
        _ndi().zoom(inp, zoom))),
)

Rotate = _pred("Rotate",
    (3, _dispatch_fn(lambda inp, angle:
        _ndi().rotate(inp, angle))),
)

Shift = _pred("Shift",
    (3, _dispatch_fn(lambda inp, shift:
        _ndi().shift(inp, shift))),
)


# ── Measurement ────────────────────────────────────────────────────────────

FindObjects = _pred("FindObjects",
    (2, _dispatch_fn(lambda inp:
        _ndi().find_objects(inp))),
)

CenterOfMass = _pred("CenterOfMass",
    (2, _dispatch_fn(lambda inp:
        _ndi().center_of_mass(inp))),
)
