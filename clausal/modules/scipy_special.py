"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_special."""
from clausal.modules.py.scipy_special import *  # noqa: F401,F403
from clausal.modules.py.scipy_special import (  # noqa: F401
    _ScipySpecialPredicate, _dispatch_fn, _sp_fn, _sp_kw, _pred, _sp,
    Gamma, GammaLog, GammaSign, BetaLog, Digamma, Polygamma,
    Factorial, Comb, Perm,
    Erf, ErfComplement, ErfInverse, ErfComplementInverse,
    NormalCdf, NormalCdfInverse,
    BesselJ, BesselY, BesselJReal, BesselYReal, BesselK, BesselI,
    BesselJZeros, SphericalBesselJ,
    EllipticK, EllipticE, EllipticKIncomplete, EllipticEIncomplete,
    Hypergeometric1F1, Hypergeometric2F1, Hypergeometric0F1,
    Entr, KlDivergence, LogSumExp,
    AssocLegendre, LegendrePoly, ChebyshevT, ChebyshevU,
    HermiteH, GeneralizedLaguerre,
    CubeRoot, Exp10, Exp2, Sigmoid, Logit, LambertW, XLogY, XLog1pY,
)
