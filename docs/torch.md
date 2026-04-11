# torch — PyTorch Tensor Operations

Provides pure tensor operations from PyTorch as [importable](import.md)
clausal predicates. Phase 1 covers tensor creation, properties, math,
shape operations, and conversions.

## Import

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:import"
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
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor"
```

Create a tensor from a Python list or nested list.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor_ex2"
```

### zeros, ones

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:zeros_ones"
```

Create zero/one-filled tensors. `OPTS` is a dict for `dtype`/`device` kwargs.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:zeros_ones_ex2"
```

### randn

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:randn"
```

Create a tensor filled with values from a standard normal distribution.

### arange

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:arange"
```

Create a 1-D tensor with values from a range.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:arange_ex2"
```

### linspace

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:linspace"
```

Create a 1-D tensor with `STEPS` evenly spaced values from `START` to `END`.

### full

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:full"
```

Create a tensor filled with `VALUE`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:full_ex2"
```

### eye

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:eye"
```

Create an identity matrix of size `N x N` or `N x M`.

---

## Tensor Properties (Multi-Mode)

These predicates support two modes:
- **Query mode** `(+T, -V)`: second arg unbound, returns the property
- **Check mode** `(+T, +V)`: both bound, succeeds only if the property matches

### shape

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:shape"
```

Query or check the shape of a tensor. Shape is a list of integers.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:shape_ex2"
```

### dtype

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dtype"
```

Query or check the data type of a tensor.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dtype_ex2"
```

### device

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:device"
```

Query or check the device of a tensor. Returns a string (`"cpu"`, `"cuda:0"`, etc.).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:device_ex2"
```

### dim

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dim"
```

Query the number of dimensions.

### element_count

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:element_count"
```

Query the total number of elements.

### requires_gradient

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:requires_gradient"
```

Query the gradient tracking flag (boolean).

### is_contiguous

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:is_contiguous"
```

Succeeds if the tensor is contiguous in memory.

---

## Tensor Math

All math predicates are pure: they produce new tensors without mutating inputs.

### matmul

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:matmul"
```

Matrix multiplication.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:matmul_ex2"
```

### add, mul

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:add_mul"
```

Element-wise addition and multiplication.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:add_mul_ex2"
```

### cat, stack

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cat_stack"
```

Concatenate or stack a list of tensors along a dimension.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cat_stack_ex2"
```

### sum, mean, max, min

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sum_mean_max_min"
```

Reduction operations. Without `DIM`, reduces over all elements.
With `DIM`, reduces along that dimension. `max`/`min` along a dimension
return only the values (not indices).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sum_mean_max_min_ex2"
```

### clamp

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:clamp"
```

Clamp all values to `[MIN, MAX]`.

### abs

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:abs"
```

Element-wise absolute value.

### softmax

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:softmax"
```

Apply softmax along `DIM`.

### relu

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:relu"
```

Apply ReLU activation (zeroes negatives).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:relu_ex2"
```

---

## Shape Operations

### reshape

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:reshape"
```

Reshape a tensor to `SHAPE`.

### squeeze, unsqueeze

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:squeeze_unsqueeze"
```

Remove or add size-1 dimensions. These are inverses of each other.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:squeeze_unsqueeze_ex2"
```

### flatten, unflatten

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:flatten_unflatten"
```

Flatten or unflatten dimensions. These are inverses of each other.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:flatten_unflatten_ex2"
```

### transpose

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:transpose"
```

Swap two dimensions. Self-inverse: transposing twice returns the original.

### permute

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:permute"
```

Reorder all dimensions.

### contiguous

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:contiguous"
```

Return a contiguous-in-memory copy of the tensor.

---

## Additional Shape Operations

### split

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:split"
```

Split a tensor into chunks of `SIZE` elements along `DIM` (default 0).
Returns a list of tensors. The last chunk may be smaller if the tensor
size is not divisible by `SIZE`. Inverse of `cat`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:split_ex2"
```

