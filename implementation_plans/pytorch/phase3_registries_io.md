# Phase 3 — Registries and IO

Adds fact tables for layer/activation/loss/optimizer types, plus save/load.

**Depends on:** Phase 2 — `clausal/modules/py/torch_nn.py` must exist
with module enumeration predicates.

**Files to modify:**
- `clausal/modules/py/torch_nn.py` — add registry predicates
- `clausal/modules/py/torch.py` — add `save/2`, `load/2`, `dtype_info/3`

---

## Predicates

### Registries (in `py.torch_nn`, nondeterministic fact tables)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `layer` | `/2` | `(+name,-class)`, `(-name,+class)`, `(-name,-class)` | Available nn.Module layer types |
| `activation` | `/2` | `(+name,-fn)`, `(-name,+fn)`, `(-name,-fn)` | Activation functions |
| `loss_fn` | `/2` | `(+name,-class)`, `(-name,+class)`, `(-name,-class)` | Loss functions |
| `optimizer_type` | `/2` | `(+name,-class)`, `(-name,+class)`, `(-name,-class)` | Optimizer types |

### Dtype catalogue (in `py.torch`)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `dtype_info` | `/3` | `(+dtype,+key,-value)`, `(+dtype,-key,-value)` | Dtype properties (bits, is_floating_point, etc.) |

### IO (in `py.torch`, impure)

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `save` | `/2` | `(+obj, +path)` | impure | Save tensor/model state to file |
| `load` | `/2` | `(+path, -obj)` | impure | Load from file |

---

## Context and Reference Patterns

### Registry fact tables

Follow the pattern in `clausal/modules/py/sklearn.py` — see
`_ALGORITHM_FACTS` (a list of `(name, role)` tuples around line 50) and
the `_algorithm_2` dispatch function (around line 180) which enumerates
them via backtracking with `trail.mark()` / `trail.undo()`.

Build similar fact lists:

```python
_LAYER_FACTS = [
    ("linear", "nn.Linear"),
    ("conv1d", "nn.Conv1d"),
    ("conv2d", "nn.Conv2d"),
    ("conv3d", "nn.Conv3d"),
    ("conv_transpose1d", "nn.ConvTranspose1d"),
    ("conv_transpose2d", "nn.ConvTranspose2d"),
    ("batch_norm1d", "nn.BatchNorm1d"),
    ("batch_norm2d", "nn.BatchNorm2d"),
    ("layer_norm", "nn.LayerNorm"),
    ("group_norm", "nn.GroupNorm"),
    ("instance_norm1d", "nn.InstanceNorm1d"),
    ("instance_norm2d", "nn.InstanceNorm2d"),
    ("dropout", "nn.Dropout"),
    ("dropout2d", "nn.Dropout2d"),
    ("embedding", "nn.Embedding"),
    ("lstm", "nn.LSTM"),
    ("gru", "nn.GRU"),
    ("rnn", "nn.RNN"),
    ("transformer", "nn.Transformer"),
    ("transformer_encoder", "nn.TransformerEncoder"),
    ("transformer_decoder", "nn.TransformerDecoder"),
    ("multi_head_attention", "nn.MultiheadAttention"),
]
```

However, rather than hardcoding, consider **introspecting `torch.nn`** at
import time to build the list dynamically. This keeps the registry current
across PyTorch versions:

```python
def _build_layer_facts():
    nn = _ensure_torch().nn
    facts = []
    for name in dir(nn):
        cls = getattr(nn, name)
        if isinstance(cls, type) and issubclass(cls, nn.Module):
            # Convert CamelCase to snake_case for the atom name
            snake = _camel_to_snake(name)
            facts.append((snake, cls))
    return facts
```

This approach should be validated during implementation — check whether
it produces a sensible list and whether the snake_case conversion handles
PyTorch's naming (e.g. `BatchNorm2d` -> `batch_norm2d`).

### Dtype info

`dtype_info/3` is a three-argument fact table enumerating properties of
each dtype. Structure as a static dict:

