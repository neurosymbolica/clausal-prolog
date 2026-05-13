# Phase 3 — Filtering and Morphology

Image filtering, edge detection, and morphological operations — the
heart of classical image processing.

All predicates are **Tier 1 (pure)**. Image arithmetic and morphology
flags are exposed both as imported constants and as registry
predicates for config-driven workflows.

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_imgproc.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend
  `_CONSTANT_NAMES` with `INTER_*`, `BORDER_*`, `MORPH_*` constants.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase3_filtering.clausal`
- `packages/clausal-opencv/docs/opencv_imgproc.md`

---

## Predicates

### Smoothing

| Name | Arity | Modes | Description |
|---|---|---|---|
| `gaussian_blur` | `/3` | `(+img, +ksize, -out)` | Default sigma=0 (computed from ksize) |
| `gaussian_blur` | `/4` | `(+img, +ksize, +sigma, -out)` | Explicit sigmaX (sigmaY=sigmaX) |
| `gaussian_blur` | `/5` | `(+img, +ksize, +sigma_x, +sigma_y, -out)` | |
| `median_blur` | `/3` | `(+img, +ksize, -out)` | |
| `box_filter` | `/4` | `(+img, +ddepth, +ksize, -out)` | |
| `bilateral_filter` | `/5` | `(+img, +d, +sigma_color, +sigma_space, -out)` | |

### Convolution

| Name | Arity | Modes | Description |
|---|---|---|---|
| `filter_2d` | `/4` | `(+img, +ddepth, +kernel, -out)` | `cv2.filter2D` |
| `sep_filter_2d` | `/5` | `(+img, +ddepth, +kernel_x, +kernel_y, -out)` | |

### Edge detection

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sobel` | `/5` | `(+img, +ddepth, +dx, +dy, -out)` | Default ksize=3 |
| `sobel` | `/6` | `(+img, +ddepth, +dx, +dy, +ksize, -out)` | |
| `scharr` | `/5` | `(+img, +ddepth, +dx, +dy, -out)` | |
| `laplacian` | `/3` | `(+img, +ddepth, -out)` | Default ksize=1 |
| `laplacian` | `/4` | `(+img, +ddepth, +ksize, -out)` | |
| `canny` | `/4` | `(+img, +threshold_1, +threshold_2, -out)` | Default apertureSize=3 |
| `canny` | `/5` | `(+img, +threshold_1, +threshold_2, +aperture_size, -out)` | |

### Morphology

| Name | Arity | Modes | Description |
|---|---|---|---|
| `get_structuring_element` | `/3` | `(+shape, +ksize, -kernel)` | Default anchor=(-1,-1) |
| `get_structuring_element` | `/4` | `(+shape, +ksize, +anchor, -kernel)` | |
| `erode` | `/3` | `(+img, +kernel, -out)` | Default iterations=1 |
| `erode` | `/4` | `(+img, +kernel, +iterations, -out)` | |
| `dilate` | `/3` | `(+img, +kernel, -out)` | |
| `dilate` | `/4` | `(+img, +kernel, +iterations, -out)` | |
| `morphology_ex` | `/4` | `(+img, +op, +kernel, -out)` | |
| `morphology_ex` | `/5` | `(+img, +op, +kernel, +iterations, -out)` | |

### Pyramid

