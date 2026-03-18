"""clausal.modules.py.scipy_fft — scipy.fft predicates for Clausal.

Provides fast Fourier transform routines from scipy.fft as importable
predicate objects for use in .clausal files via::

    -import_from(scipy_fft, [FFTransform, InverseFFT, FFTShift, FFTFrequencies, ...])

All predicates are **Tier 1 — pure functions**: accept NumPy arrays and
return transformed arrays directly in RESULT.

Predicate catalogue
-------------------
1-D transforms:
    FFTransform(X, RESULT)               — 1-D forward DFT
    FFTransform(X, N, RESULT)            — with output length N

    InverseFFT(X, RESULT)               — 1-D inverse DFT
    InverseFFT(X, N, RESULT)            — with output length N

2-D transforms:
    FFTransform2D(X, RESULT)             — 2-D forward DFT
    FFTransform2D(X, S, RESULT)          — with output shape S=(rows, cols)

    InverseFFT2D(X, RESULT)             — 2-D inverse DFT
    InverseFFT2D(X, S, RESULT)          — with output shape S

N-D transforms:
    FFTransformND(X, RESULT)             — N-D forward DFT over all axes
    FFTransformND(X, S, RESULT)          — with output shape S (list of lengths)

Real-input transforms (output length n//2+1):
    RealFFT(X, RESULT)                  — real-input forward FFT
    RealFFT(X, N, RESULT)               — with output length N

    InverseRealFFT(X, RESULT)           — inverse of RealFFT; real-valued output
    InverseRealFFT(X, N, RESULT)        — with output length N (must be even for
                                          symmetric spectrum)

Cosine transforms:
    DiscreteCosineTransform(X, RESULT)           — DCT type-2 (default)
    DiscreteCosineTransform(X, TYPE, RESULT)     — with explicit type (1–4)

    InverseDiscreteCosineTransform(X, RESULT)    — IDCT type-2
    InverseDiscreteCosineTransform(X, TYPE, RESULT)

Utility:
    FFTFrequencies(N, RESULT)           — DFT sample frequencies for length-N output
    FFTFrequencies(N, D, RESULT)        — with sample spacing D (default 1.0)

    RealFFTFrequencies(N, RESULT)       — frequencies for length-N real FFT
    RealFFTFrequencies(N, D, RESULT)    — with sample spacing D

    FFTShift(X, RESULT)                 — shift zero-frequency component to centre
    InverseFFTShift(X, RESULT)          — inverse of FFTShift
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


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


# ── Predicate adapter ─────────────────────────────────────────────────────

class _SciPyFFTPredicate:
    """Dispatch adapter for a scipy.fft predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_SciPyFFTPredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        # args layout: (input_0, ..., input_{n-1}, result, trail)
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.fft.{self._name}/{arities}"


# ── Dispatch function factory ─────────────────────────────────────────────

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


def _pred(name: str, *arity_fns) -> _SciPyFFTPredicate:
    """Create a ``_SciPyFFTPredicate`` from (arity, dispatch_fn) pairs."""
    p = _SciPyFFTPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── 1-D transforms ────────────────────────────────────────────────────────

FFTransform = _pred("FFTransform",
    (2, _dispatch_fn(lambda x:
        _fft().fft(x))),
    (3, _dispatch_fn(lambda x, n:
        _fft().fft(x, n=n))),
)

InverseFFT = _pred("InverseFFT",
    (2, _dispatch_fn(lambda x:
        _fft().ifft(x))),
    (3, _dispatch_fn(lambda x, n:
        _fft().ifft(x, n=n))),
)


# ── 2-D transforms ────────────────────────────────────────────────────────

FFTransform2D = _pred("FFTransform2D",
    (2, _dispatch_fn(lambda x:
        _fft().fft2(x))),
    (3, _dispatch_fn(lambda x, s:
        _fft().fft2(x, s=s))),
)

InverseFFT2D = _pred("InverseFFT2D",
    (2, _dispatch_fn(lambda x:
        _fft().ifft2(x))),
    (3, _dispatch_fn(lambda x, s:
        _fft().ifft2(x, s=s))),
)


# ── N-D transforms ────────────────────────────────────────────────────────

FFTransformND = _pred("FFTransformND",
    (2, _dispatch_fn(lambda x:
        _fft().fftn(x))),
    (3, _dispatch_fn(lambda x, s:
        _fft().fftn(x, s=s))),
)


# ── Real-input transforms ─────────────────────────────────────────────────

RealFFT = _pred("RealFFT",
    (2, _dispatch_fn(lambda x:
        _fft().rfft(x))),
    (3, _dispatch_fn(lambda x, n:
        _fft().rfft(x, n=n))),
)

InverseRealFFT = _pred("InverseRealFFT",
    (2, _dispatch_fn(lambda x:
        _fft().irfft(x))),
    (3, _dispatch_fn(lambda x, n:
        _fft().irfft(x, n=n))),
)


# ── Cosine transforms ─────────────────────────────────────────────────────

DiscreteCosineTransform = _pred("DiscreteCosineTransform",
    (2, _dispatch_fn(lambda x:
        _fft().dct(x))),
    (3, _dispatch_fn(lambda x, dct_type:
        _fft().dct(x, type=dct_type))),
)

InverseDiscreteCosineTransform = _pred("InverseDiscreteCosineTransform",
    (2, _dispatch_fn(lambda x:
        _fft().idct(x))),
    (3, _dispatch_fn(lambda x, dct_type:
        _fft().idct(x, type=dct_type))),
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

FFTShift = _pred("FFTShift",
    (2, _dispatch_fn(lambda x:
        _fft().fftshift(x))),
)

InverseFFTShift = _pred("InverseFFTShift",
    (2, _dispatch_fn(lambda x:
        _fft().ifftshift(x))),
)
