# Phase 9 — Camera Calibration and Homography

3D geometry: homography fitting, fundamental/essential matrices,
PnP, camera calibration, undistortion, and rotation
representations. All Tier 1 (pure).

One bijective: `rodrigues/2` — `cv2.Rodrigues` is the same function
in both directions; cv2 detects whether the input is a 3-vector
(produces a rotation matrix) or a rotation matrix (produces a 3-vector).

Several predicates return **tagged-tuple result terms** for
multi-value outputs:

- `pnp_ransac(RVEC, TVEC, INLIERS)`
- `calib(RMS, K, DIST, RVECS, TVECS)`
- `pose(R, T, MASK, N_INLIERS)`

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_calib3d.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend
  `_CONSTANT_NAMES` with `RANSAC`, `LMEDS`, `FM_*`, `SOLVEPNP_*`,
  `CALIB_*` flags.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase9_calib3d.clausal`
- `packages/clausal-opencv/docs/opencv_calib3d.md`
- A synthetic checkerboard fixture for calibration tests.

---

## Predicates

### Homography and epipolar geometry

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `find_homography` | `/3` | `(+src, +dst, -H)` | 1 | Default method=0 (least-squares) |
| `find_homography` | `/4` | `(+src, +dst, +method, -H)` | 1 | |
| `find_homography_mask` | `/4` | `(+src, +dst, +method, -H, -mask)` | 1 | Returns both |
| `find_homography_mask` | `/5` | `(+src, +dst, +method, +ransac_thresh, -H, -mask)` | 1 | |
| `find_fundamental_mat` | `/3` | `(+pts1, +pts2, -F)` | 1 | Default method=FM_RANSAC |
| `find_fundamental_mat` | `/4` | `(+pts1, +pts2, +method, -F)` | 1 | |
| `find_essential_mat` | `/3` | `(+pts1, +pts2, +camera_matrix, -E)` | 1 | |
| `find_essential_mat` | `/4` | `(+pts1, +pts2, +camera_matrix, +method, -E)` | 1 | |

### PnP

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `solve_pnp` | `/6` | `(+obj_pts, +img_pts, +K, +dist, -rvec, -tvec)` | 1 | |
| `solve_pnp` | `/7` | `(+obj_pts, +img_pts, +K, +dist, +flags, -rvec, -tvec)` | 1 | |
| `solve_pnp_ransac` | `/5` | `(+obj_pts, +img_pts, +K, +dist, -result)` | 1 | result: `pnp_ransac(RVEC, TVEC, INLIERS)` |
| `solve_pnp_ransac` | `/6` | `+flags` | 1 | |

### Calibration

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `find_chessboard_corners` | `/3` | `(+img, +pattern_size, -corners)` | 1 | Returns `[]` if not found |
| `find_chessboard_corners` | `/4` | `(+img, +pattern_size, +flags, -corners)` | 1 | |
| `corner_sub_pix` | `/5` | `(+img, +corners, +win_size, +zero_zone, -refined)` | 1 | Always uses default criteria |
| `corner_sub_pix` | `/6` | `(+img, +corners, +win_size, +zero_zone, +criteria, -refined)` | 1 | |
| `calibrate_camera` | `/4` | `(+obj_pts_list, +img_pts_list, +image_size, -result)` | 1 | result: `calib(RMS, K, DIST, RVECS, TVECS)` |
| `calibrate_camera` | `/5` | `+flags` | 1 | |

### Projection and undistortion

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `project_points` | `/5` | `(+obj_pts, +rvec, +tvec, +K, +dist, -img_pts, -jacobian)` (note 7 actual args) | 1 | Always returns both image points and jacobian |
| `undistort` | `/4` | `(+img, +K, +dist, -out)` | 1 | |
| `undistort` | `/5` | `(+img, +K, +dist, +new_K, -out)` | 1 | |
| `init_undistort_rectify_map` | `/8` | `(+K, +dist, +R, +new_K, +image_size, +m1type, -map1, -map2)` | 1 | |

### Rotation representations (bijective)

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `rodrigues` | `/2` | `(+rvec, -rmat)` / `(-rvec, +rmat)` | 1 | yes | `cv2.Rodrigues` |

### Pose recovery and homography decomposition

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `recover_pose` | `/4` | `(+E, +pts1, +pts2, +K, -result)` | 1 | result: `pose(R, T, MASK, N_INLIERS)` |
| `decompose_homography_mat` | `/3` | `(+H, +K, -solutions)` | 1 | solutions: list of `(R, T, N)` tuples |

### DFT (useful here as a frequency-domain tool)

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `dft` | `/2` | `(+img, -spec)` / `(-img, +spec)` | 1 | yes | `cv2.dft` ↔ `cv2.idft` |
| `dft` | `/3` | `(+img, +flags, -spec)` | 1 | partial | Forward-only with explicit flags |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_calib3d.py
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _bidir_2, _deep_deref
from clausal.modules.opencv import _cv
```

