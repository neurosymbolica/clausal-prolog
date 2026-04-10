# Phase 8 — Additional Shape Operations

Shape operations not covered in Phase 1: splitting, chunking, expanding,
repeating, narrowing.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to modify:** `clausal/modules/py/torch.py`

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `split` | `/3, /4` | `(+T, +size, -list)`, `(+T, +size, +dim, -list)` | yes — `cat` | Split into chunks of given size |
| `chunk` | `/3, /4` | `(+T, +n, -list)`, `(+T, +n, +dim, -list)` | yes — `cat` | Split into n chunks |
| `narrow` | `/5` | `(+T, +dim, +start, +length, -R)` | no | Narrow along dimension |
| `expand` | `/3` | `(+T, +sizes, -R)` | no (lossy) | Broadcast to larger size |
| `repeat` | `/3` | `(+T, +repeats, -R)` | no (lossy) | Tile tensor |
| `tile` | `/3` | `(+T, +reps, -R)` | no (lossy) | Tile (numpy-style) |
| `flip` | `/3` | `(+T, +dims, -R)` | self-inverse | Reverse along dims |
| `roll` | `/3, /4` | `(+T, +shifts, -R)`, `(+T, +shifts, +dims, -R)` | inverse with `-shifts` | Circular shift |
| `unbind` | `/3` | `(+T, +dim, -list)` | yes — `stack` | Remove dim, return list |

### Bijective relationships

- `split`/`chunk` are inverses of `cat` (Phase 1)
- `unbind` is the inverse of `stack` (Phase 1)
- `flip` is self-inverse: `flip(flip(T, dims), dims) == T`
- `roll` by `n` is inverted by `roll` by `-n`

---

## Context and Reference Patterns

All Tier 1 (pure). `split`, `chunk`, and `unbind` return lists of tensors
— the `_pure()` helper should convert the PyTorch tuple to a Python list
for Clausal compatibility:

```python
split = _pred("split",
    (3, _pure(lambda t, size: list(_th().split(t, int(size))))),
    (4, _pure(lambda t, size, dim: list(_th().split(t, int(size), dim=int(dim))))),
)
```

`_deep_deref()` needed for `dims`, `sizes`, `repeats` list arguments.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, zeros, split, chunk, unbind, flip,
                         roll, cat, stack, shape, tensor_list])

# split and cat are inverses
Test("split then cat") <- (
    tensor([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], T),
    split(T, 2, PARTS),
    length(PARTS, 3),
    cat(PARTS, 0, T2),
    tensor_list(T2, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
)

# unbind and stack are inverses
Test("unbind then stack") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], T),
    unbind(T, 0, ROWS),
    length(ROWS, 2),
    stack(ROWS, 0, T2),
    equal(T, T2)
)

# flip is self-inverse
Test("flip roundtrip") <- (
    tensor([1.0, 2.0, 3.0], T),
    flip(T, [0], F),
    flip(F, [0], T2),
    tensor_list(T2, [1.0, 2.0, 3.0])
)

# roll and negative roll are inverses
Test("roll roundtrip") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    roll(T, 2, R),
    roll(R, -2, T2),
    tensor_list(T2, [1.0, 2.0, 3.0, 4.0])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_shape2_tests.clausal`):
- `split`/`cat` roundtrip, `chunk`/`cat` roundtrip, `unbind`/`stack` roundtrip
- `flip` self-inverse, `roll` inverse
- `narrow` with shape verification
- `expand`/`repeat`/`tile` with shape verification
- Edge cases: split with uneven sizes, chunk with non-divisible n

---

## Docs

Update `docs/torch.md` with additional shape operations section.

---

## Issues

No issues encountered. All predicates follow the existing `_pure()` +
`_pred()` pattern. `split`, `chunk`, and `unbind` return PyTorch tuples —
converted to lists via `list()` for Clausal compatibility, as anticipated
in the plan.
