# scipy.fft — Fast Fourier Transforms

The `scipy_fft` module wraps [`scipy.fft`](https://docs.scipy.org/doc/scipy/reference/fft.html) as Clausal Prolog predicates. It covers 1-D, 2-D, and N-D forward and inverse DFTs, real-input transforms, discrete cosine transforms, and frequency/shift utilities.

---

## Import

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:import"
```

Or via the canonical `py.*` path:

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:import_ex2"
```

---

## Tier

All predicates are **Tier 1 — pure functions**: NumPy array in, NumPy array (or scalar array) directly in `RESULT`. No result dicts, no `result_get` needed.

## Bidirectionality

The core transform predicates are **bidirectional relations**: they dispatch on argument groundness, running forward or backward depending on which arguments are bound.

| Bidirectional predicate | Forward | Backward |
|---|---|---|
| `fft_transform(X, Y)` | `fft(x)` | `ifft(y)` |
| `fft_transform2d(X, Y)` | `fft2(x)` | `ifft2(y)` |
| `fft_transformnd(X, Y)` | `fftn(x)` | `ifftn(y)` |
| `real_fft(X, Y)` | `rfft(x)` | `irfft(y)` |
| `discrete_cosine_transform(X, Y)` | `dct(x)` | `idct(y)` |
| `discrete_sine_transform(X, Y)` | `dst(x)` | `idst(y)` |
| `fft_shift(X, Y)` | `fftshift(x)` | `ifftshift(y)` |

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:bidirectionality"
```

---

## Naming conventions

Abbreviations that are the universal name are kept as-is; others are spelled out:

| scipy function | Clausal Prolog predicate |
|---|---|
| `fft` | `fft_transform` forward |
| `ifft` | `fft_transform` backward |
| `fft2` | `fft_transform2d` forward |
| `ifft2` | `fft_transform2d` backward |
| `fftn` | `fft_transformnd` forward |
| `ifftn` | `fft_transformnd` backward |
| `rfft` | `real_fft` forward |
| `irfft` | `real_fft` backward |
| `dct` | `discrete_cosine_transform` forward |
| `idct` | `discrete_cosine_transform` backward |
| `dst` | `discrete_sine_transform` forward |
| `idst` | `discrete_sine_transform` backward |
| `fftfreq` | `fft_frequencies` |
| `rfftfreq` | `real_fft_frequencies` |
| `fftshift` | `fft_shift` forward |
| `ifftshift` | `fft_shift` backward |

**Why `fft_transform` instead of `FFT`?**

In `.seam` source, any identifier whose alphabetic characters are _all_ uppercase is parsed as a [logic variable](syntax.md), not a predicate name. `FFT`, `FFT2D`, and `FFTND` are entirely uppercase, so they would be treated as unbound variables rather than callable predicates. Spelling them as `fft_transform`, `fft_transform2d`, and `fft_transformnd` introduces lowercase letters, making them unambiguously predicate names.

All other predicates in this module (`real_fft`, `fft_shift`, `fft_frequencies`, etc.) already contain lowercase letters from their prefixes and suffixes, so they work without this adjustment.

---

## Predicate catalogue

### 1-D transforms

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_1d_transforms"
```

Example — frequency analysis of a sine wave:

```seam
-import_from(scipy_fft, [fft_transform, fft_frequencies])

frequency_spectrum(SIGNAL, FREQS, SPECTRUM) <- (
    fft_transform(SIGNAL, SPECTRUM),
    LEN is ++(len(SIGNAL)),
    fft_frequencies(LEN, FREQS)
)
```

---

### 2-D transforms

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_2d_transforms"
```

Example — round-trip:

```seam
-import_from(scipy_fft, [fft_transform2d])

round_trip2_d(IMAGE, RECOVERED) <- (
    fft_transform2d(IMAGE, SPECTRUM),
    fft_transform2d(RECOVERED, SPECTRUM)
)
```

---

### N-D transforms

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:fft_nd_transforms"
```

---

### Real-input transforms

`real_fft` exploits conjugate symmetry to halve storage for real signals. The output of `real_fft` has length `N//2 + 1`.

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:real_input_transforms"
```

Example — filter a 1-D signal in the frequency domain:

```seam
-import_from(scipy_fft, [real_fft])

low_pass_filter(SIGNAL, CUTOFF_BIN, FILTERED) <- (
    real_fft(SIGNAL, SPECTRUM),
    ZEROED is ++(
        [SPECTRUM[i] if i < int(CUTOFF_BIN) else 0.0
         for i in range(len(SPECTRUM))]),
    real_fft(FILTERED, ++ZEROED)
)
```

---

### Cosine and sine transforms

```seam
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

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:utility"
```

Example — plot-ready spectrum:

```seam
-import_from(scipy_fft, [fft_transform, fft_frequencies, fft_shift])

centred_spectrum(SIGNAL, FREQS_CENTRED, SPECTRUM_CENTRED) <- (
    LEN is ++(len(SIGNAL)),
    fft_transform(SIGNAL, SPECTRUM),
    fft_frequencies(LEN, FREQS),
    fft_shift(SPECTRUM, SPECTRUM_CENTRED),
    fft_shift(FREQS, FREQS_CENTRED)
)
```

---

## Complete examples

### Round-trip: 1-D signal

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:round_trip_1_d_signal"
```

### Convolution via FFT

```seam
--8<-- "tests/fixtures/docs/scipy_fft_sigs.txt:convolution_via_fft"
```

### Image spectrum (2-D)

```seam
-import_from(scipy_fft, [fft_transform2d, fft_shift])

image_spectrum(IMAGE, CENTRED_SPECTRUM) <- (
    fft_transform2d(IMAGE, SPECTRUM),
    fft_shift(SPECTRUM, CENTRED_SPECTRUM)
)
```

---

## Notes

- **Array inputs**: pass Python lists or NumPy arrays via [`++()`](python_integration.md).
- **Complex output**: `fft_transform`, `fft_transform2d`, `fft_transformnd`,
  `real_fft` all return complex128 arrays. Use `++(x.real)` to extract the
  real part.
- **real_fft backward output length**: by default, output length is
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
