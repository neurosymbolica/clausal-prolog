# Phase 5 — Geometric Transformations

Resize, warp (affine and perspective), rotate, remap, and border
padding. All Tier 1 (pure).

Two bijective predicates ship in this phase:

- `affine_inverse/2` — `cv2.invertAffineTransform`, self-inverse.
- A rotation-code helper is **not** bijective in general (e.g. rotate
  90 clockwise has rotate 90 counter-clockwise as its inverse, with a
  different code) but the *operation* is reversible — documented in
  the phase notes.

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_imgproc.py` — extend
  with geometric predicates (lives in the same file as Phase 3 to
  keep imgproc surface unified).
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend
  `_CONSTANT_NAMES` with `ROTATE_*` and `WARP_*` constants.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase5_geometric.clausal`
- `packages/clausal-opencv/docs/opencv_imgproc.md` — geometric section.

---

## Predicates

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `resize` | `/3` | `(+img, +dsize, -out)` | 1 | no | Default INTER_LINEAR |
| `resize` | `/4` | `(+img, +dsize, +interpolation, -out)` | 1 | no | |
| `resize_factor` | `/4` | `(+img, +fx, +fy, -out)` | 1 | no | Resize by scale factor (dsize=(0,0)) |
| `resize_factor` | `/5` | `(+img, +fx, +fy, +interpolation, -out)` | 1 | no | |
| `warp_affine` | `/4` | `(+img, +M, +dsize, -out)` | 1 | no | |
| `warp_affine` | `/5` | `(+img, +M, +dsize, +flags, -out)` | 1 | no | |
| `warp_affine` | `/6` | `(+img, +M, +dsize, +flags, +border_mode, -out)` | 1 | no | |
| `warp_affine` | `/7` | `(+img, +M, +dsize, +flags, +border_mode, +border_value, -out)` | 1 | no | |
| `warp_perspective` | `/4` | `(+img, +M, +dsize, -out)` | 1 | no | |
| `warp_perspective` | `/5` | `(+img, +M, +dsize, +flags, -out)` | 1 | no | |
| `warp_perspective` | `/6` | `(+img, +M, +dsize, +flags, +border_mode, -out)` | 1 | no | |
| `warp_perspective` | `/7` | `(+img, +M, +dsize, +flags, +border_mode, +border_value, -out)` | 1 | no | |
| `rotate` | `/3` | `(+img, +rotate_code, -out)` | 1 | no | `cv2.rotate` (90/180/270) |
| `get_rotation_matrix_2d` | `/4` | `(+center, +angle, +scale, -M)` | 1 | no | |
| `get_affine_transform` | `/3` | `(+src_pts, +dst_pts, -M)` | 1 | no | 3 point pairs |
| `get_perspective_transform` | `/3` | `(+src_pts, +dst_pts, -M)` | 1 | no | 4 point pairs |
| `affine_inverse` | `/2` | `(+M, -M_inv)` / `(-M, +M_inv)` | 1 | yes (self-inverse) | `cv2.invertAffineTransform` |
| `remap` | `/5` | `(+img, +map1, +map2, +interpolation, -out)` | 1 | no | |
| `remap` | `/6` | `(+img, +map1, +map2, +interpolation, +border_mode, -out)` | 1 | no | |
| `copy_make_border` | `/7` | `(+img, +top, +bot, +left, +right, +border_type, -out)` | 1 | no | |
| `copy_make_border` | `/8` | `(+img, +top, +bot, +left, +right, +border_type, +value, -out)` | 1 | no | |

---

## Context and Reference Patterns

### Imports

```python
from clausal.modules.py._helpers import _pred, _pure, _bidir_2
from clausal.modules.opencv import _cv
```

### `resize/3,4`

```python
resize = _pred("resize",
    (3, _pure(lambda img, dsize:
              _cv().resize(img, tuple(dsize)))),
    (4, _pure(lambda img, dsize, interp:
              _cv().resize(img, tuple(dsize), interpolation=int(interp)))),
)

resize_factor = _pred("resize_factor",
    (4, _pure(lambda img, fx, fy:
              _cv().resize(img, (0, 0), fx=float(fx), fy=float(fy)))),
    (5, _pure(lambda img, fx, fy, interp:
              _cv().resize(img, (0, 0), fx=float(fx), fy=float(fy),
                            interpolation=int(interp)))),
)
```

OpenCV's `resize` accepts `dsize=(0,0)` plus `fx`/`fy` for scale-factor
resizing. The wrapper splits this into two named predicates so users
don't have to remember the magic-tuple convention.

### `warp_affine/4..7`

The arity-7 variant is the most general; arity-4/5/6 are convenience
wrappers that fill in defaults:

