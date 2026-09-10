# jax_sharding — JAX Device Placement and Sharding

JAX treats device placement as **data**: `Device`, `Mesh`,
`PartitionSpec`, `NamedSharding` are immutable, comparable, and
enumerable. Unlike PyTorch (where `.to(device)` mutates a tensor's
placement), every JAX placement operation returns a new array — the
original is untouched. That functional model plus the first-class
object-ness of devices and shardings makes for a natural relational
wrapper.

All predicates are Tier 1 pure.

## Import

```clausal
-import_module(jax)
-import_from(py.jax_sharding, [
    jax_device, local_device,
    device_count, local_device_count,
    device_id, device_platform, device_of,
    make_mesh, mesh_shape, mesh_axis_names, mesh_devices,
    partition_spec, named_sharding, single_device_sharding,
    sharding, device_put,
    is_committed, is_fully_addressable, is_deleted
])
```

---

## Device enumeration

### `jax_device(D)` and `local_device(D)`

Nondeterministic — each globally-visible (or locally-addressable)
device is a solution.

```clausal
test("jax_device enumerates devices") <- (
    findall(D, jax_device(D), DS),
    length(DS, N),
    N >= 1
)
```

`jax_device/1` covers all devices across a multi-host cluster;
`local_device/1` covers only devices this process can address
directly.

### `device_count/1` and `local_device_count/1`

Deterministic totals:

```clausal
test("count matches enumeration") <- (
    findall(D, jax_device(D), DS),
    length(DS, N),
    device_count(M),
    N == M
)
```

### `device_id(D, ID)`, `device_platform(D, P)`

`device_id/2` is bidirectional — query an id from a device, or find a
device by id. `device_platform/2` returns `"cpu"`, `"gpu"`, or `"tpu"`.

```clausal
test("device by id") <- (
    device_id(D, 0),
    device_platform(D, "cpu")
)
```

### `device_of(A, D)`

Return the device hosting a **single-device** array. Contrast with
Phase 1's `device/2` which returns a string — `device_of` returns the
full `Device` object for use with `device_put`, `device_id`, etc.

On a multi-device sharded array, JAX's underlying `arr.device` raises
or returns a set; the wrapper surfaces that as predicate failure. For
sharded arrays, query `sharding/2` instead and iterate the
sharding's own `.device_set` / `.mesh` via `++()` until a
Clausal-native multi-device helper lands.

---

## Meshes

A **mesh** is a named grid of devices. `make_mesh/3` takes a shape
tuple and a tuple of axis names:

```clausal
test("make_mesh") <- (
    make_mesh([1], ["x"], MESH),
    mesh_axis_names(MESH, ("x",))
)
```

On a single-device CPU host (the CI default), only `[1]`-shaped meshes
succeed — `make_mesh([2], ["x"], _)` raises because JAX demands at
least `shape-product` devices. Multi-device meshes need a real
multi-GPU or multi-TPU host.

Inspect mesh shape, axes, and backing devices with
`mesh_shape/2`, `mesh_axis_names/2`, `mesh_devices/2`. `mesh_shape/2`
returns an `OrderedDict` mapping axis names to sizes:

```clausal
test("mesh_shape") <- (
    make_mesh([1], ["x"], MESH),
    mesh_shape(MESH, SHAPE),
    KEYS is ++(list(SHAPE.keys())),
    KEYS == ["x"]
)
```

---

## Partition specs and shardings

### `partition_spec(AXES, P)`

Build a `PartitionSpec(*axes)`. Each axis entry is either a mesh axis
name (string) or `None` for "unsharded over this tensor dim":

```clausal
test("partition_spec") <- (
    partition_spec(["x"], P),
    S is ++(str(P)),
    S == "P('x',)"
)

test("partition_spec with unsharded dim") <- (
    partition_spec(["x", ++(None)], P),
    S is ++(str(P)),
    S == "P('x', None)"
)
```

### `named_sharding(MESH, P, S)`

Combine a mesh with a `PartitionSpec` into a `NamedSharding`:

```clausal
test("named_sharding") <- (
    make_mesh([1], ["x"], MESH),
    partition_spec(["x"], P),
    named_sharding(MESH, P, S),
    S != ++(None)
)
```

