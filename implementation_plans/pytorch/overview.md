# PyTorch Wrapper — Overview

PyTorch is a tensor computation library with GPU acceleration and automatic
differentiation, primarily used for deep learning. Unlike scikit-learn (one
uniform Estimator pattern), PyTorch has **four independent subsystems** with
very different characters — from pure tensor math to deeply stateful
training loops.

The wrapper strategy: wrap what's naturally relational, be honest about
what's impure, and don't pretend GPU mutation is backtrackable.

## Phases

- [Phase 1 — Tensor Core](phase1_tensor_core.md): creation, properties, math, shape ops
- [Phase 2 — Conversions and Module Structure](phase2_conversions_modules.md): bijective conversions, nn.Module enumeration
- [Phase 3 — Registries and IO](phase3_registries_io.md): fact tables, save/load

---

## Core Abstractions

PyTorch has four major subsystems, each with its own central concept:

### `torch.Tensor` — Multidimensional Array

The fundamental data type. Most tensor operations are **pure**: they take
tensors in and produce new tensors out, without mutating the originals.

- **Lifecycle:** create -> compute -> query properties -> extract data
- **Purity:** Tensor math is pure. Shape/dtype/device queries are pure.
  In-place operations (`add_`, `mul_`) exist but the functional versions
  are preferred and the wrapper should expose only functional forms.
- **Key insight:** A tensor is fully characterised by its data, shape,
  dtype, and device. These four properties are the natural predicate
  vocabulary.

### `torch.nn.Module` — Model Architecture

A tree of nested modules, each holding parameters (tensors with gradients).
The architecture is stateful but **structurally static** after construction —
the tree shape doesn't change, only parameter values change during training.

- **Lifecycle:** construct layers -> compose into model -> forward pass ->
  query parameters/structure
- **Purity:** Construction is pure. Forward pass reads parameters (pure if
  we treat parameters as immutable handles). Structure queries (modules,
  parameters, named_parameters) are pure enumeration.
- **Key insight:** The module tree is a natural fit for relational
  enumeration — `parameter(MODEL, NAME, TENSOR)` via backtracking.

### `torch.optim` — Optimizers

State machines that update model parameters using gradients. Deeply
stateful: `step()` mutates parameter tensors and internal state (momentum
buffers, Adam moments) in-place on GPU.

- **Lifecycle:** create with params + hyperparams -> zero_grad -> backward
  -> step (repeat)
- **Purity:** **Fundamentally impure.** State-threading is impractical
  (copying GPU tensors for backtracking safety would be prohibitively
  expensive). The training loop should stay close to `++()` or use
  thin impure wrappers that are documented as such.
- **Key insight:** Hyperparameter queries (learning rate, momentum, weight
  decay) and parameter group enumeration *are* pure and relational.

### `torch.utils.data` — Data Loading

Datasets and dataloaders for batching, shuffling, and parallel loading.
IO-heavy and iterator-based.

- **Lifecycle:** define dataset -> wrap in dataloader -> iterate batches
- **Purity:** Dataset construction is pure. Iteration is stateful (file
  handles, shuffle state, worker processes).
- **Key insight:** Dataset *definition* (what data, what transforms) is
  relational. Iteration is not.

---

## Bijective Relationships

### Strict bijections (both directions computable)

| Procedural pair | Predicate | Notes |
|---|---|---|
| `tensor.squeeze(d)` / `tensor.unsqueeze(d)` | `squeeze(T, DIM, T2)` | Strict inverses at a given dim |
| `tensor.flatten(s,e)` / `tensor.unflatten(d,shape)` | `flatten(T, START, END, T2)` | Inverse needs original shape |
| `torch.from_numpy(a)` / `tensor.numpy()` | `numpy(TENSOR, ARRAY)` | Bidirectional, shared memory |
| `tensor.tolist()` / `torch.tensor(list)` | `tensor_list(TENSOR, LIST)` | Bidirectional, copies data |
| `torch.save(obj, path)` / `torch.load(path)` | `saved(OBJ, PATH)` | Serialization pair |
| `tensor.transpose(d0,d1)` self-inverse | `transpose(T, D0, D1, T2)` | `transpose(transpose(T)) == T` |

