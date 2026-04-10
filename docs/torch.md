# torch — PyTorch Tensor Operations

Provides pure tensor operations from PyTorch as [importable](import.md)
clausal predicates. Phase 1 covers tensor creation, properties, math,
shape operations, and conversions.

## Import

```clausal
# skip
-import_from(py.torch, [tensor, zeros, ones, randn, shape, dtype, device,
                         reshape, matmul, add, relu, softmax,
                         tensor_numpy, tensor_list,
                         float32, float64, int32, int64])
```

Dtype constants (`float32`, `float64`, `int32`, etc.) are exported
directly — no need for `++()` escape to access them.


---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 1 — pure | Creation, math, shape ops, properties | Tensor in, tensor out |
| 1 — pure (bijective) | `tensor_numpy`, `tensor_list` | Bidirectional conversion |
| 1 — pure (multi-mode) | `shape`, `dtype`, `device` | Query or check |

---

## Tensor Creation

### tensor

```clausal
# skip
tensor(DATA, T)
```

Create a tensor from a Python list or nested list.

```clausal
# skip
tensor([1.0, 2.0, 3.0], T),
shape(T, [3])
```

### zeros, ones

```clausal
# skip
zeros(SHAPE, T)
zeros(SHAPE, OPTS, T)
ones(SHAPE, T)
ones(SHAPE, OPTS, T)
```

Create zero/one-filled tensors. `OPTS` is a dict for `dtype`/`device` kwargs.

```clausal
# skip
zeros([3, 4], T),
shape(T, [3, 4])

zeros([2, 3], {"dtype": float64}, T),
dtype(T, float64)
```

### randn

```clausal
# skip
randn(SHAPE, T)
randn(SHAPE, OPTS, T)
```

Create a tensor filled with values from a standard normal distribution.

### arange

```clausal
# skip
arange(END, T)
arange(START, END, T)
arange(START, END, STEP, T)
```

Create a 1-D tensor with values from a range.

```clausal
# skip
arange(5, T),
shape(T, [5])

arange(0, 10, 2, T),
shape(T, [5])
```

### linspace

```clausal
# skip
linspace(START, END, STEPS, T)
linspace(START, END, STEPS, OPTS, T)
```

Create a 1-D tensor with `STEPS` evenly spaced values from `START` to `END`.

### full

```clausal
# skip
full(SHAPE, VALUE, T)
full(SHAPE, VALUE, OPTS, T)
```

Create a tensor filled with `VALUE`.

```clausal
# skip
full([2, 3], 7.0, T),
tensor_list(T, [[7.0, 7.0, 7.0], [7.0, 7.0, 7.0]])
```

### eye

```clausal
# skip
eye(N, T)
eye(N, M, T)
```

Create an identity matrix of size `N x N` or `N x M`.

---

## Tensor Properties (Multi-Mode)

These predicates support two modes:
- **Query mode** `(+T, -V)`: second arg unbound, returns the property
- **Check mode** `(+T, +V)`: both bound, succeeds only if the property matches

### shape

```clausal
# skip
shape(T, S)
```

Query or check the shape of a tensor. Shape is a list of integers.

```clausal
# skip
zeros([3, 4, 5], T),
shape(T, S),        # S = [3, 4, 5]
shape(T, [3, 4, 5]) # check mode: succeeds
```

### dtype

```clausal
# skip
dtype(T, D)
```

Query or check the data type of a tensor.

```clausal
# skip
zeros([2], T),
dtype(T, D),        # D = torch.float32
dtype(T, float32)   # check mode: succeeds
```

### device

```clausal
# skip
device(T, D)
```

Query or check the device of a tensor. Returns a string (`"cpu"`, `"cuda:0"`, etc.).

```clausal
# skip
zeros([2], T),
device(T, "cpu")    # check mode: succeeds
```

### dim

```clausal
# skip
dim(T, N)
```

Query the number of dimensions.

### element_count

```clausal
# skip
element_count(T, N)
```

Query the total number of elements.

### requires_gradient

```clausal
# skip
requires_gradient(T, B)
```

Query the gradient tracking flag (boolean).

### is_contiguous

```clausal
# skip
is_contiguous(T)
```

Succeeds if the tensor is contiguous in memory.

---

## Tensor Math

