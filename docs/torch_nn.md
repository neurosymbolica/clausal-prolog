# torch_nn — Module Structure, Registries, and Gradient Utilities

Provides nondeterministic enumeration of PyTorch `nn.Module` structure,
registry fact tables for layers, activations, losses, optimizers, and
LR schedulers, plus gradient utility predicates.

## Import

```clausal
# skip
-import_from(py.torch_nn, [parameter, named_parameter, module,
                            named_module, child, named_child,
                            layer, activation, loss_fn, optimizer_type,
                            scheduler_type, current_lr,
                            clip_grad_norm, clip_grad_value])
```

---

## Predicates

All predicates enumerate via backtracking. Use `findall/3` to collect
results into a list.

### parameter

```clausal
# skip
parameter(MODEL, PARAM)
```

Enumerate all parameter tensors in `MODEL`.

```clausal
# skip
-import_module(torch)

MODEL is torch.nn.Linear(10, 5),
findall(P, parameter(MODEL, P), PS),
length(PS, 2)
```

### named_parameter

```clausal
# skip
named_parameter(MODEL, NAME, PARAM)
```

Enumerate `(name, tensor)` pairs for all parameters.

```clausal
# skip
MODEL is torch.nn.Linear(10, 5),
findall(NAME, named_parameter(MODEL, NAME, _), NAMES),
in_("weight", NAMES),
in_("bias", NAMES)
```

### module

```clausal
# skip
module(MODEL, SUBMODULE)
```

Enumerate all submodules recursively, including `MODEL` itself.

### named_module

```clausal
# skip
named_module(MODEL, NAME, SUBMODULE)
```

Enumerate `(name, submodule)` pairs recursively. The root module has
name `""`.

```clausal
# skip
MODEL is torch.nn.Sequential(
    torch.nn.Linear(10, 5),
    torch.nn.ReLU(),
    torch.nn.Linear(5, 2)
),
findall(N, named_module(MODEL, N, _), NAMES),
in_("", NAMES),
in_("0", NAMES),
in_("1", NAMES),
in_("2", NAMES)
```

### child

```clausal
# skip
child(MODEL, CHILD)
```

Enumerate direct children only (not recursive).

### named_child

```clausal
# skip
named_child(MODEL, NAME, CHILD)
```

Enumerate `(name, child)` pairs for direct children only.

```clausal
# skip
MODEL is torch.nn.Sequential(
    torch.nn.Linear(10, 5),
    torch.nn.ReLU()
),
findall(N, named_child(MODEL, N, _), NAMES),
in_("0", NAMES),
in_("1", NAMES)
```

---

## Registries (Fact Tables)

Registry predicates enumerate via backtracking over all known types.
Names use the original PyTorch class names (e.g. `"Linear"`, `"ReLU"`,
`"CrossEntropyLoss"`, `"Adam"`).

### layer

```clausal
# skip
layer(NAME, CLASS)
```

Enumerate all `nn.Module` subclasses. Built by introspecting `torch.nn`
at import time, so it stays current across PyTorch versions.

```clausal
# skip
findall(N, layer(N, _), NS),
in_("Linear", NS),
in_("Conv2d", NS),
in_("LSTM", NS)
```

### activation

```clausal
# skip
activation(NAME, CLASS)
```

Enumerate activation modules (`ReLU`, `Sigmoid`, `Tanh`, `Softmax`, etc.).

### loss_fn

```clausal
# skip
loss_fn(NAME, CLASS)
```

Enumerate loss functions (`CrossEntropyLoss`, `MSELoss`, `BCELoss`, etc.).

### optimizer_type

```clausal
# skip
optimizer_type(NAME, CLASS)
```

Enumerate optimizer types (`Adam`, `SGD`, `AdamW`, `RMSprop`, etc.).

```clausal
# skip
findall(N, optimizer_type(N, _), NS),
in_("Adam", NS),
in_("SGD", NS)
```

### scheduler_type

```clausal
# skip
scheduler_type(NAME, CLASS)
```

Enumerate LR scheduler types (`StepLR`, `CosineAnnealingLR`,
`ExponentialLR`, `ReduceLROnPlateau`, etc.). Built by introspecting
`torch.optim.lr_scheduler`.

```clausal
# skip
findall(N, scheduler_type(N, _), NS),
in_("StepLR", NS),
in_("CosineAnnealingLR", NS)
```

---

## Scheduler Queries

### current_lr

```clausal
# skip
current_lr(SCHEDULER, LRs)
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
# skip
clip_grad_norm(PARAMS, MAX_NORM, TOTAL_NORM)
```

Clip gradient norms in-place. Returns the total norm before clipping.
`PARAMS` is a list of parameter tensors.

### clip_grad_value

```clausal
# skip
clip_grad_value(PARAMS, CLIP_VALUE)
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
