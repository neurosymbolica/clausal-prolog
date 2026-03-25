"""clausal.modules.py.scipy_signal — scipy.signal predicates for Clausal.

Provides signal-processing routines from scipy.signal as importable predicate
objects for use in .clausal files via::

    -import_from(py.scipy_signal, [Butterworth, SOSForwardBackwardFilter, ResultGet, ...])

Tiers
-----
- **Tier 2** (returns result dict; use ResultGet to access fields):
    Butterworth      → dict {b,a} or {z,p,k} or {sos} depending on OUTPUT
    Bessel           → same
    ChebyshevType1   → same
    ChebyshevType2   → same
    Elliptic         → same
    FrequencyResponse → dict {w, h}
    Periodogram      → dict {f, Pxx}
    Welch            → dict {f, Pxx}
    Spectrogram      → dict {f, t, Sxx}

- **Tier 1** (array inputs → array result, or dict when ZI supplied):
    LinearFilter                         → array, or dict {y, zf} when ZI provided
    SOSFilter            → array, or dict {y, zf} when ZI provided
    ForwardBackwardFilter                → array
    SOSForwardBackwardFilter → array
    Decimate                             → array
    Resample                             → array
    Convolve                             → array
    Correlate                            → array
    FFTConvolve                          → array

Helper:
    ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE

Predicate catalogue
-------------------
Filter design (Tier 2):
    Butterworth(N, WN, RESULT)
    Butterworth(N, WN, BTYPE, RESULT)            # BTYPE: 'low','high','band','bandstop'
    Butterworth(N, WN, BTYPE, OUTPUT, RESULT)    # OUTPUT: 'ba','zpk','sos'
    Butterworth(N, WN, BTYPE, OUTPUT, FS, RESULT)

    Bessel(N, WN, RESULT)
    Bessel(N, WN, BTYPE, RESULT)
    Bessel(N, WN, BTYPE, OUTPUT, RESULT)

    ChebyshevType1(N, RP, WN, RESULT)
    ChebyshevType1(N, RP, WN, BTYPE, RESULT)
    ChebyshevType1(N, RP, WN, BTYPE, OUTPUT, RESULT)

    ChebyshevType2(N, RS, WN, RESULT)
    ChebyshevType2(N, RS, WN, BTYPE, RESULT)
    ChebyshevType2(N, RS, WN, BTYPE, OUTPUT, RESULT)

    Elliptic(N, RP, RS, WN, RESULT)
    Elliptic(N, RP, RS, WN, BTYPE, RESULT)
    Elliptic(N, RP, RS, WN, BTYPE, OUTPUT, RESULT)

    FrequencyResponse(B, A, RESULT)              # RESULT: dict {w, h}
    FrequencyResponse(B, A, NFREQS, RESULT)      # NFREQS: number of frequency points

Filtering (Tier 1):
    LinearFilter(B, A, X, RESULT)
    LinearFilter(B, A, X, AXIS, RESULT)
    LinearFilter(B, A, X, AXIS, ZI, RESULT)      # RESULT: dict {y, zf}

    SOSFilter(SOS, X, RESULT)
    SOSFilter(SOS, X, AXIS, RESULT)
    SOSFilter(SOS, X, AXIS, ZI, RESULT)  # RESULT: dict {y, zf}

    ForwardBackwardFilter(B, A, X, RESULT)
    ForwardBackwardFilter(B, A, X, AXIS, RESULT)

    SOSForwardBackwardFilter(SOS, X, RESULT)
    SOSForwardBackwardFilter(SOS, X, AXIS, RESULT)

    Decimate(X, Q, RESULT)
    Decimate(X, Q, AXIS, RESULT)

    Resample(X, NUM, RESULT)
    Resample(X, NUM, AXIS, RESULT)

Convolution/correlation (Tier 1):
    Convolve(IN1, IN2, RESULT)
    Convolve(IN1, IN2, MODE, RESULT)              # MODE: 'full','valid','same'
    Convolve(IN1, IN2, MODE, METHOD, RESULT)      # METHOD: 'auto','direct','fft'

    Correlate(IN1, IN2, RESULT)
    Correlate(IN1, IN2, MODE, RESULT)
    Correlate(IN1, IN2, MODE, METHOD, RESULT)

    FFTConvolve(IN1, IN2, RESULT)
    FFTConvolve(IN1, IN2, MODE, RESULT)

Spectral analysis (Tier 2):
    Periodogram(X, RESULT)                       # RESULT: dict {f, Pxx}
    Periodogram(X, FS, RESULT)

    Welch(X, RESULT)                             # RESULT: dict {f, Pxx}
    Welch(X, FS, RESULT)

    Spectrogram(X, RESULT)                       # RESULT: dict {f, t, Sxx}
    Spectrogram(X, FS, RESULT)
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Lazy scipy.signal import ──────────────────────────────────────────────

_scipy_signal = None
_sig_lock = _threading.Lock()


def _ensure_sig():
    global _scipy_signal
    if _scipy_signal is not None:
        return
    with _sig_lock:
        if _scipy_signal is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_signal = _import_stdlib("scipy.signal")


def _sig():
    _ensure_sig()
    return _scipy_signal


# ── Dispatch function factories ───────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: inputs → value → unify RESULT."""
    def dispatch(this_generator, parent, *args):
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