All math predicates are pure: they produce new tensors without mutating inputs.

### matmul

```clausal
# skip
matmul(A, B, C)
```

Matrix multiplication.

```clausal
# skip
zeros([2, 3], A),
zeros([3, 4], B),
matmul(A, B, C),
shape(C, [2, 4])
```

### add, mul

```clausal
# skip
add(A, B, C)
mul(A, B, C)
```

Element-wise addition and multiplication.

```clausal
# skip
tensor([1.0, 2.0, 3.0], A),
tensor([10.0, 20.0, 30.0], B),
add(A, B, C),
tensor_list(C, [11.0, 22.0, 33.0])
```

### cat, stack

```clausal
# skip
cat(TENSORS, DIM, T)
stack(TENSORS, DIM, T)
```

Concatenate or stack a list of tensors along a dimension.

```clausal
# skip
zeros([2, 3], A),
ones([2, 3], B),
cat([A, B], 0, C),
shape(C, [4, 3])
```

### sum, mean, max, min

```clausal
# skip
sum(T, S)
sum(T, DIM, S)
mean(T, M)
mean(T, DIM, M)
max(T, M)
max(T, DIM, M)
min(T, M)
min(T, DIM, M)
```

Reduction operations. Without `DIM`, reduces over all elements.
With `DIM`, reduces along that dimension. `max`/`min` along a dimension
return only the values (not indices).

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], T),
sum(T, S),
tensor_list(S, 10.0)

sum(T, 0, S2),
tensor_list(S2, [4.0, 6.0])
```

### clamp

```clausal
# skip
clamp(T, MIN, MAX, T2)
```

Clamp all values to `[MIN, MAX]`.

### abs

```clausal
# skip
abs(T, T2)
```

Element-wise absolute value.

### softmax

```clausal
# skip
softmax(T, DIM, T2)
```

Apply softmax along `DIM`.

### relu

```clausal
# skip
relu(T, T2)
```

Apply ReLU activation (zeroes negatives).

```clausal
# skip
tensor([-1.0, 0.0, 1.0], T),
relu(T, T2),
tensor_list(T2, [0.0, 0.0, 1.0])
```

---

## Shape Operations

### reshape

```clausal
# skip
reshape(T, SHAPE, T2)
```

Reshape a tensor to `SHAPE`.

### squeeze, unsqueeze

```clausal
# skip
squeeze(T, T2)
squeeze(T, DIM, T2)
unsqueeze(T, DIM, T2)
```

Remove or add size-1 dimensions. These are inverses of each other.

```clausal
# skip
zeros([3, 1, 4], T),
squeeze(T, 1, T2),
shape(T2, [3, 4]),
unsqueeze(T2, 1, T3),
shape(T3, [3, 1, 4])
```

### flatten, unflatten

```clausal
# skip
flatten(T, T2)
flatten(T, START, END, T2)
unflatten(T, DIM, SHAPE, T2)
```

Flatten or unflatten dimensions. These are inverses of each other.

```clausal
# skip
zeros([2, 3, 4], T),
flatten(T, 0, 1, FLAT),
shape(FLAT, [6, 4]),
unflatten(FLAT, 0, [2, 3], T2),
shape(T2, [2, 3, 4])
```

### transpose

```clausal
# skip
transpose(T, D0, D1, T2)
```

Swap two dimensions. Self-inverse: transposing twice returns the original.

### permute

```clausal
# skip
permute(T, DIMS, T2)
```

Reorder all dimensions.

### contiguous

```clausal
# skip
contiguous(T, T2)
```

Return a contiguous-in-memory copy of the tensor.

---

## Additional Shape Operations

### split

```clausal
# skip
split(T, SIZE, LIST)
split(T, SIZE, DIM, LIST)
```

Split a tensor into chunks of `SIZE` elements along `DIM` (default 0).
Returns a list of tensors. The last chunk may be smaller if the tensor
size is not divisible by `SIZE`. Inverse of `cat`.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], T),
split(T, 2, PARTS),
length(PARTS, 3),
cat(PARTS, 0, T2),
equal(T, T2)
```

### chunk

```clausal
# skip
chunk(T, N, LIST)
chunk(T, N, DIM, LIST)
```