### Multi-mode property queries (query or constrain)

| Property | Predicate | Modes |
|---|---|---|
| `tensor.shape` | `shape(TENSOR, SHAPE)` | `(+,-)` query, `(+,+)` check |
| `tensor.dtype` | `dtype(TENSOR, DTYPE)` | `(+,-)` query, `(+,+)` check |
| `tensor.device` | `device(TENSOR, DEVICE)` | `(+,-)` query, `(+,+)` check |
| `tensor.dim()` | `dim(TENSOR, N)` | `(+,-)` query, `(+,+)` check |
| `tensor.numel()` | `element_count(TENSOR, N)` | `(+,-)` query |
| `tensor.requires_grad` | `requires_gradient(TENSOR, BOOL)` | `(+,-)` query, `(+,+)` check |

### Enumerables (nondeterministic via backtracking)

| Collection | Predicate | Yields |
|---|---|---|
| `model.parameters()` | `parameter(MODEL, PARAM)` | Each parameter tensor |
| `model.named_parameters()` | `named_parameter(MODEL, NAME, PARAM)` | Name-tensor pairs |
| `model.modules()` | `module(MODEL, SUBMODULE)` | Each submodule |
| `model.named_modules()` | `named_module(MODEL, NAME, SUBMODULE)` | Name-submodule pairs |
| `model.children()` | `child(MODEL, CHILD)` | Direct children only |
| `model.named_children()` | `named_child(MODEL, NAME, CHILD)` | Direct children with names |
| `optimizer.param_groups` | `param_group(OPT, GROUP)` | Each parameter group dict |

### Broader relational patterns

- **Layer registry:** `layer(NAME, CLASS)` — enumerate available layer types
  via backtracking
- **Activation functions:** `activation(NAME, FN)` — enumerate activations
- **Loss functions:** `loss(NAME, CLASS)` — enumerate loss functions
- **Dtype catalogue:** `dtype_info(DTYPE, KEY, VALUE)` — properties of each dtype

---

## Purity Analysis

### Pure (backtracking-safe)

All tensor math — arithmetic, matmul, convolution, activation functions,
reductions, comparisons. These produce new tensors without mutating inputs.

All property queries — shape, dtype, device, dim, element_count, requires_gradient.

All structural queries — parameter enumeration, module tree traversal.

All tensor creation — `zeros`, `ones`, `randn`, `arange`, `linspace`, etc.

Shape operations — `reshape`, `transpose`, `squeeze`, `unsqueeze`, `flatten`,
`unflatten`, `permute`, `contiguous`, `expand`, `repeat`, `cat`, `stack`,
`split`, `chunk`.

Type/device conversions — `to(dtype)`, `to(device)`, `float()`, `int()`,
`cpu()`, `cuda()`.

### Stateful (needs state threading or impure acknowledgement)

**Training loop operations** — these mutate in-place on GPU:
- `loss.backward()` — populates `.grad` buffers on leaf tensors
- `optimizer.zero_grad()` — zeros all `.grad` buffers
- `optimizer.step()` — updates parameters and optimizer state in-place

State-threading is impractical here. A model's parameters live on GPU;
copying them for backtracking safety would:
- Require O(parameters) GPU memory per choice point
- Destroy performance (GPU->CPU->GPU round trips)
- Defeat the purpose of using PyTorch

**Decision:** Training loop stays as `++()` or thin impure wrappers
documented as non-backtrackable.

**Model construction** is a middle ground. `nn.Linear(in, out)` allocates
parameters, but the construction itself could be treated as pure if we
treat the resulting module as an opaque value. The mutation happens later
during training, not during construction.

### Constraint-like