```python
_DTYPE_PROPS = {
    torch.float16:  {"bits": 16, "is_floating_point": True,  "is_complex": False, "is_signed": True},
    torch.float32:  {"bits": 32, "is_floating_point": True,  "is_complex": False, "is_signed": True},
    torch.float64:  {"bits": 64, "is_floating_point": True,  "is_complex": False, "is_signed": True},
    torch.int8:     {"bits": 8,  "is_floating_point": False, "is_complex": False, "is_signed": True},
    torch.int16:    {"bits": 16, "is_floating_point": False, "is_complex": False, "is_signed": True},
    torch.int32:    {"bits": 32, "is_floating_point": False, "is_complex": False, "is_signed": True},
    torch.int64:    {"bits": 64, "is_floating_point": False, "is_complex": False, "is_signed": True},
    torch.bool:     {"bits": 1,  "is_floating_point": False, "is_complex": False, "is_signed": False},
    # ... etc
}
```

Dispatch: if `dtype` is bound but `key` is unbound, enumerate all
key-value pairs for that dtype. If both `dtype` and `key` are bound,
look up and unify the value.

### Save/Load (impure)

These are thin wrappers. Mark them clearly as impure in docs:

```python
def _save_2(this_generator, parent, obj_var, path_var, trail):
    obj = deref(obj_var)
    path = deref(path_var)
    torch = _ensure_torch()
    try:
        torch.save(obj, str(path))
    except Exception:
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)
```

`load/2` similarly wraps `torch.load()` and unifies the result.

---

## Example Usage

```clausal
-import_from(py.torch_nn, [layer, activation, loss_fn, optimizer_type])
-import_from(py.torch, [dtype_info, save, load, zeros])

Test("enumerate all layer types") <- (
    findall(N, layer(N, _), NS),
    member(linear, NS),
    member(conv2d, NS),
    member(lstm, NS)
)

Test("lookup specific layer class") <- (
    layer(linear, CLASS),
    CLASS == ++(torch.nn.Linear)
)

Test("reverse lookup: class to name") <- (
    layer(NAME, ++(torch.nn.Linear)),
    NAME == linear
)

Test("enumerate activations") <- (
    findall(N, activation(N, _), NS),
    member(relu, NS),
    member(sigmoid, NS),
    member(tanh, NS),
    member(softmax, NS)
)

Test("enumerate loss functions") <- (
    findall(N, loss_fn(N, _), NS),
    member(cross_entropy, NS),
    member(mse, NS)
)

Test("enumerate optimizer types") <- (
    findall(N, optimizer_type(N, _), NS),
    member(adam, NS),
    member(sgd, NS)
)

Test("dtype info query") <- (
    dtype_info(++(torch.float32), bits, BITS),
    BITS == 32
)

Test("dtype info enumerate keys") <- (
    findall(K-V, dtype_info(++(torch.float32), K, V), PROPS),
    member(bits-32, PROPS),
    member(is_floating_point-true, PROPS)
)

Test("save and load roundtrip") <- (
    zeros([3, 4], T),
    PATH is "/tmp/clausal_test_tensor.pt",
    save(T, PATH),
    load(PATH, T2),
    shape(T2, [3, 4])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/clausal_files/torch_registries.clausal`):
- All four registries: `findall` enumeration, specific lookup, reverse lookup
- `dtype_info` in query and enumerate modes
- Registry completeness: check that known layers/activations/losses/optimizers
  appear

**`.clausal` integration tests** (`tests/clausal_files/torch_io.clausal`):
- `save/2` and `load/2` roundtrip with tensors
- `save/2` and `load/2` roundtrip with model state_dict
- Load nonexistent file fails (predicate failure, not crash)
- Temp file cleanup (use `/tmp/` paths)

**Python unit tests:**
- If using introspection for registries: test that `_build_layer_facts()`
  produces a non-empty list with expected entries
- `_camel_to_snake` conversion edge cases if implemented

---

## Docs

- Update `docs/torch_nn.md` with registry predicates — enumeration,
  lookup, reverse lookup examples
- Update `docs/torch.md` with `dtype_info/3` and `save/2`, `load/2`
- Note `save/2` and `load/2` as impure
- All code examples must appear in `.clausal` test files

---

## Issues

_To be populated during implementation._
