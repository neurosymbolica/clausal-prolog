"""clausal.modules.py.scipy_ndimage — scipy.ndimage predicates for Clausal.

Provides N-dimensional image processing routines from scipy.ndimage as
importable predicate objects for use in .clausal files via::

    -import_from(scipy_ndimage, [gaussian_filter, label, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_ndimage, [gaussian_filter, ...])

All predicates are **Tier 1 — pure functions**: accept NumPy arrays and return
results directly in ``RESULT``.

Predicate catalogue
-------------------
Smoothing filters:
    gaussian_filter(INPUT, SIGMA, RESULT)
    uniform_filter(INPUT, RESULT)
    uniform_filter(INPUT, SIZE, RESULT)
    median_filter(INPUT, SIZE, RESULT)

Convolution:
    convolve(INPUT, WEIGHTS, RESULT)

Morphological operations (binary):
    binary_erosion(INPUT, RESULT)
    binary_dilation(INPUT, RESULT)
    binary_opening(INPUT, RESULT)
    binary_closing(INPUT, RESULT)

Connected-component labelling:
    label(INPUT, RESULT)
        RESULT: dict with keys 'label_array' and 'num_features'

Geometric transforms:
    zoom(INPUT, ZOOM, RESULT)
    rotate(INPUT, ANGLE, RESULT)
    shift(INPUT, SHIFT, RESULT)

Measurement:
    find_objects(INPUT, RESULT)
        RESULT: list of slice-tuple regions per labelled component
    center_of_mass(INPUT, RESULT)
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
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Smoothing filters ──────────────────────────────────────────────────────

gaussian_filter = _pred("gaussian_filter",
    (3, _dispatch_fn(lambda inp, sigma:
        _ndi().gaussian_filter(inp, sigma))),
)

uniform_filter = _pred("uniform_filter",
    (2, _dispatch_fn(lambda inp:
        _ndi().uniform_filter(inp))),
    (3, _dispatch_fn(lambda inp, size:
        _ndi().uniform_filter(inp, size=size))),
)

median_filter = _pred("median_filter",
    (3, _dispatch_fn(lambda inp, size:
        _ndi().median_filter(inp, size=size))),
)


# ── Convolution ────────────────────────────────────────────────────────────

convolve = _pred("convolve",
    (3, _dispatch_fn(lambda inp, weights:
        _ndi().convolve(inp, weights))),
)


# ── Connected-component labelling ──────────────────────────────────────────

def _label_fn(this_generator, _proceed, _fail, _catcher, inp, result_var, trail):
    inp = deref(inp)
    try:
        labeled_array, num_features = _ndi().label(inp)
    except Exception:
        yield (_fail, DONE)
        return
    out = {"label_array": labeled_array, "num_features": num_features}
    try:
        ok = bool(unify(result_var, out, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


label = ModulePredicate("label")
label._register(2, _label_fn)


# ── Morphological operations ───────────────────────────────────────────────

binary_erosion = _pred("binary_erosion",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_erosion(inp))),
)

binary_dilation = _pred("binary_dilation",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_dilation(inp))),
)

binary_opening = _pred("binary_opening",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_opening(inp))),
)

binary_closing = _pred("binary_closing",
    (2, _dispatch_fn(lambda inp:
        _ndi().binary_closing(inp))),
)


# ── Geometric transforms ───────────────────────────────────────────────────

zoom = _pred("zoom",
    (3, _dispatch_fn(lambda inp, zoom:
        _ndi().zoom(inp, zoom))),
)

rotate = _pred("rotate",
    (3, _dispatch_fn(lambda inp, angle:
        _ndi().rotate(inp, angle))),
)

shift = _pred("shift",
    (3, _dispatch_fn(lambda inp, shift:
        _ndi().shift(inp, shift))),
)


# ── Measurement ────────────────────────────────────────────────────────────

find_objects = _pred("find_objects",
    (2, _dispatch_fn(lambda inp:
        _ndi().find_objects(inp))),
)

center_of_mass = _pred("center_of_mass",
    (2, _dispatch_fn(lambda inp:
        _ndi().center_of_mass(inp))),
)
