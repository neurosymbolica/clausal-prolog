"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_optimize."""
from clausal.modules.py.scipy_optimize import *  # noqa: F401,F403
from clausal.modules.py.scipy_optimize import (  # noqa: F401
    _SciPyOptimizePredicate,
    MinimizeScalar, Minimize,
    DifferentialEvolution, BasinHopping, DualAnnealing, ShgoMinimize,
    NonlinearLeastSquares, CurveFit,
    RootScalar, Root,
    LinearProgram, MixedIntegerLinearProgram,
    LinearConstraint, Bounds,
    ResultGet,
)
