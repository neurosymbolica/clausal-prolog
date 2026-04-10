"""clausal.modules.py.torch — PyTorch tensor predicates for Clausal.

Provides pure tensor operations from PyTorch as importable predicate objects
for use in .clausal files via::

    -import_from(py.torch, [tensor, zeros, ones, randn, shape, dtype, device,
                             reshape, matmul, add, relu, softmax,
                             tensor_numpy, tensor_list, float32, float64,
                             det, inv, svd, solve, cholesky, qr, norm])

Phase 1 — Tensor Core
----------------------
All predicates in this phase are Tier 1 (pure, no state).

Tensor creation:
    tensor(DATA, T)                         Create tensor from list/nested list
    zeros(SHAPE, T)  /  zeros(SHAPE, OPTS, T)   Zero tensor; OPTS dict for dtype/device
    ones(SHAPE, T)   /  ones(SHAPE, OPTS, T)    Ones tensor
    randn(SHAPE, T)  /  randn(SHAPE, OPTS, T)   Normal random tensor
    arange(END, T)   /  arange(START, END, T)  /  arange(START, END, STEP, T)
    linspace(START, END, STEPS, T)  /  linspace(START, END, STEPS, OPTS, T)
    full(SHAPE, VALUE, T)  /  full(SHAPE, VALUE, OPTS, T)
    eye(N, T)  /  eye(N, M, T)

Tensor properties (multi-mode):
    shape(T, S)             (+T,-S) query or (+T,+S) check
    dtype(T, D)             (+T,-D) query or (+T,+D) check
    device(T, D)            (+T,-D) query or (+T,+D) check
    dim(T, N)               (+T,-N) query
    element_count(T, N)     (+T,-N) query
    requires_gradient(T, B) (+T,-B) query

Tensor math:
    matmul(A, B, C)         Matrix multiply
    add(A, B, C)            Element-wise add
    mul(A, B, C)            Element-wise multiply
    cat(TENSORS, DIM, T)    Concatenate along dim
    stack(TENSORS, DIM, T)  Stack along new dim
    sum(T, S)  /  sum(T, DIM, S)       Sum reduction
    mean(T, M)  /  mean(T, DIM, M)     Mean reduction
    max(T, M)  /  max(T, DIM, M)       Max reduction
    min(T, M)  /  min(T, DIM, M)       Min reduction
    clamp(T, MIN, MAX, T2)  Clamp values
    abs(T, T2)              Absolute value
    softmax(T, DIM, T2)     Softmax
    relu(T, T2)             ReLU activation

Shape operations:
    reshape(T, SHAPE, T2)           Reshape tensor
    squeeze(T, T2)  /  squeeze(T, DIM, T2)   Remove size-1 dims
    unsqueeze(T, DIM, T2)           Add size-1 dim
    flatten(T, T2)  /  flatten(T, START, END, T2)   Flatten dims
    unflatten(T, DIM, SHAPE, T2)    Unflatten dim
    transpose(T, D0, D1, T2)        Swap two dims
    permute(T, DIMS, T2)            Reorder all dims
    contiguous(T, T2)               Make memory contiguous

Conversions (bijective):
    tensor_numpy(TENSOR, ARRAY)  Tensor <-> numpy (bidirectional, shared memory)
    tensor_list(TENSOR, LIST)    Tensor <-> nested list (bidirectional, copies)

Phase 4 — Linear Algebra
-------------------------
Pure tensor linear algebra via torch.linalg.

    det(A, D)                    Determinant
    inv(A, B)                    Matrix inverse (self-inverse)
    solve(A, B, X)               Solve AX = B
    svd(A, RESULT)               SVD → (U, S, Vh) tuple
    eig(A, RESULT)               Eigendecomposition → (L, V) tuple
    cholesky(A, L)               Cholesky decomposition
    qr(A, RESULT)                QR decomposition → (Q, R) tuple
    norm(A, N) / norm(A, ORD, N) Matrix/vector norm
    matrix_rank(A, R)            Matrix rank
    pinv(A, B)                   Moore-Penrose pseudoinverse
    cross(A, B, C)               Cross product
    dot(A, B, C)                 Dot product
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Lazy torch import ────────────────────────────────────────────────────

_torch = None
_torch_lock = _threading.Lock()


def _ensure_torch():
    global _torch
    if _torch is not None:
        return
    with _torch_lock:
        if _torch is not None:
            return
        from clausal.modules.py import _import_stdlib
        _torch = _import_stdlib("torch")


def _th():
    _ensure_torch()
    return _torch


# ── Dispatch helpers ─────────────────────────────────────────────────────

def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


def _deep_deref(val):
    """Deref a value, recursively deref-ing list elements and dict values."""
    val = deref(val)
    if isinstance(val, list):
        return [_deep_deref(x) for x in val]
    if isinstance(val, dict):
        return {k: _deep_deref(v) for k, v in val.items()}
    return val


def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deep-deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [_deep_deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (parent, DONE)
            return
        if unify(result_var, out, trail):
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _property_2(getter):
    """Multi-mode property predicate: query (+T,-V) or check (+T,+V)."""
    def dispatch(this_generator, parent, tensor_var, value_var, trail):
        t = deref(tensor_var)
        v = deref(value_var)
        try:
            actual = getter(t)
        except Exception:
            yield (parent, DONE)
            return
        if is_var(v):
            # Query mode: unify value_var with actual
            if unify(value_var, actual, trail):
                yield (parent, None)
        else:
            # Check mode: succeed if values match
            if actual == v:
                yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _bidir_2(forward, backward):
    """Bidirectional predicate: (+X,-Y) forward, (-X,+Y) backward, (+X,+Y) check."""
    def dispatch(this_generator, parent, x_raw, y_raw, trail):
        x = deref(x_raw)
        y = deref(y_raw)

        if not is_var(x) and is_var(y):
            try:
                out = forward(x)
            except Exception:
                yield (parent, DONE)
                return
            if unify(y_raw, out, trail):
                yield (parent, None)

        elif is_var(x) and not is_var(y):
            try:
                out = backward(y)
            except Exception:
                yield (parent, DONE)
                return
            if unify(x_raw, out, trail):
                yield (parent, None)

        elif not is_var(x) and not is_var(y):
            # Both ground: check via forward
            try:
                out = forward(x)
                if unify(y_raw, out, trail):
                    yield (parent, None)
            except Exception:
                pass

        # Both unbound: fail
        yield (parent, DONE)
    return dispatch


# ═══════════════════════════════════════════════════════════════════════════
# Tensor creation
# ═══════════════════════════════════════════════════════════════════════════

tensor = _pred("tensor",
    (2, _pure(lambda data: _th().tensor(data))),
)

zeros = _pred("zeros",
    (2, _pure(lambda shape: _th().zeros(shape))),
    (3, _pure(lambda shape, opts: _th().zeros(shape, **opts))),
)

ones = _pred("ones",
    (2, _pure(lambda shape: _th().ones(shape))),
    (3, _pure(lambda shape, opts: _th().ones(shape, **opts))),
)

randn = _pred("randn",
    (2, _pure(lambda shape: _th().randn(shape))),
    (3, _pure(lambda shape, opts: _th().randn(shape, **opts))),
)

arange = _pred("arange",
    (2, _pure(lambda end: _th().arange(end))),
    (3, _pure(lambda start, end: _th().arange(start, end))),
    (4, _pure(lambda start, end, step: _th().arange(start, end, step))),
)

linspace = _pred("linspace",
    (4, _pure(lambda start, end, steps: _th().linspace(start, end, int(steps)))),
    (5, _pure(lambda start, end, steps, opts:
              _th().linspace(start, end, int(steps), **opts))),
)

full = _pred("full",
    (3, _pure(lambda shape, value: _th().full(shape, value))),
    (4, _pure(lambda shape, value, opts: _th().full(shape, value, **opts))),
)

eye = _pred("eye",
    (2, _pure(lambda n: _th().eye(int(n)))),
    (3, _pure(lambda n, m: _th().eye(int(n), int(m)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tensor properties (multi-mode)
# ═══════════════════════════════════════════════════════════════════════════

shape = _pred("shape",
    (2, _property_2(lambda t: list(t.shape))),
)

dtype = _pred("dtype",
    (2, _property_2(lambda t: t.dtype)),
)

device = _pred("device",
    (2, _property_2(lambda t: str(t.device))),
)

dim = _pred("dim",
    (2, _pure(lambda t: t.dim())),
)

element_count = _pred("element_count",
    (2, _pure(lambda t: t.numel())),
)

requires_gradient = _pred("requires_gradient",
    (2, _pure(lambda t: t.requires_grad)),
)


def _check_1(predicate_fn):
    """Predicate that succeeds if predicate_fn(tensor) is truthy, fails otherwise."""
    def dispatch(this_generator, parent, tensor_var, trail):
        t = deref(tensor_var)
        try:
            if predicate_fn(t):
                yield (parent, None)
        except Exception:
            pass
        yield (parent, DONE)
    return dispatch


is_contiguous = _pred("is_contiguous",
    (1, _check_1(lambda t: t.is_contiguous())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tensor math
# ═══════════════════════════════════════════════════════════════════════════

matmul = _pred("matmul",
    (3, _pure(lambda a, b: _th().matmul(a, b))),
)

add = _pred("add",
    (3, _pure(lambda a, b: _th().add(a, b))),
)

mul = _pred("mul",
    (3, _pure(lambda a, b: _th().mul(a, b))),
)

cat = _pred("cat",
    (3, _pure(lambda tensors, dim: _th().cat(tensors, int(dim)))),
)

stack = _pred("stack",
    (3, _pure(lambda tensors, dim: _th().stack(tensors, int(dim)))),
)


def _reduction_dispatches(torch_fn_name):
    """Create arity-2 (full) and arity-3 (along dim) dispatches for reductions."""
    def full_reduce(t):
        return getattr(_th(), torch_fn_name)(t)
    def dim_reduce(t, dim):
        result = getattr(_th(), torch_fn_name)(t, int(dim))
        # torch.max/min along dim return (values, indices) namedtuple
        if isinstance(result, tuple):
            return result[0]  # return values only
        return result
    return (
        (2, _pure(full_reduce)),
        (3, _pure(dim_reduce)),
    )

# sum is a Python builtin — the module-scoped import prevents collision
sum = _pred("sum", *_reduction_dispatches("sum"))
mean = _pred("mean", *_reduction_dispatches("mean"))
max = _pred("max", *_reduction_dispatches("max"))
min = _pred("min", *_reduction_dispatches("min"))

clamp = _pred("clamp",
    (4, _pure(lambda t, lo, hi: _th().clamp(t, float(lo), float(hi)))),
)

abs = _pred("abs",
    (2, _pure(lambda t: _th().abs(t))),
)

softmax = _pred("softmax",
    (3, _pure(lambda t, dim: _th().nn.functional.softmax(t, dim=int(dim)))),
)

relu = _pred("relu",
    (2, _pure(lambda t: _th().nn.functional.relu(t))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Shape operations
# ═══════════════════════════════════════════════════════════════════════════

reshape = _pred("reshape",
    (3, _pure(lambda t, shape: t.reshape(shape))),
)

squeeze = _pred("squeeze",
    (2, _pure(lambda t: t.squeeze())),
    (3, _pure(lambda t, dim: t.squeeze(int(dim)))),
)

unsqueeze = _pred("unsqueeze",
    (3, _pure(lambda t, dim: t.unsqueeze(int(dim)))),
)

flatten = _pred("flatten",
    (2, _pure(lambda t: t.flatten())),
    (4, _pure(lambda t, start, end: t.flatten(int(start), int(end)))),
)

unflatten = _pred("unflatten",
    (4, _pure(lambda t, dim, shape: t.unflatten(int(dim), shape))),
)

transpose = _pred("transpose",
    (4, _pure(lambda t, d0, d1: t.transpose(int(d0), int(d1)))),
)

permute = _pred("permute",
    (3, _pure(lambda t, dims: t.permute(dims))),
)

contiguous = _pred("contiguous",
    (2, _pure(lambda t: t.contiguous())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Conversions (bijective)
# ═══════════════════════════════════════════════════════════════════════════

tensor_numpy = _pred("tensor_numpy",
    (2, _bidir_2(
        lambda t: t.detach().numpy(),
        lambda a: _th().from_numpy(a),
    )),
)

tensor_list = _pred("tensor_list",
    (2, _bidir_2(
        lambda t: t.tolist(),
        lambda l: _th().tensor(l),
    )),
)


# ═══════════════════════════════════════════════════════════════════════════
# Dtype info (fact table)
# ═══════════════════════════════════════════════════════════════════════════

def _dtype_properties(dt):
    """Return a dict of properties for a torch dtype."""
    t = _th()
    info = {
        "bits": dt.itemsize * 8 if hasattr(dt, "itemsize") else
                t.tensor([], dtype=dt).element_size() * 8,
        "is_floating_point": t.is_floating_point(t.tensor([], dtype=dt)),
        "is_complex": t.is_complex(t.tensor([], dtype=dt)),
    }
    return info


def _dtype_info_3(this_generator, parent, dtype_var, key_var, value_var, trail):
    dt = deref(dtype_var)
    k = deref(key_var)
    v = deref(value_var)

    if is_var(dt):
        # dtype unbound: fail (too many dtypes to enumerate usefully)
        yield (parent, DONE)
        return

    try:
        props = _dtype_properties(dt)
    except Exception:
        yield (parent, DONE)
        return

    if not is_var(k):
        # Key bound: look up single property
        val = props.get(k)
        if val is not None and unify(value_var, val, trail):
            yield (parent, None)
    else:
        # Key unbound: enumerate all properties
        for key, val in props.items():
            mark = trail.mark()
            if unify(key_var, key, trail) and unify(value_var, val, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


dtype_info = _pred("dtype_info",
    (3, _dtype_info_3),
)


# ═══════════════════════════════════════════════════════════════════════════
# IO (impure)
# ═══════════════════════════════════════════════════════════════════════════

def _save_2(this_generator, parent, obj_var, path_var, trail):
    obj = deref(obj_var)
    path = str(deref(path_var))
    try:
        _th().save(obj, path)
    except Exception:
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)


def _load_2(this_generator, parent, path_var, result_var, trail):
    path = str(deref(path_var))
    try:
        obj = _th().load(path, weights_only=True)
    except Exception:
        yield (parent, DONE)
        return
    if unify(result_var, obj, trail):
        yield (parent, None)
    yield (parent, DONE)


save = _pred("save",
    (2, _save_2),
)

load = _pred("load",
    (2, _load_2),
)


# ═══════════════════════════════════════════════════════════════════════════
# Linear algebra (Phase 4)
# ═══════════════════════════════════════════════════════════════════════════

det = _pred("det",
    (2, _pure(lambda a: _th().linalg.det(a))),
)

inv = _pred("inv",
    (2, _pure(lambda a: _th().linalg.inv(a))),
)

solve = _pred("solve",
    (3, _pure(lambda a, b: _th().linalg.solve(a, b))),
)

svd = _pred("svd",
    (2, _pure(lambda a: tuple(_th().linalg.svd(a)))),
)

eig = _pred("eig",
    (2, _pure(lambda a: tuple(_th().linalg.eig(a)))),
)

cholesky = _pred("cholesky",
    (2, _pure(lambda a: _th().linalg.cholesky(a))),
)

qr = _pred("qr",
    (2, _pure(lambda a: tuple(_th().linalg.qr(a)))),
)

norm = _pred("norm",
    (2, _pure(lambda a: _th().linalg.norm(a))),
    (3, _pure(lambda a, ord: _th().linalg.norm(a, ord=ord))),
)

matrix_rank = _pred("matrix_rank",
    (2, _pure(lambda a: _th().linalg.matrix_rank(a))),
)

pinv = _pred("pinv",
    (2, _pure(lambda a: _th().linalg.pinv(a))),
)

cross = _pred("cross",
    (3, _pure(lambda a, b: _th().linalg.cross(a, b))),
)

dot = _pred("dot",
    (3, _pure(lambda a, b: _th().dot(a, b))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Dtype constants (re-exported from torch for direct import)
# ═══════════════════════════════════════════════════════════════════════════

def _export_dtypes():
    _ensure_torch()
    t = _torch
    return {
        "float16": t.float16, "float32": t.float32, "float64": t.float64,
        "bfloat16": t.bfloat16,
        "int8": t.int8, "int16": t.int16, "int32": t.int32, "int64": t.int64,
        "uint8": t.uint8,
        "bool": t.bool,
        "complex64": t.complex64, "complex128": t.complex128,
    }

# Populate module-level dtype names lazily on first access via __getattr__
_DTYPE_CACHE = None

def __getattr__(name):
    global _DTYPE_CACHE
    if _DTYPE_CACHE is None:
        _DTYPE_CACHE = _export_dtypes()
    if name in _DTYPE_CACHE:
        return _DTYPE_CACHE[name]
    raise AttributeError(f"module 'clausal.modules.py.torch' has no attribute {name!r}")


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Creation
    "tensor", "zeros", "ones", "randn", "arange", "linspace", "full", "eye",
    # Properties
    "shape", "dtype", "device", "dim", "element_count",
    "requires_gradient", "is_contiguous",
    # Math
    "matmul", "add", "mul", "cat", "stack",
    "sum", "mean", "max", "min",
    "clamp", "abs", "softmax", "relu",
    # Shape operations
    "reshape", "squeeze", "unsqueeze", "flatten", "unflatten",
    "transpose", "permute", "contiguous",
    # Conversions
    "tensor_numpy", "tensor_list",
    # Dtype info
    "dtype_info",
    # IO (impure)
    "save", "load",
    # Linear algebra
    "det", "inv", "solve", "svd", "eig", "cholesky", "qr",
    "norm", "matrix_rank", "pinv", "cross", "dot",
    # Dtype constants
    "float16", "float32", "float64", "bfloat16",
    "int8", "int16", "int32", "int64", "uint8",
    "bool", "complex64", "complex128",
]
