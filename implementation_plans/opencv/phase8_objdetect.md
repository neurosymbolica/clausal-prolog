# Phase 8 — Object Detection (Cascade, HOG)

Pre-deep-learning object detectors: Haar/LBP cascade classifiers and
HOG descriptors. Handle-based (Tier 3).

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_objdetect.py` (new)
- `packages/clausal-opencv/tests/clausal_files/opencv_phase8_objdetect.clausal`
- `packages/clausal-opencv/docs/opencv_objdetect.md`
- A built-in cascade XML (`haarcascade_frontalface_default.xml`) is
  shipped with `opencv-python` itself — accessed via
  `cv2.data.haarcascades + "haarcascade_frontalface_default.xml"`.
  Tests use this rather than committing an XML to fixtures.

---

## Predicates

### Cascade classifier

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `make_cascade_classifier` | `/2` | `(+xml_path, -handle)` | 3 | Load Haar/LBP cascade from XML |
| `detect_multi_scale` | `/3` | `(+handle, +img, -rects)` | 3 | rects: list of `rect(X,Y,W,H)` |
| `detect_multi_scale` | `/4` | `(+handle, +img, +scale_factor, -rects)` | 3 | |
| `detect_multi_scale` | `/5` | `(+handle, +img, +scale_factor, +min_neighbors, -rects)` | 3 | |
| `detect_multi_scale` | `/6` | `(+handle, +img, +scale_factor, +min_neighbors, +min_size, -rects)` | 3 | |
| `haar_cascade_path` | `/2` | `(+name, -path)` | 2 | Registry of bundled Haar cascade names: `face`, `eye`, `smile`, `body`, etc. |

### HOG descriptor

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `make_hog` | `/1` | `(-handle)` | 3 | Default args |
| `make_hog` | `/2` | `(+opts, -handle)` | 3 | Opts: `win_size`, `block_size`, `block_stride`, `cell_size`, `nbins` |
| `hog_compute` | `/3` | `(+handle, +img, -descriptors)` | 3 | |
| `hog_detect` | `/3` | `(+handle, +img, -found)` | 3 | found: list of `rect(X,Y,W,H)` |
| `hog_detect` | `/4` | `(+handle, +img, +opts, -found)` | 3 | Opts dict |
| `hog_set_svm_detector` | `/3` | `(+handle0, +svm, -handle1)` | 3 | **State-threaded** — returns a new handle |
| `hog_default_people_detector` | `/1` | `(-svm)` | 1 | Built-in people SVM vector (a numpy array) |

`hog_set_svm_detector/3` follows the state-threading pattern from
[Step 3.2 of the checklist](../EXTERNAL_WRAPPER_CHECKLIST.md#32-stateful-operations-need-explicit-state-threading):
the input handle is unchanged, and a new handle to a copy of the HOG
descriptor with the SVM installed is returned. Backtracking past this
call abandons the new handle; the original remains valid.

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_objdetect.py
import os
import copy as _copy

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _fact_table_2, _deep_deref
from clausal.modules.opencv import _cv
from clausal.modules._opencv_handles import alloc, lookup
```

### `make_cascade_classifier/2`

```python
def _make_cascade(xml_path):
    cv = _cv()
    cascade = cv.CascadeClassifier(str(xml_path))
    if cascade.empty():
        raise RuntimeError(f"Failed to load cascade: {xml_path!r}")
    return alloc(cascade)

make_cascade_classifier = _pred("make_cascade_classifier",
    (2, _pure(_make_cascade)),
)
```

### `detect_multi_scale/3-6`

`cv2.CascadeClassifier.detectMultiScale` returns a numpy `(N, 4)` array
or a tuple. The wrapper converts each row to a tagged `rect`:

