# Phase 8 — Shape Extras

Additional shape operations beyond Phase 1: split, tile, flip, roll,
repeat, broadcast. Mirrors PyTorch Phase 8.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1.

---

## Predicates

| Name | Arity | Modes | Description |
|---|---|---|---|
| `split` | `/3, /4` | `(+A, +N_OR_INDICES, -LIST)`, `(+A, +N_OR_INDICES, +AXIS, -LIST)` | `jnp.split` |
| `array_split` | `/3, /4` | | `jnp.array_split` (uneven OK) |
| `hsplit` | `/3` | `(+A, +N, -LIST)` | |
| `vsplit` | `/3` | | |
| `dsplit` | `/3` | | |
| `tile` | `/3` | `(+A, +REPS, -R)` | |
| `repeat` | `/4` | `(+A, +REPS, +AXIS, -R)` | |
| `flip` | `/3` | `(+A, +AXIS, -R)` | |
| `roll` | `/3, /4` | `(+A, +SHIFTS, -R)`, `(+A, +SHIFTS, +AXIS, -R)` | |
| `unstack` | `/3` | `(+A, +AXIS, -LIST)` | |
| `pad` | `/4, /5` | `(+A, +PAD_WIDTH, -R)`, `(+A, +PAD_WIDTH, +MODE, -R)` | |

---

## Context

All `_pure()`:

```python
split = _pred("split",
    (3, _pure(lambda a, n: list(_jnp_mod().split(a, n)))),
    (4, _pure(lambda a, n, axis: list(_jnp_mod().split(a, n, axis=int(axis))))),
)
```

Note `list(...)` — `jnp.split` returns a tuple of arrays; we want a
list for Clausal `findall`/pattern-match.

Bijective pairs like `split` + `concatenate` are not combined into a
single predicate because the split criteria (N or indices) aren't
inferable from the concatenated result.

---

## Example Usage

```clausal
-import_from(py.jax, [array, arange, shape, array_list,
                      split, tile, flip, roll, repeat, unstack,
                      concatenate])

Test("split into 3") <- (
    arange(0, 6, A),
    split(A, 3, LS),
    length(LS, 3)
)

Test("split + concat roundtrip") <- (
    arange(0, 6, A),
    split(A, 3, LS),
    concatenate(LS, 0, A2),
    array_list(A, L),
    array_list(A2, L)
)

Test("tile") <- (
    array([1, 2], A),
    tile(A, [3], R),
    array_list(R, [1, 2, 1, 2, 1, 2])
)

Test("flip along axis") <- (
    array([[1, 2], [3, 4]], A),
    flip(A, 0, R),
    array_list(R, [[3, 4], [1, 2]])
)

Test("roll by 1") <- (
    array([1, 2, 3, 4], A),
    roll(A, 1, R),
    array_list(R, [4, 1, 2, 3])
)

Test("unstack") <- (
    array([[1, 2], [3, 4], [5, 6]], A),
    unstack(A, 0, LS),
    length(LS, 3)
)
```

---

## Tests

`tests/fixtures/jax_shape_extras_tests.clausal`:
- Every predicate with shape check
- `split` + `concatenate` roundtrip
- Edge cases: split into 1, tile by 1

---

## Docs

Update `docs/jax.md` shape section.

---

## Issues

_To be populated during implementation._

1. `split` return type: tuple vs list — we convert to list.
2. `pad` mode argument: `"constant"`, `"edge"`, `"reflect"`, etc.
   Passed as a string atom.