Split a tensor into `N` chunks along `DIM` (default 0). If the tensor
size is not divisible by `N`, the last chunk will be smaller. Inverse
of `cat`.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], T),
chunk(T, 3, PARTS),
length(PARTS, 3)
```

### unbind

```clausal
# skip
unbind(T, DIM, LIST)
```

Remove dimension `DIM` and return a list of slices. Inverse of `stack`.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], T),
unbind(T, 0, ROWS),
length(ROWS, 2),
stack(ROWS, 0, T2),
equal(T, T2)
```

### narrow

```clausal
# skip
narrow(T, DIM, START, LENGTH, R)
```

Narrow a tensor along `DIM` from `START` for `LENGTH` elements.

```clausal
# skip
tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], T),
narrow(T, 1, 0, 2, R),
tensor_list(R, [[1.0, 2.0], [4.0, 5.0]])
```

### expand

```clausal
# skip
expand(T, SIZES, R)
```

Broadcast a tensor to a larger size. Use `-1` to keep a dimension
unchanged. Not invertible (lossy).

```clausal
# skip
tensor([[1.0], [2.0], [3.0]], T),
expand(T, [3, 4], R),
shape(R, [3, 4])
```

### repeat

```clausal
# skip
repeat(T, REPEATS, R)
```

Tile a tensor by repeating it along each dimension. Not invertible
(lossy).

```clausal
# skip
tensor([1.0, 2.0, 3.0], T),
repeat(T, [2], R),
tensor_list(R, [1.0, 2.0, 3.0, 1.0, 2.0, 3.0])
```

### tile

```clausal
# skip
tile(T, REPS, R)
```

Tile a tensor (numpy-style). Similar to `repeat` but follows NumPy
semantics for dimension handling. Not invertible (lossy).

```clausal
# skip
tensor([1.0, 2.0], T),
tile(T, [3], R),
tensor_list(R, [1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
```

### flip

```clausal
# skip
flip(T, DIMS, R)
```

Reverse the order of elements along the given dimensions. Self-inverse:
`flip(flip(T, DIMS), DIMS) == T`.

```clausal
# skip
tensor([1.0, 2.0, 3.0], T),
flip(T, [0], F),
tensor_list(F, [3.0, 2.0, 1.0]),
flip(F, [0], T2),
tensor_list(T2, [1.0, 2.0, 3.0])
```

### roll

```clausal
# skip
roll(T, SHIFTS, R)
roll(T, SHIFTS, DIMS, R)
```

Circular shift elements by `SHIFTS` positions. Roll by `n` is inverted
by roll by `-n`.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0], T),
roll(T, 1, R),
tensor_list(R, [4.0, 1.0, 2.0, 3.0]),
roll(R, -1, T2),
tensor_list(T2, [1.0, 2.0, 3.0, 4.0])
```

---

## Conversions (Bijective)

### tensor_list

```clausal
# skip
tensor_list(TENSOR, LIST)
```

Bidirectional conversion between a tensor and a nested Python list.

- `(+TENSOR, -LIST)`: convert tensor to list
- `(-TENSOR, +LIST)`: create tensor from list
- `(+TENSOR, +LIST)`: check consistency

```clausal
# skip
tensor([1.0, 2.0, 3.0], T),
tensor_list(T, L),
L == [1.0, 2.0, 3.0]

tensor_list(T2, [4.0, 5.0, 6.0]),
shape(T2, [3])
```

### tensor_numpy

```clausal
# skip
tensor_numpy(TENSOR, ARRAY)
```

Bidirectional relationship between a tensor and a NumPy array (shared memory).

- `(+TENSOR, -ARRAY)`: get the numpy array for a tensor
- `(-TENSOR, +ARRAY)`: get the tensor for a numpy array

```clausal
# skip
-import_module(numpy)
-import_from(py.torch, [tensor, tensor_numpy, tensor_list])

tensor_numpy(T, numpy.array([1.0, 2.0, 3.0])),
tensor_list(T, [1.0, 2.0, 3.0])
```

---

## Dtype Info

### dtype_info

```clausal
# skip
dtype_info(DTYPE, KEY, VALUE)
```

Query properties of a dtype. `DTYPE` must be bound (use an exported
dtype constant). `KEY` can be bound for a single lookup or unbound to
enumerate all properties.

Available keys: `"bits"`, `"is_floating_point"`, `"is_complex"`.

```clausal
# skip
-import_from(py.torch, [dtype_info, float32])

