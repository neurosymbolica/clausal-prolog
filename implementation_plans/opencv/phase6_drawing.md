# Phase 6 — Drawing (non-mutating)

OpenCV's drawing primitives (`cv2.line`, `cv2.rectangle`, etc.) mutate
the destination image in place. The wrapper exposes **non-mutating
drawing predicates**: each predicate copies the source image, draws on
the copy, and unifies the copy as RESULT. This is the price of being
backtracking-safe — see [Step 3 — Purity](overview.md#step-3--purity-analysis)
of the overview.

All predicates are Tier 1 (pure relative to the predicate boundary —
the C-level mutation is hidden behind the copy).

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_draw.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend
  `_CONSTANT_NAMES` with `LINE_*`, `FONT_HERSHEY_*`, `MARKER_*`,
  `FILLED` constants.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase6_drawing.clausal`
- `packages/clausal-opencv/docs/opencv_draw.md`

---

## Predicates

| Name | Arity | Modes | Description |
|---|---|---|---|
| `line` | `/5` | `(+img, +p1, +p2, +color, -out)` | Default thickness=1, line_type=LINE_8 |
| `line` | `/6` | `(+img, +p1, +p2, +color, +thickness, -out)` | |
| `line` | `/7` | `(+img, +p1, +p2, +color, +thickness, +line_type, -out)` | |
| `arrowed_line` | `/5,/6,/7` | same shape as `line` | |
| `rectangle` | `/5,/6,/7` | `(+img, +pt1, +pt2, +color, -out)` ± thickness ± line_type | |
| `circle` | `/5,/6,/7` | `(+img, +center, +radius, +color, -out)` ± thickness ± line_type | |
| `ellipse` | `/8` | `(+img, +center, +axes, +angle, +start_angle, +end_angle, +color, -out)` | |
| `ellipse` | `/9` | `+thickness` | |
| `polylines` | `/5` | `(+img, +pts_list, +is_closed, +color, -out)` | |
| `polylines` | `/6` | `+thickness` | |
| `fill_poly` | `/4` | `(+img, +pts_list, +color, -out)` | |
| `put_text` | `/8` | `(+img, +text, +origin, +font, +scale, +color, +thickness, -out)` | |
| `put_text` | `/9` | `+line_type` | |
| `marker` | `/5` | `(+img, +position, +color, -out)` | Default marker_type=MARKER_CROSS, size=20, thickness=1 |
| `marker` | `/6,/7,/8` | `+marker_type` ± `+marker_size` ± `+thickness` | |
| `draw_contours` | `/5` | `(+img, +contours, +contour_idx, +color, -out)` | -1 for all |
| `draw_contours` | `/6` | `+thickness` | -1 for filled |
| `draw_keypoints` | `/4` | `(+img, +keypoints, +color, -out)` | |
| `draw_keypoints` | `/5` | `+flags` | |
| `draw_matches` | `/7` | `(+img1, +kp1, +img2, +kp2, +matches, +flags, -out)` | |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_draw.py
from clausal.modules.py._helpers import _pred, _pure
from clausal.modules.opencv import _cv
```

### The copy-on-write `_draw` helper

Add to `opencv_draw.py` (not `_helpers.py` — it's opencv-specific):

```python
def _draw(call):
    """Drawing dispatch: copy the source image, mutate the copy, return it.

    `call(canvas, *params)` mutates canvas in place. After the call,
    canvas is the result.
    """
    def fn(src, *params):
        canvas = src.copy()
        call(canvas, *params)
        return canvas
    return fn
```

This pairs with `_pure` — `_draw` produces a pure function from a
mutating one. Example:

```python
line = _pred("line",
    (5, _pure(_draw(lambda canvas, p1, p2, color:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color))))),
    (6, _pure(_draw(lambda canvas, p1, p2, color, thickness:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color),
                          int(thickness))))),
    (7, _pure(_draw(lambda canvas, p1, p2, color, thickness, line_type:
              _cv().line(canvas, tuple(p1), tuple(p2), tuple(color),
                          int(thickness), int(line_type))))),
)
```

Every drawing predicate follows this pattern. The `tuple(...)`
coercion converts list-style points (`[10, 20]`) and colours
(`[0, 255, 0]`) — Clausal users write lists naturally; OpenCV expects
tuples.

### `polylines/5,6` and `fill_poly/4`

These take a *list of point arrays*, not a single point array.
OpenCV's Python binding wants `[np.array([[x,y], [x,y], ...], int32)]`.
The wrapper converts a Clausal list-of-lists into the expected form:

```python
import numpy as _np

def _to_int32_poly_list(pts_list):
    # pts_list is a list of lists-of-pairs (or numpy arrays).
    # Convert each to an int32 ndarray with shape (N, 1, 2) which is
    # what cv2 polyline drawing expects.
    return [
        _np.asarray(p, dtype=_np.int32).reshape(-1, 1, 2)
        for p in pts_list
    ]

polylines = _pred("polylines",
    (5, _pure(_draw(lambda canvas, pts_list, is_closed, color:
              _cv().polylines(canvas, _to_int32_poly_list(pts_list),
                               bool(is_closed), tuple(color))))),
    (6, _pure(_draw(lambda canvas, pts_list, is_closed, color, thickness:
              _cv().polylines(canvas, _to_int32_poly_list(pts_list),
                               bool(is_closed), tuple(color),
                               int(thickness))))),
)
```

### `draw_keypoints` / `draw_matches`

These take `cv2.KeyPoint` lists and `cv2.DMatch` lists directly —
which are the native terms produced by Phase 7's detector/matcher
predicates. No conversion needed:

```python
draw_keypoints = _pred("draw_keypoints",
    (4, _pure(_draw(lambda canvas, kps, color:
              _cv().drawKeypoints(canvas, list(kps), canvas,
                                    color=tuple(color))))),
    (5, _pure(_draw(lambda canvas, kps, color, flags:
              _cv().drawKeypoints(canvas, list(kps), canvas,
                                    color=tuple(color), flags=int(flags))))),
)
```

Note: `cv2.drawKeypoints` *also* takes a destination image
explicitly — our `_draw` helper passes the canvas as both source and
destination, which is what we want.

### Constants exported

```python
_CONSTANT_NAMES |= frozenset([
    # Line types
    "LINE_4", "LINE_8", "LINE_AA", "FILLED",
    # Hershey fonts
    "FONT_HERSHEY_SIMPLEX", "FONT_HERSHEY_PLAIN",
    "FONT_HERSHEY_DUPLEX", "FONT_HERSHEY_COMPLEX",
    "FONT_HERSHEY_TRIPLEX", "FONT_HERSHEY_COMPLEX_SMALL",
    "FONT_HERSHEY_SCRIPT_SIMPLEX", "FONT_HERSHEY_SCRIPT_COMPLEX",
    "FONT_ITALIC",
    # Markers
    "MARKER_CROSS", "MARKER_TILTED_CROSS", "MARKER_STAR",
    "MARKER_DIAMOND", "MARKER_SQUARE", "MARKER_TRIANGLE_UP",
    "MARKER_TRIANGLE_DOWN",
    # Keypoint draw flags
    "DRAW_MATCHES_FLAGS_DEFAULT",
    "DRAW_MATCHES_FLAGS_DRAW_OVER_OUTIMG",
    "DRAW_MATCHES_FLAGS_NOT_DRAW_SINGLE_POINTS",
    "DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS",
])
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, absdiff, min_max_loc, copy_image, IMREAD_COLOR,
    LINE_AA, FILLED, FONT_HERSHEY_SIMPLEX
])
-import_from(py.opencv_draw, [
    line, rectangle, circle, ellipse, polylines, fill_poly,
    put_text, marker, draw_contours
])

Test("line does not mutate source") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    copy_image(IMG, SNAPSHOT),
    line(IMG, [0, 0], [3, 3], [0, 255, 0], OUT),
    # IMG must still equal SNAPSHOT — drawing was on a copy
    absdiff(IMG, SNAPSHOT, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("line actually draws on the copy") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    line(IMG, [0, 0], [3, 3], [0, 255, 0], OUT),
    absdiff(IMG, OUT, D),
    min_max_loc(D, R),
    R is ("min_max", _, MAX, _, _),
    MAX > 0
)

Test("rectangle preserves shape") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    rectangle(IMG, [0, 0], [3, 3], [255, 0, 0], 1, OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("circle filled with FILLED thickness") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    circle(IMG, [2, 2], 1, [0, 0, 255], FILLED, OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("put_text preserves shape") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    put_text(IMG, "hi", [0, 3], FONT_HERSHEY_SIMPLEX, 0.3,
             [255, 255, 255], 1, OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("polylines closed polygon") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    polylines(IMG, [[[0,0],[3,0],[3,3],[0,3]]], True, [0, 255, 0], OUT),
    shape(IMG, S),
    shape(OUT, S)
)

Test("fill_poly fills a polygon") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    fill_poly(IMG, [[[0,0],[3,0],[3,3],[0,3]]], [128, 128, 128], OUT),
    # Centre pixel should be (128, 128, 128) — check via min_max
    # on the absdiff of OUT minus a uniform 128 image (skip for now;
    # phase test focuses on shape and no-mutation).
    shape(IMG, S),
    shape(OUT, S)
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase6_drawing.clausal`:

- All Test cases above.
- Every drawing predicate's basic arity variant.
- The **no-mutation invariant** for `line`, `rectangle`, `circle`,
  `ellipse`, `polylines`, `fill_poly`, `put_text`, `marker`,
  `draw_contours`. Each test uses the `copy_image` + `absdiff` +
  `min_max_loc` pattern from the first test above.
- LINE_AA antialiasing flag — verify the output differs from LINE_8
  on a diagonal line (using `absdiff` + `min_max_loc`).

`draw_keypoints` and `draw_matches` are tested in Phase 7's tests
where the keypoints/matches inputs are available naturally.

### Python unit tests

None additional — the no-mutation invariant is enforced at the
`.clausal` level.

---

## Docs

`packages/clausal-opencv/docs/opencv_draw.md`:

- Intro: "OpenCV's drawing functions mutate the destination image in
  place. The Clausal wrapper exposes them as non-mutating predicates:
  each predicate copies the source, draws on the copy, and returns the
  copy as RESULT. This makes drawing safe to use inside relational
  pipelines without corrupting bound terms under backtracking."
- Performance note: each drawing call costs one `ndarray.copy()`. For
  tight inner loops over a single canvas, calling `cv2.line(...)`
  directly via `++()` may be appropriate — but the copy cost is usually
  dominated by the draw itself for any non-trivial canvas, so prefer
  the relational form.
- Worked example per predicate. Match the `.clausal` test cases.

---

## Issues

### 1. Constants use lowercase aliases — INHERITED FROM PHASE 1

`LINE_*`, `FONT_HERSHEY_*`, `MARKER_*`, `FILLED`,
`DRAW_MATCHES_FLAGS_*` exported as `line_*`, `font_hershey_*`,
`marker_*`, `filled`, `draw_matches_flags_*`. See Phase 1 Issue 1.

### 2. `_draw` helper is opencv-specific — DECIDED

The copy-on-write helper lives in `opencv_draw.py`, not in the
shared `_helpers.py`. The pattern is specific to opencv (it's the
only library wrapped so far that has in-place mutating drawing
APIs). If a future library has the same shape, the helper can be
lifted, but speculatively generalising before that happens has no
upside.

### 3. `draw_keypoints` / `draw_matches` ship now, are tested in Phase 7 — DOCUMENTED

These two predicates need a `cv2.KeyPoint` list or `cv2.DMatch`
list as input. Phase 7 will produce both from real detector and
matcher runs. To avoid building synthetic KeyPoint test fixtures
just for Phase 6, the predicates ship here (alongside the other
drawing primitives) and the integration tests live with Phase 7.
Documented in `opencv_draw.md`.

### 4. Polygon point lists need int32 reshape — HANDLED

`cv2.polylines` and `cv2.fillPoly` expect a Python list of ndarrays
with shape `(N, 1, 2)` and dtype `int32`. Clausal users naturally
write `[[[x, y], ...]]` — a list-of-lists. The
`_to_int32_poly_list` helper converts each polygon to the right
ndarray form via `np.asarray(..., dtype=np.int32).reshape(-1, 1, 2)`.
Tested directly via the `polylines` and `fill_poly` test cases.

### 5. Grayscale color is a 1-element list — DOCUMENTED

For 8-bit grayscale images, color is `[128]` (1-element list), not
`128`. The wrapper coerces lists to tuples via `tuple(color)`, so
`[128]` becomes `(128,)` which cv2 accepts. Color images use
`[b, g, r]` or `[b, g, r, a]`. Documented in `opencv_draw.md`.

### 6. `cv2.drawKeypoints` requires a destination argument — HANDLED

Unlike most cv2 drawing functions, `drawKeypoints(src, kps, dst)`
needs an explicit destination — it doesn't accept `dst=None`. The
wrapper passes the canvas as both source and destination (after the
`_draw` copy), which is what we want for in-place-on-the-copy
semantics.

### 7. `cv2.drawMatches` returns a brand-new image — HANDLED

Unlike the in-place drawers, `cv2.drawMatches(img1, kp1, img2, kp2,
matches, outImg=None)` *constructs* a new wide image (img1 and img2
side-by-side with match lines between them). The wrapper passes
`outImg=None` and returns whatever cv2 constructs. `_draw` is not
used for this one — there's no source to copy. Implementation is a
plain `_pure` over `_draw_matches`.