### `find_homography/3,4` and `find_homography_mask/4,5`

`cv2.findHomography` returns `(H, mask)` even when the caller doesn't
want the mask. We split into two predicates:

- `find_homography/3,4` ignores the mask and returns just `H`.
- `find_homography_mask/4,5` returns both.

```python
def _find_homography(src, dst, method=0):
    H, _mask = _cv().findHomography(src, dst, int(method))
    return H

def _find_homography_mask(src, dst, method, ransac_thresh=None):
    if ransac_thresh is None:
        H, mask = _cv().findHomography(src, dst, int(method))
    else:
        H, mask = _cv().findHomography(src, dst, int(method),
                                          float(ransac_thresh))
    return H, mask

find_homography = _pred("find_homography",
    (3, _pure(lambda s, d: _find_homography(s, d))),
    (4, _pure(_find_homography)),
)

def _fh_mask_4_dispatch(this_generator, _proceed, _fail, _catcher,
                        s_v, d_v, m_v, H_v, mask_v, trail):
    s = _deep_deref(s_v); d = _deep_deref(d_v); m = deref(m_v)
    try:
        H, mask = _find_homography_mask(s, d, m)
    except Exception:
        yield (_fail, DONE); return
    if unify(H_v, H, trail) and unify(mask_v, mask, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

# Similar for /5 with ransac_thresh
find_homography_mask = _pred("find_homography_mask",
    (4, _fh_mask_4_dispatch),
    (5, _fh_mask_5_dispatch),
)
```

### `solve_pnp/6,7`

`cv2.solvePnP` returns `(retval, rvec, tvec)`. The wrapper discards
`retval` (it's a boolean success flag — failure causes the predicate
to fail) and unifies `rvec`, `tvec`:

```python
def _solve_pnp(obj, img, K, dist, flags=None):
    cv = _cv()
    if flags is None:
        ok, rvec, tvec = cv.solvePnP(obj, img, K, dist)
    else:
        ok, rvec, tvec = cv.solvePnP(obj, img, K, dist, flags=int(flags))
    if not ok:
        raise RuntimeError("solvePnP returned False")
    return rvec, tvec

def _solve_pnp_6_dispatch(this_generator, _proceed, _fail, _catcher,
                          obj_v, img_v, K_v, dist_v, rvec_v, tvec_v, trail):
    try:
        rvec, tvec = _solve_pnp(
            _deep_deref(obj_v), _deep_deref(img_v),
            _deep_deref(K_v),   _deep_deref(dist_v))
    except Exception:
        yield (_fail, DONE); return
    if unify(rvec_v, rvec, trail) and unify(tvec_v, tvec, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

solve_pnp = _pred("solve_pnp",
    (6, _solve_pnp_6_dispatch),
    (7, _solve_pnp_7_dispatch),
)
```

### `solve_pnp_ransac/5,6` — tagged-tuple result

