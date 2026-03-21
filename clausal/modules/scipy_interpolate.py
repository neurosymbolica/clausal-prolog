"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_interpolate."""
from clausal.modules.py.scipy_interpolate import *  # noqa: F401,F403
from clausal.modules.py.scipy_interpolate import (  # noqa: F401
    MakeSpline,
    MakeCubic,
    MakePCHIP,
    MakeAkima,
    MakeLinear1D,
    MakeRegularGrid,
    MakeRadialBasis,
    EvalSpline,
    EvalRegularGrid,
    EvalRadialBasis,
    SplineIntegral,
    SplineDerivative,
    SplineRoots,
    Free,
)
