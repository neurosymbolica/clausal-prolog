# `opencv_objdetect` — Classical object detection

Pre-deep-learning object detection: Haar/LBP cascade classifiers and
HOG descriptors. Still useful for small problems, embedded use, and
as classical baselines.

This is the first phase that uses **state-threaded handles** — see
`hog_set_svm_detector/3` below.

```clausal
-import_from(opencv_objdetect, [
    make_cascade_classifier, detect_multi_scale, haar_cascade_path,
    make_hog, hog_compute, hog_detect,
    hog_set_svm_detector, hog_default_people_detector,
])
-import_from(opencv, [free])
```

## Cascade classifier

Haar/LBP cascades are read-only after loading — once the XML is
loaded, the cascade does not change. Tier 3 handle, no copying.

| Predicate | Arity | Description |
|---|---|---|
| `make_cascade_classifier(XML_PATH, HANDLE)` | /2 | Loads from XML; fails if path is missing or XML is empty |
| `detect_multi_scale(HANDLE, IMG, RECTS)` | /3 | Returns a list of `("rect", x, y, w, h)` tuples |
| `detect_multi_scale(HANDLE, IMG, SCALE, RECTS)` | /4 | With `scaleFactor` |
| `detect_multi_scale(HANDLE, IMG, SCALE, NEIGHBORS, RECTS)` | /5 | With `minNeighbors` |
| `detect_multi_scale(HANDLE, IMG, SCALE, NEIGHBORS, MIN_SIZE, RECTS)` | /6 | With `minSize=[w, h]` |