dtype_info(float32, "bits", BITS),     # BITS = 32
dtype_info(float32, "is_floating_point", True)
```

---

## IO (Impure)

These predicates perform file IO and are **not backtracking-safe**.

### save

```clausal
# skip
save(OBJ, PATH)
```

Save a tensor or model state to a file. Wraps `torch.save`.

### load

```clausal
# skip
load(PATH, OBJ)
```

Load a tensor or model state from a file. Wraps `torch.load`.
Fails (predicate failure, not crash) if the file doesn't exist.

```clausal
# skip
zeros([3, 4], T),
save(T, "/tmp/test.pt"),
load("/tmp/test.pt", T2),
shape(T2, [3, 4])
```

---

## Linear Algebra

Pure linear algebra operations via `torch.linalg`. All predicates are
Tier 1 (pure, no state). Decompositions return tuples — unpack with `is`.

```clausal
# skip
-import_from(py.torch, [tensor, eye, det, inv, svd, solve, cholesky,
                         qr, norm, matrix_rank, pinv, cross, dot])
```

### det

```clausal
# skip
det(A, D)
```

Compute the determinant of a square matrix.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], A),
det(A, D)
# D ≈ -2.0
```

### inv

```clausal
# skip
inv(A, B)
```

Compute the matrix inverse. Self-inverse: `inv(inv(A)) ≈ A`.
Fails on singular matrices.

```clausal
# skip
eye(3, I),
inv(I, B)
# B is the identity matrix
```

### solve

```clausal
# skip
solve(A, B, X)
```

Solve the linear system `AX = B`.

```clausal
# skip
eye(2, A),
tensor([3.0, 4.0], B),
solve(A, B, X)
# X = [3.0, 4.0]
```

### svd

```clausal
# skip
svd(A, RESULT)
```

Singular value decomposition. Returns a `(U, S, Vh)` tuple.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], A),
svd(A, RESULT),
RESULT is (U, S, VH),
shape(U, [2, 2]),
shape(S, [2]),
shape(VH, [2, 2])
```

### eig

```clausal
# skip
eig(A, RESULT)
```

Eigendecomposition. Returns a `(L, V)` tuple of eigenvalues and
eigenvectors. Eigenvalues may be complex.

```clausal
# skip
tensor([[1.0, 2.0], [2.0, 1.0]], A),
eig(A, RESULT),
RESULT is (L, V),
shape(L, [2]),
shape(V, [2, 2])
```

### cholesky

```clausal
# skip
cholesky(A, L)
```

Cholesky decomposition of a positive-definite matrix. `A = L @ L.T`.
Fails on non-positive-definite matrices.

```clausal
# skip
tensor([[4.0, 2.0], [2.0, 3.0]], A),
cholesky(A, L),
shape(L, [2, 2])
```

### qr

```clausal
# skip
qr(A, RESULT)
```

QR decomposition. Returns a `(Q, R)` tuple.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], A),
qr(A, RESULT),
RESULT is (Q, R),
shape(Q, [3, 2]),
shape(R, [2, 2])
```

### norm

```clausal
# skip
norm(A, N)
norm(A, ORD, N)
```

Matrix or vector norm. Without `ORD`, computes the Frobenius norm (matrix)
or 2-norm (vector). With `ORD`, computes the specified norm.

```clausal
# skip
tensor([3.0, 4.0], A),
norm(A, N)
# N = 5.0

norm(A, 1, N1)
# N1 = 7.0
```

### matrix_rank

```clausal
# skip
matrix_rank(A, R)
```

Compute the numerical rank of a matrix.

```clausal
# skip
eye(3, I),
matrix_rank(I, R)
# R = 3
```

### pinv

```clausal
# skip
pinv(A, B)
```

Moore-Penrose pseudoinverse. Works on any matrix shape.

```clausal
# skip
tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], A),
pinv(A, B),
shape(B, [3, 2])
```

### cross

```clausal
# skip
cross(A, B, C)
```

Cross product of two 3-element vectors.

