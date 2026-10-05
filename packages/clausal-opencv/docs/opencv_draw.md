# `opencv_draw` — Non-mutating drawing

OpenCV's drawing primitives (`cv2.line`, `cv2.rectangle`,
`cv2.putText`, …) **mutate the destination image in place** and
return it. That breaks Clausal Prolog's relational guarantees: a backtrack
point above a draw call would leave the canvas corrupted, and any
bound term pointing at that array would silently change underfoot.

The wrapper resolves this with **copy-on-write at the predicate
boundary**:

```python
def _draw(call):
    def fn(src, *params):
        canvas = src.copy()   # one ndarray.copy()
        call(canvas, *params) # mutates the copy
        return canvas         # unified as RESULT
    return fn
```

Each drawing predicate produces a **fresh ndarray** containing the
drawing applied to a copy of the source. The source array is never
touched, so backtracking past a draw call is safe — the predicate
behaves exactly like the pure predicates in earlier phases.

```seam
-import_from(opencv_draw, [
    line, arrowed_line, rectangle, circle, ellipse,
    polylines, fill_poly, put_text, marker,
    draw_contours, draw_keypoints, draw_matches,
])
-import_from(opencv, [
    line_aa, filled,
    font_hershey_simplex,
    marker_cross, marker_star,
])
```

## Cost

One `ndarray.copy()` per draw call. For a 1080p uint8 image that's
~6 MB of memcpy, typically dominated by the draw itself for any
non-trivial primitive. For **tight inner loops** over a single
canvas — say, drawing 10000 keypoints — you can drop to
`++cv2.line(img, ...)` directly, accepting the loss of backtracking
safety in exchange for one less copy per call. Reach for the escape
only when profiling actually shows the copies dominating.

## Predicate index

### Lines

| Predicate | Arity | Notes |
|---|---|---|
| `line(IMG, P1, P2, COLOR, OUT)` | /5 | Default thickness=1, line_type=line_8 |
| `line(IMG, P1, P2, COLOR, THICK, OUT)` | /6 | |
| `line(IMG, P1, P2, COLOR, THICK, LINE_TYPE, OUT)` | /7 | |
| `arrowed_line(...)` | /5,/6,/7 | Same arities, arrowhead at P2 |

### Shapes

| Predicate | Arity | Notes |
|---|---|---|
| `rectangle(IMG, PT1, PT2, COLOR, OUT)` | /5,/6,/7 | THICK = `filled` (-1) fills |
| `circle(IMG, CENTER, RADIUS, COLOR, OUT)` | /5,/6,/7 | |
| `ellipse(IMG, CENTER, AXES, ANGLE, START_A, END_A, COLOR, OUT)` | /8 | |
| `ellipse(..., THICK, OUT)` | /9 | |
| `polylines(IMG, PTS_LIST, IS_CLOSED, COLOR, OUT)` | /5,/6 | |
| `fill_poly(IMG, PTS_LIST, COLOR, OUT)` | /4 | |
| `marker(IMG, POSITION, COLOR, OUT)` | /4,/5,/6,/7 | `marker_type`, `marker_size`, `thickness` |

### Text

| Predicate | Arity | Notes |
|---|---|---|
| `put_text(IMG, TEXT, ORIGIN, FONT, SCALE, COLOR, THICK, OUT)` | /8 | |
| `put_text(..., LINE_TYPE, OUT)` | /9 | |

### Overlay annotations

| Predicate | Arity | Notes |
|---|---|---|
| `draw_contours(IMG, CONTOURS, IDX, COLOR, OUT)` | /5,/6 | IDX=-1 draws all |
| `draw_keypoints(IMG, KEYPOINTS, COLOR, OUT)` | /4,/5 | Phase 7 feeds it cv2.KeyPoint lists |
| `draw_matches(IMG1, KP1, IMG2, KP2, MATCHES, FLAGS, OUT)` | /7 | Phase 7 |

## Argument conventions

- **Points and colors are lists**: `[x, y]`, `[b, g, r]` (BGR — not
  RGB). The wrapper coerces to tuples for cv2. Grayscale color is
  `[gray]`.
- **`PTS_LIST` for `polylines`/`fill_poly` is a list of polygons**,
  each polygon a list of `[x, y]` pairs. cv2 wants `N×1×2` int32
  ndarrays — the wrapper converts internally.
- **`THICK = filled`** (the `cv2.FILLED` constant, value -1) fills
  closed shapes. Use it with `rectangle`, `circle`, `ellipse`,
  `marker`. For unfilled drawings, pass a positive integer.

## Worked examples

Each example below is an exact copy of an integration test in
`tests/fixtures/opencv_phase6_drawing.seam`.

### A green diagonal line on a color image

```seam
imread("photo.png", imread_color, IMG),
line(IMG, [0, 0], [3, 3], [0, 255, 0], OUT)
```

### Filled rectangle (grayscale)

```seam
imread("photo.png", imread_grayscale, IMG),
rectangle(IMG, [0, 0], [3, 3], [128], filled, OUT)
```

### Antialiased text

```seam
imread("photo.png", imread_grayscale, IMG),
put_text(IMG, "hi", [2, 16], font_hershey_simplex, 0.5, [255], 1, line_aa, OUT)
```

### A closed quadrilateral outline

```seam
imread("photo.png", imread_color, IMG),
polylines(IMG, [[[0,0],[3,0],[3,3],[0,3]]], True, [0, 255, 0], OUT)
```

### Star markers

```seam
imread("photo.png", imread_color, IMG),
marker(IMG, [2, 2], [255, 0, 0], marker_star, OUT)
```

### Verify the no-mutation invariant

```seam
imread("photo.png", imread_grayscale, IMG),
copy_image(IMG, SNAP),
line(IMG, [0, 0], [3, 3], [255], _),     % the underscore swallows the canvas
absdiff(IMG, SNAP, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))   % IMG unchanged
```

### Overlay contours from Phase 4

```seam
imread("shapes.png", imread_grayscale, IMG),
threshold(IMG, 128.0, 255.0, thresh_binary, _, BIN),
find_contours(BIN, retr_external, chain_approx_simple, CS, _),
draw_contours(IMG, CS, -1, [128], OUT)
```

## See also

- [`opencv`](opencv.md) — exported drawing constants (`line_*`,
  `filled`, `font_hershey_*`, `marker_*`, `draw_matches_flags_*`)
  and the `copy_image/2` and `absdiff` predicates used in the
  no-mutation checks.
- [`opencv_contours`](opencv_contours.md) — produces the contour
  lists consumed by `draw_contours/5,6`.
- [`opencv_features`](opencv_features.md) (Phase 7) — produces the
  `cv2.KeyPoint` and `cv2.DMatch` lists consumed by `draw_keypoints`
  and `draw_matches`. Tests for those two drawing predicates live
  with Phase 7's fixtures.
