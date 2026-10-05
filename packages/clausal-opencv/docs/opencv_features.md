# `opencv_features` — Feature detectors and matchers

Six classical feature detectors (ORB, SIFT, AKAZE, KAZE, BRISK, FAST)
and two descriptor matchers (Brute Force, FLANN). Plus
`keypoint/2,7`, `match_pair/2`, and `dmatch/5` for enumerating and
decomposing the `cv2.KeyPoint` and `cv2.DMatch` outputs.

## Statefulness

Detectors and matchers are **Tier 3 handle-based**. They are
**read-only after construction**:

- `cv2.ORB.detect(img)` and similar do not mutate the detector.
- `cv2.BFMatcher.match(query, train)` does not mutate the matcher.

The handle is just an integer key into a process-global registry of
detector / matcher objects (see `_opencv_handles.py`). Because the
underlying objects don't change between calls, **backtracking over
detect/match calls is safe with no copying or restoration** — re-running
the call gives identical output. See
[overview Step 3](../../implementation_plans/opencv/overview.md#step-3--purity-analysis)
for the full purity analysis.

The standard `free/1` predicate (Phase 1) releases any feature
handle.

```seam
-import_from(opencv_features, [
    make_orb, make_sift, make_akaze, make_brisk, make_fast,
    detect, compute, detect_and_compute,
    make_bf_matcher, make_flann_matcher,
    match, knn_match, radius_match,
    keypoint, match_pair, dmatch,
])
-import_from(opencv, [norm_hamming, norm_l2, free])
```

## Detector predicate index

Each `make_*/1,2` takes an optional **string-keyed opts dict** (use
quoted keys — `{"n_features": 500}`, not `{n_features: 500}`).

### ORB

| Predicate | Arity | Opt keys |
|---|---|---|
| `make_orb(H)` | /1 | — |
| `make_orb(OPTS, H)` | /2 | `n_features`, `scale_factor`, `n_levels`, `edge_threshold`, `first_level`, `wta_k`, `score_type`, `patch_size`, `fast_threshold` |

Binary 256-bit descriptors (32 bytes per keypoint). Use
`norm_hamming` matcher distance.

### SIFT

| Predicate | Arity | Opt keys |
|---|---|---|
| `make_sift(H)` | /1 | — |
| `make_sift(OPTS, H)` | /2 | `n_features`, `n_octave_layers`, `contrast_threshold`, `edge_threshold`, `sigma` |

128-dimensional float32 descriptors. Use `norm_l2` matcher distance.

### AKAZE / KAZE / BRISK / FAST

All follow the same `make_X/1,2` pattern. The accepted opt-dict keys
are listed in `opencv_features.py:_AKAZE_OPTS` etc.

- AKAZE → binary descriptors → `norm_hamming`
- KAZE → float descriptors → `norm_l2`
- BRISK → binary descriptors → `norm_hamming`
- FAST → detector only (no descriptors)

## Detection / description

| Predicate | Arity | Description |
|---|---|---|
| `detect(HANDLE, IMG, KEYPOINTS)` | /3 | Returns a Python list of `cv2.KeyPoint` |
| `detect(HANDLE, IMG, MASK, KEYPOINTS)` | /4 | With uint8 mask |
| `compute(HANDLE, IMG, KEYPOINTS, DESCRIPTORS)` | /4 | After `detect`, fill in descriptors |
| `detect_and_compute(HANDLE, IMG, KEYPOINTS, DESCRIPTORS)` | /4 | Combined |
| `detect_and_compute(HANDLE, IMG, MASK, KEYPOINTS, DESCRIPTORS)` | /5 | With mask |

Keypoints come back as a **Python list of `cv2.KeyPoint` objects**.
Descriptors are an ndarray with shape `[N, descriptor_size]` and
dtype that depends on the detector (uint8 for binary, float32 for
SIFT/KAZE).

## Matcher predicate index

### Brute Force

| Predicate | Arity | Notes |
|---|---|---|
| `make_bf_matcher(H)` | /1 | Default norm_l2, no cross-check |
| `make_bf_matcher(NORM, H)` | /2 | Use `norm_hamming` for binary descriptors |
| `make_bf_matcher(NORM, CROSS_CHECK, H)` | /3 | Cross-check filters mutual matches |

### FLANN

| Predicate | Arity | Notes |
|---|---|---|
| `make_flann_matcher(H)` | /1 | Default KDTree, 5 trees, 50 checks |
| `make_flann_matcher(INDEX_PARAMS, SEARCH_PARAMS, H)` | /3 | Both string-keyed dicts |

FLANN requires **float32 descriptors**, so it pairs with SIFT/KAZE,
not ORB/AKAZE/BRISK (use BF + `norm_hamming` for those).

## Matching

| Predicate | Arity | Description |
|---|---|---|
| `match(MATCHER, QUERY_DESC, TRAIN_DESC, MATCHES)` | /4 | One `DMatch` per query keypoint |
| `knn_match(MATCHER, QUERY, TRAIN, K, MATCHES)` | /5 | List of K matches per query keypoint |
| `radius_match(MATCHER, QUERY, TRAIN, MAX_DIST, MATCHES)` | /5 | All matches within radius |

`MATCHES` from `match/4` is a flat list of `cv2.DMatch`. From
`knn_match/5` and `radius_match/5` it's a list-of-lists.

## KeyPoint and DMatch terms

### `keypoint/2,7`

```
keypoint(KP_LIST, KP)                                                 % nondet enum
keypoint(KP, PT, SIZE, ANGLE, RESPONSE, OCTAVE, CLASS_ID)             % bidirectional
```

`keypoint/7` is **bidirectional**:

- When `KP` is bound and the fields are unbound, decompose: bind
  fields from the keypoint.
- When `KP` is unbound and all fields are bound, construct: build
  a new `cv2.KeyPoint` from the fields.

```seam
% Decompose
detect(ORB, IMG, [KP, *_]),
keypoint(KP, [X, Y], SIZE, _, RESP, _, _)

% Construct
keypoint(KP, [10.0, 20.0], 5.0, 0.0, 0.5, 0, 0)
```

`PT` is a 2-element list `[x, y]`. `OCTAVE` and `CLASS_ID` are ints;
`SIZE`, `ANGLE`, `RESPONSE` are floats.

### `match_pair/2`, `dmatch/5`

```
match_pair(MATCH_LIST, M)                                  % nondet enum
dmatch(M, QUERY_IDX, TRAIN_IDX, IMG_IDX, DISTANCE)         % decompose
```

`dmatch/5` is **decompose only** — construction is rare (cv2 builds
DMatch objects internally during matching).

## Drawing keypoints and matches

The `draw_keypoints/4,5` and `draw_matches/7` predicates ship in
[`opencv_draw`](opencv_draw.md) (Phase 6) but are tested with the
real KeyPoint/DMatch lists Phase 7 produces. See the worked examples
below.

## Worked examples

Each example below is an exact copy of an integration test in
`tests/fixtures/opencv_phase7_features.seam`.

### ORB detect-and-compute

```seam
make_orb({"n_features": 200}, ORB),
imread("scene.png", imread_grayscale, IMG),
detect_and_compute(ORB, IMG, KPS, DESCS),
length(KPS, N),
shape(DESCS, [N, 32])     % ORB produces 32-byte descriptors
```

### Self-match with BF + Hamming

```seam
make_orb({"n_features": 50}, ORB),
detect_and_compute(ORB, IMG, _, DESCS),
make_bf_matcher(norm_hamming, BF),
match(BF, DESCS, DESCS, MATCHES),
findall(D, (
    match_pair(MATCHES, M),
    dmatch(M, _, _, _, D)
), DISTANCES),
% Every distance is zero because DESCS matches against itself
findall(D, (in_(D, DISTANCES), D > 0.0), NON_ZERO),
length(NON_ZERO, 0)
```

### k-NN match

```seam
knn_match(BF, DESCS, DESCS, 2, [FIRST_GROUP, *_]),
length(FIRST_GROUP, 2)
```

### FLANN with SIFT

```seam
make_sift({"n_features": 50}, SIFT),
detect_and_compute(SIFT, IMG, _, DESCS),
make_flann_matcher(FLANN),
match(FLANN, DESCS, DESCS, MATCHES)
```

### Build a `cv2.KeyPoint` from scratch

```seam
keypoint(KP, [10.0, 20.0], 5.0, 0.0, 0.5, 0, 0),
keypoint(KP, [X, Y], SIZE, _, RESP, _, _),
X == 10.0, Y == 20.0, SIZE == 5.0, RESP == 0.5
```

### Lowe's ratio test

The canonical filter for `knn_match` k=2 results — keep only the
first match if its distance is significantly shorter than the
second:

```seam
good_match(MATCH_PAIR, GOOD) <- (
    MATCH_PAIR = [M1, M2],
    dmatch(M1, _, _, _, D1),
    dmatch(M2, _, _, _, D2),
    D1 < 0.75 * D2,
    GOOD = M1
)
```

### Free a handle

```seam
make_orb(H),
free(H),
not detect(H, _, _)     % subsequent use of H fails
```

### Overlay keypoints (uses Phase 6 `draw_keypoints`)

```seam
make_orb({"n_features": 20}, ORB),
imread("scene.png", imread_color, IMG),
cvt_color(IMG, color_bgr2gray, GRAY),
detect(ORB, GRAY, KPS),
draw_keypoints(IMG, KPS, [0, 255, 0], OUT)
```

### Side-by-side match visualization (uses Phase 6 `draw_matches`)

```seam
detect_and_compute(ORB, GRAY, KPS, DESCS),
make_bf_matcher(norm_hamming, BF),
match(BF, DESCS, DESCS, MATCHES),
draw_matches(IMG, KPS, IMG, KPS, MATCHES,
             draw_matches_flags_default, OUT)
```

## See also

- [`opencv`](opencv.md) — `norm_*` constants and `free/1`.
- [`opencv_draw`](opencv_draw.md) — `draw_keypoints` and
  `draw_matches` consume the lists this module produces.
- [`opencv_calib3d`](opencv_calib3d.md) (Phase 9) — `findHomography`
  consumes the point arrays you extract from matched keypoints.