```clausal
# skip
tensor([1.0, 0.0, 0.0], A),
tensor([0.0, 1.0, 0.0], B),
cross(A, B, C)
# C = [0.0, 0.0, 1.0]
```

### dot

```clausal
# skip
dot(A, B, C)
```

Dot product of two 1-D tensors.

```clausal
# skip
tensor([1.0, 2.0, 3.0], A),
tensor([4.0, 5.0, 6.0], B),
dot(A, B, C)
# C = 32.0
```

---

## FFT (Bijective Pairs)

Pure FFT operations via `torch.fft`. Each transform pair is a single
bidirectional predicate: `(+T, -F)` computes the forward transform,
`(-T, +F)` computes the inverse.

```clausal
# skip
-import_from(py.torch, [tensor, fft_transform, real_fft,
                         fft_transform_2d, fft_transform_nd,
                         fft_shift, fft_frequencies, real_fft_frequencies])
```

### fft_transform

```clausal
# skip
fft_transform(T, F)
fft_transform(T, DIM, F)
```

Bijective complex-to-complex FFT. Forward: `(+T, -F)`. Inverse: `(-T, +F)`.
Optional `DIM` specifies the dimension to transform along.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0], T),
fft_transform(T, F),
shape(F, [4]),
fft_transform(T2, F),
shape(T2, [4])
```

### real_fft

```clausal
# skip
real_fft(T, F)
real_fft(T, DIM, F)
```

Bijective real-to-complex FFT. Forward output length is `n//2 + 1`.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0], T),
real_fft(T, F),
shape(F, [3]),
real_fft(T2, F),
shape(T2, [4])
```

### fft_transform_2d

```clausal
# skip
fft_transform_2d(T, F)
```

Bijective 2-dimensional FFT.

### fft_transform_nd

```clausal
# skip
fft_transform_nd(T, F)
```

Bijective N-dimensional FFT. Transforms along all dimensions.

### fft_shift

```clausal
# skip
fft_shift(T, S)
```

Bijective zero-frequency shift. Forward shifts zero-freq to centre,
inverse shifts it back.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0], T),
fft_shift(T, S),
tensor_list(S, [3.0, 4.0, 1.0, 2.0]),
fft_shift(T2, S),
tensor_list(T2, [1.0, 2.0, 3.0, 4.0])
```

### fft_frequencies, real_fft_frequencies

```clausal
# skip
fft_frequencies(N, F)
fft_frequencies(N, D, F)
real_fft_frequencies(N, F)
real_fft_frequencies(N, D, F)
```

DFT sample frequencies (not bijective). `N` is the window length, `D`
is the sample spacing (default 1.0). `real_fft_frequencies` returns
`n//2 + 1` frequencies.

```clausal
# skip
fft_frequencies(4, F),
shape(F, [4])

real_fft_frequencies(4, F2),
shape(F2, [3])
```

---

## Comparisons

Element-wise comparison predicates. All return bool tensors.

### eq, ne, gt, lt, ge, le

```clausal
# skip
eq(A, B, C)
ne(A, B, C)
gt(A, B, C)
lt(A, B, C)
ge(A, B, C)
le(A, B, C)
```

Element-wise comparison, producing a bool tensor.

```clausal
# skip
tensor([1.0, 5.0, 3.0], A),
tensor([2.0, 2.0, 3.0], B),
gt(A, B, C),
tensor_list(C, [False, True, False])
```

### equal

```clausal
# skip
equal(A, B)
```

Check predicate: succeeds if all elements of `A` and `B` are equal.
No output variable — use `not(equal(A, B))` for inequality check.

### allclose

```clausal
# skip
allclose(A, B)
allclose(A, B, ATOL, RTOL)
```

Check predicate: succeeds if tensors are approximately equal.
Optional `ATOL` (absolute tolerance) and `RTOL` (relative tolerance).

```clausal
# skip
tensor([1.0, 2.0], A),
tensor([1.01, 2.01], B),
allclose(A, B, 0.1, 0.0)
```

---

## Logical Operations

### logical_and, logical_or, logical_xor

```clausal
# skip
logical_and(A, B, C)
logical_or(A, B, C)
logical_xor(A, B, C)
```

Element-wise logical operations on bool tensors.

### logical_not

```clausal
# skip
logical_not(A, B)
```

Element-wise logical NOT.

### any, all

