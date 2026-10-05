# `opencv_calib3d` — Camera calibration and 3D geometry

Homography fitting, fundamental/essential matrices, Perspective-n-Point
(PnP), camera calibration, projection, undistortion, rotation
representations, plus DFT as a frequency-domain math tool. The
pure-math half of OpenCV's computer-vision toolkit.

All predicates are **Tier 1 (pure)**. Inputs are NumPy ndarrays and
scalars; outputs are fresh ndarrays or tagged tuples.

```seam
-import_from(opencv_calib3d, [
    find_homography, find_homography_mask,
    find_fundamental_mat, find_essential_mat,
    solve_pnp, solve_pnp_ransac,
    calibrate_camera, find_chessboard_corners, corner_sub_pix,
    project_points, undistort, init_undistort_rectify_map,
    rodrigues, decompose_homography_mat, recover_pose, dft,
])
-import_from(opencv, [ransac, lmeds, solvepnp_iterative])
```

## Tagged result terms

Three new tagged tuples ship in this phase:

| Term | From | Decomposes as |
|---|---|---|
| `("pnp_ransac", RVEC, TVEC, INLIERS)` | `solve_pnp_ransac/5,6` | rvec, tvec ndarrays + inlier indices |
| `("calib", RMS, K, DIST, RVECS, TVECS)` | `calibrate_camera/4,5` | float, 3×3, dist coefs, list of rvecs, list of tvecs |
| `("pose", R, T, MASK, N_INLIERS)` | `recover_pose/5` | rotation, translation, mask, inlier count |

As elsewhere in the wrapper (Phases 4, 7), **prefer passing the
pattern directly to the producing predicate** rather than splitting
into "bind result, then `==` against pattern" — `==` is strict
equality and does not unify into `_` placeholders inside structures.

```seam
% Recommended
solve_pnp_ransac(OBJ, IMG, K, DIST, ("pnp_ransac", RVEC, TVEC, INLIERS))

% Equivalent for fully-bound expected results — but rarely useful
solve_pnp_ransac(OBJ, IMG, K, DIST, R),
R == ("pnp_ransac", RVEC0, TVEC0, INLIERS0)   % only if RVEC0 etc are bound first
```

## Homography

| Predicate | Arity | Returns |
|---|---|---|
| `find_homography(SRC, DST, H)` | /3 | `H` only (mask discarded) |
| `find_homography(SRC, DST, METHOD, H)` | /4 | `METHOD` is `ransac`, `lmeds`, `rho`, or `0` for least-squares |
| `find_homography_mask(SRC, DST, METHOD, H, MASK)` | /5 | Both `H` and inlier mask |
| `find_homography_mask(SRC, DST, METHOD, THRESH, H, MASK)` | /6 | With explicit RANSAC reprojection threshold |

```seam
find_homography(SRC, DST, H)
find_homography_mask(SRC, DST, ransac, H, MASK)
```

## Fundamental / Essential matrices

| Predicate | Arity | Notes |
|---|---|---|
| `find_fundamental_mat(PTS1, PTS2, F)` | /3 | Default method=ransac |
| `find_fundamental_mat(PTS1, PTS2, METHOD, F)` | /4 | `fm_7point`, `fm_8point`, `fm_ransac`, `fm_lmeds` |
| `find_essential_mat(PTS1, PTS2, K, E)` | /4 | With intrinsics |
| `find_essential_mat(PTS1, PTS2, K, METHOD, E)` | /5 | |

Point sets must be **diverse** — collinear or degenerate
configurations cause cv2 to fail with an internal assertion. The
test fixtures use `numpy.random.default_rng(seed).random(...)` to
generate reproducible random points.

## PnP — Perspective-n-Point

| Predicate | Arity | Returns |
|---|---|---|
| `solve_pnp(OBJ_PTS, IMG_PTS, K, DIST, RVEC, TVEC)` | /6 | `RVEC` is a 3×1 Rodrigues vector |
| `solve_pnp(OBJ_PTS, IMG_PTS, K, DIST, FLAGS, RVEC, TVEC)` | /7 | `FLAGS = solvepnp_iterative`, `solvepnp_epnp`, `solvepnp_p3p`, ... |
| `solve_pnp_ransac(OBJ_PTS, IMG_PTS, K, DIST, RESULT)` | /5 | RESULT = `("pnp_ransac", RVEC, TVEC, INLIERS)` |
| `solve_pnp_ransac(..., FLAGS, RESULT)` | /6 | |

`OBJ_PTS` is an `(N, 3)` float32 array, `IMG_PTS` is `(N, 2)` float32.
`K` is the 3×3 camera matrix, `DIST` is a 5-element distortion vector
(`numpy.zeros(5)` for no distortion).

## Calibration

| Predicate | Arity | Description |
|---|---|---|
| `find_chessboard_corners(IMG, PATTERN_SIZE, CORNERS)` | /3 | Returns `[]` if pattern not found |
| `find_chessboard_corners(IMG, PATTERN_SIZE, FLAGS, CORNERS)` | /4 | `calib_cb_*` flags |
| `corner_sub_pix(IMG, CORNERS, WIN, ZERO_ZONE, REFINED)` | /5 | Default termination criteria |
| `corner_sub_pix(..., CRITERIA, REFINED)` | /6 | Explicit `(type, max_iter, epsilon)` |
| `calibrate_camera(OBJ_LIST, IMG_LIST, IMAGE_SIZE, RESULT)` | /4 | RESULT = `("calib", RMS, K, DIST, RVECS, TVECS)` |
| `calibrate_camera(..., FLAGS, RESULT)` | /5 | `calib_*` flags |