# ── Filter design result packaging ───────────────────────────────────────

def _filter_result(raw, output: str):
    """Convert scipy filter design tuple/array to a result dict."""
    if output == 'ba':
        b, a = raw
        return {'b': b, 'a': a}
    elif output == 'zpk':
        z, p, k = raw
        return {'z': z, 'p': p, 'k': k}
    elif output == 'sos':
        return {'sos': raw}
    return raw


# ── Filter design (Tier 2) ────────────────────────────────────────────────

def _butterworth(n, wn, btype='low', output='ba', fs=None):
    raw = _sig().butter(n, wn, btype=btype, output=output, fs=fs)
    return _filter_result(raw, output)


Butterworth = _pred("Butterworth",
    (3, _dispatch_fn(lambda n, wn: _butterworth(n, wn))),
    (4, _dispatch_fn(lambda n, wn, btype: _butterworth(n, wn, btype=btype))),
    (5, _dispatch_fn(lambda n, wn, btype, output: _butterworth(n, wn, btype=btype, output=output))),
    (6, _dispatch_fn(lambda n, wn, btype, output, fs: _butterworth(n, wn, btype=btype, output=output, fs=fs))),
)


def _bessel(n, wn, btype='low', output='ba'):
    raw = _sig().bessel(n, wn, btype=btype, output=output)
    return _filter_result(raw, output)


Bessel = _pred("Bessel",
    (3, _dispatch_fn(lambda n, wn: _bessel(n, wn))),
    (4, _dispatch_fn(lambda n, wn, btype: _bessel(n, wn, btype=btype))),
    (5, _dispatch_fn(lambda n, wn, btype, output: _bessel(n, wn, btype=btype, output=output))),
)


def _chebyshev_type1(n, rp, wn, btype='low', output='ba'):
    raw = _sig().cheby1(n, rp, wn, btype=btype, output=output)
    return _filter_result(raw, output)


ChebyshevType1 = _pred("ChebyshevType1",
    (4, _dispatch_fn(lambda n, rp, wn: _chebyshev_type1(n, rp, wn))),
    (5, _dispatch_fn(lambda n, rp, wn, btype: _chebyshev_type1(n, rp, wn, btype=btype))),
    (6, _dispatch_fn(lambda n, rp, wn, btype, output: _chebyshev_type1(n, rp, wn, btype=btype, output=output))),
)


def _chebyshev_type2(n, rs, wn, btype='low', output='ba'):
    raw = _sig().cheby2(n, rs, wn, btype=btype, output=output)
    return _filter_result(raw, output)


ChebyshevType2 = _pred("ChebyshevType2",
    (4, _dispatch_fn(lambda n, rs, wn: _chebyshev_type2(n, rs, wn))),
    (5, _dispatch_fn(lambda n, rs, wn, btype: _chebyshev_type2(n, rs, wn, btype=btype))),
    (6, _dispatch_fn(lambda n, rs, wn, btype, output: _chebyshev_type2(n, rs, wn, btype=btype, output=output))),
)


def _elliptic(n, rp, rs, wn, btype='low', output='ba'):
    raw = _sig().ellip(n, rp, rs, wn, btype=btype, output=output)
    return _filter_result(raw, output)


Elliptic = _pred("Elliptic",
    (5, _dispatch_fn(lambda n, rp, rs, wn: _elliptic(n, rp, rs, wn))),
    (6, _dispatch_fn(lambda n, rp, rs, wn, btype: _elliptic(n, rp, rs, wn, btype=btype))),
    (7, _dispatch_fn(lambda n, rp, rs, wn, btype, output: _elliptic(n, rp, rs, wn, btype=btype, output=output))),
)


def _frequency_response(b, a=1, nfreqs=512):
    w, h = _sig().freqz(b, a, worN=nfreqs)
    return {'w': w, 'h': h}


FrequencyResponse = _pred("FrequencyResponse",
    (3, _dispatch_fn(lambda b, a: _frequency_response(b, a))),
    (4, _dispatch_fn(lambda b, a, nfreqs: _frequency_response(b, a, nfreqs=nfreqs))),
)


# ── Filtering (Tier 1) ────────────────────────────────────────────────────

def _linear_filter(b, a, x, axis=-1, zi=None):
    if zi is not None:
        y, zf = _sig().lfilter(b, a, x, axis=axis, zi=zi)
        return {'y': y, 'zf': zf}
    return _sig().lfilter(b, a, x, axis=axis)


