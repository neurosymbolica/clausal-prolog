# torch_nn — Module Structure, Registries, and Gradient Utilities

Provides nondeterministic enumeration of PyTorch `nn.Module` structure,
registry fact tables for layers, activations, losses, optimizers, and
LR schedulers, plus gradient utility predicates.

## Import

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:import"
```

---

## Predicates

All predicates enumerate via backtracking. Use `findall/3` to collect
results into a list.

### parameter

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:parameter"
```

Enumerate all parameter tensors in `MODEL`.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:parameter_ex2"
```

### named_parameter

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_parameter"
```

Enumerate `(name, tensor)` pairs for all parameters.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_parameter_ex2"
```

### module

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:module"
```

Enumerate all submodules recursively, including `MODEL` itself.

### named_module

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_module"
```

Enumerate `(name, submodule)` pairs recursively. The root module has
name `""`.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_module_ex2"
```

### child

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:child"
```

Enumerate direct children only (not recursive).

### named_child

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_child"
```

Enumerate `(name, child)` pairs for direct children only.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:named_child_ex2"
```

---

## Registries (Fact Tables)

Registry predicates enumerate via backtracking over all known types.
Names use the original PyTorch class names (e.g. `"Linear"`, `"ReLU"`,
`"CrossEntropyLoss"`, `"Adam"`).

### layer

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:layer"
```

Enumerate all `nn.Module` subclasses. Built by introspecting `torch.nn`
at import time, so it stays current across PyTorch versions.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:layer_ex2"
```

### activation

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:activation"
```

Enumerate activation modules (`ReLU`, `Sigmoid`, `Tanh`, `Softmax`, etc.).

### loss_fn

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:loss_fn"
```

Enumerate loss functions (`CrossEntropyLoss`, `MSELoss`, `BCELoss`, etc.).

### optimizer_type

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:optimizer_type"
```

Enumerate optimizer types (`Adam`, `SGD`, `AdamW`, `RMSprop`, etc.).

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:optimizer_type_ex2"
```

### scheduler_type

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:scheduler_type"
```

Enumerate LR scheduler types (`StepLR`, `CosineAnnealingLR`,
`ExponentialLR`, `ReduceLROnPlateau`, etc.). Built by introspecting
`torch.optim.lr_scheduler`.

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:scheduler_type_ex2"
```

---

## Scheduler Queries

### current_lr

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:current_lr"
```

Get the current learning rate(s) from a scheduler. Returns a list of
learning rates (one per parameter group). Supports query `(+sched, -lrs)`
and check `(+sched, +lrs)` modes.

---

## Gradient Utilities (Impure)

These predicates modify gradient tensors **in-place** and are documented
as impure. They are commonly needed at the boundary of training loops.

### clip_grad_norm

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:clip_grad_norm"
```

Clip gradient norms in-place. Returns the total norm before clipping.
`PARAMS` is a list of parameter tensors.

### clip_grad_value

```clausal
--8<-- "tests/fixtures/docs/torch_nn_sigs.txt:clip_grad_value"
```

Clip gradient values in-place to `[-CLIP_VALUE, +CLIP_VALUE]`.
Always succeeds (no return value).

---

## Design Notes

1. **All predicates are nondeterministic.** They yield multiple solutions
   via backtracking. Use `findall/3` to collect all solutions.

2. **Models are opaque handles.** Construct them in Python with
   `-import_module(torch)` and `torch.nn.Linear(...)` etc. The
   enumeration predicates query structure without modifying it.

3. **Recursive vs direct.** `module/2` and `named_module/3` recurse into
   nested submodules. `child/2` and `named_child/3` return only the
   immediate children.
