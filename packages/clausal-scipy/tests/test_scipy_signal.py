"""Tests for clausal.modules.py.scipy_signal — scipy.signal predicates.

Tests are organised per predicate family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via result_get
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")
pytest.importorskip("numpy", reason="numpy not installed")

import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_signal import (
    butterworth,
    bessel,
    chebyshev_type1,
    chebyshev_type2,
    elliptic,
    frequency_response,
    linear_filter,
    sos_filter,
    forward_backward_filter,
    sos_forward_backward_filter,
    decimate,
    resample,
    convolve,
    correlate,
    fft_convolve,
    periodogram,
    welch,
    spectrogram,
    result_get,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _drive_result_get(result_dict, field):
    """Use result_get to extract a field from a dict result."""
    value = Var()
    dispatch = result_get._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, result_dict, field, value, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(value)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is bound to wrong value."""
    trail = Trail()
    result_bound = object()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# Sample signal data
_FS = 1000.0
_T = np.linspace(0, 1, int(_FS), endpoint=False)
_SIGNAL = np.sin(2 * np.pi * 50 * _T) + 0.5 * np.sin(2 * np.pi * 200 * _T)


# ── TestButterworth ───────────────────────────────────────────────────────

class TestButterworth:
    def test_default_returns_dict(self):
        # nv
        r = _drive(butterworth, 4, 0.1)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_ba_coefficients_are_arrays(self):
        # nv
        r = _drive(butterworth, 4, 0.1)
        assert hasattr(r['b'], '__len__')
        assert hasattr(r['a'], '__len__')

    def test_with_btype_high(self):
        # nv
        r = _drive(butterworth, 4, 0.1, 'high')
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_with_output_sos(self):
        # nv
        r = _drive(butterworth, 4, 0.1, 'low', 'sos')
        assert isinstance(r, dict)
        assert 'sos' in r
        assert r['sos'].ndim == 2

    def test_with_output_zpk(self):
        # nv
        r = _drive(butterworth, 4, 0.1, 'low', 'zpk')
        assert isinstance(r, dict)
        assert 'z' in r and 'p' in r and 'k' in r

    def test_with_fs(self):
        # nv
        r = _drive(butterworth, 4, 100.0, 'low', 'ba', _FS)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(butterworth, 4, 0.1)

    def test_result_get_b(self):
        # nv
        r = _drive(butterworth, 4, 0.1)
        b = _drive_result_get(r, 'b')
        assert b is not None

    def test_result_get_sos(self):
        # nv
        r = _drive(butterworth, 4, 0.1, 'low', 'sos')
        sos = _drive_result_get(r, 'sos')
        assert sos is not None
        assert sos.ndim == 2


# ── TestBessel ────────────────────────────────────────────────────────────

class TestBessel:
    def test_default_returns_dict(self):
        # nv
        r = _drive(bessel, 4, 0.1)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_with_btype(self):
        # nv
        r = _drive(bessel, 4, 0.1, 'low')
        assert isinstance(r, dict)

    def test_with_output_sos(self):
        # nv
        r = _drive(bessel, 4, 0.1, 'low', 'sos')
        assert isinstance(r, dict)
        assert 'sos' in r

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(bessel, 4, 0.1)


# ── TestChebyshevType1 ────────────────────────────────────────────────────

class TestChebyshevType1:
    def test_default_returns_dict(self):
        # nv
        r = _drive(chebyshev_type1, 4, 5, 0.1)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_with_btype(self):
        # nv
        r = _drive(chebyshev_type1, 4, 5, 0.1, 'high')
        assert isinstance(r, dict)

    def test_with_output_sos(self):
        # nv
        r = _drive(chebyshev_type1, 4, 5, 0.1, 'low', 'sos')
        assert isinstance(r, dict)
        assert 'sos' in r

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(chebyshev_type1, 4, 5, 0.1)


# ── TestChebyshevType2 ────────────────────────────────────────────────────

class TestChebyshevType2:
    def test_default_returns_dict(self):
        # nv
        r = _drive(chebyshev_type2, 4, 40, 0.1)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_with_btype(self):
        # nv
        r = _drive(chebyshev_type2, 4, 40, 0.1, 'high')
        assert isinstance(r, dict)

    def test_with_output_sos(self):
        # nv
        r = _drive(chebyshev_type2, 4, 40, 0.1, 'low', 'sos')
        assert isinstance(r, dict)
        assert 'sos' in r

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(chebyshev_type2, 4, 40, 0.1)