```python
def _detect_multi_scale(handle, img, **kwargs):
    cascade = lookup(handle)
    result = cascade.detectMultiScale(img, **kwargs)
    # detectMultiScale returns () when nothing found, or ndarray Nx4
    rects = []
    for row in result:
        x, y, w, h = (int(v) for v in row)
        rects.append(("rect", x, y, w, h))
    return rects

detect_multi_scale = _pred("detect_multi_scale",
    (3, _pure(lambda h, img: _detect_multi_scale(h, img))),
    (4, _pure(lambda h, img, sf:
              _detect_multi_scale(h, img, scaleFactor=float(sf)))),
    (5, _pure(lambda h, img, sf, mn:
              _detect_multi_scale(h, img,
                                    scaleFactor=float(sf),
                                    minNeighbors=int(mn)))),
    (6, _pure(lambda h, img, sf, mn, msize:
              _detect_multi_scale(h, img,
                                    scaleFactor=float(sf),
                                    minNeighbors=int(mn),
                                    minSize=tuple(msize)))),
)
```

The `rect` term constructor matches Phase 4's `bounding_rect/2` —
decompose with `R is ("rect", X, Y, W, H)`.

### `haar_cascade_path/2`

`opencv-python` ships a directory of XML files at `cv2.data.haarcascades`.
The wrapper exposes the most-used cascades by short name:

```python
def _haar_facts():
    base = _cv().data.haarcascades
    files = [
        ("face",         "haarcascade_frontalface_default.xml"),
        ("face_alt",     "haarcascade_frontalface_alt.xml"),
        ("face_alt2",    "haarcascade_frontalface_alt2.xml"),
        ("profile_face", "haarcascade_profileface.xml"),
        ("eye",          "haarcascade_eye.xml"),
        ("smile",        "haarcascade_smile.xml"),
        ("body",         "haarcascade_fullbody.xml"),
        ("upper_body",   "haarcascade_upperbody.xml"),
        ("lower_body",   "haarcascade_lowerbody.xml"),
        ("license_plate", "haarcascade_russian_plate_number.xml"),
    ]
    return [(name, os.path.join(base, fname)) for name, fname in files]

haar_cascade_path = _pred("haar_cascade_path",
    (2, _fact_table_2(_haar_facts)),
)
```

