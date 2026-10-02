# `opencv_imgproc` — Filtering and morphology

Smoothing, convolution, edge detection, morphology, and image
pyramids — the workhorse predicates of classical image processing.
Plus four name ↔ code registries for the most-used flag families:
`interpolation`, `border_type`, `morph_op`, `morph_shape`.

All predicates are **Tier 1 (pure)**. Each takes one or more NumPy
arrays and returns a fresh array; backtracking simply abandons the
output.

```clausal
-import_from(opencv_imgproc, [
    gaussian_blur, median_blur, sobel, canny,
    get_structuring_element, morphology_ex,
    pyr_down, pyr_up,
    interpolation, border_type, morph_op, morph_shape,
])
-import_from(opencv, [
    inter_cubic, border_reflect, morph_rect, morph_open, cv_8u,
])
```

## Predicate index

### Smoothing

| Predicate | Arity | Notes |
|---|---|---|
| `gaussian_blur(IMG, KSIZE, OUT)` | /3 | Default sigma=0 (computed from KSIZE) |
| `gaussian_blur(IMG, KSIZE, SIGMA, OUT)` | /4 | Explicit sigma (same in both axes) |
| `gaussian_blur(IMG, KSIZE, SIGMA_X, SIGMA_Y, OUT)` | /5 | Per-axis sigma |
| `median_blur(IMG, KSIZE, OUT)` | /3 | KSIZE is an int, must be odd ≥ 3 |
| `box_filter(IMG, DDEPTH, KSIZE, OUT)` | /4 | |
| `bilateral_filter(IMG, D, SIGMA_COLOR, SIGMA_SPACE, OUT)` | /5 | Edge-preserving |

`KSIZE` accepts a 2-element list `[w, h]`. For square kernels write
`[3, 3]`. Internally the wrapper coerces to a 2-tuple for cv2.

### Convolution

| Predicate | Arity | Notes |
|---|---|---|
| `filter_2d(IMG, DDEPTH, KERNEL, OUT)` | /4 | `cv2.filter2D` — 2-D correlation |
| `sep_filter_2d(IMG, DDEPTH, KERNEL_X, KERNEL_Y, OUT)` | /5 | Separable 2-D |

`KERNEL` is a numpy ndarray (typically `float32`).

### Edge detection

| Predicate | Arity | Notes |
|---|---|---|
| `sobel(IMG, DDEPTH, DX, DY, OUT)` | /5 | Default ksize=3 |
| `sobel(IMG, DDEPTH, DX, DY, KSIZE, OUT)` | /6 | |
| `scharr(IMG, DDEPTH, DX, DY, OUT)` | /5 | Like sobel but a fixed 3×3 kernel |
| `laplacian(IMG, DDEPTH, OUT)` | /3 | Default ksize=1 |
| `laplacian(IMG, DDEPTH, KSIZE, OUT)` | /4 | |
| `canny(IMG, T1, T2, OUT)` | /4 | Default apertureSize=3 |
| `canny(IMG, T1, T2, APERTURE, OUT)` | /5 | |

For Sobel/Scharr/Laplacian, prefer a signed output type like `cv_16s`
or `cv_32f` since gradients can be negative.

### Morphology

| Predicate | Arity | Notes |
|---|---|---|
| `get_structuring_element(SHAPE, KSIZE, KERNEL)` | /3 | Anchor defaults to `(-1, -1)` (centre) |
| `get_structuring_element(SHAPE, KSIZE, ANCHOR, KERNEL)` | /4 | Explicit anchor |
| `erode(IMG, KERNEL, OUT)` | /3 | Default iterations=1 |
| `erode(IMG, KERNEL, ITERATIONS, OUT)` | /4 | |
| `dilate(IMG, KERNEL, OUT)` | /3 | |
| `dilate(IMG, KERNEL, ITERATIONS, OUT)` | /4 | |
| `morphology_ex(IMG, OP, KERNEL, OUT)` | /4 | OP is `morph_open`, `morph_close`, … |
| `morphology_ex(IMG, OP, KERNEL, ITERATIONS, OUT)` | /5 | |

### Pyramids

| Predicate | Arity | Notes |
|---|---|---|
| `pyr_down(IMG, OUT)` | /2 | Default dstsize = `((W+1)//2, (H+1)//2)` |
| `pyr_down(IMG, DSTSIZE, OUT)` | /3 | DSTSIZE is `[W, H]` (OpenCV order) |
| `pyr_up(IMG, OUT)` | /2 | Default dstsize = `(W*2, H*2)` |
| `pyr_up(IMG, DSTSIZE, OUT)` | /3 | |

### Registries