Two `NamedSharding`s built from equal meshes and equal specs compare
equal with `==`:

```clausal
test("named_sharding equality") <- (
    make_mesh([1], ["x"], M1),
    make_mesh([1], ["x"], M2),
    partition_spec(["x"], P),
    named_sharding(M1, P, S1),
    named_sharding(M2, P, S2),
    S1 == S2
)
```

### `single_device_sharding(DEV, S)`

A sharding that puts the whole array on one device — equivalent to
`device_put` with a raw `Device`, but lets you hold the sharding as a
value for reuse.

---

## Array placement

### `device_put(A, DEVICE_OR_SHARDING, A2)`

Produce a new array placed on the given device or matching the given
sharding. The second argument is a `Device` object or a `Sharding`
object — **not a numeric index**:

```clausal
test("resolve id to Device before placement") <- (
    # Correct — resolve id to a Device first
    array([1.0], A),
    device_id(D, 0),
    device_put(A, D, _A2)
)

test("numeric index fails") <- (
    # Wrong — raises TypeError, surfaced as predicate failure
    array([1.0], A),
    not device_put(A, 0, _A2)
)
```

```clausal
test("device_put to device") <- (
    array([1.0, 2.0, 3.0], A),
    jax_device(D),
    device_put(A, D, A2),
    device_of(A2, D2),
    device_id(D2, 0)
)

test("device_put with named sharding") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    make_mesh([1], ["x"], M),
    partition_spec(["x"], P),
    named_sharding(M, P, NS),
    device_put(A, NS, A2),
    shape(A2, [2, 2])
)
```

`device_put` returns a new array; the original is untouched, which is
what Clausal backtracking expects.

### `sharding(A, S)`

Query or check an array's sharding. Query mode binds `S` to the
sharding object; check mode accepts either direct `==` or `repr`
equality as a fallback:

```clausal
test("sharding query") <- (
    array([1.0, 2.0, 3.0], A),
    sharding(A, S),
    S != ++(None)
)
```

---

## Check predicates

| Predicate | Semantics |
|---|---|
| `is_committed(A)` | Succeeds iff `A.committed` is true (has been placed explicitly) |
| `is_fully_addressable(A)` | Succeeds iff all shards live on locally-addressable devices |
| `is_deleted(A)` | Succeeds iff the buffer has been freed (rare in Clausal since we don't call `.delete()`) |

`is_deleted` is a **method** in JAX, not a property — the wrapper
calls it for you, so you just write `is_deleted(A)`.

```clausal
test("fresh array is not deleted") <- (
    array([1.0, 2.0, 3.0], A),
    not is_deleted(A)
)
```

---

## Relational pattern — find a sharding with constraints

The Clausal-friendly style: treat shardings as values and query
relationally. For example, "given a mesh and some candidate
`PartitionSpec`s, find one where the first axis is named `'data'`":

```clausal
candidate_pspec(["data"]).
candidate_pspec(["data", ++(None)]).
candidate_pspec([++(None), "data"]).

data_first_sharding(MESH, S) <- (
    candidate_pspec(AXES),
    AXES is [First | _],
    First == "data",
    partition_spec(AXES, P),
    named_sharding(MESH, P, S)
)

test("find a data-first sharding") <- (
    make_mesh([1], ["data"], M),
    data_first_sharding(M, _S)
)
```

Combine with device enumeration to search for compatible placements
without writing an explicit loop.

---

## Deferred

- **Multi-host deployment.** `jax.distributed.initialize`, global
  mesh construction, cross-host sharding are production concerns not
  well-suited to relational wrapping. Out of scope for this phase.
- **`pjit` / `shard_map`.** Compilation primitives that take a
  sharding and produce a sharded-aware callable. They belong with the
  transforms in `py.jax_transforms` — revisit when there's multi-device
  testing infrastructure.
- **Async transfers.** `device_put` may return before the transfer
  completes. `jax.block_until_ready(arr)` forces completion and is
  accessible via `++()`. A dedicated predicate isn't worth it until a
  use case appears.
