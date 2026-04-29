"""clausal.modules.scipy_spatial — scipy.spatial predicates for Clausal.

Provides spatial algorithms from scipy.spatial as importable predicate objects
for use in .clausal files via::

    -import_from(scipy_spatial, [CrossDistance, PairwiseDistance, MakeKdTree, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_spatial, [CrossDistance, ...])

Tiers
-----
**Tier 1 — pure distance functions** (no handle):
    CrossDistance, PairwiseDistance, SquareForm, PointDistance

**Tier 3 — handle-based spatial objects**:
    KD-tree:    MakeKdTree, KdTreeQuery, KdTreeQueryBall, KdTreeQueryPairs
    ConvexHull: MakeConvexHull, ConvexHullAttr
    Delaunay:   MakeDelaunay, DelaunayFindSimplex
    Rotation:   MakeRotation, RotationApply, RotationAs, RotationCompose,
                RotationInverse
    Lifecycle:  Free

Predicate catalogue
-------------------

Distance functions (Tier 1, pure):
    CrossDistance(XA, XB, RESULT)
    CrossDistance(XA, XB, METRIC, RESULT)
    CrossDistance(XA, XB, METRIC, KWARGS, RESULT)
        → scipy.spatial.distance.cdist(XA, XB, metric=METRIC, **(KWARGS or {}))
        Compute pairwise distances between each row of XA and each row of XB.
        RESULT: (nA × nB) distance matrix.

    PairwiseDistance(X, RESULT)
    PairwiseDistance(X, METRIC, RESULT)
    PairwiseDistance(X, METRIC, KWARGS, RESULT)
        → scipy.spatial.distance.pdist(X, metric=METRIC, **(KWARGS or {}))
        Compute condensed pairwise distance vector for all pairs within X.
        RESULT: condensed 1-D distance array of length n*(n-1)/2.

    SquareForm(X, RESULT)
        → scipy.spatial.distance.squareform(X)
        Convert between condensed distance vector and square distance matrix.

    PointDistance(METRIC, X, Y, RESULT)
        → scipy.spatial.distance.cdist([X], [Y], metric=METRIC)[0, 0]
        Compute a single scalar distance between points X and Y using the
        named metric (e.g. 'euclidean', 'cosine', 'cityblock').

KD-tree (Tier 3):
    MakeKdTree(DATA, RESULT)
    MakeKdTree(DATA, LEAFSIZE, RESULT)
        → scipy.spatial.KDTree(data, leafsize=LEAFSIZE)
        Build a KD-tree for fast nearest-neighbour lookup.
        RESULT: integer HANDLE.

    KdTreeQuery(HANDLE, X, RESULT)
    KdTreeQuery(HANDLE, X, K, RESULT)
        → handle.query(x, k=K)
        Query HANDLE for the K nearest neighbours of each point in X.
        RESULT: dict with keys 'distances' and 'indices'.

    KdTreeQueryBall(HANDLE, X, RADIUS, RESULT)
        → handle.query_ball_point(x, r)
        Find all points within RADIUS of each point in X.
        RESULT: list of index lists (one per query point).

    KdTreeQueryPairs(HANDLE, RADIUS, RESULT)
        → handle.query_pairs(r)
        Find all pairs of points within RADIUS of each other.
        RESULT: set of (i, j) index pairs.

ConvexHull (Tier 3):
    MakeConvexHull(POINTS, RESULT)
        → scipy.spatial.ConvexHull(points)
        Compute the convex hull of a set of points.
        RESULT: integer HANDLE.

    ConvexHullAttr(HANDLE, ATTR, RESULT)
        Retrieve an attribute of the ConvexHull object.
        ATTR: 'vertices', 'simplices', 'equations', 'area', 'volume',
              'coplanar', 'neighbors'
        RESULT: the attribute value (array, float, etc.).

Delaunay triangulation (Tier 3):
    MakeDelaunay(POINTS, RESULT)
        → scipy.spatial.Delaunay(points)
        Compute the Delaunay triangulation of a set of points.
        RESULT: integer HANDLE.

    DelaunayFindSimplex(HANDLE, XI, RESULT)
    DelaunayFindSimplex(HANDLE, XI, BRUTEFORCE, RESULT)
        → handle.find_simplex(xi, bruteforce=BRUTEFORCE)
        Find the simplex containing each point in XI.
        RESULT: array of simplex indices (-1 if outside triangulation).

Rotation (Tier 3, from scipy.spatial.transform):
    MakeRotation(METHOD, DATA, RESULT)
        → scipy.spatial.transform.Rotation.from_<method>(data)
        Construct a rotation from the given representation.
        METHOD: 'quat', 'matrix', 'rotvec', 'mrp'
                'euler' requires DATA = (seq, angles) e.g. ('xyz', angles_array)
        RESULT: integer HANDLE.

    RotationApply(HANDLE, VECTORS, RESULT)
    RotationApply(HANDLE, VECTORS, INVERSE, RESULT)
        → handle.apply(vectors, inverse=INVERSE)
        Apply the rotation to an array of vectors.
        RESULT: rotated vectors array.

    RotationAs(HANDLE, FORM, RESULT)
    RotationAs(HANDLE, FORM, SEQ, RESULT)
        → handle.as_quat() / as_matrix() / as_rotvec() / as_euler(seq)
        Export the rotation to the requested representation.
        FORM: 'quat', 'matrix', 'rotvec', 'mrp', 'euler'
        SEQ: required when FORM='euler', e.g. 'xyz'

    RotationCompose(HANDLE_A, HANDLE_B, RESULT)
        → handle_a * handle_b
        Compose two rotations (right-to-left: HANDLE_B applied first).
        RESULT: integer HANDLE for the composed rotation.

    RotationInverse(HANDLE, RESULT)
        → handle.inv()
        Invert a rotation.
        RESULT: integer HANDLE for the inverse rotation.

Lifecycle:
    Free(HANDLE)
        Release the object registered under HANDLE.  Always succeeds.

Usage example::

    -import_from(scipy_spatial, [CrossDistance, MakeKdTree, KdTreeQuery, Free])

    closest_pair(POINTS, DISTANCES) <- (
        MakeKdTree(POINTS, KD),
        KdTreeQuery(KD, POINTS, 2, R),
        DISTANCES is ++(R['distances'][:, 1]),
        Free(KD)
    )
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

import numpy as _np

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Lazy scipy imports ────────────────────────────────────────────────────

_scipy_spatial = None
_scipy_distance = None
_scipy_transform = None
_spatial_lock = _threading.Lock()


def _ensure_spatial():
    global _scipy_spatial, _scipy_distance, _scipy_transform
    if _scipy_spatial is not None:
        return
    with _spatial_lock:
        if _scipy_spatial is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_spatial = _import_stdlib("scipy.spatial")
        _scipy_distance = _import_stdlib("scipy.spatial.distance")
        _scipy_transform = _import_stdlib("scipy.spatial.transform")


def _sp():
    _ensure_spatial()
    return _scipy_spatial


def _dist():
    _ensure_spatial()
    return _scipy_distance


def _transform():
    _ensure_spatial()
    return _scipy_transform


# ── Handle registry ───────────────────────────────────────────────────────

_SPATIAL_REGISTRY: dict[int, object] = {}
_registry_lock = _threading.Lock()
_registry_counter = [0]


def _alloc_handle(obj: object) -> int:
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _SPATIAL_REGISTRY[handle] = obj
    return handle


def _lookup_handle(handle: int) -> object:
    obj = _SPATIAL_REGISTRY.get(int(handle))
    if obj is None:
        raise KeyError(f"Unknown spatial handle: {handle!r}")
    return obj


def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Tier 1 dispatch helpers ───────────────────────────────────────────────

def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


# ── Tier 3 dispatch helpers ───────────────────────────────────────────────

def _make(constructor: Callable) -> Callable:
    """Deref inputs, construct object, alloc handle, unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            obj = constructor(*inputs)
            handle = _alloc_handle(obj)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, handle, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _query(evaluator: Callable) -> Callable:
    """Deref inputs, look up handle from first input, call evaluator, unify."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        raw = [deref(x) for x in args[:-2]]
        try:
            obj = _lookup_handle(raw[0])
            out = evaluator(obj, *raw[1:])
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _make_returning_handle(constructor: Callable) -> Callable:
    """Like _make but the constructor returns an object that gets a new handle."""
    return _make(constructor)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 1 — distance functions
# ═══════════════════════════════════════════════════════════════════════════

# ── CrossDistance ─────────────────────────────────────────────────────────
# Arity = number of args visible to user INCLUDING RESULT, excluding trail.
# CrossDistance(XA, XB, RESULT) → arity 3
# CrossDistance(XA, XB, METRIC, RESULT) → arity 4
# CrossDistance(XA, XB, METRIC, KWARGS, RESULT) → arity 5

CrossDistance = _pred("CrossDistance",
    (3, _pure(lambda xa, xb:
        _dist().cdist(xa, xb))),
    (4, _pure(lambda xa, xb, metric:
        _dist().cdist(xa, xb, metric=metric))),
    (5, _pure(lambda xa, xb, metric, kwargs:
        _dist().cdist(xa, xb, metric=metric, **(kwargs or {})))),
)

# ── PairwiseDistance ──────────────────────────────────────────────────────
# PairwiseDistance(X, RESULT) → arity 2
# PairwiseDistance(X, METRIC, RESULT) → arity 3
# PairwiseDistance(X, METRIC, KWARGS, RESULT) → arity 4

PairwiseDistance = _pred("PairwiseDistance",
    (2, _pure(lambda x:
        _dist().pdist(x))),
    (3, _pure(lambda x, metric:
        _dist().pdist(x, metric=metric))),
    (4, _pure(lambda x, metric, kwargs:
        _dist().pdist(x, metric=metric, **(kwargs or {})))),
)

# ── SquareForm ────────────────────────────────────────────────────────────
# SquareForm(X, RESULT) → arity 2

SquareForm = _pred("SquareForm",
    (2, _pure(lambda x:
        _dist().squareform(x))),
)

# ── PointDistance ─────────────────────────────────────────────────────────
# PointDistance(METRIC, X, Y, RESULT) → arity 4

def _point_distance(metric, x, y):
    xa = _np.atleast_2d(x)
    ya = _np.atleast_2d(y)
    return float(_dist().cdist(xa, ya, metric=metric)[0, 0])

PointDistance = _pred("PointDistance",
    (4, _pure(lambda metric, x, y: _point_distance(metric, x, y))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — KD-tree
# ═══════════════════════════════════════════════════════════════════════════

# ── MakeKdTree ────────────────────────────────────────────────────────────
# MakeKdTree(DATA, RESULT) → arity 2
# MakeKdTree(DATA, LEAFSIZE, RESULT) → arity 3

MakeKdTree = _pred("MakeKdTree",
    (2, _make(lambda data:
        _sp().KDTree(data))),
    (3, _make(lambda data, leafsize:
        _sp().KDTree(data, leafsize=int(leafsize)))),
)

# ── KdTreeQuery ───────────────────────────────────────────────────────────
# KdTreeQuery(HANDLE, X, RESULT) → arity 3
# KdTreeQuery(HANDLE, X, K, RESULT) → arity 4

def _kdtree_query(obj, x):
    distances, indices = obj.query(x, k=1)
    return {"distances": distances, "indices": indices}

def _kdtree_query_k(obj, x, k):
    distances, indices = obj.query(x, k=int(k))
    return {"distances": distances, "indices": indices}

KdTreeQuery = _pred("KdTreeQuery",
    (3, _query(_kdtree_query)),
    (4, _query(_kdtree_query_k)),
)

# ── KdTreeQueryBall ───────────────────────────────────────────────────────
# KdTreeQueryBall(HANDLE, X, RADIUS, RESULT) → arity 4

KdTreeQueryBall = _pred("KdTreeQueryBall",
    (4, _query(lambda obj, x, radius:
        obj.query_ball_point(x, float(radius)))),
)

# ── KdTreeQueryPairs ──────────────────────────────────────────────────────
# KdTreeQueryPairs(HANDLE, RADIUS, RESULT) → arity 3

KdTreeQueryPairs = _pred("KdTreeQueryPairs",
    (3, _query(lambda obj, radius:
        obj.query_pairs(float(radius)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — ConvexHull
# ═══════════════════════════════════════════════════════════════════════════

# ── MakeConvexHull ────────────────────────────────────────────────────────
# MakeConvexHull(POINTS, RESULT) → arity 2

MakeConvexHull = _pred("MakeConvexHull",
    (2, _make(lambda points:
        _sp().ConvexHull(points))),
)

# ── ConvexHullAttr ────────────────────────────────────────────────────────
# ConvexHullAttr(HANDLE, ATTR, RESULT) → arity 3

def _convex_hull_attr(obj, attr):
    return getattr(obj, str(attr))

ConvexHullAttr = _pred("ConvexHullAttr",
    (3, _query(_convex_hull_attr)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Delaunay
# ═══════════════════════════════════════════════════════════════════════════

# ── MakeDelaunay ──────────────────────────────────────────────────────────
# MakeDelaunay(POINTS, RESULT) → arity 2

MakeDelaunay = _pred("MakeDelaunay",
    (2, _make(lambda points:
        _sp().Delaunay(points))),
)

# ── DelaunayFindSimplex ───────────────────────────────────────────────────
# DelaunayFindSimplex(HANDLE, XI, RESULT) → arity 3
# DelaunayFindSimplex(HANDLE, XI, BRUTEFORCE, RESULT) → arity 4

DelaunayFindSimplex = _pred("DelaunayFindSimplex",
    (3, _query(lambda obj, xi:
        obj.find_simplex(xi))),
    (4, _query(lambda obj, xi, bruteforce:
        obj.find_simplex(xi, bruteforce=bool(bruteforce)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Rotation (scipy.spatial.transform)
# ═══════════════════════════════════════════════════════════════════════════

# ── MakeRotation ─────────────────────────────────────────────────────────

_ROTATION_CONSTRUCTORS = {
    "quat":   lambda data: _transform().Rotation.from_quat(data),
    "matrix": lambda data: _transform().Rotation.from_matrix(data),
    "rotvec": lambda data: _transform().Rotation.from_rotvec(data),
    "mrp":    lambda data: _transform().Rotation.from_mrp(data),
    "euler":  lambda data: _transform().Rotation.from_euler(data[0], data[1]),
}

def _make_rotation(method, data):
    key = str(method).lower()
    constructor = _ROTATION_CONSTRUCTORS.get(key)
    if constructor is None:
        raise ValueError(f"Unknown rotation method: {method!r}")
    return constructor(data)

def _make_rotation_dispatch(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    method = deref(args[0])
    data = deref(args[1])
    try:
        rot = _make_rotation(method, data)
        handle = _alloc_handle(rot)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(result_var, handle, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

# MakeRotation(METHOD, DATA, RESULT) → arity 3
MakeRotation = _pred("MakeRotation",
    (3, _make_rotation_dispatch),
)

# ── RotationApply ─────────────────────────────────────────────────────────

# RotationApply(HANDLE, VECTORS, RESULT) → arity 3
# RotationApply(HANDLE, VECTORS, INVERSE, RESULT) → arity 4
RotationApply = _pred("RotationApply",
    (3, _query(lambda obj, vectors:
        obj.apply(vectors))),
    (4, _query(lambda obj, vectors, inverse:
        obj.apply(vectors, inverse=bool(inverse)))),
)

# ── RotationAs ────────────────────────────────────────────────────────────

def _rotation_as(obj, form):
    key = str(form).lower()
    if key == "quat":
        return obj.as_quat()
    if key == "matrix":
        return obj.as_matrix()
    if key == "rotvec":
        return obj.as_rotvec()
    if key == "mrp":
        return obj.as_mrp()
    raise ValueError(f"Unknown rotation form: {form!r}; use 'euler' form with SEQ argument")

def _rotation_as_euler(obj, form, seq):
    if str(form).lower() != "euler":
        raise ValueError(f"SEQ argument only valid for form='euler', got {form!r}")
    return obj.as_euler(str(seq))

# RotationAs(HANDLE, FORM, RESULT) → arity 3
# RotationAs(HANDLE, FORM, SEQ, RESULT) → arity 4
RotationAs = _pred("RotationAs",
    (3, _query(_rotation_as)),
    (4, _query(_rotation_as_euler)),
)

# ── RotationCompose ───────────────────────────────────────────────────────

def _rotation_compose_dispatch(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    handle_a = int(deref(args[0]))
    handle_b = int(deref(args[1]))
    try:
        rot_a = _lookup_handle(handle_a)
        rot_b = _lookup_handle(handle_b)
        composed = rot_a * rot_b
        handle = _alloc_handle(composed)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(result_var, handle, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

# RotationCompose(HANDLE_A, HANDLE_B, RESULT) → arity 3
RotationCompose = _pred("RotationCompose",
    (3, _rotation_compose_dispatch),
)

# ── RotationInverse ───────────────────────────────────────────────────────

def _rotation_inverse_dispatch(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    handle = int(deref(args[0]))
    try:
        rot = _lookup_handle(handle)
        inv_rot = rot.inv()
        new_handle = _alloc_handle(inv_rot)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(result_var, new_handle, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

# RotationInverse(HANDLE, RESULT) → arity 2
RotationInverse = _pred("RotationInverse",
    (2, _rotation_inverse_dispatch),
)


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle — Free
# ═══════════════════════════════════════════════════════════════════════════

def _free_dispatch(this_generator, _proceed, _fail, _catcher, handle, trail):
    try:
        with _registry_lock:
            _SPATIAL_REGISTRY.pop(int(deref(handle)), None)
    except Exception:
        pass
    yield (_proceed, None)
    yield (_fail, DONE)

Free = _pred("Free",
    (1, _free_dispatch),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    "CrossDistance",
    "PairwiseDistance",
    "SquareForm",
    "PointDistance",
    "MakeKdTree",
    "KdTreeQuery",
    "KdTreeQueryBall",
    "KdTreeQueryPairs",
    "MakeConvexHull",
    "ConvexHullAttr",
    "MakeDelaunay",
    "DelaunayFindSimplex",
    "MakeRotation",
    "RotationApply",
    "RotationAs",
    "RotationCompose",
    "RotationInverse",
    "Free",
    "_SPATIAL_REGISTRY",
]
