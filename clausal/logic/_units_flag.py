"""One boolean: has this process ever built a Quantity or declared a units
variable? The units side channel around CLP (clausal.logic.units_clp)
checks it before walking any expression tree, so a program that uses no
units pays nothing for the feature. Kept in its own module because both
clausal.terms and clausal.logic.units_constraint set it and neither may
import the other at module level.
"""

active = False


def touch() -> None:
    global active
    if not active:
        active = True
