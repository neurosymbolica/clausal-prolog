# Phase 4 — Thresholding and Contours

Thresholding (global, adaptive, Otsu, Triangle) and contour analysis
(extraction, area, perimeter, moments, hull, fitting). All Tier 1
(pure).

This phase introduces two new term constructors:

- `rect(X, Y, W, H)` — axis-aligned bounding rectangle.
- `rotated_rect(CENTER, SIZE, ANGLE)` — output of `min_area_rect`.
- `moments_t(M00, M10, ..., NU03)` — full image moments record.

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_contours.py` (new) —
  contour-specific predicates split out from `opencv_imgproc.py`.
  Thresholding lives in `opencv_imgproc.py` (it's a filtering-adjacent
  operation; keeps Phase 3 and Phase 4 in adjacent files).
- `packages/clausal-opencv/clausal/modules/opencv_imgproc.py` — extend
  with `threshold/6` and `adaptive_threshold/7`.
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend
  `_CONSTANT_NAMES` with `THRESH_*`, `RETR_*`, `CHAIN_APPROX_*`,
  `ADAPTIVE_THRESH_*` constants.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase4_thresh_contours.clausal`
- `packages/clausal-opencv/docs/opencv_imgproc.md` — section on
  thresholding.
- `packages/clausal-opencv/docs/opencv_contours.md` — new file.

---

## Predicates

### Thresholding

| Name | Arity | Modes | Description |
|---|---|---|---|
| `threshold` | `/6` | `(+img, +thresh, +maxval, +type, -used_thresh, -out)` | `cv2.threshold` returning both the used threshold (relevant for Otsu/Triangle) and the binary output |
| `adaptive_threshold` | `/7` | `(+img, +maxval, +adaptive_method, +threshold_type, +block_size, +c, -out)` | |
| `threshold_type` | `/2` | `(+name,-code)`, inverse, enum | Registry: `binary`, `binary_inv`, `trunc`, `tozero`, `tozero_inv`, `otsu`, `triangle` |

### Contours

| Name | Arity | Modes | Description |
|---|---|---|---|
| `find_contours` | `/5` | `(+img, +mode, +method, -contours, -hierarchy)` | |
| `find_contours` | `/6` | `(+img, +mode, +method, +offset, -contours, -hierarchy)` | |
| `contour` | `/2` | `(+contours, -c)` | **Nondeterministic** enumeration |
| `contour_area` | `/2` | `(+contour, -area)` | Default oriented=False |
| `contour_area` | `/3` | `(+contour, +oriented, -area)` | |
| `contour_perimeter` | `/3` | `(+contour, +closed, -p)` | `cv2.arcLength` |
| `moments` | `/2` | `(+contour_or_img, -moments)` | Returns `moments_t(...)` term |
| `moments` | `/3` | `(+img, +binary_image, -moments)` | When input is a raster image, second arg flags binary interpretation |
| `moments_field` | `/3` | `(+moments, +name, -value)` | Field accessor: `"m00"`, `"m10"`, ..., `"nu03"` |
| `convex_hull` | `/2` | `(+points, -hull)` | Default clockwise=False, returnPoints=True |
| `convex_hull` | `/3` | `(+points, +clockwise, -hull)` | |
| `bounding_rect` | `/2` | `(+points, -rect)` | Returns `rect(X, Y, W, H)` |
| `min_enclosing_circle` | `/3` | `(+points, -center, -radius)` | |
| `min_area_rect` | `/2` | `(+points, -rotated_rect)` | Returns `rotated_rect(CENTER, SIZE, ANGLE)` |
| `approx_poly_dp` | `/4` | `(+contour, +epsilon, +closed, -out)` | Ramer-Douglas-Peucker |
| `point_polygon_test` | `/4` | `(+contour, +pt, +measure_dist, -result)` | Result: signed distance or +1/0/-1 |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_contours.py
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _deep_deref
from clausal.modules.opencv import _cv
```

### `threshold/6`

```python
def _threshold(img, thresh, maxval, type_):
    used, out = _cv().threshold(img, float(thresh), float(maxval), int(type_))
    return used, out

