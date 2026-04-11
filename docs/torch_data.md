# torch_data — Datasets

Wraps `torch.utils.data` — dataset definition and item access.
Dataset *definition* and item access are relational. Iteration
(DataLoader) is stateful and stays as `++()`.

## Import

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:import"
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
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:tensor_dataset"
```

Create a `TensorDataset` from a list of tensors. All tensors must have
the same first dimension (number of samples).

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:tensor_dataset_ex2"
```

---

## Properties

### dataset_length

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_length"
```

Number of items in the dataset. Supports query `(+ds, -n)` and check
`(+ds, +n)` modes.

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_length_ex2"
```

---

## Item Access

### dataset_item

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_item"
```

Get a single item by index. Returns a tuple of tensors (one per tensor
in the dataset). Access tuple elements via `++()`:

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_item_ex2"
```

Fails gracefully on out-of-bounds indices.

---

## Enumeration

### dataset_element

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_element"
```

Enumerate items via backtracking. The 2-arity version yields each item;
the 3-arity version yields `(index, item)` pairs.

```clausal
--8<-- "tests/fixtures/docs/torch_data_sigs.txt:dataset_element_ex2"
```
