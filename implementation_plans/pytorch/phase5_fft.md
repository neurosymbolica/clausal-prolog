# Phase 5 — FFT

Fast Fourier Transform operations. All are strict bijective pairs
(transform/inverse transform).

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to modify:** `clausal/modules/py/torch.py`

**Overlap with scipy:** `scipy_fft.py` covers the same operations on
numpy arrays (`FFTransform`, `RealFFT`, etc.). The PyTorch versions
operate on tensors (GPU-accelerated). The naming here follows PyTorch's
API (`fft`, `ifft`, `rfft`, `irfft`), which matches the standard
domain terminology.

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `fft` | `/2, /3` | `(+T, -F)`, `(+T, +dim, -F)` | yes — `ifft` | Complex-to-complex FFT |
| `ifft` | `/2, /3` | `(+F, -T)`, `(+F, +dim, -T)` | yes — `fft` | Inverse FFT |
| `rfft` | `/2, /3` | `(+T, -F)`, `(+T, +dim, -F)` | yes — `irfft` | Real-to-complex FFT |
| `irfft` | `/2, /3` | `(+F, -T)`, `(+F, +dim, -T)` | yes — `rfft` | Complex-to-real inverse FFT |
| `fft2` | `/2` | `(+T, -F)` | yes — `ifft2` | 2D FFT |
| `ifft2` | `/2` | `(+F, -T)` | yes — `fft2` | 2D inverse FFT |
| `fftn` | `/2` | `(+T, -F)` | yes — `ifftn` | N-dimensional FFT |
| `ifftn` | `/2` | `(+F, -T)` | yes — `fftn` | N-dimensional inverse FFT |
| `fftfreq` | `/2, /3` | `(+n, -F)`, `(+n, +d, -F)` | no | Sample frequencies |
| `rfftfreq` | `/2, /3` | `(+n, -F)`, `(+n, +d, -F)` | no | Real FFT sample frequencies |
| `fftshift` | `/2` | `(+T, -S)` | yes — `ifftshift` | Shift zero-freq to centre |
| `ifftshift` | `/2` | `(+S, -T)` | yes — `fftshift` | Inverse shift |

`fft`/`ifft` are domain-standard abbreviations — acceptable per naming rules.

---

## Context and Reference Patterns

All Tier 1 (pure). Same `_pure()` + `_pred()` pattern as Phase 1.

All operations are in `torch.fft` submodule:

```python
fft = _pred("fft",
    (2, _pure(lambda t: _th().fft.fft(t))),
    (3, _pure(lambda t, dim: _th().fft.fft(t, dim=int(dim)))),
)
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, fft, ifft, rfft, irfft, fftshift,
                         ifftshift, fftfreq, shape, tensor_list])

# FFT/IFFT are inverses
Test("fft ifft roundtrip") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    fft(T, F),
    ifft(F, T2),
    # T2 should be close to T (complex, take real part)
    shape(T2, [4])
)

# Real FFT
Test("rfft shape") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    rfft(T, F),
    shape(F, [3])    # n//2 + 1 for real FFT
)

# fftshift/ifftshift are inverses
Test("fftshift roundtrip") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    fftshift(T, S),
    ifftshift(S, T2),
    tensor_list(T2, [1.0, 2.0, 3.0, 4.0])
)

# Frequency bins
Test("fftfreq") <- (
    fftfreq(4, F),
    shape(F, [4])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_fft_tests.clausal`):
- Every bijective pair roundtrip: fft/ifft, rfft/irfft, fft2/ifft2, fftshift/ifftshift
- Shape verification for rfft output (n//2 + 1)
- Dim argument variants
- fftfreq/rfftfreq shape checks

---

## Docs

Update `docs/torch.md` with FFT section. Note bijective pairs.

---

## Issues

_To be populated during implementation._
