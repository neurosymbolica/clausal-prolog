"""clausal — logic programming for Python.

Top-level public API (Step 7 and later).
"""

from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.logic.database import Module, Database, Clause
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Compound, KWTerm, Dimensioned, UnitsMismatch
from clausal.logic.builtins import (
    structural_unify,
    get_builtin_class,
    _BUILTIN_CLASSES,
)
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.exceptions import LogicException


# ── Export all builtin predicate classes as top-level names ────────────────────
# This lets users write: from clausal import Append, Between, In, Length, ...

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
    "Dimensioned",
    "UnitsMismatch",
    "deref",
    "unify",
    "structural_unify",
    "PredicateMeta",
    "make_predicate",
    "LogicException",
    "get_builtin_class",
    # All builtin predicate classes
    *_builtin_names,
]
