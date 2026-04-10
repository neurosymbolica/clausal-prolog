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
