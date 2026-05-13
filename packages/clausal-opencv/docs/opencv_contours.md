# `opencv_contours` — Contour extraction and measurements

Contours are the standard representation of object outlines in binary
images. OpenCV's `findContours` returns them as a list of *N*×1×2
int32 arrays. This module exposes the list (`find_contours/5,6`),
individual contours via `contour/2` (nondeterministic enumeration),
and a family of per-contour measurements: area, perimeter, moments,
convex hull, bounding shapes, polygonal approximation, and a
point-in-polygon test.

A small registry — `threshold_type/2` — also lives here for
symmetry with the Phase 3 registries; threshold predicates themselves
are in [`opencv_imgproc`](opencv_imgproc.md).

```clausal
-import_from(opencv, [
    imread_grayscale, thresh_binary, thresh_otsu,
    retr_external, retr_tree, chain_approx_simple,
])
-import_from(opencv_imgproc, [threshold])
-import_from(opencv_contours, [
    find_contours, contour, contour_area, contour_perimeter,
    moments, moments_field, convex_hull, bounding_rect,
    min_enclosing_circle, min_area_rect, approx_poly_dp,
    point_polygon_test, threshold_type,
])
```

## Predicate index

### Contour extraction

| Predicate | Arity | Notes |
|---|---|---|
| `find_contours(IMG, MODE, METHOD, CONTOURS, HIER)` | /5 | Returns both contour list and hierarchy array |
| `find_contours(IMG, MODE, METHOD, OFFSET, CONTOURS, HIER)` | /6 | With `OFFSET = [x, y]` translation |
| `contour(CONTOURS, C)` | /2 | **Nondeterministic** — yields each contour on backtracking |

### Per-contour measurements

| Predicate | Arity | Returns |
|---|---|---|
| `contour_area(C, AREA)` | /2 | Float; default `oriented=False` |
| `contour_area(C, ORIENTED, AREA)` | /3 | Float, possibly signed |
| `contour_perimeter(C, CLOSED, P)` | /3 | `cv2.arcLength` |
| `convex_hull(POINTS, HULL)` | /2 | Default `clockwise=False` |
| `convex_hull(POINTS, CLOCKWISE, HULL)` | /3 | |
| `bounding_rect(POINTS, RECT)` | /2 | `("rect", X, Y, W, H)` |
| `min_enclosing_circle(POINTS, CENTER, RADIUS)` | /3 | `CENTER = [cx, cy]`, `RADIUS` float |
| `min_area_rect(POINTS, ROTATED_RECT)` | /2 | `("rotated_rect", [cx, cy], [w, h], angle)` |
| `approx_poly_dp(C, EPSILON, CLOSED, APPROX)` | /4 | Ramer–Douglas–Peucker |
| `point_polygon_test(C, PT, MEASURE_DIST, RESULT)` | /4 | Signed distance or +1/0/-1 |

### Moments

| Predicate | Arity | Returns |
|---|---|---|
| `moments(C_OR_IMG, MOMENTS)` | /2 | `("moments_t", m00, m10, m01, …, nu03)` (25-tuple) |
| `moments(IMG, BINARY, MOMENTS)` | /3 | With explicit `binaryImage` flag |
| `moments_field(MOMENTS, NAME, VALUE)` | /3 | Field accessor by string name |

The moments record has 24 fields:

```
m00, m10, m01, m20, m11, m02,
m30, m21, m12, m03,
mu20, mu11, mu02, mu30, mu21, mu12, mu03,
nu20, nu11, nu02, nu30, nu21, nu12, nu03
```

Prefer `moments_field/3` over decomposing the 25-tuple in clause
heads — only specific fields are usually needed and the long
tuple-match is fragile to upstream changes.

### Registry

| Registry | Names |
|---|---|
| `threshold_type/2` | `binary`, `binary_inv`, `trunc`, `tozero`, `tozero_inv`, `otsu`, `triangle` |

## Term constructors

Three new tagged-tuple terms ship with this phase:

| Term | Decomposes as | Source |
|---|---|---|
| `("rect", X, Y, W, H)` | Five ints | `bounding_rect/2` |
| `("rotated_rect", [cx, cy], [w, h], angle)` | Two float lists + angle | `min_area_rect/2` |
| `("moments_t", m00, m10, …, nu03)` | Tag + 24 floats | `moments/2,3` |

The `rect` term is also used by Phase 8 (`detect_multi_scale`) and
Phase 9 (`min_area_rect` results from feature points), so unifying
on `("rect", X, Y, W, H)` in a clause head works across phases.

## Pattern matching

OpenCV result terms are tuples — match them by **passing the pattern
directly** to the predicate rather than via a separate `==` after the
fact:

```clausal
% Recommended — direct unification through the predicate result-var
bounding_rect(C, ("rect", X, Y, W, H))

% Equivalent (still works because the tuple is fully bound):
bounding_rect(C, ("rect", 10, 8, 12, 16))

% Avoid — `==` is strict equality, not unification, and won't bind
% the `_` placeholders inside the RHS:
bounding_rect(C, R),
R == ("rect", _, _, _, _)      % FAILS
```

See Phase 4 Issues for the underlying reason. This is the same trap
as in Phase 1's `min_max_loc` pattern usage.

## Worked examples

Each example below is an exact copy of an integration test in
`tests/fixtures/opencv_phase4_thresh_contours.clausal`.

### Extract a single rectangle's outline

```clausal
imread("/tmp/clausal_opencv_shapes.png", imread_grayscale, IMG),
threshold(IMG, 128.0, 255.0, thresh_binary, _, BIN),
find_contours(BIN, retr_external, chain_approx_simple, CS, _),
length(CS, 1)
```

### Enumerate contours via backtracking

```clausal
threshold(IMG, 128.0, 255.0, thresh_binary, _, BIN),
find_contours(BIN, retr_external, chain_approx_simple, CS, _),
findall(C, contour(CS, C), ALL),
length(ALL, 1)
```

### Read the bounding rectangle as `rect/4`

```clausal
threshold(IMG, 128.0, 255.0, thresh_binary, _, BIN),
find_contours(BIN, retr_external, chain_approx_simple, CS, _),
contour(CS, C),
bounding_rect(C, R),
R == ("rect", 10, 8, 12, 16)   % concrete check
```

### Use moments_field to read m00 and compare to contour area

```clausal
find_contours(BIN, retr_external, chain_approx_simple, CS, _),
contour(CS, C),
moments(C, M),
moments_field(M, "m00", M00),
contour_area(C, A),
A - M00 < 0.001
```

### point_polygon_test inside/outside

```clausal
% Inside the white rectangle (10..22 × 8..24): distance is positive.
point_polygon_test(C, [16, 16], True, D),
D > 0.0

% Outside the rectangle: distance is negative.
point_polygon_test(C, [0, 0], True, D),
D < 0.0
```

### Look up threshold type by name

```clausal
threshold_type("otsu", T),
T == thresh_otsu
```

### Enumerate all threshold types

```clausal
findall(N, threshold_type(N, _), NAMES),
length(NAMES, 7)
```

## See also

- [`opencv_imgproc`](opencv_imgproc.md) — the `threshold/6` and
  `adaptive_threshold/7` predicates that produce the binary images
  these contour predicates consume.
- [`opencv`](opencv.md) — exported constants (`retr_*`,
  `chain_approx_*`, `thresh_*`, `adaptive_thresh_*`) and the
  `min_max_loc` reduction.