LinearFilter = _pred("LinearFilter",
    (4, _dispatch_fn(lambda b, a, x: _linear_filter(b, a, x))),
    (5, _dispatch_fn(lambda b, a, x, axis: _linear_filter(b, a, x, axis=axis))),
    (6, _dispatch_fn(lambda b, a, x, axis, zi: _linear_filter(b, a, x, axis=axis, zi=zi))),
)


def _second_order_sections_filter(sos, x, axis=-1, zi=None):
    if zi is not None:
        y, zf = _sig().sosfilt(sos, x, axis=axis, zi=zi)
        return {'y': y, 'zf': zf}
    return _sig().sosfilt(sos, x, axis=axis)


SOSFilter = _pred("SOSFilter",
    (3, _dispatch_fn(lambda sos, x: _second_order_sections_filter(sos, x))),
    (4, _dispatch_fn(lambda sos, x, axis: _second_order_sections_filter(sos, x, axis=axis))),
    (5, _dispatch_fn(lambda sos, x, axis, zi: _second_order_sections_filter(sos, x, axis=axis, zi=zi))),
)


ForwardBackwardFilter = _pred("ForwardBackwardFilter",
    (4, _dispatch_fn(lambda b, a, x: _sig().filtfilt(b, a, x))),
    (5, _dispatch_fn(lambda b, a, x, axis: _sig().filtfilt(b, a, x, axis=axis))),
)


SOSForwardBackwardFilter = _pred("SOSForwardBackwardFilter",
    (3, _dispatch_fn(lambda sos, x: _sig().sosfiltfilt(sos, x))),
    (4, _dispatch_fn(lambda sos, x, axis: _sig().sosfiltfilt(sos, x, axis=axis))),
)


Decimate = _pred("Decimate",
    (3, _dispatch_fn(lambda x, q: _sig().decimate(x, q))),
    (4, _dispatch_fn(lambda x, q, axis: _sig().decimate(x, q, axis=axis))),
)


Resample = _pred("Resample",
    (3, _dispatch_fn(lambda x, num: _sig().resample(x, num))),
    (4, _dispatch_fn(lambda x, num, axis: _sig().resample(x, num, axis=axis))),
)


# ── Convolution and correlation (Tier 1) ──────────────────────────────────

Convolve = _pred("Convolve",
    (3, _dispatch_fn(lambda in1, in2: _sig().convolve(in1, in2))),
    (4, _dispatch_fn(lambda in1, in2, mode: _sig().convolve(in1, in2, mode=mode))),
    (5, _dispatch_fn(lambda in1, in2, mode, method: _sig().convolve(in1, in2, mode=mode, method=method))),
)


Correlate = _pred("Correlate",
    (3, _dispatch_fn(lambda in1, in2: _sig().correlate(in1, in2))),
    (4, _dispatch_fn(lambda in1, in2, mode: _sig().correlate(in1, in2, mode=mode))),
    (5, _dispatch_fn(lambda in1, in2, mode, method: _sig().correlate(in1, in2, mode=mode, method=method))),
)


FFTConvolve = _pred("FFTConvolve",
    (3, _dispatch_fn(lambda in1, in2: _sig().fftconvolve(in1, in2))),
    (4, _dispatch_fn(lambda in1, in2, mode: _sig().fftconvolve(in1, in2, mode=mode))),
)


# ── Spectral analysis (Tier 2) ────────────────────────────────────────────

def _periodogram(x, fs=1.0):
    f, Pxx = _sig().periodogram(x, fs=fs)
    return {'f': f, 'Pxx': Pxx}


Periodogram = _pred("Periodogram",
    (2, _dispatch_fn(lambda x: _periodogram(x))),
    (3, _dispatch_fn(lambda x, fs: _periodogram(x, fs=fs))),
)


def _welch(x, fs=1.0):
    f, Pxx = _sig().welch(x, fs=fs)
    return {'f': f, 'Pxx': Pxx}


Welch = _pred("Welch",
    (2, _dispatch_fn(lambda x: _welch(x))),
    (3, _dispatch_fn(lambda x, fs: _welch(x, fs=fs))),
)


def _spectrogram(x, fs=1.0):
    f, t, Sxx = _sig().spectrogram(x, fs=fs)
    return {'f': f, 't': t, 'Sxx': Sxx}


Spectrogram = _pred("Spectrogram",
    (2, _dispatch_fn(lambda x: _spectrogram(x))),
    (3, _dispatch_fn(lambda x, fs: _spectrogram(x, fs=fs))),
)


# ── Helper: ResultGet ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (as produced by Tier 2 predicates).
    FIELD must be a ground string key.
    VALUE is unified with the retrieved value.
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, result, field, value, trail):
        result = deref(result)
        field = deref(field)
        if not isinstance(result, dict) or not isinstance(field, str):
            yield (parent, DONE)
            return
        if field not in result:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(value, result[field], trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)

    def __repr__(self) -> str:
        return "ResultGet/3"


ResultGet = _ResultGetPredicate()
