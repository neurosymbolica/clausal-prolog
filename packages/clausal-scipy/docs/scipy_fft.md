# scipy.fft — Fast Fourier Transforms

The `scipy_fft` module wraps [`scipy.fft`](https://docs.scipy.org/doc/scipy/reference/fft.html) as Clausal predicates. It covers 1-D, 2-D, and N-D forward and inverse DFTs, real-input transforms, discrete cosine transforms, and frequency/shift utilities.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:import_ex2"
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
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:bidirectionality"
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

in_ `.clausal` source, any identifier whose alphabetic characters are _all_ uppercase is parsed as a [logic variable](syntax.md), not a predicate name. `FFT`, `FFT2D`, and `FFTND` are entirely uppercase, so they would be treated as unbound variables rather than callable predicates. Spelling them as `FFTransform`, `FFTransform2D`, and `FFTransformND` introduces lowercase letters, making them unambiguously predicate names.

All other predicates in this module (`RealFFT`, `FFTShift`, `FFTFrequencies`, etc.) already contain lowercase letters from their prefixes and suffixes, so they work without this adjustment.

---

## Predicate catalogue

### 1-D transforms

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_1d_transforms"
```

Example — frequency analysis of a sine wave:

```clausal
-import_from(scipy_fft, [FFTransform, FFTFrequencies])

frequency_spectrum(SIGNAL, FREQS, SPECTRUM) <- (
    FFTransform(SIGNAL, SPECTRUM),
    LEN is ++(len(SIGNAL)),
    FFTFrequencies(LEN, FREQS)
)
```

---

### 2-D transforms

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_2d_transforms"
```

Example — round-trip:

```clausal
-import_from(scipy_fft, [FFTransform2D])

round_trip2_d(IMAGE, RECOVERED) <- (
    FFTransform2D(IMAGE, SPECTRUM),
    FFTransform2D(RECOVERED, SPECTRUM)
)
```

---

### N-D transforms

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_nd_transforms"
```

---

### Real-input transforms

`RealFFT` exploits conjugate symmetry to halve storage for real signals. The output of `RealFFT` has length `N//2 + 1`.

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:real_input_transforms"
```

Example — filter a 1-D signal in the frequency domain:

```clausal
-import_from(scipy_fft, [RealFFT])

low_pass_filter(SIGNAL, CUTOFF_BIN, FILTERED) <- (
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
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:cosine_and_sine_transforms"
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
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:utility"
```

Example — plot-ready spectrum:

```clausal
-import_from(scipy_fft, [FFTransform, FFTFrequencies, FFTShift])

centred_spectrum(SIGNAL, FREQS_CENTRED, SPECTRUM_CENTRED) <- (
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
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:round_trip_1_d_signal"
```

### Convolution via FFT

```clausal
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:convolution_via_fft"
```

### Image spectrum (2-D)

```clausal
-import_from(scipy_fft, [FFTransform2D, FFTShift])

image_spectrum(IMAGE, CENTRED_SPECTRUM) <- (
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
