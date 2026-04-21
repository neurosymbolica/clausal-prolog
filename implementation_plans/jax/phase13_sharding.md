# Phase 13 — Sharding and Devices

JAX treats device placement and sharding as first-class values:
`Device`, `Mesh`, `PartitionSpec`, `NamedSharding`. These are
immutable, comparable, and enumerable — a natural relational fit.
This phase exposes them.

**File to create:** `clausal/modules/py/jax_sharding.py`

**Depends on:** Phase 1 — `clausal/modules/py/jax.py` for lazy import.
Does not depend on pytrees or transforms.

---

## Predicates

### Device enumeration

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `jax_device` | `/1` | `(-D)`, `(+D)` | pure | yes | Enumerate or check visible devices |
| `local_device` | `/1` | `(-D)`, `(+D)` | pure | yes | Enumerate locally-addressable devices |
| `device_count` | `/1` | `(-N)` | pure | no | Total device count |
| `local_device_count` | `/1` | `(-N)` | pure | no | Local device count |
| `device_id` | `/2` | `(+D, -ID)`, `(-D, +ID)` | pure | partial | Device ↔ numeric id |
| `device_platform` | `/2` | `(+D, -P)` | pure | no | Platform string: `"cpu"`, `"gpu"`, `"tpu"` |

### Mesh construction

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `make_mesh` | `/3` | `(+SHAPE, +AXIS_NAMES, -MESH)` | pure | `jax.make_mesh` |
| `mesh_shape` | `/2` | `(+MESH, -SHAPE)` | pure | OrderedDict of axis names to sizes |
| `mesh_axis_names` | `/2` | `(+MESH, -NAMES)` | pure | Tuple of axis names |
| `mesh_devices` | `/2` | `(+MESH, -DEVS)` | pure | Array of devices in the mesh |

### Partition specs and shardings

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `partition_spec` | `/2` | `(+AXES, -P)` | pure | Build `PartitionSpec(*axes)` |
| `named_sharding` | `/3` | `(+MESH, +P, -SHARDING)` | pure | Build `NamedSharding(mesh, p)` |
| `single_device_sharding` | `/2` | `(+DEV, -SHARDING)` | pure | Build `SingleDeviceSharding(dev)` |

### Array placement and queries

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `sharding` | `/2` | `(+A, -S)`, `(+A, +S)` check (string repr) | pure | Array's sharding |
| `device_of` | `/2` | `(+A, -D)` | pure | Array's device (for single-device arrays) |
| `device_put` | `/3` | `(+A, +DEVICE_OR_SHARDING, -A2)` | pure | Place array on device / sharding |

### Check predicates

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `is_committed` | `/1` | `(+A)` | pure | Check `arr.committed` |
| `is_fully_addressable` | `/1` | `(+A)` | pure | Check `arr.is_fully_addressable` |
| `is_deleted` | `/1` | `(+A)` | pure | Check `arr.is_deleted` |

---

## Context and Reference Patterns

### File structure

Mirror `torch_nn.py`. Lazy import JAX and pull submodules as-needed:

```python
from clausal.modules.py.jax import _ensure_jax, _jx

def _jsh():
    _ensure_jax()
    import jax.sharding as _m
    return _m
```

### Device enumeration — nondeterministic fact pattern

Same idea as Phase 9's `leaf/2` or Phase 2's `sampler/2`: iterate and
yield with `trail.mark()`/`trail.undo()`:

```python
def _jax_device_1(this_generator, _proceed, _fail, _catcher, dev_var, trail):
    devices = _jx().devices()
    d = deref(dev_var)
    if is_var(d):
        for dev in devices:
            mark = trail.mark()
            if unify(dev_var, dev, trail):
                yield (_proceed, None)
            trail.undo(mark)
    else:
        # Check mode
        if d in devices:
            yield (_proceed, None)
    yield (_fail, DONE)

jax_device = _pred("jax_device", (1, _jax_device_1))
```

`local_device/1` is identical but uses `jax.local_devices()`.

### `make_mesh` — convert tuples

`jax.make_mesh(shape, axis_names)` expects a tuple for shape and a
tuple of strings for axes. Lists from Clausal should be converted:

```python
make_mesh = _pred("make_mesh",
    (3, _pure(lambda shape, axes: _jx().make_mesh(tuple(shape), tuple(axes)))),
)
```

### `partition_spec` — variadic axes

`PartitionSpec(*axes)` takes any number of axis names or `None`. The
Clausal form passes a list:

```python
partition_spec = _pred("partition_spec",
    (2, _pure(lambda axes: _jsh().PartitionSpec(*axes))),
)
```

Axes can include `None` for unsharded dims — pass through. If the user
needs `None`, they write `none` in Clausal and `_deep_deref` resolves
to Python `None`.

### `named_sharding`

```python
named_sharding = _pred("named_sharding",
    (3, _pure(lambda mesh, p: _jsh().NamedSharding(mesh, p))),
)
```