**Shape compatibility** is constraint-like — matmul requires compatible
dimensions, broadcasting has rules, conv2d has stride/padding/dilation
constraints. However, PyTorch's shape inference is eager (fails at
runtime), not lazy (fails when checked). Wrapping shape rules as
constraints would be a significant new feature, not a thin wrapper.

**Decision:** Defer shape-as-constraints to a future phase. For now, let
shape errors propagate as predicate failure.

---

## Tier Classification

| Tier | Operations |
|---|---|
| **1 — Pure** | Tensor math, shape ops, type/device conversions, creation functions, property queries |
| **2 — Fact tables** | Layer registry, activation registry, loss registry, dtype catalogue |
| **3 — Handle-based** | nn.Module (treated as opaque after construction), DataLoader |
| **4 — IO/Impure** | Training loop (backward, step, zero_grad), save/load, cuda management |

---

## Scope

### In scope (Phase 1-3)

**Tensor core** — creation, math, shape, dtype/device queries and
conversions. This is the largest and purest surface. ~20 predicates
covering the most common tensor operations.

**Module queries** — parameter/module enumeration, structural queries.
Pure, relational, natural fit for backtracking. ~8 predicates.

**Registries** — layer, activation, loss, dtype fact tables. ~4 predicates.

**Bijections** — squeeze/unsqueeze, flatten/unflatten, numpy conversion,
save/load. ~6 predicates.

### Out of scope (stay as `++()`)

**Training loop** — `backward()`, `step()`, `zero_grad()`. Fundamentally
impure, impractical to state-thread. Users write training loops in Python
and call into Clausal for architecture search, hyperparameter exploration,
or data pipeline logic.

**torch.jit** — compilation/tracing is a deployment concern, not a logic
programming task.

**torch.distributed** — multi-machine coordination is orchestration, not
relational.

**torch.cuda low-level** — memory management, streams, events.

### Deferred

**Shape constraints** — expressing shape compatibility as CLP-style
constraints. Interesting but a research project, not a wrapper task.

**Architecture search** — using backtracking to enumerate valid
architectures. Builds on Phase 2 (module queries) but needs design work.

**Data pipeline** — relational dataset definition. Needs design work on
how to express transforms.

---

## Term Language

PyTorch's own types are the terms. `torch.Tensor`, `torch.dtype`,
`torch.device`, and `nn.Module` subclasses are all Python classes that
are first-class in Clausal — matchable in clause heads, constructible in
bodies.

### Core types (used directly from PyTorch)

| Type | Role | Example |
|---|---|---|
| `torch.Tensor` | The fundamental data type | Result of any tensor operation |
| `torch.dtype` | Data type descriptor | `torch.float32`, `torch.int64` |
| `torch.device` | Hardware location | `torch.device('cpu')`, `torch.device('cuda:0')` |
| `torch.Size` | Shape tuple | `torch.Size([3, 4, 5])` |
| `nn.Module` subclasses | Model components | `nn.Linear(10, 5)`, `nn.Conv2d(3, 16, 3)` |

### Wrapper-defined terms (for groupings without a PyTorch class)

| Term | Constructor | Semantics |
|---|---|---|
| `layer_info(NAME, CLASS, DEFAULTS)` | Registry entry | Available layer type with default args |
| `param_info(NAME, SHAPE, DTYPE, REQUIRES_GRAD)` | Parameter descriptor | Decomposed view of a parameter |

These are lightweight — most of the term language *is* PyTorch's own types.

---

## Predicate Catalogue

### Tensor creation

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `tensor` | `/2` | `(+data, -T)` | pure | Create tensor from list/nested list |
| `zeros` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | pure | Zero tensor; opts dict for dtype/device |
| `ones` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | pure | Ones tensor |
| `randn` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | pure | Normal random tensor |
| `arange` | `/2, /3, /4` | `(+end, -T)`, ... | pure | Range tensor |
| `linspace` | `/4, /5` | `(+start, +end, +steps, -T)`, ... | pure | Linearly spaced tensor |
| `full` | `/3, /4` | `(+shape, +value, -T)`, ... | pure | Filled tensor |
| `eye` | `/2, /3` | `(+n, -T)`, `(+n, +m, -T)` | pure | Identity matrix |

