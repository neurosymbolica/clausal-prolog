"""clausal.modules.scipy_fft — scipy.fft predicates for Clausal.

Provides fast Fourier transform routines from scipy.fft as importable
predicate objects for use in .clausal files via::

    -import_from(scipy_fft, [FFTransform, RealFFT, FFTShift, FFTFrequencies, ...])

All predicates are **Tier 1 — pure functions**: accept NumPy arrays and
return transformed arrays directly in RESULT.

Predicate catalogue
-------------------
All core transforms are bidirectional: X ground → forward; RESULT ground → inverse.

1-D transforms:
    FFTransform(X, Y)                    — fft(x) / ifft(y)
    FFTransform(X, N, Y)                 — with output length N

2-D transforms:
    FFTransform2D(X, Y)                  — fft2(x) / ifft2(y)
    FFTransform2D(X, S, Y)               — with output shape S=(rows, cols)

N-D transforms:
    FFTransformND(X, Y)                  — fftn(x) / ifftn(y)
    FFTransformND(X, S, Y)               — with output shape S (list of lengths)

Real-input transforms:
    RealFFT(X, Y)                        — rfft(x) / irfft(y)
    RealFFT(X, N, Y)                     — with output/input length N

Cosine / Sine transforms:
    DiscreteCosineTransform(X, Y)        — dct(x) / idct(y)
    DiscreteCosineTransform(X, TYPE, Y)  — with explicit type (1–4)
    DiscreteSineTransform(X, Y)          — dst(x) / idst(y)
    DiscreteSineTransform(X, TYPE, Y)    — with explicit type

Utility:
    FFTFrequencies(N, RESULT)            — DFT sample frequencies for length-N output
    FFTFrequencies(N, D, RESULT)         — with sample spacing D (default 1.0)
    RealFFTFrequencies(N, RESULT)        — frequencies for length-N real FFT
    RealFFTFrequencies(N, D, RESULT)     — with sample spacing D
    FFTShift(X, Y)                       — fftshift(x) / ifftshift(y)
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate
from clausal.modules.py._scipy_relations import _bidir_dispatch, _fft_bidir_n
from clausal.modules.py._scipy_units import make_quantity_aware, PASS_THROUGH_FIRST


# ── Lazy scipy.fft import ──────────────────────────────────────────────────

_scipy_fft = None
_fft_lock = _threading.Lock()


def _ensure_fft():
    global _scipy_fft
    if _scipy_fft is not None:
        return
    with _fft_lock:
        if _scipy_fft is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_fft = _import_stdlib("scipy.fft")


def _fft():
    _ensure_fft()
    return _scipy_fft


# ── Dispatch function factory ─────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: dereference inputs, call scipy, unify RESULT.

    *call* is wrapped with :func:`make_quantity_aware` using
    :data:`PASS_THROUGH_FIRST`: FFT output has the same physical dimensions
    as the input signal.
    """
    q_call = make_quantity_aware(call, PASS_THROUGH_FIRST)

    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = q_call(*inputs)
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


def _fft_fn(attr: str):
    """Return a quantity-aware callable for ``scipy.fft.<attr>(x)``.

    The output has the same dims as the input (pass-through).
    """
    def call(x):
        return getattr(_fft(), attr)(x)
    return make_quantity_aware(call, PASS_THROUGH_FIRST)


def _pred(name: str, *arity_fns) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


def _pred_bidir(name: str, *arity_dispatches) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, already-wrapped dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, dispatch_fn in arity_dispatches:
        p._dispatch_fns[arity] = dispatch_fn
    return p


# ── 1-D transforms ────────────────────────────────────────────────────────

FFTransform = _pred_bidir("FFTransform",
    (2, _bidir_dispatch(_fft_fn("fft"), _fft_fn("ifft"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, n: _fft().fft(x, n=n), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, n: _fft().ifft(y, n=n), PASS_THROUGH_FIRST))),
)


# ── 2-D transforms ────────────────────────────────────────────────────────

FFTransform2D = _pred_bidir("FFTransform2D",
    (2, _bidir_dispatch(_fft_fn("fft2"), _fft_fn("ifft2"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, s: _fft().fft2(x, s=s), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, s: _fft().ifft2(y, s=s), PASS_THROUGH_FIRST))),
)


# ── N-D transforms ────────────────────────────────────────────────────────

FFTransformND = _pred_bidir("FFTransformND",
    (2, _bidir_dispatch(_fft_fn("fftn"), _fft_fn("ifftn"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, s: _fft().fftn(x, s=s), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, s: _fft().ifftn(y, s=s), PASS_THROUGH_FIRST))),
)


# ── Real-input transforms ─────────────────────────────────────────────────

RealFFT = _pred_bidir("RealFFT",
    (2, _bidir_dispatch(_fft_fn("rfft"), _fft_fn("irfft"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, n: _fft().rfft(x, n=n), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, n: _fft().irfft(y, n=n), PASS_THROUGH_FIRST))),
)


# ── Cosine / Sine transforms ──────────────────────────────────────────────

DiscreteCosineTransform = _pred_bidir("DiscreteCosineTransform",
    (2, _bidir_dispatch(_fft_fn("dct"), _fft_fn("idct"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, dct_type: _fft().dct(x, type=dct_type), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, dct_type: _fft().idct(y, type=dct_type), PASS_THROUGH_FIRST))),
)

DiscreteSineTransform = _pred_bidir("DiscreteSineTransform",
    (2, _bidir_dispatch(_fft_fn("dst"), _fft_fn("idst"))),
    (3, _fft_bidir_n(
            make_quantity_aware(lambda x, dst_type: _fft().dst(x, type=dst_type), PASS_THROUGH_FIRST),
            make_quantity_aware(lambda y, dst_type: _fft().idst(y, type=dst_type), PASS_THROUGH_FIRST))),
)



# ── Utility ───────────────────────────────────────────────────────────────

FFTFrequencies = _pred("FFTFrequencies",
    (2, _dispatch_fn(lambda n:
        _fft().fftfreq(n))),
    (3, _dispatch_fn(lambda n, d:
        _fft().fftfreq(n, d=d))),
)

RealFFTFrequencies = _pred("RealFFTFrequencies",
    (2, _dispatch_fn(lambda n:
        _fft().rfftfreq(n))),
    (3, _dispatch_fn(lambda n, d:
        _fft().rfftfreq(n, d=d))),
)

FFTShift = _pred_bidir("FFTShift",
    (2, _bidir_dispatch(_fft_fn("fftshift"), _fft_fn("ifftshift"))),
)
# Note: _fft_fn already wraps with PASS_THROUGH_FIRST, so both directions propagate units.
