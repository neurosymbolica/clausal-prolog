"""One boolean: has this process ever built a Quantity or declared a units
variable? The units side channel around CLP (clausal.logic.units_clp)
checks it before walking any expression tree.

Granularity, honestly: the unit modules (clausal.modules.units, imperial,
the currency minor units) build Quantity constants at IMPORT time, so
importing any of them turns the channel on for the process. A program that
imports no unit module pays nothing; one that does pays one tree scan per
non-integer comparison post, measured indistinguishable from the baseline
on an interleaved A/B (spec §3.1). Kept in its own module because both
clausal.terms and clausal.logic.units_constraint set it and neither may
import the other at module level.
"""

active = False


def touch() -> None:
    global active
    if not active:
        active = True
