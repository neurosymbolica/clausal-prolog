# scipy.signal — Signal Processing

The `scipy_signal` module wraps [`scipy.signal`](https://docs.scipy.org/doc/scipy/reference/signal.html) as Clausal predicates. It covers IIR filter design, causal and zero-phase filtering, convolution, correlation, and spectral analysis.

---

## Import

```clausal
# skip
-import_from(scipy_signal, [Butterworth, SOSForwardBackwardFilter, ResultGet, ...])
```

Or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_signal, [Butterworth, SOSForwardBackwardFilter, ResultGet, ...])
```

---

## Tiers

| Tier | Predicates | RESULT type |
|---|---|---|
| **Tier 2** | Filter design, FrequencyResponse, Periodogram, Welch, Spectrogram | dict — use `ResultGet` |
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

## Filter design (Tier 2)

Filter design predicates return a result dict keyed by the `OUTPUT` format:

| OUTPUT | Dict keys |
|---|---|
| `'ba'` (default) | `b`, `a` |
| `'zpk'` | `z`, `p`, `k` |
| `'sos'` | `sos` |

Use `ResultGet` to extract fields:

```clausal
# skip
Butterworth(4, 0.1, 'low', 'sos', FILTER_DESIGN),
ResultGet(FILTER_DESIGN, 'sos', SOS).
```

### Butterworth

```clausal
# skip
Butterworth(N, WN, RESULT)
Butterworth(N, WN, BTYPE, RESULT)
Butterworth(N, WN, BTYPE, OUTPUT, RESULT)
Butterworth(N, WN, BTYPE, OUTPUT, FS, RESULT)
    N:      filter order
    WN:     cutoff frequency — normalised [0,1] or Hz when FS provided
    BTYPE:  'low' (default), 'high', 'band', 'bandstop'
    OUTPUT: 'ba' (default), 'zpk', 'sos'
    FS:     sample rate in Hz; if omitted WN must be in [0,1]
```

### Bessel

```clausal
# skip
Bessel(N, WN, RESULT)
Bessel(N, WN, BTYPE, RESULT)
Bessel(N, WN, BTYPE, OUTPUT, RESULT)
    Maximally flat group delay (linear phase) filter.
```

### ChebyshevType1

```clausal
# skip
ChebyshevType1(N, RP, WN, RESULT)
ChebyshevType1(N, RP, WN, BTYPE, RESULT)
ChebyshevType1(N, RP, WN, BTYPE, OUTPUT, RESULT)
    RP: maximum passband ripple in dB (e.g. 5)
```

### ChebyshevType2

```clausal
# skip
ChebyshevType2(N, RS, WN, RESULT)
ChebyshevType2(N, RS, WN, BTYPE, RESULT)
ChebyshevType2(N, RS, WN, BTYPE, OUTPUT, RESULT)
    RS: minimum stopband attenuation in dB (e.g. 40)
```

### Elliptic

```clausal
# skip
Elliptic(N, RP, RS, WN, RESULT)
Elliptic(N, RP, RS, WN, BTYPE, RESULT)
Elliptic(N, RP, RS, WN, BTYPE, OUTPUT, RESULT)
    RP: maximum passband ripple in dB
    RS: minimum stopband attenuation in dB
    Sharpest roll-off for a given order; equiripple in both bands.
```

### FrequencyResponse

```clausal
# skip
FrequencyResponse(B, A, RESULT)
FrequencyResponse(B, A, NFREQS, RESULT)
    B, A:   filter coefficients (from 'ba' output)
    NFREQS: number of frequency points (default 512)
    RESULT: dict {w, h}
        w — angular frequencies (radians/sample) in [0, π]
        h — complex frequency response
```

---

## Filtering (Tier 1)

### LinearFilter

Causal IIR filter using direct-form II transposed implementation.

```clausal
# skip
LinearFilter(B, A, X, RESULT)
LinearFilter(B, A, X, AXIS, RESULT)
LinearFilter(B, A, X, AXIS, ZI, RESULT)
    B, A:   numerator / denominator coefficients
    X:      input signal array
    AXIS:   axis along which to filter (default -1)
    ZI:     initial conditions; when provided RESULT is dict {y, zf}
            where zf carries the final filter delay values
```

### SOSFilter

Numerically more stable than `LinearFilter` for higher-order filters. Use when `OUTPUT='sos'` in filter design.

```clausal
# skip
SOSFilter(SOS, X, RESULT)
SOSFilter(SOS, X, AXIS, RESULT)
SOSFilter(SOS, X, AXIS, ZI, RESULT)
    SOS: second-order sections matrix (from 'sos' output)
    ZI:  initial conditions; when provided RESULT is dict {y, zf}
```

### ForwardBackwardFilter

Zero-phase filtering: applies the filter twice (forward then backward), eliminating phase distortion. Signal length must be longer than the filter's padding requirements.

```clausal
# skip
ForwardBackwardFilter(B, A, X, RESULT)
ForwardBackwardFilter(B, A, X, AXIS, RESULT)
    Produces zero-phase output at the cost of twice the computation.
    Cannot be used for real-time (causal) filtering.
```

### SOSForwardBackwardFilter

SOS form of `ForwardBackwardFilter`. Preferred for high-order filters.

```clausal
# skip
SOSForwardBackwardFilter(SOS, X, RESULT)
SOSForwardBackwardFilter(SOS, X, AXIS, RESULT)
```

### Decimate

Low-pass filter then downsample by integer factor `Q`.

```clausal
# skip
Decimate(X, Q, RESULT)
Decimate(X, Q, AXIS, RESULT)
    Q: integer decimation factor
