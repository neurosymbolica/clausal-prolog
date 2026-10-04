"""clausal.modules.py.scipy_spatial — scipy.spatial predicates for Clausal.

Provides spatial algorithms from scipy.spatial as importable predicate objects
for use in .clausal files via::

    -import_from(scipy_spatial, [cross_distance, pairwise_distance, make_kd_tree, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_spatial, [cross_distance, ...])

Tiers
-----
**Tier 1 — pure distance functions** (no handle):
    cross_distance, pairwise_distance, square_form, point_distance

**Tier 3 — handle-based spatial objects**:
    KD-tree:    make_kd_tree, kd_tree_query, kd_tree_query_ball, kd_tree_query_pairs
    ConvexHull: make_convex_hull, convex_hull_attr
    Delaunay:   make_delaunay, delaunay_find_simplex
    Rotation:   make_rotation, rotation_apply, rotation_as, rotation_compose,
                rotation_inverse
    Lifecycle:  free

Predicate catalogue
-------------------

Distance functions (Tier 1, pure):
    cross_distance(XA, XB, RESULT)
    cross_distance(XA, XB, METRIC, RESULT)
    cross_distance(XA, XB, METRIC, KWARGS, RESULT)
        → scipy.spatial.distance.cdist(XA, XB, metric=METRIC, **(KWARGS or {}))
        Compute pairwise distances between each row of XA and each row of XB.
        RESULT: (nA × nB) distance matrix.

    pairwise_distance(X, RESULT)
    pairwise_distance(X, METRIC, RESULT)
    pairwise_distance(X, METRIC, KWARGS, RESULT)
        → scipy.spatial.distance.pdist(X, metric=METRIC, **(KWARGS or {}))
        Compute condensed pairwise distance vector for all pairs within X.
        RESULT: condensed 1-D distance array of length n*(n-1)/2.

    square_form(X, RESULT)
        → scipy.spatial.distance.squareform(X)
        Convert between condensed distance vector and square distance matrix.

    point_distance(METRIC, X, Y, RESULT)
        → scipy.spatial.distance.cdist([X], [Y], metric=METRIC)[0, 0]
        Compute a single scalar distance between points X and Y using the
        named metric (e.g. 'euclidean', 'cosine', 'cityblock').

KD-tree (Tier 3):
    make_kd_tree(DATA, RESULT)
    make_kd_tree(DATA, LEAFSIZE, RESULT)
        → scipy.spatial.KDTree(data, leafsize=LEAFSIZE)
        Build a KD-tree for fast nearest-neighbour lookup.
        RESULT: integer HANDLE.

    kd_tree_query(HANDLE, X, RESULT)
    kd_tree_query(HANDLE, X, K, RESULT)
        → handle.query(x, k=K)
        Query HANDLE for the K nearest neighbours of each point in X.
        RESULT: dict with keys 'distances' and 'indices'.

    kd_tree_query_ball(HANDLE, X, RADIUS, RESULT)
        → handle.query_ball_point(x, r)
        find all points within RADIUS of each point in X.
        RESULT: list of index lists (one per query point).

    kd_tree_query_pairs(HANDLE, RADIUS, RESULT)
        → handle.query_pairs(r)
        find all pairs of points within RADIUS of each other.
        RESULT: set of (i, j) index pairs.

ConvexHull (Tier 3):
    make_convex_hull(POINTS, RESULT)
        → scipy.spatial.ConvexHull(points)
        Compute the convex hull of a set of points.
        RESULT: integer HANDLE.

    convex_hull_attr(HANDLE, ATTR, RESULT)
        Retrieve an attribute of the ConvexHull object.
        ATTR: 'vertices', 'simplices', 'equations', 'area', 'volume',
              'coplanar', 'neighbors'
        RESULT: the attribute value (array, float, etc.).

Delaunay triangulation (Tier 3):
    make_delaunay(POINTS, RESULT)
        → scipy.spatial.Delaunay(points)
        Compute the Delaunay triangulation of a set of points.
        RESULT: integer HANDLE.

    delaunay_find_simplex(HANDLE, XI, RESULT)
    delaunay_find_simplex(HANDLE, XI, BRUTEFORCE, RESULT)
        → handle.find_simplex(xi, bruteforce=BRUTEFORCE)
        find the simplex containing each point in XI.
        RESULT: array of simplex indices (-1 if outside triangulation).

Rotation (Tier 3, from scipy.spatial.transform):
    make_rotation(METHOD, DATA, RESULT)
        → scipy.spatial.transform.Rotation.from_<method>(data)
        Construct a rotation from the given representation.
        METHOD: 'quat', 'matrix', 'rotvec', 'mrp'
                'euler' requires DATA = (seq, angles) e.g. ('xyz', angles_array)
        RESULT: integer HANDLE.

    rotation_apply(HANDLE, VECTORS, RESULT)
    rotation_apply(HANDLE, VECTORS, INVERSE, RESULT)
        → handle.apply(vectors, inverse=INVERSE)
        Apply the rotation to an array of vectors.
        RESULT: rotated vectors array.

    rotation_as(HANDLE, FORM, RESULT)
    rotation_as(HANDLE, FORM, SEQ, RESULT)
        → handle.as_quat() / as_matrix() / as_rotvec() / as_euler(seq)
        Export the rotation to the requested representation.
        FORM: 'quat', 'matrix', 'rotvec', 'mrp', 'euler'
        SEQ: required when FORM='euler', e.g. 'xyz'

    rotation_compose(HANDLE_A, HANDLE_B, RESULT)
        → handle_a * handle_b
        Compose two rotations (right-to-left: HANDLE_B applied first).
        RESULT: integer HANDLE for the composed rotation.

    rotation_inverse(HANDLE, RESULT)
        → handle.inv()
        Invert a rotation.
        RESULT: integer HANDLE for the inverse rotation.

Lifecycle:
    free(HANDLE)
        Release the object registered under HANDLE.  Always succeeds.

Usage example::

    -import_from(scipy_spatial, [cross_distance, make_kd_tree, kd_tree_query, free])

    closest_pair(POINTS, DISTANCES) <- (
        make_kd_tree(POINTS, KD),
        kd_tree_query(KD, POINTS, 2, R),
        DISTANCES is ++(R['distances'][:, 1]),
        free(KD)
    )
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

import numpy as _np

from clausal.logic.variables import deref, unify
from clausal.modules.py._helpers import _text_arg
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
        inputs = [_text_arg(x) for x in args[:-2]]
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
        inputs = [_text_arg(x) for x in args[:-2]]
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
        raw = [_text_arg(x) for x in args[:-2]]
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

# ── cross_distance ─────────────────────────────────────────────────────────
# Arity = number of args visible to user INCLUDING RESULT, excluding trail.
# cross_distance(XA, XB, RESULT) → arity 3
# cross_distance(XA, XB, METRIC, RESULT) → arity 4
# cross_distance(XA, XB, METRIC, KWARGS, RESULT) → arity 5

cross_distance = _pred("cross_distance",
    (3, _pure(lambda xa, xb:
        _dist().cdist(xa, xb))),
    (4, _pure(lambda xa, xb, metric:
        _dist().cdist(xa, xb, metric=metric))),
    (5, _pure(lambda xa, xb, metric, kwargs:
        _dist().cdist(xa, xb, metric=metric, **(kwargs or {})))),
)

# ── pairwise_distance ──────────────────────────────────────────────────────
# pairwise_distance(X, RESULT) → arity 2
# pairwise_distance(X, METRIC, RESULT) → arity 3
# pairwise_distance(X, METRIC, KWARGS, RESULT) → arity 4

pairwise_distance = _pred("pairwise_distance",
    (2, _pure(lambda x:
        _dist().pdist(x))),
    (3, _pure(lambda x, metric:
        _dist().pdist(x, metric=metric))),
    (4, _pure(lambda x, metric, kwargs:
        _dist().pdist(x, metric=metric, **(kwargs or {})))),
)

# ── square_form ────────────────────────────────────────────────────────────
# square_form(X, RESULT) → arity 2

square_form = _pred("square_form",
    (2, _pure(lambda x:
        _dist().squareform(x))),
)

# ── point_distance ─────────────────────────────────────────────────────────
# point_distance(METRIC, X, Y, RESULT) → arity 4

def _point_distance(metric, x, y):
    xa = _np.atleast_2d(x)
    ya = _np.atleast_2d(y)
    return float(_dist().cdist(xa, ya, metric=metric)[0, 0])

point_distance = _pred("point_distance",
    (4, _pure(lambda metric, x, y: _point_distance(metric, x, y))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — KD-tree
# ═══════════════════════════════════════════════════════════════════════════

# ── make_kd_tree ────────────────────────────────────────────────────────────
# make_kd_tree(DATA, RESULT) → arity 2
# make_kd_tree(DATA, LEAFSIZE, RESULT) → arity 3

make_kd_tree = _pred("make_kd_tree",
    (2, _make(lambda data:
        _sp().KDTree(data))),
    (3, _make(lambda data, leafsize:
        _sp().KDTree(data, leafsize=int(leafsize)))),
)

# ── kd_tree_query ───────────────────────────────────────────────────────────
# kd_tree_query(HANDLE, X, RESULT) → arity 3
# kd_tree_query(HANDLE, X, K, RESULT) → arity 4

def _kdtree_query(obj, x):
    distances, indices = obj.query(x, k=1)
    return {"distances": distances, "indices": indices}

def _kdtree_query_k(obj, x, k):
    distances, indices = obj.query(x, k=int(k))
    return {"distances": distances, "indices": indices}

kd_tree_query = _pred("kd_tree_query",
    (3, _query(_kdtree_query)),
    (4, _query(_kdtree_query_k)),
)

# ── kd_tree_query_ball ───────────────────────────────────────────────────────
# kd_tree_query_ball(HANDLE, X, RADIUS, RESULT) → arity 4

kd_tree_query_ball = _pred("kd_tree_query_ball",
    (4, _query(lambda obj, x, radius:
        obj.query_ball_point(x, float(radius)))),
)

# ── kd_tree_query_pairs ──────────────────────────────────────────────────────
# kd_tree_query_pairs(HANDLE, RADIUS, RESULT) → arity 3

kd_tree_query_pairs = _pred("kd_tree_query_pairs",
    (3, _query(lambda obj, radius:
        obj.query_pairs(float(radius)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — ConvexHull
# ═══════════════════════════════════════════════════════════════════════════

# ── make_convex_hull ────────────────────────────────────────────────────────
# make_convex_hull(POINTS, RESULT) → arity 2

make_convex_hull = _pred("make_convex_hull",
    (2, _make(lambda points:
        _sp().ConvexHull(points))),
)

# ── convex_hull_attr ────────────────────────────────────────────────────────
# convex_hull_attr(HANDLE, ATTR, RESULT) → arity 3

def _convex_hull_attr(obj, attr):
    return getattr(obj, str(attr))

convex_hull_attr = _pred("convex_hull_attr",
    (3, _query(_convex_hull_attr)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Delaunay
# ═══════════════════════════════════════════════════════════════════════════

# ── make_delaunay ──────────────────────────────────────────────────────────
# make_delaunay(POINTS, RESULT) → arity 2

make_delaunay = _pred("make_delaunay",
    (2, _make(lambda points:
        _sp().Delaunay(points))),
)

# ── delaunay_find_simplex ───────────────────────────────────────────────────
# delaunay_find_simplex(HANDLE, XI, RESULT) → arity 3
# delaunay_find_simplex(HANDLE, XI, BRUTEFORCE, RESULT) → arity 4

delaunay_find_simplex = _pred("delaunay_find_simplex",
    (3, _query(lambda obj, xi:
        obj.find_simplex(xi))),
    (4, _query(lambda obj, xi, bruteforce:
        obj.find_simplex(xi, bruteforce=bool(bruteforce)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Rotation (scipy.spatial.transform)
# ═══════════════════════════════════════════════════════════════════════════

# ── make_rotation ─────────────────────────────────────────────────────────

_ROTATION_CONSTRUCTORS = {
    "quat":   lambda data: _transform().Rotation.from_quat(data),
    "matrix": lambda data: _transform().Rotation.from_matrix(data),
    "rotvec": lambda data: _transform().Rotation.from_rotvec(data),
    "mrp":    lambda data: _transform().Rotation.from_mrp(data),
    "euler":  lambda data: _transform().Rotation.from_euler(
        _text_arg(data[0]), deref(data[1])),
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
    method = _text_arg(args[0])
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

# make_rotation(METHOD, DATA, RESULT) → arity 3
make_rotation = _pred("make_rotation",
    (3, _make_rotation_dispatch),
)

# ── rotation_apply ─────────────────────────────────────────────────────────

# rotation_apply(HANDLE, VECTORS, RESULT) → arity 3
# rotation_apply(HANDLE, VECTORS, INVERSE, RESULT) → arity 4
rotation_apply = _pred("rotation_apply",
    (3, _query(lambda obj, vectors:
        obj.apply(vectors))),
    (4, _query(lambda obj, vectors, inverse:
        obj.apply(vectors, inverse=bool(inverse)))),
)

# ── rotation_as ────────────────────────────────────────────────────────────

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

# rotation_as(HANDLE, FORM, RESULT) → arity 3
# rotation_as(HANDLE, FORM, SEQ, RESULT) → arity 4
rotation_as = _pred("rotation_as",
    (3, _query(_rotation_as)),
    (4, _query(_rotation_as_euler)),
)

# ── rotation_compose ───────────────────────────────────────────────────────

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

# rotation_compose(HANDLE_A, HANDLE_B, RESULT) → arity 3
rotation_compose = _pred("rotation_compose",
    (3, _rotation_compose_dispatch),
)

# ── rotation_inverse ───────────────────────────────────────────────────────

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

# rotation_inverse(HANDLE, RESULT) → arity 2
rotation_inverse = _pred("rotation_inverse",
    (2, _rotation_inverse_dispatch),
)


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle — free
# ═══════════════════════════════════════════════════════════════════════════

def _free_dispatch(this_generator, _proceed, _fail, _catcher, handle, trail):
    try:
        with _registry_lock:
            _SPATIAL_REGISTRY.pop(int(deref(handle)), None)
    except Exception:
        pass
    yield (_proceed, None)
    yield (_fail, DONE)

free = _pred("free",
    (1, _free_dispatch),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    "cross_distance",
    "pairwise_distance",
    "square_form",
    "point_distance",
    "make_kd_tree",
    "kd_tree_query",
    "kd_tree_query_ball",
    "kd_tree_query_pairs",
    "make_convex_hull",
    "convex_hull_attr",
    "make_delaunay",
    "delaunay_find_simplex",
    "make_rotation",
    "rotation_apply",
    "rotation_as",
    "rotation_compose",
    "rotation_inverse",
    "free",
    "_SPATIAL_REGISTRY",
]
