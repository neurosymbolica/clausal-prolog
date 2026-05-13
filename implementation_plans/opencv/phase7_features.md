# Phase 7 — Features and Matching

Feature detectors (ORB, SIFT, AKAZE, KAZE, BRISK, FAST), descriptor
extractors, and matchers (BFMatcher, FlannBasedMatcher). Handle-based
(Tier 3) with the registry from Phase 1.

Two new tagged-tuple decompositions:

- `keypoint(PT, SIZE, ANGLE, RESPONSE, OCTAVE, CLASS_ID)` — bidirectional
  decompose/construct.
- `dmatch(QUERY_IDX, TRAIN_IDX, IMG_IDX, DISTANCE)` — decompose only
  (DMatch construction in Python user code is rare).

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_features.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — Phase 1
  already adds `NORM_*`. No new constants here.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase7_features.clausal`
- `packages/clausal-opencv/docs/opencv_features.md`
- `packages/clausal-opencv/tests/fixtures/scene.png` — small textured
  image for feature tests.

---

## Predicates

### Detector / extractor construction (Tier 3, handle-based)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `make_orb` | `/1` | `(-handle)` | Default args |
| `make_orb` | `/2` | `(+opts, -handle)` | Opts dict: `n_features`, `scale_factor`, `n_levels`, `edge_threshold`, `first_level`, `wta_k`, `score_type`, `patch_size`, `fast_threshold` |
| `make_sift` | `/1, /2` | as above | Opts: `n_features`, `n_octave_layers`, `contrast_threshold`, `edge_threshold`, `sigma` |
| `make_akaze` | `/1, /2` | as above | |
| `make_kaze` | `/1, /2` | as above | |
| `make_brisk` | `/1, /2` | as above | |
| `make_fast` | `/1, /2` | as above | Opts: `threshold`, `nonmax_suppression`, `type` |

### Detector operations (Tier 3)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `detect` | `/3` | `(+detector_handle, +img, -keypoints)` | |
| `detect` | `/4` | `(+detector_handle, +img, +mask, -keypoints)` | |
| `compute` | `/4` | `(+detector_handle, +img, +keypoints, -descriptors)` | |
| `detect_and_compute` | `/4` | `(+handle, +img, -kps, -descs)` | |
| `detect_and_compute` | `/5` | `(+handle, +img, +mask, -kps, -descs)` | |

### Matcher construction (Tier 3)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `make_bf_matcher` | `/1` | `(-handle)` | Default norm=NORM_L2, crossCheck=False |
| `make_bf_matcher` | `/2` | `(+norm_type, -handle)` | |
| `make_bf_matcher` | `/3` | `(+norm_type, +cross_check, -handle)` | |
| `make_flann_matcher` | `/1` | `(-handle)` | Default params (KDTree, 5 trees, 50 checks) |
| `make_flann_matcher` | `/3` | `(+index_params, +search_params, -handle)` | Both are dicts |

### Matcher operations (Tier 3)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `match` | `/4` | `(+matcher, +query_desc, +train_desc, -matches)` | |
| `knn_match` | `/5` | `(+matcher, +query_desc, +train_desc, +k, -matches)` | matches is list-of-lists |
| `radius_match` | `/5` | `(+matcher, +query_desc, +train_desc, +max_distance, -matches)` | |

### Term enumeration and decomposition (Tier 1)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `keypoint` | `/2` | `(+kp_list, -kp)` | Nondeterministic enumeration over a list of KeyPoints |
| `keypoint_decompose` | `/7` | `(+kp, -pt, -size, -angle, -response, -octave, -class_id)` | Decompose into fields |
| `keypoint_make` | `/7` | `(-kp, +pt, +size, +angle, +response, +octave, +class_id)` | Construct from fields |
| `match_pair` | `/2` | `(+match_list, -m)` | Nondet enumeration |
| `dmatch_decompose` | `/5` | `(+m, -query_idx, -train_idx, -img_idx, -distance)` | |

### Handle lifecycle

| Name | Arity | Modes | Description |
|---|---|---|---|
| `free` | `/1` | `(+handle)` | Inherited from Phase 1's `opencv.py` — releases any Phase 7/8/10 handle |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_features.py
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _deep_deref
from clausal.modules.opencv import _cv
from clausal.modules._opencv_handles import alloc, lookup
```

