"""The ratio-unit vocabulary as DATA, with nothing constructed.

Kept out of ``units.py`` deliberately. The scale-in-a-name lint reads this
table on **every transform**, and importing ``clausal.modules.units`` builds
84 ``Quantity`` constants at import time -- each of which calls
``_units_flag.touch()``. ``clausal/logic/_units_flag.py`` promises in its own
docstring that "a program that imports no unit module pays nothing", and the
flag is read at six sites in ``clpfd.py`` and four in ``units_clp.py``, so
turning it on makes every CLP program take the units side-channel branch.

Reading a vocabulary must not be the thing that breaks that promise. Landed
2026-09-12 after the lint's `from clausal.modules import units` did exactly
that, pinned by
``test_transforming_a_unit_free_file_does_not_import_the_units_module``.

Mirrors ``clausal.modules.countries._data``, which is a data-only module for
the same reason and which the same lint already reads.
"""
from __future__ import annotations

#: name -> decimal exponent. **The authority for the ratio vocabulary**: the
#: scale-in-a-name lint reads it from here, and ``units.py`` builds the
#: bindings from it, so adding a ratio unit extends both with no second edit.
#: ``units.RATIO_UNITS`` re-exports this same object.
RATIO_UNITS = {
    "percent":     2,
    "basis_point": 4,
}