| Name | Arity | Modes | Description |
|---|---|---|---|
| `pyr_down` | `/2` | `(+img, -out)` | Default dstsize = (cols//2, rows//2) |
| `pyr_down` | `/3` | `(+img, +dstsize, -out)` | |
| `pyr_up` | `/2` | `(+img, -out)` | |
| `pyr_up` | `/3` | `(+img, +dstsize, -out)` | |

### Registries

| Name | Arity | Modes | Description |
|---|---|---|---|
| `interpolation` | `/2` | name ↔ code, enum | `nearest`, `linear`, `cubic`, `area`, `lanczos4` |
| `border_type` | `/2` | name ↔ code, enum | `constant`, `replicate`, `reflect`, `reflect_101`, `wrap` |
| `morph_op` | `/2` | name ↔ code, enum | `erode`, `dilate`, `open`, `close`, `gradient`, `tophat`, `blackhat`, `hitmiss` |
| `morph_shape` | `/2` | name ↔ code, enum | `rect`, `ellipse`, `cross` |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_imgproc.py
from clausal.modules.py._helpers import _pred, _pure, _fact_table_2
from clausal.modules.opencv import _cv
from clausal.modules._scipy_units import make_quantity_aware, PASS_THROUGH_FIRST
```

### Smoothing — handling tuple ksize

OpenCV expects `ksize=(w, h)` as a tuple in many filters. In `.clausal`
users naturally write `[5, 5]` (a list). The `_pure` helper's
`_deep_deref` returns lists; convert inside the lambda:

```python
gaussian_blur = _pred("gaussian_blur",
    (3, _pure(make_quantity_aware(
        lambda img, ksize: _cv().GaussianBlur(img, tuple(ksize), 0),
        PASS_THROUGH_FIRST))),
    (4, _pure(make_quantity_aware(
        lambda img, ksize, sigma: _cv().GaussianBlur(img, tuple(ksize), float(sigma)),
        PASS_THROUGH_FIRST))),
    (5, _pure(make_quantity_aware(
        lambda img, ksize, sx, sy: _cv().GaussianBlur(img, tuple(ksize), float(sx), sigmaY=float(sy)),
        PASS_THROUGH_FIRST))),
)
```

Every smoothing predicate follows the same pattern. The `tuple(...)`
coercion is necessary — `cv2.GaussianBlur` rejects a list for `ksize`.

### `median_blur/3` — int ksize

`cv2.medianBlur` takes an integer ksize, not a tuple:

```python
median_blur = _pred("median_blur",
    (3, _pure(lambda img, ksize: _cv().medianBlur(img, int(ksize)))),
)
```

### Edge detection — same tuple pattern

```python
sobel = _pred("sobel",
    (5, _pure(lambda img, ddepth, dx, dy:
              _cv().Sobel(img, int(ddepth), int(dx), int(dy)))),
    (6, _pure(lambda img, ddepth, dx, dy, ksize:
              _cv().Sobel(img, int(ddepth), int(dx), int(dy), ksize=int(ksize)))),
)

canny = _pred("canny",
    (4, _pure(lambda img, t1, t2:
              _cv().Canny(img, float(t1), float(t2)))),
    (5, _pure(lambda img, t1, t2, ap:
              _cv().Canny(img, float(t1), float(t2), apertureSize=int(ap)))),
)
```

### Morphology

```python
get_structuring_element = _pred("get_structuring_element",
    (3, _pure(lambda shape, ksize:
              _cv().getStructuringElement(int(shape), tuple(ksize)))),
    (4, _pure(lambda shape, ksize, anchor:
              _cv().getStructuringElement(int(shape), tuple(ksize), tuple(anchor)))),
)

morphology_ex = _pred("morphology_ex",
    (4, _pure(lambda img, op, kernel:
              _cv().morphologyEx(img, int(op), kernel))),
    (5, _pure(lambda img, op, kernel, iterations:
              _cv().morphologyEx(img, int(op), kernel, iterations=int(iterations)))),
)
```

### Registries

Hand-rolled fact tables (these registries enumerate a fixed small set
of constants — no introspection needed):

```python
def _interpolation_facts():
    cv = _cv()
    return [
        ("nearest",  cv.INTER_NEAREST),
        ("linear",   cv.INTER_LINEAR),
        ("cubic",    cv.INTER_CUBIC),
        ("area",     cv.INTER_AREA),
        ("lanczos4", cv.INTER_LANCZOS4),
    ]

interpolation = _pred("interpolation",
    (2, _fact_table_2(_interpolation_facts)),
)

def _border_facts():
    cv = _cv()
    return [
        ("constant",    cv.BORDER_CONSTANT),
        ("replicate",   cv.BORDER_REPLICATE),
        ("reflect",     cv.BORDER_REFLECT),
        ("reflect_101", cv.BORDER_REFLECT_101),
        ("wrap",        cv.BORDER_WRAP),
        ("isolated",    cv.BORDER_ISOLATED),
    ]

border_type = _pred("border_type",
    (2, _fact_table_2(_border_facts)),
)

def _morph_op_facts():
    cv = _cv()
    return [
        ("erode",    cv.MORPH_ERODE),
        ("dilate",   cv.MORPH_DILATE),
        ("open",     cv.MORPH_OPEN),
        ("close",    cv.MORPH_CLOSE),
        ("gradient", cv.MORPH_GRADIENT),
        ("tophat",   cv.MORPH_TOPHAT),
        ("blackhat", cv.MORPH_BLACKHAT),
        ("hitmiss",  cv.MORPH_HITMISS),
    ]

morph_op = _pred("morph_op",
    (2, _fact_table_2(_morph_op_facts)),
)

def _morph_shape_facts():
    cv = _cv()
    return [
        ("rect",    cv.MORPH_RECT),
        ("ellipse", cv.MORPH_ELLIPSE),
        ("cross",   cv.MORPH_CROSS),
    ]

morph_shape = _pred("morph_shape",
    (2, _fact_table_2(_morph_shape_facts)),
)
```

### Constants exported

Extend `_CONSTANT_NAMES` in `opencv.py` (or in `opencv_imgproc.py`'s
own `__getattr__` — the convention in the existing wrappers is to
re-export from the top-level module):

```python
_CONSTANT_NAMES |= frozenset([
    # Interpolation
    "INTER_NEAREST", "INTER_LINEAR", "INTER_CUBIC", "INTER_AREA",
    "INTER_LANCZOS4",
    # Border types
    "BORDER_CONSTANT", "BORDER_REPLICATE", "BORDER_REFLECT",
    "BORDER_REFLECT_101", "BORDER_REFLECT101", "BORDER_DEFAULT",
    "BORDER_WRAP", "BORDER_ISOLATED",
    # Morphology operations
    "MORPH_ERODE", "MORPH_DILATE", "MORPH_OPEN", "MORPH_CLOSE",
    "MORPH_GRADIENT", "MORPH_TOPHAT", "MORPH_BLACKHAT", "MORPH_HITMISS",
    # Morphology shapes
    "MORPH_RECT", "MORPH_ELLIPSE", "MORPH_CROSS",
])
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, channels_count, is_grayscale, absdiff, min_max_loc,
    IMREAD_COLOR, IMREAD_GRAYSCALE, CV_8U, CV_32F, CV_16S,
    INTER_LINEAR, INTER_CUBIC, BORDER_REFLECT,
    MORPH_RECT, MORPH_ELLIPSE, MORPH_OPEN, MORPH_CLOSE
])
-import_from(py.opencv_imgproc, [
    gaussian_blur, median_blur, bilateral_filter, filter_2d,
    sobel, scharr, laplacian, canny,
    get_structuring_element, erode, dilate, morphology_ex,
    pyr_down, pyr_up,
    interpolation, border_type, morph_op, morph_shape
])