### chunk

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:chunk"
```

Split a tensor into `N` chunks along `DIM` (default 0). If the tensor
size is not divisible by `N`, the last chunk will be smaller. Inverse
of `cat`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:chunk_ex2"
```

### unbind

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:unbind"
```

Remove dimension `DIM` and return a list of slices. Inverse of `stack`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:unbind_ex2"
```

### narrow

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:narrow"
```

Narrow a tensor along `DIM` from `START` for `LENGTH` elements.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:narrow_ex2"
```

### expand

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:expand"
```

Broadcast a tensor to a larger size. Use `-1` to keep a dimension
unchanged. Not invertible (lossy).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:expand_ex2"
```

### repeat

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:repeat"
```

Tile a tensor by repeating it along each dimension. Not invertible
(lossy).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:repeat_ex2"
```

### tile

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tile"
```

Tile a tensor (numpy-style). Similar to `repeat` but follows NumPy
semantics for dimension handling. Not invertible (lossy).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tile_ex2"
```

### flip

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:flip"
```

Reverse the order of elements along the given dimensions. Self-inverse:
`flip(flip(T, DIMS), DIMS) == T`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:flip_ex2"
```

### roll

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:roll"
```

Circular shift elements by `SHIFTS` positions. Roll by `n` is inverted
by roll by `-n`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:roll_ex2"
```

---

## Conversions (Bijective)

### tensor_list

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor_list"
```

Bidirectional conversion between a tensor and a nested Python list.

- `(+TENSOR, -LIST)`: convert tensor to list
- `(-TENSOR, +LIST)`: create tensor from list
- `(+TENSOR, +LIST)`: check consistency

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor_list_ex2"
```

### tensor_numpy

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor_numpy"
```

Bidirectional relationship between a tensor and a NumPy array (shared memory).

- `(+TENSOR, -ARRAY)`: get the numpy array for a tensor
- `(-TENSOR, +ARRAY)`: get the tensor for a numpy array

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tensor_numpy_ex2"
```

---

## Dtype Info

### dtype_info

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dtype_info"
```

Query properties of a dtype. `DTYPE` must be bound (use an exported
dtype constant). `KEY` can be bound for a single lookup or unbound to
enumerate all properties.

Available keys: `"bits"`, `"is_floating_point"`, `"is_complex"`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dtype_info_ex2"
```

---

## IO (Impure)

These predicates perform file IO and are **not backtracking-safe**.

### save

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:save"
```

Save a tensor or model state to a file. Wraps `torch.save`.

### load

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:load"
```

Load a tensor or model state from a file. Wraps `torch.load`.
Fails (predicate failure, not crash) if the file doesn't exist.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:load_ex2"
```

---

## Linear Algebra

Pure linear algebra operations via `torch.linalg`. All predicates are
Tier 1 (pure, no state). Decompositions return tuples — unpack with `is`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:linear_algebra"
```

### det

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:det"
```

Compute the determinant of a square matrix.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:det_ex2"
```

### inv

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:inv"
```

Compute the matrix inverse. Self-inverse: `inv(inv(A)) ≈ A`.
Fails on singular matrices.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:inv_ex2"
```

### solve

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:solve"
```

Solve the linear system `AX = B`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:solve_ex2"
```

### svd

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:svd"
```

Singular value decomposition. Returns a `(U, S, Vh)` tuple.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:svd_ex2"
```

### eig

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:eig"
```

Eigendecomposition. Returns a `(L, V)` tuple of eigenvalues and
eigenvectors. Eigenvalues may be complex.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:eig_ex2"
```

### cholesky

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cholesky"
```

Cholesky decomposition of a positive-definite matrix. `A = L @ L.T`.
Fails on non-positive-definite matrices.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cholesky_ex2"
```

### qr

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:qr"
```

QR decomposition. Returns a `(Q, R)` tuple.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:qr_ex2"
```