### Handle-based detector construction

Pattern follows `MakeKdTree` in `scipy_spatial.py:347-351`:

```python
def _make_dispatch(constructor):
    def fn(*opts_args):
        obj = constructor(*opts_args)
        return alloc(obj)
    return fn

def _make_orb_default():
    return _cv().ORB_create()

def _make_orb_opts(opts):
    return _cv().ORB_create(**_opts_to_kwargs_orb(opts))

def _opts_to_kwargs_orb(opts):
    """Map snake_case opts keys to ORB_create kwargs."""
    mapping = {
        "n_features":      "nfeatures",
        "scale_factor":    "scaleFactor",
        "n_levels":        "nlevels",
        "edge_threshold":  "edgeThreshold",
        "first_level":     "firstLevel",
        "wta_k":           "WTA_K",
        "score_type":      "scoreType",
        "patch_size":      "patchSize",
        "fast_threshold":  "fastThreshold",
    }
    return {mapping[k]: v for k, v in opts.items() if k in mapping}

make_orb = _pred("make_orb",
    (1, _pure(lambda: alloc(_make_orb_default()))),
    (2, _pure(lambda opts: alloc(_make_orb_opts(opts)))),
)
```

The same pattern applies to `make_sift`, `make_akaze`, `make_kaze`,
`make_brisk`, `make_fast`. Each has its own opts mapping. Define a
small helper per detector — explicit is better than meta-programming
here because the opts surfaces are stable and small.

### Detector operations — handle-keyed dispatch

Pattern from `KdTreeQuery` in `scipy_spatial.py`:

```python
def _detect(handle, img):
    detector = lookup(handle)
    return list(detector.detect(img))

def _detect_masked(handle, img, mask):
    detector = lookup(handle)
    return list(detector.detect(img, mask=mask))

def _detect_and_compute(handle, img):
    detector = lookup(handle)
    kps, descs = detector.detectAndCompute(img, None)
    return list(kps), descs

def _detect_and_compute_dispatch(this_generator, _proceed, _fail, _catcher,
                                  handle_v, img_v, kps_v, descs_v, trail):
    handle = deref(handle_v)
    img = _deep_deref(img_v)
    try:
        kps, descs = _detect_and_compute(handle, img)
    except Exception:
        yield (_fail, DONE); return
    if unify(kps_v, kps, trail) and unify(descs_v, descs, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

detect = _pred("detect",
    (3, _pure(_detect)),
    (4, _pure(_detect_masked)),
)

detect_and_compute = _pred("detect_and_compute",
    (4, _detect_and_compute_dispatch),
    (5, _detect_and_compute_5_dispatch),  # similar pattern with mask
)
```

### KeyPoint decomposition / construction

`cv2.KeyPoint` exposes `.pt`, `.size`, `.angle`, `.response`,
`.octave`, `.class_id`. The decomposition predicate returns these as
Clausal-friendly values:

```python
def _keypoint_decompose(kp):
    return (list(kp.pt), float(kp.size), float(kp.angle),
            float(kp.response), int(kp.octave), int(kp.class_id))

def _keypoint_decompose_dispatch(this_generator, _proceed, _fail, _catcher,
                                  kp_v, pt_v, size_v, angle_v, resp_v,
                                  octave_v, class_id_v, trail):
    kp = deref(kp_v)
    try:
        pt, size, angle, resp, octave, class_id = _keypoint_decompose(kp)
    except Exception:
        yield (_fail, DONE); return
    if (unify(pt_v, pt, trail)
            and unify(size_v, size, trail)
            and unify(angle_v, angle, trail)
            and unify(resp_v, resp, trail)
            and unify(octave_v, octave, trail)
            and unify(class_id_v, class_id, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)

keypoint_decompose = _pred("keypoint_decompose",
    (7, _keypoint_decompose_dispatch),
)

def _keypoint_make(pt, size, angle, response, octave, class_id):
    return _cv().KeyPoint(
        float(pt[0]), float(pt[1]),
        float(size), float(angle), float(response),
        int(octave), int(class_id),
    )

keypoint_make = _pred("keypoint_make",
    (7, _pure(lambda kp_var_placeholder, pt, size, angle, resp, oct, cls:
              # First arg is the result var (handled by _pure as last);
              # actual signature uses _pure's args[-2] convention.
              # The construction is the simple case below.
              _keypoint_make(pt, size, angle, resp, oct, cls))),
)
```

