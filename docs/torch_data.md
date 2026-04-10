# torch_data — Datasets

Wraps `torch.utils.data` — dataset definition and item access.
Dataset *definition* and item access are relational. Iteration
(DataLoader) is stateful and stays as `++()`.

## Import

```clausal
# skip
-import_from(py.torch_data, [tensor_dataset, dataset_length,
                              dataset_item, dataset_element])
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 1 — pure | `tensor_dataset`, `dataset_item` | Construction and indexed access |
| 1 — pure (property) | `dataset_length` | Query or check length |
| 1 — pure (nondet) | `dataset_element` | Enumerate items via backtracking |

---

## Construction

### tensor_dataset

```clausal
# skip
tensor_dataset(TENSORS, DS)
```

Create a `TensorDataset` from a list of tensors. All tensors must have
the same first dimension (number of samples).

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], X),
tensor([0, 1, 0], Y),
tensor_dataset([X, Y], DS)
```

---

## Properties

### dataset_length

```clausal
# skip
dataset_length(DS, N)
```

Number of items in the dataset. Supports query `(+ds, -n)` and check
`(+ds, +n)` modes.

```clausal
# skip
tensor_dataset([X, Y], DS),
dataset_length(DS, 3)
```

---

## Item Access

### dataset_item

```clausal
# skip
dataset_item(DS, INDEX, ITEM)
```

Get a single item by index. Returns a tuple of tensors (one per tensor
in the dataset). Access tuple elements via `++()`:

```clausal
# skip
dataset_item(DS, 0, ITEM),
X0 is ++(ITEM[0])
```

Fails gracefully on out-of-bounds indices.

---

## Enumeration

### dataset_element

```clausal
# skip
dataset_element(DS, ITEM)
dataset_element(DS, INDEX, ITEM)
```

Enumerate items via backtracking. The 2-arity version yields each item;
the 3-arity version yields `(index, item)` pairs.

```clausal
# skip
findall(I, dataset_element(DS, I, _), INDICES),
length(INDICES, 3)
```
