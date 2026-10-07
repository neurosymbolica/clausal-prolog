"""The sandbox switch, read on hot paths (:mod:`clausal.sandbox`).

No imports on purpose: the engine's dispatch paths read :data:`ACTIVE` with
one attribute load, and importing this module costs nothing.  Only
:func:`clausal.sandbox.enable` writes here, once; nothing turns it off.
"""

#: True once :func:`clausal.sandbox.enable` ran (or ``CLAUSAL_SANDBOX=1``
#: at engine import).  Process-wide and irreversible.
ACTIVE = False
