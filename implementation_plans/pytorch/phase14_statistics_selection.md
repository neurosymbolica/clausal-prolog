# Phase 14 — Statistics and Selection

Statistical reductions (`median`, `std`, `var`) and selection/sorting
operations (`argmin`, `argmax`, `sort`, `argsort`, `topk`, `nonzero`,
`unique`). Several of these have strong relational character — `nonzero`
and `unique` are natural nondeterministic enumeration candidates.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` and `_helpers.py`.

**File to modify:** `clausal/modules/py/torch.py`

---

## Predicates

### Statistical reductions

| Name | Arity | Modes | Description |
|---|---|---|---|
| `median` | `/2, /3` | `(+T, -M)`, `(+T, +dim, -M)` | Median value |
| `std` | `/2, /3` | `(+T, -S)`, `(+T, +dim, -S)` | Standard deviation |
| `var` | `/2, /3` | `(+T, -V)`, `(+T, +dim, -V)` | Variance |

`median` with dim returns a named tuple `(values, indices)` — same
pattern as `max`/`min` with dim from Phase 1.

### Selection and sorting

| Name | Arity | Modes | Description |
|---|---|---|---|
| `argmin` | `/2, /3` | `(+T, -I)`, `(+T, +dim, -I)` | Index of minimum |
| `argmax` | `/2, /3` | `(+T, -I)`, `(+T, +dim, -I)` | Index of maximum |
| `sort` | `/2, /3` | `(+T, -sorted)`, `(+T, +dim, -sorted)` | Sort (returns values, indices tuple) |
| `argsort` | `/2, /3` | `(+T, -I)`, `(+T, +dim, -I)` | Indices that would sort |
| `topk` | `/3, /4` | `(+T, +k, -result)`, `(+T, +k, +dim, -result)` | Top-k values and indices |
| `nonzero` | `/2` | `(+T, -indices)` | Indices of nonzero elements |
| `unique` | `/2` | `(+T, -U)` | Unique elements |

`sort` and `topk` return `(values, indices)` tuples. Users decompose
with `is`: `(VALS, IDXS) is RESULT`.

---

## Context and Reference Patterns

All Tier 1 (pure). Use `_pure` and `_pred` from `_helpers.py`.

`sort` and `topk` return named tuples — wrap with `tuple()` like
Phase 4's `svd`/`eig`/`qr`:

```python
sort = _pred("sort",
    (2, _pure(lambda t: tuple(_th().sort(t)))),
    (3, _pure(lambda t, dim: tuple(_th().sort(t, dim=int(dim))))),
)
```

`argmin`/`argmax` without dim return a scalar index (flattened). With
dim, return a tensor of indices along that dimension — same dispatch
pattern as Phase 1's `sum`/`mean`/`max`/`min`.

`nonzero` returns a 2D tensor of shape `(N, ndim)` where N is the number
of nonzero elements. Each row is an index tuple.

`unique` returns the unique elements sorted.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, std, var, median, argmin, argmax,
                         sort, argsort, topk, nonzero, unique,
                         shape, tensor_list])

Test("std of known values") <- (
    tensor([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0], T),
    std(T, S),
    tensor_list(S, SV),
    SV > 1.0,
    SV < 3.0
)

Test("var of constant is zero") <- (
    tensor([3.0, 3.0, 3.0], T),
    var(T, V),
    tensor_list(V, 0.0)
)

Test("argmax") <- (
    tensor([1.0, 5.0, 3.0], T),
    argmax(T, I),
    tensor_list(I, 1)
)

Test("argmin") <- (
    tensor([1.0, 5.0, 3.0], T),
    argmin(T, I),
    tensor_list(I, 0)
)

Test("sort returns values and indices") <- (
    tensor([3.0, 1.0, 2.0], T),
    sort(T, RESULT),
    RESULT is (VALS, IDXS),
    tensor_list(VALS, [1.0, 2.0, 3.0]),
    tensor_list(IDXS, [1, 2, 0])
)

Test("argsort") <- (
    tensor([3.0, 1.0, 2.0], T),
    argsort(T, I),
    tensor_list(I, [1, 2, 0])
)

Test("topk") <- (
    tensor([1.0, 5.0, 3.0, 4.0, 2.0], T),
    topk(T, 3, RESULT),
    RESULT is (VALS, IDXS),
    tensor_list(VALS, [5.0, 4.0, 3.0])
)

Test("nonzero") <- (
    tensor([0.0, 1.0, 0.0, 3.0], T),
    nonzero(T, NZ),
    shape(NZ, [2, 1])
)

Test("unique") <- (
    tensor([3, 1, 2, 1, 3], T),
    unique(T, U),
    tensor_list(U, [1, 2, 3])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_stats_selection_tests.clausal`):
- `std`/`var`/`median` with and without dim
- `argmin`/`argmax` with and without dim
- `sort`/`argsort` with tuple unpacking
- `topk` with tuple unpacking
- `nonzero` shape verification
- `unique` with duplicates
- Edge cases: all-equal tensors, single-element tensors

---

## Docs

Update `docs/torch.md` with statistics and selection sections.

---

## Issues

### 1. Missing opts-dict arities for keyword arguments — NOTED

Several predicates don't expose important PyTorch keyword arguments.
Per Checklist E, defaulted keyword args should be passable via opts dict.

- `sort`/`argsort`: no `descending` option (always ascending)
- `topk`: no `largest` option (always largest-k, no smallest-k)
- `std`/`var`: no `unbiased`/`correction` option (always Bessel's N-1)
- `unique`: no `return_counts`, `return_inverse`, `sorted` options

These should get higher-arity variants accepting opts dicts, e.g.
`sort(T, DIM, OPTS, R)` where `OPTS` is `{"descending": True}`.

### 2. `unique` returns only values — NOTED

PyTorch's `unique` can also return counts and inverse indices, which
are the most useful modes for many applications. The current wrapper
only returns the sorted unique values. An opts-dict variant or
separate `unique_with_counts` predicate would expose this.

### 3. `median` return type varies by arity — NOTED

Arity 2 returns a scalar tensor, arity 3 returns a `(values, indices)`
tuple. This matches PyTorch's own API but may surprise users expecting
consistent tuple returns. Documented as-is.

### 4. Tuple returns follow Phase 4 pattern — OK

`median` with dim, `sort`, and `topk` return `(values, indices)` tuples
matching the `svd`/`eig`/`qr` pattern from Phase 4. This is consistent.
