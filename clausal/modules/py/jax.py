"""clausal.modules.py.jax — JAX array predicates for Clausal.

Provides pure array operations from JAX as importable predicate objects
for use in .clausal files via::

    -import_from(py.jax, [array, zeros, ones, arange, linspace, full, eye,
                          shape, dtype, device, dim, element_count,
                          matmul, dot, add, mul, sum, mean, max, min,
                          clip, abs,
                          reshape, squeeze, expand_dims, transpose,
                          swapaxes, moveaxis, concatenate, stack,
                          broadcast_to, astype,
                          at_set, at_add, at_mul, at_min, at_max, at_get,
                          jax_numpy, array_list,
                          det, slogdet, inv, solve, svd,
                          eig, eigh, eigvals, eigvalsh,
                          cholesky, qr, lstsq,
                          norm, matrix_rank, pinv, matrix_power, cross,
                          fft_transform, real_fft,
                          fft_transform_2d, fft_transform_nd, fft_shift,
                          fft_frequencies, real_fft_frequencies,
                          eq, ne, gt, lt, ge, le, equal, array_equal, allclose,
                          logical_and, logical_or, logical_not, logical_xor,
                          any, all,
                          where, masked_select, take, put_along_axis,
                          einsum, logarithm, sine, cosine, tangent,
                          sqrt, pow, atan2, sinh, cosh, tanh,
                          sigmoid, softmax, log_softmax, logsumexp,
                          floor, ceil, round, sign, cumsum, cumprod,
                          float32, float64, int32, newaxis])

Phase 1 — Array Core
----------------------
All predicates in this phase are Tier 1 (pure, no state).

Array creation:
    array(DATA, A)                         Create array from list/nested list
    zeros(SHAPE, A)  /  zeros(SHAPE, OPTS, A)   Zero array; OPTS dict for dtype
    ones(SHAPE, A)   /  ones(SHAPE, OPTS, A)    Ones array
    full(SHAPE, VALUE, A)  /  full(SHAPE, VALUE, OPTS, A)
    arange(END, A)   /  arange(START, END, A)  /  arange(START, END, STEP, A)
    linspace(START, END, STEPS, A)  /  linspace(START, END, STEPS, OPTS, A)
    eye(N, A)  /  eye(N, M, A)  /  eye(N, M, OPTS, A)

Array properties (multi-mode):
    shape(A, S)             (+A,-S) query or (+A,+S) check
    dtype(A, D)             (+A,-D) query or (+A,+D) check
    device(A, D)            (+A,-D) query or (+A,+D) check  (string form)
    dim(A, N)               (+A,-N) query
    element_count(A, N)     (+A,-N) query

Array math:
    matmul(A, B, C)         Matrix multiply
    dot(A, B, C)            Dot product
    add(A, B, C)            Element-wise add
    mul(A, B, C)            Element-wise multiply
    sum(A, S)   / sum(A, AXIS, S)        Sum reduction
    mean(A, M)  / mean(A, AXIS, M)       Mean reduction
    max(A, M)   / max(A, AXIS, M)        Max reduction
    min(A, M)   / min(A, AXIS, M)        Min reduction
    clip(A, MIN, MAX, A2)   Clip values
    abs(A, A2)              Absolute value

Shape operations:
    reshape(A, SHAPE, A2)           Reshape array
    squeeze(A, A2) / squeeze(A, AXIS, A2)   Remove size-1 dims
    expand_dims(A, AXIS, A2)        Add size-1 dim
    transpose(A, A2) / transpose(A, AXES, A2)   Transpose
    swapaxes(A, A0, A1, A2)         Swap two axes
    moveaxis(A, SRC, DEST, A2)      Move an axis
    concatenate(ARRS, AXIS, A)      Concatenate
    stack(ARRS, AXIS, A)            Stack along new axis
    broadcast_to(A, SHAPE, A2)      Broadcast to shape
    astype(A, DTYPE, A2)            Cast to dtype

Functional updates (`.at`, pure — returns a new array, leaves A untouched):
    at_set(A, IDX, VAL, A2)         A.at[IDX].set(VAL)
    at_add(A, IDX, VAL, A2)         A.at[IDX].add(VAL)
    at_mul(A, IDX, VAL, A2)         A.at[IDX].mul(VAL)
    at_min(A, IDX, VAL, A2)         A.at[IDX].min(VAL)
    at_max(A, IDX, VAL, A2)         A.at[IDX].max(VAL)
    at_get(A, IDX, VAL)             A.at[IDX].get()

Conversions (bijective):
    jax_numpy(A, N)          jax.Array <-> numpy.ndarray
    array_list(A, L)         jax.Array <-> nested Python list

Linear algebra (jnp.linalg):
    det(A, D)                Determinant
    slogdet(A, (SIGN, LOGDET))
    inv(A, B)                Matrix inverse (self-inverse pair)
    solve(A, B, X)           Solve A @ X == B
    svd(A, (U, S, VH))       Singular value decomposition
    eig(A, (VAL, VEC))       Eigendecomposition (complex)
    eigh(A, (VAL, VEC))      Hermitian eigendecomposition (real)
    eigvals(A, VAL)          Eigenvalues only (complex)
    eigvalsh(A, VAL)         Hermitian eigenvalues (real)
    cholesky(A, L)           Cholesky factor; A = L @ L.T
    qr(A, (Q, R))            QR decomposition
    lstsq(A, B, (X, RES, RANK, S))     Least squares
    norm(A, N) / norm(A, ORD, N)        Matrix/vector norm
    matrix_rank(A, R)        Rank
    pinv(A, B)               Moore-Penrose pseudoinverse
    matrix_power(A, N, B)    A ** N (integer N)
    cross(A, B, C)           Cross product

Comparisons, logic, and selection (Phase 6):
    eq(A, B, C)             Element-wise == → bool array
    ne(A, B, C)             Element-wise !=
    gt(A, B, C)             Element-wise >
    lt(A, B, C)             Element-wise <
    ge(A, B, C)             Element-wise >=
    le(A, B, C)             Element-wise <=
    equal(A, B)             Check: every element equal (shape + values)
    array_equal(A, B)       Check: alias for equal/2
    allclose(A, B)          Check: approximately equal (default tol)
    allclose(A, B, ATOL, RTOL)     Check: approximately equal with tolerances
    logical_and(A, B, C)    Element-wise AND
    logical_or(A, B, C)     Element-wise OR
    logical_not(A, B)       Element-wise NOT
    logical_xor(A, B, C)    Element-wise XOR
    any(A) / any(A, AXIS)   Check: any element true (Python bool)
    all(A) / all(A, AXIS)   Check: all elements true (Python bool)
    where(COND, X, Y, R)    Element-wise jnp.where(cond, x, y)
    masked_select(A, MASK, R)      Select elements where MASK is true (1-D)
    take(A, INDICES, AXIS, R)      Gather elements along AXIS
    put_along_axis(A, IDX, VAL, AXIS, R)   Scatter VAL at IDX along AXIS (copy)

Einsum and advanced math (Phase 7):
    einsum(EQ, ARRS, R)        jnp.einsum(eq, *arrs) — ARRS is a list
    logarithm(X, Y)            Bijective log <-> exp (Y = log X)
    sine(ANGLE, VALUE)         Bijective sin <-> arcsin (partial range)
    cosine(ANGLE, VALUE)       Bijective cos <-> arccos (partial range)
    tangent(ANGLE, VALUE)      Bijective tan <-> arctan (partial range)
    sqrt(A, R)                 Element-wise square root
    pow(A, E, R)               Element-wise A ** E
    atan2(Y, X, R)             Two-arg arctangent jnp.arctan2(y, x)
    sinh / cosh / tanh(A, R)   Hyperbolic functions
    sigmoid(A, R)              jax.nn.sigmoid
    softmax(A, AXIS, R)        jax.nn.softmax along AXIS
    log_softmax(A, AXIS, R)    jax.nn.log_softmax along AXIS
    logsumexp(A, AXIS, R)      jax.scipy.special.logsumexp along AXIS
    floor / ceil / round / sign(A, R)   Rounding / sign
    cumsum(A, AXIS, R)         Cumulative sum along AXIS
    cumprod(A, AXIS, R)        Cumulative product along AXIS

FFT (jnp.fft) — bijective pairs exposed as single multi-mode predicates:
    fft_transform(T, F) / fft_transform(T, AXIS, F)
                              Complex FFT (fft <-> ifft)
    real_fft(T, F)    / real_fft(T, AXIS, F)
                              Real FFT (rfft <-> irfft); bijective for even N
    fft_transform_2d(T, F) / fft_transform_2d(T, AXES, F)
                              2-D FFT (fft2 <-> ifft2); default AXES=(-2, -1)
    fft_transform_nd(T, F) / fft_transform_nd(T, AXES, F)
                              N-D FFT (fftn <-> ifftn); default = all axes
    fft_shift(T, S) / fft_shift(T, AXES, S)
                              fftshift <-> ifftshift; default = all axes
    fft_frequencies(N, F) / fft_frequencies(N, D, F)
                              jnp.fft.fftfreq (one-way)
    real_fft_frequencies(N, F) / (/3)
                              jnp.fft.rfftfreq (one-way)

Exported constants (via __getattr__):
    Dtypes: float16, float32, float64, bfloat16,
            int8, int16, int32, int64,
            uint8, uint16, uint32, uint64,
            bool_, complex64, complex128
    Math constants: pi, e, inf, nan
    Indexing: newaxis

Gotcha — float64 is silent-downcast to float32 by default
----------------------------------------------------------
JAX disables 64-bit floats by default. With the default config,
``zeros([2, 3], {"dtype": float64}, A)`` emits a ``UserWarning`` and
produces a ``float32`` array — check modes like ``dtype(A, float64)``
will then fail and the cause is non-obvious.

The wrapper intentionally does **not** flip ``jax_enable_x64`` on import,
because doing so would also change the default dtype from ``float32`` to
``float64`` globally — a surprise for anyone else in the same process.

If you need float64, enable it explicitly **before** any JAX computation
(and before importing this module's constants if you rely on them at
import time)::

    import jax
    jax.config.update("jax_enable_x64", True)

Or set the environment variable ``JAX_ENABLE_X64=1`` before Python
starts. See https://docs.jax.dev/en/latest/notebooks/Common_Gotchas_in_JAX.html#double-64bit-precision
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import (
    _pred, _pure, _property_2, _bidir_2, _bidir_3_mid,
    _check_2, _check_4, _check_1, _check_axis_1,
)


# ── Lazy jax import ──────────────────────────────────────────────────────

_jax = None
_jnp = None
_jax_lock = _threading.Lock()


def _ensure_jax():
    global _jax, _jnp
    if _jax is not None:
        return
    with _jax_lock:
        if _jax is not None:
            return
        from clausal.modules.py import _import_stdlib
        _jax = _import_stdlib("jax")
        _jnp = _import_stdlib("jax.numpy")


def _jx():
    _ensure_jax()
    return _jax


def _jnp_mod():
    _ensure_jax()
    return _jnp


_numpy = None
_numpy_lock = _threading.Lock()


def _np():
    global _numpy
    if _numpy is not None:
        return _numpy
    with _numpy_lock:
        if _numpy is not None:
            return _numpy
        from clausal.modules.py import _import_stdlib
        _numpy = _import_stdlib("numpy")
    return _numpy


# ═══════════════════════════════════════════════════════════════════════════
# Array creation
# ═══════════════════════════════════════════════════════════════════════════

array = _pred("array",
    (2, _pure(lambda data: _jnp_mod().array(data))),
    (3, _pure(lambda data, opts: _jnp_mod().array(data, **opts))),
)

zeros = _pred("zeros",
    (2, _pure(lambda shape: _jnp_mod().zeros(shape))),
    (3, _pure(lambda shape, opts: _jnp_mod().zeros(shape, **opts))),
)

ones = _pred("ones",
    (2, _pure(lambda shape: _jnp_mod().ones(shape))),
    (3, _pure(lambda shape, opts: _jnp_mod().ones(shape, **opts))),
)

full = _pred("full",
    (3, _pure(lambda shape, value: _jnp_mod().full(shape, value))),
    (4, _pure(lambda shape, value, opts: _jnp_mod().full(shape, value, **opts))),
)

arange = _pred("arange",
    (2, _pure(lambda end: _jnp_mod().arange(end))),
    (3, _pure(lambda start, end: _jnp_mod().arange(start, end))),
    (4, _pure(lambda start, end, step: _jnp_mod().arange(start, end, step))),
    (5, _pure(lambda start, end, step, opts:
              _jnp_mod().arange(start, end, step, **opts))),
)

linspace = _pred("linspace",
    (4, _pure(lambda start, end, steps: _jnp_mod().linspace(start, end, int(steps)))),
    (5, _pure(lambda start, end, steps, opts:
              _jnp_mod().linspace(start, end, int(steps), **opts))),
)

eye = _pred("eye",
    (2, _pure(lambda n: _jnp_mod().eye(int(n)))),
    (3, _pure(lambda n, m: _jnp_mod().eye(int(n), int(m)))),
    (4, _pure(lambda n, m, opts: _jnp_mod().eye(int(n), int(m), **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Array properties (multi-mode)
# ═══════════════════════════════════════════════════════════════════════════

shape = _pred("shape",
    (2, _property_2(lambda a: list(a.shape))),
)

dtype = _pred("dtype",
    (2, _property_2(lambda a: a.dtype)),
)

device = _pred("device",
    (2, _property_2(lambda a: str(a.device))),
)

dim = _pred("dim",
    (2, _pure(lambda a: a.ndim)),
)

element_count = _pred("element_count",
    (2, _pure(lambda a: a.size)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Array math
# ═══════════════════════════════════════════════════════════════════════════

matmul = _pred("matmul",
    (3, _pure(lambda a, b: _jnp_mod().matmul(a, b))),
)

dot = _pred("dot",
    (3, _pure(lambda a, b: _jnp_mod().dot(a, b))),
)

add = _pred("add",
    (3, _pure(lambda a, b: _jnp_mod().add(a, b))),
)

mul = _pred("mul",
    (3, _pure(lambda a, b: _jnp_mod().multiply(a, b))),
)


def _reduction_dispatches(fn_name):
    def full_reduce(a):
        return getattr(_jnp_mod(), fn_name)(a)
    def axis_reduce(a, axis):
        return getattr(_jnp_mod(), fn_name)(a, axis=int(axis))
    return (
        (2, _pure(full_reduce)),
        (3, _pure(axis_reduce)),
    )


# sum, max, min are Python builtins — module-scoped import prevents collision
sum = _pred("sum", *_reduction_dispatches("sum"))
mean = _pred("mean", *_reduction_dispatches("mean"))
max = _pred("max", *_reduction_dispatches("max"))
min = _pred("min", *_reduction_dispatches("min"))

clip = _pred("clip",
    (4, _pure(lambda a, lo, hi: _jnp_mod().clip(a, lo, hi))),
)

abs = _pred("abs",
    (2, _pure(lambda a: _jnp_mod().abs(a))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Shape operations
# ═══════════════════════════════════════════════════════════════════════════

reshape = _pred("reshape",
    (3, _pure(lambda a, shape: _jnp_mod().reshape(a, shape))),
)

squeeze = _pred("squeeze",
    (2, _pure(lambda a: _jnp_mod().squeeze(a))),
    (3, _pure(lambda a, axis: _jnp_mod().squeeze(a, axis=int(axis)))),
)

expand_dims = _pred("expand_dims",
    (3, _pure(lambda a, axis: _jnp_mod().expand_dims(a, int(axis)))),
)

transpose = _pred("transpose",
    (2, _pure(lambda a: _jnp_mod().transpose(a))),
    (3, _pure(lambda a, axes: _jnp_mod().transpose(a, axes))),
)

swapaxes = _pred("swapaxes",
    (4, _pure(lambda a, a0, a1: _jnp_mod().swapaxes(a, int(a0), int(a1)))),
)

moveaxis = _pred("moveaxis",
    (4, _pure(lambda a, src, dest: _jnp_mod().moveaxis(a, int(src), int(dest)))),
)

concatenate = _pred("concatenate",
    (3, _pure(lambda arrs, axis: _jnp_mod().concatenate(arrs, axis=int(axis)))),
)

stack = _pred("stack",
    (3, _pure(lambda arrs, axis: _jnp_mod().stack(arrs, axis=int(axis)))),
)

broadcast_to = _pred("broadcast_to",
    (3, _pure(lambda a, shape: _jnp_mod().broadcast_to(a, shape))),
)

astype = _pred("astype",
    (3, _pure(lambda a, dt: a.astype(dt))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Functional updates (`.at`) — JAX's pure equivalent of tensor[idx] = v
# ═══════════════════════════════════════════════════════════════════════════
#
# JAX's `arr.at[idx].set(v)` returns a new array; the original is untouched,
# so the update composes with Clausal backtracking. Index types accepted:
# scalar int, tuple of ints for multi-dim, and a JAX array for fancy
# indexing (user constructs it via ++(jnp.array([...]))). Slice updates are
# out of scope for this phase — use `lax.dynamic_update_slice` via ++().

at_set = _pred("at_set",
    (4, _pure(lambda a, idx, val: a.at[idx].set(val))),
)

at_add = _pred("at_add",
    (4, _pure(lambda a, idx, val: a.at[idx].add(val))),
)

at_mul = _pred("at_mul",
    (4, _pure(lambda a, idx, val: a.at[idx].mul(val))),
)

at_min = _pred("at_min",
    (4, _pure(lambda a, idx, val: a.at[idx].min(val))),
)

at_max = _pred("at_max",
    (4, _pure(lambda a, idx, val: a.at[idx].max(val))),
)

at_get = _pred("at_get",
    (3, _pure(lambda a, idx: a.at[idx].get())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Conversions (bijective)
# ═══════════════════════════════════════════════════════════════════════════

jax_numpy = _pred("jax_numpy",
    (2, _bidir_2(
        lambda a: _np().asarray(a),
        lambda n: _jnp_mod().asarray(n),
    )),
)

array_list = _pred("array_list",
    (2, _bidir_2(
        lambda a: a.tolist(),
        lambda l: _jnp_mod().array(l),
    )),
)


# ═══════════════════════════════════════════════════════════════════════════
# Linear algebra (jnp.linalg)
# ═══════════════════════════════════════════════════════════════════════════
#
# Pure operations from jax.numpy.linalg. Decompositions that return a
# NamedTuple (SVDResult, QRResult, EighResult, …) are converted to plain
# tuples so they decompose with `RESULT is (U, S, VH)` in Clausal.
#
# Numerical note: JAX defaults to float32. Round-trip equalities
# (`inv(inv(A)) == A`, `L @ L.T == A`) can drift — tests use loose
# tolerance or pass `{"dtype": float64}` (and require x64 enabled).

def _jla():
    return _jnp_mod().linalg


det = _pred("det",
    (2, _pure(lambda a: _jla().det(a))),
)

slogdet = _pred("slogdet",
    (2, _pure(lambda a: tuple(_jla().slogdet(a)))),
)

inv = _pred("inv",
    (2, _pure(lambda a: _jla().inv(a))),
)

solve = _pred("solve",
    (3, _pure(lambda a, b: _jla().solve(a, b))),
)

svd = _pred("svd",
    (2, _pure(lambda a: tuple(_jla().svd(a)))),
)

eig = _pred("eig",
    (2, _pure(lambda a: tuple(_jla().eig(a)))),
)

eigh = _pred("eigh",
    (2, _pure(lambda a: tuple(_jla().eigh(a)))),
)

eigvals = _pred("eigvals",
    (2, _pure(lambda a: _jla().eigvals(a))),
)

eigvalsh = _pred("eigvalsh",
    (2, _pure(lambda a: _jla().eigvalsh(a))),
)

cholesky = _pred("cholesky",
    (2, _pure(lambda a: _jla().cholesky(a))),
)

qr = _pred("qr",
    (2, _pure(lambda a: tuple(_jla().qr(a)))),
)

# lstsq returns (solution, residuals, rank, singular_values). Pass
# rcond=None explicitly to silence JAX's "future default change" warning.
lstsq = _pred("lstsq",
    (3, _pure(lambda a, b: tuple(_jla().lstsq(a, b, rcond=None)))),
)

norm = _pred("norm",
    (2, _pure(lambda a: _jla().norm(a))),
    (3, _pure(lambda a, ord_: _jla().norm(a, ord=ord_))),
)

matrix_rank = _pred("matrix_rank",
    (2, _pure(lambda a: int(_jla().matrix_rank(a)))),
)

pinv = _pred("pinv",
    (2, _pure(lambda a: _jla().pinv(a))),
)

matrix_power = _pred("matrix_power",
    (3, _pure(lambda a, n: _jla().matrix_power(a, int(n)))),
)

cross = _pred("cross",
    (3, _pure(lambda a, b: _jnp_mod().cross(a, b))),
)


# ═══════════════════════════════════════════════════════════════════════════
# FFT (jnp.fft) — bijective pairs collapsed into multi-mode predicates
# ═══════════════════════════════════════════════════════════════════════════
#
# Every FFT / inverse-FFT pair becomes a single multi-mode predicate:
#   - (+T, -F)  runs the forward transform
#   - (-T, +F)  runs the inverse to recover the signal
#   - (+T, +F)  acts as a check
#
# real_fft is strict-bijective only for even N. For odd N, irfft
# assumes N = 2 * (K - 1) and loses the trailing sample — documented
# in docs/jax.md and exercised with even-N tests.
#
# Complex dtype note: fft on a float32 real input returns complex64;
# on float64 input it returns complex128. Shape round-trips work; exact
# dtype round-trips don't (irfft returns real float, not the complex
# that fft produced).

def _jfft():
    return _jnp_mod().fft


fft_transform = _pred("fft_transform",
    (2, _bidir_2(
        lambda t: _jfft().fft(t),
        lambda f: _jfft().ifft(f),
    )),
    (3, _bidir_3_mid(
        lambda t, axis: _jfft().fft(t, axis=int(axis)),
        lambda f, axis: _jfft().ifft(f, axis=int(axis)),
    )),
)

real_fft = _pred("real_fft",
    (2, _bidir_2(
        lambda t: _jfft().rfft(t),
        lambda f: _jfft().irfft(f),
    )),
    (3, _bidir_3_mid(
        lambda t, axis: _jfft().rfft(t, axis=int(axis)),
        lambda f, axis: _jfft().irfft(f, axis=int(axis)),
    )),
)

fft_transform_2d = _pred("fft_transform_2d",
    (2, _bidir_2(
        lambda t: _jfft().fft2(t),
        lambda f: _jfft().ifft2(f),
    )),
    (3, _bidir_3_mid(
        lambda t, axes: _jfft().fft2(t, axes=tuple(axes)),
        lambda f, axes: _jfft().ifft2(f, axes=tuple(axes)),
    )),
)

fft_transform_nd = _pred("fft_transform_nd",
    (2, _bidir_2(
        lambda t: _jfft().fftn(t),
        lambda f: _jfft().ifftn(f),
    )),
    (3, _bidir_3_mid(
        lambda t, axes: _jfft().fftn(t, axes=tuple(axes)),
        lambda f, axes: _jfft().ifftn(f, axes=tuple(axes)),
    )),
)

fft_shift = _pred("fft_shift",
    (2, _bidir_2(
        lambda t: _jfft().fftshift(t),
        lambda s: _jfft().ifftshift(s),
    )),
    (3, _bidir_3_mid(
        lambda t, axes: _jfft().fftshift(t, axes=tuple(axes)),
        lambda s, axes: _jfft().ifftshift(s, axes=tuple(axes)),
    )),
)

fft_frequencies = _pred("fft_frequencies",
    (2, _pure(lambda n: _jfft().fftfreq(int(n)))),
    (3, _pure(lambda n, d: _jfft().fftfreq(int(n), d=d))),
)

real_fft_frequencies = _pred("real_fft_frequencies",
    (2, _pure(lambda n: _jfft().rfftfreq(int(n)))),
    (3, _pure(lambda n, d: _jfft().rfftfreq(int(n), d=d))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Comparisons, Logic, and Selection (Phase 6)
# ═══════════════════════════════════════════════════════════════════════════
#
# Element-wise comparison predicates return bool JAX arrays. Check-style
# predicates (equal/2, allclose, array_equal, any, all) return Python bools
# via reduction and are wrapped as _check_* dispatchers.

# -- Element-wise comparisons --

eq = _pred("eq",
    (3, _pure(lambda a, b: _jnp_mod().equal(a, b))),
)

ne = _pred("ne",
    (3, _pure(lambda a, b: _jnp_mod().not_equal(a, b))),
)

gt = _pred("gt",
    (3, _pure(lambda a, b: _jnp_mod().greater(a, b))),
)

lt = _pred("lt",
    (3, _pure(lambda a, b: _jnp_mod().less(a, b))),
)

ge = _pred("ge",
    (3, _pure(lambda a, b: _jnp_mod().greater_equal(a, b))),
)

le = _pred("le",
    (3, _pure(lambda a, b: _jnp_mod().less_equal(a, b))),
)

# -- Check predicates --

equal = _pred("equal",
    (2, _check_2(lambda a, b: bool(_jnp_mod().array_equal(a, b)))),
)

array_equal = _pred("array_equal",
    (2, _check_2(lambda a, b: bool(_jnp_mod().array_equal(a, b)))),
)

allclose = _pred("allclose",
    (2, _check_2(lambda a, b: bool(_jnp_mod().allclose(a, b)))),
    (4, _check_4(lambda a, b, atol, rtol:
                 bool(_jnp_mod().allclose(a, b, atol=float(atol), rtol=float(rtol))))),
)

# -- Logical operations --

logical_and = _pred("logical_and",
    (3, _pure(lambda a, b: _jnp_mod().logical_and(a, b))),
)

logical_or = _pred("logical_or",
    (3, _pure(lambda a, b: _jnp_mod().logical_or(a, b))),
)

logical_not = _pred("logical_not",
    (2, _pure(lambda a: _jnp_mod().logical_not(a))),
)

logical_xor = _pred("logical_xor",
    (3, _pure(lambda a, b: _jnp_mod().logical_xor(a, b))),
)

# any / all — /1 reduces over all elements (Python-bool check); /2 adds an axis.

any = _pred("any",
    (1, _check_1(lambda a: bool(_jnp_mod().any(a)))),
    (2, _check_axis_1(lambda a, axis: bool(_jnp_mod().any(_jnp_mod().any(a, axis=axis))))),
)

all = _pred("all",
    (1, _check_1(lambda a: bool(_jnp_mod().all(a)))),
    (2, _check_axis_1(lambda a, axis: bool(_jnp_mod().all(_jnp_mod().all(a, axis=axis))))),
)

# -- Selection --

where = _pred("where",
    (4, _pure(lambda cond, x, y: _jnp_mod().where(cond, x, y))),
)

# masked_select: arr[mask]. Not jit-safe because the output size depends on
# mask values — document this caveat. For a jit-safe alternative, callers
# can use `jnp.where(mask, a, 0.0)` directly.
masked_select = _pred("masked_select",
    (3, _pure(lambda a, mask: a[mask])),
)

take = _pred("take",
    (4, _pure(lambda a, indices, axis: _jnp_mod().take(a, indices, axis=int(axis)))),
)

# put_along_axis in JAX requires inplace=False (its API difference from numpy:
# JAX's immutable arrays mean "in-place" is impossible; the caller must
# acknowledge this explicitly).
put_along_axis = _pred("put_along_axis",
    (5, _pure(lambda a, indices, values, axis:
              _jnp_mod().put_along_axis(a, indices, values, axis=int(axis), inplace=False))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Einsum and Advanced Math (Phase 7)
# ═══════════════════════════════════════════════════════════════════════════
#
# einsum is pure; bijective trig/exp pairs collapse into _bidir_2 predicates
# named after the natural reading of the second arg (logarithm(EXP, VAL):
# VAL is the log of EXP). softmax, log_softmax, sigmoid live in jax.nn.
# logsumexp lives in jax.scipy.special (no numpy.logsumexp exists).

_jnn_mod_cache = None
_jss_mod_cache = None


def _jnn():
    global _jnn_mod_cache
    if _jnn_mod_cache is None:
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jnn_mod_cache = _import_stdlib("jax.nn")
    return _jnn_mod_cache


def _jss():
    global _jss_mod_cache
    if _jss_mod_cache is None:
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jss_mod_cache = _import_stdlib("jax.scipy.special")
    return _jss_mod_cache


einsum = _pred("einsum",
    (3, _pure(lambda eq, arrs: _jnp_mod().einsum(eq, *arrs))),
)

# -- Bijective pairs --

logarithm = _pred("logarithm",
    (2, _bidir_2(
        lambda x: _jnp_mod().log(x),
        lambda y: _jnp_mod().exp(y),
    )),
)

sine = _pred("sine",
    (2, _bidir_2(
        lambda angle: _jnp_mod().sin(angle),
        lambda value: _jnp_mod().arcsin(value),
    )),
)

cosine = _pred("cosine",
    (2, _bidir_2(
        lambda angle: _jnp_mod().cos(angle),
        lambda value: _jnp_mod().arccos(value),
    )),
)

tangent = _pred("tangent",
    (2, _bidir_2(
        lambda angle: _jnp_mod().tan(angle),
        lambda value: _jnp_mod().arctan(value),
    )),
)

# -- Non-bijective math --

sqrt = _pred("sqrt",
    (2, _pure(lambda a: _jnp_mod().sqrt(a))),
)

pow = _pred("pow",
    (3, _pure(lambda a, e: _jnp_mod().power(a, e))),
)

atan2 = _pred("atan2",
    (3, _pure(lambda y, x: _jnp_mod().arctan2(y, x))),
)

sinh = _pred("sinh",
    (2, _pure(lambda a: _jnp_mod().sinh(a))),
)

cosh = _pred("cosh",
    (2, _pure(lambda a: _jnp_mod().cosh(a))),
)

tanh = _pred("tanh",
    (2, _pure(lambda a: _jnp_mod().tanh(a))),
)

sigmoid = _pred("sigmoid",
    (2, _pure(lambda a: _jnn().sigmoid(a))),
)

softmax = _pred("softmax",
    (3, _pure(lambda a, axis: _jnn().softmax(a, axis=int(axis)))),
)

log_softmax = _pred("log_softmax",
    (3, _pure(lambda a, axis: _jnn().log_softmax(a, axis=int(axis)))),
)

logsumexp = _pred("logsumexp",
    (3, _pure(lambda a, axis: _jss().logsumexp(a, axis=int(axis)))),
)

floor = _pred("floor",
    (2, _pure(lambda a: _jnp_mod().floor(a))),
)

ceil = _pred("ceil",
    (2, _pure(lambda a: _jnp_mod().ceil(a))),
)

# round is a Python builtin — module-scoped import prevents collision
round = _pred("round",
    (2, _pure(lambda a: _jnp_mod().round(a))),
)

sign = _pred("sign",
    (2, _pure(lambda a: _jnp_mod().sign(a))),
)

cumsum = _pred("cumsum",
    (3, _pure(lambda a, axis: _jnp_mod().cumsum(a, axis=int(axis)))),
)

cumprod = _pred("cumprod",
    (3, _pure(lambda a, axis: _jnp_mod().cumprod(a, axis=int(axis)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Dtype and numeric constants (re-exported from jax.numpy)
# ═══════════════════════════════════════════════════════════════════════════

_EXPORTED_DTYPES = frozenset({
    "float16", "float32", "float64", "bfloat16",
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "bool_", "complex64", "complex128",
})

_EXPORTED_CONSTS = frozenset({"pi", "e", "inf", "nan", "newaxis"})


def __getattr__(name):
    if name in _EXPORTED_DTYPES or name in _EXPORTED_CONSTS:
        _ensure_jax()
        return getattr(_jnp, name)
    raise AttributeError(f"module 'clausal.modules.py.jax' has no attribute {name!r}")


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Creation
    "array", "zeros", "ones", "full", "arange", "linspace", "eye",
    # Properties
    "shape", "dtype", "device", "dim", "element_count",
    # Math
    "matmul", "dot", "add", "mul",
    "sum", "mean", "max", "min",
    "clip", "abs",
    # Shape operations
    "reshape", "squeeze", "expand_dims", "transpose",
    "swapaxes", "moveaxis", "concatenate", "stack",
    "broadcast_to", "astype",
    # Functional updates
    "at_set", "at_add", "at_mul", "at_min", "at_max", "at_get",
    # Conversions
    "jax_numpy", "array_list",
    # Linear algebra
    "det", "slogdet", "inv", "solve", "svd",
    "eig", "eigh", "eigvals", "eigvalsh",
    "cholesky", "qr", "lstsq",
    "norm", "matrix_rank", "pinv", "matrix_power", "cross",
    # FFT
    "fft_transform", "real_fft",
    "fft_transform_2d", "fft_transform_nd",
    "fft_shift",
    "fft_frequencies", "real_fft_frequencies",
    # Comparisons, logic, selection (Phase 6)
    "eq", "ne", "gt", "lt", "ge", "le",
    "equal", "array_equal", "allclose",
    "logical_and", "logical_or", "logical_not", "logical_xor",
    "any", "all",
    "where", "masked_select", "take", "put_along_axis",
    # Einsum + advanced math (Phase 7)
    "einsum",
    "logarithm", "sine", "cosine", "tangent",
    "sqrt", "pow", "atan2",
    "sinh", "cosh", "tanh",
    "sigmoid", "softmax", "log_softmax", "logsumexp",
    "floor", "ceil", "round", "sign",
    "cumsum", "cumprod",
    # Dtype constants (via __getattr__)
    "float16", "float32", "float64", "bfloat16",
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "bool_", "complex64", "complex128",
    # Math and indexing constants
    "pi", "e", "inf", "nan", "newaxis",
]