def _threshold_dispatch(this_generator, _proceed, _fail, _catcher,
                        img_v, thresh_v, maxval_v, type_v, used_v, out_v, trail):
    img = _deep_deref(img_v)
    thresh = deref(thresh_v)
    maxval = deref(maxval_v)
    type_ = deref(type_v)
    try:
        used, out = _threshold(img, thresh, maxval, type_)
    except Exception:
        yield (_fail, DONE); return
    if unify(used_v, float(used), trail) and unify(out_v, out, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

threshold = _pred("threshold", (6, _threshold_dispatch))
```

Custom dispatch because `_pure` only unifies one RESULT.

### `adaptive_threshold/7`

```python
adaptive_threshold = _pred("adaptive_threshold",
    (7, _pure(lambda img, maxval, am, tt, bs, c:
              _cv().adaptiveThreshold(img, float(maxval), int(am), int(tt),
                                       int(bs), float(c)))),
)
```

### `find_contours/5,6`

```python
find_contours = _pred("find_contours",
    (5, _find_contours_5),
    (6, _find_contours_6),
)

def _find_contours_5(this_generator, _proceed, _fail, _catcher,
                     img_v, mode_v, method_v, contours_v, hierarchy_v, trail):
    img = _deep_deref(img_v)
    mode = int(deref(mode_v))
    method = int(deref(method_v))
    try:
        # OpenCV 4 returns (contours, hierarchy)
        contours, hierarchy = _cv().findContours(img, mode, method)
    except Exception:
        yield (_fail, DONE); return
    if (unify(contours_v, list(contours), trail)
            and unify(hierarchy_v, hierarchy, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)
```

The contours list is wrapped with `list(...)` so each element is a
numpy ndarray; the surrounding container is a Python list that
Clausal can decompose with `[H, *T]`.

### `contour/2` — nondeterministic enumeration

```python
def _contour_dispatch(this_generator, _proceed, _fail, _catcher,
                      contours_v, c_v, trail):
    contours = _deep_deref(contours_v)
    if not isinstance(contours, (list, tuple)):
        yield (_fail, DONE); return
    for c in contours:
        mark = trail.mark()
        if unify(c_v, c, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)

contour = _pred("contour", (2, _contour_dispatch))
```

Same pattern as torch's nondet predicates and `_fact_table_2` — yield
each candidate inside a `trail.mark()` / `trail.undo()` scope.

### `bounding_rect/2` — returns tagged term

```python
def _bounding_rect(points):
    x, y, w, h = _cv().boundingRect(points)
    return ("rect", int(x), int(y), int(w), int(h))

bounding_rect = _pred("bounding_rect",
    (2, _pure(_bounding_rect)),
)
```

Decomposed in `.clausal` as `R is ("rect", X, Y, W, H)`. The tag
`"rect"` distinguishes it from a plain 4-tuple of ints.

### `min_area_rect/2` — `rotated_rect` term

```python
def _min_area_rect(points):
    (cx, cy), (w, h), angle = _cv().minAreaRect(points)
    return ("rotated_rect",
            [float(cx), float(cy)],
            [float(w), float(h)],
            float(angle))

min_area_rect = _pred("min_area_rect",
    (2, _pure(_min_area_rect)),
)
```

### `moments/2,3` — `moments_t` term

`cv2.moments` returns a dict with 24 named fields. The wrapper exposes
two access patterns:

1. **Tagged tuple for clause-head decomposition**:
   `moments_t(M00, M10, M01, M20, M11, M02, M30, M21, M12, M03,
              MU20, MU11, MU02, MU30, MU21, MU12, MU03,
              NU20, NU11, NU02, NU30, NU21, NU12, NU03)`
2. **Field accessor** for users who don't want a 25-arity decomposition:
   `moments_field(M, "m00", V)`.

```python
_MOMENT_KEYS = (
    "m00", "m10", "m01", "m20", "m11", "m02",
    "m30", "m21", "m12", "m03",
    "mu20", "mu11", "mu02", "mu30", "mu21", "mu12", "mu03",
    "nu20", "nu11", "nu02", "nu30", "nu21", "nu12", "nu03",
)

def _moments(arg):
    m = _cv().moments(arg)
    return ("moments_t",) + tuple(float(m[k]) for k in _MOMENT_KEYS)

def _moments_binary(img, binary):
    m = _cv().moments(img, binaryImage=bool(binary))
    return ("moments_t",) + tuple(float(m[k]) for k in _MOMENT_KEYS)

moments = _pred("moments",
    (2, _pure(_moments)),
    (3, _pure(_moments_binary)),
)

def _moments_field(m_term, name):
    # m_term is a tuple starting with the "moments_t" tag.
    if not (isinstance(m_term, tuple) and m_term and m_term[0] == "moments_t"):
        raise ValueError("Expected moments_t term")
    name_s = str(name)
    if name_s not in _MOMENT_KEYS:
        raise KeyError(name_s)
    idx = _MOMENT_KEYS.index(name_s) + 1
    return m_term[idx]

moments_field = _pred("moments_field",
    (3, _pure(_moments_field)),
)
```

### Registries

```python
def _threshold_type_facts():
    cv = _cv()
    return [
        ("binary",     cv.THRESH_BINARY),
        ("binary_inv", cv.THRESH_BINARY_INV),
        ("trunc",      cv.THRESH_TRUNC),
        ("tozero",     cv.THRESH_TOZERO),
        ("tozero_inv", cv.THRESH_TOZERO_INV),
        ("otsu",       cv.THRESH_OTSU),
        ("triangle",   cv.THRESH_TRIANGLE),
    ]

threshold_type = _pred("threshold_type",
    (2, _fact_table_2(_threshold_type_facts)),
)
```

### Constants exported

```python
_CONSTANT_NAMES |= frozenset([
    # Thresholding
    "THRESH_BINARY", "THRESH_BINARY_INV", "THRESH_TRUNC",
    "THRESH_TOZERO", "THRESH_TOZERO_INV", "THRESH_MASK",
    "THRESH_OTSU", "THRESH_TRIANGLE",
    # Adaptive thresholding methods
    "ADAPTIVE_THRESH_MEAN_C", "ADAPTIVE_THRESH_GAUSSIAN_C",
    # Contour retrieval modes
    "RETR_EXTERNAL", "RETR_LIST", "RETR_CCOMP", "RETR_TREE",
    "RETR_FLOODFILL",
    # Contour approximation methods
    "CHAIN_APPROX_NONE", "CHAIN_APPROX_SIMPLE",
    "CHAIN_APPROX_TC89_L1", "CHAIN_APPROX_TC89_KCOS",
])
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, is_grayscale, IMREAD_GRAYSCALE,
    THRESH_BINARY, THRESH_OTSU, THRESH_BINARY_INV,
    ADAPTIVE_THRESH_MEAN_C, ADAPTIVE_THRESH_GAUSSIAN_C,
    RETR_EXTERNAL, RETR_TREE, CHAIN_APPROX_SIMPLE, CHAIN_APPROX_NONE
])
-import_from(py.opencv_imgproc, [threshold, adaptive_threshold])
-import_from(py.opencv_contours, [
    find_contours, contour, contour_area, contour_perimeter,
    moments, moments_field, convex_hull, bounding_rect,
    min_enclosing_circle, min_area_rect, approx_poly_dp,
    point_polygon_test, threshold_type
])

