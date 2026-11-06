# clausal/logic/clpq/__init__.py
"""CLP(Q): constraint logic programming over the rationals.

The solver is the port of clp(q,r) 1.3.3 (PROVENANCE.md); the package
exports the API of ``holzbaur.py``.  The solver Clausal shipped before it
was retired by operator ruling 2026-11-05 ("we should retire legacy
CLPQ"): ``CLAUSAL_CLPQ=legacy`` raises a ValueError naming that, and any
value other than ``holzbaur`` is refused, as before.
"""
import os as _os

SOLVER = _os.environ.get("CLAUSAL_CLPQ", "holzbaur")
if SOLVER == "legacy":
    raise ValueError(
        "CLAUSAL_CLPQ=legacy was removed after clausal 1.4.0 (operator "
        "ruling 2026-11-05); the port of clp(q,r) 1.3.3 is the only CLP(Q) "
        "solver: unset CLAUSAL_CLPQ or set it to holzbaur")
if SOLVER != "holzbaur":
    raise ValueError(f"CLAUSAL_CLPQ must be holzbaur (or unset), not {SOLVER!r}")

#: The names the package exports: holzbaur.py's API.
HOLZBAUR_API = (
    "Q_KEY", "q_eq", "q_ne", "q_le", "q_lt", "q_gt", "q_ge", "in_q", "sup",
    "inf", "maximize", "minimize", "entailed", "dump_q", "residual_q",
    "residual_q_goals",
    "dump", "bb_inf", "int_minimize", "clpq_constraint_block", "clpq_constraint_answers",
    "sync_fd_bounds", "ordering")

from clausal.logic.clpq import holzbaur as _holzbaur  # noqa: E402
for _name in HOLZBAUR_API:
    globals()[_name] = getattr(_holzbaur, _name)
del _name
