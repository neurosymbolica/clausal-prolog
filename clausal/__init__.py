"""clausal — logic programming for Python.

Top-level public API (Step 7 and later).
"""

# Extend __path__ so that separately-installed backend distributions
# (e.g. clausal-trealla, clausal-gprolog, clausal-scryer) that place
# subpackages under clausal/ in site-packages are discoverable.
import os as _os, site as _site
for _sp in _site.getsitepackages():
    _candidate = _os.path.join(_sp, "clausal")
    if _os.path.isdir(_candidate) and _candidate not in __path__:
        __path__.append(_candidate)

from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.logic.database import Module, Database, Clause
from clausal.logic.variables import Var, Trail, deref, unify, UnboundVarCoercionError
from clausal.terms import Compound, KWTerm, Quantity, UnitsMismatch
from clausal.logic.builtins import (
    structural_unify,
    get_builtin_class,
    _BUILTIN_CLASSES,
)
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.exceptions import LogicException
from clausal.repl import Solutions
import clausal._lazy_hook as _lazy_hook  # registers lightweight stub finder


# ── Export all builtin predicate classes as top-level names ────────────────────
# This lets users write: from clausal import append, between, in_, length, ...

def _export_builtin_classes():
    """Inject all builtin PredicateMeta classes into this module's namespace."""
    import sys
    mod = sys.modules[__name__]
    names = []
    for name, cls in _BUILTIN_CLASSES.items():
        setattr(mod, name, cls)
        names.append(name)
    return names

_builtin_names = _export_builtin_classes()


__all__ = [
    # Query API
    "call",
    "solve",
    "query",
    "once",
    # Runtime objects
    "Module",
    "Database",
    "Clause",
    "Var",
    "Trail",
    "Compound",
    "KWTerm",
    "Quantity",
    "UnitsMismatch",
    "deref",
    "unify",
    "UnboundVarCoercionError",
    "structural_unify",
    "PredicateMeta",
    "make_predicate",
    "LogicException",
    "get_builtin_class",
    "Solutions",
    # All builtin predicate classes
    *_builtin_names,
]