```

### Resample

Resample to exactly `NUM` samples using Fourier method. Suitable for arbitrary rational resampling ratios.

```clausal
# skip
Resample(X, NUM, RESULT)
Resample(X, NUM, AXIS, RESULT)
    NUM: desired number of output samples
```

---

## Convolution and correlation (Tier 1)

### Convolve

```clausal
# skip
Convolve(IN1, IN2, RESULT)
Convolve(IN1, IN2, MODE, RESULT)
Convolve(IN1, IN2, MODE, METHOD, RESULT)
    MODE:   'full' (default), 'valid', 'same'
    METHOD: 'auto' (default), 'direct', 'fft'
```

### Correlate

```clausal
# skip
Correlate(IN1, IN2, RESULT)
Correlate(IN1, IN2, MODE, RESULT)
Correlate(IN1, IN2, MODE, METHOD, RESULT)
    Cross-correlation of IN1 and IN2.
    Same MODE and METHOD options as Convolve.
```

### FFTConvolve

Convolution via FFT — efficient for large arrays or long filters.

```clausal
# skip
FFTConvolve(IN1, IN2, RESULT)
FFTConvolve(IN1, IN2, MODE, RESULT)
    Always uses the FFT method.
    MODE: 'full' (default), 'valid', 'same'
```

---

## Spectral analysis (Tier 2)

### Periodogram

Non-averaged power spectral density estimate.

```clausal
# skip
Periodogram(X, RESULT)
Periodogram(X, FS, RESULT)
    X:      input signal
    FS:     sample rate in Hz (default 1.0)
    RESULT: dict {f, Pxx}
        f   — frequency array in Hz
        Pxx — power spectral density
```

### Welch

Averaged power spectral density estimate using Welch's method. Lower variance than `Periodogram` at the cost of frequency resolution.

```clausal
# skip
Welch(X, RESULT)
Welch(X, FS, RESULT)
    RESULT: dict {f, Pxx}
```

### Spectrogram

Short-time Fourier transform power spectral density: time-frequency representation.

```clausal
# skip
Spectrogram(X, RESULT)
Spectrogram(X, FS, RESULT)
    RESULT: dict {f, t, Sxx}
        f   — frequency array in Hz
        t   — time array in seconds
        Sxx — 2-D power spectral density array (freqs × times)
```

---

## ResultGet

```clausal
# skip
ResultGet(RESULT, FIELD, VALUE)
    Extract RESULT[FIELD] → VALUE.
    RESULT must be a dict.  FIELD must be a ground string.
    Fails if FIELD is absent or RESULT is not a dict.
```

---

## Complete examples

### Low-pass filter a signal

```clausal
# skip
-import_from(scipy_signal, [Butterworth, SOSForwardBackwardFilter, ResultGet])

LowPassFilter(SIGNAL, CUTOFF_HZ, SAMPLE_RATE, FILTERED) <- (
    Butterworth(6, CUTOFF_HZ, 'low', 'sos', SAMPLE_RATE, DESIGN),
    ResultGet(DESIGN, 'sos', SOS),
    SOSForwardBackwardFilter(SOS, SIGNAL, FILTERED)
).
```

### Inspect frequency response

```clausal
# skip
-import_from(scipy_signal, [Butterworth, FrequencyResponse, ResultGet])

FilterResponse(N, WN, W, H) <- (
    Butterworth(N, WN, DESIGN),
    ResultGet(DESIGN, 'b', B),
    ResultGet(DESIGN, 'a', A),
    FrequencyResponse(B, A, 512, RESP),
    ResultGet(RESP, 'w', W),
    ResultGet(RESP, 'h', H)
).
```

### Power spectral density with Welch's method

```clausal
# skip
-import_from(scipy_signal, [Welch, ResultGet])

SignalPSD(SIGNAL, SAMPLE_RATE, FREQS, POWER) <- (
    Welch(SIGNAL, SAMPLE_RATE, PSD),
    ResultGet(PSD, 'f', FREQS),
    ResultGet(PSD, 'Pxx', POWER)
).
```

### Convolve two signals

```clausal
# skip
-import_from(scipy_signal, [FFTConvolve])

SmoothedSignal(SIGNAL, KERNEL, SMOOTHED) <- (
    FFTConvolve(SIGNAL, KERNEL, 'same', SMOOTHED)
).
```

---

## Notes

- **SOS preferred for high-order filters**: `SOSFilter` and `SOSForwardBackwardFilter` are numerically more stable than their `b`/`a` equivalents. Use `OUTPUT='sos'` in filter design and the `SOS*` filtering predicates.
- **ForwardBackwardFilter cannot be used causally**: it processes the entire signal and cannot be applied sample-by-sample. Use `LinearFilter` or `SOSFilter` for streaming / real-time use.
- **ZI for stateful filtering**: pass initial conditions `ZI` to `LinearFilter` or `SOSFilter` to get `{y, zf}` back; feed `zf` into the next call to process signals in chunks without boundary artefacts.
- **FS parameter**: when `FS` is omitted from filter design predicates, cutoff frequencies `WN` must be normalised to the range `[0, 1]` (where `1` is the Nyquist frequency). When `FS` is provided, `WN` is in Hz.
- **Predicates fail** (no solution) when scipy raises an exception (e.g. invalid filter parameters), or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.fft](scipy_fft.md) — frequency-domain analysis.*