```python
def _solve_pnp_ransac(obj, img, K, dist, flags=None):
    cv = _cv()
    kwargs = {}
    if flags is not None:
        kwargs["flags"] = int(flags)
    ok, rvec, tvec, inliers = cv.solvePnPRansac(obj, img, K, dist, **kwargs)
    if not ok:
        raise RuntimeError("solvePnPRansac returned False")
    return ("pnp_ransac", rvec, tvec, inliers)

solve_pnp_ransac = _pred("solve_pnp_ransac",
    (5, _pure(_solve_pnp_ransac)),
    (6, _pure(lambda o, i, K, d, f: _solve_pnp_ransac(o, i, K, d, f))),
)
```

User decomposition in `.clausal`:

```clausal
solve_pnp_ransac(OBJ, IMG, K, DIST, R),
R is ("pnp_ransac", RVEC, TVEC, INLIERS)
```

### `calibrate_camera/4,5` — tagged-tuple result

```python
def _calibrate_camera(obj_list, img_list, image_size, flags=None):
    cv = _cv()
    kwargs = {}
    if flags is not None:
        kwargs["flags"] = int(flags)
    rms, K, dist, rvecs, tvecs = cv.calibrateCamera(
        obj_list, img_list, tuple(image_size), None, None, **kwargs)
    return ("calib", float(rms), K, dist, list(rvecs), list(tvecs))

calibrate_camera = _pred("calibrate_camera",
    (4, _pure(_calibrate_camera)),
    (5, _pure(lambda o, i, sz, f: _calibrate_camera(o, i, sz, f))),
)
```

### `rodrigues/2` — bijective via `_bidir_2`

```python
def _rodrigues_forward(rvec):
    rmat, _jac = _cv().Rodrigues(rvec)
    return rmat

def _rodrigues_backward(rmat):
    rvec, _jac = _cv().Rodrigues(rmat)
    return rvec

rodrigues = _pred("rodrigues",
    (2, _bidir_2(_rodrigues_forward, _rodrigues_backward)),
)
```

Note: `cv2.Rodrigues` *automatically* detects whether the input is a
3-vector or a matrix and switches direction. We could use a single
function for both directions in `_bidir_2`, but explicit separation
keeps the wrapper's mode dispatch predictable.

### `dft/2` — bijective

```python
def _dft_forward(img):
    return _cv().dft(img)

def _dft_backward(spec):
    return _cv().idft(spec)

dft = _pred("dft",
    (2, _bidir_2(_dft_forward, _dft_backward)),
    (3, _pure(lambda img, flags: _cv().dft(img, flags=int(flags)))),
)
```

### Constants exported

