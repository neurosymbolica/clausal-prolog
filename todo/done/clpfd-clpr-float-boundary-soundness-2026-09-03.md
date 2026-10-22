# clpfd<->clpr float-boundary soundness: in-range one-ULP inward rounding + finite out-of-int64 UB

Two related gaps at the FD->real sync seam, found by review 2026-09-03 (phase2-prereq Task 1):
1. _sync_real applies no OUTWARD rounding for in-range bignum bounds: float(2**60+1) rounds to
   nearest, which for a HI bound is inward — unsound by one ULP. clpr has _dn/_up for exactly
   this (clausal/logic/clpr.py); use them at the sync site.
2. _clpfd_propagate.c:3028-3029 casts (int64_t)ceil(r_lo)/(int64_t)floor(r_hi) guarding only
   +/-HUGE_VAL: a FINITE double beyond int64 range (e.g. RealVar.lo == sys.float_info.max, now
   storable via _safe_float_lo; or a user interval like [1e300, inf]) is C UB. The Python twin
   (clpfd.py:2043-2044) uses exact math.ceil and does not clamp — the twins disagree. Add
   finite-range clamps to the C cast, twin-consistent.
Same seam, one reviewer, do together.
