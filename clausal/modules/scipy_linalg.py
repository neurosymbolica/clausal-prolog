"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_linalg."""
from clausal.modules.py.scipy_linalg import *  # noqa: F401,F403
from clausal.modules.py.scipy_linalg import (  # noqa: F401
    _ScipyLinalgPredicate, _dispatch_fn, _la_fn, _la_kw, _pred, _la,
    Solve, LeastSquares, SolveTriangular,
    LuDecompose, QrDecompose, SingularValueDecompose,
    Cholesky, EigenDecompose, EigenDecomposeHermitian, Schur,
    Inverse, PseudoInverse, Determinant, Norm,
    MatrixExpLog, MatrixSquareRoot, MatrixFunction,
    LuFactor, LuSolve, CholeskyFactor, CholeskySolve,
    ResultGet,
)
