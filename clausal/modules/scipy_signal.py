"""Backward compatibility — canonical implementation in clausal.modules.py.scipy_signal."""
from clausal.modules.py.scipy_signal import *  # noqa: F401,F403
from clausal.modules.py.scipy_signal import (  # noqa: F401
    Butterworth,
    Bessel,
    ChebyshevType1,
    ChebyshevType2,
    Elliptic,
    FrequencyResponse,
    LinearFilter,
    SOSFilter,
    ForwardBackwardFilter,
    SOSForwardBackwardFilter,
    Decimate,
    Resample,
    Convolve,
    Correlate,
    FFTConvolve,
    Periodogram,
    Welch,
    Spectrogram,
    ResultGet,
)
