# Phase 6 — Comparisons, Logic, and Selection

Element-wise comparison and logical operations, plus conditional selection.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to modify:** `clausal/modules/py/torch.py`

**Overlap with scipy:** No direct overlap — these are tensor-level
operations without scipy equivalents.

---

## Predicates

### Element-wise comparisons

| Name | Arity | Modes | Description |
|---|---|---|---|
| `eq` | `/3` | `(+A, +B, -C)` | Element-wise equality (bool tensor) |
| `ne` | `/3` | `(+A, +B, -C)` | Element-wise not-equal |
| `gt` | `/3` | `(+A, +B, -C)` | Element-wise greater-than |
| `lt` | `/3` | `(+A, +B, -C)` | Element-wise less-than |
| `ge` | `/3` | `(+A, +B, -C)` | Element-wise greater-or-equal |
| `le` | `/3` | `(+A, +B, -C)` | Element-wise less-or-equal |
| `equal` | `/2` | `(+A, +B)` | True if all elements equal (check predicate, no output) |
| `allclose` | `/2, /4` | `(+A, +B)`, `(+A, +B, +atol, +rtol)` | Approximate equality check |

### Logical operations

| Name | Arity | Modes | Description |
|---|---|---|---|
| `logical_and` | `/3` | `(+A, +B, -C)` | Element-wise AND |
| `logical_or` | `/3` | `(+A, +B, -C)` | Element-wise OR |
| `logical_not` | `/2` | `(+A, -B)` | Element-wise NOT |
| `logical_xor` | `/3` | `(+A, +B, -C)` | Element-wise XOR |
| `any` | `/1, /2` | `(+T)` check, `(+T, +dim)` check | Any element true |
| `all` | `/1, /2` | `(+T)` check, `(+T, +dim)` check | All elements true |

### Selection

| Name | Arity | Modes | Description |
|---|---|---|---|
| `where` | `/4` | `(+condition, +X, +Y, -result)` | Select from X or Y based on condition |
| `masked_select` | `/3` | `(+T, +mask, -selected)` | Elements where mask is true |
| `index_select` | `/4` | `(+T, +dim, +indices, -selected)` | Select along dimension |
| `gather` | `/4` | `(+T, +dim, +indices, -gathered)` | Gather along dimension |
| `scatter` | `/5` | `(+T, +dim, +indices, +src, -result)` | Scatter src into T |

---

## Context and Reference Patterns

All Tier 1 (pure). `equal/2` and `allclose/2` are check predicates
(succeed or fail, no output variable) — follow the `_check_1()` pattern
from Phase 1's `is_contiguous/1`.

For `any/1` and `all/1`, also check predicates:

```python
def _check_bool(fn):
    """Check predicate: succeed if fn(tensor) is truthy."""
    def dispatch(this_generator, parent, tensor_var, trail):
        t = _deep_deref(deref(tensor_var))
        try:
            if fn(t):
                yield (parent, None)
        except Exception:
            pass
        yield (parent, DONE)
    return dispatch
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, eq, gt, where, equal, allclose,
                         logical_and, any, all, masked_select,
                         tensor_list])

Test("element-wise gt") <- (
    tensor([1.0, 5.0, 3.0], A),
    tensor([2.0, 2.0, 2.0], B),
    gt(A, B, MASK),
    tensor_list(MASK, [false, true, true])
)

Test("where selects conditionally") <- (
    tensor([1.0, 2.0, 3.0], X),
    tensor([10.0, 20.0, 30.0], Y),
    tensor([true, false, true], COND),
    where(COND, X, Y, R),
    tensor_list(R, [1.0, 20.0, 3.0])
)

Test("equal check succeeds") <- (
    tensor([1.0, 2.0], A),
    tensor([1.0, 2.0], B),
    equal(A, B)
)

Test("equal check fails") <- (
    tensor([1.0, 2.0], A),
    tensor([1.0, 3.0], B),
    not(equal(A, B))
)

Test("masked_select") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    tensor([true, false, true, false], MASK),
    masked_select(T, MASK, R),
    tensor_list(R, [1.0, 3.0])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_comparison_tests.clausal`):
- All six comparison ops with expected bool tensor outputs
- `equal`/`allclose` as check predicates (success and failure with `not()`)
- Logical ops: and, or, not, xor
- `any`/`all` as check predicates
- `where` conditional selection
- `masked_select`, `index_select`, `gather`, `scatter`

---

## Docs

Update `docs/torch.md` with comparisons, logic, selection sections.

---

## Issues

- Plan examples used lowercase `true`/`false` for bool values in `.clausal`
  files. Clausal uses Python's `True`/`False`. All fixture tests updated.

- `any/2` and `all/2` (with dim) are check predicates that succeed if the
  condition holds across all slices. `torch.any(t, dim=d)` returns a tensor
  of per-slice results; we reduce with `.any().item()` / `.all().item()`
  to produce a single boolean for the check.

- Added three new helpers to `torch.py`: `_check_2` (binary check predicate),
  `_check_bool` (unary bool check), `_check_bool_dim` (bool check with dim).
