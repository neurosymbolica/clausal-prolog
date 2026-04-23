"""clausal.modules.py.jax_sharding — JAX device placement and sharding.

JAX treats device placement and sharding as first-class *values*:
``Device``, ``Mesh``, ``PartitionSpec``, ``NamedSharding``. They are
immutable, comparable, and enumerable — a natural relational fit.
This module exposes them as Clausal predicates.

Import usage::

    -import_from(py.jax_sharding, [
        jax_device, local_device,
        device_count, local_device_count,
        device_id, device_platform, device_of,
        make_mesh, mesh_shape, mesh_axis_names, mesh_devices,
        partition_spec, named_sharding, single_device_sharding,
        sharding, device_put,
        is_committed, is_fully_addressable, is_deleted,
    ])

Phase 13 — Sharding and Devices
---------------------------------
All predicates are Tier 1 pure (``device_put`` physically copies data
but returns a new array — the original is untouched, as with every
other JAX value-level operation).

Device enumeration (nondeterministic):
    jax_device(D)                    Each globally-visible device
    local_device(D)                  Each locally-addressable device
    device_count(N)                  Total device count
    local_device_count(N)            Local device count
    device_id(D, ID)                 Device ↔ numeric id
    device_platform(D, P)            Platform string ("cpu", "gpu", "tpu")
    device_of(A, D)                  Array's device (for single-device arrays)

Mesh construction and inspection:
    make_mesh(SHAPE, AXES, MESH)     jax.make_mesh
    mesh_shape(MESH, SHAPE)          OrderedDict of axis → size
    mesh_axis_names(MESH, NAMES)     Tuple of axis names
    mesh_devices(MESH, DEVS)         Device array backing the mesh

Partition specs and shardings:
    partition_spec(AXES, P)                       PartitionSpec(*axes);
                                                  bidirectional — backward
                                                  recovers AXES via list(p)
                                                  (None entries preserved)
    named_sharding(MESH, P, S)                    NamedSharding(mesh, p)
    single_device_sharding(DEV, S)                SingleDeviceSharding(dev)

Array placement and queries:
    sharding(A, S)                   Query (+A,-S) or check (+A,+S)
    device_put(A, DEV_OR_SHARDING, A2)
                                     Place on a Device or Sharding
                                     object. A numeric index won't
                                     work — use `device_id(D, ID)` to
                                     resolve id → Device first.

Check predicates (boolean):
    is_committed(A)                  arr.committed
    is_fully_addressable(A)          arr.is_fully_addressable
    is_deleted(A)                    arr.is_deleted()  — note it's a method

Design notes
------------
* ``Device``, ``Mesh``, ``PartitionSpec``, ``NamedSharding`` are all
  passed through unchanged. They compare sensibly with ``==`` (same
  spec + same mesh → equal NamedSharding), so Clausal unification
  works at face value.
* ``sharding/2`` uses a two-step check — first try ``actual == want``,
  then fall back to ``repr(actual) == repr(want)`` in case a user
  constructs an equivalent-but-not-identical NamedSharding via ``++()``.
* ``is_deleted`` in JAX is a *method*, not a property. The wrapper
  calls it.
* On a single-device CPU host (the CI default), ``make_mesh([2], ...)``
  fails with ``ValueError`` — JAX needs at least that many devices.
  Tests use ``[1]``.
"""

from __future__ import annotations

import threading as _threading

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _bidir_2, _check_1, _deep_deref
from clausal.modules.py.jax import _ensure_jax, _jx
from clausal.terms import DictTerm


# ── Lazy jax.sharding import ──────────────────────────────────────────────

_jsh_mod = None
_jsh_lock = _threading.Lock()


def _jsh():
    global _jsh_mod
    if _jsh_mod is not None:
        return _jsh_mod
    with _jsh_lock:
        if _jsh_mod is not None:
            return _jsh_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jsh_mod = _import_stdlib("jax.sharding")
    return _jsh_mod


# ═══════════════════════════════════════════════════════════════════════════
# Device enumeration — nondeterministic
# ═══════════════════════════════════════════════════════════════════════════