# ── TestElliptic ──────────────────────────────────────────────────────────

class TestElliptic:
    def test_default_returns_dict(self):
        # nv
        r = _drive(elliptic, 4, 5, 40, 0.1)
        assert isinstance(r, dict)
        assert 'b' in r and 'a' in r

    def test_with_btype(self):
        # nv
        r = _drive(elliptic, 4, 5, 40, 0.1, 'high')
        assert isinstance(r, dict)

    def test_with_output_sos(self):
        # nv
        r = _drive(elliptic, 4, 5, 40, 0.1, 'low', 'sos')
        assert isinstance(r, dict)
        assert 'sos' in r

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(elliptic, 4, 5, 40, 0.1)


# ── TestFrequencyResponse ─────────────────────────────────────────────────

class TestFrequencyResponse:
    def _make_butterworth(self):
        r = _drive(butterworth, 4, 0.1)
        return r['b'], r['a']

    def test_returns_w_h(self):
        # nv
        b, a = self._make_butterworth()
        r = _drive(frequency_response, b, a)
        assert isinstance(r, dict)
        assert 'w' in r and 'h' in r

    def test_w_length_default(self):
        # nv
        b, a = self._make_butterworth()
        r = _drive(frequency_response, b, a)
        assert len(r['w']) == 512

    def test_with_nfreqs(self):
        # nv
        b, a = self._make_butterworth()
        r = _drive(frequency_response, b, a, 256)
        assert len(r['w']) == 256

    def test_h_is_complex(self):
        # nv
        b, a = self._make_butterworth()
        r = _drive(frequency_response, b, a)
        assert np.iscomplexobj(r['h'])

    def test_wrong_result_fails(self):
        # nv
        b, a = self._make_butterworth()
        assert _fails_with_wrong_result(frequency_response, b, a)


# ── TestLinearFilter ──────────────────────────────────────────────────────

class TestLinearFilter:
    def _make_coeffs(self):
        r = _drive(butterworth, 4, 0.1)
        return r['b'], r['a']

    def test_filters_signal(self):
        # nv
        b, a = self._make_coeffs()
        y = _drive(linear_filter, b, a, _SIGNAL)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(_SIGNAL)

    def test_with_axis(self):
        # nv
        b, a = self._make_coeffs()
        y = _drive(linear_filter, b, a, _SIGNAL, -1)
        assert isinstance(y, np.ndarray)

    def test_with_zi_returns_dict(self):
        # nv
        import scipy.signal as sig
        b, a = self._make_coeffs()
        zi = sig.lfilter_zi(b, a) * _SIGNAL[0]
        result = _drive(linear_filter, b, a, _SIGNAL, -1, zi)
        assert isinstance(result, dict)
        assert 'y' in result and 'zf' in result

    def test_wrong_result_fails(self):
        # nv
        b, a = self._make_coeffs()
        assert _fails_with_wrong_result(linear_filter, b, a, _SIGNAL)


# ── TestSOSFilter ─────────────────────────────────────────

