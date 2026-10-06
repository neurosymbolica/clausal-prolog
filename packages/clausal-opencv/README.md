# clausal-opencv

OpenCV (`cv2`) predicates for [Clausal Prolog](https://gitlab.com/MikeAmy/clausal).

Wraps the computer-vision functions of `opencv-python` as Clausal Prolog
predicates: image I/O, properties, arithmetic, color conversion,
filtering, morphology, thresholding, contours, geometric
transformations, non-mutating drawing, classical feature detection,
classical object detection, camera calibration, and video I/O.

## Install

```
pip install clausal-opencv
```

`opencv-python` is pulled in as a dependency. For headless
environments, install `opencv-python-headless` first to override the
default.

## Use

In a seam (`.seam`) file:

```
-import_from(opencv, [imread, shape, IMREAD_COLOR])

test("read an image and query its shape") <- (
    imread("photo.jpg", IMREAD_COLOR, IMG),
    shape(IMG, [H, W, 3]),
    H > 0,
    W > 0
)
```

See `docs/` for the predicate catalogue and worked examples.

## Implementation status

See `../../implementation_plans/opencv/overview.md`.

- [x] Phase 1 — Core, I/O, Properties, Arithmetic
- [x] Phase 2 — Color Conversions
- [x] Phase 3 — Filtering and Morphology
- [x] Phase 4 — Thresholding and Contours
- [x] Phase 5 — Geometric Transformations
- [x] Phase 6 — Drawing (non-mutating)
- [x] Phase 7 — Features and Matching
- [x] Phase 8 — Object Detection
- [x] Phase 9 — Camera Calibration and Homography
- [x] Phase 10 — Video I/O
