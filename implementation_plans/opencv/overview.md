# OpenCV (opencv-python) Wrapper — Overview

OpenCV is a large computer-vision library exposed to Python as the `cv2`
module. Unlike scikit-learn (one Estimator pattern) or PyTorch (four
subsystems), OpenCV is a **flat grab-bag of ~1500 functions plus a small
zoo of stateful objects** (detectors, capture devices, matchers,
cascades). The unifying data type is the **numpy ndarray as image**;
almost every function consumes one or more arrays and either returns a
new array or — for drawing — mutates the destination in place.

The wrapper strategy:

1. Treat the image (`np.ndarray`) as the central term — it's already
   first-class in Clausal and is used by every other numpy-aware
   wrapper.
2. Wrap pure operations (filters, color conversions, geometric
   transforms, thresholding, FFT, morphology, etc.) as Tier 1
   predicates with a numpy-array RESULT.
3. Wrap detectors / matchers / capture devices as Tier 3 handle-based
   predicates following the `MakeKdTree` pattern from
   `scipy_spatial.py`.
4. Replace in-place drawing with **non-mutating drawing predicates**
   that copy the source array, draw on the copy, and return it as
   RESULT. The mutating C-level call is hidden in the dispatch.
5. Export the constellation of `cv2.*` flag constants (interpolation
   modes, border types, color conversion codes, threshold types,
   morphology shapes, contour modes, image-read flags, etc.) directly
   from the wrapper module so users never need `++(cv2.BORDER_REFLECT)`.

The wrapper lives in a new package `packages/clausal-opencv/`
mirroring the layout of `packages/clausal-torch/` and
`packages/clausal-scipy/`.

---

## Package layout

```
packages/clausal-opencv/
    pyproject.toml
    README.md
    clausal/
        modules/
            opencv.py              # Phase 1 entry — core, IO, properties, arithmetic, exports
            opencv_imgproc.py      # filters, morphology, edges, thresholding, geometric
            opencv_color.py        # color conversions (cvtColor + helpers)
            opencv_features.py     # ORB, SIFT, AKAZE, KAZE, BRISK, FAST, matchers, KeyPoint/DMatch terms
            opencv_objdetect.py    # CascadeClassifier, HOGDescriptor
            opencv_calib3d.py      # camera calibration, findHomography, solvePnP, stereo
            opencv_video.py        # VideoCapture, VideoWriter
            opencv_draw.py         # non-mutating drawing predicates
            opencv_contours.py     # findContours, contour area/perimeter/moments/hull
            _opencv_handles.py     # shared handle registry helpers
    tests/
        clausal_files/
            opencv_phase1_core.clausal
            opencv_phase2_color.clausal
            ...
        test_opencv_infra.py       # registry / lazy-import unit tests only
        fixtures/
            tiny_gray.png
            tiny_rgb.png
    docs/
        opencv.md
        opencv_imgproc.md
        opencv_color.md
        opencv_features.md
        opencv_objdetect.md
        opencv_calib3d.md
        opencv_video.md
        opencv_draw.md
        opencv_contours.md
```

`opencv.py` is the main module — it owns the lazy `import cv2` guard,
the `_cv()` accessor, the constant exports, and the core arithmetic /
property predicates. Other files import `_cv` from `opencv.py` to share
the same loaded module.

---

## Phases

### Planned

- [Phase 1 — Core, I/O, Properties, Arithmetic](phase1_core_io.md):
  `imread`, `imwrite`, `imencode`/`imdecode` (bijective),
  `shape`/`dtype`/`channels_count` (multi-mode), `add`, `subtract`,
  `multiply`, `divide`, `absdiff`, `bitwise_and/or/xor/not`, `min`,
  `max`, `mean`, `min_max_loc`, `flip`, `transpose`, `copy_image`,
  constants export.

- [Phase 2 — Color Conversions](phase2_color.md): `cvt_color` (single
  multi-mode predicate driven by COLOR_* code), `channels`
  (`split`/`merge` collapsed bijectively), color-code registry.

- [Phase 3 — Filtering and Morphology](phase3_filtering.md):
  `gaussian_blur`, `median_blur`, `box_filter`, `bilateral_filter`,
  `filter_2d`, `sep_filter_2d`, `sobel`, `scharr`, `laplacian`,
  `canny`, `morphology_ex`, `erode`, `dilate`,
  `get_structuring_element`, `pyr_down`, `pyr_up`.

- [Phase 4 — Thresholding and Contours](phase4_thresh_contours.md):
  `threshold` (bidirectional in the level/result sense — see phase
  notes), `adaptive_threshold`, `find_contours` (nondeterministic
  enumeration), `contour_area`, `contour_perimeter`, `moments`,
  `convex_hull`, `bounding_rect`, `min_enclosing_circle`,
  `min_area_rect`, `approx_poly_dp`, `point_polygon_test`.

- [Phase 5 — Geometric Transformations](phase5_geometric.md): `resize`,
  `warp_affine`, `warp_perspective`, `rotate`,
  `get_rotation_matrix_2d`, `get_affine_transform`,
  `get_perspective_transform`, `invert_affine_transform` (bijective
  via `affine_inverse`), `remap`, `pyr_mean_shift_filter`,
  `copy_make_border`.

- [Phase 6 — Drawing (non-mutating)](phase6_drawing.md): `line`,
  `rectangle`, `circle`, `ellipse`, `polylines`, `fill_poly`,
  `put_text`, `arrowed_line`, `marker`, `draw_contours`,
  `draw_keypoints`, `draw_matches`, font and line-type constants.

- [Phase 7 — Features and Matching](phase7_features.md):
  `make_orb`, `make_sift`, `make_akaze`, `make_kaze`, `make_brisk`,
  `make_fast`, `detect`, `compute`, `detect_and_compute`,
  `make_bf_matcher`, `make_flann_matcher`, `match`, `knn_match`,
  `radius_match`, `KeyPoint` / `DMatch` term decomposition.

- [Phase 8 — Object Detection](phase8_objdetect.md):
  `make_cascade_classifier`, `detect_multi_scale`, `make_hog`,
  `hog_compute`, `hog_detect`, built-in HOG people detector.

- [Phase 9 — Camera Calibration and Homography](phase9_calib3d.md):
  `find_homography`, `find_fundamental_mat`, `find_essential_mat`,
  `solve_pnp`, `solve_pnp_ransac`, `calibrate_camera`,
  `project_points`, `undistort`, `init_undistort_rectify_map`,
  `Rodrigues` (bijective), `decompose_homography_mat`,
  `recover_pose`.

- [Phase 10 — Video I/O](phase10_video.md): `make_video_capture`,
  `video_property`, `read_frame` (nondeterministic — yields each
  frame on backtracking), `make_video_writer`, `write_frame`,
  `release`, FOURCC code helpers.

### Deferred (Future Work)

- **Optical flow** (`calcOpticalFlowPyrLK`, `calcOpticalFlowFarneback`,
  DIS): the iterator-over-pyramid pattern fits Tier 3 but the API
  surface is large enough to warrant its own phase.
- **Segmentation** (`grabCut`, `watershed`, `floodFill`): stateful
  with iterative refinement loops; needs careful purity design.
- **Stitching** (`Stitcher`): high-level pipeline orchestration.
- **Photo** (`fastNlMeansDenoising`, `inpaint`, HDR): straightforward
  to wrap but niche.
- **`cv2.dnn`**: overlaps heavily with `clausal-torch` — better to
  call torch through its existing wrapper than to redo NN inference.
