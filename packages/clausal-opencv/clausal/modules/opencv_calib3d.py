"""clausal.modules.opencv_calib3d — Camera calibration and 3D geometry.

Phase 9 — Camera Calibration and Homography.

3D geometry: homography fitting, fundamental/essential matrices,
Perspective-n-Point (PnP), camera calibration, projection,
undistortion, and rotation representations. Plus DFT as a frequency-
domain math tool.

All predicates are **Tier 1 (pure)**. Inputs are NumPy ndarrays and
scalars; outputs are fresh ndarrays or tagged tuples.

Use::

    -import_from(opencv_calib3d, [
        find_homography, find_homography_mask,
        find_fundamental_mat, find_essential_mat,
        solve_pnp, solve_pnp_ransac,
        calibrate_camera, find_chessboard_corners, corner_sub_pix,
        project_points, undistort, init_undistort_rectify_map,
        rodrigues, decompose_homography_mat, recover_pose, dft,
    ])
    -import_from(opencv, [ransac, lmeds, solvepnp_iterative])

Tagged result terms
-------------------
- ``("pnp_ransac", RVEC, TVEC, INLIERS)`` — output of
  ``solve_pnp_ransac/5,6``.
- ``("calib", RMS, K, DIST, RVECS, TVECS)`` — output of
  ``calibrate_camera/4,5``.
- ``("pose", R, T, MASK, N_INLIERS)`` — output of ``recover_pose/5``.
"""

from __future__ import annotations

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import (
    _pred, _pure, _deep_deref, _bidir_2,
)
from clausal.modules.opencv import _cv


# ══════════════════════════════════════════════════════════════════════════
# Homography and epipolar geometry
# ══════════════════════════════════════════════════════════════════════════
#
# cv2.findHomography returns ``(H, mask)``. The wrapper splits this into:
# - ``find_homography/3,4`` — returns just ``H`` (mask discarded)
# - ``find_homography_mask/4,5`` — returns both ``H`` and ``mask``


def _find_homography_3(src, dst):
    H, _mask = _cv().findHomography(src, dst)
    return H

def _find_homography_4(src, dst, method):
    H, _mask = _cv().findHomography(src, dst, int(method))
    return H


find_homography = _pred("find_homography",
    (3, _pure(_find_homography_3)),
    (4, _pure(_find_homography_4)),
)