**`calibrate_camera` needs ≥ 2 views.** A single view is
under-determined and cv2 will raise an internal assertion. Pass
matching-length `OBJ_LIST` and `IMG_LIST`.

```seam
calibrate_camera([OBJP, OBJP], [IMGP1, IMGP2], [640, 480],
                   ("calib", RMS, K, DIST, RVECS, TVECS))
```

## Projection and undistortion

| Predicate | Arity | Returns |
|---|---|---|
| `project_points(OBJ, RVEC, TVEC, K, DIST, IMG_PTS, JAC)` | /7 | Both image points and jacobian |
| `undistort(IMG, K, DIST, OUT)` | /4 | |
| `undistort(IMG, K, DIST, NEW_K, OUT)` | /5 | With override camera matrix |
| `init_undistort_rectify_map(K, DIST, R, NEW_K, SIZE, M1TYPE, MAP1, MAP2)` | /8 | Used by `remap` (Phase 5) |

`M1TYPE` is one of `cv2.CV_32FC1`, `cv2.CV_16SC2` — currently passed
via `++cv2.CV_32FC1` since these dtype constants aren't yet exported
under lowercase aliases (filed as future work).

## Rotation — Rodrigues (bidirectional)

```
rodrigues(RVEC, RMAT)
```

`cv2.Rodrigues` is **self-inverse**: a 3-vector input produces a
3×3 rotation matrix output, and a 3×3 matrix input produces a
3-vector. The wrapper exposes this as a bidirectional predicate via
`_bidir_2`:

- `(+RVEC, -RMAT)`: forward — compute rotation matrix.
- `(-RVEC, +RMAT)`: backward — compute rotation vector.

```seam
RVEC is ++(numpy.array([[0.1], [0.2], [0.3]], dtype=numpy.float64)),
rodrigues(RVEC, RMAT),
rodrigues(RVEC2, RMAT),         % backward — RVEC2 should be RVEC
++(numpy.allclose(RVEC, RVEC2))
```

## Decompose homography / recover pose

| Predicate | Arity | Description |
|---|---|---|
| `decompose_homography_mat(H, K, SOLUTIONS)` | /3 | List of `(R, T, N)` 3-tuples |
| `recover_pose(E, PTS1, PTS2, K, RESULT)` | /5 | RESULT = `("pose", R, T, MASK, N_INLIERS)` |

## DFT — bidirectional

```
dft(IMG, SPEC)
dft(IMG, FLAGS, SPEC)
```

`dft/2` is bidirectional, like `rodrigues`:

- `(+IMG, -SPEC)`: forward — calls `cv2.dft(IMG, flags=DFT_COMPLEX_OUTPUT)`.
- `(-IMG, +SPEC)`: backward — calls `cv2.idft(SPEC, flags=DFT_REAL_OUTPUT | DFT_SCALE)`.

`dft/3` is forward-only with user-supplied flags.

```seam
F is ++(GRAY_U8.astype(numpy.float32)),
dft(F, SPEC),
dft(F2, SPEC),                    % backward
++(numpy.allclose(F, F2, atol=0.1))
```

## Worked examples

The examples below are exact copies of the integration tests in
`tests/fixtures/opencv_phase9_calib3d.seam`.

### Homography from 4 corner correspondences

```seam
SRC is ++(numpy.array([[0,0],[100,0],[100,100],[0,100]], dtype=numpy.float32)),
DST is ++(numpy.array([[10,10],[110,10],[110,110],[10,110]], dtype=numpy.float32)),
find_homography(SRC, DST, H),
shape(H, [3, 3])
```

### Homography with RANSAC inlier mask

```seam
find_homography_mask(SRC, DST, ransac, H, MASK),
shape(H, [3, 3]),
shape(MASK, [5, 1])
```

### PnP from 6 coplanar object points

```seam
OBJ is ++(numpy.array(
    [[0,0,0],[1,0,0],[2,0,0],[0,1,0],[1,1,0],[2,1,0]],
    dtype=numpy.float32)),
IMG is ++(numpy.array(
    [[100,100],[150,100],[200,100],[100,150],[150,150],[200,150]],
    dtype=numpy.float32)),
K is ++(numpy.array([[800,0,320],[0,800,240],[0,0,1]], dtype=numpy.float64)),
DIST is ++(numpy.zeros(5, dtype=numpy.float64)),
solve_pnp(OBJ, IMG, K, DIST, RVEC, TVEC),
shape(RVEC, [3, 1]), shape(TVEC, [3, 1])
```

### Rodrigues self-inverse

```seam
RVEC is ++(numpy.array([[0.1], [0.2], [0.3]], dtype=numpy.float64)),
rodrigues(RVEC, RMAT),
rodrigues(RVEC2, RMAT),
++(numpy.allclose(RVEC, RVEC2))
```

### DFT forward then inverse round-trips

```seam
F is ++(GRAY_U8.astype(numpy.float32)),
dft(F, SPEC),
dft(F2, SPEC),
++(numpy.allclose(F, F2, atol=0.1))
```

## See also

- [`opencv`](opencv.md) — `ransac`, `lmeds`, `solvepnp_*`,
  `calib_*`, `dft_*` constants.
- [`opencv_features`](opencv_features.md) — provides the
  KeyPoint/DMatch lists from which you extract the
  `(N, 2)` `SRC`/`DST` point arrays for homography.
- [`opencv_imgproc`](opencv_imgproc.md) — `remap` (Phase 5) consumes
  the `MAP1`/`MAP2` output of `init_undistort_rectify_map`.
