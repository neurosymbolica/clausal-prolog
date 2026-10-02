# scipy.signal — Signal Processing

The `scipy_signal` module wraps [`scipy.signal`](https://docs.scipy.org/doc/scipy/reference/signal.html) as Clausal predicates. It covers IIR filter design, causal and zero-phase filtering, convolution, correlation, and spectral analysis.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:import_ex2"
```

---

## Tiers

| Tier | Predicates | RESULT type |
|---|---|---|
| **Tier 2** | include design, frequency_response, periodogram, welch, spectrogram | dict — use `ResultGet` |
| **Tier 1** | linear_filter, sos_filter, forward_backward_filter, sos_forward_backward_filter, decimate, resample, convolve, correlate, fft_convolve | array (or dict when `ZI` supplied) |

---

## Naming conventions

| scipy function | Clausal predicate |
|---|---|
| `butter` | `butterworth` |
| `bessel` | `bessel` |
| `cheby1` | `chebyshev_type1` |
| `cheby2` | `chebyshev_type2` |
| `ellip` | `elliptic` |
| `freqz` | `frequency_response` |
| `lfilter` | `linear_filter` |
| `sosfilt` | `sos_filter` |
| `filtfilt` | `forward_backward_filter` |
| `sosfiltfilt` | `sos_forward_backward_filter` |
| `decimate` | `decimate` |
| `resample` | `resample` |
| `convolve` | `convolve` |
| `correlate` | `correlate` |
| `fftconvolve` | `fft_convolve` |
| `periodogram` | `periodogram` |
| `welch` | `welch` |
| `spectrogram` | `spectrogram` |

`SOS` (second-order sections) and `FFT` are kept as universal abbreviations. All other names are spelled out in full.

---

## include design (Tier 2)

include design predicates return a result dict keyed by the `OUTPUT` format:

| OUTPUT | Dict keys |
|---|---|
| `'ba'` (default) | `b`, `a` |
| `'zpk'` | `z`, `p`, `k` |
| `'sos'` | `sos` |

Use `ResultGet` to extract fields:

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:include_design"
```

### butterworth

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:butterworth"
```

### bessel

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:bessel"
```

### chebyshev_type1

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:chebyshevtype1"
```

### chebyshev_type2

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:chebyshevtype2"
```

### elliptic

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:elliptic"
```

### frequency_response

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:frequencyresponse"
```

---

## Filtering (Tier 1)

### linear_filter

Causal IIR filter using direct-form II transposed implementation.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:linearfilter"
```

### sos_filter

Numerically more stable than `linear_filter` for higher-order filters. Use when `OUTPUT='sos'` in filter design.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:sosfilter"
```

### forward_backward_filter

Zero-phase filtering: applies the filter twice (forward then backward), eliminating phase distortion. Signal length must be longer than the filter's padding requirements.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:forwardbackwardfilter"
```

### sos_forward_backward_filter

SOS form of `forward_backward_filter`. Preferred for high-order filters.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:sosforwardbackwardfilter"
```

### decimate

Low-pass filter then downsample by integer factor `Q`.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:decimate"
```

### resample

resample to exactly `NUM` samples using Fourier method. Suitable for arbitrary rational resampling ratios.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:resample"
```

---

## Convolution and correlation (Tier 1)

### convolve

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:convolve"
```

### correlate

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:correlate"
```

### fft_convolve

Convolution via FFT — efficient for large arrays or long filters.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:fftconvolve"
```

---

## Spectral analysis (Tier 2)

### periodogram

Non-averaged power spectral density estimate.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:periodogram"
```

### welch

Averaged power spectral density estimate using welch's method. Lower variance than `periodogram` at the cost of frequency resolution.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:welch"
```

### spectrogram

Short-time Fourier transform power spectral density: time-frequency representation.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:spectrogram"
```

---

## ResultGet

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:resultget"
```

---

## Complete examples

### Low-pass filter a signal

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:low_pass_filter_a_signal"
```

### Inspect frequency response

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:inspect_frequency_response"
```

### Power spectral density with welch's method

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:power_spectral_density_with_welch_s_method"
```

### convolve two signals

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:convolve_two_signals"
```

---

## Notes

- **SOS preferred for high-order filters**: `sos_filter` and `sos_forward_backward_filter` are numerically more stable than their `b`/`a` equivalents. Use `OUTPUT='sos'` in filter design and the `SOS*` filtering predicates.
- **forward_backward_filter cannot be used causally**: it processes the entire signal and cannot be applied sample-by-sample. Use `linear_filter` or `sos_filter` for streaming / real-time use.
- **ZI for stateful filtering**: pass initial conditions `ZI` to `linear_filter` or `sos_filter` to get `{y, zf}` back; feed `zf` into the next call to process signals in chunks without boundary artefacts.
- **FS parameter**: when `FS` is omitted from [filter design](#filter-design-tier-2) predicates, cutoff frequencies `WN` must be normalised to the range `[0, 1]` (where `1` is the Nyquist frequency). when `FS` is provided, `WN` is in Hz.
- **Predicates fail** (no solution) when scipy raises an exception (e.g. invalid filter parameters), or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.fft](scipy_fft.md) — frequency-domain analysis.*
