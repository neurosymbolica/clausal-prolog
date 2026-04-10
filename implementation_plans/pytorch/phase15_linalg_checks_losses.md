# Phase 15 — Linalg Extras, Checks, Pad, and Losses

Remaining gaps: linalg matrix operations, numeric check predicates,
tensor padding, and additional loss functions.

**Depends on:** Phase 1, Phase 4 (linalg), Phase 6 (check predicates),
Phase 11 (loss functions). Uses `_pure`, `_pred`, `_check_1` from
`_helpers.py`.

**Files to modify:**
- `clausal/modules/py/torch.py` — linalg extras, checks
- `clausal/modules/py/torch_functional.py` — pad, loss functions

---

## Predicates

### Linalg extras (in `py.torch`)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `triu` | `/2, /3` | `(+T, -R)`, `(+T, +diagonal, -R)` | Upper triangular |
| `tril` | `/2, /3` | `(+T, -R)`, `(+T, +diagonal, -R)` | Lower triangular |
| `trace` | `/2` | `(+T, -R)` | Sum of diagonal elements |

`triu`/`tril` with `diagonal=0` (default) give the standard upper/lower
triangle. With `diagonal=k`, shift the boundary up/down.

Note: `diag` is in Phase 13 (creation/extraction). `trace` is a pure
reduction (sum of diagonal), not a matrix operation in the linalg sense.

### Numeric checks (in `py.torch`)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `isnan` | `/2` | `(+T, -R)` | Element-wise NaN check (bool tensor) |
| `isinf` | `/2` | `(+T, -R)` | Element-wise infinity check (bool tensor) |
| `isfinite` | `/2` | `(+T, -R)` | Element-wise finiteness check (bool tensor) |
| `has_nan` | `/1` | `(+T)` | Check predicate: fails if no NaNs |
| `has_inf` | `/1` | `(+T)` | Check predicate: fails if no infinities |
| `all_finite` | `/1` | `(+T)` | Check predicate: fails if any non-finite |

The `/2` variants return bool tensors (like `eq`, `gt` from Phase 6).
The `/1` check predicates are convenience wrappers using `_check_1`
pattern from Phase 6 — succeed or fail with no output.

### Padding (in `py.torch_functional`)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `pad` | `/3, /4` | `(+T, +padding, -R)`, `(+T, +padding, +opts, -R)` | Pad tensor |

`padding` is a list of ints (pairs per dimension, inner to outer).
`opts` dict for `mode` (`"constant"`, `"reflect"`, `"replicate"`,
`"circular"`) and `value` (for constant mode).

### Additional loss functions (in `py.torch_functional`)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `smooth_l1_loss` | `/3, /4` | `(+input, +target, -loss)`, with opts | Smooth L1 / Huber-like |
| `huber_loss` | `/3, /4` | `(+input, +target, -loss)`, with opts | Huber loss |
| `kl_div` | `/3, /4` | `(+input, +target, -loss)`, with opts | KL divergence |

---

## Context and Reference Patterns

All Tier 1 (pure). Same patterns as established phases.

`triu`/`tril` with optional diagonal offset:

```python
triu = _pred("triu",
    (2, _pure(lambda t: _th().triu(t))),
    (3, _pure(lambda t, diag: _th().triu(t, diagonal=int(diag)))),
)
```

Check predicates follow Phase 6's `_check_1` / `_check_bool`:

```python
all_finite = _pred("all_finite",
    (1, _check_bool(lambda t: _th().isfinite(t).all().item())),
)
```

`pad` follows the opts-dict pattern from Phase 1/11:

```python
pad = _pred("pad",
    (3, _pure(lambda t, p: _th().nn.functional.pad(t, p))),
    (4, _pure(lambda t, p, opts: _th().nn.functional.pad(t, p, **opts))),
)
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, triu, tril, trace, isnan, isinf,
                         isfinite, all_finite, has_nan, tensor_list, shape])
-import_from(py.torch_functional, [pad, smooth_l1_loss, huber_loss])

# Upper/lower triangular
Test("triu") <- (
    tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], M),
    triu(M, U),
    tensor_list(U, [[1.0, 2.0, 3.0], [0.0, 5.0, 6.0], [0.0, 0.0, 9.0]])
)

Test("tril") <- (
    tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], M),
    tril(M, L),
    tensor_list(L, [[1.0, 0.0, 0.0], [4.0, 5.0, 0.0], [7.0, 8.0, 9.0]])
)

Test("trace") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], M),
    trace(M, T),
    tensor_list(T, 5.0)
)

# Numeric checks
Test("isnan element-wise") <- (
    T is ++(torch.tensor([1.0, float('nan'), 3.0])),
    isnan(T, R),
    tensor_list(R, [False, True, False])
)

Test("all_finite succeeds") <- (
    tensor([1.0, 2.0, 3.0], T),
    all_finite(T)
)

Test("all_finite fails on nan") <- (
    T is ++(torch.tensor([1.0, float('nan')])),
    not(all_finite(T))
)

# Padding
Test("pad 1D") <- (
    tensor([1.0, 2.0, 3.0], T),
    pad(T, [1, 1], R),
    shape(R, [5])
)

# Losses
Test("smooth_l1_loss") <- (
    tensor([1.0, 2.0, 3.0], PRED),
    tensor([1.0, 2.0, 3.0], TARGET),
    smooth_l1_loss(PRED, TARGET, LOSS),
    tensor_list(LOSS, 0.0)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_extras_tests.clausal`):
- `triu`/`tril` with default and shifted diagonal
- `trace` with known matrices
- `isnan`/`isinf`/`isfinite` element-wise with constructed NaN/Inf values
- Check predicates: `all_finite`, `has_nan`, `has_inf` (success and failure)
- `pad` with various padding sizes and modes
- `smooth_l1_loss`, `huber_loss`, `kl_div` with known inputs

---

## Docs

Update `docs/torch.md` with linalg extras, numeric checks.
Update `docs/torch_functional.md` with pad and additional losses.

---

## Issues

_To be populated during implementation._