### `device_put` — accepts device or sharding

JAX's `jax.device_put(x, device)` accepts either a `Device` or a
`Sharding`. Pass-through:

```python
device_put = _pred("device_put",
    (3, _pure(lambda a, dev_or_sh: _jx().device_put(a, dev_or_sh))),
)
```

### `sharding/2` — string representation for check mode

Sharding objects don't compare cleanly across constructions. For query
mode return the sharding object; for check mode, stringify both sides:

```python
def _sharding_2(this_generator, _proceed, _fail, _catcher, arr_var, s_var, trail):
    a = deref(arr_var)
    s = deref(s_var)
    try:
        actual = a.sharding
    except Exception:
        yield (_fail, DONE)
        return
    if is_var(s):
        if unify(s_var, actual, trail):
            yield (_proceed, None)
    else:
        # String-equality check
        if repr(actual) == repr(s) or actual == s:
            yield (_proceed, None)
    yield (_fail, DONE)
```

### Device as a string — separate from full Device object

Phase 1 defined `device/2` to return a string. This phase exposes full
`Device` objects via `device_of/2` for power users. The string form
stays for compatibility and simple equality checks.

---

## Example Usage

```clausal
-import_from(py.jax, [array, ones, shape])
-import_from(py.jax_sharding, [jax_device, local_device,
                                device_count, device_platform,
                                make_mesh, partition_spec,
                                named_sharding, sharding, device_of,
                                device_put,
                                is_committed, is_fully_addressable])
-import_module(jax)

Test("enumerate devices") <- (
    findall(D, jax_device(D), DS),
    length(DS, N),
    N >= 1
)

Test("device_count matches enumeration") <- (
    findall(D, jax_device(D), DS),
    length(DS, N),
    device_count(M),
    N == M
)

Test("device platform on CPU") <- (
    jax_device(D),
    device_platform(D, "cpu"),
    !
)

Test("make a mesh") <- (
    make_mesh([1], ["x"], MESH),
    mesh_axis_names(MESH, ("x",))
)

Test("build partition spec") <- (
    partition_spec(["x"], P),
    S is ++(str(P)),
    S == "P('x',)"
)

Test("build named sharding") <- (
    make_mesh([1], ["x"], MESH),
    partition_spec(["x"], P),
    named_sharding(MESH, P, S),
    # S is a NamedSharding; just verify construction succeeds
    not(S == _)
)

Test("device_put preserves values") <- (
    array([1.0, 2.0, 3.0], A),
    jax_device(D),
    device_put(A, D, A2),
    shape(A2, [3]),
    device_of(A2, D)
)

Test("is_fully_addressable on local array") <- (
    array([1.0, 2.0, 3.0], A),
    is_fully_addressable(A)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_sharding_tests.clausal`):

- Device enumeration: `findall`, check mode, count consistency
- Mesh construction with 1-d shape (always works on CPU)
- PartitionSpec construction with `None` unsharded dim
- NamedSharding construction
- `device_put` with device and with sharding
- Check predicates (`is_committed`, `is_fully_addressable`,
  `is_deleted`) on freshly-created arrays
- `sharding/2` in query mode; check mode via `repr` equality

**Python unit tests:**
- Mesh construction with various shapes (1-d, 2-d)
- `device_put` with a `NamedSharding` constructed via predicate

---

## Docs

Create `docs/jax_sharding.md`:
- Overview: JAX's sharding model — meshes, partition specs,
  named shardings
- Device enumeration as a Clausal-friendly relation
- Mesh construction and inspection
- `device_put` with a device and with a sharding
- Check predicates for array state
- Relational examples: "find a sharding where axis 0 is named 'data'"
- All examples backed by `.clausal` tests

---

## Issues

_To be populated during implementation._

Known items to validate:

1. **Multi-host sharding.** `pmap`, `shard_map`, and global-host
   meshes are out of scope for this phase. A single-host multi-device
   test is enough; multi-host is a production deployment concern.

2. **`PartitionSpec` with `None`.** `None` means "unsharded over this
   axis". Clausal user must pass `none` which `_deep_deref` resolves
   to Python `None`. Verify.

3. **Mesh axis name atoms.** Mesh axis names are Python strings in
   JAX. Clausal atoms and strings unify — test that
   `make_mesh([2], ["data"], ...)` works with both `"data"` and `data`
   depending on how the user writes it.

4. **Sharding equality.** Two `NamedSharding` instances built from
   equal meshes and equal specs should compare equal with `==`. If not,
   fall back to `repr` equality. Tests prefer `repr` for robustness.

5. **`device_put` may be async.** Under some backends the operation
   returns before the transfer finishes. `block_until_ready(arr)` can
   force completion; add it as an impure helper if needed.

6. **On CPU-only hosts, `pmap`-related predicates are no-ops.**
   Out of scope for Phase 13 — tracked for a later phase once
   multi-device testing infrastructure exists.