```clausal
# skip
any(T)
any(T, DIM)
all(T)
all(T, DIM)
```

Check predicates: succeed if any/all elements are true.
With `DIM`, checks along that dimension (succeeds if the condition
holds for at least one slice).

```clausal
# skip
tensor([False, True, False], T),
any(T)    # succeeds

tensor([True, True, True], T2),
all(T2)   # succeeds
```

---

## Selection

### where

```clausal
# skip
where(COND, X, Y, R)
```

Select elements from `X` where `COND` is true, from `Y` where false.

```clausal
# skip
tensor([True, False, True], COND),
tensor([1.0, 2.0, 3.0], X),
tensor([10.0, 20.0, 30.0], Y),
where(COND, X, Y, R),
tensor_list(R, [1.0, 20.0, 3.0])
```

### masked_select

```clausal
# skip
masked_select(T, MASK, R)
```

Select elements where `MASK` is true. Returns a 1-D tensor.

### index_select

```clausal
# skip
index_select(T, DIM, INDICES, R)
```

Select slices along `DIM` at the given `INDICES`.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], T),
tensor([0, 2], IDX),
index_select(T, 0, IDX, R),
tensor_list(R, [[1.0, 2.0], [5.0, 6.0]])
```

### gather

```clausal
# skip
gather(T, DIM, INDICES, R)
```

Gather values along `DIM` using index tensor.

### scatter

```clausal
# skip
scatter(T, DIM, INDICES, SRC, R)
```

Scatter `SRC` values into `T` at positions given by `INDICES` along `DIM`.

---

## Einsum

### einsum

```clausal
# skip
einsum(EQUATION, TENSORS, RESULT)
```

Einstein summation notation. `EQUATION` is a string like `"ij,jk->ik"`,
`TENSORS` is a list of tensors.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], A),
tensor([[5.0, 6.0], [7.0, 8.0]], B),
einsum("ij,jk->ik", [A, B], C),
shape(C, [2, 2])

# Trace
einsum("ii->", [A], T)
# T = 5.0

# Outer product
tensor([1.0, 2.0], X),
tensor([3.0, 4.0, 5.0], Y),
einsum("i,j->ij", [X, Y], O),
shape(O, [2, 3])
```

---

## Advanced Math (Bijective)

These predicates are bidirectional — bind either argument and the other
is computed. Uses `_bidir_2` internally.

### logarithm

```clausal
# skip
logarithm(EXPONENT, VALUE)
```

`VALUE = exp(EXPONENT)`. Forward: exp. Backward: log.

```clausal
# skip
tensor([0.0, 1.0], EXP),
logarithm(EXP, VAL)
# VAL = [1.0, e]

tensor([1.0, 2.0], VAL2),
logarithm(EXP2, VAL2)
# EXP2 = [0.0, ln(2)]
```

### sine

```clausal
# skip
sine(ANGLE, VALUE)
```

Forward: sin. Backward: asin. Domain for backward: `VALUE` in [-1, 1].

### cosine

```clausal
# skip
cosine(ANGLE, VALUE)
```

Forward: cos. Backward: acos.

### tangent

```clausal
# skip
tangent(ANGLE, VALUE)
```

Forward: tan. Backward: atan.

---

## Advanced Math (Non-Bijective)

One-directional predicates — all inputs must be bound.

### sqrt

```clausal
# skip
sqrt(T, R)
```

Element-wise square root.

### pow

```clausal
# skip
pow(T, EXPONENT, R)
```

Element-wise power.

```clausal
# skip
tensor([2.0, 3.0], T),
pow(T, 2.0, R)
# R = [4.0, 9.0]
```

### atan2

```clausal
# skip
atan2(Y, X, R)
```

Two-argument arctangent.

### sinh, cosh, tanh

```clausal
# skip
sinh(T, R)
cosh(T, R)
tanh(T, R)
```

Hyperbolic functions.

### sigmoid

```clausal
# skip
sigmoid(T, R)
```

Logistic sigmoid. Output in (0, 1).

```clausal
# skip
tensor([0.0], T),
sigmoid(T, R)
# R = [0.5]
```

### log_softmax

```clausal
# skip
log_softmax(T, DIM, R)
```

Log of softmax along `DIM`. Numerically more stable than
`log(softmax(T))`.

