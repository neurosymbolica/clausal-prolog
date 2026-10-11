# clausal/logic/clpq/__init__.py
"""CLP(Q): constraint logic programming over the rationals.

``CLAUSAL_CLPQ`` selects the solver: ``legacy`` (default, the pre-2026-10-12
solver) or ``holzbaur`` (the port of clp(q,r) 1.3.3, see PROVENANCE.md).
"""
import os as _os

SOLVER = _os.environ.get("CLAUSAL_CLPQ", "legacy")
if SOLVER not in ("legacy", "holzbaur"):
    raise ValueError(f"CLAUSAL_CLPQ must be legacy or holzbaur, not {SOLVER!r}")

from clausal.logic.clpq.legacy import *  # noqa: E402,F401,F403
from clausal.logic.clpq import legacy as _legacy  # noqa: E402

# Private names other modules import today (Q_KEY users, tests, the CLI).
for _name in dir(_legacy):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)