This is a pattern-(2) registry per [Step 5d](../EXTERNAL_WRAPPER_CHECKLIST.md#step-5d--when-to-add-a-registry):
name-as-data lookup. Users read `"face"` from a config and resolve the
path via the registry.

### `make_hog/1,2`

```python
def _make_hog_default():
    return alloc(_cv().HOGDescriptor())

def _make_hog_opts(opts):
    cv = _cv()
    mapping = {
        "win_size":     ("_winSize",     lambda v: tuple(v)),
        "block_size":   ("_blockSize",   lambda v: tuple(v)),
        "block_stride": ("_blockStride", lambda v: tuple(v)),
        "cell_size":    ("_cellSize",    lambda v: tuple(v)),
        "nbins":        ("_nbins",       int),
    }
    # cv2.HOGDescriptor accepts positional args (winSize, blockSize,
    # blockStride, cellSize, nbins); we keep the opts-dict interface
    # by passing positional args in order with defaults filled in.
    win   = tuple(opts.get("win_size", (64, 128)))
    block = tuple(opts.get("block_size", (16, 16)))
    stride = tuple(opts.get("block_stride", (8, 8)))
    cell  = tuple(opts.get("cell_size", (8, 8)))
    nbins = int(opts.get("nbins", 9))
    return alloc(cv.HOGDescriptor(win, block, stride, cell, nbins))

make_hog = _pred("make_hog",
    (1, _pure(_make_hog_default)),
    (2, _pure(_make_hog_opts)),
)
```

### `hog_compute/3`, `hog_detect/3,4`

```python
def _hog_compute(handle, img):
    hog = lookup(handle)
    return hog.compute(img)

def _hog_detect(handle, img):
    hog = lookup(handle)
    rects, _weights = hog.detectMultiScale(img)
    return [("rect", int(x), int(y), int(w), int(h)) for x, y, w, h in rects]

def _hog_detect_opts(handle, img, opts):
    hog = lookup(handle)
    kwargs = {}
    if "win_stride" in opts: kwargs["winStride"] = tuple(opts["win_stride"])
    if "padding"    in opts: kwargs["padding"]   = tuple(opts["padding"])
    if "scale"      in opts: kwargs["scale"]     = float(opts["scale"])
    rects, _weights = hog.detectMultiScale(img, **kwargs)
    return [("rect", int(x), int(y), int(w), int(h)) for x, y, w, h in rects]

hog_compute = _pred("hog_compute",
    (3, _pure(_hog_compute)),
)

hog_detect = _pred("hog_detect",
    (3, _pure(_hog_detect)),
    (4, _pure(_hog_detect_opts)),
)
```

### `hog_set_svm_detector/3` — state-threaded

```python
def _hog_set_svm(handle0, svm):
    hog = lookup(handle0)
    # Copy the HOGDescriptor — cv2 supports __copy__ via constructor.
    new_hog = _cv().HOGDescriptor(
        hog.winSize, hog.blockSize, hog.blockStride,
        hog.cellSize, hog.nbins,
    )
    new_hog.setSVMDetector(svm)
    return alloc(new_hog)

hog_set_svm_detector = _pred("hog_set_svm_detector",
    (3, _pure(_hog_set_svm)),
)
```

The original handle (`handle0`) remains valid — its descriptor was
copied, not mutated. The returned `handle1` is the new descriptor
with the SVM installed.

### `hog_default_people_detector/1`

```python
def _default_people_svm():
    return _cv().HOGDescriptor_getDefaultPeopleDetector()

hog_default_people_detector = _pred("hog_default_people_detector",
    (1, _pure(_default_people_svm)),
)
```

---

## Example Usage

```clausal
-import_from(py.opencv, [imread, IMREAD_GRAYSCALE, free])
-import_from(py.opencv_objdetect, [
    make_cascade_classifier, detect_multi_scale, haar_cascade_path,
    make_hog, hog_compute, hog_detect, hog_set_svm_detector,
    hog_default_people_detector
])

Test("load bundled face cascade") <- (
    haar_cascade_path("face", PATH),
    make_cascade_classifier(PATH, CASCADE),
    integer(CASCADE)
)

Test("detect_multi_scale returns list of rects") <- (
    haar_cascade_path("face", PATH),
    make_cascade_classifier(PATH, CASCADE),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect_multi_scale(CASCADE, IMG, RECTS),
    is_list(RECTS)  # may be empty for the abstract test fixture
)

Test("face detection on a face fixture") <- (
    haar_cascade_path("face", PATH),
    make_cascade_classifier(PATH, CASCADE),
    imread("fixtures/face.png", IMREAD_GRAYSCALE, IMG),
    detect_multi_scale(CASCADE, IMG, 1.1, 3, [RECT, *_]),
    RECT is ("rect", _, _, W, H),
    W > 0,
    H > 0
)

Test("haar_cascade_path enumeration") <- (
    findall(N, haar_cascade_path(N, _), NAMES),
    length(NAMES, K),
    K >= 8
)

Test("hog default produces a non-empty descriptor") <- (
    make_hog(HOG),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    # default win_size is (64,128); resize to match
    shape(IMG, [H_PX, W_PX]),
    # Skip if too small — see phase note
    H_PX >= 128,
    W_PX >= 64,
    hog_compute(HOG, IMG, DESC),
    shape(DESC, [_, _])
)

Test("hog default people detector is a non-empty array") <- (
    hog_default_people_detector(SVM),
    shape(SVM, [N]),
    N > 0
)

Test("hog_set_svm_detector returns a new handle") <- (
    make_hog(HOG0),
    hog_default_people_detector(SVM),
    hog_set_svm_detector(HOG0, SVM, HOG1),
    HOG0 \= HOG1
)

Test("free releases a cascade handle") <- (
    haar_cascade_path("face", PATH),
    make_cascade_classifier(PATH, CASCADE),
    free(CASCADE),
    not(detect_multi_scale(CASCADE, _, _))
)
```

The face-detection test references `fixtures/face.png`, a small
permissively-licensed face image (e.g. an OpenCV sample or a CC0
synthetic face) committed to `tests/fixtures/`.

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase8_objdetect.clausal`:

- All Test cases above.
- Each registry name in `haar_cascade_path/2` resolves to a file that
  exists (use `os.path.exists` via a check predicate `++(os.path.exists(P))`).
- HOG opts variants: each opt key is honoured (`win_size`,
  `block_size`, etc.).
- HOG `compute` on a deliberately-sized image (resize first) produces
  the expected descriptor length: `length = nbins * cells_per_block.x *
  cells_per_block.y * blocks_per_window.x * blocks_per_window.y`. The
  test asserts a known length for default params.
- `free` on a HOG handle.

### Python unit tests

- A check that `_haar_facts()` paths all exist on disk after
  `opencv-python` is installed (so we don't ship a broken registry).

---

## Docs

`packages/clausal-opencv/docs/opencv_objdetect.md`:

- Intro: "Pre-deep-learning detectors — Haar/LBP cascades and HOG —
  still useful for small problems, embedded use, and as classical
  baselines. The wrapper exposes both as handle-based predicates and
  ships a registry of the cascade XML files bundled with `opencv-python`."
- Cascade section with the face-detection example.
- HOG section with `make_hog` + `hog_default_people_detector` +
  `hog_set_svm_detector` showing the state-threading pattern.

---

## Issues

### 1. `hog_set_svm_detector` works via descriptor copy — IMPLEMENTED

`cv2.HOGDescriptor.setSVMDetector` mutates the descriptor in place.
The wrapper handles state-threading by constructing a fresh
`cv2.HOGDescriptor(winSize, blockSize, blockStride, cellSize, nbins)`
from the input handle's parameters, calling `setSVMDetector` on the
copy, and registering the copy under a new handle. Original handle
is untouched. Tested via the "original HOG handle remains usable
after set_svm_detector" test case.

### 2. `hog_compute` returns a 1-D vector — DOCUMENTED

The phase plan suggested `shape(DESC, [_, _])` would match. In fact
`cv2.HOGDescriptor.compute` returns a flat 1-D float32 array (e.g.
3780 elements for the default 64×128/16×16/8×8/8×8/9 configuration).
Tests now assert `shape(DESC, [_])`.

### 3. `haar_cascade_path` filters missing files — IMPLEMENTED

If the local opencv build doesn't ship a particular Haar XML, the
fact-builder omits it from the registry. The "all registered
cascades exist on disk" test runs the registry against the actual
filesystem at load time to verify this. Eleven canonical names are
declared; the actual count depends on the install.

### 4. `detect_multi_scale` `()`-vs-`[]` return — HANDLED

When no detections are found, `cv2.CascadeClassifier.detectMultiScale`
may return an empty tuple `()` rather than an empty ndarray. The
`_rectify_detections` helper iterates whatever is returned (both
work) and produces a Python list of `rect` terms — empty or not.

### 5. `cv2.HOGDescriptor` constructor uses positional args — HANDLED

cv2's `HOGDescriptor` takes 5 positional args
`(winSize, blockSize, blockStride, cellSize, nbins)` and does not
accept kwargs. The wrapper accepts a snake_case opts dict, pulls
each value (with defaults), and passes them positionally to cv2.

### 6. HOG detection needs an SVM-installed handle — DOCUMENTED

`hog_detect(HOG, IMG, RECTS)` requires `HOG` to have an SVM
installed. A default `make_hog(HOG)` followed by `hog_detect` would
fail. The test pattern is `make_hog → hog_default_people_detector
→ hog_set_svm_detector → hog_detect`. Documented in
`opencv_objdetect.md`.

### 7. State-threading discussion — verifies design decisions

This phase confirms three design choices from the overview:

- **`hog_set_svm_detector` returns a NEW handle** rather than
  mutating in place. Test: `HOG0 != HOG1`.
- **Original handle stays valid** after the call. Test:
  `hog_compute(HOG0, ...)` after `hog_set_svm_detector` succeeds.
- **Freeing the new handle doesn't invalidate the original**.
  Test: `free(HOG1)` followed by `hog_compute(HOG0, ...)` succeeds.

Together these confirm the state-threaded handle pattern works as
designed in
[overview Step 3](../../implementation_plans/opencv/overview.md#step-3--purity-analysis).
