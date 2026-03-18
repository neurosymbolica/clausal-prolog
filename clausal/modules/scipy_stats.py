"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_stats."""
from clausal.modules.py.scipy_stats import *  # noqa: F401,F403
from clausal.modules.py.scipy_stats import (  # noqa: F401
    _SciPyStatsPredicate,
    StatsDescribe, StatsMean, StatsGeometricMean, StatsHarmonicMean,
    StatsMode, StatsSkew, StatsKurtosis, StatsInterquartileRange,
    StatsZScore, StatsMedianAbsoluteDeviation,
    StatsPearsonCorrelation, StatsSpearmanCorrelation, StatsKendallTau,
    StatsLinearRegression, StatsTheilSlopes,
    StatsTTest1Sample, StatsTTestIndependent, StatsTTestRelated,
    StatsChiSquare, StatsChiSquareContingency, StatsFisherExact,
    StatsMannWhitneyU, StatsWilcoxon, StatsKruskal, StatsKs2samp,
    StatsNormalityTest, StatsShapiro,
    StatsDist,
    StatsNormalPdf, StatsNormalCdf, StatsNormalPpf, StatsNormalRvs,
    StatsFreezeDist, StatsFrozenPdf, StatsFrozenCdf, StatsFrozenPpf,
    StatsFrozenRvs, StatsFrozenStats, StatsFrozenFree,
    ResultGet,
)