def _fh_mask_4(this_generator, _proceed, _fail, _catcher,
               src_v, dst_v, method_v, H_v, mask_v, trail):
    src = _deep_deref(src_v)
    dst = _deep_deref(dst_v)
    method = int(deref(method_v))
    try:
        H, mask = _cv().findHomography(src, dst, method)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(H_v, H, trail) and unify(mask_v, mask, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


def _fh_mask_5(this_generator, _proceed, _fail, _catcher,
               src_v, dst_v, method_v, thresh_v, H_v, mask_v, trail):
    src = _deep_deref(src_v)
    dst = _deep_deref(dst_v)
    method = int(deref(method_v))
    thresh = float(deref(thresh_v))
    try:
        H, mask = _cv().findHomography(src, dst, method, thresh)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(H_v, H, trail) and unify(mask_v, mask, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


find_homography_mask = _pred("find_homography_mask",
    (5, _fh_mask_4),     # (src, dst, method, H, mask) = 5 visible args
    (6, _fh_mask_5),     # (src, dst, method, thresh, H, mask) = 6 visible args
)


def _find_fundamental(pts1, pts2):
    F, _mask = _cv().findFundamentalMat(pts1, pts2)
    return F

def _find_fundamental_4(pts1, pts2, method):
    F, _mask = _cv().findFundamentalMat(pts1, pts2, method=int(method))
    return F


find_fundamental_mat = _pred("find_fundamental_mat",
    (3, _pure(_find_fundamental)),
    (4, _pure(_find_fundamental_4)),
)


def _find_essential(pts1, pts2, K):
    E, _mask = _cv().findEssentialMat(pts1, pts2, K)
    return E

def _find_essential_4(pts1, pts2, K, method):
    E, _mask = _cv().findEssentialMat(pts1, pts2, K, method=int(method))
    return E


find_essential_mat = _pred("find_essential_mat",
    # (pts1, pts2, K, E)        = 4 user args, 3 inputs
    (4, _pure(_find_essential)),
    # (pts1, pts2, K, method, E) = 5 user args, 4 inputs
    (5, _pure(_find_essential_4)),
)


# ══════════════════════════════════════════════════════════════════════════
# PnP
# ══════════════════════════════════════════════════════════════════════════


def _solve_pnp_6(this_generator, _proceed, _fail, _catcher,
                 obj_v, img_v, K_v, dist_v, rvec_v, tvec_v, trail):
    obj = _deep_deref(obj_v)
    img = _deep_deref(img_v)
    K = _deep_deref(K_v)
    dist = _deep_deref(dist_v)
    try:
        ok, rvec, tvec = _cv().solvePnP(obj, img, K, dist)
    except Exception:
        yield (_fail, DONE)
        return
    if not ok:
        yield (_fail, DONE)
        return
    if unify(rvec_v, rvec, trail) and unify(tvec_v, tvec, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


def _solve_pnp_7(this_generator, _proceed, _fail, _catcher,
                 obj_v, img_v, K_v, dist_v, flags_v, rvec_v, tvec_v, trail):
    obj = _deep_deref(obj_v)
    img = _deep_deref(img_v)
    K = _deep_deref(K_v)
    dist = _deep_deref(dist_v)
    flags = int(deref(flags_v))
    try:
        ok, rvec, tvec = _cv().solvePnP(obj, img, K, dist, flags=flags)
    except Exception:
        yield (_fail, DONE)
        return
    if not ok:
        yield (_fail, DONE)
        return
    if unify(rvec_v, rvec, trail) and unify(tvec_v, tvec, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


solve_pnp = _pred("solve_pnp",
    (6, _solve_pnp_6),
    (7, _solve_pnp_7),
)


def _solve_pnp_ransac(obj, img, K, dist, flags=None):
    kwargs = {}
    if flags is not None:
        kwargs["flags"] = int(flags)
    ok, rvec, tvec, inliers = _cv().solvePnPRansac(obj, img, K, dist, **kwargs)
    if not ok:
        raise RuntimeError("solvePnPRansac returned False")
    return ("pnp_ransac", rvec, tvec, inliers)


solve_pnp_ransac = _pred("solve_pnp_ransac",
    (5, _pure(_solve_pnp_ransac)),
    (6, _pure(lambda o, i, K, d, f: _solve_pnp_ransac(o, i, K, d, f))),
)


# ══════════════════════════════════════════════════════════════════════════
# Calibration
# ══════════════════════════════════════════════════════════════════════════


def _find_chessboard_3(img, pattern_size):
    ok, corners = _cv().findChessboardCorners(img, tuple(pattern_size))
    return corners if ok else []


def _find_chessboard_4(img, pattern_size, flags):
    ok, corners = _cv().findChessboardCorners(img, tuple(pattern_size),
                                                 flags=int(flags))
    return corners if ok else []


find_chessboard_corners = _pred("find_chessboard_corners",
    (3, _pure(_find_chessboard_3)),
    (4, _pure(_find_chessboard_4)),
)


def _corner_sub_pix_5(img, corners, win_size, zero_zone):
    cv = _cv()
    criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    return cv.cornerSubPix(img, corners,
                              tuple(win_size), tuple(zero_zone),
                              criteria)


def _corner_sub_pix_6(img, corners, win_size, zero_zone, criteria):
    return _cv().cornerSubPix(img, corners,
                                  tuple(win_size), tuple(zero_zone),
                                  tuple(criteria))


corner_sub_pix = _pred("corner_sub_pix",
    (5, _pure(_corner_sub_pix_5)),
    (6, _pure(_corner_sub_pix_6)),
)


def _calibrate_camera_4(obj_list, img_list, image_size):
    rms, K, dist, rvecs, tvecs = _cv().calibrateCamera(
        list(obj_list), list(img_list), tuple(image_size), None, None)
    return ("calib", float(rms), K, dist, list(rvecs), list(tvecs))


def _calibrate_camera_5(obj_list, img_list, image_size, flags):
    rms, K, dist, rvecs, tvecs = _cv().calibrateCamera(
        list(obj_list), list(img_list), tuple(image_size), None, None,
        flags=int(flags))
    return ("calib", float(rms), K, dist, list(rvecs), list(tvecs))


calibrate_camera = _pred("calibrate_camera",
    (4, _pure(_calibrate_camera_4)),
    (5, _pure(_calibrate_camera_5)),
)


# ══════════════════════════════════════════════════════════════════════════
# Projection and undistortion
# ══════════════════════════════════════════════════════════════════════════


def _project_points(this_generator, _proceed, _fail, _catcher,
                    obj_v, rvec_v, tvec_v, K_v, dist_v,
                    img_pts_v, jacobian_v, trail):
    obj = _deep_deref(obj_v)
    rvec = _deep_deref(rvec_v)
    tvec = _deep_deref(tvec_v)
    K = _deep_deref(K_v)
    dist = _deep_deref(dist_v)
    try:
        img_pts, jacobian = _cv().projectPoints(obj, rvec, tvec, K, dist)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(img_pts_v, img_pts, trail) and unify(jacobian_v, jacobian, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


project_points = _pred("project_points", (7, _project_points))


undistort = _pred("undistort",
    (4, _pure(lambda img, K, dist: _cv().undistort(img, K, dist))),
    (5, _pure(lambda img, K, dist, new_K:
              _cv().undistort(img, K, dist, newCameraMatrix=new_K))),
)


def _init_undistort(this_generator, _proceed, _fail, _catcher,
                    K_v, dist_v, R_v, new_K_v, size_v, m1type_v,
                    map1_v, map2_v, trail):
    K = _deep_deref(K_v)
    dist = _deep_deref(dist_v)
    R = _deep_deref(R_v)
    new_K = _deep_deref(new_K_v)
    size = tuple(_deep_deref(size_v))
    m1type = int(deref(m1type_v))
    try:
        map1, map2 = _cv().initUndistortRectifyMap(K, dist, R, new_K, size, m1type)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(map1_v, map1, trail) and unify(map2_v, map2, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


init_undistort_rectify_map = _pred("init_undistort_rectify_map",
    (8, _init_undistort),
)


# ══════════════════════════════════════════════════════════════════════════
# Rotation: Rodrigues (bidirectional self-inverse)
# ══════════════════════════════════════════════════════════════════════════


def _rodrigues_forward(rvec):
    rmat, _jac = _cv().Rodrigues(rvec)
    return rmat


def _rodrigues_backward(rmat):
    rvec, _jac = _cv().Rodrigues(rmat)
    return rvec


rodrigues = _pred("rodrigues",
    (2, _bidir_2(_rodrigues_forward, _rodrigues_backward)),
)


# ══════════════════════════════════════════════════════════════════════════
# Homography decomposition / pose recovery
# ══════════════════════════════════════════════════════════════════════════


def _decompose_homography(H, K):
    n, Rs, Ts, Ns = _cv().decomposeHomographyMat(H, K)
    return [(Rs[i], Ts[i], Ns[i]) for i in range(int(n))]


decompose_homography_mat = _pred("decompose_homography_mat",
    (3, _pure(_decompose_homography)),
)


def _recover_pose(E, pts1, pts2, K):
    n_inliers, R, t, mask = _cv().recoverPose(E, pts1, pts2, K)
    return ("pose", R, t, mask, int(n_inliers))


recover_pose = _pred("recover_pose",
    (5, _pure(_recover_pose)),
)


# ══════════════════════════════════════════════════════════════════════════
# DFT (bidirectional)
# ══════════════════════════════════════════════════════════════════════════


def _dft_forward(img):
    return _cv().dft(img, flags=_cv().DFT_COMPLEX_OUTPUT)


def _dft_backward(spec):
    return _cv().idft(spec, flags=_cv().DFT_REAL_OUTPUT | _cv().DFT_SCALE)


dft = _pred("dft",
    (2, _bidir_2(_dft_forward, _dft_backward)),
    (3, _pure(lambda img, flags: _cv().dft(img, flags=int(flags)))),
)


__all__ = [
    # Homography / epipolar
    "find_homography", "find_homography_mask",
    "find_fundamental_mat", "find_essential_mat",
    # PnP
    "solve_pnp", "solve_pnp_ransac",
    # Calibration
    "find_chessboard_corners", "corner_sub_pix", "calibrate_camera",
    # Projection / undistortion
    "project_points", "undistort", "init_undistort_rectify_map",
    # Rotation / pose
    "rodrigues", "decompose_homography_mat", "recover_pose",
    # DFT
    "dft",
]