- **`cv2.ml`**: overlaps heavily with `clausal-sklearn`.

### Out of scope

- **`cv2.highgui`** (`imshow`, `waitKey`, `namedWindow`, trackbars):
  interactive UI is not a logic-programming task and many CI
  environments are headless.
- **UMat / GPU acceleration** (`cv2.cuda.*`, `cv2.UMat`): the wrapper
  treats images as numpy arrays; GPU mat handling belongs in a
  separate future package.
- **C++-only APIs** not exposed by `opencv-python`.

---

## Step 1 — Core Abstraction

The central concept is the **image as numpy ndarray**:

- **Shape conventions:** `(H, W)` for single-channel (grayscale, mask,
  depth), `(H, W, C)` for multi-channel (BGR is the default — OpenCV
  is BGR, not RGB).
- **Dtype conventions:** `uint8` for 8-bit images (most common),
  `uint16` for 16-bit, `float32` for floating-point intermediates and
  many calibration outputs, `int32` for label maps.
- **Lifecycle:** read or generate → transform (pure pipeline) →
  display, write, or analyse.

This is the same abstraction as `scipy.ndimage` already wraps, but
OpenCV's coverage is much broader — it has filtering, geometric
transforms, color conversions, drawing, features, detectors,
calibration, and video all in one library, where scipy splits these
across `ndimage`, `signal`, `linalg`, etc.

OpenCV also has a handful of stateful objects:

- **Detectors / descriptor extractors** (`cv2.ORB`, `cv2.SIFT`,
  `cv2.CascadeClassifier`, `cv2.HOGDescriptor`): constructed once,
  queried many times; configuration is immutable after construction.
- **Matchers** (`cv2.BFMatcher`, `cv2.FlannBasedMatcher`): hold
  trained descriptor sets for repeated matching.
- **Capture / Writer** (`cv2.VideoCapture`, `cv2.VideoWriter`):
  resource-holding IO objects.

These are all classic Tier 3 handle-based wrappings.

---

## Step 2 — Bijective Relationships

### Strict bijections (both directions computable)

| Procedural pair | Predicate | Notes |
|---|---|---|
| `cv2.imencode(ext, img)` / `cv2.imdecode(buf, flags)` | `image_encoded(IMG, EXT, BUF)` | Encode/decode the same bytes |
| `cv2.dft(img)` / `cv2.idft(spec)` | `dft(IMG, SPEC)` | Forward / inverse DFT |
| `cv2.merge(channels)` / `cv2.split(img)` | `channels(IMG, CHANNELS)` | Lists ↔ multi-channel |
| `cv2.Rodrigues(rvec)` / `cv2.Rodrigues(rmat)` | `rodrigues(RVEC, RMAT)` | 3-vector ↔ rotation matrix (cv2 detects which input was given) |
| `cv2.invertAffineTransform(M)` | `affine_inverse(M, M_INV)` | Self-inverse: `affine_inverse(affine_inverse(M)) == M` |
| `cv2.flip(img, code)` self-inverse at given code | `flip(IMG, CODE, OUT)` | `flip(flip(I,C),C) == I` |

### Multi-mode property queries

| Property | Predicate | Modes |
|---|---|---|
| `img.shape` | `shape(IMG, SHAPE)` | `(+,-)` query, `(+,+)` check |
| `img.dtype` | `dtype(IMG, D)` | `(+,-)` query, `(+,+)` check |
| `img.shape[2]` (or 1 if 2-D) | `channels_count(IMG, N)` | `(+,-)` query, `(+,+)` check |
| `img.size` | `element_count(IMG, N)` | `(+,-)` query |
| `(img.shape[1], img.shape[0])` | `size(IMG, [W, H])` | `(+,-)` query, `(+,+)` check |

### Multi-mode operation predicates

| Operation | Predicate | Modes |
|---|---|---|
| `cv2.cvtColor(img, code)` | `cvt_color(SRC_CODE, DST_CODE, SRC_IMG, DST_IMG)` | partial: forward `(+,+,+,-)` always; backward only when an inverse color code exists (e.g. BGR2RGB ↔ RGB2BGR) |
| `cv2.threshold(img, level, max, type)` | `threshold(IMG, LEVEL, MAX, TYPE, USED_LEVEL, OUT)` | `(+,+,+,+,-,-)`; with `THRESH_OTSU`/`THRESH_TRIANGLE` the computed level is unified into `USED_LEVEL` |

### Enumerables (nondeterministic via backtracking)

| Collection | Predicate | Yields |
|---|---|---|
| `cv2.findContours(...)[0]` | `contour(CONTOURS, C)` | Each contour (Nx1x2 int32 array) |
| `detector.detect(img)` | `keypoint(KEYPOINTS, KP)` | Each `cv2.KeyPoint` |
| `matcher.match(qd, td)` | `match_pair(MATCHES, M)` | Each `cv2.DMatch` |
| `cap.read()` loop | `video_frame(CAP_HANDLE, INDEX, FRAME)` | Frames until end-of-stream (see Phase 10 notes) |

### Broader relational patterns

- **Interpolation flag registry** — `interpolation(NAME, CODE)`:
  `nearest`/`linear`/`cubic`/`area`/`lanczos4` ↔ `cv2.INTER_*`.
- **Border type registry** — `border_type(NAME, CODE)`: `constant`,
  `replicate`, `reflect`, `reflect_101`, `wrap`, `isolated`.
- **Threshold type registry** — `threshold_type(NAME, CODE)`:
  `binary`, `binary_inv`, `trunc`, `tozero`, `tozero_inv`, `otsu`,
  `triangle`.
- **Morphology operation registry** — `morph_op(NAME, CODE)`:
  `erode`, `dilate`, `open`, `close`, `gradient`, `tophat`,
  `blackhat`, `hitmiss`.
- **Morphology shape registry** — `morph_shape(NAME, CODE)`: `rect`,
  `ellipse`, `cross`.
- **Color code registry** — `color_code(NAME, CODE)`: lowercase forms
  of every `cv2.COLOR_*` constant (hundreds), generated via
  introspection on first use.
- **Image read-flag registry** — `imread_flag(NAME, CODE)`:
  `grayscale`, `color`, `unchanged`, `anydepth`, `anycolor`.
- **Distance type registry** (`distance_transform`) —
  `distance_type(NAME, CODE)`: `l1`, `l2`, `c`.

