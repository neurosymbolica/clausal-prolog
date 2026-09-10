"""Tests for clausal.modules.py.scipy_fft — scipy.fft predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- round-trip identity (forward then inverse)
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import math
import numpy as np

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_fft import (
    FFTransform,
    FFTransform2D,
    FFTransformND,
    RealFFT,
    DiscreteCosineTransform,
    FFTFrequencies, RealFFTFrequencies,
    FFTShift,
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


def _drive_bwd(pred, *args):
    """Call predicate in backward direction: first arg is unbound Var, rest are ground.

    For a bidirectional predicate Pred(X, Y): binds X (result) given Y (ground).
    """
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, result, *args, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _drive_bwd_n(pred, n, spectrum):
    """Call arity-3 bidirectional predicate backward: Pred(result_var, N, spectrum).

    Used for transforms with an optional length/shape argument N.
    """
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, result, n, spectrum, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is wrong."""
    trail = Trail()
    result_bound = object()  # will not unify with any numpy array
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0



# ── TestFFT ───────────────────────────────────────────────────────────────

class TestFFT:
    def test_constant_signal_dc_only(self):
        # FFTransform of [1,1,1,1] → [4+0j, 0, 0, 0]
        # nv
        x = np.array([1.0, 1.0, 1.0, 1.0])
        result = _drive(FFTransform, x)
        assert result is not None
        assert abs(result[0] - 4.0) < 1e-10
        assert abs(result[1]) < 1e-10

    def test_impulse_spectrum_flat(self):
        # FFTransform of [1,0,0,0] → all ones (flat spectrum)
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = _drive(FFTransform, x)
        assert result is not None
        assert all(abs(abs(v) - 1.0) < 1e-10 for v in result)

    def test_with_output_length(self):
        # zero-pad to length 8
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = _drive(FFTransform, x, 8)
        assert result is not None
        assert len(result) == 8

    def test_complex_input(self):
        # nv
        x = np.array([1+0j, 0+1j, -1+0j, 0-1j])
        result = _drive(FFTransform, x)
        assert result is not None
        assert len(result) == 4

    def test_wrong_result_fails(self):
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        assert _fails_with_wrong_result(FFTransform, x)


# ── TestInverseFFT ────────────────────────────────────────────────────────

