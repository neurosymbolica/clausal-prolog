"""Shim — canonical implementation in clausal.modules.py.scipy_spatial."""
from clausal.modules.py.scipy_spatial import *  # noqa: F401,F403
from clausal.modules.py.scipy_spatial import (  # noqa: F401
    CrossDistance,
    PairwiseDistance,
    SquareForm,
    PointDistance,
    MakeKdTree,
    KdTreeQuery,
    KdTreeQueryBall,
    KdTreeQueryPairs,
    MakeConvexHull,
    ConvexHullAttr,
    MakeDelaunay,
    DelaunayFindSimplex,
    MakeRotation,
    RotationApply,
    RotationAs,
    RotationCompose,
    RotationInverse,
    Free,
)