### norm

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:norm"
```

Matrix or vector norm. Without `ORD`, computes the Frobenius norm (matrix)
or 2-norm (vector). With `ORD`, computes the specified norm.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:norm_ex2"
```

### matrix_rank

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:matrix_rank"
```

Compute the numerical rank of a matrix.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:matrix_rank_ex2"
```

### pinv

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:pinv"
```

Moore-Penrose pseudoinverse. Works on any matrix shape.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:pinv_ex2"
```

### cross

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cross"
```

Cross product of two 3-element vectors.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cross_ex2"
```

### dot

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dot"
```

Dot product of two 1-D tensors.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:dot_ex2"
```

---

## FFT (Bijective Pairs)

Pure FFT operations via `torch.fft`. Each transform pair is a single
bidirectional predicate: `(+T, -F)` computes the forward transform,
`(-T, +F)` computes the inverse.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_bijective_pairs"
```

### fft_transform

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_transform"
```

Bijective complex-to-complex FFT. Forward: `(+T, -F)`. Inverse: `(-T, +F)`.
Optional `DIM` specifies the dimension to transform along.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_transform_ex2"
```

### real_fft

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:real_fft"
```

Bijective real-to-complex FFT. Forward output length is `n//2 + 1`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:real_fft_ex2"
```

### fft_transform_2d

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_transform_2d"
```

Bijective 2-dimensional FFT.

### fft_transform_nd

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_transform_nd"
```

Bijective N-dimensional FFT. Transforms along all dimensions.

### fft_shift

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_shift"
```

Bijective zero-frequency shift. Forward shifts zero-freq to centre,
inverse shifts it back.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_shift_ex2"
```

### fft_frequencies, real_fft_frequencies

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_frequencies_real_fft_frequencies"
```

DFT sample frequencies (not bijective). `N` is the window length, `D`
is the sample spacing (default 1.0). `real_fft_frequencies` returns
`n//2 + 1` frequencies.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:fft_frequencies_real_fft_frequencies_ex2"
```

---

## Comparisons

Element-wise comparison predicates. All return bool tensors.

### eq, ne, gt, lt, ge, le

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:eq_ne_gt_lt_ge_le"
```

Element-wise comparison, producing a bool tensor.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:eq_ne_gt_lt_ge_le_ex2"
```

### equal

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:equal"
```

Check predicate: succeeds if all elements of `A` and `B` are equal.
No output variable — use `not(equal(A, B))` for inequality check.

### allclose

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:allclose"
```

Check predicate: succeeds if tensors are approximately equal.
Optional `ATOL` (absolute tolerance) and `RTOL` (relative tolerance).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:allclose_ex2"
```

---

## Logical Operations

### logical_and, logical_or, logical_xor

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logical_and_logical_or_logical_xor"
```

Element-wise logical operations on bool tensors.

### logical_not

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logical_not"
```

Element-wise logical NOT.

### any, all

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:any_all"
```

Check predicates: succeed if any/all elements are true.
With `DIM`, checks along that dimension (succeeds if the condition
holds for at least one slice).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:any_all_ex2"
```

---

## Selection

### where

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:where"
```

Select elements from `X` where `COND` is true, from `Y` where false.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:where_ex2"
```

### masked_select

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:masked_select"
```

Select elements where `MASK` is true. Returns a 1-D tensor.

### index_select

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:index_select"
```

Select slices along `DIM` at the given `INDICES`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:index_select_ex2"
```

### gather

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:gather"
```

Gather values along `DIM` using index tensor.

### scatter

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:scatter"
```

Scatter `SRC` values into `T` at positions given by `INDICES` along `DIM`.

---

## Einsum

### einsum

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:einsum"
```

Einstein summation notation. `EQUATION` is a string like `"ij,jk->ik"`,
`TENSORS` is a list of tensors.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:einsum_ex2"
```

---

## Advanced Math (Bijective)

These predicates are bidirectional — bind either argument and the other
is computed. Uses `_bidir_2` internally.

### logarithm

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logarithm"
```