```python
def _warp_affine_4(img, M, dsize):
    return _cv().warpAffine(img, M, tuple(dsize))

def _warp_affine_5(img, M, dsize, flags):
    return _cv().warpAffine(img, M, tuple(dsize), flags=int(flags))

def _warp_affine_6(img, M, dsize, flags, border_mode):
    return _cv().warpAffine(img, M, tuple(dsize),
                             flags=int(flags), borderMode=int(border_mode))

def _warp_affine_7(img, M, dsize, flags, border_mode, border_value):
    return _cv().warpAffine(img, M, tuple(dsize),
                             flags=int(flags),
                             borderMode=int(border_mode),
                             borderValue=tuple(border_value))

warp_affine = _pred("warp_affine",
    (4, _pure(_warp_affine_4)),
    (5, _pure(_warp_affine_5)),
    (6, _pure(_warp_affine_6)),
    (7, _pure(_warp_affine_7)),
)
```

`warp_perspective` follows the same pattern.

### `rotate/3`

```python
rotate = _pred("rotate",
    (3, _pure(lambda img, code: _cv().rotate(img, int(code)))),
)
```

The `rotate_code` is one of `ROTATE_90_CLOCKWISE`,
`ROTATE_180`, `ROTATE_90_COUNTERCLOCKWISE`, exported as constants.

### `get_rotation_matrix_2d/4`

```python
get_rotation_matrix_2d = _pred("get_rotation_matrix_2d",
    (4, _pure(lambda center, angle, scale:
              _cv().getRotationMatrix2D(tuple(center), float(angle), float(scale)))),
)
```

### `affine_inverse/2` (bijective)

`cv2.invertAffineTransform` is self-inverse: applying it twice returns
the original matrix (modulo numerical error). Use `_bidir_2`:

```python
def _inv_affine(M):
    return _cv().invertAffineTransform(M)

affine_inverse = _pred("affine_inverse",
    (2, _bidir_2(_inv_affine, _inv_affine)),
)
```

Both forward and backward call the same function — that's what
"self-inverse" means at the predicate level.

### Constants exported

```python
_CONSTANT_NAMES |= frozenset([
    "ROTATE_90_CLOCKWISE", "ROTATE_180", "ROTATE_90_COUNTERCLOCKWISE",
    "WARP_INVERSE_MAP", "WARP_FILL_OUTLIERS",
    "WARP_POLAR_LINEAR", "WARP_POLAR_LOG",
])
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, size, absdiff, min_max_loc, IMREAD_COLOR,
    INTER_LINEAR, INTER_NEAREST, INTER_CUBIC,
    BORDER_CONSTANT, BORDER_REPLICATE, BORDER_REFLECT,
    ROTATE_90_CLOCKWISE, ROTATE_180, ROTATE_90_COUNTERCLOCKWISE
])
-import_from(py.opencv_imgproc, [
    resize, resize_factor, warp_affine, warp_perspective, rotate,
    get_rotation_matrix_2d, get_affine_transform,
    get_perspective_transform, affine_inverse, remap, copy_make_border
])

Test("resize to explicit dsize") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    resize(IMG, [10, 10], OUT),
    size(OUT, [10, 10])
)

Test("resize_factor halves both dims") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    size(IMG, [W, H]),
    resize_factor(IMG, 0.5, 0.5, OUT),
    size(OUT, [W2, H2]),
    W2 is W // 2,
    H2 is H // 2
)

Test("rotate 90 cw then 90 ccw is identity") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    rotate(IMG, ROTATE_90_CLOCKWISE, R1),
    rotate(R1, ROTATE_90_COUNTERCLOCKWISE, R2),
    absdiff(IMG, R2, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("rotate 180 twice is identity") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    rotate(IMG, ROTATE_180, R1),
    rotate(R1, ROTATE_180, R2),
    absdiff(IMG, R2, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("affine_inverse is self-inverse") <- (
    get_rotation_matrix_2d([2.0, 2.0], 30.0, 1.0, M),
    affine_inverse(M, M_INV),
    affine_inverse(M_INV, M_BACK),
    # M_BACK and M should be element-wise close — we use the numpy
    # check predicate from the core wrapper for this.
    ++(numpy.allclose(M, M_BACK))
)
```