**Design check**: a single bidirectional `keypoint/7` is cleaner than
separate `_make` / `_decompose`. Following the `_bidir_2` pattern, we
can write:

```python
def _keypoint_dispatch(this_generator, _proceed, _fail, _catcher,
                       kp_raw, pt_raw, size_raw, angle_raw, resp_raw,
                       octave_raw, class_id_raw, trail):
    kp = deref(kp_raw)
    fields = [deref(v) for v in
              (pt_raw, size_raw, angle_raw, resp_raw, octave_raw, class_id_raw)]
    kp_unbound = is_var(kp)
    fields_all_bound = not any(is_var(f) for f in fields)
    fields_all_unbound = all(is_var(f) for f in fields)

    if not kp_unbound and (fields_all_unbound or not fields_all_bound):
        # Decompose
        pt, size, angle, resp, octave, class_id = _keypoint_decompose(kp)
        ok = (unify(pt_raw, pt, trail)
              and unify(size_raw, size, trail)
              and unify(angle_raw, angle, trail)
              and unify(resp_raw, resp, trail)
              and unify(octave_raw, octave, trail)
              and unify(class_id_raw, class_id, trail))
        if ok:
            yield (_proceed, None)
    elif kp_unbound and fields_all_bound:
        # Construct
        new_kp = _keypoint_make(*fields)
        if unify(kp_raw, new_kp, trail):
            yield (_proceed, None)
    yield (_fail, DONE)

keypoint = _pred("keypoint",
    (7, _keypoint_dispatch),
)
```

**However** — `keypoint/2` is already used for nondeterministic
enumeration over a list of keypoints. Two predicates of different
arity sharing the same name is fine (Clausal dispatches on arity),
so we have:

- `keypoint/2` — `(+kp_list, -kp)`, nondet enumeration.
- `keypoint/7` — `(?kp, ?pt, ?size, ?angle, ?resp, ?octave, ?class_id)`,
  bidirectional decompose/construct.

This is cleaner than three separate names (`keypoint_decompose`,
`keypoint_make`, `keypoint`). **The phase ships keypoint/2 and
keypoint/7 only**; the `_decompose`/`_make` names in the predicate
catalogue above are deprecated before they're written. The overview's
predicate catalogue should be updated to match — filed as an Issue
below.

For DMatch, the same logic applies but DMatch construction from
Python is rare in practice. Ship:

- `match_pair/2` — `(+match_list, -m)`, nondet enumeration.
- `dmatch/5` — `(+m, -query_idx, -train_idx, -img_idx, -distance)`,
  decompose only. Construction can be added later if needed.

### `keypoint/2` and `match_pair/2` — nondet enumeration

```python
def _enum_dispatch(this_generator, _proceed, _fail, _catcher,
                   list_v, item_v, trail):
    lst = _deep_deref(list_v)
    if not isinstance(lst, (list, tuple)):
        yield (_fail, DONE); return
    for item in lst:
        mark = trail.mark()
        if unify(item_v, item, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)

keypoint = _pred("keypoint",
    (2, _enum_dispatch),
    (7, _keypoint_dispatch),  # bidirectional, see above
)

match_pair = _pred("match_pair",
    (2, _enum_dispatch),
)
```

Note `_enum_dispatch` is general — it could live in `_helpers.py` as
`_enumerate_2`. Filed as a follow-up.

### Matcher operations

```python
def _match(matcher_handle, query_desc, train_desc):
    matcher = lookup(matcher_handle)
    return list(matcher.match(query_desc, train_desc))

def _knn_match(matcher_handle, query_desc, train_desc, k):
    matcher = lookup(matcher_handle)
    return [list(m) for m in matcher.knnMatch(query_desc, train_desc, int(k))]

def _radius_match(matcher_handle, query_desc, train_desc, max_dist):
    matcher = lookup(matcher_handle)
    return [list(m) for m in matcher.radiusMatch(query_desc, train_desc, float(max_dist))]

match = _pred("match",
    (4, _pure(_match)),
)
knn_match = _pred("knn_match",
    (5, _pure(_knn_match)),
)
radius_match = _pred("radius_match",
    (5, _pure(_radius_match)),
)
```

