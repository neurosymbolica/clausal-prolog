# Phase 5 — FFT

Pure FFT operations via `jax.numpy.fft`. Every FFT pair is bijective —
`fft` / `ifft` compose as inverses. Exposed as single multi-mode
predicates following the PyTorch Phase 5 precedent.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1 — `_pure()`, `_pred()`, `_bidir_2()`,
`_bidir_3_mid()`, `_jnp_mod()`.

---

## Predicates

### Bijective pairs (single multi-mode predicate each)

| Name | Arity | Modes | Collapses | Description |
|---|---|---|---|---|
| `fft_transform` | `/2, /3` | `(+T, -F)`, `(-T, +F)`; with axis `(+T, +AXIS, -F)`, `(-T, +AXIS, +F)` | `jnp.fft.fft` / `jnp.fft.ifft` | Complex FFT |
| `real_fft` | `/2, /3` | same | `jnp.fft.rfft` / `jnp.fft.irfft` | Real-input FFT |
| `fft_transform_2d` | `/2` | `(+T, -F)`, `(-T, +F)` | `jnp.fft.fft2` / `jnp.fft.ifft2` | 2-D FFT |
| `fft_transform_nd` | `/2` | `(+T, -F)`, `(-T, +F)` | `jnp.fft.fftn` / `jnp.fft.ifftn` | N-D FFT |
| `fft_shift` | `/2` | `(+T, -S)`, `(-T, +S)` | `jnp.fft.fftshift` / `jnp.fft.ifftshift` | Shift zero-frequency to centre |

### Non-bijective

| Name | Arity | Modes | Description |
|---|---|---|---|
| `fft_frequencies` | `/2, /3` | `(+N, -F)`, `(+N, +D, -F)` | `jnp.fft.fftfreq` |
| `real_fft_frequencies` | `/2, /3` | | `jnp.fft.rfftfreq` |

---

## Context and Reference Patterns

### Bijective pairs use `_bidir_2`

Exactly the same helper Phase 1 introduced. The forward computes an
FFT; the backward computes the inverse:

```python
def _jfft():
    return _jnp_mod().fft

fft_transform = _pred("fft_transform",
    (2, _bidir_2(
        forward=lambda t: _jfft().fft(t),
        backward=lambda f: _jfft().ifft(f),
    )),
    (3, _bidir_3_mid(
        forward=lambda t, axis: _jfft().fft(t, axis=int(axis)),
        backward=lambda f, axis: _jfft().ifft(f, axis=int(axis)),
    )),
)

real_fft = _pred("real_fft",
    (2, _bidir_2(
        forward=lambda t: _jfft().rfft(t),
        backward=lambda f: _jfft().irfft(f),
    )),
    # 3-ary: axis mediator
)
```

### `real_fft` round-trip needs original length

`rfft` of a length-N real signal produces `N // 2 + 1` complex values.
`irfft` needs to know N to reconstruct uniquely — without it, `irfft`
assumes `N = 2 * (K - 1)`. This is lossy for odd N. Document; tests use
even N for strict bijection.

### `fft_shift` is its own inverse for even N

For even N, `fftshift == ifftshift`. For odd N they differ by one
element. The `_bidir_2` helper handles both directions.

### Frequency helpers are not bijective

`fftfreq(N)` returns the frequency for each index. One-way only:

```python
fft_frequencies = _pred("fft_frequencies",
    (2, _pure(lambda n: _jfft().fftfreq(int(n)))),
    (3, _pure(lambda n, d: _jfft().fftfreq(int(n), d=d))),
)
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, zeros, shape, array_list, allclose,
                      fft_transform, real_fft, fft_shift,
                      fft_transform_2d,
                      fft_frequencies, real_fft_frequencies])

Test("fft_transform forward") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    fft_transform(T, F),
    shape(F, [4])
)

Test("fft_transform roundtrip") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    fft_transform(T, F),
    fft_transform(T2, F),
    # T2 should be close to T
    allclose(T, T2)
)

Test("real_fft roundtrip (even length)") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    real_fft(T, F),
    real_fft(T2, F),
    allclose(T, T2)
)

Test("fft_shift is self-inverse for even") <- (
    array([1.0, 2.0, 3.0, 4.0], T),
    fft_shift(T, S),
    fft_shift(T2, S),
    allclose(T, T2)
)

Test("fft_transform_2d on matrix") <- (
    zeros([4, 4], T),
    fft_transform_2d(T, F),
    shape(F, [4, 4])
)

Test("fft_frequencies") <- (
    fft_frequencies(4, F),
    array_list(F, [0.0, 0.25, -0.5, -0.25])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_fft_tests.clausal`):