Test("threshold binary preserves the level we gave it") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, USED, OUT),
    USED = 128.0,
    is_grayscale(OUT)
)

Test("threshold otsu returns the chosen level") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 0.0, 255.0, THRESH_BINARY + THRESH_OTSU, USED, OUT),
    USED >= 0.0,
    USED =< 255.0
)

Test("adaptive_threshold preserves shape") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    adaptive_threshold(GRAY, 255.0, ADAPTIVE_THRESH_MEAN_C, THRESH_BINARY,
                       3, 0.0, OUT),
    shape(GRAY, S),
    shape(OUT, S)
)

Test("find_contours on a thresholded image yields some contours") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE, CONTOURS, _),
    findall(C, contour(CONTOURS, C), CS),
    length(CS, N),
    N >= 0
)

Test("bounding_rect decomposes to rect/4") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE, [C, *_], _),
    bounding_rect(C, RECT),
    RECT is ("rect", _, _, W, H),
    W > 0,
    H > 0
)

Test("min_area_rect decomposes to rotated_rect") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE, [C, *_], _),
    min_area_rect(C, RR),
    RR is ("rotated_rect", _CENTER, _SIZE, _ANGLE)
)

Test("moments_field m00 equals contour_area for binary contour") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE, [C, *_], _),
    moments(C, M),
    moments_field(M, "m00", M00),
    contour_area(C, A),
    abs(M00 - A) =< 0.001
)

Test("convex_hull of a contour is a contour itself") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE, [C, *_], _),
    convex_hull(C, HULL),
    contour_area(HULL, A_HULL),
    contour_area(C, A_C),
    A_HULL >= A_C
)

Test("approx_poly_dp reduces vertex count with large epsilon") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY),
    threshold(GRAY, 128.0, 255.0, THRESH_BINARY, _, BIN),
    find_contours(BIN, RETR_EXTERNAL, CHAIN_APPROX_NONE, [C, *_], _),
    approx_poly_dp(C, 5.0, True, APPROX),
    shape(C, [N_BEFORE, _, _]),
    shape(APPROX, [N_AFTER, _, _]),
    N_AFTER =< N_BEFORE
)