**Note:** The last test uses `++(numpy.allclose(...))` as the only
convenient way to compare two small float matrices. This is the
test-fixture exception in [Checklist H](../EXTERNAL_WRAPPER_CHECKLIST.md#checklist-h--escape-minimisation),
not user-facing code. Real-world code would unify against an expected
matrix or use `min_max_loc(absdiff(...))` for a single scalar check —
but that pattern works on `uint8` images, not `float64` matrices.
**Action item:** consider adding a `matrix_allclose/4` predicate
(`(+A, +B, +ATOL, -BOOL)`) to `opencv.py` if this pattern recurs in
Phases 7/9. Filed in this phase's Issues.

```clausal
Test("warp_affine identity transform") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    size(IMG, [W, H]),
    # Identity transform as 2x3 matrix
    M = ++(numpy.array([[1, 0, 0], [0, 1, 0]], dtype=numpy.float32)),
    warp_affine(IMG, M, [W, H], OUT),
    absdiff(IMG, OUT, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("get_perspective_transform from 4 corners") <- (
    SRC = ++(numpy.array([[0,0],[10,0],[10,10],[0,10]], dtype=numpy.float32)),
    DST = ++(numpy.array([[0,0],[20,0],[20,20],[0,20]], dtype=numpy.float32)),
    get_perspective_transform(SRC, DST, M),
    shape(M, [3, 3])
)

Test("copy_make_border preserves dtype and adds borders") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    size(IMG, [W, H]),
    copy_make_border(IMG, 2, 2, 2, 2, BORDER_REPLICATE, OUT),
    size(OUT, [W2, H2]),
    W2 is W + 4,
    H2 is H + 4
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase5_geometric.clausal`:

- All Test cases above.
- `resize` with each interpolation flag (sanity check, just verify
  shape).
- `warp_perspective` identity transform is identity.
- `get_affine_transform` from 3 collinear-rejecting point pairs.
- `affine_inverse` round-trip through a rotation matrix.
- `remap` with identity maps returns the input unchanged.

### Python unit tests

None additional.

---

## Docs

Extend `packages/clausal-opencv/docs/opencv_imgproc.md` with a
"Geometric transformations" section covering all predicates above.
Worked examples taken verbatim from the test file.

---

## Issues

### 1. Constants use lowercase aliases — INHERITED FROM PHASE 1

`ROTATE_*` and `WARP_*` exported as `rotate_90_clockwise`,
`rotate_180`, `rotate_90_counterclockwise`, `warp_inverse_map`,
`warp_fill_outliers`, `warp_polar_linear`, `warp_polar_log`. See
Phase 1 Issue 1.

### 2. `dsize` is `[W, H]`, not `[H, W]` — DOCUMENTED

OpenCV's `dsize` argument is `(W, H)` — opposite of numpy's
`(H, W)`. The wrapper takes a 2-list `[W, H]` (matching OpenCV) and
coerces to a tuple. The `size/2` query predicate already returns
`[W, H]`, so chaining `size(IMG, [W, H]), resize(IMG, [W2, H2], _)`
is consistent. Documented in `opencv_imgproc.md`.

### 3. `affine_inverse/2` self-inverse — VERIFIED

`cv2.invertAffineTransform` is its own inverse: applying it twice
returns the original matrix modulo floating-point error. Tests verify
forward-forward equivalence via `numpy.allclose`. The bidirectional
dispatch uses `_bidir_2(_inv_affine, _inv_affine)` — same function
for forward and backward, which is what self-inverse means at the
predicate level.

### 4. `resize_factor` vs `resize` — SPLIT INTO TWO PREDICATES

OpenCV's `cv2.resize` accepts a magic-tuple `dsize=(0, 0)` plus
`fx`/`fy` for scale-factor resizing. The wrapper splits this into
two named predicates (`resize` for explicit size, `resize_factor`
for scale factors) so users don't have to remember the magic-tuple
convention. Both modes use the same `cv2.resize` under the hood.

### 5. `matrix_allclose/4` not added — DEFERRED

The matrix-equality tests (`affine_inverse` round-trip) use
`++(numpy.allclose(M, M_BACK))` per the Checklist H test-fixture
exception. A dedicated `matrix_allclose/4` predicate would clean
this up, but the same `numpy.allclose` escape recurs in Phases 7
and 9. Decision: revisit when Phase 9 (calibration) is implemented
— if the pattern is universal, lift it to Phase 1's `opencv.py`
under a name like `array_allclose(A, B, ATOL, BOOL_OUT)` returning
a check predicate. For now the test-fixture escape is documented.

### 6. `warp_affine`/`warp_perspective` 4-7 arity chain — CLEAN

OpenCV exposes `warpAffine(src, M, dsize, [dst, [flags, [borderMode,
[borderValue]]]])`. The wrapper splits this into arity-4/5/6/7
variants, each adding one positional argument. No magic defaults
sentinels in Clausal code — cv2 fills in its own defaults for
omitted kwargs. Tests cover all four arities.

### 7. `rotate/3` does NOT generalise `affine_inverse` — DOCUMENTED

`rotate(IMG, rotate_90_clockwise, R)` is *not* the bidirectional
inverse of `rotate(R, rotate_90_counterclockwise, IMG)` — there are
two different `rotate_code` values. Tests verify the chain
explicitly. A bidirectional `rotate/3` collapsing the two
directions could be designed but would obscure which direction is
which. Left as separate codes.