- Every bijective predicate: forward, reverse, roundtrip
- `real_fft` with even-length input (strict roundtrip)
- `fft_transform` with axis argument
- `fft_shift` self-inverse for even N
- `fft_frequencies` values

**Python unit tests:** None beyond the `.clausal` tests.

---

## Docs

Update `docs/jax.md` with an FFT section. Highlight bijective pairs
collapsed into single predicates. All examples backed by `.clausal`
tests.

---

## Issues

Implementation completed — 27 integration tests green (17 initial + 10
backfill). Notes from the pass:

- **`_bidir_2` and `_bidir_3_mid` reused.** Every FFT / inverse-FFT
  pair maps directly onto the Phase 1 helpers. `fft_transform_2d`,
  `fft_transform_nd`, and `fft_shift` each gained an `/3` variant that
  forwards an `axes` list via `_bidir_3_mid`.
- **Round-trip through `fft_transform` returns complex.** `fft` of a
  real array produces `complex64`; `ifft` keeps the complex dtype.
  Recovery has tiny imaginary noise (~1e-7), so round-trip tests
  compare via `.real` in a `++()` escape rather than exact equality.
  `real_fft` is different — `irfft` returns real, matching the input
  dtype.
- **The plan example used `allclose`,** which belongs to Phase 6 and
  isn't yet available. The fixture substitutes explicit range checks
  on individual elements extracted via `at_get` — the same pattern as
  Phase 4 linalg.
- **Odd-N `real_fft` is lossy** — `irfft` defaults to `N = 2 * (K - 1)`,
  which drops the trailing sample for odd input. Documented in
  `docs/jax.md` and pinned by `real_fft roundtrip for odd N is lossy`.
- **Float32 kills exact equality for `fft_frequencies` at odd N.**
  0.2 can't be represented exactly, so the odd-N fixture uses range
  checks on extracted elements instead of `array_list` equality.

- **`_bidir_2` / `_bidir_3_mid` check mode was broken for array types.**
  Both helpers used to call `unify(y_raw, forward(x), trail)` in check
  mode. `unify` falls back to Python `==`, which on JAX / numpy /
  multi-element torch arrays returns an element-wise bool array —
  `bool(...)` on that raises `ValueError`, which the helpers silently
  swallowed via `except Exception: pass`. The net effect: any
  `(+X, +Y)` call on a predicate built from these helpers always
  failed, even when `Y` genuinely equalled `forward(X)`.

  Fix: added `_values_equal` to `_helpers.py` (array-aware equality:
  identity check → `==` if scalar bool → `.all()` reduction). The
  helpers now try `unify` first (so structured Y with embedded Vars,
  like `tensor_list(X, [V1, V2])`, still partially-unifies), and fall
  back to `_values_equal` if `unify` raises. Trail is unwound via
  `trail.mark()` / `trail.undo()` around the attempted unify so the
  fallback runs on a clean trail.

  Non-regressing across the full 559-test suite. Pinned by
  `fft_shift check mode succeeds on equal JAX arrays` and
  `fft_shift check mode fails on unequal JAX arrays`.

Known items to validate:

1. **`real_fft` round-trip for odd N.** Lossy — `irfft` assumes even N.
   Tests use even N; docs note the caveat.

2. **Complex dtype.** `fft_transform` on real input returns
   `complex64`; on `float64` input returns `complex128`. Shape checks
   work; dtype checks must match the input precision.

3. **Axis argument defaults.** `jnp.fft.fft` defaults to the last axis
   (`-1`). Our 2-ary variant matches this. The 3-ary variant passes
   the axis explicitly.

4. **FFT of a JIT-traced array.** FFT composes with `jit`. If this
   phase ever integrates with Phase 12 transforms, verify trace
   compatibility.
