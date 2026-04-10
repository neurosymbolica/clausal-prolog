# Phase 5 — FFT

Fast Fourier Transform operations. Transform/inverse pairs are single
bijective predicates using `_bidir_2` / `_bidir_3_mid`.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File modified:** `clausal/modules/py/torch.py`

**Overlap with scipy:** `scipy_fft.py` covers the same operations on
numpy arrays (`FFTransform`, `RealFFT`, etc.). The PyTorch versions
operate on tensors (GPU-accelerated). Same bijective-predicate pattern.

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `fft_transform` | `/2, /3` | `(+T,-F)`, `(-T,+F)`, `(+T,+dim,-F)` | yes | Complex FFT / inverse |
| `real_fft` | `/2, /3` | `(+T,-F)`, `(-T,+F)`, `(+T,+dim,-F)` | yes | Real-to-complex FFT / inverse |
| `fft_transform_2d` | `/2` | `(+T,-F)`, `(-T,+F)` | yes | 2D FFT / inverse |
| `fft_transform_nd` | `/2` | `(+T,-F)`, `(-T,+F)` | yes | N-dimensional FFT / inverse |
| `fft_shift` | `/2` | `(+T,-S)`, `(-T,+S)` | yes | Shift zero-freq to centre / back |
| `fft_frequencies` | `/2, /3` | `(+n,-F)`, `(+n,+d,-F)` | no | DFT sample frequencies |
| `real_fft_frequencies` | `/2, /3` | `(+n,-F)`, `(+n,+d,-F)` | no | Real FFT sample frequencies |

---

## Design Decision: Bijective Predicates

The original plan had separate `fft`/`ifft`, `rfft`/`irfft` etc. predicates.
These were collapsed into single bidirectional predicates (`fft_transform`,
`real_fft`, etc.) to match the relational pattern — the same predicate
expresses both directions of the relationship, like `tensor_numpy` and
`tensor_list` in Phase 1.

A new helper `_bidir_3_mid` was added for the arity-3 dim variants:
`(+X, +MID, -Y)` forward, `(-X, +MID, +Y)` backward.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, fft_transform, real_fft, fft_shift,
                         fft_frequencies, shape, tensor_list])

# FFT is bijective: same predicate for forward and inverse
Test("fft_transform roundtrip") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    fft_transform(T, F),
    fft_transform(T2, F),
    shape(T2, [4])
)

# Real FFT
Test("real_fft shape") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    real_fft(T, F),
    shape(F, [3])    # n//2 + 1 for real FFT
)

# fft_shift is bijective
Test("fft_shift roundtrip") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    fft_shift(T, S),
    fft_shift(T2, S),
    tensor_list(T2, [1.0, 2.0, 3.0, 4.0])
)

# Frequency bins
Test("fft_frequencies") <- (
    fft_frequencies(4, F),
    shape(F, [4])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_fft_tests.clausal`):
- Every bijective predicate roundtrip: fft_transform, real_fft, fft_transform_2d, fft_transform_nd, fft_shift
- Shape verification for real_fft output (n//2 + 1)
- Dim argument variants for fft_transform and real_fft
- fft_frequencies/real_fft_frequencies shape checks
- Value check for fft_shift output ordering

---

## Docs

Updated `docs/torch.md` with FFT section. Notes bijective design.

---

## Issues

- Added `_bidir_3_mid` helper to `torch.py` for arity-3 bidirectional
  predicates with a ground middle argument (used by dim variants).
