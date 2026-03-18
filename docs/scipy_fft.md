# scipy.fft — Fast Fourier Transforms

The `scipy_fft` module wraps [`scipy.fft`](https://docs.scipy.org/doc/scipy/reference/fft.html) as Clausal predicates. It covers 1-D, 2-D, and N-D forward and inverse DFTs, real-input transforms, discrete cosine transforms, and frequency/shift utilities.

---

## Import

```
-import_from(scipy_fft, [FFTransform, InverseFFT, RealFFT, FFTFrequencies, FFTShift, ...])
```

Or via the canonical `py.*` path:

```
-import_from(py.scipy_fft, [FFTransform, InverseFFT, ...])
```

---

## Tier

All predicates are **Tier 1 — pure functions**: NumPy array in, NumPy array (or scalar array) directly in `RESULT`. No result dicts, no `ResultGet` needed.

```
FFTransform(++(np.array([1,0,0,0])), RESULT),
% RESULT is unified with the complex spectrum array
```

---

## Naming conventions

Abbreviations that are the universal name are kept as-is; others are spelled out:

| scipy function | Clausal predicate |
|---|---|
| `fft` | `FFTransform` |
| `ifft` | `InverseFFT` |
| `fft2` | `FFTransform2D` |
| `ifft2` | `InverseFFT2D` |
| `fftn` | `FFTransformND` |
| `rfft` | `RealFFT` |
| `irfft` | `InverseRealFFT` |
| `dct` | `DiscreteCosineTransform` |
| `idct` | `InverseDiscreteCosineTransform` |
| `fftfreq` | `FFTFrequencies` |
| `rfftfreq` | `RealFFTFrequencies` |
| `fftshift` | `FFTShift` |
| `ifftshift` | `InverseFFTShift` |

**Why `FFTransform` instead of `FFT`?**

In `.clausal` source, any identifier whose alphabetic characters are _all_ uppercase is parsed as a logic variable, not a predicate name. `FFT`, `FFT2D`, and `FFTND` are entirely uppercase, so they would be treated as unbound variables rather than callable predicates. Spelling them as `FFTransform`, `FFTransform2D`, and `FFTransformND` introduces lowercase letters, making them unambiguously predicate names.

All other predicates in this module (`InverseFFT`, `RealFFT`, `FFTShift`, `FFTFrequencies`, etc.) already contain lowercase letters from their prefixes and suffixes, so they work without this adjustment.

---

## Predicate catalogue

### 1-D transforms

```
FFTransform(X, RESULT)
    1-D forward Discrete Fourier Transform of array X.
    X:      real or complex 1-D array
    RESULT: complex array of length len(X)

FFTransform(X, N, RESULT)
    N: output length; zero-pads or truncates X to length N before computing.

InverseFFT(X, RESULT)
    1-D inverse DFT.
    RESULT: complex array of length len(X)

InverseFFT(X, N, RESULT)
    N: output length.
```

Example — frequency analysis of a sine wave:

```
-import_from(scipy_fft, [FFTransform, FFTFrequencies])

FrequencySpectrum(SIGNAL_, FREQS_, SPECTRUM_) <- (
    FFTransform(SIGNAL_, SPECTRUM_) and
    LEN_ is ++(len(SIGNAL_)) and
    FFTFrequencies(LEN_, FREQS_)
)
```

---

### 2-D transforms

```
FFTransform2D(X, RESULT)
    2-D forward DFT over the last two axes.
    X:      2-D real or complex array
    RESULT: complex array of the same shape

FFTransform2D(X, S, RESULT)
    S: output shape as (rows, cols); zero-pads or truncates X to this shape.

InverseFFT2D(X, RESULT)
    2-D inverse DFT.

InverseFFT2D(X, S, RESULT)
    S: output shape.
```

Example — round-trip:

```
-import_from(scipy_fft, [FFTransform2D, InverseFFT2D])

RoundTrip2D(IMAGE_, RECOVERED_) <- (
    FFTransform2D(IMAGE_, SPECTRUM_) and
    InverseFFT2D(SPECTRUM_, RECOVERED_)
)
```

---

### N-D transforms

```
FFTransformND(X, RESULT)
    N-D forward DFT over all axes of array X.
    RESULT: complex array of the same shape

FFTransformND(X, S, RESULT)
    S: list of output lengths, one per axis.
```

---

### Real-input transforms

`RealFFT` and `InverseRealFFT` exploit conjugate symmetry to halve storage for
real signals. The output of `RealFFT` has length `N//2 + 1`.

```
RealFFT(X, RESULT)
    Real-input forward FFT of 1-D real array X.
    X:      1-D real array of length N
    RESULT: complex array of length N//2 + 1

RealFFT(X, N, RESULT)
    N: output length before FFT (pads/truncates X).

InverseRealFFT(X, RESULT)
    Inverse of RealFFT; produces a real-valued output.
    X:      complex half-spectrum of length N//2 + 1
    RESULT: real array of length 2*(len(X)-1)
    Note: assumes even-length original signal.

InverseRealFFT(X, N, RESULT)
    N: explicit output length (required for odd-length originals).
```

Example — filter a 1-D signal in the frequency domain:

```
-import_from(scipy_fft, [RealFFT, InverseRealFFT])

LowPassFilter(SIGNAL_, CUTOFF_BIN_, FILTERED_) <- (
    RealFFT(SIGNAL_, SPECTRUM_) and
    ZEROED_ is ++(
        [SPECTRUM_[i] if i < int(CUTOFF_BIN_) else 0.0
         for i in range(len(SPECTRUM_))]) and
    InverseRealFFT(++ZEROED_, FILTERED_)
)
```

---

### Cosine transforms

```
DiscreteCosineTransform(X, RESULT)
    DCT type-2 (the default) of 1-D array X.
    RESULT: real array of the same length

DiscreteCosineTransform(X, TYPE, RESULT)
    TYPE: integer 1–4 selecting the DCT variant.

InverseDiscreteCosineTransform(X, RESULT)
    Inverse DCT type-2.  InverseDCT(DCT(x)) ≈ x.

InverseDiscreteCosineTransform(X, TYPE, RESULT)
    TYPE: must match the type used in DiscreteCosineTransform.
```

DCT types:

| TYPE | Description |
|---|---|
| 1 | DCT-I: symmetric boundary conditions |
| 2 | DCT-II: default; used in JPEG compression |
| 3 | DCT-III: inverse of DCT-II (up to a scale) |
| 4 | DCT-IV: symmetric half-sample |

---

### Utility

```
FFTFrequencies(N, RESULT)
    DFT sample frequencies for a length-N transform with unit sample spacing.
    RESULT: real array of length N
    Layout: [0, 1/N, 2/N, ..., -k/N, ..., -1/N]
            where k = N//2

FFTFrequencies(N, D, RESULT)
    D: sample spacing in seconds (reciprocal of sample rate).
       Frequencies are in cycles per unit time (Hz if D is in seconds).

RealFFTFrequencies(N, RESULT)
    Sample frequencies for a length-N real FFT output.
    RESULT: real array of length N//2 + 1 (all non-negative)

RealFFTFrequencies(N, D, RESULT)
    D: sample spacing.

FFTShift(X, RESULT)
    Shift the zero-frequency component to the centre of the spectrum.
    Input index 0 (DC) moves to index N//2.
    Useful for plotting: low frequencies appear in the middle.

InverseFFTShift(X, RESULT)
    Inverse of FFTShift.  InverseFFTShift(FFTShift(X)) = X.
```

Example — plot-ready spectrum:

```
-import_from(scipy_fft, [FFTransform, FFTFrequencies, FFTShift])

CentredSpectrum(SIGNAL_, FREQS_CENTRED_, SPECTRUM_CENTRED_) <- (
    LEN_ is ++(len(SIGNAL_)) and
    FFTransform(SIGNAL_, SPECTRUM_) and
    FFTFrequencies(LEN_, FREQS_) and
    FFTShift(SPECTRUM_, SPECTRUM_CENTRED_) and
    FFTShift(FREQS_, FREQS_CENTRED_)
)
```

---

## Complete examples

### Round-trip: 1-D signal

```
-import_from(scipy_fft, [FFTransform, InverseFFT])

TestRoundTrip(SIGNAL_) <- (
    FFTransform(SIGNAL_, SPECTRUM_) and
    InverseFFT(SPECTRUM_, RECOVERED_) and
    % check first element recovered correctly
    ERR_ is ++(abs(float(RECOVERED_[0].real) - float(SIGNAL_[0]))) and
    ERR_ < 1e-10
)
```

### Convolution via FFT

```
-import_from(scipy_fft, [FFTransform, InverseFFT])

% Linear convolution of two equal-length signals (circular; pad as needed)
FFTConvolve(A_, B_, RESULT_) <- (
    FA_ is ++(list(__import__('clausal.modules.py.scipy_fft', fromlist=['FFTransform']))),
    FFTransform(A_, FA_) and
    FFTransform(B_, FB_) and
    PRODUCT_ is ++(FA_ * FB_) and
    InverseFFT(++PRODUCT_, RESULT_)
)
```

### Image spectrum (2-D)

```
-import_from(scipy_fft, [FFTransform2D, FFTShift])

ImageSpectrum(IMAGE_, CENTRED_SPECTRUM_) <- (
    FFTransform2D(IMAGE_, SPECTRUM_) and
    FFTShift(SPECTRUM_, CENTRED_SPECTRUM_)
)
```

---

## Notes

- **Array inputs**: pass Python lists or NumPy arrays via `++()`.
- **Complex output**: `FFTransform`, `InverseFFT`, `FFTransform2D`, `InverseFFT2D`, `FFTransformND`,
  `RealFFT` all return complex128 arrays. Use `++(x.real)` to extract the
  real part.
- **InverseRealFFT output length**: by default, output length is
  `2 * (len(X) - 1)`, which assumes the original signal had even length.
  Pass `N` explicitly for odd-length originals.
- **Normalisation**: the default (un-normalised) convention is `fft` followed
  by `ifft` recovers the original signal. Pass `NORM='ortho'` for the
  orthonormal convention — but this requires the 3-arity form which is not yet
  exposed; use the `++()` escape directly for that case.
- Predicates fail (no solution) when scipy raises an exception, or when a
  bound `RESULT` does not unify with the computed value.