class TestInverseFFT:
    def test_round_trip(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        spectrum = _drive(FFTransform, x)
        # Backward direction of FFTransform: FFTransform(result_var, spectrum) → result_var = ifft(spectrum)
        recovered = _drive_bwd(FFTransform, spectrum)
        assert recovered is not None
        assert np.allclose(recovered.real, x, atol=1e-10)

    def test_dc_only_to_constant(self):
        # ifft([4,0,0,0]) → [1,1,1,1]
        # nv
        spectrum = np.array([4.0+0j, 0.0, 0.0, 0.0])
        result = _drive_bwd(FFTransform, spectrum)
        assert result is not None
        assert np.allclose(result.real, np.ones(4), atol=1e-10)

    def test_with_output_length(self):
        # nv
        spectrum = np.array([4.0+0j, 0.0, 0.0, 0.0])
        # Backward direction with N: FFTransform(result_var, N, spectrum)
        result = _drive_bwd_n(FFTransform, 4, spectrum)
        assert result is not None
        assert len(result) == 4

    def test_wrong_result_fails(self):
        # Consistency check: FFTransform(wrong_x, spectrum) where wrong_x ≠ ifft(spectrum) fails
        # nv
        spectrum = np.array([4.0+0j, 0.0, 0.0, 0.0])
        wrong_x = np.array([9.0, 9.0, 9.0, 9.0])
        trail = Trail()
        dispatch = FFTransform._get_dispatch()
        gen = dispatch(None, None, None, None, wrong_x, spectrum, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── TestFFTransform2D ─────────────────────────────────────────────────────

class TestFFTransform2D:
    def test_identity_matrix(self):
        # nv
        x = np.eye(2)
        result = _drive(FFTransform2D, x)
        assert result is not None
        assert result.shape == (2, 2)

    def test_constant_matrix_dc_only(self):
        # nv
        x = np.ones((2, 2))
        result = _drive(FFTransform2D, x)
        assert result is not None
        # DC component should be 4.0 (sum of all elements)
        assert abs(result[0, 0] - 4.0) < 1e-10
        assert abs(result[0, 1]) < 1e-10

    def test_with_output_shape(self):
        # nv
        x = np.ones((2, 2))
        result = _drive(FFTransform2D, x, (4, 4))
        assert result is not None
        assert result.shape == (4, 4)

    def test_wrong_result_fails(self):
        # nv
        x = np.eye(2)
        assert _fails_with_wrong_result(FFTransform2D, x)


# ── TestInverseFFT2D ──────────────────────────────────────────────────────

class TestInverseFFT2D:
    def test_round_trip(self):
        # nv
        x = np.array([[1.0, 2.0], [3.0, 4.0]])
        spectrum = _drive(FFTransform2D, x)
        # Backward direction of FFTransform2D: FFTransform2D(result_var, spectrum) → result_var = ifft2(spectrum)
        recovered = _drive_bwd(FFTransform2D, spectrum)
        assert recovered is not None
        assert np.allclose(recovered.real, x, atol=1e-10)

    def test_wrong_result_fails(self):
        # Consistency check: FFTransform2D(wrong_x, spectrum) where wrong_x ≠ ifft2(spectrum) fails
        # nv
        x = np.ones((2, 2))
        spectrum = _drive(FFTransform2D, x)
        wrong_x = np.full((2, 2), 99.0)
        trail = Trail()
        dispatch = FFTransform2D._get_dispatch()
        gen = dispatch(None, None, None, None, wrong_x, spectrum, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── TestFFTransformND ─────────────────────────────────────────────────────

class TestFFTransformND:
    def test_1d_matches_fft(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        result_fftn = _drive(FFTransformND, x)
        result_fft = _drive(FFTransform, x)
        assert result_fftn is not None
        assert np.allclose(result_fftn, result_fft, atol=1e-10)

    def test_2d_round_trip(self):
        # nv
        x = np.array([[1.0, 2.0], [3.0, 4.0]])
        spectrum = _drive(FFTransformND, x)
        # Backward direction of FFTransform2D: ifft2(spectrum)
        recovered = _drive_bwd(FFTransform2D, spectrum)
        assert recovered is not None
        assert np.allclose(recovered.real, x, atol=1e-10)

    def test_with_output_shape(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        result = _drive(FFTransformND, x, [8])
        assert result is not None
        assert len(result) == 8

    def test_wrong_result_fails(self):
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        assert _fails_with_wrong_result(FFTransformND, x)


# ── TestRealFFT ───────────────────────────────────────────────────────────

class TestRealFFT:
    def test_output_length(self):
        # rfft of length-N real signal → N//2+1 complex values
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = _drive(RealFFT, x)
        assert result is not None
        assert len(result) == 3  # N//2 + 1 = 4//2 + 1 = 3

    def test_impulse_flat_spectrum(self):
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = _drive(RealFFT, x)
        assert result is not None
        assert all(abs(abs(v) - 1.0) < 1e-10 for v in result)

    def test_constant_signal(self):
        # rfft([1,1,1,1]) → DC=4, all others 0
        # nv
        x = np.ones(4)
        result = _drive(RealFFT, x)
        assert result is not None
        assert abs(result[0] - 4.0) < 1e-10
        assert abs(result[1]) < 1e-10

    def test_with_output_length(self):
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = _drive(RealFFT, x, 8)
        assert result is not None
        assert len(result) == 5  # 8//2 + 1

    def test_wrong_result_fails(self):
        # nv
        x = np.array([1.0, 0.0, 0.0, 0.0])
        assert _fails_with_wrong_result(RealFFT, x)


# ── TestInverseRealFFT ────────────────────────────────────────────────────

class TestInverseRealFFT:
    def test_round_trip(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        spectrum = _drive(RealFFT, x)
        # Backward direction of RealFFT: RealFFT(result_var, spectrum) → result_var = irfft(spectrum)
        recovered = _drive_bwd(RealFFT, spectrum)
        assert recovered is not None
        assert np.allclose(recovered, x, atol=1e-10)

    def test_output_is_real(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        spectrum = _drive(RealFFT, x)
        result = _drive_bwd(RealFFT, spectrum)
        assert result is not None
        assert result.dtype in (np.float32, np.float64, float)

    def test_with_output_length(self):
        # nv
        spectrum = np.array([4.0+0j, 0.0+0j, 0.0+0j])
        # Backward direction with N: RealFFT(result_var, N, spectrum)
        result = _drive_bwd_n(RealFFT, 4, spectrum)
        assert result is not None
        assert len(result) == 4

    def test_wrong_result_fails(self):
        # Consistency check: RealFFT(wrong_x, spectrum) where wrong_x ≠ irfft(spectrum) fails
        # nv
        spectrum = np.array([4.0+0j, 0.0, 0.0])
        wrong_x = np.array([9.0, 9.0, 9.0, 9.0])
        trail = Trail()
        dispatch = RealFFT._get_dispatch()
        gen = dispatch(None, None, None, None, wrong_x, spectrum, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── TestDiscreteCosineTransform ───────────────────────────────────────────

class TestDiscreteCosineTransform:
    def test_constant_signal(self):
        # DCT-2 of constant → first coefficient is large, rest zero
        # nv
        x = np.ones(4)
        result = _drive(DiscreteCosineTransform, x)
        assert result is not None
        assert len(result) == 4
        # first coefficient = 2*N * x[0] for constant = 8.0
        assert abs(result[0] - 8.0) < 1e-10
        assert all(abs(result[i]) < 1e-10 for i in range(1, 4))

    def test_type_2_is_default(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        result_default = _drive(DiscreteCosineTransform, x)
        result_type2 = _drive(DiscreteCosineTransform, x, 2)
        assert result_default is not None
        assert np.allclose(result_default, result_type2, atol=1e-10)

    def test_type_1(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _drive(DiscreteCosineTransform, x, 1)
        assert result is not None
        assert len(result) == 5

    def test_wrong_result_fails(self):
        # nv
        x = np.ones(4)
        assert _fails_with_wrong_result(DiscreteCosineTransform, x)


# ── TestInverseDiscreteCosineTransform ────────────────────────────────────

class TestInverseDiscreteCosineTransform:
    def test_round_trip(self):
        # nv
        x = np.array([1.0, 2.0, 3.0, 4.0])
        coeffs = _drive(DiscreteCosineTransform, x)
        # Backward direction of DiscreteCosineTransform: DCT(result_var, coeffs) → result_var = idct(coeffs)
        recovered = _drive_bwd(DiscreteCosineTransform, coeffs)
        assert recovered is not None
        assert np.allclose(recovered, x, atol=1e-10)

    def test_type_2_round_trip(self):
        # nv
        x = np.array([1.0, 0.0, -1.0, 0.0])
        coeffs = _drive(DiscreteCosineTransform, x, 2)
        # Backward direction with TYPE: DiscreteCosineTransform(result_var, TYPE, coeffs)
        recovered = _drive_bwd_n(DiscreteCosineTransform, 2, coeffs)
        assert recovered is not None
        assert np.allclose(recovered, x, atol=1e-10)

    def test_wrong_result_fails(self):
        # Consistency check: DiscreteCosineTransform(wrong_x, coeffs) where wrong_x ≠ idct(coeffs) fails
        # nv
        coeffs = np.array([8.0, 0.0, 0.0, 0.0])
        wrong_x = np.array([9.0, 9.0, 9.0, 9.0])
        trail = Trail()
        dispatch = DiscreteCosineTransform._get_dispatch()
        gen = dispatch(None, None, None, None, wrong_x, coeffs, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── TestFFTFrequencies ────────────────────────────────────────────────────

class TestFFTFrequencies:
    def test_length_4(self):
        # fftfreq(4) → [0, 0.25, -0.5, -0.25]
        # nv
        result = _drive(FFTFrequencies, 4)
        assert result is not None
        expected = np.array([0.0, 0.25, -0.5, -0.25])
        assert np.allclose(result, expected, atol=1e-10)

    def test_with_sample_spacing(self):
        # fftfreq(4, d=2.0) → [0, 0.125, -0.25, -0.125]
        # nv
        result = _drive(FFTFrequencies, 4, 2.0)
        assert result is not None
        expected = np.array([0.0, 0.125, -0.25, -0.125])
        assert np.allclose(result, expected, atol=1e-10)

    def test_length_equals_n(self):
        # nv
        result = _drive(FFTFrequencies, 8)
        assert result is not None
        assert len(result) == 8

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(FFTFrequencies, 4)


# ── TestRealFFTFrequencies ────────────────────────────────────────────────

class TestRealFFTFrequencies:
    def test_length_4(self):
        # rfftfreq(4) → [0, 0.25, 0.5]  (length n//2+1)
        # nv
        result = _drive(RealFFTFrequencies, 4)
        assert result is not None
        expected = np.array([0.0, 0.25, 0.5])
        assert np.allclose(result, expected, atol=1e-10)

    def test_length_is_n_half_plus_one(self):
        # nv
        result = _drive(RealFFTFrequencies, 8)
        assert result is not None
        assert len(result) == 5  # 8//2 + 1

    def test_with_sample_spacing(self):
        # nv
        result = _drive(RealFFTFrequencies, 4, 2.0)
        assert result is not None
        expected = np.array([0.0, 0.125, 0.25])
        assert np.allclose(result, expected, atol=1e-10)

    def test_all_non_negative(self):
        # nv
        result = _drive(RealFFTFrequencies, 8)
        assert result is not None
        assert all(f >= 0.0 for f in result)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(RealFFTFrequencies, 4)


# ── TestFFTShift ──────────────────────────────────────────────────────────

class TestFFTShift:
    def test_1d_shift(self):
        # fftshift([0,1,2,3]) → [2,3,0,1]
        # nv
        x = np.array([0.0, 1.0, 2.0, 3.0])
        result = _drive(FFTShift, x)
        assert result is not None
        expected = np.array([2.0, 3.0, 0.0, 1.0])
        assert np.allclose(result, expected, atol=1e-10)

    def test_moves_dc_to_centre(self):
        # after fftshift the DC component (index 0 of fftfreq) should be centred
        # nv
        freqs = _drive(FFTFrequencies, 4)
        shifted_freqs = _drive(FFTShift, freqs)
        assert shifted_freqs is not None
        # centre of length-4 array is index 2 (or 1), DC (0.0) should be there
        assert abs(shifted_freqs[len(shifted_freqs) // 2]) < 1e-10

    def test_2d_shift(self):
        # nv
        x = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = _drive(FFTShift, x)
        assert result is not None
        assert result.shape == (2, 2)

    def test_wrong_result_fails(self):
        # nv
        x = np.array([0.0, 1.0, 2.0, 3.0])
        assert _fails_with_wrong_result(FFTShift, x)


# ── TestInverseFFTShift ───────────────────────────────────────────────────

class TestInverseFFTShift:
    def test_round_trip_1d(self):
        # nv
        x = np.array([0.0, 1.0, 2.0, 3.0])
        shifted = _drive(FFTShift, x)
        # Backward direction of FFTShift: FFTShift(result_var, shifted) → result_var = ifftshift(shifted)
        recovered = _drive_bwd(FFTShift, shifted)
        assert recovered is not None
        assert np.allclose(recovered, x, atol=1e-10)

    def test_round_trip_2d(self):
        # nv
        x = np.array([[1.0, 2.0], [3.0, 4.0]])
        shifted = _drive(FFTShift, x)
        recovered = _drive_bwd(FFTShift, shifted)
        assert recovered is not None
        assert np.allclose(recovered, x, atol=1e-10)

    def test_wrong_result_fails(self):
        # Consistency check: FFTShift(wrong_x, shifted) where wrong_x ≠ ifftshift(shifted) fails
        # nv
        shifted = np.array([2.0, 3.0, 0.0, 1.0])
        wrong_x = np.array([9.0, 9.0, 9.0, 9.0])
        trail = Trail()
        dispatch = FFTShift._get_dispatch()
        gen = dispatch(None, None, None, None, wrong_x, shifted, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── Fixture integration ───────────────────────────────────────────────────

import os
from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestClausalFixture:
    """Run Test predicates from tests/fixtures/scipy_fft_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_fft_tests")

    @pytest.mark.parametrize("name", [
        "fft constant signal",
        "fft round trip",
        "real fft output length",
        "fft frequencies length 4",
        "real fft frequencies non negative",
        "fft shift and inverse",
        "dct round trip",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