Test("threshold_type registry") <- (
    threshold_type("otsu", T),
    T = THRESH_OTSU
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase4_thresh_contours.clausal`:

- All Test cases above.
- Every threshold type via the registry: round-trip name ↔ code.
- `find_contours` with each `RETR_*` mode and each `CHAIN_APPROX_*`
  method.
- `min_enclosing_circle` on a contour: center is inside the bounding
  rect.
- `point_polygon_test` with `measure_dist=False` returns +1/0/-1;
  with `True` returns signed distance.
- Failure modes: `moments_field(M, "bogus", _)` fails cleanly.

### Python unit tests

None additional.

---

## Docs

`packages/clausal-opencv/docs/opencv_contours.md` — new file:

- Intro: "Contours are the standard representation of object outlines
  in binary images. OpenCV's `findContours` returns them as a list of
  Nx1x2 int32 arrays; this module exposes the list, individual contours
  via `contour/2`, and measurements (area, perimeter, moments, hull,
  bounding shapes) on each."
- Worked example: load → threshold → find contours → measure largest
  contour. Mirrors the example block above.
- Section per term constructor (`rect`, `rotated_rect`, `moments_t`)
  with decomposition examples.
- Section on the `moments_field/3` accessor — when to prefer it over
  the 25-arity tuple decomposition.

`packages/clausal-opencv/docs/opencv_imgproc.md` — extend with a
"Thresholding" subsection: `threshold/6`, `adaptive_threshold/7`,
`threshold_type/2` registry. Document the `used_thresh` output as the
Otsu/Triangle-computed level.

---

## Issues

### 1. Constants and registry names use lowercase — INHERITED FROM PHASE 1

`THRESH_*`, `RETR_*`, `CHAIN_APPROX_*`, `ADAPTIVE_THRESH_*` are
exported as `thresh_*`, `retr_*`, `chain_approx_*`,
`adaptive_thresh_*`. Registry short names follow the same
lowercase-and-strip-prefix recipe (`"binary"`, `"otsu"`, …). See
Phase 1 Issue 1.

### 2. `thresh_binary + thresh_otsu` does not evaluate in goal-arg position — DOCUMENTED

Clausal's arithmetic evaluator does not reduce a `BinOp` whose
operands resolve through `LoadName` to module-level Python ints when
that `BinOp` appears as a *predicate argument* (rather than the RHS
of an explicit `is`). In testing, `threshold(IMG, 0.0, 255.0,
thresh_binary + thresh_otsu, ...)` failed with the operands
remaining as a `BinOp` term passed to `cv2.threshold` as the type
argument.

`OTSU_TYPE is thresh_binary + thresh_otsu` *also* fails — same root
cause as Phase 1 Issue 4 (`is` doesn't reduce when the RHS contains
Var-bound names).

**Workaround:** pass `thresh_otsu` alone. Otsu already implies a
binary output (the cv2 documentation is misleading on this point —
the `THRESH_BINARY | THRESH_OTSU` idiom is required only because C++
needs *some* binary mode flag; cv2-python accepts `THRESH_OTSU`
standalone). Tests confirm: `threshold(IMG, 0.0, 255.0, thresh_otsu,
USED, _)` produces a valid binary image with the Otsu-computed
level.

This is documented in `opencv_imgproc.md` under the thresholding
section.

### 3. `==` does not unify with vars inside structures — DOCUMENTED

`bounding_rect(C, R), R == ("rect", _, _, _, _)` fails: `==` is
strict structural equality, not unification, so the `_`
placeholders on the RHS don't get bound to the corresponding
elements of the LHS tuple. **The pattern that works** is to pass
the tuple-with-`_`s directly to the predicate that produces it:

```clausal
bounding_rect(C, ("rect", X, Y, W, H))
```

This routes through the predicate's result-var unification (`unify`,
which descends into tuples and binds Vars on the way).

Same pattern applies to:

- `min_enclosing_circle(C, [_, _], RADIUS)` rather than separate
  `min_enclosing_circle(C, CENTER, RADIUS), CENTER == [_, _]`.
- `min_area_rect(C, ("rotated_rect", _, _, _))` rather than
  `min_area_rect(C, RR), RR == ("rotated_rect", _, _, _)`.
- `moments(IMG, True, ("moments_t", _, _, _, ...))` for a
  25-element tuple structural check.

Documented in `opencv_contours.md` under "Pattern matching". The
underlying behaviour is consistent across Phase 1's `min_max_loc`
checks — wherever a result is a tagged tuple, pass the pattern
through the predicate, not after.

### 4. `findContours` returns a tuple, not a list — HANDLED

`cv2.findContours` returns its `contours` slot as a `tuple` of
ndarrays in some OpenCV builds. The wrapper unconditionally wraps it
with `list(...)` before unification so `contour/2`'s enumeration
helper sees a list and `length/2` reports the right count.

### 5. `point_polygon_test` returns float, registry includes int comparisons — VERIFIED

`pointPolygonTest(..., measureDist=False)` returns `+1.0`, `0.0`, or
`-1.0` (floats, not ints). Tests assert `D == 1.0` and `D < 0.0`
which both work. Documented in `opencv_contours.md`.

### 6. `moments_field` on a non-`moments_t` term raises — DESIRED BEHAVIOUR

A user calling `moments_field(R, "m00", _)` on a `rect` term gets a
predicate failure (the `ValueError` is caught by `_pure`). Tested
explicitly via `not moments_field(M, "bogus", _)`. The error message
is preserved for debugging — only the predicate result is squelched.