### floor, ceil, round

```clausal
# skip
floor(T, R)
ceil(T, R)
round(T, R)
```

Rounding operations. Not invertible.

```clausal
# skip
tensor([1.7, 2.3, -0.5], T),
floor(T, R)
# R = [1.0, 2.0, -1.0]
```

### sign

```clausal
# skip
sign(T, R)
```

Sign function: returns -1, 0, or +1 per element.

### cumsum, cumprod

```clausal
# skip
cumsum(T, DIM, R)
cumprod(T, DIM, R)
```

Cumulative sum/product along `DIM`.

```clausal
# skip
tensor([1.0, 2.0, 3.0, 4.0], T),
cumsum(T, 0, R)
# R = [1.0, 3.0, 6.0, 10.0]

cumprod(T, 0, P)
# P = [1.0, 2.0, 6.0, 24.0]
```

---

## Creation Variants (Phase 13)

### zeros_like, ones_like, full_like

```clausal
# skip
zeros_like(T, R)
ones_like(T, R)
full_like(T, VALUE, R)
```

Create tensors with the same shape, dtype, and device as an existing tensor.

```clausal
# skip
tensor([[1.0, 2.0], [3.0, 4.0]], T),
zeros_like(T, Z),
shape(Z, [2, 2])
# Z has same dtype and device as T
```

### empty

```clausal
# skip
empty(SHAPE, T)
empty(SHAPE, OPTS, T)
```

Create an uninitialized tensor. Values are indeterminate.

### rand, randint

```clausal
# skip
rand(SHAPE, T)
rand(SHAPE, OPTS, T)
randint(LOW, HIGH, SHAPE, T)
randint(LOW, HIGH, SHAPE, OPTS, T)
```

`rand` produces uniform random values in `[0, 1)`.
`randint` produces random integers in `[LOW, HIGH)`.

```clausal
# skip
rand([3, 4], T),
shape(T, [3, 4])

randint(0, 10, [5], T)
# T contains integers 0..9
```

### logspace

```clausal
# skip
logspace(START, END, STEPS, T)
logspace(START, END, STEPS, OPTS, T)
```

Logarithmically spaced values: `10^START` to `10^END`.

```clausal
# skip
logspace(0.0, 2.0, 3, T)
# T = [1.0, 10.0, 100.0]
```

### diag

```clausal
# skip
diag(T, R)
diag(T, DIAGONAL, R)
```

Input-polymorphic: if input is 1D, creates a 2D diagonal matrix.
If input is 2D, extracts the diagonal. This is forward-only — you
cannot bind the output and recover the input. Optional `DIAGONAL`
offset (default 0, positive = above main diagonal, negative = below).

```clausal
# skip
tensor([1.0, 2.0, 3.0], V),
diag(V, M),
shape(M, [3, 3])

tensor([[1.0, 2.0], [3.0, 4.0]], M),
diag(M, V)
# V = [1.0, 4.0]
```

---

## Arithmetic Gaps (Phase 13)

### sub

```clausal
# skip
sub(A, B, C)
```

Element-wise subtraction: `C = A - B`.

### div

```clausal
# skip
div(A, B, C)
```

Element-wise division: `C = A / B`.

### neg

```clausal
# skip
neg(T, R)
```

Element-wise negation: `R = -T`.

```clausal
# skip
tensor([5.0, 3.0], A),
tensor([2.0, 1.0], B),
sub(A, B, C)
# C = [3.0, 2.0]

tensor([1.0, -2.0, 3.0], T),
neg(T, R)
# R = [-1.0, 2.0, -3.0]
```

---

## Design Notes

1. **`shape/2`, `dtype/2`, `device/2` in `(+T, +S)` mode are check-only.**
   They don't reshape/cast/transfer.

2. **No in-place operations.** The wrapper exposes only functional
   (non-mutating) forms. In-place operations (`add_`, `mul_`, etc.) break
   backtracking.

3. **GPU tensor equality.** PyTorch's `==` is element-wise, not scalar.
   Use `tensor_list` to compare tensor contents in tests.

4. **Dtype constants.** Common dtypes (`float32`, `float64`, `int32`, etc.)
   are exported directly from `py.torch` and can be imported by name —
   no `++()` escape needed.
