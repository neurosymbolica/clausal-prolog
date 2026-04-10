# Phase 2 — Conversions and Module Structure

Adds bidirectional tensor conversions and nn.Module enumeration predicates.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` must exist with
tensor creation and property predicates.

**Files to create/modify:**
- Modify `clausal/modules/py/torch.py` — add `numpy/2`, `tensor_list/2`
- Create `clausal/modules/py/torch_nn.py` — module enumeration predicates

---

## Predicates

### Conversions (in `py.torch`)

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `numpy` | `/2` | `(+T,-A)`, `(-T,+A)` | yes — shared memory | Tensor <-> numpy array |
| `tensor_list` | `/2` | `(+T,-L)`, `(-T,+L)` | yes — copies data | Tensor <-> nested Python list |

### Module enumeration (in `py.torch_nn`)

| Name | Arity | Modes | Nondet? | Description |
|---|---|---|---|---|
| `parameter` | `/2` | `(+model, -param)` | yes | Enumerate all parameters |
| `named_parameter` | `/3` | `(+model, -name, -param)` | yes | Parameters with names |
| `module` | `/2` | `(+model, -submodule)` | yes | Enumerate all submodules (recursive) |
| `named_module` | `/3` | `(+model, -name, -submodule)` | yes | Submodules with names |
| `child` | `/2` | `(+model, -child)` | yes | Direct children only |
| `named_child` | `/3` | `(+model, -name, -child)` | yes | Direct children with names |

---

## Context and Reference Patterns

### Bijective conversions (`numpy/2`, `tensor_list/2`)

These are multi-mode: which direction to convert depends on which argument
is bound. Implement with explicit mode dispatch.

Follow the pattern in `clausal/modules/py/sklearn.py` — the `_algorithm_2`
function (around line 180) shows how to check `isinstance(deref(var), Var)`
to determine which arguments are bound vs free:

```python
def _numpy_2(this_generator, parent, tensor_var, array_var, trail):
    t = deref(tensor_var)
    a = deref(array_var)
    torch = _ensure_torch()

    if not isinstance(t, Var) and isinstance(a, Var):
        # Forward: tensor -> numpy
        result = t.detach().cpu().numpy()
        if unify(array_var, result, trail):
            yield (parent, None)
    elif isinstance(t, Var) and not isinstance(a, Var):
        # Reverse: numpy -> tensor
        result = torch.from_numpy(a)
        if unify(tensor_var, result, trail):
            yield (parent, None)
    elif not isinstance(t, Var) and not isinstance(a, Var):
        # Check: both bound, verify roundtrip
        import numpy as np
        if np.array_equal(t.detach().cpu().numpy(), a):
            yield (parent, None)
    yield (parent, DONE)
```

Note: `tensor.numpy()` requires CPU tensors. The wrapper should call
`.detach().cpu().numpy()` to handle GPU tensors transparently.

### Nondeterministic module enumeration

Follow the pattern in `clausal/modules/spacy_module.py` — see the
`_token_2` function for how to iterate over a collection with
`trail.mark()` / `trail.undo()`, yielding each element via backtracking:

```python
def _named_parameter_3(this_generator, parent, model_var, name_var, param_var, trail):
    model = deref(model_var)
    for name, param in model.named_parameters():
        mark = trail.mark()
        if unify(name_var, name, trail) and unify(param_var, param, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)
```

This is the standard nondeterministic enumeration pattern — each
`yield (parent, None)` is a choice point. The trail mark/undo ensures
clean backtracking.

`parameter/2` is the same but without names — just yields each parameter
tensor. `module/2`, `named_module/3`, `child/2`, `named_child/3` follow
the same pattern over `model.modules()`, `model.named_modules()`,
`model.children()`, `model.named_children()` respectively.

### File structure for `torch_nn.py`

Same layout as `torch.py` (Phase 1): lazy import, `_pred()` factory,
`ModulePredicate`. Import `deref`, `unify`, `Var`, `DONE` from
`clausal.logic.util`. No need to import anything from `torch.py` — the
PyTorch types come from PyTorch itself.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, numpy, tensor_list])
-import_from(py.torch_nn, [parameter, named_parameter, module,
                            named_module, child, named_child])

Test("numpy forward: tensor to array") <- (
    tensor([1.0, 2.0, 3.0], T),
    numpy(T, ARR),
    ++isinstance(ARR, ++(numpy.ndarray))
)

Test("numpy reverse: array to tensor") <- (
    ARR is ++(numpy.array([1.0, 2.0, 3.0])),
    numpy(T, ARR),
    tensor_list(T, [1.0, 2.0, 3.0])
)

Test("numpy roundtrip") <- (
    tensor([1.0, 2.0, 3.0], T),
    numpy(T, ARR),
    numpy(T2, ARR),
    tensor_list(T2, [1.0, 2.0, 3.0])
)

Test("tensor_list forward") <- (
    tensor([[1, 2], [3, 4]], T),
    tensor_list(T, [[1, 2], [3, 4]])
)

Test("tensor_list reverse") <- (
    tensor_list(T, [[1.0, 2.0], [3.0, 4.0]]),
    shape(T, [2, 2])
)

Test("enumerate parameters of Linear") <- (
    MODEL is ++(torch.nn.Linear(10, 5)),
    findall(NAME, named_parameter(MODEL, NAME, _), NAMES),
    member("weight", NAMES),
    member("bias", NAMES)
)

Test("parameter count") <- (
    MODEL is ++(torch.nn.Linear(10, 5)),
    findall(P, parameter(MODEL, P), PS),
    length(PS, 2)
)

Test("enumerate submodules of Sequential") <- (
    MODEL is ++(torch.nn.Sequential(
        torch.nn.Linear(10, 5),
        torch.nn.ReLU(),
        torch.nn.Linear(5, 2)
    )),
    findall(N-M, named_module(MODEL, N, M), PAIRS),
    length(PAIRS, LEN),
    LEN >= 4    % Sequential itself + 3 children
)

Test("direct children only") <- (
    MODEL is ++(torch.nn.Sequential(
        torch.nn.Linear(10, 5),
        torch.nn.ReLU(),
        torch.nn.Linear(5, 2)
    )),
    findall(C, child(MODEL, C), CS),
    length(CS, 3)
)

Test("named children") <- (
    MODEL is ++(torch.nn.Sequential(
        torch.nn.Linear(10, 5),
        torch.nn.ReLU()
    )),
    findall(N, named_child(MODEL, N, _), NAMES),
    member("0", NAMES),
    member("1", NAMES)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/clausal_files/torch_conversions.clausal`):
- `numpy/2` in forward, reverse, and check modes
- `tensor_list/2` in both modes
- Roundtrip: tensor -> numpy -> tensor, tensor -> list -> tensor
- Edge cases: scalar tensors, empty tensors, GPU tensors (if available)

**`.clausal` integration tests** (`tests/clausal_files/torch_nn.clausal`):
- All six enumeration predicates with `findall`
- `nn.Linear` (has weight + bias)
- `nn.Sequential` with mixed layer types
- Nested models (Sequential containing Sequential)
- Models with no parameters (e.g. `nn.ReLU()`)

**Python unit tests** (`tests/test_torch_nn_infra.py`):
- Only if `torch_nn.py` has non-trivial infrastructure beyond the standard
  pattern. Likely not needed.

---

## Docs

- Update `docs/torch.md` with `numpy/2` and `tensor_list/2` — modes,
  bijective nature, examples
- Create `docs/torch_nn.md` — module enumeration predicates, nondeterministic
  semantics, examples with `findall`
- All code examples must appear in `.clausal` test files

---

## Issues

_To be populated during implementation._