Test("gaussian_blur preserves shape") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    gaussian_blur(IMG, [3, 3], OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("median_blur preserves shape with odd ksize") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    median_blur(IMG, 3, OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("canny on grayscale yields 2-D output") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    canny(GRAY, 50, 150, EDGES),
    is_grayscale(EDGES)
)

Test("sobel changes depth to CV_16S") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    sobel(GRAY, CV_16S, 1, 0, SX),
    shape(GRAY, S),
    shape(SX, S)
)

Test("morphology_ex open is erode then dilate") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    get_structuring_element(MORPH_RECT, [3, 3], K),
    erode(GRAY, K, ER),
    dilate(ER, K, OPEN_BY_HAND),
    morphology_ex(GRAY, MORPH_OPEN, K, OPEN_BY_PRED),
    absdiff(OPEN_BY_HAND, OPEN_BY_PRED, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("pyr_down halves linear dimensions") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, [H, W, _]),
    pyr_down(IMG, DOWN),
    shape(DOWN, [HD, WD, _]),
    HD is (H + 1) // 2,
    WD is (W + 1) // 2
)

Test("interpolation registry yields cv code") <- (
    interpolation("cubic", C),
    C = INTER_CUBIC
)

Test("border_type registry inverse lookup") <- (
    border_type(NAME, BORDER_REFLECT),
    NAME = "reflect"
)

