# Phase 3 — Registries and IO

Adds fact tables for layer/activation/loss/optimizer types, plus save/load.

**Depends on:** Phase 2 — `clausal/modules/py/torch_nn.py` must exist
with module enumeration predicates and the nondeterministic enumeration
pattern (`trail.mark()` / `trail.undo()`).

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

These are nondeterministic enumerations over static data — the same
`trail.mark()` / `trail.undo()` pattern used in Phase 2 for module
enumeration, and in Phase 1's `_property_2()` for mode dispatch.

Rather than hardcoding fact lists, **introspect `torch.nn`** at import
time to build them dynamically. This keeps registries current across
PyTorch versions:

```python
def _build_layer_facts():
    nn = _ensure_torch().nn
    facts = []
    for name in dir(nn):
        cls = getattr(nn, name)
        if isinstance(cls, type) and issubclass(cls, nn.Module):
            snake = _camel_to_snake(name)
            facts.append((snake, cls))
    return facts
```

Validate during implementation that:
- `_camel_to_snake` handles PyTorch naming correctly (e.g. `BatchNorm2d` -> `batch_norm_2d` or `batch_norm2d`)
- The resulting list is sensible (filters out internal/private classes)
- Similar introspection works for activations (functional API in `torch.nn.functional`) and losses

For `activation/2`, consider introspecting both `torch.nn` (module-based
activations like `nn.ReLU`) and `torch.nn.functional` (function-based
like `F.relu`).

For `optimizer_type/2`, introspect `torch.optim`.

### Exported constants from Phase 1

Phase 1 exports dtype constants (`float32`, `float64`, `int32`, etc.)
directly from `py.torch` via `__getattr__`. Use these in tests and docs
instead of `++()` escapes:

```clausal
# GOOD: use exported dtype constant
-import_from(py.torch, [float32, dtype_info])
dtype_info(float32, bits, 32)

# BAD: ++() escape
dtype_info(++(torch.float32), bits, 32)
```

Similarly, registry tests should export layer/activation classes or use
the name-based lookup mode rather than `++()` for class references.

### Dtype info

`dtype_info/3` is a three-argument fact table. Phase 1 already exports
dtype constants, so the first argument can use those directly.

Dispatch: if `dtype` is bound but `key` is unbound, enumerate all
key-value pairs for that dtype. If both `dtype` and `key` are bound,
look up and unify the value. Follow the `_property_2()` pattern from
Phase 1 (`clausal/modules/py/torch.py`) for mode dispatch via `is_var()`.

### Save/Load (impure)

These are thin wrappers. Use the same `_pure()` pattern from Phase 1 but
document them as impure:

```python
def _save_2(this_generator, parent, obj_var, path_var, trail):
    obj = deref(obj_var)
    path = deref(path_var)
    try:
        _th().save(obj, str(path))
    except Exception:
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)
```

`load/2` similarly wraps `torch.load()` and unifies the result.

---

## Example Usage

Note: `.clausal` files use Python syntax — `#` comments, `not(...)` for
negation. Use exported constants from `py.torch` instead of `++()` escapes
wherever possible. `++()` in goal position always succeeds — never use for
boolean checks.

```clausal
-import_from(py.torch_nn, [layer, activation, loss_fn, optimizer_type])
-import_from(py.torch, [dtype_info, save, load, zeros, shape, float32])

# Registry tests

Test("enumerate all layer types") <- (
    findall(N, layer(N, _), NS),
    member(linear, NS),
    member(conv2d, NS),
    member(lstm, NS)
)

Test("lookup specific layer by name") <- (
    layer(linear, CLASS),
    NAME is ++(CLASS.__name__),
    NAME == "Linear"
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

# Dtype info — using exported constant, no ++() needed

Test("dtype info query") <- (
    dtype_info(float32, bits, BITS),
    BITS == 32
)

Test("dtype info enumerate keys") <- (
    findall(K-V, dtype_info(float32, K, V), PROPS),
    member(bits-32, PROPS),
    member(is_floating_point-true, PROPS)
)

# IO — impure

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

**`.clausal` integration tests** (`tests/fixtures/torch_registries_tests.clausal`):
- All four registries: `findall` enumeration, specific name lookup, reverse lookup
- `dtype_info` in query and enumerate modes — using exported dtype constants
- Registry completeness: check that known layers/activations/losses/optimizers
  appear

**`.clausal` integration tests** (`tests/fixtures/torch_io_tests.clausal`):
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
- Use exported dtype constants in all examples, not `++()` escapes

---

## Issues

### 1. CamelCase-to-snake_case conversion abandoned — FIXED

The plan suggested converting PyTorch class names to snake_case
(`CrossEntropyLoss` -> `cross_entropy_loss`). This produced incorrect
results for names with unconventional casing (`ReLU` -> `re_lu`,
`RMSprop` -> `rm_sprop`). Switched to using the original PyTorch class
names directly as atoms (`"Linear"`, `"ReLU"`, `"CrossEntropyLoss"`).
This follows the "follow the library's naming convention" principle.

### 2. Class identity comparison via `is` after predicate binding — NOTED

`CLASS is torch.nn.Linear` fails when `CLASS` was bound by a predicate
(via `unify`) rather than by a previous `is` expression. The `is`
operator evaluates its RHS as an expression, which may not produce a
value identical to what `unify` bound. Tests use `++(CLASS(10, 5))`
to construct with the looked-up class, or simply call the lookup
twice to verify determinism, rather than comparing class identity.

### 3. `torch.load` requires `weights_only=True` — FIXED

Modern PyTorch (2.6+) defaults to `weights_only=True` and warns/errors
without it. The `load/2` implementation passes `weights_only=True`
explicitly.