```python
_CONSTANT_NAMES |= frozenset([
    # Generic estimator methods
    "RANSAC", "LMEDS", "RHO",
    # Fundamental matrix methods
    "FM_7POINT", "FM_8POINT", "FM_RANSAC", "FM_LMEDS",
    # PnP methods
    "SOLVEPNP_ITERATIVE", "SOLVEPNP_EPNP", "SOLVEPNP_P3P",
    "SOLVEPNP_DLS", "SOLVEPNP_UPNP", "SOLVEPNP_AP3P",
    "SOLVEPNP_IPPE", "SOLVEPNP_IPPE_SQUARE", "SOLVEPNP_SQPNP",
    # Calibration flags
    "CALIB_USE_INTRINSIC_GUESS", "CALIB_FIX_PRINCIPAL_POINT",
    "CALIB_FIX_ASPECT_RATIO", "CALIB_ZERO_TANGENT_DIST",
    "CALIB_FIX_K1", "CALIB_FIX_K2", "CALIB_FIX_K3",
    "CALIB_FIX_K4", "CALIB_FIX_K5", "CALIB_FIX_K6",
    "CALIB_RATIONAL_MODEL",
    # Chessboard
    "CALIB_CB_ADAPTIVE_THRESH", "CALIB_CB_NORMALIZE_IMAGE",
    "CALIB_CB_FILTER_QUADS", "CALIB_CB_FAST_CHECK",
    # DFT flags
    "DFT_INVERSE", "DFT_SCALE", "DFT_ROWS", "DFT_COMPLEX_OUTPUT",
    "DFT_REAL_OUTPUT", "DFT_COMPLEX_INPUT",
])
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, IMREAD_GRAYSCALE,
    RANSAC, LMEDS, SOLVEPNP_ITERATIVE
])
-import_from(py.opencv_calib3d, [
    find_homography, find_homography_mask, find_fundamental_mat,
    solve_pnp, solve_pnp_ransac, rodrigues,
    find_chessboard_corners, calibrate_camera,
    project_points, undistort
])

# Synthetic point set for homography tests
Test("find_homography on 4 corner correspondences is exact") <- (
    SRC = ++(numpy.array([[0,0],[100,0],[100,100],[0,100]], dtype=numpy.float32)),
    DST = ++(numpy.array([[10,10],[110,10],[110,110],[10,110]], dtype=numpy.float32)),
    find_homography(SRC, DST, H),
    shape(H, [3, 3])
)

Test("find_homography_mask returns mask of inliers") <- (
    SRC = ++(numpy.array([[0,0],[100,0],[100,100],[0,100],[50,50]], dtype=numpy.float32)),
    DST = ++(numpy.array([[10,10],[110,10],[110,110],[10,110],[60,60]], dtype=numpy.float32)),
    find_homography_mask(SRC, DST, RANSAC, H, MASK),
    shape(H, [3, 3]),
    shape(MASK, [5, 1])
)

Test("rodrigues round-trips a rotation vector") <- (
    RVEC = ++(numpy.array([0.1, 0.2, 0.3], dtype=numpy.float64)),
    rodrigues(RVEC, RMAT),
    shape(RMAT, [3, 3]),
    rodrigues(RVEC2, RMAT),
    shape(RVEC2, [3, 1])
)

Test("rodrigues forward then backward is identity") <- (
    RVEC = ++(numpy.array([[0.1], [0.2], [0.3]], dtype=numpy.float64)),
    rodrigues(RVEC, RMAT),
    rodrigues(RVEC2, RMAT),
    ++(numpy.allclose(RVEC, RVEC2))
)

Test("solve_pnp_ransac returns tagged result") <- (
    # 6 known 3D points in a plane
    OBJ = ++(numpy.array(
        [[0,0,0],[1,0,0],[2,0,0],[0,1,0],[1,1,0],[2,1,0]], dtype=numpy.float32)),
    IMG = ++(numpy.array(
        [[100,100],[150,100],[200,100],[100,150],[150,150],[200,150]],
        dtype=numpy.float32)),
    K = ++(numpy.array([[800,0,320],[0,800,240],[0,0,1]], dtype=numpy.float64)),
    DIST = ++(numpy.zeros(5, dtype=numpy.float64)),
    solve_pnp_ransac(OBJ, IMG, K, DIST, R),
    R is ("pnp_ransac", _RVEC, _TVEC, _INLIERS)
)

Test("dft forward then inverse round-trips") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, GRAY_U8),
    F = ++(GRAY_U8.astype(numpy.float32)),
    dft(F, SPEC),
    dft(F2, SPEC),
    ++(numpy.allclose(F, F2, atol=0.01))
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase9_calib3d.clausal`:

- All Test cases above.
- `find_fundamental_mat` on synthetic 8-point correspondences.
- `find_chessboard_corners` on a synthetic checkerboard fixture
  generated programmatically (e.g. `numpy.kron` of a 4x6 pattern,
  then scaled).
- A small end-to-end calibration: 3-5 synthetic views of the
  checkerboard → `calibrate_camera` returns a non-empty K.
- `project_points` round-trip: project then solvePnP, recover
  approximately the input pose.
- `undistort` with zero distortion is identity.

### Python unit tests

None additional.

---

## Docs

`packages/clausal-opencv/docs/opencv_calib3d.md`:

- Intro: "Camera calibration, homography fitting, PnP, undistortion,
  and rotation representations. The pure-math half of OpenCV's
  computer-vision toolkit."
- Section per predicate group: homography, epipolar, PnP, calibration,
  projection/undistortion, rotation.
- Result-tuple terms (`pnp_ransac`, `calib`, `pose`) with
  decomposition examples.
