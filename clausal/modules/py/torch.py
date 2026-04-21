"""clausal.modules.py.torch — PyTorch tensor predicates for Clausal.

Provides pure tensor operations from PyTorch as importable predicate objects
for use in .clausal files via::

    -import_from(py.torch, [tensor, zeros, ones, randn, shape, dtype, device,
                             reshape, matmul, add, relu, softmax,
                             tensor_numpy, tensor_list, float32, float64,
                             det, inv, svd, solve, cholesky, qr, norm,
                             fft_transform, real_fft, fft_shift,
                             eq, gt, lt, where, equal, allclose,
                             logical_and, any, all, masked_select,
                             einsum, logarithm, sine, cosine, tangent,
                             sqrt, pow, sigmoid, cumsum, cumprod])

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

Phase 8 — Additional Shape Operations
---------------------------------------
    split(T, SIZE, LIST) / split(T, SIZE, DIM, LIST)   Split into chunks
    chunk(T, N, LIST)    / chunk(T, N, DIM, LIST)      Split into N chunks
    unbind(T, DIM, LIST)                                Remove dim, return list
    narrow(T, DIM, START, LENGTH, R)                    Narrow along dimension
    expand(T, SIZES, R)                                 Broadcast to larger size
    repeat(T, REPEATS, R)                               Tile tensor
    tile(T, REPS, R)                                    Tile (numpy-style)
    flip(T, DIMS, R)                                    Reverse along dims
    roll(T, SHIFTS, R) / roll(T, SHIFTS, DIMS, R)      Circular shift

Conversions (bijective):
    tensor_numpy(TENSOR, ARRAY)  Tensor <-> numpy (bidirectional, shared memory)
    tensor_list(TENSOR, LIST)    Tensor <-> nested list (bidirectional, copies)

Phase 5 — FFT
--------------
Pure FFT operations via torch.fft.  Bijective pairs are single predicates.

    fft_transform(T, F) / fft_transform(T, DIM, F)          Complex FFT (+T,-F) / (-T,+F)
    real_fft(T, F) / real_fft(T, DIM, F)                    Real FFT (+T,-F) / (-T,+F)
    fft_transform_2d(T, F)                                   2D FFT (+T,-F) / (-T,+F)
    fft_transform_nd(T, F)                                   N-D FFT (+T,-F) / (-T,+F)
    fft_shift(T, S)                                          Shift zero-freq (+T,-S) / (-T,+S)
    fft_frequencies(N, F) / fft_frequencies(N, D, F)         DFT sample frequencies
    real_fft_frequencies(N, F) / real_fft_frequencies(N, D, F)  Real FFT sample frequencies

Phase 6 — Comparisons, Logic, and Selection
---------------------------------------------
Element-wise comparison, logical operations, and conditional selection.

Comparisons:
    eq(A, B, C)                  Element-wise equality (bool tensor)
    ne(A, B, C)                  Element-wise not-equal
    gt(A, B, C)                  Element-wise greater-than
    lt(A, B, C)                  Element-wise less-than
    ge(A, B, C)                  Element-wise greater-or-equal
    le(A, B, C)                  Element-wise less-or-equal
    equal(A, B)                  True if all elements equal (check predicate)
    allclose(A, B)               Approximate equality check
    allclose(A, B, ATOL, RTOL)   Approximate equality with tolerances

Logic:
    logical_and(A, B, C)         Element-wise AND
    logical_or(A, B, C)          Element-wise OR
    logical_not(A, B)            Element-wise NOT
    logical_xor(A, B, C)         Element-wise XOR
    any(T)  /  any(T, DIM)       Any element true (check predicate)
    all(T)  /  all(T, DIM)       All elements true (check predicate)

Selection:
    where(COND, X, Y, R)         Select from X or Y based on condition
    masked_select(T, MASK, R)    Elements where mask is true
    index_select(T, DIM, IDX, R) Select along dimension
    gather(T, DIM, IDX, R)       Gather along dimension
    scatter(T, DIM, IDX, SRC, R) Scatter src into T

Phase 7 — Einsum and Advanced Math
------------------------------------
Einstein summation and additional math operations.

Einsum:
    einsum(EQ, TENSORS, R)              Einstein summation

Bijective (inverse pairs):
    logarithm(EXP, VAL)                 exp/log bidirectional
    sine(ANGLE, VAL)                    sin/asin bidirectional
    cosine(ANGLE, VAL)                  cos/acos bidirectional
    tangent(ANGLE, VAL)                 tan/atan bidirectional

Non-bijective:
    sqrt(T, R)                          Square root
    pow(T, EXP, R)                      Element-wise power
    atan2(Y, X, R)                      Two-argument arctangent
    sinh(T, R)  cosh(T, R)  tanh(T, R)  Hyperbolic functions
    sigmoid(T, R)                        Logistic sigmoid
    log_softmax(T, DIM, R)              Log-softmax
    floor(T, R)  ceil(T, R)  round(T, R)  Rounding
    sign(T, R)                           Sign function
    cumsum(T, DIM, R)                    Cumulative sum
    cumprod(T, DIM, R)                   Cumulative product

Phase 13 — Creation Variants and Arithmetic Gaps
--------------------------------------------------
Creation variants:
    zeros_like(T, R)                     Zero tensor, same shape/dtype/device
    ones_like(T, R)                      Ones tensor, same shape/dtype/device
    full_like(T, VALUE, R)               Filled tensor, same shape/dtype/device
    empty(SHAPE, T) / empty(SHAPE, OPTS, T)  Uninitialized tensor
    rand(SHAPE, T)  / rand(SHAPE, OPTS, T)   Uniform random [0, 1)
    randint(LOW, HIGH, SHAPE, T) / with OPTS Random integers
    logspace(START, END, STEPS, T) / with OPTS  Logarithmically spaced
    diag(T, R)  /  diag(T, DIAGONAL, R)  Create diagonal or extract diagonal

Arithmetic gaps:
    sub(A, B, C)                         Element-wise subtract
    div(A, B, C)                         Element-wise divide
    neg(T, R)                            Element-wise negate

Phase 14 — Statistics and Selection
-------------------------------------
Statistical reductions:
    median(T, M)  /  median(T, DIM, M)   Median (dim variant returns (values, indices) tuple)
    std(T, S)     /  std(T, DIM, S)      Standard deviation
    var(T, V)     /  var(T, DIM, V)      Variance

Selection and sorting:
    argmin(T, I)  /  argmin(T, DIM, I)   Index of minimum
    argmax(T, I)  /  argmax(T, DIM, I)   Index of maximum
    sort(T, R)    /  sort(T, DIM, R)     Sort (returns (values, indices) tuple)
    argsort(T, I) /  argsort(T, DIM, I)  Indices that would sort
    topk(T, K, R) /  topk(T, K, DIM, R) Top-k (returns (values, indices) tuple)
    nonzero(T, NZ)                       Indices of nonzero elements
    unique(T, U)                         Unique elements (sorted)

Phase 15 — Linalg Extras and Numeric Checks
---------------------------------------------
Linalg extras:
    triu(T, R)  /  triu(T, DIAGONAL, R)  Upper triangular
    tril(T, R)  /  tril(T, DIAGONAL, R)  Lower triangular
    trace(T, R)                          Sum of diagonal elements

Numeric checks (element-wise, return bool tensors):
    isnan(T, R)                          Element-wise NaN check
    isinf(T, R)                          Element-wise infinity check
    isfinite(T, R)                       Element-wise finiteness check

Numeric checks (check predicates, succeed/fail):
    has_nan(T)                           Succeeds if any NaN
    has_inf(T)                           Succeeds if any infinity
    all_finite(T)                        Succeeds if all finite

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

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import (
    _pred, _deep_deref, _pure, _property_2, _bidir_2, _bidir_3_mid,
    _check_1, _check_2, _check_axis_1,
)


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


# ═══════════════════════════════════════════════════════════════════════════
# Tensor creation
# ═══════════════════════════════════════════════════════════════════════════

tensor = _pred("tensor",
    (2, _pure(lambda data: _th().tensor(data))),
    (3, _pure(lambda data, opts: _th().tensor(data, **opts))),
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
    (5, _pure(lambda start, end, step, opts:
              _th().arange(start, end, step, **opts))),
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
    (4, _pure(lambda n, m, opts: _th().eye(int(n), int(m), **opts))),
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
# Additional shape operations (Phase 8)
# ═══════════════════════════════════════════════════════════════════════════

split = _pred("split",
    (3, _pure(lambda t, size: list(t.split(int(size))))),
    (4, _pure(lambda t, size, dim: list(t.split(int(size), dim=int(dim))))),
)

chunk = _pred("chunk",
    (3, _pure(lambda t, n: list(t.chunk(int(n))))),
    (4, _pure(lambda t, n, dim: list(t.chunk(int(n), dim=int(dim))))),
)

unbind = _pred("unbind",
    (3, _pure(lambda t, dim: list(t.unbind(int(dim))))),
)

narrow = _pred("narrow",
    (5, _pure(lambda t, dim, start, length: t.narrow(int(dim), int(start), int(length)))),
)

expand = _pred("expand",
    (3, _pure(lambda t, sizes: t.expand(sizes))),
)

repeat = _pred("repeat",
    (3, _pure(lambda t, repeats: t.repeat(repeats))),
)

tile = _pred("tile",
    (3, _pure(lambda t, reps: _th().tile(t, reps))),
)

flip = _pred("flip",
    (3, _pure(lambda t, dims: _th().flip(t, dims))),
)

roll = _pred("roll",
    (3, _pure(lambda t, shifts: _th().roll(t, int(shifts)))),
    (4, _pure(lambda t, shifts, dims: _th().roll(t, int(shifts), int(dims)))),
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


def _dtype_info_3(this_generator, _proceed, _fail, _catcher, dtype_var, key_var, value_var, trail):
    dt = deref(dtype_var)
    k = deref(key_var)
    v = deref(value_var)

    if is_var(dt):
        # dtype unbound: fail (too many dtypes to enumerate usefully)
        yield (_fail, DONE)
        return

    try:
        props = _dtype_properties(dt)
    except Exception:
        yield (_fail, DONE)
        return

    if not is_var(k):
        # Key bound: look up single property
        val = props.get(k)
        if val is not None and unify(value_var, val, trail):
            yield (_proceed, None)
    else:
        # Key unbound: enumerate all properties
        for key, val in props.items():
            mark = trail.mark()
            if unify(key_var, key, trail) and unify(value_var, val, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


dtype_info = _pred("dtype_info",
    (3, _dtype_info_3),
)


# ═══════════════════════════════════════════════════════════════════════════
# IO (impure)
# ═══════════════════════════════════════════════════════════════════════════

def _save_2(this_generator, _proceed, _fail, _catcher, obj_var, path_var, trail):
    obj = deref(obj_var)
    path = str(deref(path_var))
    try:
        _th().save(obj, path)
    except Exception:
        yield (_fail, DONE)
        return
    yield (_proceed, None)
    yield (_fail, DONE)


def _load_2(this_generator, _proceed, _fail, _catcher, path_var, result_var, trail):
    path = str(deref(path_var))
    try:
        obj = _th().load(path, weights_only=True)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(result_var, obj, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


save = _pred("save",
    (2, _save_2),
)

load = _pred("load",
    (2, _load_2),
)


# ═══════════════════════════════════════════════════════════════════════════
# FFT (Phase 5) — bijective pairs
# ═══════════════════════════════════════════════════════════════════════════

fft_transform = _pred("fft_transform",
    (2, _bidir_2(
        lambda t: _th().fft.fft(t),
        lambda f: _th().fft.ifft(f),
    )),
    (3, _bidir_3_mid(
        lambda t, dim: _th().fft.fft(t, dim=int(dim)),
        lambda f, dim: _th().fft.ifft(f, dim=int(dim)),
    )),
)

real_fft = _pred("real_fft",
    (2, _bidir_2(
        lambda t: _th().fft.rfft(t),
        lambda f: _th().fft.irfft(f),
    )),
    (3, _bidir_3_mid(
        lambda t, dim: _th().fft.rfft(t, dim=int(dim)),
        lambda f, dim: _th().fft.irfft(f, dim=int(dim)),
    )),
)

fft_transform_2d = _pred("fft_transform_2d",
    (2, _bidir_2(
        lambda t: _th().fft.fft2(t),
        lambda f: _th().fft.ifft2(f),
    )),
)

fft_transform_nd = _pred("fft_transform_nd",
    (2, _bidir_2(
        lambda t: _th().fft.fftn(t),
        lambda f: _th().fft.ifftn(f),
    )),
)

fft_shift = _pred("fft_shift",
    (2, _bidir_2(
        lambda t: _th().fft.fftshift(t),
        lambda f: _th().fft.ifftshift(f),
    )),
)

fft_frequencies = _pred("fft_frequencies",
    (2, _pure(lambda n: _th().fft.fftfreq(int(n)))),
    (3, _pure(lambda n, d: _th().fft.fftfreq(int(n), d=float(d)))),
)

real_fft_frequencies = _pred("real_fft_frequencies",
    (2, _pure(lambda n: _th().fft.rfftfreq(int(n)))),
    (3, _pure(lambda n, d: _th().fft.rfftfreq(int(n), d=float(d)))),
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
# Comparisons, Logic, and Selection (Phase 6)
# ═══════════════════════════════════════════════════════════════════════════

# -- Element-wise comparisons --

eq = _pred("eq",
    (3, _pure(lambda a, b: _th().eq(a, b))),
)

ne = _pred("ne",
    (3, _pure(lambda a, b: _th().ne(a, b))),
)

gt = _pred("gt",
    (3, _pure(lambda a, b: _th().gt(a, b))),
)

lt = _pred("lt",
    (3, _pure(lambda a, b: _th().lt(a, b))),
)

ge = _pred("ge",
    (3, _pure(lambda a, b: _th().ge(a, b))),
)

le = _pred("le",
    (3, _pure(lambda a, b: _th().le(a, b))),
)

# -- Check predicates --

equal = _pred("equal",
    (2, _check_2(lambda a, b: _th().equal(a, b))),
)


def _allclose_4(this_generator, _proceed, _fail, _catcher, a_var, b_var, atol_var, rtol_var, trail):
    a = _deep_deref(deref(a_var))
    b = _deep_deref(deref(b_var))
    atol = float(deref(atol_var))
    rtol = float(deref(rtol_var))
    try:
        if _th().allclose(a, b, atol=atol, rtol=rtol):
            yield (_proceed, None)
    except Exception:
        pass
    yield (_fail, DONE)


allclose = _pred("allclose",
    (2, _check_2(lambda a, b: _th().allclose(a, b))),
    (4, _allclose_4),
)

# -- Logical operations --

logical_and = _pred("logical_and",
    (3, _pure(lambda a, b: _th().logical_and(a, b))),
)

logical_or = _pred("logical_or",
    (3, _pure(lambda a, b: _th().logical_or(a, b))),
)

logical_not = _pred("logical_not",
    (2, _pure(lambda a: _th().logical_not(a))),
)

logical_xor = _pred("logical_xor",
    (3, _pure(lambda a, b: _th().logical_xor(a, b))),
)

any = _pred("any",
    (1, _check_1(lambda t: _th().any(t).item())),
    (2, _check_axis_1(lambda t, d: _th().any(t, dim=d).any().item())),
)

all = _pred("all",
    (1, _check_1(lambda t: _th().all(t).item())),
    (2, _check_axis_1(lambda t, d: _th().all(t, dim=d).all().item())),
)

# -- Selection --

where = _pred("where",
    (4, _pure(lambda cond, x, y: _th().where(cond, x, y))),
)

masked_select = _pred("masked_select",
    (3, _pure(lambda t, mask: _th().masked_select(t, mask))),
)

index_select = _pred("index_select",
    (4, _pure(lambda t, dim, idx: _th().index_select(t, int(dim), idx))),
)

gather = _pred("gather",
    (4, _pure(lambda t, dim, idx: _th().gather(t, int(dim), idx))),
)

scatter = _pred("scatter",
    (5, _pure(lambda t, dim, idx, src: t.scatter(int(dim), idx, src))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Einsum and Advanced Math (Phase 7)
# ═══════════════════════════════════════════════════════════════════════════

# -- Einsum --

einsum = _pred("einsum",
    (3, _pure(lambda eq, tensors: _th().einsum(eq, *tensors))),
)

# -- Bijective trig / log --

logarithm = _pred("logarithm",
    (2, _bidir_2(
        lambda x: _th().exp(x),
        lambda y: _th().log(y),
    )),
)

sine = _pred("sine",
    (2, _bidir_2(
        lambda a: _th().sin(a),
        lambda v: _th().asin(v),
    )),
)

cosine = _pred("cosine",
    (2, _bidir_2(
        lambda a: _th().cos(a),
        lambda v: _th().acos(v),
    )),
)

tangent = _pred("tangent",
    (2, _bidir_2(
        lambda a: _th().tan(a),
        lambda v: _th().atan(v),
    )),
)

# -- Non-bijective math --

sqrt = _pred("sqrt",
    (2, _pure(lambda t: _th().sqrt(t))),
)

pow = _pred("pow",
    (3, _pure(lambda t, exp: _th().pow(t, exp))),
)

atan2 = _pred("atan2",
    (3, _pure(lambda y, x: _th().atan2(y, x))),
)

sinh = _pred("sinh",
    (2, _pure(lambda t: _th().sinh(t))),
)

cosh = _pred("cosh",
    (2, _pure(lambda t: _th().cosh(t))),
)

tanh = _pred("tanh",
    (2, _pure(lambda t: _th().tanh(t))),
)

sigmoid = _pred("sigmoid",
    (2, _pure(lambda t: _th().sigmoid(t))),
)

log_softmax = _pred("log_softmax",
    (3, _pure(lambda t, dim: _th().nn.functional.log_softmax(t, dim=int(dim)))),
)

floor = _pred("floor",
    (2, _pure(lambda t: _th().floor(t))),
)

ceil = _pred("ceil",
    (2, _pure(lambda t: _th().ceil(t))),
)

round = _pred("round",
    (2, _pure(lambda t: _th().round(t))),
)

sign = _pred("sign",
    (2, _pure(lambda t: _th().sign(t))),
)

cumsum = _pred("cumsum",
    (3, _pure(lambda t, dim: _th().cumsum(t, int(dim)))),
)

cumprod = _pred("cumprod",
    (3, _pure(lambda t, dim: _th().cumprod(t, int(dim)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — Creation variants
# ═══════════════════════════════════════════════════════════════════════════

zeros_like = _pred("zeros_like",
    (2, _pure(lambda t: _th().zeros_like(t))),
)

ones_like = _pred("ones_like",
    (2, _pure(lambda t: _th().ones_like(t))),
)

full_like = _pred("full_like",
    (3, _pure(lambda t, value: _th().full_like(t, value))),
)

empty = _pred("empty",
    (2, _pure(lambda shape: _th().empty(shape))),
    (3, _pure(lambda shape, opts: _th().empty(shape, **opts))),
)

rand = _pred("rand",
    (2, _pure(lambda shape: _th().rand(shape))),
    (3, _pure(lambda shape, opts: _th().rand(shape, **opts))),
)

randint = _pred("randint",
    (4, _pure(lambda low, high, shape: _th().randint(int(low), int(high), shape))),
    (5, _pure(lambda low, high, shape, opts:
              _th().randint(int(low), int(high), shape, **opts))),
)

logspace = _pred("logspace",
    (4, _pure(lambda start, end, steps: _th().logspace(start, end, int(steps)))),
    (5, _pure(lambda start, end, steps, opts:
              _th().logspace(start, end, int(steps), **opts))),
)

diag = _pred("diag",
    (2, _pure(lambda t: _th().diag(t))),
    (3, _pure(lambda t, diagonal: _th().diag(t, int(diagonal)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — Arithmetic gaps
# ═══════════════════════════════════════════════════════════════════════════

sub = _pred("sub",
    (3, _pure(lambda a, b: _th().sub(a, b))),
)

div = _pred("div",
    (3, _pure(lambda a, b: _th().div(a, b))),
)

neg = _pred("neg",
    (2, _pure(lambda t: _th().neg(t))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 14 — Statistical reductions
# ═══════════════════════════════════════════════════════════════════════════

median = _pred("median",
    (2, _pure(lambda t: _th().median(t))),
    (3, _pure(lambda t, dim: tuple(_th().median(t, int(dim))))),
)

std = _pred("std",
    (2, _pure(lambda t: _th().std(t))),
    (3, _pure(lambda t, dim: _th().std(t, int(dim)))),
    (4, _pure(lambda t, dim, opts: _th().std(t, int(dim), **opts))),
)

var = _pred("var",
    (2, _pure(lambda t: _th().var(t))),
    (3, _pure(lambda t, dim: _th().var(t, int(dim)))),
    (4, _pure(lambda t, dim, opts: _th().var(t, int(dim), **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 14 — Selection and sorting
# ═══════════════════════════════════════════════════════════════════════════

argmin = _pred("argmin",
    (2, _pure(lambda t: _th().argmin(t))),
    (3, _pure(lambda t, dim: _th().argmin(t, int(dim)))),
)

argmax = _pred("argmax",
    (2, _pure(lambda t: _th().argmax(t))),
    (3, _pure(lambda t, dim: _th().argmax(t, int(dim)))),
)

sort = _pred("sort",
    (2, _pure(lambda t: tuple(_th().sort(t)))),
    (3, _pure(lambda t, dim: tuple(_th().sort(t, dim=int(dim))))),
    (4, _pure(lambda t, dim, opts: tuple(_th().sort(t, dim=int(dim), **opts)))),
)

argsort = _pred("argsort",
    (2, _pure(lambda t: _th().argsort(t))),
    (3, _pure(lambda t, dim: _th().argsort(t, dim=int(dim)))),
    (4, _pure(lambda t, dim, opts: _th().argsort(t, dim=int(dim), **opts))),
)

topk = _pred("topk",
    (3, _pure(lambda t, k: tuple(_th().topk(t, int(k))))),
    (4, _pure(lambda t, k, dim: tuple(_th().topk(t, int(k), dim=int(dim))))),
    (5, _pure(lambda t, k, dim, opts:
              tuple(_th().topk(t, int(k), dim=int(dim), **opts)))),
)

nonzero = _pred("nonzero",
    (2, _pure(lambda t: _th().nonzero(t))),
)

unique = _pred("unique",
    (2, _pure(lambda t: _th().unique(t))),
    (3, _pure(lambda t, opts: _th().unique(t, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 15 — Linalg extras
# ═══════════════════════════════════════════════════════════════════════════

triu = _pred("triu",
    (2, _pure(lambda t: _th().triu(t))),
    (3, _pure(lambda t, diag: _th().triu(t, diagonal=int(diag)))),
)

tril = _pred("tril",
    (2, _pure(lambda t: _th().tril(t))),
    (3, _pure(lambda t, diag: _th().tril(t, diagonal=int(diag)))),
)

trace = _pred("trace",
    (2, _pure(lambda t: _th().trace(t))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 15 — Numeric checks
# ═══════════════════════════════════════════════════════════════════════════

isnan = _pred("isnan",
    (2, _pure(lambda t: _th().isnan(t))),
)

isinf = _pred("isinf",
    (2, _pure(lambda t: _th().isinf(t))),
)

isfinite = _pred("isfinite",
    (2, _pure(lambda t: _th().isfinite(t))),
)

has_nan = _pred("has_nan",
    (1, _check_1(lambda t: _th().isnan(t).any().item())),
)

has_inf = _pred("has_inf",
    (1, _check_1(lambda t: _th().isinf(t).any().item())),
)

all_finite = _pred("all_finite",
    (1, _check_1(lambda t: _th().isfinite(t).all().item())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Dtype and numeric constants (re-exported from torch for direct import)
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
        # Numeric constants (also available as AST-level builtins: NaN, Inf, -Inf)
        "NaN": float("nan"), "Inf": float("inf"),
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
    # Additional shape operations (Phase 8)
    "split", "chunk", "unbind", "narrow",
    "expand", "repeat", "tile", "flip", "roll",
    # Conversions
    "tensor_numpy", "tensor_list",
    # Dtype info
    "dtype_info",
    # IO (impure)
    "save", "load",
    # FFT (bijective pairs)
    "fft_transform", "real_fft",
    "fft_transform_2d", "fft_transform_nd",
    "fft_shift", "fft_frequencies", "real_fft_frequencies",
    # Linear algebra
    "det", "inv", "solve", "svd", "eig", "cholesky", "qr",
    "norm", "matrix_rank", "pinv", "cross", "dot",
    # Comparisons, logic, selection
    "eq", "ne", "gt", "lt", "ge", "le", "equal", "allclose",
    "logical_and", "logical_or", "logical_not", "logical_xor",
    "any", "all",
    "where", "masked_select", "index_select", "gather", "scatter",
    # Einsum and advanced math
    "einsum",
    "logarithm", "sine", "cosine", "tangent",
    "sqrt", "pow", "atan2",
    "sinh", "cosh", "tanh", "sigmoid", "log_softmax",
    "floor", "ceil", "round", "sign",
    "cumsum", "cumprod",
    # Creation variants (Phase 13)
    "zeros_like", "ones_like", "full_like", "empty",
    "rand", "randint", "logspace", "diag",
    # Arithmetic gaps (Phase 13)
    "sub", "div", "neg",
    # Statistics and selection (Phase 14)
    "median", "std", "var",
    "argmin", "argmax", "sort", "argsort", "topk",
    "nonzero", "unique",
    # Linalg extras (Phase 15)
    "triu", "tril", "trace",
    # Numeric checks (Phase 15)
    "isnan", "isinf", "isfinite", "has_nan", "has_inf", "all_finite",
    # Dtype constants
    "float16", "float32", "float64", "bfloat16",
    "int8", "int16", "int32", "int64", "uint8",
    "bool", "complex64", "complex128",
    # Numeric constants (also AST-level builtins, no import needed)
    "NaN", "Inf",
]