### Test fixture

`tests/fixtures/scene.png` — a small textured 64×64 PNG that produces
enough ORB keypoints for the tests below. Generated once and committed:

```python
import cv2, numpy as np
np.random.seed(42)
img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
# Add a few high-contrast features
cv2.rectangle(img, (10, 10), (30, 30), (255, 255, 255), 2)
cv2.circle(img, (45, 45), 8, (0, 0, 0), 2)
cv2.imwrite("fixtures/scene.png", img)
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, IMREAD_COLOR, IMREAD_GRAYSCALE, NORM_HAMMING, NORM_L2,
    free
])
-import_from(py.opencv_features, [
    make_orb, make_sift, make_bf_matcher, make_flann_matcher,
    detect, compute, detect_and_compute,
    match, knn_match, radius_match,
    keypoint, match_pair, dmatch
])

Test("make_orb default returns a handle (integer)") <- (
    make_orb(H),
    integer(H)
)

Test("orb detect_and_compute yields nonempty results") <- (
    make_orb({n_features: 100}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect_and_compute(ORB, IMG, KPS, DESCS),
    length(KPS, N),
    N > 0,
    shape(DESCS, [N, _])
)

Test("keypoint enumeration") <- (
    make_orb({n_features: 50}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect(ORB, IMG, KPS),
    findall(KP, keypoint(KPS, KP), ALL),
    length(KPS, N),
    length(ALL, N)
)

Test("keypoint/7 decomposes to fields") <- (
    make_orb({n_features: 10}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect(ORB, IMG, [KP, *_]),
    keypoint(KP, [X, Y], SIZE, _, RESP, _, _),
    X >= 0.0,
    Y >= 0.0,
    SIZE > 0.0,
    RESP >= 0.0
)

Test("bf_matcher hamming matches descriptors") <- (
    make_orb({n_features: 200}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect_and_compute(ORB, IMG, _, DESCS),
    make_bf_matcher(NORM_HAMMING, BF),
    match(BF, DESCS, DESCS, MATCHES),
    findall(M, match_pair(MATCHES, M), ALL),
    length(ALL, N),
    N > 0
)

Test("self-match distances are zero") <- (
    make_orb({n_features: 50}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect_and_compute(ORB, IMG, _, DESCS),
    make_bf_matcher(NORM_HAMMING, BF),
    match(BF, DESCS, DESCS, MATCHES),
    findall(D, (
        match_pair(MATCHES, M),
        dmatch(M, _, _, _, D)
    ), DISTANCES),
    findall(D, (member(D, DISTANCES), D > 0), NON_ZERO),
    length(NON_ZERO, 0)
)

Test("knn_match yields k candidates per query") <- (
    make_orb({n_features: 50}, ORB),
    imread("fixtures/scene.png", IMREAD_GRAYSCALE, IMG),
    detect_and_compute(ORB, IMG, _, DESCS),
    make_bf_matcher(NORM_HAMMING, BF),
    knn_match(BF, DESCS, DESCS, 2, KNN),
    KNN is [FIRST_GROUP, *_],
    length(FIRST_GROUP, 2)
)

Test("free releases an ORB handle") <- (
    make_orb(H),
    free(H),
    not(detect(H, _, _))  # using freed handle fails
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase7_features.clausal`:

- All Test cases above.
- Each `make_*` predicate (ORB, SIFT, AKAZE, KAZE, BRISK, FAST) with
  default and opts variants — verify handle is an integer.
- `compute` (separate from detect): detect, then compute, descriptors
  have the expected shape.
- `radius_match` with a generous radius.
- FLANN matcher with default params on SIFT descriptors (FLANN doesn't
  work with Hamming distance, so this uses SIFT).
- `dmatch/5` decomposition: `query_idx` and `train_idx` are integers,
  `distance` is non-negative.

### Python unit tests

`tests/test_opencv_infra.py` extends with:

- Handle registry distinguishes detector and matcher handles by
  storing the constructed object — `free` on an ORB handle does not
  affect a BFMatcher handle.