def _enumerate_devices(getter):
    """Build a dispatch function that enumerates devices from `getter()`.

    Thin spot: check mode uses Python's `in`, which is O(n) over the
    device list. Negligible on real host sizes (even a 256-TPU pod is
    a one-time membership test) but worth knowing.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, dev_var, trail):
        devices = getter()
        d = deref(dev_var)
        if is_var(d):
            for dev in devices:
                mark = trail.mark()
                if unify(dev_var, dev, trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            if d in devices:
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


jax_device = _pred("jax_device",
    (1, _enumerate_devices(lambda: _jx().devices())),
)

local_device = _pred("local_device",
    (1, _enumerate_devices(lambda: _jx().local_devices())),
)

device_count = _pred("device_count",
    (1, _pure(lambda: _jx().device_count())),
)

local_device_count = _pred("local_device_count",
    (1, _pure(lambda: _jx().local_device_count())),
)


def _device_id_2(this_generator, _proceed, _fail, _catcher, dev_var, id_var, trail):
    d = deref(dev_var)
    i = deref(id_var)
    if not is_var(d):
        actual = d.id
        if is_var(i):
            if unify(id_var, actual, trail):
                yield (_proceed, None)
        else:
            if actual == i:
                yield (_proceed, None)
    elif not is_var(i):
        # Reverse lookup: find the device with that id. Thin spot:
        # this assumes device ids are unique on a given host (JAX's own
        # guarantee — https://docs.jax.dev/en/latest/api.html#jax.Device).
        # `break` after a match means we won't enumerate if that
        # guarantee ever weakens.
        for dev in _jx().devices():
            if dev.id == i:
                if unify(dev_var, dev, trail):
                    yield (_proceed, None)
                break
    else:
        # Both unbound — enumerate (device, id) pairs.
        for dev in _jx().devices():
            mark = trail.mark()
            if unify(dev_var, dev, trail) and unify(id_var, dev.id, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


device_id = _pred("device_id", (2, _device_id_2))


device_platform = _pred("device_platform",
    (2, _pure(lambda d: d.platform)),
)


# device_of works for single-device arrays. On multi-device sharded
# arrays, `arr.device` raises or returns a set — the caller sees
# predicate failure and should query `sharding/2` instead.
device_of = _pred("device_of",
    (2, _pure(lambda a: a.device)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Mesh construction and inspection
# ═══════════════════════════════════════════════════════════════════════════

make_mesh = _pred("make_mesh",
    (3, _pure(lambda shape, axes:
              _jx().make_mesh(tuple(shape), tuple(axes)))),
)

# Return a DictTerm so check-mode works with Clausal dict literals —
# e.g. `mesh_shape(MESH, {"x": 1})` unifies correctly. Clausal's dict
# syntax compiles to DictTerm, and unify(plain_dict, DictTerm) is
# False even when contents match, so wrapping the return is necessary.
# Users can still reach through with `S["x"]` (DictTerm supports
# `__getitem__`) and iterate with Python idioms under `++()`. JAX's own
# `mesh.shape` is an OrderedDict; the conversion preserves iteration
# order for modern Python (3.7+) where dict order is guaranteed.
mesh_shape = _pred("mesh_shape",
    (2, _pure(lambda m: DictTerm(dict(m.shape)))),
)

mesh_axis_names = _pred("mesh_axis_names",
    (2, _pure(lambda m: m.axis_names)),
)

# `mesh.devices` is a numpy ndarray of Device objects. Flatten and cast
# to a plain list so `findall(D, ..., DS)` and list-pattern matching
# ([D | _]) work naturally. For multi-dim meshes the flatten preserves
# row-major order, matching JAX's own iteration convention.
mesh_devices = _pred("mesh_devices",
    (2, _pure(lambda m: list(m.devices.flatten()))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Partition specs and shardings
# ═══════════════════════════════════════════════════════════════════════════
#
# PartitionSpec is variadic: PartitionSpec("x"), PartitionSpec("x", None),
# PartitionSpec(None, "y"). Users pass a list of axis names (strings)
# or None entries for unsharded dimensions.

# Bidirectional: forward constructs PartitionSpec(*axes); backward
# recovers the axes list via list(p). PartitionSpec is tuple-like so
# list(p) yields [axis_or_None, ...] in order — enough for a structural
# check against the original axes list.
partition_spec = _pred("partition_spec",
    (2, _bidir_2(
        lambda axes: _jsh().PartitionSpec(*axes),
        lambda p: list(p),
    )),
)

named_sharding = _pred("named_sharding",
    (3, _pure(lambda mesh, p: _jsh().NamedSharding(mesh, p))),
)

# Thin spot: `single_device_sharding/2` is tested for construction and
# for placement via `device_put`, but not separately for
# sharding-equality (two SDSes over the same device comparing equal).
# On JAX 0.10 we've verified `SDS(d) == SDS(d)` → True, so check-mode
# with `sharding/2` should work — just not covered by an explicit test.
# Add one if this path becomes load-bearing for user code.
single_device_sharding = _pred("single_device_sharding",
    (2, _pure(lambda dev: _jsh().SingleDeviceSharding(dev))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Array placement and queries
# ═══════════════════════════════════════════════════════════════════════════

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
        # Try direct ==, then fall back to repr equality.
        try:
            ok = bool(actual == s)
        except Exception:
            ok = False
        if not ok:
            ok = repr(actual) == repr(s)
        if ok:
            yield (_proceed, None)
    yield (_fail, DONE)


sharding = _pred("sharding", (2, _sharding_2))


device_put = _pred("device_put",
    (3, _pure(lambda a, dev_or_sh: _jx().device_put(a, dev_or_sh))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Check predicates — boolean attributes
# ═══════════════════════════════════════════════════════════════════════════

is_committed = _pred("is_committed",
    (1, _check_1(lambda a: bool(a.committed))),
)

is_fully_addressable = _pred("is_fully_addressable",
    (1, _check_1(lambda a: bool(a.is_fully_addressable))),
)

# is_deleted is a method in modern JAX, not a property — call it.
is_deleted = _pred("is_deleted",
    (1, _check_1(lambda a: bool(a.is_deleted()))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Device enumeration
    "jax_device", "local_device",
    "device_count", "local_device_count",
    "device_id", "device_platform", "device_of",
    # Mesh
    "make_mesh", "mesh_shape", "mesh_axis_names", "mesh_devices",
    # Partition / sharding constructors
    "partition_spec", "named_sharding", "single_device_sharding",
    # Placement / queries
    "sharding", "device_put",
    # Check predicates
    "is_committed", "is_fully_addressable", "is_deleted",
]