- Refer to the [overview showcase](overview.md#step-9--showcase-example)
  for the homography-based stitching pipeline.

---

## Issues

### 1. Constants use lowercase aliases — INHERITED FROM PHASE 1

`RANSAC`, `LMEDS`, `RHO`, `FM_*`, `SOLVEPNP_*`, `CALIB_*`,
`CALIB_CB_*`, `DFT_*` exported under their lowercase forms. See
Phase 1 Issue 1.

### 2. Arities are 1-greater than input count — DISCOVERED DURING IMPLEMENTATION

When wrapping cv2 functions that take an input matrix plus a method
flag, the wrapper's `_pred` arity is **one greater** than the
number of cv2 input arguments because the RESULT var counts. For
`find_essential_mat`:

- `(pts1, pts2, K, E)`            — 4 user args, 3 cv2 inputs → arity 4
- `(pts1, pts2, K, method, E)`    — 5 user args, 4 cv2 inputs → arity 5

The phase plan's draft predicate catalogue used `/3, /4` because it
counted only cv2 inputs. The arities were corrected during
implementation. Tests for `find_essential_mat` and
`find_homography_mask` exercise both arity variants.

### 3. `==` against tagged result doesn't unify with vars — RECURRENT PHASE 4 ISSUE

`calibrate_camera(..., R), R == ("calib", _RMS, _K, ...)` does
**not** work — `==` is strict equality, not unification. The fix is
to pass the pattern directly to the producing predicate:
`calibrate_camera(..., ("calib", _RMS, _K, ...))`. Same trap as
Phase 4's contour/moments tests. Documented in
`opencv_calib3d.md`.

### 4. `find_fundamental_mat` / `find_essential_mat` reject degenerate configurations — DOCUMENTED

cv2's 8-point algorithm raises an internal assertion if the input
points are collinear or in a symmetric pattern. Initial tests using
a regular grid failed; rewritten to use `numpy.random.default_rng`
for reproducible random scattered points. Documented in
`opencv_calib3d.md` under "Fundamental / Essential matrices".

### 5. `calibrate_camera` needs ≥ 2 views — DOCUMENTED

A single view is under-determined; cv2 raises `m.dims >= 2`
internally. Tests pass two views with slightly translated image
points (synthetic — the recovered K is meaningless but the
tagged-tuple shape and list lengths are what we're verifying).

### 6. `cv2.HOGDescriptor` style positional-args is mirrored — N/A
   (this was a Phase 8 note; here for cross-reference only.)

### 7. `dft/2` is bidirectional via `_bidir_2` — IMPLEMENTED

Forward uses `DFT_COMPLEX_OUTPUT` (yields a complex-channel
ndarray). Backward uses `DFT_REAL_OUTPUT | DFT_SCALE` to recover the
original real-valued image. Round-trip verified via
`numpy.allclose(F, F2, atol=0.1)`. `dft/3` is forward-only with
user-supplied flags — useful when you want the imaginary part or
inverse-scale variants.

### 8. `M1TYPE` for `init_undistort_rectify_map` — TEST USES ESCAPE

`init_undistort_rectify_map/8` takes a CV-dtype constant
(`CV_32FC1`, `CV_16SC2`) for the map encoding. These aren't yet
exported under lowercase aliases — the test uses
`++__import__("cv2").CV_32FC1` as a fixture escape. Future work:
add `cv_32fc1` etc. to `_CONSTANTS`.

### 9. `findChessboardCorners` returns `(ok, corners)` — HANDLED

cv2 returns a (bool, corners) tuple. The wrapper unpacks and
returns `corners if ok else []`, so a failed find produces an empty
list rather than a failure. The list is empty so downstream
predicates can detect the failure with `length(CORNERS, 0)` or by
matching `[]`. Tests cover the success path; the failure path is
exercised in Phase 4 with `bounding_rect` on empty contours.

### 10. `matrix_allclose/4` — STILL DEFERRED

The `++(numpy.allclose(...))` escape from Phase 5 recurs in this
phase (rodrigues round-trip, dft round-trip). Decision: lift to a
dedicated check predicate once Phase 10 is in. Currently 3 test
cases use it; a fourth would tip into "lift it" territory.
