# scipy.fft — Fast Fourier Transforms

The `scipy_fft` module wraps [`scipy.fft`](https://docs.scipy.org/doc/scipy/reference/fft.html) as Clausal predicates. It covers 1-D, 2-D, and N-D forward and inverse DFTs, real-input transforms, discrete cosine transforms, and frequency/shift utilities.

---

## Import

```clausal
# skip
-import_from(scipy_fft, [FFTransform, RealFFT, FFTFrequencies, FFTShift, ...])
```

Or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_fft, [FFTransform, RealFFT, ...])
```

---

## Tier

All predicates are **Tier 1 — pure functions**: NumPy array in, NumPy array (or scalar array) directly in `RESULT`. No result dicts, no `ResultGet` needed.

## Bidirectionality

The core transform predicates are **bidirectional relations**: they dispatch on argument groundness, running forward or backward depending on which arguments are bound.

| Bidirectional predicate | Forward | Backward |
|---|---|---|
| `FFTransform(X, Y)` | `fft(x)` | `ifft(y)` |
| `FFTransform2D(X, Y)` | `fft2(x)` | `ifft2(y)` |
| `FFTransformND(X, Y)` | `fftn(x)` | `ifftn(y)` |
| `RealFFT(X, Y)` | `rfft(x)` | `irfft(y)` |
| `DiscreteCosineTransform(X, Y)` | `dct(x)` | `idct(y)` |
| `DiscreteSineTransform(X, Y)` | `dst(x)` | `idst(y)` |
| `FFTShift(X, Y)` | `fftshift(x)` | `ifftshift(y)` |

```clausal
# skip
FFTransform(++(np.array([1,0,0,0])), RESULT),
# RESULT is unified with the complex spectrum array
```

---

## Naming conventions

Abbreviations that are the universal name are kept as-is; others are spelled out:

| scipy function | Clausal predicate |
|---|---|
| `fft` | `FFTransform` forward |
| `ifft` | `FFTransform` backward |
| `fft2` | `FFTransform2D` forward |
| `ifft2` | `FFTransform2D` backward |
| `fftn` | `FFTransformND` forward |
| `ifftn` | `FFTransformND` backward |
| `rfft` | `RealFFT` forward |
| `irfft` | `RealFFT` backward |
| `dct` | `DiscreteCosineTransform` forward |
| `idct` | `DiscreteCosineTransform` backward |
| `dst` | `DiscreteSineTransform` forward |
| `idst` | `DiscreteSineTransform` backward |
| `fftfreq` | `FFTFrequencies` |
| `rfftfreq` | `RealFFTFrequencies` |
| `fftshift` | `FFTShift` forward |
| `ifftshift` | `FFTShift` backward |

**Why `FFTransform` instead of `FFT`?**

In `.clausal` source, any identifier whose alphabetic characters are _all_ uppercase is parsed as a [logic variable](syntax.md), not a predicate name. `FFT`, `FFT2D`, and `FFTND` are entirely uppercase, so they would be treated as unbound variables rather than callable predicates. Spelling them as `FFTransform`, `FFTransform2D`, and `FFTransformND` introduces lowercase letters, making them unambiguously predicate names.

All other predicates in this module (`RealFFT`, `FFTShift`, `FFTFrequencies`, etc.) already contain lowercase letters from their prefixes and suffixes, so they work without this adjustment.

---

## Predicate catalogue

### 1-D transforms

```clausal
# skip
FFTransform(X, Y)                  # bidirectional
    X ground, Y unbound → Y = fft(x)   # forward DFT
    Y ground, X unbound → X = ifft(y)  # backward (inverse DFT)
    Both ground         → consistency check: succeeds iff fft(x) ≈ y
    X:      real or complex 1-D array
    Y:      complex array of length len(X)

FFTransform(X, N, Y)               # bidirectional; N always ground
    N: output length (zero-pads or truncates).
```

Example — frequency analysis of a sine wave:

```clausal
-import_from(scipy_fft, [FFTransform, FFTFrequencies])

FrequencySpectrum(SIGNAL, FREQS, SPECTRUM) <- (
    FFTransform(SIGNAL, SPECTRUM),
    LEN is ++(len(SIGNAL)),
    FFTFrequencies(LEN, FREQS)
)
```

---

### 2-D transforms

```clausal
# skip
FFTransform2D(X, Y)                # bidirectional
    X ground, Y unbound → Y = fft2(x)   # 2-D forward DFT over last two axes
    Y ground, X unbound → X = ifft2(y)  # backward (2-D inverse DFT)
    Both ground         → consistency check: succeeds iff fft2(x) ≈ y
    X:      2-D real or complex array
    Y:      complex array of the same shape

FFTransform2D(X, S, Y)             # bidirectional; S always ground
    S: output shape as (rows, cols); zero-pads or truncates X to this shape.
```

Example — round-trip:

```clausal
-import_from(scipy_fft, [FFTransform2D])

RoundTrip2D(IMAGE, RECOVERED) <- (
    FFTransform2D(IMAGE, SPECTRUM),
    FFTransform2D(RECOVERED, SPECTRUM)
)
```

---

### N-D transforms

```clausal
# skip
FFTransformND(X, Y)                # bidirectional
    X ground, Y unbound → Y = fftn(x)   # N-D forward DFT over all axes
    Y ground, X unbound → X = ifftn(y)  # backward (N-D inverse DFT)
    Both ground         → consistency check: succeeds iff fftn(x) ≈ y
    Y:      complex array of the same shape as X