### Tensor properties (multi-mode)

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `shape` | `/2` | `(+T,-S)`, `(+T,+S)` check | pure | partial — query + check | Shape of tensor |
| `dtype` | `/2` | `(+T,-D)`, `(+T,+D)` check | pure | partial — query + check | Dtype of tensor |
| `device` | `/2` | `(+T,-D)`, `(+T,+D)` check | pure | partial — query + check | Device of tensor |
| `dim` | `/2` | `(+T,-N)` | pure | no | Number of dimensions |
| `element_count` | `/2` | `(+T,-N)` | pure | no | Number of elements |
| `requires_gradient` | `/2` | `(+T,-B)` | pure | no | Gradient tracking flag |

### Shape operations (bijective pairs)

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `reshape` | `/3` | `(+T,+shape,-T2)` | pure | with shape | Reshape tensor |
| `squeeze` | `/2, /3` | `(+T,-T2)`, `(+T,+dim,-T2)` | pure | `unsqueeze` | Remove size-1 dims |
| `unsqueeze` | `/3` | `(+T,+dim,-T2)` | pure | `squeeze` | Add size-1 dim |
| `flatten` | `/2, /4` | `(+T,-T2)`, `(+T,+start,+end,-T2)` | pure | `unflatten` | Flatten dims |
| `unflatten` | `/4` | `(+T,+dim,+shape,-T2)` | pure | `flatten` | Unflatten dim |
| `transpose` | `/4` | `(+T,+d0,+d1,-T2)` | pure | self-inverse | Swap two dims |
| `permute` | `/3` | `(+T,+dims,-T2)` | pure | with inverse perm | Reorder all dims |
| `contiguous` | `/2` | `(+T,-T2)` | pure | no | Make memory contiguous |

### Tensor math

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `matmul` | `/3` | `(+A,+B,-C)` | pure | Matrix multiply |
| `add` | `/3` | `(+A,+B,-C)` | pure | Element-wise add |
| `mul` | `/3` | `(+A,+B,-C)` | pure | Element-wise multiply |
| `cat` | `/3` | `(+tensors,+dim,-T)` | pure | Concatenate along dim |
| `stack` | `/3` | `(+tensors,+dim,-T)` | pure | Stack along new dim |
| `sum` | `/2, /3` | `(+T,-S)`, `(+T,+dim,-S)` | pure | Sum reduction |
| `mean` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | pure | Mean reduction |
| `max` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | pure | Max reduction |
| `min` | `/2, /3` | `(+T,-M)`, `(+T,+dim,-M)` | pure | Min reduction |
| `clamp` | `/4` | `(+T,+min,+max,-T2)` | pure | Clamp values |
| `abs` | `/2` | `(+T,-T2)` | pure | Absolute value |
| `softmax` | `/3` | `(+T,+dim,-T2)` | pure | Softmax |
| `relu` | `/2` | `(+T,-T2)` | pure | ReLU activation |

### Conversion (bijective)

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `numpy` | `/2` | `(+T,-A)`, `(-T,+A)` | pure | yes — shared memory | Tensor <-> numpy |
| `tensor_list` | `/2` | `(+T,-L)`, `(-T,+L)` | pure | yes — copies | Tensor <-> nested list |

### Module structure (nondeterministic enumeration)

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `parameter` | `/2` | `(+model, -param)` | pure | yes | Enumerate all parameters |
| `named_parameter` | `/3` | `(+model, -name, -param)` | pure | yes | Parameters with names |
| `module` | `/2` | `(+model, -submodule)` | pure | yes | Enumerate all submodules |
| `named_module` | `/3` | `(+model, -name, -submodule)` | pure | yes | Submodules with names |
| `child` | `/2` | `(+model, -child)` | pure | yes | Direct children |
| `named_child` | `/3` | `(+model, -name, -child)` | pure | yes | Direct children with names |

