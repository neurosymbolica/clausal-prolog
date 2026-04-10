# Phase 2 — Conversions and Module Structure

Adds bidirectional tensor conversions and nn.Module enumeration predicates.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` must exist with
tensor creation, property predicates, and the `_deep_deref()`, `_pure()`,
`_pred()`, `_property_2()`, `_bidir_2()` helpers.

**Files to create/modify:**
- Modify `clausal/modules/py/torch.py` — add `tensor_numpy/2`, `tensor_list/2`
- Create `clausal/modules/py/torch_nn.py` — module enumeration predicates

---

## Predicates

### Conversions (in `py.torch`)

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `tensor_numpy` | `/2` | `(+T,-A)`, `(-T,+A)` | yes — shared memory | Tensor <-> numpy array |
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

### Bijective conversions (`tensor_numpy/2`, `tensor_list/2`)

These are multi-mode: which direction to convert depends on which argument
is bound. Phase 1 already established the `_bidir_2()` helper in
`clausal/modules/py/torch.py` — use it. It handles all four mode
combinations (forward, reverse, check, both-unbound).

```python
# _bidir_2() from Phase 1 — already in torch.py
# forward_fn: called when first arg is bound, second is unbound
# backward_fn: called when first arg is unbound, second is bound
tensor_numpy = _pred("tensor_numpy",
    (2, _bidir_2(
        forward_fn=lambda t: t.detach().cpu().numpy(),
        backward_fn=lambda a: _th().from_numpy(a),
    )),
)
```

Note: `tensor.numpy()` requires CPU tensors. The forward function must
call `.detach().cpu().numpy()` to handle GPU tensors transparently.

For `tensor_list`, the backward function is `lambda l: _th().tensor(l)`.

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

Same layout as `torch.py` (Phase 1): lazy import with `_ensure_torch()`,
`_pred()` factory, `ModulePredicate`. Import `deref`, `unify`, `Var`,
`DONE` from `clausal.logic.util`. Use `is_var()` for mode dispatch.

No need to import anything from `py.torch` — the PyTorch types come from
PyTorch itself.

---

## Example Usage

Note: `.clausal` files use Python syntax — `#` comments, `not(...)` for
negation, `[H, *REST]` for list decomposition. `++()` in goal position
always succeeds and should not be used for boolean checks.

Where models need to be constructed from the Python API for testing, use
`-import_module(torch)` and construct via `++()`. This is acceptable for
test fixtures — the goal is zero `++()` in the *predicates being tested*.

```clausal
-import_from(py.torch, [tensor, tensor_numpy, tensor_list, shape])
-import_from(py.torch_nn, [parameter, named_parameter, module,
                            named_module, child, named_child])
-import_module(torch)
-import_module(numpy)

# Conversion tests

Test("tensor_numpy forward") <- (
    tensor([1.0, 2.0, 3.0], T),
    tensor_numpy(T, ARR),
    tensor_list(T, [1.0, 2.0, 3.0])
)

Test("tensor_numpy reverse") <- (
    ARR is ++(numpy.array([1.0, 2.0, 3.0])),
    tensor_numpy(T, ARR),
    tensor_list(T, [1.0, 2.0, 3.0])
)

Test("tensor_numpy roundtrip") <- (
    tensor([1.0, 2.0, 3.0], T),
    tensor_numpy(T, ARR),
    tensor_numpy(T2, ARR),
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

# Module enumeration tests

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
    LEN >= 4    # Sequential itself + 3 children
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

**`.clausal` integration tests** (`tests/fixtures/torch_conversions.clausal`):
- `tensor_numpy/2` in forward, reverse, and check modes
- `tensor_list/2` in both modes
- Roundtrip: tensor -> numpy -> tensor, tensor -> list -> tensor
- Edge cases: scalar tensors, empty tensors

**`.clausal` integration tests** (`tests/fixtures/torch_nn_tests.clausal`):
- All six enumeration predicates with `findall`
- `nn.Linear` (has weight + bias)
- `nn.Sequential` with mixed layer types
- Nested models (Sequential containing Sequential)
- Models with no parameters (e.g. `nn.ReLU()`)

**Python unit tests:**
- Only if `torch_nn.py` has non-trivial infrastructure beyond the standard
  pattern. Likely not needed.

---

## Docs

- Update `docs/torch.md` with `tensor_numpy/2` and `tensor_list/2` — modes,
  bijective nature, examples
- Create `docs/torch_nn.md` — module enumeration predicates, nondeterministic
  semantics, examples with `findall`
- All code examples must appear in `.clausal` test files

---

## Issues

_To be populated during implementation._