These registries enable both name-as-data lookup (reading a config
that says `"interpolation": "cubic"` and resolving to `cv2.INTER_CUBIC`
at runtime) and `findall`-style discovery. They fit pattern (2) of
[Step 5d](../EXTERNAL_WRAPPER_CHECKLIST.md#step-5d--when-to-add-a-registry).

---

## Step 3 — Purity Analysis

### Pure (backtracking-safe)

The vast majority of OpenCV's surface. Filtering, color conversion,
geometric warps, thresholding, edge detection, morphology, FFT, feature
description, matching, calibration math, homography computation — these
all consume input arrays and produce new output arrays without
modifying the inputs.

In `cv2`'s Python bindings, the `dst=` parameter is *optional*; when
omitted, the function allocates and returns a fresh array. The wrapper
always omits `dst=` so the function is effectively pure even though the
C++ underneath may write into a pre-allocated buffer when given one.

### Pseudo-stateful — drawing operations

`cv2.line`, `cv2.rectangle`, `cv2.putText`, `cv2.drawContours`, etc.
mutate the destination image in place and return it. Used directly,
this would corrupt previously-bound terms under backtracking.

**Wrapping strategy:** the wrapper makes a **copy of the source image**
inside the dispatch, draws on the copy, and unifies the copy as RESULT.
Backtracking abandons the copy; the original is untouched.

```python
# Conceptual dispatch (Phase 6):
def _draw(call):
    def dispatch(..., src, *params, result_var, trail):
        canvas = src.copy()
        call(canvas, *params)
        unify(result_var, canvas, trail)
        ...
```

The cost (one `np.ndarray.copy`) is the price of relational drawing.
For tight inner loops the user can drop to `++cv2.line(...)` directly —
documented in the phase notes.

### Stateful (handle-based, Tier 3)

| Object | Lifecycle | Backtracking treatment |
|---|---|---|
| `cv2.ORB`, `cv2.SIFT`, `cv2.AKAZE`, `cv2.KAZE`, `cv2.BRISK`, `cv2.FastFeatureDetector` | construct → detect/compute many times | Configuration is immutable after construction; detectors are effectively pure once built. Handle stored in registry, `detect`/`compute` are pure relative to the handle. |
| `cv2.BFMatcher`, `cv2.FlannBasedMatcher` | construct → optionally train → match | Treat `match` as pure relative to the handle plus its added descriptors. Avoid `matcher.add(...)`-then-mutate; use the train-and-build-handle convention via a top-level `make_bf_matcher_trained` instead, so adding descriptors yields a new handle. |
| `cv2.CascadeClassifier` | load from XML → detect | Read-only after load; pure relative to the handle. |
| `cv2.HOGDescriptor` | construct → compute/detect | Read-only after construction. |
| `cv2.VideoCapture` | open → read frames → release | **Truly stateful** — each `read()` advances an internal cursor. Treated as Tier 4 IO; iteration via the nondeterministic `video_frame/3` predicate is documented as **not safe to backtrack across**. |
| `cv2.VideoWriter` | open → write frames → release | Tier 4 IO. |

The handle registry mirrors `scipy_spatial.py`: a process-local dict
mapping integer handles to objects, with a `free/1` predicate for
cleanup. Detector / matcher / cascade handles have no internal mutation,
so backtracking over `detect`/`match` is safe — the registry entry is
never modified after `make_*` returns.

### Constraint-like

OpenCV has no operations that benefit from a CLP-style wrapping in the
sense of `clpq.rational/1` or `z3.integer/1`. Camera calibration and
homography fitting are solvers internally, but their Python API is
"feed points, get a result" — already in the right shape for a
Tier-1-or-2 predicate. No solver-style infrastructure is needed.

### Decisions

- **Drawing**: copy-on-write at the predicate boundary. Document the
  trade-off in `opencv_draw.md`.
- **Video capture**: keep IO-level honesty — read returns a frame, but
  the predicate is acknowledged as having side effects. Provide a
  `read_frame/3` that yields frames lazily but commits each read to
  the underlying capture cursor; backtracking does **not** rewind the
  stream. Document this and recommend `seek`/`set` for seekable
  files.
- **All other operations**: pure. No state threading is required.

---

## Step 4 — Tier Classification

| Tier | Operations |
|---|---|
| **1 — Pure** | All filtering, color conversion, geometric transforms, thresholding, edge detection, morphology, FFT, calibration math, homography, drawing (via copy-on-write), arithmetic, bitwise ops, property queries |
| **2 — Fact tables** | Interpolation, border, threshold, morphology op/shape, color code, image-read flag, distance-type, FOURCC registries |
| **3 — Handle-based** | ORB / SIFT / AKAZE / KAZE / BRISK / FAST detectors, BF / FLANN matchers, CascadeClassifier, HOGDescriptor |
| **4 — IO / Impure** | `imread`, `imwrite`, `VideoCapture` / `VideoWriter` (read/write frames, release) |

---

## Step 5 — Scope

### In scope

Everything listed in **Phases 1–10** above. Coverage rationale:

- **Phase 1–6** covers the standard image-processing pipeline (load,
  convert, filter, threshold, find contours, transform, draw) — the
  workflow ~80% of OpenCV users actually run.
- **Phase 7** covers classical feature matching, which still has
  active use in panorama stitching, structure-from-motion, AR
  tracking, and as a baseline for deep matching pipelines.
- **Phase 8** covers Haar / HOG detectors — pre-deep-learning object
  detection that's still useful for small problems and educational
  examples.
- **Phase 9** covers calibration / homography — needed by anyone
  doing 3D geometry, AR, or stereo vision with OpenCV.
- **Phase 10** covers video IO — the gateway to per-frame processing
  pipelines that compose all the earlier phases.

### Out of scope (stays as `++cv2.*(...)`)

- **`cv2.highgui`** — interactive UI. Users compose with `matplotlib`
  or `cv2.imshow` directly when they need it.
- **`cv2.dnn`** — neural-net inference. The torch wrapper covers this
  better.
- **`cv2.ml`** — classical ML. The sklearn wrapper covers this better.
- **`cv2.cuda.*`**, **UMat** — GPU acceleration. Belongs in a separate
  `clausal-opencv-cuda` package if/when needed.

### Deferred

Listed in the **Deferred** subsection of [Phases](#phases) above.

---

## Step 5b — `++()` Escape Minimisation

The showcase example (Step 9) has **zero `++()` escapes**. Achieving
this requires:

### Constants exported from `py.opencv`

Constants are surfaced two ways:

1. **By-name imports** — every commonly-used flag constant is exported
   from `py.opencv` directly so users can write
   `-import_from(py.opencv, [INTER_CUBIC, BORDER_REFLECT, ...])` and
   pass `INTER_CUBIC` as an argument. The implementation re-exports
   `cv2.INTER_*`, `cv2.BORDER_*`, `cv2.COLOR_*`, `cv2.THRESH_*`,
   `cv2.MORPH_*`, `cv2.RETR_*`, `cv2.CHAIN_APPROX_*`, `cv2.IMREAD_*`,
   `cv2.ADAPTIVE_THRESH_*`, `cv2.DIST_*`, `cv2.CV_8U` etc.,
   `cv2.NORM_*`, `cv2.LINE_*`, `cv2.FONT_*`, `cv2.MARKER_*`, and
   `cv2.FILLED`.

2. **By-name registries** — for cases where the user has a *string*
   from a config file (`"cubic"`, `"reflect"`), the registries
   (`interpolation/2`, `border_type/2`, etc.) look up the integer
   code. This is the [Step 5d](../EXTERNAL_WRAPPER_CHECKLIST.md#step-5d--when-to-add-a-registry)
   pattern-(2) name-as-data lookup.

### Check predicates for boolean properties

| Python expression | Predicate |
|---|---|
| `img.ndim == 2` | `is_grayscale(IMG)` |
| `img.ndim == 3 and img.shape[2] == 3` | `is_color(IMG)` |
| `img.dtype == np.uint8` | `is_uint8(IMG)` |
| `cv2.VideoCapture.isOpened()` | `is_open(CAP_HANDLE)` |
| `keypoint.octave & 0xff` (etc.) | Decomposable via `keypoint/6` (see Phase 7) |

### String representations

- Colour-conversion codes are exposed by **name** (`"BGR2GRAY"`) via
  `color_code/2`; the integer code is also exported as a constant
  (`COLOR_BGR2GRAY`). User-facing predicates accept either.
- FOURCC codes — `cv2.VideoWriter_fourcc('m','p','4','v')` is wrapped
  by `fourcc(CHARS, CODE)` which takes a 4-character string and
  returns the integer code (bijective).

### Module name shadowing

`-import_from(py.opencv, [...])` shadows `-import_module(opencv)`,
which is harmless because `opencv` isn't a real Python module name
(it's `cv2`). Users who need raw `cv2.*` can write
`-import_module(cv2)` independently — no conflict with `py.opencv`.

### Showcase audit

The Phase 9 example (full panorama-stitch pipeline) uses only
predicates and exported constants — no `++()`. Verified in
[Step 9](#step-9--showcase-example) below.

---

## Step 5c — Quantity (Units) Awareness

Image pixel values are typically dimensionless (intensity counts on
[0, 255] or [0, 1]). The cases where `Quantity` matters in computer
vision are:

- **Spatial coordinates** in metres when working with calibrated
  cameras (`solve_pnp`, `project_points`, stereo reconstruction).
- **Camera focal length / principal point** in pixels.
- **Time** in seconds (frame timestamps from `VideoCapture.get`).

These are narrow use cases. The wrapper assigns propagators
conservatively — most predicates use `PASS_THROUGH_FIRST` (output
inherits the input image's dimensions, which are usually `None`) or
`STRIP_TO_PLAIN` (boolean masks, distance values).

Propagator assignments per phase:

| Phase | Group | Propagator | Rationale |
|---|---|---|---|
| 1 | arithmetic (`add`, `subtract`, `multiply`, `divide`, `absdiff`) | algebraic | matches scipy convention |
| 1 | bitwise (`bitwise_and/or/xor/not`) | `STRIP_TO_PLAIN` | bool output |
| 1 | reductions (`mean`, `min`, `max`, `min_max_loc`) | `PASS_THROUGH_FIRST` | scalar in same unit |
| 1 | properties (`shape`, `dtype`, `channels_count`) | none — non-numeric output |
| 2 | `cvt_color` | `PASS_THROUGH_FIRST` | colour space change, dims unchanged |
| 2 | `channels` | `PASS_THROUGH_FIRST` |
| 3 | smoothing/edge/morphology | `PASS_THROUGH_FIRST` | image-shaped output, same dims |
| 4 | `threshold`, `adaptive_threshold` | `STRIP_TO_PLAIN` | binary output |
| 4 | contour measurements (`contour_area`, `contour_perimeter`, `moments`) | `STRIP_TO_PLAIN` | pixel counts — dimensionless |
| 5 | geometric warps (`resize`, `warp_affine`, `warp_perspective`, `rotate`) | `PASS_THROUGH_FIRST` |
| 6 | drawing | `PASS_THROUGH_FIRST` |
| 7 | features — descriptors, keypoints | `STRIP_TO_PLAIN` | counts, indices |
| 8 | object detection — bounding boxes | `STRIP_TO_PLAIN` | integer rectangles |
| 9 | calibration math | mixed — see phase file |
| 10 | video IO | none — handle-based |

Implementation is one line per predicate via `make_quantity_aware`
from `clausal.modules._scipy_units` (re-used from the scipy package).
Zero overhead when `_SCIPY_UNITS_ENABLED = False`.

---

## Step 5d — Registry Decisions

The wrapper proposes **eight registries**, all listed under
[Step 2 — Broader relational patterns](#broader-relational-patterns).
For each, the legitimacy pattern that applies:

| Registry | Legitimacy pattern |
|---|---|
| `interpolation/2` | (2) name-as-data — interpolation modes are read from config files / user prefs and passed to `resize`/`warp_*`. Per-predicate alternatives (`resize_cubic`) would explode the catalogue. |
| `border_type/2` | (2) name-as-data — same argument-passing rationale. |
| `threshold_type/2` | (2) name-as-data — threshold mode often comes from config. |
| `morph_op/2` | (1) construction surface — `morphology_ex(IMG, KERNEL, OP_CODE, OUT)` takes the op as data. |
| `morph_shape/2` | (2) name-as-data — passed to `get_structuring_element`. |
| `color_code/2` | (2) name-as-data — there are hundreds of `COLOR_*` constants; per-predicate (`bgr_to_rgb`, `bgr_to_gray`, ...) would explode. The registry IS the practical surface. (3) enumeration is also real — `findall(N, color_code(N, _), Names)` is genuinely useful for discovery. |
| `imread_flag/2` | (2) name-as-data — load mode from config. |
| `distance_type/2` | (2) name-as-data — only three values but exposed as a registry for symmetry with the other flag groups, AND because the per-predicate alternative isn't sensible (you don't write `distance_transform_l1` etc.). |

All eight registries pass [Checklist J](../EXTERNAL_WRAPPER_CHECKLIST.md#checklist-j--registry-audit):
each maps to a real workflow (config-driven flag selection), not
"symmetry with neighbouring registries". The `findall(N, color_code(N, _), _)`
exercise is part of the Phase 2 test suite, not a presence-check.

The wrapper does **not** add registries for:

- **Per-detector type** (`detector(NAME, CLASS)`): the per-class
  `make_orb`/`make_sift`/... predicates are the construction surface
  (each has different parameters). A `detector_type/2` registry would
  add nothing — its only use case (`detector_type("sift", CLASS), CLASS(...)`)
  is already covered by `make_sift/...`. Excluded.
- **Image dtypes**: `np.uint8`, `np.float32` etc. are already
  importable from `numpy`. Cross-package duplication serves no one.

---

## Step 6 — Term Language

### Library types used directly

OpenCV's Python bindings expose several types that are first-class in
Clausal — usable as terms without wrapping:

| Type | Role | Notes |
|---|---|---|
| `numpy.ndarray` | Images and matrices | The dominant term type. Already shared with scipy/torch/jax wrappers. |
| `cv2.KeyPoint` | Feature keypoint | Attributes: `pt` (x, y), `size`, `angle`, `response`, `octave`, `class_id`. |
| `cv2.DMatch` | Descriptor match | Attributes: `queryIdx`, `trainIdx`, `imgIdx`, `distance`. |
| `tuple` | Point `(x, y)`, size `(w, h)`, scalar `(b, g, r)` or `(b, g, r, a)`, rect `(x, y, w, h)` | OpenCV's Python idiom. Tuples are first-class in Clausal. |

### Wrapper-defined terms

| Term | Constructor / decomposition | Semantics |
|---|---|---|
| `rect(X, Y, W, H)` | tagged decomposition of an `(x, y, w, h)` tuple | Bounding rectangle from `bounding_rect`, cascade detection, etc. Decomposes for pattern matching in clause heads. |
| `rotated_rect(CENTER, SIZE, ANGLE)` | tagged decomposition of `((cx, cy), (w, h), angle)` | Output of `min_area_rect`. |
| `min_max(MIN_VAL, MAX_VAL, MIN_LOC, MAX_LOC)` | result of `min_max_loc` | Single term for the four-way result. |
| `moments_t(M00, M10, M01, M20, M11, M02, M30, M21, M12, M03, MU20, MU11, MU02, MU30, MU21, MU12, MU03, NU20, NU11, NU02, NU30, NU21, NU12, NU03)` | result of `moments` | Full image-moment record. In practice users access individual fields via the `moments_field/3` predicate (see Phase 4) so the long tuple is rarely decomposed directly. |
| `keypoint(PT, SIZE, ANGLE, RESPONSE, OCTAVE, CLASS_ID)` | decomposition of `cv2.KeyPoint` | Used by `keypoint_decompose/7` in Phase 7. The native `cv2.KeyPoint` is the canonical term; the tagged form is for clause-head matching. |
| `dmatch(QUERY_IDX, TRAIN_IDX, IMG_IDX, DISTANCE)` | decomposition of `cv2.DMatch` | Same pattern as `keypoint`. |

### Decomposition examples

```clausal
# Pattern-match the result of bounding_rect
small_box(R) <- (
    bounding_rect(_, R),
    R is rect(_, _, W, H),
    W < 20,
    H < 20
)

# Decompose a keypoint into its fields
strong_keypoints(KP_LIST, STRONG) <- (
    findall(KP, (
        member(KP, KP_LIST),
        keypoint_decompose(KP, _, _, _, RESP, _, _),
        RESP > 0.1
    ), STRONG)
)
```

---

## Step 7 — Predicate Catalogue

Grouped by phase. Modes: `+` input, `-` output. Purity is `pure`
unless noted.

### Phase 1 — Core, I/O, Properties, Arithmetic

| Name | Arity | Modes | Tier | Bijective? | Nondet? | Description |
|---|---|---|---|---|---|---|
| `imread` | `/2, /3` | `(+path, -img)`, `(+path, +flag, -img)` | 4 | no | no | Read image from file |
| `imwrite` | `/2, /3` | `(+path, +img)`, `(+path, +img, +params)` | 4 | no | no | Write image to file |
| `image_encoded` | `/3` | `(+img, +ext, -buf)` / `(-img, +ext, +buf)` | 1 | yes | no | Encode ↔ decode in-memory |
| `shape` | `/2` | `(+img, -shape)` query, `(+img, +shape)` check | 1 | partial | no | Image shape |
| `dtype` | `/2` | `(+img, -d)` query, `(+img, +d)` check | 1 | partial | no | Image dtype |
| `channels_count` | `/2` | `(+img, -n)`, `(+img, +n)` check | 1 | partial | no | Number of channels (1 for 2-D image) |
| `size` | `/2` | `(+img, -[w, h])`, `(+img, +[w, h])` check | 1 | partial | no | `(width, height)` — note: OpenCV convention is `(W, H)`, NumPy is `(H, W)` |
| `element_count` | `/2` | `(+img, -n)` | 1 | no | no | Total elements (`img.size`) |
| `is_grayscale` | `/1` | `(+img)` check | 1 | n/a | no | Single-channel check |
| `is_color` | `/1` | `(+img)` check | 1 | n/a | no | 3-channel check |
| `is_uint8` | `/1` | `(+img)` check | 1 | n/a | no | dtype check |
| `add` | `/3` | `(+a, +b, -c)` | 1 | no | no | Saturated add |
| `subtract` | `/3` | `(+a, +b, -c)` | 1 | no | no | Saturated subtract |
| `multiply` | `/3, /4` | `(+a, +b, -c)`, `(+a, +b, +scale, -c)` | 1 | no | no | Element-wise multiply |
| `divide` | `/3, /4` | `(+a, +b, -c)`, `(+a, +b, +scale, -c)` | 1 | no | no | Element-wise divide |
| `absdiff` | `/3` | `(+a, +b, -c)` | 1 | no | no | `|a - b|` |
| `bitwise_and` | `/3, /4` | `(+a, +b, -c)`, `(+a, +b, +mask, -c)` | 1 | no | no | |
| `bitwise_or` | `/3, /4` | `(+a, +b, -c)`, `(+a, +b, +mask, -c)` | 1 | no | no | |
| `bitwise_xor` | `/3, /4` | `(+a, +b, -c)`, `(+a, +b, +mask, -c)` | 1 | no | no | |
| `bitwise_not` | `/2, /3` | `(+a, -c)`, `(+a, +mask, -c)` | 1 | no | no | |
| `min` | `/3` | `(+a, +b, -c)` | 1 | no | no | Element-wise min |
| `max` | `/3` | `(+a, +b, -c)` | 1 | no | no | Element-wise max |
| `mean` | `/2, /3` | `(+img, -m)`, `(+img, +mask, -m)` | 1 | no | no | Channel-wise mean as 4-tuple |
| `min_max_loc` | `/2, /3` | `(+img, -result)`, `(+img, +mask, -result)` | 1 | no | no | Returns `min_max(...)` term |
| `flip` | `/3` | `(+img, +code, -out)` | 1 | self-inverse at code | no | code: 0/1/-1 |
| `transpose` | `/2` | `(+img, -out)` | 1 | self-inverse | no | |
| `copy_image` | `/2` | `(+img, -copy)` | 1 | no | no | `img.copy()` |

### Phase 2 — Color Conversions

| Name | Arity | Modes | Tier | Bijective? | Nondet? | Description |
|---|---|---|---|---|---|---|
| `cvt_color` | `/3` | `(+img, +code, -out)` | 1 | partial — inverse via inverse-code | no | `cv2.cvtColor(img, code)` |
| `cvt_color_named` | `/3` | `(+img, +name, -out)` | 1 | partial — inverse via inverse-name | no | `cvtColor` keyed by string (e.g. `"BGR2GRAY"`) |
| `color_code` | `/2` | `(+name, -code)`, `(-name, +code)`, `(-name, -code)` | 2 | yes | yes (enum) | Name ↔ integer code registry |
| `channels` | `/2` | `(+img, -list)` / `(-img, +list)` | 1 | yes | no | `split(img)` ↔ `merge(channels)` |

### Phase 3 — Filtering and Morphology

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `gaussian_blur` | `/3, /4` | `(+img, +ksize, -out)`, `(+img, +ksize, +sigma, -out)` | 1 | `cv2.GaussianBlur` |
| `median_blur` | `/3` | `(+img, +ksize, -out)` | 1 | `cv2.medianBlur` |
| `box_filter` | `/4` | `(+img, +ddepth, +ksize, -out)` | 1 | `cv2.boxFilter` |
| `bilateral_filter` | `/5` | `(+img, +d, +sigma_color, +sigma_space, -out)` | 1 | `cv2.bilateralFilter` |
| `filter_2d` | `/4` | `(+img, +ddepth, +kernel, -out)` | 1 | `cv2.filter2D` |
| `sep_filter_2d` | `/5` | `(+img, +ddepth, +kx, +ky, -out)` | 1 | `cv2.sepFilter2D` |
| `sobel` | `/5, /6` | `(+img, +ddepth, +dx, +dy, -out)`, `(+img, +ddepth, +dx, +dy, +ksize, -out)` | 1 | `cv2.Sobel` |
| `scharr` | `/5` | `(+img, +ddepth, +dx, +dy, -out)` | 1 | `cv2.Scharr` |
| `laplacian` | `/3, /4` | `(+img, +ddepth, -out)`, `(+img, +ddepth, +ksize, -out)` | 1 | `cv2.Laplacian` |
| `canny` | `/4, /5` | `(+img, +t1, +t2, -out)`, `(+img, +t1, +t2, +apertureSize, -out)` | 1 | `cv2.Canny` |
| `get_structuring_element` | `/3, /4` | `(+shape, +ksize, -kernel)`, `(+shape, +ksize, +anchor, -kernel)` | 1 | |
| `erode` | `/3, /4` | `(+img, +kernel, -out)`, `(+img, +kernel, +iterations, -out)` | 1 | |
| `dilate` | `/3, /4` | `(+img, +kernel, -out)`, `(+img, +kernel, +iterations, -out)` | 1 | |
| `morphology_ex` | `/4, /5` | `(+img, +op, +kernel, -out)`, `(+img, +op, +kernel, +iterations, -out)` | 1 | `cv2.morphologyEx` |
| `pyr_down` | `/2, /3` | `(+img, -out)`, `(+img, +dstsize, -out)` | 1 | |
| `pyr_up` | `/2, /3` | `(+img, -out)`, `(+img, +dstsize, -out)` | 1 | |
| `interpolation` | `/2` | `(+name, -code)` / inverse / `(-,-)` enum | 2 | Registry |
| `border_type` | `/2` | same modes | 2 | Registry |
| `morph_op` | `/2` | same modes | 2 | Registry |
| `morph_shape` | `/2` | same modes | 2 | Registry |

### Phase 4 — Thresholding and Contours

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `threshold` | `/6` | `(+img, +thresh, +maxval, +type, -used_thresh, -out)` | 1 | Tuple-style: `used_thresh` is the level returned by Otsu/Triangle, or `thresh` otherwise |
| `adaptive_threshold` | `/7` | `(+img, +maxval, +adaptive_method, +threshold_type, +block_size, +c, -out)` | 1 | |
| `find_contours` | `/4, /5` | `(+img, +mode, +method, -contours, -hierarchy)`, `(+img, +mode, +method, +offset, -contours, -hierarchy)` | 1 | Always returns the contour list and hierarchy together |
| `contour` | `/2` | `(+contours, -c)` | 1 | Nondeterministic enumeration of individual contours |
| `contour_area` | `/2, /3` | `(+contour, -a)`, `(+contour, +oriented, -a)` | 1 | |
| `contour_perimeter` | `/3` | `(+contour, +closed, -p)` | 1 | `cv2.arcLength` |
| `moments` | `/2` | `(+contour_or_img, -moments)` | 1 | Returns `moments_t(...)` term |
| `moments_field` | `/3` | `(+moments, +name, -value)` | 1 | Field lookup by name (`"m00"`, `"mu20"`, etc.) |
| `convex_hull` | `/2, /3` | `(+points, -hull)`, `(+points, +clockwise, -hull)` | 1 | |
| `bounding_rect` | `/2` | `(+points, -rect)` | 1 | Returns `rect(X, Y, W, H)` term |
| `min_enclosing_circle` | `/3` | `(+points, -center, -radius)` | 1 | |
| `min_area_rect` | `/2` | `(+points, -rotated_rect)` | 1 | Returns `rotated_rect(CENTER, SIZE, ANGLE)` |
| `approx_poly_dp` | `/4` | `(+contour, +epsilon, +closed, -out)` | 1 | |
| `point_polygon_test` | `/4` | `(+contour, +pt, +measure_dist, -result)` | 1 | |
| `threshold_type` | `/2` | registry modes | 2 | |

### Phase 5 — Geometric Transformations

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `resize` | `/3, /4` | `(+img, +dsize, -out)`, `(+img, +dsize, +interpolation, -out)` | 1 | no | |
| `warp_affine` | `/4, /5` | `(+img, +M, +dsize, -out)`, `(+img, +M, +dsize, +flags, -out)` | 1 | no | |
| `warp_perspective` | `/4, /5` | `(+img, +M, +dsize, -out)`, `(+img, +M, +dsize, +flags, -out)` | 1 | no | |
| `rotate` | `/3` | `(+img, +rotate_code, -out)` | 1 | partial — inverse code exists | |
| `get_rotation_matrix_2d` | `/4` | `(+center, +angle, +scale, -M)` | 1 | no | |
| `get_affine_transform` | `/3` | `(+src, +dst, -M)` | 1 | no | |
| `get_perspective_transform` | `/3` | `(+src, +dst, -M)` | 1 | no | |
| `affine_inverse` | `/2` | `(+M, -M_inv)` / `(-M, +M_inv)` | 1 | yes — self-inverse | `cv2.invertAffineTransform` |
| `remap` | `/5, /6` | `(+img, +map1, +map2, +interpolation, -out)`, +border_mode | 1 | no | |
| `copy_make_border` | `/7` | `(+img, +top, +bot, +left, +right, +border_type, -out)` | 1 | no | |

### Phase 6 — Drawing (non-mutating)

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `line` | `/5, /6, /7` | `(+img, +p1, +p2, +color, -out)`, `+thickness`, `+line_type` | 1 | Copy-on-write |
| `arrowed_line` | `/5, /6, /7` | same shape | 1 | |
| `rectangle` | `/5, /6, /7` | `(+img, +p1, +p2, +color, -out)`, `+thickness`, `+line_type` | 1 | |
| `circle` | `/5, /6, /7` | `(+img, +center, +radius, +color, -out)`, `+thickness`, `+line_type` | 1 | |
| `ellipse` | `/8` | `(+img, +center, +axes, +angle, +start_angle, +end_angle, +color, -out)` | 1 | |
| `polylines` | `/5, /6` | `(+img, +pts_list, +is_closed, +color, -out)`, `+thickness` | 1 | |
| `fill_poly` | `/4` | `(+img, +pts_list, +color, -out)` | 1 | |
| `put_text` | `/8` | `(+img, +text, +origin, +font, +scale, +color, +thickness, -out)` | 1 | |
| `marker` | `/5, /6, /7, /8` | `(+img, +position, +color, -out)`, `+marker_type`, `+marker_size`, `+thickness` | 1 | |
| `draw_contours` | `/5, /6` | `(+img, +contours, +contour_idx, +color, -out)`, `+thickness` | 1 | |
| `draw_keypoints` | `/4, /5` | `(+img, +keypoints, +color, -out)`, `+flags` | 1 | |
| `draw_matches` | `/7` | `(+img1, +kp1, +img2, +kp2, +matches, +flags, -out)` | 1 | |

### Phase 7 — Features and Matching

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `make_orb` | `/1, /2` | `(-handle)`, `(+opts, -handle)` | 3 | opts dict: `n_features`, `scale_factor`, `n_levels`, ... |
| `make_sift` | `/1, /2` | same shape | 3 | |
| `make_akaze` | `/1, /2` | same shape | 3 | |
| `make_kaze` | `/1, /2` | same shape | 3 | |
| `make_brisk` | `/1, /2` | same shape | 3 | |
| `make_fast` | `/1, /2` | same shape | 3 | |
| `detect` | `/3, /4` | `(+detector_handle, +img, -keypoints)`, `(+,+,+mask,-)` | 3 | |
| `compute` | `/4` | `(+detector_handle, +img, +keypoints, -descriptors)` | 3 | |
| `detect_and_compute` | `/4, /5` | `(+handle, +img, -kps, -descs)`, `(+,+,+mask,-,-)` | 3 | |
| `make_bf_matcher` | `/1, /2, /3` | `(-handle)`, `(+norm_type, -handle)`, `(+norm_type, +cross_check, -handle)` | 3 | |
| `make_flann_matcher` | `/1, /3` | `(-handle)`, `(+index_params, +search_params, -handle)` | 3 | |
| `match` | `/4` | `(+matcher, +query_desc, +train_desc, -matches)` | 3 | |
| `knn_match` | `/5` | `(+matcher, +query_desc, +train_desc, +k, -matches)` | 3 | |
| `radius_match` | `/5` | `(+matcher, +query_desc, +train_desc, +radius, -matches)` | 3 | |
| `keypoint` | `/2` | `(+keypoint_list, -kp)` | 1 | Nondet enumeration |
| `keypoint_decompose` | `/7` | `(+kp, -pt, -size, -angle, -response, -octave, -class_id)` | 1 | |
| `keypoint_make` | `/7` | `(-kp, +pt, +size, +angle, +response, +octave, +class_id)` | 1 | Inverse of `keypoint_decompose`; combined into a bidirectional `keypoint/7` predicate in the phase file |
| `match_pair` | `/2` | `(+match_list, -m)` | 1 | Nondet enumeration |
| `dmatch_decompose` | `/5` | `(+m, -query_idx, -train_idx, -img_idx, -distance)` | 1 | |
| `free` | `/1` | `(+handle)` | 3 | Release any Phase-7/8/9/10 handle |

### Phase 8 — Object Detection

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `make_cascade_classifier` | `/2` | `(+xml_path, -handle)` | 3 | |
| `detect_multi_scale` | `/3, /4, /5` | `(+handle, +img, -rects)`, `(+,+,+scale_factor,-)`, `(+,+,+scale_factor,+min_neighbors,-)` | 3 | |
| `make_hog` | `/1, /2` | `(-handle)`, `(+opts, -handle)` | 3 | |
| `hog_compute` | `/3` | `(+handle, +img, -descriptors)` | 3 | |
| `hog_detect` | `/3, /4` | `(+handle, +img, -found)`, `(+handle, +img, +opts, -found)` | 3 | |
| `hog_set_svm_detector` | `/3` | `(+handle0, +svm, -handle1)` | 3 | State-threaded: returns a new handle |
| `hog_default_people_detector` | `/1` | `(-svm)` | 1 | |

### Phase 9 — Camera Calibration and Homography

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `find_homography` | `/3, /4, /5` | `(+src, +dst, -H)`, `(+,+,+method,-)`, `(+,+,+method,+ransac_thresh,-H)` | 1 | no | also returns mask in arity-4/5 |
| `find_homography_mask` | `/4, /5` | `(+src, +dst, +method, -H, -mask)`, with `+ransac_thresh` | 1 | no | |
| `find_fundamental_mat` | `/3, /4` | `(+pts1, +pts2, -F)`, `(+,+,+opts,-)` | 1 | no | |
| `find_essential_mat` | `/4, /5` | `(+pts1, +pts2, +camera_matrix, -E)`, `(+,+,+,+opts,-)` | 1 | no | |
| `solve_pnp` | `/4, /5` | `(+object_pts, +image_pts, +camera_matrix, +dist_coeffs, -rvec, -tvec)` | 1 | no | tuple-style |
| `solve_pnp_ransac` | `/5` | `(+object_pts, +image_pts, +camera_matrix, +dist_coeffs, -result)` | 1 | no | result: `pnp_ransac(rvec, tvec, inliers)` |
| `calibrate_camera` | `/4, /5` | `(+object_pts, +image_pts, +image_size, -result)`, `(+,+,+,+opts,-)` | 1 | no | result: `calib(rms, K, dist, rvecs, tvecs)` |
| `project_points` | `/5` | `(+object_pts, +rvec, +tvec, +camera_matrix, +dist_coeffs, -image_pts, -jacobian)` | 1 | no | |
| `undistort` | `/4, /5` | `(+img, +camera_matrix, +dist_coeffs, -out)`, `(+,+,+,+new_camera_matrix,-)` | 1 | no | |
| `init_undistort_rectify_map` | `/7` | `(+camera_matrix, +dist_coeffs, +R, +new_camera_matrix, +image_size, +m1type, -map1, -map2)` | 1 | no | |
| `rodrigues` | `/2` | `(+rvec, -rmat)` / `(-rvec, +rmat)` | 1 | yes | `cv2.Rodrigues` |
| `decompose_homography_mat` | `/3` | `(+H, +K, -solutions)` | 1 | no | |
| `recover_pose` | `/4` | `(+E, +pts1, +pts2, +K, -result)` | 1 | no | result: `pose(R, t, mask, n_inliers)` |
| `dft` | `/2` | `(+img, -spec)` / `(-img, +spec)` | 1 | yes | Forward / inverse DFT (also useful here as a math tool) |

### Phase 10 — Video I/O

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `make_video_capture` | `/2` | `(+source, -handle)` | 4 | `source` is a file path or device index |
| `is_open` | `/1` | `(+handle)` check | 4 | `cv2.VideoCapture.isOpened()` |
| `video_property` | `/3` | `(+handle, +name, -value)` | 4 | Wraps `get(cv2.CAP_PROP_*)`; name registry built-in |
| `video_property_set` | `/4` | `(+handle0, +name, +value, -handle1)` | 4 | State-threaded |
| `read_frame` | `/2` | `(+handle, -frame)` | 4 | One-shot |
| `video_frame` | `/3` | `(+handle, -index, -frame)` | 4 | Nondeterministic — yields frames until end-of-stream. **Not safe to backtrack across.** Documented in phase file. |
| `make_video_writer` | `/5, /6` | `(+path, +fourcc_code, +fps, +size, -handle)`, `(+,+,+,+,+is_color,-)` | 4 | |
| `write_frame` | `/2` | `(+handle, +frame)` | 4 | |
| `release` | `/1` | `(+handle)` | 4 | Close capture / writer |
| `fourcc` | `/2` | `(+chars, -code)` / `(-chars, +code)` | 1 | Bijective 4-char ↔ int |
| `video_prop_name` | `/2` | `(+name, -prop_code)` / inverse / enum | 2 | Registry of `cv2.CAP_PROP_*` names |

---

## Step 8 — Submodule Breakdown

See [Package layout](#package-layout) above. Cross-module dependencies:

- All files import `_cv()` from `clausal.modules.opencv` (the Phase 1
  entry) to share the same lazy `cv2` import.
- `opencv_features.py`, `opencv_objdetect.py`, `opencv_video.py` import
  `_alloc_handle` / `_lookup_handle` / `_free_handle` from
  `clausal.modules._opencv_handles` for the shared handle registry,
  modelled directly on `scipy_spatial.py`'s registry pattern.
- All Tier 1 predicates use the shared `_pred`, `_pure`, `_property_2`,
  `_bidir_2`, `_bidir_3_mid`, `_check_1`, `_fact_table_2` helpers from
  `clausal.modules.py._helpers` (already used by torch/scipy).
- `opencv_color.py` and `opencv_imgproc.py` share the constant /
  registry export pattern but are split because color conversion is
  large and self-contained.

---

## Step 9 — Showcase Example

Image-stitching pipeline using features + homography + warping. **No
`++()` escapes**.

```clausal
-import_from(py.opencv, [
    imread, cvt_color, shape, size, copy_make_border, COLOR_BGR2GRAY,
    BORDER_CONSTANT, IMREAD_COLOR
])
-import_from(py.opencv_features, [
    make_orb, detect_and_compute, make_bf_matcher, knn_match,
    keypoint_decompose, dmatch_decompose, match_pair
])
-import_from(py.opencv_calib3d, [
    find_homography_mask
])
-import_from(py.opencv_imgproc, [
    warp_perspective
])
-import_from(py.opencv, [NORM_HAMMING])

# Ratio-test filter for KNN matches: keep first if dist0 < 0.75 * dist1.
good_match(MATCH_PAIR, GOOD) <- (
    MATCH_PAIR is [M1, M2],
    dmatch_decompose(M1, _, _, _, D1),
    dmatch_decompose(M2, _, _, _, D2),
    D1 < 0.75 * D2,
    GOOD = M1
)

# Build a homography from image A onto image B's plane.
stitch(IMG_A_PATH, IMG_B_PATH, RESULT) <- (
    imread(IMG_A_PATH, IMREAD_COLOR, IMG_A),
    imread(IMG_B_PATH, IMREAD_COLOR, IMG_B),
    cvt_color(IMG_A, COLOR_BGR2GRAY, GRAY_A),
    cvt_color(IMG_B, COLOR_BGR2GRAY, GRAY_B),

    make_orb({n_features: 5000}, ORB),
    detect_and_compute(ORB, GRAY_A, KP_A, DESC_A),
    detect_and_compute(ORB, GRAY_B, KP_B, DESC_B),

    make_bf_matcher(NORM_HAMMING, BF),
    knn_match(BF, DESC_A, DESC_B, 2, KNN_MATCHES),

    findall(GOOD, (
        member(PAIR, KNN_MATCHES),
        good_match(PAIR, GOOD)
    ), GOOD_MATCHES),

    # Build source / destination point arrays for findHomography
    findall(P, (
        match_pair(GOOD_MATCHES, M),
        dmatch_decompose(M, QIDX, _, _, _),
        nth0(QIDX, KP_A, KP),
        keypoint_decompose(KP, P, _, _, _, _, _)
    ), SRC_PTS),
    findall(P, (
        match_pair(GOOD_MATCHES, M),
        dmatch_decompose(M, _, TIDX, _, _),
        nth0(TIDX, KP_B, KP),
        keypoint_decompose(KP, P, _, _, _, _, _)
    ), DST_PTS),

    find_homography_mask(SRC_PTS, DST_PTS, 4, H, _MASK),

    size(IMG_B, [W, H_PX]),
    warp_perspective(IMG_A, H, [W, H_PX], RESULT)
)

# Find all images that match a query strongly enough.
Test("at least one good match for a self-stitch") <- (
    stitch("fixtures/scene.png", "fixtures/scene.png", RESULT),
    shape(RESULT, [_, _, 3])
)
```

This example uses:

- Multi-mode property predicates (`shape/2`, `size/2` in query mode).
- Nondeterministic enumeration (`member`, `match_pair`).
- Tagged-term decomposition (`dmatch_decompose`, `keypoint_decompose`).
- Constants imported by name (`COLOR_BGR2GRAY`, `NORM_HAMMING`,
  `IMREAD_COLOR`).
- A multi-step Tier-3 handle pipeline (ORB + BFMatcher).
- A pure Tier-1 chain (cvtColor → warpPerspective).

If any of these read awkwardly when Phase 7/9 is implemented, the
relevant phase plan needs revision before that phase ships.

---

## Step 10 — Phasing

Phase dependencies:

```
Phase 1 (core/IO)
   ↓
   ├─ Phase 2 (color)
   ├─ Phase 3 (filtering)
   │     ↓
   │     Phase 4 (thresholding/contours)
   ├─ Phase 5 (geometric)
   │     ↓
   │     Phase 6 (drawing)            (drawing depends on geometric for sanity-only;
   │                                    can ship Phase 6 right after Phase 1 if needed)
   ├─ Phase 7 (features)
   │     ↓
   │     Phase 8 (object detection)
   │     Phase 9 (calibration)
   └─ Phase 10 (video)                 (can ship any time after Phase 1)
```

Each phase is independently mergeable. Each phase file is
self-contained — phase 7 must reference phase 1's `_cv()` / handle
registry / constant export pattern by file and function, so an agent
opening the phase file without the overview can still complete it.

### Commit cadence

- One commit per phase as the unit of completeness.
- Within a phase, commit on natural sub-boundaries (e.g. "Phase 3:
  filters", "Phase 3: morphology", "Phase 3: docs + tests").
- Update the phase's Issues section and the overview's Implemented /
  Planned list before each commit.

---

## Design Notes (a priori)

Observations from the design pass, before any implementation:

1. **BGR vs RGB.** OpenCV reads images as BGR by default. This is the
   single most common source of confusion for OpenCV users. The wrapper
   does **not** silently convert to RGB — it preserves the library's
   convention. Users coming from matplotlib (which expects RGB) must
   either call `cvt_color(IMG, COLOR_BGR2RGB, RGB_IMG)` or use
   `imread(..., IMREAD_UNCHANGED)`. This is documented prominently in
   `opencv.md`.

2. **Shape conventions.** Image shapes are `(H, W)` or `(H, W, C)`,
   but `size` is `(W, H)` and points are `(X, Y)`. This is OpenCV's
   convention, not the wrapper's choice; the wrapper preserves it.
   `shape/2` returns the numpy shape `(H, W, C)`; `size/2` returns
   the OpenCV size `(W, H)`. Both are predicates so both modes are
   available without `++()`.

3. **`dst=` argument is omitted everywhere.** OpenCV functions accept
   an optional `dst=` array that they write into; the wrapper never
   passes it. This guarantees the C-level call cannot mutate a
   previously-bound term.

4. **`channels/2` collapses `cv2.split` / `cv2.merge`.** A single
   bidirectional predicate replaces the two procedural calls — see
   Phase 2.

5. **`threshold/6` returns the used threshold.** `cv2.threshold` with
   `THRESH_OTSU` or `THRESH_TRIANGLE` returns the computed level as
   the function's first return value. Rather than splitting Otsu /
   Triangle into separate predicates, the wrapper exposes the used
   level as an output argument. Users who don't care can use `_`.

6. **Contours come with hierarchy.** `cv2.findContours` returns both
   the contour list and a hierarchy array. The wrapper always returns
   both — splitting them into separate predicates would force two
   calls. Users who don't need hierarchy use `_`.

7. **KeyPoint and DMatch as native + tagged.** `cv2.KeyPoint` and
   `cv2.DMatch` are Python objects with `.attr` access. The wrapper
   uses them directly as terms (passing through detector/matcher
   results) and provides `keypoint_decompose/7` and
   `dmatch_decompose/5` for clause-head matching. This is the same
   "native + decompose" pattern as PyTorch's tensors plus
   `tensor_list`.

8. **Drawing copy-on-write.** Each drawing predicate calls
   `img.copy()` before invoking the C-level draw call. The cost is
   one ndarray copy per call (typically dominated by the draw itself
   for any non-trivial canvas) and bought correctness under
   backtracking. Documented in `opencv_draw.md`.

9. **Video iteration commits.** `read_frame/2` and `video_frame/3`
   advance the capture cursor. Backtracking does **not** rewind —
   the capture is a true IO resource. Phase 10 documents this and
   recommends `video_property_set(CAP, "pos_frames", N, CAP1)` for
   seekable files.

10. **`make_orb` etc. take an opts dict, not positional args.**
    Detectors have many parameters (`nfeatures`, `scaleFactor`,
    `nlevels`, `edgeThreshold`, `firstLevel`, `WTA_K`, `scoreType`,
    `patchSize`, `fastThreshold` for ORB alone). A positional-args
    constructor would be unwieldy; an opts dict mirrors the kwargs
    interface most users already know. This matches the `zeros/3`
    opts pattern in torch.

11. **No `++()` in tests.** Tests use exported constants and
    predicates only. The handful of test fixtures (small PNG / JPG
    files) are committed as binary blobs to
    `packages/clausal-opencv/tests/fixtures/`.

12. **`numpy` is a soft dependency.** `cv2` already depends on numpy,
    so adding `numpy` to `clausal-opencv`'s `dependencies` is
    redundant but harmless. The wrapper also re-exports a few numpy
    dtype constants (`uint8`, `float32`) for ergonomics, mirroring
    the torch dtype exports.

---

## Issues

_To be populated during implementation. Items found while writing the
overview that haven't been resolved here are filed against the
relevant phase file's Issues section, not here._