### Registries (fact tables, nondeterministic)

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `layer` | `/2` | `(+name,-class)`, `(-name,-class)` | pure | yes | Available layer types |
| `activation` | `/2` | `(+name,-fn)`, `(-name,-fn)` | pure | yes | Activation functions |
| `loss_fn` | `/2` | `(+name,-class)`, `(-name,-class)` | pure | yes | Loss functions |
| `optimizer_type` | `/2` | `(+name,-class)`, `(-name,-class)` | pure | yes | Optimizer types |
| `dtype_info` | `/3` | `(+dtype,+key,-value)` | pure | yes | Dtype properties |

### IO / Impure

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `save` | `/2` | `(+obj, +path)` | impure | Save tensor/model to file |
| `load` | `/2` | `(+path, -obj)` | impure | Load from file |

---

## Submodule Breakdown

```
clausal/modules/py/torch.py           # Core: tensor creation, math, properties, conversions
clausal/modules/py/torch_nn.py        # nn.Module: structure queries, layer registry
clausal/modules/py/torch_optim.py     # Optimizer registry, hyperparameter queries (thin)
```

`torch.py` is the main module. It defines tensor predicates and exports
the PyTorch types (`Tensor`, `dtype`, `device`, `Size`) as terms.

`torch_nn.py` imports from `torch.py` and adds module enumeration, layer/
activation/loss registries.

`torch_optim.py` is thin — just the optimizer type registry and
hyperparameter queries. The actual training loop stays in Python.

Shared types (`torch.Tensor`, `torch.dtype`, etc.) come from PyTorch
itself — no need to define or re-export them.

---

## Showcase Example

```clausal
-import_from(py.torch, [tensor, zeros, shape, dtype, device, matmul,
                         reshape, squeeze, unsqueeze, relu, softmax,
                         numpy, tensor_list])
-import_from(py.torch_nn, [named_parameter, named_module, layer])

% Pure tensor computation
classify(INPUT, PROBS) <- (
    W1 is ++(torch.randn(784, 256)),
    W2 is ++(torch.randn(256, 10)),
    matmul(INPUT, W1, H),
    relu(H, H_ACT),
    matmul(H_ACT, W2, LOGITS),
    softmax(LOGITS, 1, PROBS)
)

% Enumerate all parameters in a model
large_parameters(MODEL, NAME, PARAM) <- (
    named_parameter(MODEL, NAME, PARAM),
    element_count(PARAM, N),
    N > 1000
)

% Find all conv layers in a model
conv_layers(MODEL, NAME, MOD) <- (
    named_module(MODEL, NAME, MOD),
    ++isinstance(MOD, torch.nn.Conv2d)
)

% Multi-mode: query or check shape
check_batch_shape(T, BATCH_SIZE) <- (
    shape(T, S),
    S is [BATCH_SIZE, *_]
)

% Enumerate available layer types
all_layers(LAYERS) <- (
    findall(NAME, layer(NAME, _), LAYERS)
)
```

---

## Design Notes

Upfront observations to keep in mind during implementation:

1. **`shape/2`, `dtype/2`, `device/2` in `(+T, +S)` mode are check-only.**
   They don't reshape/cast/transfer — that's what `reshape/3` and `++(T.to(...))`
   are for. Check-only is more relational.

2. **No in-place operations.** The wrapper exposes only functional (non-mutating)
   forms. In-place operations (`add_`, `mul_`, etc.) break backtracking.

3. **`tensor/2` name collision** is a non-issue — module-scoped imports prevent it.

4. **GPU tensor equality.** PyTorch's `==` is element-wise, not scalar. Use
   `++(torch.equal(T1, T2))` or compare via `tensor_list` in tests.

5. **`randn` randomness** is acceptable — same category as `random_float/1`
   in Prolog. "Pure" in the sense of no side effects.

6. **Registry maintenance.** Consider generating fact tables from `torch.nn`
   introspection rather than hardcoding, to stay current across PyTorch versions.