`VALUE = exp(EXPONENT)`. Forward: exp. Backward: log.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logarithm_ex2"
```

### sine

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sine"
```

Forward: sin. Backward: asin. Domain for backward: `VALUE` in [-1, 1].

### cosine

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cosine"
```

Forward: cos. Backward: acos.

### tangent

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:tangent"
```

Forward: tan. Backward: atan.

---

## Advanced Math (Non-Bijective)

One-directional predicates — all inputs must be bound.

### sqrt

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sqrt"
```

Element-wise square root.

### pow

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:pow"
```

Element-wise power.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:pow_ex2"
```

### atan2

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:atan2"
```

Two-argument arctangent.

### sinh, cosh, tanh

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sinh_cosh_tanh"
```

Hyperbolic functions.

### sigmoid

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sigmoid"
```

Logistic sigmoid. Output in (0, 1).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sigmoid_ex2"
```

### log_softmax

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:log_softmax"
```

Log of softmax along `DIM`. Numerically more stable than
`log(softmax(T))`.

### floor, ceil, round

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:floor_ceil_round"
```

Rounding operations. Not invertible.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:floor_ceil_round_ex2"
```

### sign

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sign"
```

Sign function: returns -1, 0, or +1 per element.

### cumsum, cumprod

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cumsum_cumprod"
```

Cumulative sum/product along `DIM`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:cumsum_cumprod_ex2"
```

---

## Creation Variants (Phase 13)

### zeros_like, ones_like, full_like

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:zeros_like_ones_like_full_like"
```

Create tensors with the same shape, dtype, and device as an existing tensor.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:zeros_like_ones_like_full_like_ex2"
```

### empty

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:empty"
```

Create an uninitialized tensor. Values are indeterminate.

### rand, randint

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:rand_randint"
```

`rand` produces uniform random values in `[0, 1)`.
`randint` produces random integers in `[LOW, HIGH)`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:rand_randint_ex2"
```

### logspace

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logspace"
```

Logarithmically spaced values: `10^START` to `10^END`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:logspace_ex2"
```

### diag

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:diag"
```

Input-polymorphic: if input is 1D, creates a 2D diagonal matrix.
If input is 2D, extracts the diagonal. This is forward-only — you
cannot bind the output and recover the input. Optional `DIAGONAL`
offset (default 0, positive = above main diagonal, negative = below).

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:diag_ex2"
```

---

## Arithmetic Gaps (Phase 13)

### sub

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sub"
```

Element-wise subtraction: `C = A - B`.

### div

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:div"
```

Element-wise division: `C = A / B`.

### neg

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:neg"
```

Element-wise negation: `R = -T`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:neg_ex2"
```

---

## Statistical Reductions (Phase 14)

### median

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:median"
```

Without `DIM`, returns the median scalar. With `DIM`, returns a
`(values, indices)` tuple — decompose with `RESULT is (VALS, IDXS)`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:median_ex2"
```

### std, var

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:std_var"
```

Standard deviation and variance. Without `DIM`, reduces over all
elements. With `DIM`, reduces along that dimension.

---

## Selection and Sorting (Phase 14)

### argmin, argmax

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:argmin_argmax"
```

Without `DIM`, returns the index into the flattened tensor. With `DIM`,
returns a tensor of indices along that dimension.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:argmin_argmax_ex2"
```

### sort

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sort"
```

Returns a `(values, indices)` tuple. Decompose with `RESULT is (VALS, IDXS)`.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:sort_ex2"
```

### argsort

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:argsort"
```

Returns indices that would sort the tensor.

### topk

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:topk"
```

Returns `(values, indices)` tuple of the `K` largest elements.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:topk_ex2"
```

### nonzero

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:nonzero"
```

Returns a 2D tensor of shape `(N, ndim)` where each row is the index
of a nonzero element.

### unique

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:unique"
```

Returns unique elements, sorted.

```clausal
--8<-- "tests/fixtures/docs/torch_sigs.txt:unique_ex2"
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
