# Phase 10 — Datasets

Wraps `torch.utils.data` — dataset definition and access. Dataset
*definition* and item access are relational. Iteration (DataLoader)
is stateful and stays as `++()`.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to create:** `clausal/modules/py/torch_data.py`

---

## Predicates

### Dataset construction

| Name | Arity | Modes | Description |
|---|---|---|---|
| `tensor_dataset` | `/2` | `(+tensors, -dataset)` | Create TensorDataset from list of tensors |
| `dataset_length` | `/2` | `(+dataset, -N)` | Number of items in dataset |
| `dataset_item` | `/3` | `(+dataset, +index, -item)` | Get item by index |

### Nondeterministic access

| Name | Arity | Modes | Nondet? | Description |
|---|---|---|---|---|
| `dataset_element` | `/2` | `(+dataset, -item)` | yes | Enumerate items via backtracking |
| `dataset_element` | `/3` | `(+dataset, -index, -item)` | yes | Enumerate (index, item) pairs |

### Built-in datasets (if torchvision available)

Not in core scope — torchvision is a separate package. Note for future.

---

## Context and Reference Patterns

`dataset_item/3` is a pure indexed lookup:

```python
dataset_item = _pred("dataset_item",
    (3, _pure(lambda ds, idx: ds[int(idx)])),
)
```

`dataset_element/2,3` are nondeterministic — enumerate over
`range(len(dataset))` using the `trail.mark()` / `trail.undo()` pattern
from Phase 2 (`torch_nn.py` module enumeration).

`dataset_length/2` follows `_property_2()` from Phase 1.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, shape])
-import_from(py.torch_data, [tensor_dataset, dataset_length,
                              dataset_item, dataset_element])

# Create a dataset from tensors
Test("tensor_dataset length") <- (
    tensor([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], X),
    tensor([0, 1, 0], Y),
    tensor_dataset([X, Y], DS),
    dataset_length(DS, 3)
)

# Access by index
Test("dataset_item") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], X),
    tensor([0, 1], Y),
    tensor_dataset([X, Y], DS),
    dataset_item(DS, 0, ITEM),
    # ITEM is a tuple of tensors
    ITEM is (X0, Y0),
    tensor_list(Y0, 0)
)

# Enumerate items via backtracking
Test("dataset_element enumerate") <- (
    tensor([[1.0], [2.0], [3.0]], X),
    tensor([10, 20, 30], Y),
    tensor_dataset([X, Y], DS),
    findall(I, dataset_element(DS, I, _), INDICES),
    length(INDICES, 3)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_data_tests.clausal`):
- `tensor_dataset` creation and length
- `dataset_item` access by index, shape verification
- `dataset_element` enumeration with `findall`
- Out-of-bounds index fails gracefully
- Single-tensor and multi-tensor datasets

---

## Docs

Create `docs/torch_data.md`.

---

## Issues

No issues. Straightforward implementation using established patterns:
`_pure` from `_helpers`, `_property_2` with query/check modes,
nondeterministic enumeration with `trail.mark()`/`trail.undo()`.