---

## Docs

`packages/clausal-opencv/docs/opencv_features.md`:

- Intro: "OpenCV ships several classical feature detectors and
  descriptor extractors (ORB, SIFT, AKAZE, KAZE, BRISK, FAST) and two
  matchers (BFMatcher, FlannBasedMatcher). The wrapper exposes each as
  a handle-based predicate group."
- Section per detector with `make_*` and the opts dict spec.
- Section on matchers, including the Hamming-vs-L2 norm choice
  (binary descriptors like ORB use Hamming; SIFT uses L2).
- Section on `keypoint/2`, `keypoint/7`, `match_pair/2`, `dmatch/5`
  with decomposition examples.
- Note on the ratio test (Lowe's) using `knn_match` + a custom
  predicate. Refer to the [overview showcase](overview.md#step-9--showcase-example).

---

## Issues

- **`keypoint/2,7` as dual-arity** — IMPLEMENTED. `keypoint/2` is the
  nondeterministic enumerator over a KeyPoint list; `keypoint/7` is
  the bidirectional decomposer / constructor. The original
  `keypoint_decompose/7` and `keypoint_make/7` names from the plan
  were not shipped — the dual-arity form is more relational.
- **`_enum_dispatch` is defined locally** in `opencv_features.py`,
  shared between `keypoint/2` and `match_pair/2`. The same helper
  would simplify `contour/2` (Phase 4) — lifting it to
  `_helpers.py` is a candidate cleanup, but not a blocker.

## Issues

### 1. Constants use lowercase aliases — INHERITED FROM PHASE 1

`NORM_*` flags were already added in Phase 1. `DRAW_MATCHES_FLAGS_*`
were added in Phase 6. No new constants in Phase 7.

### 2. Opts dicts require string keys — DOCUMENTED

`make_orb({"n_features": 100}, H)` — the keys must be **quoted
strings**, not bare identifiers. A bare-identifier key (`n_features`
without quotes) is parsed as a Clausal LoadName and the resulting
`{LoadName('n_features'): 100}` dict fails with
`TypeError: unhashable type: 'LoadName'`. Same convention as torch
(`zeros([2,3], {"dtype": float64}, T)`).

### 3. `member/2` is not the list-membership name — `in_/2`

The standard list-membership predicate is `in_/2`, not `member/2`.
`findall(D, (in_(D, LIST), D > 0.0), NON_ZERO)` is the right form.
Affects the self-match-distance test in Phase 7.

### 4. `H1 != H2` for distinct-handle check — `\=` is invalid syntax

Clausal parses Python AST, so Prolog's `\=` (not-unify) does not
parse. Use `!=` (Python not-equal). The integer handles are plain
Python ints, so `!=` does the right thing.

### 5. Detector classes are stateless after construction — VERIFIED

`cv2.ORB.detect(img)` and similar do not mutate the detector. Two
calls with the same image produce identical keypoints. This is what
makes Tier 3 handles backtracking-safe without copy/restore — see
the discussion in
[overview Step 3](../../implementation_plans/opencv/overview.md#step-3--purity-analysis).

### 6. `BFMatcher.add()` accumulator not exposed — DECIDED

`cv2.BFMatcher` supports an `.add(descriptors)` mode that accumulates
a corpus to match against. The wrapper does **not** expose this —
only the stateless `match(matcher, query, train, matches)` form.
Mutating the matcher's internal descriptor pool would require either
copy-on-write per call (expensive) or state-threaded handles (extra
complexity for a workflow that's already cleanly stateless).

### 7. FLANN needs float32 — DOCUMENTED

`cv2.FlannBasedMatcher` requires `float32` descriptors. ORB/AKAZE/
BRISK produce uint8 binary descriptors, so the test pairs FLANN
with SIFT (which produces 128-dim float32). Documented in
`opencv_features.md`.

### 8. `cv2.KeyPoint` constructor signature — VERIFIED

cv2's `KeyPoint(x, y, size, angle, response, octave, class_id)`
takes 7 scalar args. The wrapper's `keypoint/7` accepts `PT` as a
`[x, y]` list (for symmetry with the decomposed form) and unpacks
into the first two scalar args.
