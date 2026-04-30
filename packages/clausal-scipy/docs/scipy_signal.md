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
| **Tier 2** | include design, FrequencyResponse, Periodogram, Welch, Spectrogram | dict — use `ResultGet` |
| **Tier 1** | LinearFilter, SOSFilter, ForwardBackwardFilter, SOSForwardBackwardFilter, Decimate, Resample, Convolve, Correlate, FFTConvolve | array (or dict when `ZI` supplied) |

---

## Naming conventions

| scipy function | Clausal predicate |
|---|---|
| `butter` | `Butterworth` |
| `bessel` | `Bessel` |
| `cheby1` | `ChebyshevType1` |
| `cheby2` | `ChebyshevType2` |
| `ellip` | `Elliptic` |
| `freqz` | `FrequencyResponse` |
| `lfilter` | `LinearFilter` |
| `sosfilt` | `SOSFilter` |
| `filtfilt` | `ForwardBackwardFilter` |
| `sosfiltfilt` | `SOSForwardBackwardFilter` |
| `decimate` | `Decimate` |
| `resample` | `Resample` |
| `convolve` | `Convolve` |
| `correlate` | `Correlate` |
| `fftconvolve` | `FFTConvolve` |
| `periodogram` | `Periodogram` |
| `welch` | `Welch` |
| `spectrogram` | `Spectrogram` |

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

### Butterworth

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:butterworth"
```

### Bessel

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:bessel"
```

### ChebyshevType1

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:chebyshevtype1"
```

### ChebyshevType2

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:chebyshevtype2"
```

### Elliptic

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:elliptic"
```

### FrequencyResponse

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:frequencyresponse"
```

---

## Filtering (Tier 1)

### LinearFilter

Causal IIR filter using direct-form II transposed implementation.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:linearfilter"
```

### SOSFilter

Numerically more stable than `LinearFilter` for higher-order filters. Use when `OUTPUT='sos'` in filter design.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:sosfilter"
```

### ForwardBackwardFilter

Zero-phase filtering: applies the filter twice (forward then backward), eliminating phase distortion. Signal length must be longer than the filter's padding requirements.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:forwardbackwardfilter"
```

### SOSForwardBackwardFilter

SOS form of `ForwardBackwardFilter`. Preferred for high-order filters.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:sosforwardbackwardfilter"
```

### Decimate

Low-pass filter then downsample by integer factor `Q`.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:decimate"
```

### Resample

Resample to exactly `NUM` samples using Fourier method. Suitable for arbitrary rational resampling ratios.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:resample"
```

---

## Convolution and correlation (Tier 1)

### Convolve

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:convolve"
```

### Correlate

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:correlate"
```

### FFTConvolve

Convolution via FFT — efficient for large arrays or long filters.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:fftconvolve"
```

---

## Spectral analysis (Tier 2)

### Periodogram

Non-averaged power spectral density estimate.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:periodogram"
```

### Welch

Averaged power spectral density estimate using Welch's method. Lower variance than `Periodogram` at the cost of frequency resolution.

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:welch"
```

### Spectrogram

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

### Power spectral density with Welch's method

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:power_spectral_density_with_welch_s_method"
```

### Convolve two signals

```clausal
--8<-- "tests/fixtures/docs/scipy_signal_sigs.txt:convolve_two_signals"
```

---

## Notes

- **SOS preferred for high-order filters**: `SOSFilter` and `SOSForwardBackwardFilter` are numerically more stable than their `b`/`a` equivalents. Use `OUTPUT='sos'` in filter design and the `SOS*` filtering predicates.
- **ForwardBackwardFilter cannot be used causally**: it processes the entire signal and cannot be applied sample-by-sample. Use `LinearFilter` or `SOSFilter` for streaming / real-time use.
- **ZI for stateful filtering**: pass initial conditions `ZI` to `LinearFilter` or `SOSFilter` to get `{y, zf}` back; feed `zf` into the next call to process signals in chunks without boundary artefacts.
- **FS parameter**: when `FS` is omitted from [filter design](#filter-design-tier-2) predicates, cutoff frequencies `WN` must be normalised to the range `[0, 1]` (where `1` is the Nyquist frequency). when `FS` is provided, `WN` is in Hz.
- **Predicates fail** (no solution) when scipy raises an exception (e.g. invalid filter parameters), or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.fft](scipy_fft.md) — frequency-domain analysis.*
