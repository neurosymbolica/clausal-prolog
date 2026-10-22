# clausal/logic/clpq/__init__.py
"""CLP(Q): constraint logic programming over the rationals.

``CLAUSAL_CLPQ`` selects the solver: ``legacy`` (default, the pre-2026-10-12
solver) or ``holzbaur`` (the port of clp(q,r) 1.3.3, see PROVENANCE.md).
The package exports the same names under either: legacy's, and under
``holzbaur`` the API of ``holzbaur.py`` in place of legacy's.  Both
solvers' attribute hooks are registered whichever is selected (ruling R1);
only the selected one's API puts attributes.
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

#: The names holzbaur.py provides in place of legacy's.
HOLZBAUR_API = (
    "Q_KEY", "q_eq", "q_ne", "q_le", "q_lt", "q_gt", "q_ge", "in_q", "sup",
    "inf", "maximize", "minimize", "entailed", "dump_q", "residual_q",
    "dump", "bb_inf", "clpq_constraint_block", "clpq_constraint_answers",
    "sync_fd_bounds", "ordering")

if SOLVER == "holzbaur":
    from clausal.logic.clpq import holzbaur as _holzbaur  # noqa: E402
    for _name in HOLZBAUR_API:
        globals()[_name] = getattr(_holzbaur, _name)