Test("findall over morph_op enumerates all") <- (
    findall(N, morph_op(N, _), NAMES),
    length(NAMES, L),
    L >= 7
)

Test("filter_2d with identity kernel is identity") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    # Identity kernel: [[0,0,0],[0,1,0],[0,0,0]] as float32 array
    K_IDENTITY = ++(numpy.array([[0,0,0],[0,1,0],[0,0,0]], dtype=numpy.float32)),
    filter_2d(GRAY, CV_8U, K_IDENTITY, OUT),
    absdiff(GRAY, OUT, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)
```

**Note:** The last test uses `++(numpy.array(...))` to construct a
test kernel — this is acceptable for test fixtures (per
[Checklist H](../EXTERNAL_WRAPPER_CHECKLIST.md#checklist-h--escape-minimisation)).
Real usage would use a kernel produced by `get_structuring_element`
or similar.

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase3_filtering.clausal`:

- All Test cases above.
- `bilateral_filter` with default args; verify shape preservation.
- `scharr` shape preservation.
- `laplacian` with each ksize variant.
- `get_structuring_element` returns a uint8 ndarray of the right shape
  for each `MORPH_*` shape.
- `morphology_ex` with each `MORPH_*` op produces the right shape.
- All four registries in every mode: query, inverse lookup, enumeration,
  failure on unknown name.

### Python unit tests

None additional.

---

## Docs

`packages/clausal-opencv/docs/opencv_imgproc.md`:

- Intro: smoothing, edges, morphology, pyramids — workhorse
  image-processing operations.
- One worked example per group. All examples have a corresponding
  `.clausal` test.
- A subsection per registry: when to use it (config-driven flag
  selection) versus the imported constant directly.

---

## Issues

### 1. Constants and registry names use lowercase — INHERITED FROM PHASE 1

All `INTER_*`, `BORDER_*`, `MORPH_*` constants exported from
`opencv.py` use lowercase aliases (`inter_cubic`, `border_reflect`,
`morph_rect`, …). Registry name keys follow the same convention.
See Phase 1 Issue 1.

### 2. `KSIZE` accepts a 2-element list — DOCUMENTED

OpenCV's filter functions expect a 2-tuple for `ksize` (e.g.
`(3, 3)`), but Clausal users naturally write `[3, 3]`. The
`_ksize_tuple` helper accepts either a list/tuple of two ints **or**
a single int (treated as a square kernel). `median_blur` is the
exception — its `ksize` is a scalar int, so it goes through `int(...)`.

### 3. `box_filter` requires explicit `ddepth` — DECIDED

OpenCV's `cv2.boxFilter` lets you pass `ddepth=-1` to inherit from
the source, but exposing that as the default would force users
through `++cv2.CV_DEFAULT` to opt in to anything else. The wrapper
takes `ddepth` as a required positional argument and exports
`cv_8u`, `cv_16s`, `cv_32f`, etc. as constants so the common cases
have no escape.

### 4. `pyr_down` halving rule on 4×4 fixture — VERIFIED

`cv2.pyrDown` downsamples by 2 with the formula
`((W+1)//2, (H+1)//2)`. On the 4×4 test fixture this yields 2×2, not
the `[(H+1)//2, (W+1)//2]` formula the phase doc originally cited.
The test asserts the concrete 2×2 output rather than the formula —
both formulas agree on even dimensions.

### 5. `++(numpy.array(...))` in tests is acceptable — DOCUMENTED

The `filter_2d` and `sep_filter_2d` tests construct test kernels via
`++(numpy.array(...))`. Per [Checklist H](../EXTERNAL_WRAPPER_CHECKLIST.md#checklist-h--escape-minimisation),
this is the test-fixture exception — there's no Clausal predicate
to build a Float32 ndarray from a nested list of literals. Real
usage would either source kernels from `get_structuring_element/3`
or use a higher-level helper (out of scope for Phase 3).
