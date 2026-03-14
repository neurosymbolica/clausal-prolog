"""clausal — logic programming for Python.

Top-level public API (Step 7 and later).
"""

from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.logic.database import Module, Database, Clause
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Compound, KWTerm
from clausal.logic.builtins import structural_unify
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.exceptions import LogicException

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
    "deref",
    "unify",
    "structural_unify",
    "PredicateMeta",
    "make_predicate",
    "LogicException",
]