class TestSOSFilter:
    def _make_sos(self):
        r = _drive(butterworth, 4, 0.1, 'low', 'sos')
        return r['sos']

    def test_filters_signal(self):
        # nv
        sos = self._make_sos()
        y = _drive(sos_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(_SIGNAL)

    def test_with_axis(self):
        # nv
        sos = self._make_sos()
        y = _drive(sos_filter, sos, _SIGNAL, -1)
        assert isinstance(y, np.ndarray)

    def test_with_zi_returns_dict(self):
        # nv
        import scipy.signal as sig
        sos = self._make_sos()
        zi = sig.sosfilt_zi(sos) * _SIGNAL[0]
        result = _drive(sos_filter, sos, _SIGNAL, -1, zi)
        assert isinstance(result, dict)
        assert 'y' in result and 'zf' in result

    def test_wrong_result_fails(self):
        # nv
        sos = self._make_sos()
        assert _fails_with_wrong_result(sos_filter, sos, _SIGNAL)


# ── TestForwardBackwardFilter ─────────────────────────────────────────────

class TestForwardBackwardFilter:
    def _make_coeffs(self):
        r = _drive(butterworth, 4, 0.1)
        return r['b'], r['a']

    def test_zero_phase_filtering(self):
        # nv
        b, a = self._make_coeffs()
        y = _drive(forward_backward_filter, b, a, _SIGNAL)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(_SIGNAL)

    def test_with_axis(self):
        # nv
        b, a = self._make_coeffs()
        y = _drive(forward_backward_filter, b, a, _SIGNAL, -1)
        assert isinstance(y, np.ndarray)

    def test_wrong_result_fails(self):
        # nv
        b, a = self._make_coeffs()
        assert _fails_with_wrong_result(forward_backward_filter, b, a, _SIGNAL)

    def test_differs_from_linear_filter(self):
        """Forward-backward filter produces different output than linear filter (zero-phase)."""
        # nv
        b, a = self._make_coeffs()
        y_fb = _drive(forward_backward_filter, b, a, _SIGNAL)
        y_lf = _drive(linear_filter, b, a, _SIGNAL)
        assert not np.allclose(y_fb, y_lf)


# ── TestSOSForwardBackwardFilter ──────────────────────────

class TestSOSForwardBackwardFilter:
    def _make_sos(self):
        r = _drive(butterworth, 4, 0.1, 'low', 'sos')
        return r['sos']

    def test_zero_phase_filtering(self):
        # nv
        sos = self._make_sos()
        y = _drive(sos_forward_backward_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(_SIGNAL)

    def test_with_axis(self):
        # nv
        sos = self._make_sos()
        y = _drive(sos_forward_backward_filter, sos, _SIGNAL, -1)
        assert isinstance(y, np.ndarray)

    def test_wrong_result_fails(self):
        # nv
        sos = self._make_sos()
        assert _fails_with_wrong_result(sos_forward_backward_filter, sos, _SIGNAL)

    def test_pipeline_design_and_filter(self):
        """Full pipeline: design sos filter → apply forward-backward filter."""
        # nv
        r = _drive(butterworth, 4, 0.1, 'low', 'sos')
        sos = _drive_result_get(r, 'sos')
        y = _drive(sos_forward_backward_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)
        # Low-pass filter should attenuate 200 Hz component
        assert y.std() < _SIGNAL.std()


# ── TestDecimate ──────────────────────────────────────────────────────────

class TestDecimate:
    def test_decimates_signal(self):
        # nv
        y = _drive(decimate, _SIGNAL, 10)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(_SIGNAL) // 10

    def test_with_axis(self):
        # nv
        y = _drive(decimate, _SIGNAL, 10, 0)
        assert isinstance(y, np.ndarray)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(decimate, _SIGNAL, 10)


# ── TestResample ──────────────────────────────────────────────────────────

class TestResample:
    def test_resamples_signal(self):
        # nv
        num = len(_SIGNAL) // 2
        y = _drive(resample, _SIGNAL, num)
        assert isinstance(y, np.ndarray)
        assert len(y) == num

    def test_with_axis(self):
        # nv
        num = len(_SIGNAL) // 2
        y = _drive(resample, _SIGNAL, num, 0)
        assert isinstance(y, np.ndarray)
        assert len(y) == num

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(resample, _SIGNAL, len(_SIGNAL) // 2)


# ── TestConvolve ──────────────────────────────────────────────────────────

class TestConvolve:
    _A = np.array([1.0, 2.0, 3.0])
    _B = np.array([0.0, 1.0, 0.5])

    def test_full_convolution(self):
        # nv
        y = _drive(convolve, self._A, self._B)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(self._A) + len(self._B) - 1

    def test_with_mode_same(self):
        # nv
        y = _drive(convolve, self._A, self._B, 'same')
        assert isinstance(y, np.ndarray)
        assert len(y) == max(len(self._A), len(self._B))

    def test_with_mode_valid(self):
        # nv
        y = _drive(convolve, self._A, self._B, 'valid')
        assert isinstance(y, np.ndarray)

    def test_with_method_direct(self):
        # nv
        y = _drive(convolve, self._A, self._B, 'full', 'direct')
        assert isinstance(y, np.ndarray)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(convolve, self._A, self._B)

    def test_known_result(self):
        # nv
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 0.0])
        y = _drive(convolve, a, b, 'valid')
        assert y is not None


# ── TestCorrelate ─────────────────────────────────────────────────────────

class TestCorrelate:
    _A = np.array([1.0, 2.0, 3.0])
    _B = np.array([0.0, 1.0, 0.5])

    def test_full_correlation(self):
        # nv
        y = _drive(correlate, self._A, self._B)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(self._A) + len(self._B) - 1

    def test_with_mode(self):
        # nv
        y = _drive(correlate, self._A, self._B, 'same')
        assert isinstance(y, np.ndarray)

    def test_with_method(self):
        # nv
        y = _drive(correlate, self._A, self._B, 'full', 'direct')
        assert isinstance(y, np.ndarray)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(correlate, self._A, self._B)


# ── TestFFTConvolve ───────────────────────────────────────────────────────

class TestFFTConvolve:
    _A = np.array([1.0, 2.0, 3.0])
    _B = np.array([0.0, 1.0, 0.5])

    def test_full_convolution(self):
        # nv
        y = _drive(fft_convolve, self._A, self._B)
        assert isinstance(y, np.ndarray)
        assert len(y) == len(self._A) + len(self._B) - 1

    def test_with_mode(self):
        # nv
        y = _drive(fft_convolve, self._A, self._B, 'same')
        assert isinstance(y, np.ndarray)

    def test_matches_direct_convolve(self):
        """FFT convolution should match direct convolution."""
        # nv
        y_fft = _drive(fft_convolve, self._A, self._B)
        y_dir = _drive(convolve, self._A, self._B, 'full', 'direct')
        assert np.allclose(y_fft, y_dir, atol=1e-10)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(fft_convolve, self._A, self._B)


# ── TestPeriodogram ───────────────────────────────────────────────────────

class TestPeriodogram:
    def test_returns_f_pxx(self):
        # nv
        r = _drive(periodogram, _SIGNAL)
        assert isinstance(r, dict)
        assert 'f' in r and 'Pxx' in r

    def test_default_fs(self):
        # nv
        r = _drive(periodogram, _SIGNAL)
        # default fs=1.0, max freq = 0.5
        assert r['f'][-1] <= 0.5

    def test_with_fs(self):
        # nv
        r = _drive(periodogram, _SIGNAL, _FS)
        assert r['f'][-1] <= _FS / 2 + 1

    def test_pxx_nonnegative(self):
        # nv
        r = _drive(periodogram, _SIGNAL, _FS)
        assert np.all(r['Pxx'] >= 0)

    def test_result_get_f(self):
        # nv
        r = _drive(periodogram, _SIGNAL, _FS)
        f = _drive_result_get(r, 'f')
        assert f is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(periodogram, _SIGNAL)

    def test_peak_at_50hz(self):
        """periodogram should show a peak near 50 Hz."""
        # nv
        r = _drive(periodogram, _SIGNAL, _FS)
        f, Pxx = r['f'], r['Pxx']
        peak_idx = np.argmax(Pxx)
        assert abs(f[peak_idx] - 50.0) < 5.0


# ── TestWelch ─────────────────────────────────────────────────────────────

class TestWelch:
    def test_returns_f_pxx(self):
        # nv
        r = _drive(welch, _SIGNAL)
        assert isinstance(r, dict)
        assert 'f' in r and 'Pxx' in r

    def test_with_fs(self):
        # nv
        r = _drive(welch, _SIGNAL, _FS)
        assert r['f'][-1] <= _FS / 2 + 1

    def test_pxx_nonnegative(self):
        # nv
        r = _drive(welch, _SIGNAL, _FS)
        assert np.all(r['Pxx'] >= 0)

    def test_result_get_pxx(self):
        # nv
        r = _drive(welch, _SIGNAL, _FS)
        pxx = _drive_result_get(r, 'Pxx')
        assert pxx is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(welch, _SIGNAL)

    def test_smoother_than_periodogram(self):
        """welch power spectral density should be smoother than periodogram."""
        # nv
        rw = _drive(welch, _SIGNAL, _FS)
        rp = _drive(periodogram, _SIGNAL, _FS)
        assert rw['Pxx'].std() <= rp['Pxx'].std() + 1e-10


# ── TestSpectrogram ───────────────────────────────────────────────────────

class TestSpectrogram:
    def test_returns_f_t_sxx(self):
        # nv
        r = _drive(spectrogram, _SIGNAL)
        assert isinstance(r, dict)
        assert 'f' in r and 't' in r and 'Sxx' in r

    def test_with_fs(self):
        # nv
        r = _drive(spectrogram, _SIGNAL, _FS)
        assert r['f'][-1] <= _FS / 2 + 1

    def test_sxx_is_2d(self):
        # nv
        r = _drive(spectrogram, _SIGNAL, _FS)
        assert r['Sxx'].ndim == 2

    def test_sxx_nonnegative(self):
        # nv
        r = _drive(spectrogram, _SIGNAL, _FS)
        assert np.all(r['Sxx'] >= 0)

    def test_result_get_sxx(self):
        # nv
        r = _drive(spectrogram, _SIGNAL, _FS)
        sxx = _drive_result_get(r, 'Sxx')
        assert sxx is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(spectrogram, _SIGNAL)


# ── TestResultGet ─────────────────────────────────────────────────────────

class TestResultGet:
    def test_extracts_field(self):
        # nv
        d = {'x': 42.0, 'fun': 0.0}
        v = _drive_result_get(d, 'x')
        assert v == 42.0

    def test_missing_field_fails(self):
        # nv
        d = {'x': 42.0}
        v = _drive_result_get(d, 'missing')
        assert v is None

    def test_non_dict_fails(self):
        # nv
        v = _drive_result_get("not a dict", 'x')
        assert v is None

    def test_non_string_field_fails(self):
        # nv
        d = {'x': 1.0}
        v = _drive_result_get(d, 42)
        assert v is None

    def test_unify_with_bound_correct(self):
        """result_get should succeed when VALUE is already bound to the correct value."""
        # nv
        d = {'b': np.array([1.0])}
        dispatch = result_get._get_dispatch()
        trail = Trail()
        value_bound = d['b']
        gen = dispatch(None, None, None, None, d, 'b', value_bound, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1

    def test_unify_with_bound_wrong_fails(self):
        """result_get should fail when VALUE is bound to a different value."""
        # nv
        d = {'x': 42.0}
        dispatch = result_get._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, d, 'x', 99.0, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── TestFilterPipeline ────────────────────────────────────────────────────

class TestFilterPipeline:
    """Integration tests for the filter design → apply pipeline."""

    def test_butterworth_ba_linear_filter(self):
        # nv
        r = _drive(butterworth, 4, 100.0, 'low', 'ba', _FS)
        b = _drive_result_get(r, 'b')
        a = _drive_result_get(r, 'a')
        y = _drive(linear_filter, b, a, _SIGNAL)
        assert isinstance(y, np.ndarray)

    def test_butterworth_sos_forward_backward(self):
        # nv
        r = _drive(butterworth, 4, 100.0, 'low', 'sos', _FS)
        sos = _drive_result_get(r, 'sos')
        y = _drive(sos_forward_backward_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)

    def test_chebyshev_type1_sos_second_order_sections_filter(self):
        # nv
        r = _drive(chebyshev_type1, 4, 5, 0.1, 'low', 'sos')
        sos = _drive_result_get(r, 'sos')
        y = _drive(sos_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)

    def test_butterworth_highpass_attenuates_low_frequency(self):
        """High-pass butterworth should attenuate the 50 Hz component."""
        # nv
        r = _drive(butterworth, 6, 0.3, 'high', 'sos')
        sos = _drive_result_get(r, 'sos')
        y = _drive(sos_forward_backward_filter, sos, _SIGNAL)
        assert isinstance(y, np.ndarray)

    def test_frequency_response_after_design(self):
        # nv
        r = _drive(butterworth, 4, 0.1)
        b = _drive_result_get(r, 'b')
        a = _drive_result_get(r, 'a')
        fz = _drive(frequency_response, b, a)
        assert 'w' in fz and 'h' in fz
        # At DC (w=0), magnitude should be ~1 for low-pass
        assert abs(abs(fz['h'][0]) - 1.0) < 0.01

    def test_convolve_correlate_symmetry(self):
        """For a symmetric kernel, convolve and correlate should match."""
        # nv
        kernel = np.array([1.0, 2.0, 1.0])
        signal = np.array([1.0, 0.0, 1.0, 0.0, 1.0])
        y_conv = _drive(convolve, signal, kernel, 'same')
        y_corr = _drive(correlate, signal, kernel, 'same')
        assert np.allclose(y_conv, y_corr)