Detections are returned as tagged `rect` terms (the same constructor
used by Phase 4's `bounding_rect/2`), so they can be drawn directly:

```clausal
detect_multi_scale(CASCADE, IMG, RECTS),
in_(("rect", X, Y, W, H), RECTS),
rectangle(IMG, [X, Y], [X+W, Y+H], [0, 255, 0], OUT)
```

### `haar_cascade_path/2` registry

`opencv-python` bundles a set of pre-trained Haar XMLs at
`cv2.data.haarcascades`. The registry exposes the most-used ones
by short name. A NAME is a key: given, it may be an atom or a string
(`face` or `"face"`); enumerated, it comes back as an atom. The PATH is
free-form text and comes back as a **string**, not an atom:

| Name | Cascade |
|---|---|
| `"face"` | `haarcascade_frontalface_default.xml` |
| `"face_alt"`, `"face_alt2"` | Alternative frontal-face variants |
| `"profile_face"` | `haarcascade_profileface.xml` |
| `"eye"` | `haarcascade_eye.xml` |
| `"eye_tree_eyeglasses"` | Eyes with glasses |
| `"smile"` | `haarcascade_smile.xml` |
| `"body"`, `"upper_body"`, `"lower_body"` | Full / partial bodies |
| `"license_plate"` | Russian plate number |

The registry filters out names whose XML isn't actually present in
your opencv install — if your build ships only a subset, only those
appear in `findall(N, haar_cascade_path(N, _), NAMES)`.

```clausal
haar_cascade_path("face", PATH),
make_cascade_classifier(PATH, CASCADE)
```

## HOG descriptor

`cv2.HOGDescriptor` is mostly read-only — `compute` and
`detectMultiScale` don't change the descriptor object. The exception
is `setSVMDetector(svm)`, which installs an SVM in-place for use by
the detector. The wrapper handles this with **explicit state
threading**: see `hog_set_svm_detector` below.

### Construction and compute

| Predicate | Arity | Description |
|---|---|---|
| `make_hog(HANDLE)` | /1 | Default 64×128 window, 16×16 block, 8×8 stride, 8×8 cell, 9 bins (cv2 pedestrian defaults) |
| `make_hog(OPTS, HANDLE)` | /2 | String-keyed opts dict |
| `hog_compute(HANDLE, IMG, DESCRIPTORS)` | /3 | Returns a 1-D float32 ndarray |
| `hog_default_people_detector(SVM)` | /1 | The built-in pedestrian SVM vector |

Opt-dict keys (with defaults): `"win_size": [64, 128]`,
`"block_size": [16, 16]`, `"block_stride": [8, 8]`,
`"cell_size": [8, 8]`, `"nbins": 9`.

### Detection — state-threaded SVM installation

```
hog_set_svm_detector(HOG0, SVM, HOG1)
```

This is the canonical state-threaded handle pattern:

1. **HOG0** — input handle, **unchanged after the call**.
2. **SVM** — the SVM vector to install (an ndarray, usually from
   `hog_default_people_detector/1`).
3. **HOG1** — output handle, a **fresh registry entry** holding a
   **copy** of HOG0's underlying `cv2.HOGDescriptor` with the SVM
   installed.

Why this shape? `cv2.HOGDescriptor.setSVMDetector` mutates the
descriptor in place. If the wrapper called it directly on HOG0's
object, any term still holding HOG0 would silently get the
SVM-installed version on a subsequent goal — and backtracking
above the call would leave that mutation in place.

Instead the wrapper does:

```python
def _hog_set_svm(handle0, svm):
    hog0 = lookup(handle0)
    new_hog = _copy_hog_descriptor(hog0)   # fresh cv2.HOGDescriptor
    new_hog.setSVMDetector(svm)            # mutate the copy
    return alloc(new_hog)                   # register under new handle
```

After the call:

- `HOG0` still points to the original (no SVM, can still `hog_compute`).
- `HOG1` points to the SVM-installed copy (can also `hog_detect`).
- Backtracking past the call abandons `HOG1`; the registry entry
  still exists until explicitly freed (which is harmless if no
  outer goal references it).

```clausal
make_hog(HOG0),
hog_default_people_detector(SVM),
hog_set_svm_detector(HOG0, SVM, HOG1),
HOG0 != HOG1,                            % distinct handles
hog_detect(HOG1, BIG_IMG, RECTS)        % uses the SVM
```

This is the same pattern as standard Prolog state threading:
`pred(STATE_IN, ..., STATE_OUT)`. The HOG handle is the state; the
predicate takes the old state, returns the new state. Backtracking
naturally restores the previous state by abandoning the output
handle.

### Detection predicates

| Predicate | Arity | Description |
|---|---|---|
| `hog_detect(HANDLE, IMG, RECTS)` | /3 | Default detector settings |
| `hog_detect(HANDLE, IMG, OPTS, RECTS)` | /4 | Opts: `win_stride`, `padding`, `scale` |

The HOG handle must have an SVM installed (via
`hog_set_svm_detector`) or detection will fail. `RECTS` is the same
`("rect", x, y, w, h)` list as `detect_multi_scale/3-6`.

## Worked examples

### Face detection from the bundled cascade

```clausal
haar_cascade_path("face", PATH),
make_cascade_classifier(PATH, CASCADE),
imread("photo.jpg", imread_grayscale, IMG),
detect_multi_scale(CASCADE, IMG, 1.1, 3, RECTS)
```

### Enumerate every bundled cascade name

```clausal
findall(N, haar_cascade_path(N, _), NAMES),
length(NAMES, K),
K >= 5
```

### People detection with HOG + the default pedestrian SVM

```clausal
make_hog(HOG0),
hog_default_people_detector(SVM),
hog_set_svm_detector(HOG0, SVM, HOG),
imread("photo.jpg", imread_grayscale, IMG),
hog_detect(HOG, IMG, {"win_stride": [8, 8], "scale": 1.05}, RECTS)
```

### HOG compute on a fixed-size window

```clausal
make_hog(HOG),                          % default 64x128 window
imread("clip.png", imread_grayscale, IMG),
resize(IMG, [64, 128], RESIZED),
hog_compute(HOG, RESIZED, DESC),
shape(DESC, [3780])                     % 9 bins * 4 cells/block * 105 blocks
```

### Free a handle

```clausal
haar_cascade_path("face", PATH),
make_cascade_classifier(PATH, H),
free(H),
not detect_multi_scale(H, _, _)         % H is gone
```

## See also

- [`opencv`](opencv.md) — `free/1` lifecycle and the `rect/5` term
  shared with Phase 4.
- [`opencv_imgproc`](opencv_imgproc.md) — `resize` (commonly applied
  before HOG compute to fit the descriptor window).
- [`opencv_draw`](opencv_draw.md) — `rectangle/5,6,7` to overlay
  detection boxes on the source image.