| Registry | Names |
|---|---|
| `interpolation/2` | `nearest`, `linear`, `cubic`, `area`, `lanczos4` |
| `border_type/2` | `constant`, `replicate`, `reflect`, `reflect_101`, `wrap`, `isolated` |
| `morph_op/2` | `erode`, `dilate`, `open`, `close`, `gradient`, `tophat`, `blackhat`, `hitmiss` |
| `morph_shape/2` | `rect`, `ellipse`, `cross` |

Each registry supports all four modes: `(+name, -code)`, `(-name, +code)`,
`(-name, -code)` (enumeration), `(+name, +code)` (check).

When the flag is known at code-write time, the lowercase constants
from `opencv` (`inter_cubic`, `border_reflect`, `morph_open`, …) are
the more direct choice. The registries are for **name-as-data**
workflows — reading a flag from a config file or user input.

## Worked examples

Examples below are exact copies of the integration tests under
`tests/fixtures/opencv_phase3_filtering.seam`.

### Gaussian blur with explicit sigma

```clausal
imread("photo.png", imread_grayscale, IMG),
gaussian_blur(IMG, [3, 3], 1.0, OUT),
shape(IMG, S),
shape(OUT, S)
```

### filter_2d with identity kernel is identity

```clausal
imread("photo.png", imread_grayscale, IMG),
K_IDENT is ++(numpy.array([[0,0,0],[0,1,0],[0,0,0]], dtype=numpy.float32)),
filter_2d(IMG, cv_8u, K_IDENT, OUT),
absdiff(IMG, OUT, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### Sobel on grayscale with signed output

```clausal
imread("photo.png", imread_grayscale, IMG),
sobel(IMG, cv_16s, 1, 0, OUT),
shape(IMG, S),
shape(OUT, S)
```

### Canny edges

```clausal
imread("photo.png", imread_grayscale, IMG),
canny(IMG, 50.0, 150.0, EDGES),
is_grayscale(EDGES)
```

### `morphology_ex open` equals erode-then-dilate

```clausal
imread("photo.png", imread_grayscale, IMG),
get_structuring_element(morph_rect, [3, 3], K),
erode(IMG, K, ER),
dilate(ER, K, OPEN_BY_HAND),
morphology_ex(IMG, morph_open, K, OPEN_BY_PRED),
absdiff(OPEN_BY_HAND, OPEN_BY_PRED, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### Image pyramids

```clausal
imread("photo.png", imread_color, IMG),
pyr_down(IMG, DOWN),
pyr_up(DOWN, REBUILT),
shape(IMG, S),
shape(REBUILT, S)
```

### Look up an interpolation flag by name

```clausal
interpolation("cubic", C),
C == inter_cubic
```

### Enumerate all border types

```clausal
findall(N, border_type(N, _), NAMES),
length(NAMES, 6)
```

## Thresholding (Phase 4)

Two predicates exposed from this same module:

| Predicate | Arity | Description |
|---|---|---|
| `threshold(IMG, THRESH, MAXVAL, TYPE, USED, OUT)` | /6 | `cv2.threshold` returning both the level used and the binary output |
| `adaptive_threshold(IMG, MAXVAL, AM, TT, BLOCK, C, OUT)` | /7 | `cv2.adaptiveThreshold` |

For `threshold/6` the `USED` output carries the level **actually
applied** by cv2 — which equals `THRESH` for plain modes like
`thresh_binary`, but is the **computed level** when `thresh_otsu` or
`thresh_triangle` is used. Pass `_` for `USED` when you don't care.

`thresh_otsu` and `thresh_triangle` are normally OR-ed with another
mode in C++ (`THRESH_BINARY | THRESH_OTSU`). In Clausal, **pass them
alone or precompute the OR'd value as an int literal** — Clausal
doesn't evaluate `thresh_binary + thresh_otsu` in goal-arg position
(see Phase 4 Issues). `thresh_otsu` alone already implies
`thresh_binary`, so it's the recommended form for the common case.

### Thresholding examples

```clausal
imread("photo.png", imread_grayscale, IMG),
threshold(IMG, 128.0, 255.0, thresh_binary, USED, OUT),
USED == 128.0,
is_grayscale(OUT)
```

```clausal
imread("photo.png", imread_grayscale, IMG),
threshold(IMG, 0.0, 255.0, thresh_otsu, USED, OUT),
USED >= 0.0,
USED <= 255.0
```

```clausal
imread("photo.png", imread_grayscale, IMG),
adaptive_threshold(IMG, 255.0, adaptive_thresh_mean_c, thresh_binary,
                   3, 0.0, OUT)
```

The `threshold_type/2` registry lives in
[`opencv_contours`](opencv_contours.md) — there's no architectural
reason for the split, just that the contours module is where Phase 4
puts the smaller per-phase registry alongside the contour predicates.

## Geometric transformations (Phase 5)

Resize, warp (affine and perspective), rotate by 90°/180°/270°,
build transform matrices, invert affine matrices, remap, and pad.

| Predicate | Arity | Description |
|---|---|---|
| `resize(IMG, DSIZE, OUT)` | /3 | Default INTER_LINEAR. `DSIZE = [W, H]` |
| `resize(IMG, DSIZE, INTERP, OUT)` | /4 | |
| `resize_factor(IMG, FX, FY, OUT)` | /4 | Scale-factor variant |
| `resize_factor(IMG, FX, FY, INTERP, OUT)` | /5 | |
| `warp_affine(IMG, M, DSIZE, OUT)` | /4 | M is 2×3 |
| `warp_affine(IMG, M, DSIZE, FLAGS, OUT)` | /5 | |
| `warp_affine(IMG, M, DSIZE, FLAGS, BORDER, OUT)` | /6 | |
| `warp_affine(IMG, M, DSIZE, FLAGS, BORDER, VALUE, OUT)` | /7 | VALUE is a per-channel scalar list |
| `warp_perspective(IMG, M, DSIZE, OUT)` | /4 | M is 3×3 |
| `warp_perspective(IMG, M, DSIZE, FLAGS, OUT)` | /5 | |
| `warp_perspective(IMG, M, DSIZE, FLAGS, BORDER, OUT)` | /6 | |
| `warp_perspective(IMG, M, DSIZE, FLAGS, BORDER, VALUE, OUT)` | /7 | |
| `rotate(IMG, ROTATE_CODE, OUT)` | /3 | 90°/180°/270° lossless |
| `get_rotation_matrix_2d(CENTER, ANGLE_DEG, SCALE, M)` | /4 | Returns a 2×3 |
| `get_affine_transform(SRC_PTS, DST_PTS, M)` | /3 | 3 point pairs |
| `get_perspective_transform(SRC_PTS, DST_PTS, M)` | /3 | 4 point pairs |
| `affine_inverse(M, M_INV)` | /2 | **Bidirectional**, self-inverse |
| `remap(IMG, MAP_X, MAP_Y, INTERP, OUT)` | /5 | |
| `remap(IMG, MAP_X, MAP_Y, INTERP, BORDER, OUT)` | /6 | |
| `copy_make_border(IMG, T, B, L, R, BORDER, OUT)` | /7 | |
| `copy_make_border(IMG, T, B, L, R, BORDER, VALUE, OUT)` | /8 | |

### `DSIZE` convention

OpenCV's `dsize` argument is `(W, H)`, opposite of `numpy.ndarray.shape`.
The wrapper takes a 2-element list `[W, H]` and coerces to a tuple
internally. The `size/2` query predicate in `opencv` already returns
`[W, H]`, so chaining works:

```clausal
shape(IMG, [H, W, _]),       % numpy order
resize(IMG, [W // 2, H // 2], SMALL)
```

### `affine_inverse/2` is bidirectional

```clausal
get_rotation_matrix_2d([16.0, 16.0], 30.0, 1.0, M),
affine_inverse(M, M_INV),    % forward: M -> M_INV
affine_inverse(M2, M_INV)    % backward: M2 = invert(M_INV) = M
```

`cv2.invertAffineTransform` is self-inverse, so the forward and
backward implementations are the same function — supplied to
`_bidir_2(_inv_affine, _inv_affine)`.

### `rotate/3` for the three lossless rotations

```clausal
rotate(IMG, rotate_90_clockwise, R1),
rotate(R1, rotate_90_counterclockwise, R2),
absdiff(IMG, R2, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

For arbitrary angles, build a matrix with `get_rotation_matrix_2d/4`
and apply with `warp_affine`.

### `remap` and `copy_make_border` examples

```clausal
% Identity remap with float32 coordinate grids
MAP_X is ++(numpy.tile(numpy.arange(32, dtype=numpy.float32), (32, 1))),
MAP_Y is ++(numpy.tile(numpy.arange(32, dtype=numpy.float32).reshape(-1, 1), (1, 32))),
remap(IMG, MAP_X, MAP_Y, inter_nearest, OUT)
```

```clausal
% 2-pixel replicate border
copy_make_border(IMG, 2, 2, 2, 2, border_replicate, PADDED)
```

## See also

- [`opencv`](opencv.md) — for the BGR/shape conventions, exported
  constants (`cv_8u`, `cv_16s`, `inter_*`, `border_*`, `morph_*`,
  `thresh_*`, `adaptive_thresh_*`, `rotate_*`, `warp_*`), and the
  `min_max_loc` reduction used for equality checks above.
- [`opencv_color`](opencv_color.md) — colour conversions, often a
  pre-step for edge detection or thresholding.
- [`opencv_contours`](opencv_contours.md) — Phase 4 contour
  extraction and measurements, often following a `threshold` call.