FFTransformND(X, S, Y)             # bidirectional; S always ground
    S: list of output lengths, one per axis.
```

---

### Real-input transforms

`RealFFT` exploits conjugate symmetry to halve storage for real signals. The output of `RealFFT` has length `N//2 + 1`.

```clausal
# skip
RealFFT(X, Y)                      # bidirectional
    X ground, Y unbound → Y = rfft(x)   forward: complex half-spectrum of length N//2 + 1
    Y ground, X unbound → X = irfft(y)  backward: real array of length 2*(len(Y)-1)
    Both ground         → consistency check: succeeds iff rfft(x) ≈ y
    Note: assumes even-length original signal when going backward without N.

RealFFT(X, N, Y)                   # bidirectional; N always ground
    N: explicit length for unambiguous round-trips of odd-length originals.
```

Example — filter a 1-D signal in the frequency domain:

```clausal
-import_from(scipy_fft, [RealFFT])

LowPassFilter(SIGNAL, CUTOFF_BIN, FILTERED) <- (
    RealFFT(SIGNAL, SPECTRUM),
    ZEROED is ++(
        [SPECTRUM[i] if i < int(CUTOFF_BIN) else 0.0
         for i in range(len(SPECTRUM))]),
    RealFFT(FILTERED, ++ZEROED)
)
```

---

### Cosine and sine transforms

```clausal
# skip
DiscreteCosineTransform(X, Y)              # bidirectional
    X ground, Y unbound → Y = dct(x)   (type-2 default)
    Y ground, X unbound → X = idct(y)
    Both ground         → consistency check: succeeds iff dct(x) ≈ y

DiscreteCosineTransform(X, TYPE, Y)        # bidirectional; TYPE always ground
    TYPE: integer 1–4 selecting the DCT variant.

DiscreteSineTransform(X, Y)                # bidirectional
    X ground, Y unbound → Y = dst(x)   (type-2 default)
    Y ground, X unbound → X = idst(y)
    Both ground         → consistency check: succeeds iff dst(x) ≈ y

DiscreteSineTransform(X, TYPE, Y)          # bidirectional; TYPE always ground
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

```clausal
# skip
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

FFTShift(X, Y)                     # bidirectional
    X ground, Y unbound → Y = fftshift(x)   (DC to centre)
    Y ground, X unbound → X = ifftshift(y)  (DC back to index 0)
    Both ground         → consistency check: succeeds iff fftshift(x) ≈ y
```

Example — plot-ready spectrum:

```clausal
-import_from(scipy_fft, [FFTransform, FFTFrequencies, FFTShift])

CentredSpectrum(SIGNAL, FREQS_CENTRED, SPECTRUM_CENTRED) <- (
    LEN is ++(len(SIGNAL)),
    FFTransform(SIGNAL, SPECTRUM),
    FFTFrequencies(LEN, FREQS),
    FFTShift(SPECTRUM, SPECTRUM_CENTRED),
    FFTShift(FREQS, FREQS_CENTRED)
)
```

---

## Complete examples

### Round-trip: 1-D signal

```clausal
# skip
-import_from(scipy_fft, [FFTransform])

TestRoundTrip(SIGNAL) <- (
    FFTransform(SIGNAL, SPECTRUM),
    FFTransform(RECOVERED, SPECTRUM),
    % check first element recovered correctly
    ERR is ++(abs(float(RECOVERED[0].real) - float(SIGNAL[0]))),
    ERR < 1e-10
)
```

### Convolution via FFT

```clausal
# skip
-import_from(scipy_fft, [FFTransform])

# Linear convolution of two equal-length signals (circular; pad as needed)
FFTConvolve(A, B, RESULT) <- (
    FFTransform(A, FA),
    FFTransform(B, FB),
    PRODUCT is ++(FA * FB),
    FFTransform(RESULT, ++PRODUCT)
)
```

### Image spectrum (2-D)

```clausal
-import_from(scipy_fft, [FFTransform2D, FFTShift])

ImageSpectrum(IMAGE, CENTRED_SPECTRUM) <- (
    FFTransform2D(IMAGE, SPECTRUM),
    FFTShift(SPECTRUM, CENTRED_SPECTRUM)
)
```

---

## Notes

- **Array inputs**: pass Python lists or NumPy arrays via [`++()`](python_integration.md).
- **Complex output**: `FFTransform`, `FFTransform2D`, `FFTransformND`,
  `RealFFT` all return complex128 arrays. Use `++(x.real)` to extract the
  real part.
- **RealFFT backward output length**: by default, output length is
  `2 * (len(X) - 1)`, which assumes the original signal had even length.
  Pass `N` explicitly for odd-length originals.
- **Normalisation**: the default (un-normalised) convention is `fft` followed
  by `ifft` recovers the original signal. Pass `NORM='ortho'` for the
  orthonormal convention — but this requires the 3-arity form which is not yet
  exposed; use the `++()` escape directly for that case.
- Predicates fail (no solution) when scipy raises an exception, or when a
  bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.signal](scipy_signal.md) — signal processing using FFT · [scipy.interpolate](scipy_interpolate.md) — frequency-domain interpolation.*
